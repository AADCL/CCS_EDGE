"""Bounded PCD reader and conservative 2D display projection."""
import json
from pathlib import Path
import numpy as np
import yaml
from .core import atomic_json

def read_pcd(path):
    with open(path,'rb') as f:
        h={}
        for _ in range(100):
            line=f.readline().decode('ascii').strip()
            if not line or line.startswith('#'):continue
            key,*values=line.split();h[key]=values
            if key=='DATA':break
        count=int(h['POINTS'][0])
        if not 0<count<=5000000:raise ValueError('invalid PCD point count')
        names=h['FIELDS'];sizes=list(map(int,h['SIZE']));types=h['TYPE'];counts=list(map(int,h.get('COUNT',['1']*len(names))))
        mapping={('F',4):'<f4',('F',8):'<f8',('U',1):'u1',('U',2):'<u2',('U',4):'<u4',('I',4):'<i4'}
        dtype=np.dtype([(n,mapping[t,s],(c,)) if c!=1 else (n,mapping[t,s]) for n,s,t,c in zip(names,sizes,types,counts)])
        if h['DATA']==['binary']:
            data=np.fromfile(f,dtype=dtype,count=count)
            if len(data)!=count:raise ValueError('truncated PCD')
            xyz=np.column_stack([data[k] for k in ('x','y','z')])
        elif h['DATA']==['ascii']:
            data=np.loadtxt(f,ndmin=2)
            xyz=data[:,[names.index(k) for k in ('x','y','z')]]
            if len(xyz)!=count:raise ValueError('PCD count mismatch')
        else:raise ValueError('unsupported PCD compression')
    xyz=xyz[np.isfinite(xyz).all(axis=1)]
    if not len(xyz):raise ValueError('no finite map points')
    return xyz

def export(source,destination,matrix,resolution=.05):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    xyz=read_pcd(source)
    matrix=np.asarray(matrix,dtype=float)
    if matrix.shape!=(4,4) or not np.isfinite(matrix).all():raise ValueError('invalid map transform')
    xyz=(xyz@matrix[:3,:3].T+matrix[:3,3]).astype('<f4')
    header=('# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH %d\nHEIGHT 1\nPOINTS %d\nDATA binary\n'%(len(xyz),len(xyz))).encode()
    (destination/'map.pcd').write_bytes(header+xyz.tobytes())
    origin=np.floor(xyz[:,:2].min(axis=0)/resolution)*resolution-resolution
    pixels=np.floor((xyz[:,:2]-origin)/resolution).astype(int)
    width,height=(pixels.max(axis=0)+2).tolist()
    if width*height>16000000:raise ValueError('projection exceeds display raster limit')
    grid=np.full((height,width),205,dtype=np.uint8)
    grid[height-1-pixels[:,1],pixels[:,0]]=0
    (destination/'map.pgm').write_bytes(('P5\n%d %d\n255\n'%(width,height)).encode()+grid.tobytes())
    (destination/'map.yaml').write_text(yaml.safe_dump(dict(image='map.pgm',resolution=resolution,
        origin=[float(origin[0]),float(origin[1]),0.],negate=0,occupied_thresh=.65,free_thresh=.196)),encoding='utf-8')
    atomic_json(str(destination/'transform.json'),dict(source_frame='camera_init',frame_id='odom',
        odom_from_camera_init=matrix.tolist(),projection='occupied points; all unobserved cells unknown; display only'))
    return len(xyz)
