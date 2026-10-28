"""Package verified generated game files for manual installation; never read saves.

Requires text/logo build manifests from the existing source installer build.
Only the redistribution font differs from the installer edition.
"""
import argparse,base64,hashlib,json,shutil,struct,zipfile
from pathlib import Path
import UnityPy
from fontTools.ttLib import TTFont
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
 p=argparse.ArgumentParser();p.add_argument('--text-manifest',type=Path,required=True);p.add_argument('--logo-manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 text=read(a.text_manifest);logo=read(a.logo_manifest);out=a.output;stage=out/'staged';stage.mkdir(parents=True,exist_ok=True)
 config=read(HERE.parent/'resources/supported.json');version=config['version']
 sources={}
 for name in config['original_sha256']:
  if name in logo['after']:path=Path(logo['staged'])/name;expected=logo['after'][name]['sha256']
  else:
   short=name.removeprefix('StreamingAssets/');path=Path(text['staged'])/short;expected=text['patched'][short]['sha256']
  assert sha(path)==expected,('Unverified staged source',name)
  sources[name]=path
 font=HERE/'font/NanumGothic-Regular.ttf';tt=TTFont(font);family=tt['name'].getDebugName(1);cmap=tt.getBestCmap()
 translations=HERE.parent/'resources/translation/translated.json';assert sha(translations)==text['translation_sha256']
 rows=read(translations);hangul={ord(c) for r in rows for c in r['ko'] if 0xac00<=ord(c)<=0xd7a3 or 0x3130<=ord(c)<=0x318f}
 assert not hangul-set(cmap),'Missing Korean glyphs'
 data=font.read_bytes();font_name='StreamingAssets/fontspack_assets_all.bundle';env=UnityPy.load(str(sources[font_name]));pid=-1992918319746030303
 obj=next(o for o in env.objects if o.path_id==pid);d=obj.read_typetree();d['m_FontData']=list(data);d['m_FontNames']=[family];obj.save_typetree(d)
 dest=stage/'BearAndBreakfast_Data'/font_name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(env.file.save(packer='lz4'));del env
 original=UnityPy.load(str(sources[font_name]));final=UnityPy.load(str(dest));before={o.path_id:o for o in original.objects};after={o.path_id:o for o in final.objects};assert before.keys()==after.keys()
 for oid in before:
  if oid==pid:
   x=before[oid].read_typetree();y=after[oid].read_typetree();assert bytes(v&255 for v in y['m_FontData'])==data
   assert y['m_FontNames']==[family]
   assert {k:v for k,v in x.items() if k not in ['m_FontData','m_FontNames']}=={k:v for k,v in y.items() if k not in ['m_FontData','m_FontNames']}
  else:assert before[oid].get_raw_data()==after[oid].get_raw_data(),('Unexpected font object change',oid)
 del original,final,before,after
 for name,source in sources.items():
  if name==font_name:continue
  target=stage/'BearAndBreakfast_Data'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
 catpath=stage/'BearAndBreakfast_Data/StreamingAssets/aa/catalog.json';cat=read(catpath);extra=bytearray(base64.b64decode(cat['m_ExtraDataString']));entries=base64.b64decode(cat['m_EntryDataString']);hits=0
 for i in range(struct.unpack_from('<i',entries)[0]):
  v=struct.unpack_from('<7i',entries,4+i*28)
  if not cat['m_InternalIds'][v[0]].endswith('fontspack_assets_all.bundle'):continue
  pos=v[4];assert extra[pos]==7;pos+=1;pos+=1+extra[pos];pos+=1+extra[pos];n=struct.unpack_from('<i',extra,pos)[0];pos+=4
  raw=bytes(extra[pos:pos+n]).decode('utf-16-le');opts=json.loads(raw);assert opts['m_Crc']==0
  import re
  match=re.search(r'"m_BundleSize":(\d+)\s*',raw);assert match
  replacement='"m_BundleSize":'+str(dest.stat().st_size);assert len(replacement)<=len(match[0])
  raw=raw[:match.start()]+replacement.ljust(len(match[0]))+raw[match.end():];b=raw.encode('utf-16-le');assert len(b)==n
  extra[pos:pos+n]=b;hits+=1
 assert hits==1
 cat['m_ExtraDataString']=base64.b64encode(extra).decode('ascii');catpath.write_text(json.dumps(cat,separators=(',',':'),ensure_ascii=False),encoding='utf-8')
 shutil.copy2(HERE/'INSTALL_KO.txt',stage/'설치안내.txt');shutil.copy2(HERE/'font/OFL.txt',stage/'NanumGothic-OFL.txt')
 report={'version':version,'edition':'overwrite','font':{'family':family,'sha256':sha(font),'license':'SIL OFL 1.1','hangul_glyphs_verified':len(hangul),'source':'https://github.com/google/fonts/tree/main/ofl/nanumgothic'},'files':{name:{'sha256':sha(stage/'BearAndBreakfast_Data'/name),'size':(stage/'BearAndBreakfast_Data'/name).stat().st_size} for name in sources},'save_tool_included':False,'save_files_accessed':False,'game_launched':False,'runtime_font_rendering_verified':False}
 (stage/'overwrite-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 archive=out/f'BearAndBreakfast-KR-v{version}-Overwrite.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for file in sorted(stage.rglob('*')):
   if file.is_file():z.write(file,file.relative_to(stage).as_posix())
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  assert not any(Path(n).suffix.lower() in ['.exe','.py','.bat','.cmd','.ps1'] or Path(n).name.startswith('Save') for n in z.namelist())
  for name,info in report['files'].items():assert hashlib.sha256(z.read('BearAndBreakfast_Data/'+name)).hexdigest()==info['sha256']
 report.update({'archive':archive.name,'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size})
 (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
