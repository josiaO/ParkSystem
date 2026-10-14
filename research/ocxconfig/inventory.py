"""Read-only inventory of the OcxConfig vendor package."""
from pathlib import Path
import struct,json,hashlib
def pe(p):
 b=p.read_bytes(); u16=lambda o:struct.unpack_from('<H',b,o)[0]; u32=lambda o:struct.unpack_from('<I',b,o)[0]
 h=u32(60);
 if b[:2]!=b'MZ' or b[h:h+4]!=b'PE\0\0':raise ValueError('Not a standard PE image')
 opt=h+24; magic=u16(opt); base=u32(opt+28) if magic==267 else struct.unpack_from('<Q',b,opt+24)[0]; dd=opt+(96 if magic==267 else 112)
 sections=[]
 for i in range(u16(h+6)):
  o=opt+u16(h+20)+40*i; sections.append((u32(o+12),max(u32(o+8),u32(o+16)),u32(o+20)))
 def off(r):
  for v,s,f in sections:
   if v<=r<v+s:return f+r-v
  return r
 def string(r):
  o=off(r);return b[o:b.index(0,o)].decode('ascii','replace')
 imports=[]; r=u32(dd+8)
 if r:
  o=off(r)
  while u32(o+12):
   dll=string(u32(o+12)); thunk=u32(o) or u32(o+16); iat=u32(o+16); n=0; step=4 if magic==267 else 8
   while True:
    value=int.from_bytes(b[off(thunk)+n*step:off(thunk)+(n+1)*step],'little')
    if not value:break
    name=f'ordinal:{value&65535}' if value>>(step*8-1) else string(value+2)
    imports.append(dict(dll=dll,name=name,iat_va=hex(base+iat+n*step)));n+=1
   o+=20
 exports=[];r=u32(dd)
 if r:
  o=off(r); funcs=off(u32(o+28));names=off(u32(o+32));ords=off(u32(o+36))
  for i in range(u32(o+24)):
   index=u16(ords+2*i);exports.append(dict(name=string(u32(names+4*i)),va=hex(base+u32(funcs+4*index))))
 return dict(machine=hex(u16(h+4)),image_base=hex(base),managed=bool(u32(dd+14*8)),imports=imports,exports=exports)
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'Current_ParkSystem_configs/Camera_config/OcxConfig'
rows=[]
for p in sorted(SRC.iterdir()):
 if p.suffix.lower() in {'.dll','.exe','.ocx'}:
  rows.append({'path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),**pe(p)})
(Path(__file__).parent/'evidence/inventory.json').write_text(json.dumps(rows,indent=2))
