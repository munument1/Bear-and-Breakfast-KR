import base64,collections,csv,hashlib,io,json,struct
from pathlib import Path
import UnityPy
import os
P=Path(__file__).resolve().parent
m=json.loads((P/'manifest.json').read_text(encoding='utf-8'));backup=Path(m['backup']);stage=Path(m['staged'])
rows=json.loads((P.parent/'translation/translated.json').read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P.parent/'translation/translated.json')==m['translation_sha256']
for name in m['originals']:
 assert sha(backup/name)==m['originals'][name]['sha256']
 assert sha(stage/name)==m['patched'][name]['sha256']
def objects(name):
 a=UnityPy.load(str(backup/name));b=UnityPy.load(str(stage/name))
 before={o.path_id:o for o in a.objects};after={o.path_id:o for o in b.objects}
 assert set(before)==set(after),('object identifiers changed',name)
 assert all(before[i].type==after[i].type for i in before)
 return a,b,before,after

name='localization_assets_all.bundle';a,b,old,new=objects(name);seen=set();tables=0
idx=collections.defaultdict(dict)
for r in rows:
 if r['source']!='Main Database':idx[r['source']][int(r['key'].split(':',1)[0])]=r
for pid,o in old.items():
 if o.type.name!='TextAsset':continue
 x=o.read_typetree();y=new[pid].read_typetree();ox=list(csv.DictReader(io.StringIO(x['m_Script'].lstrip('\ufeff'))));ny=list(csv.DictReader(io.StringIO(y['m_Script'].lstrip('\ufeff'))))
 aliases=m.get('lookup_aliases_added',[]) if x['m_Name']=='BNB - Localization - Misc' else []
 assert len(ny)==len(ox)+len(aliases)
 for row,alias in zip(ny[len(ox):],aliases):
  assert row['Key']==alias['key'] and row['en']==alias['ko']
  assert all(not v for k,v in row.items() if k not in ['Key','en'])
 for n,(u,v) in enumerate(zip(ox,ny),2):
  r=idx[x['m_Name']].get(n)
  if r:assert v['en']==r['ko'];seen.add(r['id'])
  else:assert v['en']==u['en']
  assert {k:z for k,z in u.items() if k!='en'}=={k:z for k,z in v.items() if k!='en'}
 tables+=1
del a,b,old,new
print('Verified all CSV fields; foreign languages and keys unchanged.',flush=True)

name='uipack_assets_all.bundle';a,b,old,new=objects(name);count=0
for pid,o in old.items():
 if o.type.name!='MonoBehaviour':continue
 # Only the database object was serialized. All other UI/prefab components
 # must retain their original raw data, independent of type-tree decoding.
 if pid!=-8459904919152792432:
  assert o.get_raw_data()==new[pid].get_raw_data(),('unexpected UI change',pid)
  continue
 x=o.read_typetree();y=new[pid].read_typetree()
 entries={(c['id'],e['id']):e for c in y['conversations'] for e in c['dialogueEntries']}
 sections={s:{v['id']:v for v in y[s]} for s in ['items','actors','locations']}
 origsections={s:{v['id']:v for v in x[s]} for s in ['actors','locations']}
 for r in rows:
  if r['source']!='Main Database':continue
  bits=r['key'].split('/')
  if bits[0]=='conversation':item=entries[int(bits[1]),int(bits[3])];title=bits[4]
  elif bits[0]=='quest':item=sections['items'][int(bits[1])];title=bits[2]
  else:item=sections[bits[0]][int(bits[1])];title=bits[2]
  field=next(f for f in item['fields'] if f['title']==title)
  if bits[0] in ['actors','locations'] and title=='Name':
   assert field['value']==r['en']
   display=next(f for f in item['fields'] if f['title']=='Display Name');assert display['value']==r['en']
   prev=next((f for f in origsections[bits[0]][int(bits[1])]['fields'] if f['title']=='Display Name'),None)
   if prev:display['value']=prev['value']
   else:item['fields'].remove(display)
  else:assert field['value']==r['ko'];field['value']=r['en']
  seen.add(r['id']);count+=1
 assert x==y,'Database changed outside approved text/display fields'
del a,b,old,new
assert len(seen)==8725
print('Verified all database fields, original scripts, links and internal names.',flush=True)

name='fontspack_assets_all.bundle';a,b,old,new=objects(name);font_count=0
for pid,o in old.items():
 if o.type.name=='Font' and pid==-1992918319746030303:
  x=o.read_typetree();y=new[pid].read_typetree()
  assert hashlib.sha256(bytes(v&255 for v in y['m_FontData'])).hexdigest()==m['font']['sha256']
  for k in x:
   if k not in ['m_FontData','m_FontNames']:assert x[k]==y[k]
 elif o.type.name=='MonoBehaviour':
  x=o.read_typetree();y=new[pid].read_typetree()
  if 'm_CharacterTable' not in x:assert x==y;continue
  if pid!=8854149489604602138:assert {'m_FileID':0,'m_PathID':8854149489604602138} in y['m_FallbackFontAssetTable']
  else:assert y['m_AtlasPopulationMode']==1 and y['m_IsMultiAtlasTexturesEnabled']
  for k in x:
   if k not in ['m_FallbackFontAssetTable','m_IsMultiAtlasTexturesEnabled']:assert x[k]==y[k]
  font_count+=1
del a,b,old,new
print('Verified font fallback links and embedded Korean font.',flush=True)

orig=json.loads((backup/'aa/catalog.json').read_text(encoding='utf-8'));patched=json.loads((stage/'aa/catalog.json').read_text(encoding='utf-8'))
assert {k:v for k,v in orig.items() if k!='m_ExtraDataString'}=={k:v for k,v in patched.items() if k!='m_ExtraDataString'}
e1=base64.b64decode(orig['m_ExtraDataString']);e2=base64.b64decode(patched['m_ExtraDataString']);assert len(e1)==len(e2)
entries=base64.b64decode(orig['m_EntryDataString']);expected={x['file'] for x in m['catalog_options']};hits=set()
for i in range(struct.unpack_from('<i',entries)[0]):
 v=struct.unpack_from('<7i',entries,4+i*28);iid=orig['m_InternalIds'][v[0]];start=v[4]
 if start<0:continue
 pos=start+1;pos+=1+e1[pos];pos+=1+e1[pos];n=struct.unpack_from('<i',e1,pos)[0];pos+=4
 j1=json.loads(e1[pos:pos+n].decode('utf-16-le'));j2=json.loads(e2[pos:pos+n].decode('utf-16-le'))
 target=next((f for f in expected if iid.endswith(f)),None)
 if target:
  assert j2['m_Crc']==0
  assert {k:z for k,z in j1.items() if k not in ['m_Crc','m_BundleSize']}=={k:z for k,z in j2.items() if k not in ['m_Crc','m_BundleSize']}
  hits.add(target)
 else:assert j1==j2
assert hits==expected
report={'status':'staged_files_verified','translation_sha256':m['translation_sha256'],'text_entries_verified':len(seen),'csv_tables':tables,'database_entries':count,'internal_names_preserved':len(m['internal_names_preserved']),'font_assets':font_count,'hangul_characters_covered':m['font']['korean_glyphs_covered'],'scripts_and_branches_unchanged':True,'foreign_languages_unchanged':True,'modified_bundle_crc_options_only':True,'game_launched':False,'runtime_rendering_verified':False}
(P/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
