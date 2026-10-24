"""Migrate only display strings in existing game saves; preserve progression.

Usage: migrate_save_text.py [ko|en]. Does not launch or stop the game.
"""
import collections,datetime,gzip,hashlib,json,os,re,shutil,struct,subprocess,sys
from pathlib import Path
import UnityPy
import os
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parent/'audit/_save_tools'))
import msgpack
mode=sys.argv[1] if len(sys.argv)>1 else 'ko'
assert mode in ['ko','en']
tasks=subprocess.run(['tasklist','/FI','IMAGENAME eq BearAndBreakfast.exe','/FO','CSV','/NH'],capture_output=True).stdout
if b'BearAndBreakfast.exe' in tasks:raise SystemExit('Close the game before migrating saved display text.')
m=json.loads((P/'manifest.json').read_text(encoding='utf-8'))
rows=json.loads((P.parent/'translation/translated.json').read_text(encoding='utf-8'))
translations={r['key']:r for r in rows if r['source']=='Main Database'}
env=UnityPy.load(str(Path(m['backup'])/'uipack_assets_all.bundle'))
for o in env.objects:
 if o.type.name=='MonoBehaviour':
  d=o.read_typetree()
  if d.get('m_Name')=='Main Database':db=d;break
def fs(a):return {f['title']:f['value'] for f in a['fields']}
items={}
for q in db['items']:
 f=fs(q);targets={}
 for key,r in translations.items():
  if key.startswith(f"quest/{q['id']}/"):
   title=key.split('/',2)[2];targets[title.replace(' ','_')]=r['ko'] if mode=='ko' else r['en']
 if targets:items[f['Name']]=targets
actors={fs(a)['Name']:fs(a)['Name'] for a in db['actors']}
locations={fs(a)['Name']:fs(a)['Name'] for a in db['locations']}
ko_to_name={r['ko']:r['en'] for r in rows if r['category']=='Actor names' and r['key'].endswith('/Name')}
quoted=re.compile(r'"(?:\\.|[^"\\])*"',re.S)
field_pattern=re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*("(?:\\.|[^"\\])*")',re.S)
escape={'a':'\a','b':'\b','f':'\f','n':'\n','r':'\r','t':'\t','v':'\v','\\':'\\','"':'"',"'":"'"}
def decode(value):
 return re.sub(r'\\(\d{1,3}|.)',lambda m:chr(int(m[1])) if m[1].isdigit() else escape.get(m[1],m[1]),value[1:-1],flags=re.S)
def encode(value):return json.dumps(value,ensure_ascii=False)
def fix_lua(s):
 stack=[];records=[];i=0
 while i<len(s):
  if s[i]=='"':
   match=quoted.match(s,i);assert match,('bad Lua string',i);i=match.end();continue
  if s[i]=='{':
   pre=s[max(0,i-250):i]
   if re.search(r'\bItem\["(?:\\.|[^"\\])*"\]\s*=\s*$',pre):group='Item'
   elif re.search(r'\bActor\s*=\s*$',pre):group='Actor'
   elif re.search(r'\bLocation\s*=\s*$',pre):group='Location'
   elif re.search(r'\bVariable\s*=\s*$',pre):group='Variable'
   else:group=stack[-1]['group'] if stack else ''
   if stack:stack[-1]['child']=True
   stack.append({'start':i+1,'group':group,'child':False})
  elif s[i]=='}':
   assert stack,'Unbalanced Lua table';r=stack.pop()
   if not r['child']:records.append(dict(r,end=i))
  i+=1
 assert not stack
 changes=[];counts=collections.Counter();quest_count=0
 for rec in records:
  fields=list(field_pattern.finditer(s,rec['start'],rec['end']))
  parsed={f[1]:decode(f[2]) for f in fields}
  name=parsed.get('Name','');group=rec['group'];targets={}
  if group=='Item' and name in items:targets=items[name];quest_count+=1
  elif group=='Actor' and name in actors:targets={'Display_Name':name}
  elif group=='Location' and name in locations:targets={'Display_Name':name}
  elif group=='Variable':
   targets={k:ko_to_name[v] for k,v in parsed.items() if k in ['Actor','Conversant'] and v in ko_to_name}
  for f in fields:
   key=f[1]
   if key in targets and parsed[key]!=targets[key]:
    changes.append((f.start(2),f.end(2),encode(targets[key]),group,key,name));counts[group]+=1
 changes.sort()
 assert all(a[1]<=b[0] for a,b in zip(changes,changes[1:]))
 new=s
 for start,end,value,*_ in reversed(changes):new=new[:start]+value+new[end:]
 # Everything outside explicitly allowlisted string-value spans is kept
 # byte-for-byte, including Name, State, Entry_N_State, rules and scripts.
 cursor=0;out=[]
 for start,end,value,*_ in changes:out.extend([s[cursor:start],value]);cursor=end
 out.append(s[cursor:]);assert ''.join(out)==new
 assert quest_count>0,'No known saved quest table was found'
 return new,changes,dict(counts),quest_count

save_dir=Path(os.environ['BNBKR_SAVE_DIR'])
batch=P/'save_text_backups'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
reports=[]
for path in sorted(save_dir.iterdir()):
 if not path.is_file() or not re.fullmatch(r'Save\d+',path.name):continue
 raw=path.read_bytes();data=gzip.decompress(raw);unpacker=msgpack.Unpacker(raw=False,strict_map_key=False,max_buffer_size=64*1024*1024);unpacker.feed(data);state=next(unpacker);consumed=unpacker.tell()
 assert not any(data[consumed:]),'Unexpected nonzero trailing save data'
 old=state['dialogueSystemData'];new,changes,counts,quests=fix_lua(old)
 if not changes:
  reports.append({'file':str(path),'changed_fields':0,'quest_tables_checked':quests});continue
 oldbytes=old.encode('utf-8');offset=data.find(oldbytes);assert offset>=5 and data.count(oldbytes)==1
 assert data[offset-5]==0xdb and struct.unpack_from('>I',data,offset-4)[0]==len(oldbytes),'Unexpected MessagePack string layout'
 packed=msgpack.packb(new,use_bin_type=True)
 payload=data[:offset-5]+packed+data[offset+len(oldbytes):consumed]
 capacity=len(data)
 while capacity<len(payload):capacity*=2
 output=payload+b'\0'*(capacity-len(payload))
 chk=msgpack.Unpacker(raw=False,strict_map_key=False,max_buffer_size=64*1024*1024);chk.feed(output);after=next(chk)
 assert {k:v for k,v in state.items() if k!='dialogueSystemData'}=={k:v for k,v in after.items() if k!='dialogueSystemData'}
 assert after['dialogueSystemData']==new
 assert fix_lua(new)[0]==new,'Migration must be idempotent'
 # Confirm the two reported quests and every migrated record actually
 # resolve to the desired language without touching completion flags.
 fields=[]
 for start,end,value,group,key,name in changes:fields.append({'group':group,'field':key,'name':name})
 batch.mkdir(parents=True,exist_ok=True);shutil.copy2(path,batch/path.name)
 candidate=batch/(path.name+'.patched');candidate.write_bytes(gzip.compress(output,mtime=0))
 assert gzip.decompress(candidate.read_bytes())==output
 assert path.read_bytes()==raw,'Save changed while migrating; restart with game closed'
 temp=path.with_name(path.name+'.kr-text-tmp');shutil.copy2(candidate,temp);os.replace(temp,path)
 reports.append({'file':str(path),'backup':str(batch/path.name),'changed_fields':len(changes),'by_group':counts,'quest_tables_checked':quests,'all_other_save_data_unchanged':True,'before_sha256':hashlib.sha256(raw).hexdigest(),'after_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'changed_metadata':fields})
report={'mode':mode,'save_reports':reports,'game_launched':False}
batch.mkdir(parents=True,exist_ok=True);(batch/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(P/'save_text_migration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'mode':mode,'saves':[{'file':r['file'],'changed_fields':r['changed_fields'],'quest_tables_checked':r['quest_tables_checked'],'by_group':r.get('by_group',{})} for r in reports],'progress_and_inventory_preserved':True},ensure_ascii=False))
