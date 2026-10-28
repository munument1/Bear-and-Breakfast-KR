"""Regression tests for new/empty saves and different cached Lua layouts.

Run: python -m unittest discover -s tests -v
Only temporary synthetic saves are used; Unity data is replaced by a tiny fixture.
"""
import contextlib,gzip,io,json,os,runpy,struct,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
import msgpack

HELPER=Path(__file__).resolve().parents[1]/'resources/patch/migrate_save_text.py'
def fields(**values):return [{'title':k,'value':v} for k,v in values.items()]
DB={'m_Name':'Main Database','items':[{'id':1,'fields':fields(Name='Quest One')}],
    'actors':[{'fields':fields(Name='Hank')}],'locations':[]}
ROWS=[{'key':'quest/1/Display Name','source':'Main Database','category':'Quests','en':'Old title','ko':'새 제목'},
      {'key':'quest/1/Entry 1','source':'Main Database','category':'Quests','en':'Old objective','ko':'새 목표'},
      {'key':'actors/1/Name','source':'Main Database','category':'Actor names','en':'Hank','ko':'행크'}]

class SaveMigrationTests(unittest.TestCase):
 def migrate(self,lua,header=None,expect_error=False):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'patch').mkdir();(root/'translation').mkdir();(root/'saves').mkdir()
   (root/'translation/translated.json').write_text(json.dumps(ROWS),encoding='utf-8')
   (root/'patch/manifest.json').write_text(json.dumps({'backup':str(root/'original')}),encoding='utf-8')
   helper=root/'patch/migrate_save_text.py';helper.write_bytes(HELPER.read_bytes())
   state={'inventory':[1,2,3],'progress':{'gold':32,'flags':[True,False]},'dialogueSystemData':lua}
   payload=msgpack.packb(state,use_bin_type=True)
   if header and lua:
    b=lua.encode();token=msgpack.packb(lua,use_bin_type=True)
    prefix={'str8':lambda:b'\xd9'+bytes([len(b)]),'str16':lambda:b'\xda'+struct.pack('>H',len(b)),
            'str32':lambda:b'\xdb'+struct.pack('>I',len(b))}[header]()
    payload=payload.replace(token,prefix+b,1)
   raw=gzip.compress(payload+b'\0'*1024,mtime=0);save=root/'saves/Save0';save.write_bytes(raw)
   fake=types.ModuleType('UnityPy')
   obj=types.SimpleNamespace(type=types.SimpleNamespace(name='MonoBehaviour'),read_typetree=lambda:DB)
   fake.load=lambda *args:types.SimpleNamespace(objects=[obj])
   with patch.dict(sys.modules,{'UnityPy':fake}),patch.dict(os.environ,{'BNBKR_SAVE_DIR':str(save.parent)}),patch.object(sys,'argv',[str(helper),'ko']),patch('subprocess.run',return_value=types.SimpleNamespace(stdout=b'')),contextlib.redirect_stdout(io.StringIO()):
    if expect_error:
     with self.assertRaises(AssertionError):runpy.run_path(str(helper),run_name='__main__')
     self.assertEqual(save.read_bytes(),raw);return
    runpy.run_path(str(helper),run_name='__main__')
   unpacker=msgpack.Unpacker(raw=False);unpacker.feed(gzip.decompress(save.read_bytes()));after=next(unpacker)
   self.assertEqual(after['inventory'],state['inventory']);self.assertEqual(after['progress'],state['progress'])
   report=json.loads((root/'patch/save_text_migration.json').read_text(encoding='utf-8'))['save_reports'][0]
   return after['dialogueSystemData'],report,save.read_bytes()==raw
 def test_new_empty_dialogue_unchanged(self):
  for lua in [None,'','Item = {}','Actor = {}; Item = {}; Variable = {}']:
   with self.subTest(lua=lua):
    result,r,unchanged=self.migrate(lua);self.assertEqual(result,lua);self.assertTrue(unchanged);self.assertEqual(r['changed_fields'],0)
 def test_unknown_quest_unchanged(self):
  lua='Item = { unknown = { Name="Unknown", Display_Name="Keep this", State="in progress" } }'
  result,r,unchanged=self.migrate(lua);self.assertTrue(unchanged);self.assertEqual(result,lua);self.assertEqual(r['quest_tables_checked'],0)
 def test_nested_item_table(self):
  lua='Item = { Quest_One={Name="Quest One", Display_Name="Old title", Entry_1="Old objective", State="in progress", Entry_1_State="available"} }'
  result,r,_=self.migrate(lua);self.assertIn('새 제목',result);self.assertIn('새 목표',result);self.assertIn('State="in progress"',result);self.assertEqual(r['quest_tables_checked'],1)
 def test_indexed_item_table(self):
  lua='Item["Quest_One"]={Name="Quest One", Display_Name="Old title", State="success"}'
  result,r,_=self.migrate(lua);self.assertIn('새 제목',result);self.assertIn('State="success"',result);self.assertEqual(r['quest_tables_checked'],1)
 def test_actor_only_and_string_headers(self):
  lua='Actor={Hank={Name="Hank",Display_Name="행크"}}'
  for header in [None,'str8','str16','str32']:
   with self.subTest(header=header):
    result,r,_=self.migrate(lua,header)
    self.assertIn('Display_Name="Hank"',result);self.assertEqual(r['quest_tables_checked'],0);self.assertEqual(r['changed_fields'],1)
 def test_short_fixstr_header(self):
  result,r,_=self.migrate('Variable={Actor="행크"}')
  self.assertIn('Actor="Hank"',result);self.assertEqual(r['quest_tables_checked'],0)
 def test_malformed_lua_still_rejected_without_save_changes(self):self.migrate('Item={',expect_error=True)

if __name__=='__main__':unittest.main()
