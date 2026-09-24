#!/usr/bin/env python3
import argparse
import os
from epgeneral_wheeltec_integration.native_maps import ensure_native_map

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('map_dir')
    parser.add_argument('--timeout', type=float, default=300)
    args = parser.parse_args()
    print(ensure_native_map(args.map_dir, os.environ.get('CCS_EDGE_WORKSPACE', '/home/nrc19/ccs_edge_ws'), args.timeout))
