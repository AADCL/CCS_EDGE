#!/usr/bin/env python3
"""ARP duplicate-address probe and read-only Livox SDK2 discovery."""
import argparse
import binascii
import json
import socket
import struct
import time
from pathlib import Path


def probe(interface, address):
    mac = bytes.fromhex(Path('/sys/class/net/%s/address' % interface).read_text().strip().replace(':', ''))
    target = socket.inet_aton(address)
    frame = b'\xff' * 6 + mac + b'\x08\x06'
    frame += struct.pack('!HHBBH', 1, 0x0800, 6, 4, 1) + mac + b'\0' * 4 + b'\0' * 6 + target
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0806)) as sock:
        sock.bind((interface, 0))
        sock.settimeout(0.2)
        for attempt in range(3):
            sock.send(frame)
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                try:
                    packet = sock.recv(2048)
                except socket.timeout:
                    continue
                if len(packet) >= 42 and packet[22:28] != mac:
                    if packet[28:32] == target or (packet[28:32] == b'\0'*4 and packet[38:42] == target):
                        raise RuntimeError('address conflict: %s MAC=%s' % (address, packet[22:28].hex(':')))
    print(json.dumps({'address': address, 'conflict': False, 'probes': 3}))


def discover(host, target):
    header = struct.pack('<BBHIHBB6s', 0xaa, 0, 24, 1, 0, 0, 0, b'\0'*6)
    packet = header + struct.pack('<HI', binascii.crc_hqx(header, 0xffff), 0)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('', 56000))
        sock.settimeout(2)
        for unused in range(3):
            sock.sendto(packet, (host.rsplit('.', 1)[0] + '.255', 56000))
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try:
                    data, source = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                if len(data) < 48 or source[0] != target or data[0] != 0xaa:
                    continue
                length = struct.unpack_from('<H', data, 2)[0]
                if length != len(data) or binascii.crc_hqx(data[:18], 0xffff) != struct.unpack_from('<H', data, 18)[0]:
                    continue
                payload = data[24:]
                if binascii.crc32(payload) & 0xffffffff != struct.unpack_from('<I', data, 20)[0]:
                    continue
                if payload[0] != 0:
                    raise RuntimeError('discovery returned error')
                result = {'ip': source[0], 'device_type': payload[1], 'serial': payload[2:18].split(b'\0')[0].decode('ascii'), 'payload_hex': payload.hex()}
                print(json.dumps(result))
                if result['device_type'] != 9:
                    raise RuntimeError('expected MID-360 (type 9); refusing configuration')
                return
    raise RuntimeError('no valid Livox discovery response')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['probe', 'discover'])
    parser.add_argument('--interface', default='eth0')
    parser.add_argument('--host', default='192.168.123.5')
    parser.add_argument('--lidar', default='192.168.123.124')
    args = parser.parse_args()
    probe(args.interface, args.host) if args.mode == 'probe' else discover(args.host, args.lidar)
