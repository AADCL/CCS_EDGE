import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
if os.name != 'nt':
    from epgeneral_wheeltec_integration.native_maps import ensure_native_map, build, validate_products, LAYERS


@unittest.skipIf(os.name == 'nt', 'file leases require Linux; run on UGV_003')
class NativeMapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.map = self.root / 'maps/download/test_map'
        self.map.mkdir(parents=True)
        for name in ('public_map.pcd', 'map.yaml', 'map.pgm'):
            (self.map / name).write_text('original-' + name)
        self.original = {p.name: p.read_bytes() for p in self.map.iterdir()}
        self.builds = 0
        self.configuration = {'version': 'one'}

    def loader(self):
        return {}, dict(self.configuration)

    def builder(self, source, output, configs, deadline, cancelled):
        self.assertEqual(source, self.map / 'public_map.pcd')
        self.builds += 1
        terrain = {'format': 'wheeltec_terrain_2p5d', 'version': 1, 'frame_id': 'map',
                   'resolution': 0.1, 'width': 2, 'height': 2, 'origin': [0, 0, 0], 'layers': {}}
        for key, size in LAYERS.items():
            terrain['layers'][key] = key + '.bin'
            (output / (key + '.bin')).write_bytes(bytes(4 * size))
        (output / 'terrain_2p5d.yaml').write_text(yaml.safe_dump(terrain))
        (output / 'map_raw.yaml').write_text('image: map_raw.pgm\nresolution: 0.05\n')
        (output / 'map_raw.pgm').write_bytes(b'P5\n2 2\n255\n' + b'\xff'*4)
        for name in ('terrain_ground_candidates_map.pcd','terrain_ground_map.pcd','terrain_obstacles_map.pcd'):
            (output / name).write_bytes(b'FIELDS x y z\nSIZE 4 4 4\nCOUNT 1 1 1\nPOINTS 1\nDATA binary\n' + bytes(12))

    def prepare(self, **kwargs):
        return ensure_native_map(self.map, self.root, profile_loader=self.loader, builder=kwargs.pop('builder', self.builder), **kwargs)

    def test_cache_preserves_received_map_and_invalidates_source_or_configuration(self):
        self.prepare(); self.prepare()
        self.assertEqual(self.builds, 1)
        for name, content in self.original.items():
            self.assertEqual((self.map / name).read_bytes(), content)
        (self.map / 'public_map.pcd').write_text('updated-source')
        self.prepare(); self.assertEqual(self.builds, 2)
        self.configuration['version'] = 'two'
        self.prepare(); self.assertEqual(self.builds, 3)

    def test_corrupt_layer_is_not_accepted_from_cache(self):
        target = self.prepare()
        (target / 'cost.bin').write_bytes(b'')
        self.prepare(); self.assertEqual(self.builds, 2)

    def test_failed_conversion_keeps_previous_output_but_refuses_readiness(self):
        target = self.prepare()
        original = (target / 'manifest.json').read_bytes()
        self.configuration['version'] = 'two'
        def failed(*args):
            raise RuntimeError('converter failed')
        with self.assertRaisesRegex(RuntimeError, 'converter failed'):
            self.prepare(builder=failed)
        self.assertEqual((target / 'manifest.json').read_bytes(), original)
        self.assertEqual(list(self.map.glob('.native_v60-*')), [])

    def test_truncated_generated_image_or_cloud_never_publishes(self):
        for filename in ('map_raw.pgm', 'terrain_ground_map.pcd'):
            def truncated(source, output, *args):
                self.builder(source, output, *args)
                path = output / filename
                path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                self.prepare(builder=truncated)
            self.assertFalse((self.map / 'native_v60').exists())

    def test_cancelled_conversion_never_publishes(self):
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.prepare(cancelled=lambda: True)
        self.assertFalse((self.map / 'native_v60').exists())

    def test_external_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.map / 'public_map.pcd').unlink()
            (Path(outside) / 'input.pcd').write_text('external')
            (self.map / 'public_map.pcd').symlink_to(Path(outside) / 'input.pcd')
            with self.assertRaisesRegex(ValueError, 'escapes'):
                self.prepare()

    def test_native_builder_does_not_transform_map_frame_cloud(self):
        configs = {'reclassify': {'ground_reference_radius_m': .35, 'min_obstacle_relative_height_m': .04,
                                  'max_obstacle_relative_height_m': 1.5},
                   'geometry': {'odom_to_camera_init': {'z': .15}}, 'terrain': {}, 'raw': {}}
        commands = []
        output = self.map / 'products'; output.mkdir()
        def runner(command, deadline, cancelled):
            commands.append(command)
            if command[2] == 'pcd_to_pgm_node':
                (output / 'map_raw.yaml').write_text('image: map_raw.pgm\n')
        build(self.map / 'public_map.pcd', output, configs, 999999, lambda: False, runner=runner)
        self.assertEqual([c[2] for c in commands], ['terrain_reclassify_node','terrain_map_builder_node','pcd_to_pgm_node'])
        self.assertIn('_input_pcd:=' + str(self.map / 'public_map.pcd'), commands[0])
        self.assertNotIn('pcd_transform_node', str(commands))


if __name__ == '__main__':
    unittest.main()
