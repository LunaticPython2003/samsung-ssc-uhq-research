import pathlib, struct, re
root=pathlib.Path(__file__).resolve().parent
import sys
root=pathlib.Path(sys.argv[1]).resolve() if len(sys.argv)>1 else root
for f in root.glob('*.so'):
    b=f.read_bytes()
    if b[:4] != b'\x7fELF':
        print(f.name, 'not ELF'); continue
    cls=b[4]; mach=struct.unpack_from('<H',b,18)[0]
    if cls != 2:
        print(f.name, 'ELF class',cls,'machine',mach); continue
    h=struct.unpack_from('<16sHHIQQQIHHHHHH',b,0)
    shoff,shentsize,shnum,shstrndx=h[6],h[11],h[12],h[13]
    sh=[]
    for i in range(shnum): sh.append(struct.unpack_from('<IIQQQQIIQQ',b,shoff+i*shentsize))
    namesec=sh[shstrndx]; names=b[namesec[4]:namesec[4]+namesec[5]]
    def cstr(buf,off):
        if off>=len(buf): return ''
        return buf[off:buf.find(b'\0',off) if b'\0' in buf[off:] else len(buf)].decode('utf-8','replace')
    sn={cstr(names,s[0]):(i,s) for i,s in enumerate(sh)}
    dynstr=sn.get('.dynstr',(None,None))[1]
    dt=b[dynstr[4]:dynstr[4]+dynstr[5]] if dynstr else b''
    needed=[]
    if '.dynamic' in sn:
        s=sn['.dynamic'][1]
        for off in range(s[4],s[4]+s[5],16):
            tag,val=struct.unpack_from('<qQ',b,off)
            if tag==0: break
            if tag==1: needed.append(cstr(dt,val))
    syms=[]
    for secname in ('.dynsym',):
        if secname in sn:
            s=sn[secname][1]; link=sh[s[6]]; st=b[link[4]:link[4]+link[5]]
            for off in range(s[4],s[4]+s[5],s[9] or 24):
                no,info,other,ndx,val,size=struct.unpack_from('<IBBHQQ',b,off)
                n=cstr(st,no)
                if n and (ndx==0 or info>>4 in (1,2)): syms.append(('UND' if ndx==0 else 'DEF',n))
    strs={m.decode('ascii','ignore') for m in re.findall(rb'[\x20-\x7e]{5,}',b)}
    markers=sorted(x for x in strs if re.search(r'(?i)(scalable|samsung|codec|bluetooth|android|encode|decode|uhq|ssc|aptx|a2dp|qti)',x))
    print('\n###',f.name,'bytes',len(b),'ELF64 machine',mach,'###')
    print('NEEDED:',needed)
    print('SYMBOLS:',syms[:100])
    print('STRINGS:',markers[:100])
