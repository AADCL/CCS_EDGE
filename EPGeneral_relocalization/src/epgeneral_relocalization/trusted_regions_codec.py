"""Version 1 trusted-region XML contract; kept identical in CCS_EDGE.

Only the Python standard library is required, including on ROS Python 3.6.
"""
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET

MAX_BYTES = 1024 * 1024
MAX_REGIONS = 128
MAX_POINTS = 512


def safe_id(value):
    if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)
            or value.upper().split('.')[0] in (
                'CON', 'PRN', 'AUX', 'NUL',
                *('COM%d' % i for i in range(1, 10)),
                *('LPT%d' % i for i in range(1, 10)))):
        raise ValueError("invalid region storage identifier")
    return value


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def validate_polygon(points):
    if not 3 <= len(points) <= MAX_POINTS:
        raise ValueError("区域须有 3–512 个顶点")
    if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError("坐标必须为有限二维数值")
    span = max(max(p[i] for p in points) - min(p[i] for p in points) for i in (0, 1))
    length_eps = max(span * 1e-10, 1e-9)
    area_eps = max(span * span * 1e-10, 1e-12)
    for i, a in enumerate(points):
        for b in points[i + 1:]:
            if math.hypot(a[0] - b[0], a[1] - b[1]) <= length_eps:
                raise ValueError("区域不能包含重复顶点")
    # Work relative to the first point to avoid cancellation at large origins.
    area = sum(_cross(points[0], points[i], points[i + 1]) for i in range(1, len(points) - 1))
    if abs(area) <= area_eps:
        raise ValueError("区域至少需要三个不共线的点")

    def on_segment(a, b, c):
        return (abs(_cross(a, b, c)) <= area_eps
                and min(a[0], b[0]) - length_eps <= c[0] <= max(a[0], b[0]) + length_eps
                and min(a[1], b[1]) - length_eps <= c[1] <= max(a[1], b[1]) + length_eps)

    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        previous = points[i - 1]
        if on_segment(previous, a, b) or on_segment(a, b, previous):
            raise ValueError("相邻边不能折返或重叠")
        for j in range(i + 1, len(points)):
            if j == i + 1 or (i == 0 and j == len(points) - 1):
                continue
            c, d = points[j], points[(j + 1) % len(points)]
            ab_c, ab_d, cd_a, cd_b = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
            if ((ab_c > area_eps and ab_d < -area_eps or ab_d > area_eps and ab_c < -area_eps)
                    and (cd_a > area_eps and cd_b < -area_eps or cd_b > area_eps and cd_a < -area_eps)
                    or any((on_segment(a, b, c), on_segment(a, b, d),
                            on_segment(c, d, a), on_segment(c, d, b)))):
                raise ValueError("区域边界不能自交")


def validate_document(document):
    safe_id(document['map_id'])
    safe_id(document['device_id'])
    safe_id(document['revision'])
    frame = document['frame_id']
    if not isinstance(frame, str) or not frame.strip() or len(frame) > 128:
        raise ValueError("invalid map frame")
    regions = document['regions']
    if len(regions) > MAX_REGIONS:
        raise ValueError("区域数量不能超过 128")
    ids = set()
    for region in regions:
        number = region['id']
        if type(number) is not int or number < 1 or number in ids:
            raise ValueError("区域编号须为唯一正整数")
        ids.add(number)
        validate_polygon(region['points'])
    return document


def encode_xml(document):
    validate_document(document)
    root = ET.Element('trusted_regions', schema_version='1', **{
        key: document[key] for key in ('map_id', 'device_id', 'frame_id', 'revision')})
    for region in document['regions']:
        node = ET.SubElement(root, 'region', id=str(region['id']))
        for index, (x, y) in enumerate(region['points'], 1):
            ET.SubElement(node, 'point', index=str(index), x=repr(float(x)), y=repr(float(y)))
    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    if len(data) > MAX_BYTES:
        raise ValueError("区域 XML 超过 1 MiB")
    return data


def decode_xml(data, map_id=None, device_id=None, frame_id=None):
    if len(data) > MAX_BYTES:
        raise ValueError("区域 XML 超过 1 MiB")
    try:
        text = data.decode('utf-8')
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
            raise ValueError("XML declarations are not allowed")
        root = ET.fromstring(text)
        expected = {'schema_version', 'map_id', 'device_id', 'frame_id', 'revision'}
        if root.tag != 'trusted_regions' or set(root.attrib) != expected or root.get('schema_version') != '1':
            raise ValueError("invalid trusted-region XML schema")
        document = {key: root.attrib[key] for key in expected - {'schema_version'}}
        document['regions'] = []
        for node in root:
            if node.tag != 'region' or set(node.attrib) != {'id'}:
                raise ValueError("invalid region element")
            points = []
            for index, point in enumerate(node, 1):
                if (point.tag != 'point' or set(point.attrib) != {'index', 'x', 'y'}
                        or len(point) or int(point.attrib['index']) != index):
                    raise ValueError("invalid ordered point element")
                points.append((float(point.attrib['x']), float(point.attrib['y'])))
            document['regions'].append({'id': int(node.attrib['id']), 'points': points})
        for key, value in (('map_id', map_id), ('device_id', device_id), ('frame_id', frame_id)):
            if value is not None and document[key] != value:
                raise ValueError("trusted-region %s mismatch" % key)
        return validate_document(document)
    except (ET.ParseError, UnicodeError, KeyError, TypeError, OverflowError) as exc:
        raise ValueError("invalid trusted-region XML: %s" % exc)


def read_xml(path, **identity):
    with open(path, 'rb') as stream:
        return decode_xml(stream.read(MAX_BYTES + 1), **identity)


def atomic_write(path, data):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.trusted-', suffix='.tmp', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
