"""Package the approved artwork at the original texture size; no game launch."""
import base64,datetime,hashlib,json,re,shutil,struct
from pathlib import Path
import UnityPy
import os
from PIL import Image
P=Path(__file__).resolve().parent
ROOT=P.parents[1]
GAME=Path(os.environ['BNBKR_BUILD_GAME_DATA'])
FILES={'sharedassets0.assets':15,'StreamingAssets/uipack_assets_all.bundle':-4799266148971636026}
CAT='StreamingAssets/aa/catalog.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
base=json.loads((ROOT/'patch/manifest.json').read_text(encoding='utf-8'))
manifest_path=P/'manifest.json'
if manifest_path.exists():
 m=json.loads(manifest_path.read_text(encoding='utf-8'));backup=Path(m['backup'])
 for n,v in m['before'].items():assert sha(backup/n)==v['sha256']
 # After a text-patch upgrade, rebase the logo overlay onto that verified
 # text version rather than rebuilding an obsolete dialogue database.
 if sha(GAME/'StreamingAssets/uipack_assets_all.bundle')!=m['before']['StreamingAssets/uipack_assets_all.bundle']['sha256'] or sha(GAME/CAT)!=m['before'][CAT]['sha256']:
  assert sha(GAME/'StreamingAssets/uipack_assets_all.bundle')==base['patched']['uipack_assets_all.bundle']['sha256']
  assert sha(GAME/CAT)==base['patched']['aa/catalog.json']['sha256']
  assert sha(GAME/'sharedassets0.assets')==m['before']['sharedassets0.assets']['sha256']
  write(P/('manifest_previous_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.json'),m)
  backup=P/'backups'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
  for n in [*FILES,CAT]:
   dst=backup/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(GAME/n,dst)
  m={'game_data':str(GAME),'backup':str(backup),'before':{n:{'sha256':sha(backup/n),'size':(backup/n).stat().st_size} for n in [*FILES,CAT]}}
  write(manifest_path,m)
else:
 assert sha(GAME/'StreamingAssets/uipack_assets_all.bundle')==base['patched']['uipack_assets_all.bundle']['sha256'],'Expected installed text patch'
 assert sha(GAME/CAT)==base['patched']['aa/catalog.json']['sha256'],'Unexpected catalog version'
 backup=P/'backups'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
 for n in [*FILES,CAT]:
  dst=backup/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(GAME/n,dst)
 m={'game_data':str(GAME),'backup':str(backup),'before':{n:{'sha256':sha(backup/n),'size':(backup/n).stat().st_size} for n in [*FILES,CAT]}}
 write(manifest_path,m)
stage=P/'staged';stage.mkdir(exist_ok=True)
approved=P.parent/'logo_ko_preview.png'
original=Image.open(approved).convert('RGBA')
# Pure asset-size conversion of the approved design. Keep all artwork,
# transparency, colors, and original sprite rectangle/UVs unchanged.
logo=original.resize((1377,585),Image.Resampling.LANCZOS)
assert logo.getchannel('A').getextrema()==(0,255)
logo.save(P/'logo_ko_1377x585.png')
results=[]
for name,pid in FILES.items():
 env=UnityPy.load(str(backup/name));obj=next(o for o in env.objects if o.path_id==pid)
 tex=obj.read();assert tex.m_Name=='BearGameLogo_Alpha' and (tex.m_Width,tex.m_Height)==logo.size
 # RGBA32 is a plain byte format. Set it directly to avoid importing
 # unrelated audio-export dependencies when running the frozen installer.
 tex.image_data=logo.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
 tex.m_Width,tex.m_Height=logo.size
 tex.m_CompleteImageSize=len(tex.image_data);tex.m_TextureFormat=4
 if tex.m_MipMap is not None:tex.m_MipMap=False
 if tex.m_MipCount is not None:tex.m_MipCount=1
 if tex.m_StreamData is not None:
  tex.m_StreamData.path='';tex.m_StreamData.offset=0;tex.m_StreamData.size=0
 tex.save()
 dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True)
 dest.write_bytes(env.file.save(packer='lz4') if name.endswith('.bundle') else env.file.save())
 del env
 # Reload the final file. Only the intended Texture2D object may change.
 before=UnityPy.load(str(backup/name));after=UnityPy.load(str(dest))
 a={o.path_id:o for o in before.objects};b={o.path_id:o for o in after.objects};assert set(a)==set(b)
 for oid in a:
  if oid!=pid:assert a[oid].get_raw_data()==b[oid].get_raw_data(),('Unexpected object change',name,oid)
 texture=b[pid].read();assert texture.m_TextureFormat==4;decoded=Image.frombytes('RGBA',(texture.m_Width,texture.m_Height),bytes(texture.image_data)).transpose(Image.Transpose.FLIP_TOP_BOTTOM);assert decoded.size==logo.size and decoded.tobytes()==logo.tobytes(),('Texture round trip',name)
 results.append({'file':name,'texture_id':pid,'width':1377,'height':585,'format':'RGBA32','alpha_preserved':True,'other_objects_unchanged':True,'sprites_unchanged':True})
 print('Verified logo:',name,flush=True)
 del before,after,a,b

cat=json.loads((backup/CAT).read_text(encoding='utf-8'));oldextra=base64.b64decode(cat['m_ExtraDataString']);extra=bytearray(oldextra);entries=base64.b64decode(cat['m_EntryDataString']);hits=0
for i in range(struct.unpack_from('<i',entries)[0]):
 v=struct.unpack_from('<7i',entries,4+i*28);internal=cat['m_InternalIds'][v[0]]
 if not internal.endswith('uipack_assets_all.bundle'):continue
 pos=v[4];assert extra[pos]==7
 pos+=1;pos+=1+extra[pos];pos+=1+extra[pos];length=struct.unpack_from('<i',extra,pos)[0];pos+=4
 text=bytes(extra[pos:pos+length]).decode('utf-16-le');opts=json.loads(text);assert opts['m_Crc']==0
 match=re.search(r'"m_BundleSize":(\d+)\s*',text);assert match
 value=str((stage/'StreamingAssets/uipack_assets_all.bundle').stat().st_size);old=match.group(0);new='"m_BundleSize":'+value
 assert len(new)<=len(old)
 text=text[:match.start()]+new.ljust(len(old))+text[match.end():]
 encoded=text.encode('utf-16-le');assert len(encoded)==length
 extra[pos:pos+length]=encoded;assert json.loads(text)['m_BundleSize']==int(value);hits+=1
assert hits==1 and len(extra)==len(oldextra)
cat['m_ExtraDataString']=base64.b64encode(extra).decode('ascii')
(stage/CAT).parent.mkdir(parents=True,exist_ok=True);(stage/CAT).write_text(json.dumps(cat,separators=(',',':'),ensure_ascii=False),encoding='utf-8')
m.update({'staged':str(stage),'approved_image':str(approved),'approved_image_sha256':sha(approved),'texture_size':[1377,585],'after':{n:{'sha256':sha(stage/n),'size':(stage/n).stat().st_size} for n in m['before']},'verification':results,'text_patch_preserved':True,'catalog_offsets_preserved':True,'unchanged_external_resource':{'file':'sharedassets0.assets.resS','sha256':sha(GAME/'sharedassets0.assets.resS')},'game_launched':False,'runtime_rendering_verified':False})
write(manifest_path,m)
write(P/'verification.json',{'status':'verified','approved_image_sha256':m['approved_image_sha256'],'files':m['after'],'checks':results,'text_patch_preserved':True,'game_launched':False})
print('Logo patch ready; game files unchanged until install.py runs.',flush=True)
