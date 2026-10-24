"""Build a reversible local English-slot Korean patch; never launches the game."""
import base64,collections,csv,datetime,hashlib,io,json,re,shutil,struct
from pathlib import Path
import UnityPy
import os
from fontTools.ttLib import TTFont

P=Path(__file__).resolve().parent
ROOT=P.parent
GAME=Path(os.environ['BNBKR_GAME_DATA'])/'StreamingAssets'
NAMES=['localization_assets_all.bundle','uipack_assets_all.bundle','fontspack_assets_all.bundle','aa/catalog.json']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
manifest_path=P/'manifest.json'
if manifest_path.exists():
 manifest=json.loads(manifest_path.read_text(encoding='utf-8'));backup=Path(manifest['backup'])
 previous=manifest.get('patched')
 if previous and previous not in manifest.setdefault('previous_patched_versions',[]):manifest['previous_patched_versions'].append(previous)
 for name in NAMES:assert sha(backup/name)==manifest['originals'][name]['sha256']
else:
 volume=json.loads((ROOT/'audit/translation_volume.json').read_text(encoding='utf-8'))
 for inp in volume['inputs']:assert sha(GAME/inp['file'])==inp['sha256'],('source version changed',inp['file'])
 backup=P/'backups'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
 for name in NAMES:
  dst=backup/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(GAME/name,dst)
 manifest={'game_streaming_assets':str(GAME),'backup':str(backup),'originals':{n:{'sha256':sha(backup/n),'size':(backup/n).stat().st_size} for n in NAMES}}
 write(manifest_path,manifest)
stage=P/'staged';stage.mkdir(exist_ok=True)
rows=json.loads((ROOT/'translation/translated.json').read_text(encoding='utf-8'))
assert len(rows)==8725
table_rows=collections.defaultdict(dict);dbrows=[]
for r in rows:
 if r['source']=='Main Database':dbrows.append(r)
 else:
  rownum,key=r['key'].split(':',1);table_rows[r['source']][int(rownum)]=(key,r)

env=UnityPy.load(str(backup/NAMES[0]));table_count=0;text_count=0;lookup_aliases=[]
for o in env.objects:
 if o.type.name!='TextAsset':continue
 d=o.read_typetree();name=d['m_Name'];reader=csv.DictReader(io.StringIO(d['m_Script'].lstrip('\ufeff')));columns=reader.fieldnames;content=list(reader)
 for rownum,(key,r) in table_rows[name].items():
  a=content[rownum-2];assert a['Key']==key and a['en']==r['en'],('CSV mismatch',r['id']);a['en']=r['ko'];text_count+=1
 if name=='BNB - Localization - Misc':
  keys={a['Key'] for a in content}
  for r in rows:
   if r['category']!='Actor names' or not r['key'].endswith('/Name'):continue
   alias='character_'+r['en']
   if alias not in keys:
    a={col:'' for col in columns};a.update(Key=alias,en=r['ko']);content.append(a);keys.add(alias);lookup_aliases.append({'key':alias,'ko':r['ko']})
 out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=columns,lineterminator='\r\n');writer.writeheader();writer.writerows(content)
 d['m_Script']=out.getvalue();o.save_typetree(d);table_count+=1
(stage/NAMES[0]).write_bytes(env.file.save(packer='lz4'));del env
print('Staged localization:',table_count,'tables,',text_count,'rows',flush=True)

env=UnityPy.load(str(backup/NAMES[1]));dbobj=None
for o in env.objects:
 if o.type.name=='MonoBehaviour':
  d=o.read_typetree()
  if d.get('m_Name')=='Main Database':dbobj=o;db=d;break
assert dbobj
entries={(c['id'],e['id']):e for c in db['conversations'] for e in c['dialogueEntries']}
sections={k:{a['id']:a for a in db[k]} for k in ['items','actors','locations']}
preserved_names=[]
for r in dbrows:
 bits=r['key'].split('/')
 if bits[0]=='conversation':item=entries[int(bits[1]),int(bits[3])];title=bits[4]
 elif bits[0]=='quest':item=sections['items'][int(bits[1])];title=bits[2]
 else:item=sections[bits[0]][int(bits[1])];title=bits[2]
 field=next(f for f in item['fields'] if f['title']==title)
 assert field['value']==r['en'],('DB mismatch',r['id'])
 if bits[0] in ['actors','locations'] and title=='Name':
  # The game's subtitle panel performs a SECOND lookup using
  # "character_" + CharacterInfo.Name. Display Name must therefore stay an
  # English lookup identifier; the Misc/Areas CSV supplies the Korean label.
  display=next((f for f in item['fields'] if f['title']=='Display Name'),None)
  if display is None:item['fields'].append({'title':'Display Name','value':r['en'],'type':0,'typeString':''})
  else:display['value']=r['en']
  preserved_names.append(r['id'])
 else:field['value']=r['ko']
dbobj.save_typetree(db)
(stage/NAMES[1]).write_bytes(env.file.save(packer='lz4'));del env
print('Staged dialogue database:',len(dbrows),'entries; preserved internal names:',len(preserved_names),flush=True)

font_path=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Fonts/malgun.ttf';font_bytes=font_path.read_bytes();tt=TTFont(str(font_path));cmap=tt.getBestCmap()
hangul={ord(ch) for r in rows for ch in r['ko'] if 0xac00<=ord(ch)<=0xd7a3 or 0x3130<=ord(ch)<=0x318f}
assert not hangul-set(cmap),'Missing Korean glyphs in fallback font'
env=UnityPy.load(str(backup/NAMES[2]));source_id=-1992918319746030303;fallback_id=8854149489604602138;tmp_count=0
for o in env.objects:
 if o.type.name=='Font' and o.path_id==source_id:
  d=o.read_typetree();d['m_FontData']=list(font_bytes);d['m_FontNames']=['Malgun Gothic'];o.save_typetree(d)
 elif o.type.name=='MonoBehaviour':
  d=o.read_typetree()
  if 'm_CharacterTable' not in d:continue
  if o.path_id!=fallback_id:
   ptr={'m_FileID':0,'m_PathID':fallback_id}
   if ptr not in d['m_FallbackFontAssetTable']:d['m_FallbackFontAssetTable'].append(ptr)
  else:
   assert d['m_AtlasPopulationMode']==1 and d['m_SourceFontFile']['m_PathID']==source_id
   d['m_IsMultiAtlasTexturesEnabled']=True
  o.save_typetree(d);tmp_count+=1
(stage/NAMES[2]).write_bytes(env.file.save(packer='lz4'));del env
print('Staged fonts:',tmp_count,'TMP assets;',len(hangul),'Korean glyphs supported',flush=True)

# Change only the three modified bundles' local CRC options, retaining the
# binary catalog's exact object lengths and every existing offset.
catalog=json.loads((backup/NAMES[3]).read_text(encoding='utf-8'))
edata=base64.b64decode(catalog['m_EntryDataString']);extra=bytearray(base64.b64decode(catalog['m_ExtraDataString']));patched_options=[]
for i in range(struct.unpack_from('<i',edata)[0]):
 values=struct.unpack_from('<7i',edata,4+i*28);internal=catalog['m_InternalIds'][values[0]]
 if not any(internal.endswith(n) for n in NAMES[:3]):continue
 pos=values[4];assert extra[pos]==7
 pos+=1;pos+=1+extra[pos];pos+=1+extra[pos]
 length=struct.unpack_from('<i',extra,pos)[0];pos+=4
 raw=bytes(extra[pos:pos+length]).decode('utf-16-le');opts=json.loads(raw)
 filename=next(n for n in NAMES[:3] if internal.endswith(n))
 for key,value in [('m_Crc',0),('m_BundleSize',(stage/filename).stat().st_size)]:
  match=re.search('"'+key+r'":(\d+)',raw);assert match
  old=match.group(1);new=str(value)
  # BundleSize is informational for local files; if it grows a digit, use 0
  # rather than shift serialized offsets or alter unrelated catalog entries.
  if len(new)>len(old):new='0'
  raw=raw[:match.start(1)]+new.ljust(len(old))+raw[match.end(1):]
 encoded=raw.encode('utf-16-le');assert len(encoded)==length
 extra[pos:pos+length]=encoded
 newopts=json.loads(raw);assert newopts['m_Crc']==0
 patched_options.append({'file':filename,'original_crc':opts['m_Crc'],'patched_crc':0,'original_size':opts['m_BundleSize'],'patched_size':newopts['m_BundleSize']})
assert len(patched_options)==3
catalog['m_ExtraDataString']=base64.b64encode(extra).decode('ascii')
(stage/NAMES[3]).parent.mkdir(exist_ok=True);(stage/NAMES[3]).write_text(json.dumps(catalog,separators=(',',':'),ensure_ascii=False),encoding='utf-8')
manifest.update({'translation_sha256':sha(ROOT/'translation/translated.json'),'staged':str(stage),'patched':{n:{'sha256':sha(stage/n),'size':(stage/n).stat().st_size} for n in NAMES},'localization_rows':text_count,'lookup_aliases_added':lookup_aliases,'database_rows':len(dbrows),'internal_names_preserved':preserved_names,'font':{'local_source':str(font_path),'sha256':sha(font_path),'korean_glyphs_covered':len(hangul),'tmp_assets':tmp_count},'catalog_options':patched_options,'language_slot':'en','game_launched':False})
write(manifest_path,manifest)
print('Build complete; game files have not been replaced yet.',flush=True)
