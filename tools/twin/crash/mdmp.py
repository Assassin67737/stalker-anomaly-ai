#!/usr/bin/env python3
"""Разбор минидампа X-Ray под wine (свой парсер: готовый minidump не понимает поток 0xFFF0).
Печатает адрес исключения и адреса возврата в AnomalyDX11.exe со стека. Функцию по адресу ищем
objdump -d + строки, на которые она ссылается в .rdata (так нашли CAI_Stalker::OnEvent, 20.10.2026).
Использование: python3 crash/mdmp.py appdata/logs/xray_player_*.mdmp
"""
import struct,sys
def parse(fn):
    d=open(fn,'rb').read()
    _,_,n,rva=struct.unpack_from('<4sIII',d,0)
    st={}
    for i in range(n):
        t,size,r=struct.unpack_from('<III',d,rva+i*12); st.setdefault(t,[]).append((size,r))
    def mstr(r):
        l=struct.unpack_from('<I',d,r)[0]; return d[r+4:r+4+l].decode('utf-16le')
    mods=[]; size,r=st[4][0]; cnt=struct.unpack_from('<I',d,r)[0]
    for i in range(cnt):
        o=r+4+i*108; base,sz=struct.unpack_from('<QI',d,o); nr=struct.unpack_from('<I',d,o+20)[0]
        mods.append((base,sz,mstr(nr).split('\\')[-1]))
    which=lambda a: next(((nm,a-b) for b,s,nm in mods if b<=a<b+s),None)
    size,r=st[6][0]; tid=struct.unpack_from('<I',d,r)[0]
    code,flags,rec,addr,np_=struct.unpack_from('<IIQQI',d,r+8)
    csz,crva=struct.unpack_from('<II',d,r+8+32+15*8)
    rsp=struct.unpack_from('<Q',d,crva+0x98)[0]
    mem=[]; size,r=st[5][0]; c=struct.unpack_from('<I',d,r)[0]
    for i in range(c):
        s0,ds,dr=struct.unpack_from('<QII',d,r+4+i*16); mem.append((s0,ds,dr))
    blk=next((d[dr+rsp-s0:dr+rsp-s0+0x800] for s0,ds,dr in mem if s0<=rsp<s0+ds),b'')
    out=[]
    for i in range(0,len(blk)-7,8):
        v=struct.unpack_from('<Q',blk,i)[0]; w=which(v)
        if w and w[0].startswith('Anomaly'): out.append(hex(w[1]))
    return hex(addr), out[:12]
for fn in sys.argv[1:]:
    a,o=parse(fn); print(fn[-23:], a, ' '.join(o))
