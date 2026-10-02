from pathlib import Path
import re, zipfile, collections, json, sys

hw=Path('F:/Embedded systems_study/Kicad_project/STM32_ESC_HW')
def primitives(s):
    s=s.replace('\r\n','\n')
    apertures=dict(re.findall(r'%ADD(\d+)(.*?)\*%',s))
    macros=tuple(sorted(re.findall(r'%AM.*?%',s,re.S)))
    s=re.sub(r'%.*?%',lambda m:'\n'+m.group()+'\n',s,flags=re.S)
    pos=(0,0); ap=None; mode='G01'; polarity='D'; region=None; out=[]; unknown=[]
    for line in s.splitlines():
        line=line.strip()
        if not line: continue
        if line.startswith('%LP'): polarity=line[3]; continue
        if line.startswith(('%','G04')): continue
        if re.fullmatch(r'D\d+\*',line): ap=apertures[line[1:-1]]; continue
        if line in ['G01*','G02*','G03*']: mode=line[:-1]; continue
        if line=='G36*': region=[]; continue
        if line=='G37*': out.append(('region',polarity,tuple(region)));region=None;continue
        if line in ['G75*','M02*']:continue
        m=re.fullmatch(r'X(-?\d+)Y(-?\d+)(?:I(-?\d+)J(-?\d+))?D0([123])\*',line)
        if not m:
            # Macro contents are ignored below; this generated KiCad macro set is compared separately.
            if not line.endswith('*') or line[:1].isdigit(): continue
            unknown.append(line);continue
        x,y,i,j,d=m.groups(); new=(int(x),int(y)); arc=(int(i or 0),int(j or 0))
        if region is not None:
            region.append((d,mode,pos if d=='1' else None,new,arc))
        elif d=='1': out.append(('draw',polarity,ap,mode,pos,new,arc))
        elif d=='3': out.append(('flash',polarity,ap,new))
        pos=new
    return collections.Counter(out),macros,unknown
with zipfile.ZipFile(hw/'gerber/STM32_ESC_HW_Gerber_final.zip') as z:
    read=lambda name: (hw/'gerber'/name).read_bytes() if '--loose' in sys.argv else z.read(name)
    for name in z.namelist():
        if not name.endswith('.gbr') or 'drl_map' in name: continue
        fresh=next((hw/'review_20260906_gerber').glob(Path(name).stem+'.*'))
        a,am,au=primitives(read(name).decode());b,bm,bu=primitives(fresh.read_text())
        print(name, 'primitives',sum(a.values()),sum(b.values()),'macros_equal',am==bm,'unknown',au[:3],bu[:3],'removed',sum((a-b).values()),'added',sum((b-a).values()))
        if a!=b:
            print('DIFF',str(list((a-b).items())[:2])[:650],str(list((b-a).items())[:2])[:650])
    def drills(s):
        defs={}; current=None; plating=None; out=[]; unknown=[]; slot_start=None
        for line in s.splitlines():
            if line.startswith('; #@! TA.AperFunction,'): plating=line.split(',')[1]
            m=re.fullmatch(r'T(\d+)C([\d.]+)',line)
            if m: defs[m[1]]=(plating,float(m[2]));continue
            m=re.fullmatch(r'T(\d+)',line)
            if m: current=defs[m[1]];continue
            if line.startswith('G00X'): slot_start=line[3:];continue
            if line.startswith('G01X') and slot_start:
                out.append((current,slot_start+'G85'+line[3:]));slot_start=None;continue
            if line.startswith('X'):out.append((current,line))
        return collections.Counter(out)
    a=drills(read('STM32_ESC_HW-PTH.drl').decode())+drills(read('STM32_ESC_HW-NPTH.drl').decode())
    b=drills((hw/'review_20260906_gerber/STM32_ESC_HW.drl').read_text())
    print('Drills: old',sum(a.values()),'current',sum(b.values()),'equal including plating',a==b)
    print('Drill removed:',list((a-b).items()))
    print('Drill added:',list((b-a).items()))
