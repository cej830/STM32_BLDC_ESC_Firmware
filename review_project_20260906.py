from pathlib import Path
import csv, io, re, json, zipfile, collections, xml.etree.ElementTree as ET

hw=Path('F:/Embedded systems_study/Kicad_project/STM32_ESC_HW')
sw=Path(__file__).parent
def sexp(text):
    root=[]; stack=[root]
    for m in re.finditer(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text):
        t=m.group()
        if t=='(':
            a=[]; stack[-1].append(a); stack.append(a)
        elif t==')': stack.pop()
        else: stack[-1].append(json.loads(t) if t.startswith('"') else t)
    return root[0]
def children(a,key): return [b for b in a if isinstance(b,list) and b and b[0]==key]
def prop(a,key): return next((b[2] for b in children(a,'property') if b[1]==key),None)
board=sexp((hw/'STM32_ESC_HW.kicad_pcb').read_text(encoding='utf-8'))
fps={prop(f,'Reference'):f for f in children(board,'footprint')}
rows=[{k.strip():v.strip() for k,v in r.items()} for r in csv.DictReader(io.StringIO((hw/'Manufacturer/STM32_ESC_HW.csv').read_text(encoding='utf-8-sig')),skipinitialspace=True)]
refs={ref:r for r in rows for ref in r['Reference'].split(',')}
print('BOM:',len(rows),'groups',sum(int(r['Qty']) for r in rows),'components',len(refs),'unique refs')
print('Qty mismatch:',[(r['Reference'],r['Qty']) for r in rows if len(r['Reference'].split(','))!=int(r['Qty'])])
print('PCB:',len(fps),'footprints',len(children(board,'segment')),'segments',len(children(board,'via')),'vias',len(children(board,'zone')),'zones')
print('PCB without BOM:',sorted(set(fps)-set(refs)))
print('BOM without PCB:',sorted(set(refs)-set(fps)))
print('BOM PCB value/footprint mismatches:',[(ref, r['Value'],prop(fps[ref],'Value'),r['Footprint'],fps[ref][1]) for ref,r in refs.items() if ref in fps and (r['Value']!=prop(fps[ref],'Value') or r['Footprint']!=fps[ref][1])])
print('Empty MPN:',[r['Reference'] for r in rows if not r['Part number']])
print('Special parts:',[{k:r[k] for k in ['Reference','Part number','Value','Footprint']} for r in rows if r['Reference'] in ['R20,R22','U5,U6,U7,U8,U9,U10','J7','TVS1']])
sch=ET.parse(hw/'final_review_netlist.xml').getroot()
comps={c.attrib['ref']:c for c in sch.find('components')}
print('BOM schematic mismatches:',[(r,refs[r]['Value'],c.findtext('value')) for r,c in comps.items() if r in refs and refs[r]['Value']!=c.findtext('value')])
def norm(s): return '\n'.join(l for l in s.splitlines() if not l.startswith(('%TF.CreationDate','G04 Created by')))
with zipfile.ZipFile(hw/'gerber/STM32_ESC_HW_Gerber_final.zip') as z:
    for entry in z.namelist():
        if entry.endswith('.gbr') and '-drl_map' not in entry:
            local=hw/'gerber'/entry
            fresh=list((hw/'review_20260906_gerber').glob(Path(entry).stem+'.*'))
            old=z.read(entry).decode()
            same=local.exists() and z.read(entry)==local.read_bytes()
            freshsame=bool(fresh) and norm(old)==norm(fresh[0].read_text())
            print('Gerber',entry,'ZIP=loose',same,'normalized ZIP=current',freshsame)
print('Closed loop logs:')
for p in sorted((sw/'Measurment/측정 프로그램/BEMF_Close LOOP Debug').glob('*.csv')):
    data=list(csv.DictReader(p.open(encoding='utf-8-sig')))
    zc=[r for r in data if r.get('is_ZC_Occur')=='1']
    print(p.name,'rows',len(data),'ZCs',len(zc),'max_laptime',max(int(r['laptime']) for r in data),'last',data[-1])
