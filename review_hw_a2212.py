from pathlib import Path
import re, json, math, urllib.request
out=Path('review_a2212');out.mkdir(exist_ok=True)
urls={
 'irfh7440':'https://www.infineon.com/assets/row/public/documents/24/49/infineon-irfh7440-datasheet-en.pdf',
 'drv8300':'https://www.ti.com/lit/gpn/DRV8300',
 'stm32f103':'https://www.st.com/resource/en/datasheet/stm32f103c8.pdf',
 'tlv3202':'https://www.ti.com/lit/gpn/TLV3202',
 'tps560430':'https://www.ti.com/lit/gpn/TPS560430',
}
import concurrent.futures
def fetch(item):
 name,url=item;dest=out/(name+'.pdf')
 try:
  if not dest.exists():
   with urllib.request.urlopen(url,timeout=35) as r: dest.write_bytes(r.read())
  from pypdf import PdfReader
  reader=PdfReader(dest)
  (out/(name+'.txt')).write_text('\n'.join(f'PAGE {i+1}\n'+(p.extract_text() or '') for i,p in enumerate(reader.pages)),encoding='utf-8')
  return name,len(reader.pages)
 except Exception as e:return name,str(e)
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
 for result in pool.map(fetch,urls.items()): print(result,flush=True)

namespace={'__file__':str(Path('review_project_20260906.py').resolve())}
source=Path('review_project_20260906.py').read_text(encoding='utf-8')
exec(source[:source.index('rows=')],namespace)
children=namespace['children'];fps=namespace['fps'];board=namespace['board']
def first(a,k,default=None): return next(iter(children(a,k)),default)
for ref in ['U1','U2','U4','U5','U6','U13','U15','C22','C24','C37','R33','R61','J7','D6','D7']:
 f=fps[ref]
 at=first(f,'at');print(ref,'position',at,flush=True)
 if ref.startswith('U') or ref=='J7':
  print([(p[1],first(p,'at'),first(p,'size'),first(p,'net')) for p in children(f,'pad') if p[1]],flush=True)
for name in ['/Shunt_A+','Net-(R61-Pad1)','/PWM_CH1','/Inverter_BLOCK/Hiside_GATE_1','Net-(R28-Pad2)']:
 net=next(n[1] for n in children(board,'net') if n[2]==name)
 segs=[s for s in children(board,'segment') if first(s,'net')[1]==net]
 length=sum(math.dist(list(map(float,first(s,'start')[1:])),list(map(float,first(s,'end')[1:]))) for s in segs)
 print('Trace',name,'total length',round(length,2),'widths',sorted(set(first(s,'width')[1] for s in segs)),flush=True)
