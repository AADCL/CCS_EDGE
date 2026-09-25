"""Build V6 navigation products from an already map-frame CCS PCD.

Never run pcd_transform_node here: the downloaded cloud is public_map.pcd,
not the mapper's camera_init cloud. All generated files remain under CCS.
"""
import copy
import fcntl
import hashlib
import json
import math
import os
import shutil
import signal
import struct
import subprocess
import tempfile
import time
from pathlib import Path

import yaml

LAYERS = {'elevation': 4, 'slope_deg': 4, 'roughness': 4,
          'step_height': 4, 'cost': 1, 'confidence': 1}


def contained(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if os.path.commonpath([str(path), str(root)]) != str(root) or path == root:
        raise ValueError('path escapes CCS directory: %s' % path)
    return path


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def stop_process(process):
    if process.poll() is not None:
        return
    for sig, seconds in ((signal.SIGINT, 8), (signal.SIGTERM, 3), (signal.SIGKILL, 3)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        try:
            process.wait(timeout=seconds)
            break
        except subprocess.TimeoutExpired:
            pass


def run(command, deadline, cancelled):
    print('native_map command: ' + ' '.join(command), flush=True)
    process = subprocess.Popen(command, start_new_session=True)
    try:
        while process.poll() is None:
            if cancelled() or time.monotonic() >= deadline:
                raise RuntimeError('native map generation cancelled or timed out')
            time.sleep(0.1)
        if process.returncode:
            raise RuntimeError('native map converter failed: %s (%s)' % (command[2], process.returncode))
    finally:
        stop_process(process)


def private_args(params):
    return ['_%s:=%s' % (key, str(value).lower() if isinstance(value, bool) else value)
            for key, value in params.items()]


def load(path):
    with Path(path).open() as stream:
        return yaml.safe_load(stream)


def profiles():
    packages = {name: Path(subprocess.check_output(['rospack', 'find', name], text=True).strip())
                for name in ('wheeltec_map_tools', 'wheeltec_2p5d_navigation', 'wheeltec_system_bringup')}
    paths = {
        'reclassify': packages['wheeltec_map_tools'] / 'config/terrain_reclassify.yaml',
        'raw': packages['wheeltec_map_tools'] / 'config/wheeltec_raw.yaml',
        'terrain': packages['wheeltec_2p5d_navigation'] / 'config/terrain_builder.yaml',
        'geometry': packages['wheeltec_system_bringup'] / 'config/wheeltec_geometry.yaml',
    }
    hashes = {name: digest(path) for name, path in paths.items()}
    hashes.update({name + '_version': digest(path / 'package.xml') for name, path in packages.items()})
    hashes['generator'] = digest(__file__)
    return {name: load(path) for name, path in paths.items()}, hashes


def validate_pgm(path):
    with Path(path).open('rb') as stream:
        def token():
            value = bytearray()
            while True:
                char = stream.read(1)
                if not char:
                    if value:
                        return bytes(value)
                    raise ValueError('truncated PGM header')
                if char == b'#' and not value:
                    stream.readline()
                elif char.isspace():
                    if value:
                        if char == b'\r':
                            position = stream.tell()
                            if stream.read(1) != b'\n':
                                stream.seek(position)
                        return bytes(value)
                else:
                    value.extend(char)
        magic, width, height, maximum = token(), int(token()), int(token()), int(token())
        if magic not in (b'P5', b'P2') or min(width, height, maximum) <= 0 or maximum > 65535:
            raise ValueError('invalid PGM dimensions/range')
        pixels = stream.read()
        if magic == b'P5':
            valid = len(pixels) == width * height * (1 if maximum < 256 else 2)
        else:
            values = [int(v) for line in pixels.splitlines() for v in line.split(b'#')[0].split()]
            valid = len(values) == width * height and all(0 <= v <= maximum for v in values)
        if not valid:
            raise ValueError('incomplete PGM pixels')


def validate_pcd(path):
    with Path(path).open('rb') as stream:
        header = {}
        while True:
            line = stream.readline(65536)
            if not line or len(line) == 65536:
                raise ValueError('incomplete PCD header')
            parts = line.decode('ascii').split()
            if not parts or parts[0].startswith('#'):
                continue
            header[parts[0]] = parts[1:]
            if parts[0] == 'DATA':
                break
        points = int(header['POINTS'][0])
        sizes = [int(v) for v in header['SIZE']]
        counts = [int(v) for v in header.get('COUNT', ['1'] * len(sizes))]
        if points < 0 or len(sizes) != len(counts) or any(v <= 0 for v in sizes + counts):
            raise ValueError('invalid PCD fields')
        raw_size = points * sum(a*b for a,b in zip(sizes, counts))
        payload = stream.read()
        mode = header['DATA'][0]
        if mode == 'binary':
            valid = len(payload) == raw_size
        elif mode == 'binary_compressed':
            valid = len(payload) >= 8
            if valid:
                compressed, uncompressed = struct.unpack('<II', payload[:8])
                valid = len(payload) == compressed + 8 and uncompressed == raw_size
        elif mode == 'ascii':
            valid = len(payload.split()) == points * sum(counts)
        else:
            valid = False
        if not valid:
            raise ValueError('incomplete PCD payload')


def validate_products(directory):
    directory = Path(directory)
    terrain = load(directory / 'terrain_2p5d.yaml')
    if terrain.get('format') != 'wheeltec_terrain_2p5d' or terrain.get('version') != 1 or terrain.get('frame_id') != 'map':
        raise ValueError('invalid native terrain format/frame')
    width, height = terrain['width'], terrain['height']
    if type(width) is not int or type(height) is not int or min(width, height) <= 0:
        raise ValueError('invalid terrain dimensions')
    if not math.isfinite(float(terrain['resolution'])) or float(terrain['resolution']) <= 0:
        raise ValueError('invalid terrain resolution')
    if len(terrain['origin']) != 3 or not all(math.isfinite(float(v)) for v in terrain['origin']):
        raise ValueError('invalid terrain origin')
    for layer, size in LAYERS.items():
        path = contained(directory / terrain['layers'][layer], directory)
        if path.stat().st_size != width * height * size:
            raise ValueError('incomplete terrain layer: ' + layer)
    occupancy = load(directory / 'map_raw.yaml')
    image = contained(directory / occupancy['image'], directory)
    validate_pgm(image)
    if not math.isfinite(float(occupancy['resolution'])) or float(occupancy['resolution']) <= 0:
        raise ValueError('invalid occupancy resolution')
    for name in ('terrain_ground_candidates_map.pcd', 'terrain_ground_map.pcd', 'terrain_obstacles_map.pcd'):
        validate_pcd(directory / name)


def build(source, output, configs, deadline, cancelled, runner=run):
    ground = output / 'terrain_ground_map.pcd'
    obstacles = output / 'terrain_obstacles_map.pcd'
    cfg = copy.deepcopy(configs['reclassify'])
    cfg.pop('ground_reference_radius_m', None)
    cfg.update(input_pcd=str(source), output_candidate_pcd=str(output / 'terrain_ground_candidates_map.pcd'),
               output_ground_pcd=str(ground), output_obstacle_pcd=str(obstacles),
               seed_ground_z=-float(configs['geometry']['odom_to_camera_init']['z']))
    runner(['rosrun', 'wheeltec_map_tools', 'terrain_reclassify_node'] + private_args(cfg), deadline, cancelled)
    reclassify = configs['reclassify']
    cfg = copy.deepcopy(configs['terrain'])
    cfg.update(ground_pcd=str(ground), obstacle_pcd=str(obstacles), output_yaml=str(output / 'terrain_2p5d.yaml'),
               frame_id='map', obstacle_ground_search_radius_m=reclassify['ground_reference_radius_m'],
               obstacle_min_relative_height_m=reclassify['min_obstacle_relative_height_m'],
               obstacle_max_relative_height_m=reclassify['max_obstacle_relative_height_m'])
    runner(['rosrun', 'wheeltec_2p5d_navigation', 'terrain_map_builder_node'] + private_args(cfg), deadline, cancelled)
    cfg = copy.deepcopy(configs['raw'])
    cfg.update(classification_mode=True, ground_pcd=str(ground), obstacle_pcd=str(obstacles),
               output_pgm=str(output / 'map_raw.pgm'), output_yaml=str(output / 'map_raw.yaml'))
    for key, source_key in (('ground_search_radius_m', 'ground_reference_radius_m'),
                            ('min_relative_height_m', 'min_obstacle_relative_height_m'),
                            ('max_relative_height_m', 'max_obstacle_relative_height_m')):
        cfg['classified_obstacle/' + key] = reclassify[source_key]
    runner(['rosrun', 'wheeltec_map_tools', 'pcd_to_pgm_node', '__name:=ccs_native_map_converter'] + private_args(cfg), deadline, cancelled)
    # Native tools may emit an absolute staging image path. Publish relocatable YAML.
    for name, key in (('map_raw.yaml', 'image'),):
        data = load(output / name)
        image = Path(data[key])
        if image.is_absolute() and image.parent.resolve() != output.resolve():
            raise ValueError('converter output points outside staging')
        data[key] = image.name
        (output / name).write_text(yaml.safe_dump(data, sort_keys=False))


def ensure_native_map(map_dir, workspace, timeout=300, cancelled=lambda: False,
                      profile_loader=profiles, builder=build):
    directory = contained(map_dir, workspace)
    source = contained(directory / 'public_map.pcd', directory)
    source_files = [source, contained(directory / 'map.yaml', directory), contained(directory / 'map.pgm', directory)]
    if any(not path.is_file() or path.stat().st_size == 0 for path in source_files):
        raise ValueError('incomplete source map')
    configs, config_hashes = profile_loader()
    signature = {'schema_version': 1, 'sources': {p.name: digest(p) for p in source_files}, 'configuration': config_hashes}
    target = directory / 'native_v60'
    contained(target, directory)
    lock = contained(directory / '.native_v60.lock', directory).open('a')
    staging = None
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if cancelled():
            raise RuntimeError('native map preparation cancelled')
        try:
            manifest = json.loads((target / 'manifest.json').read_text())
            if manifest['inputs'] == signature:
                validate_products(target)
                if all(digest(contained(target / name, target)) == sha for name, sha in manifest['outputs'].items()):
                    print('native_map cache valid: ' + str(target), flush=True)
                    return target
        except (OSError, ValueError, KeyError, TypeError):
            pass
        staging = Path(tempfile.mkdtemp(prefix='.native_v60-', dir=str(directory)))
        builder(source, staging, configs, time.monotonic() + timeout, cancelled)
        validate_products(staging)
        if cancelled() or any(digest(p) != signature['sources'][p.name] for p in source_files):
            raise RuntimeError('source map changed or conversion cancelled')
        outputs = {p.name: digest(p) for p in staging.iterdir() if p.is_file()}
        (staging / 'manifest.json').write_text(json.dumps({'inputs': signature, 'outputs': outputs}, indent=2))
        previous = directory / '.native_v60.previous'
        contained(previous, directory)
        if previous.exists():
            shutil.rmtree(previous)
        if target.exists():
            os.replace(target, previous)
        try:
            os.replace(staging, target)
            staging = None
        except Exception:
            if previous.exists():
                os.replace(previous, target)
            raise
        if previous.exists():
            shutil.rmtree(previous)
        print('native_map prepared: ' + str(target), flush=True)
        return target
    finally:
        if staging is not None:
            shutil.rmtree(staging)
        lock.close()
