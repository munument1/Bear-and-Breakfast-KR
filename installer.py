"""Windows installer for Bear and Breakfast Korean localization v0.1.1."""
import argparse,contextlib,datetime,hashlib,json,os,runpy,shutil,subprocess,sys,traceback
from pathlib import Path
VERSION='0.1.1'
BASE=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
RES=BASE/'resources'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def run(path,*args):
 old=sys.argv[:]
 try:sys.argv=[str(path),*args];runpy.run_path(str(path),run_name='__main__')
 finally:sys.argv=old
def no_game():
 r=subprocess.run(['tasklist','/FI','IMAGENAME eq BearAndBreakfast.exe','/FO','CSV','/NH'],capture_output=True)
 if b'BearAndBreakfast.exe' in r.stdout:raise RuntimeError('게임을 종료한 뒤 다시 실행해 주세요.')
def save_dir():return Path(os.environ['USERPROFILE'])/'AppData/LocalLow/GummyCat/BearAndBreakfast'
def restore_files(data,backup,names):
 for name in names:
  target=data/name;temp=target.with_name(target.name+'.bnbkr-tmp')
  shutil.copy2(backup/name,temp);os.replace(temp,target)
def migrate(work,mode,skip):
 if skip or not save_dir().exists() or not any(save_dir().glob('Save[0-9]*')):return
 os.environ['BNBKR_SAVE_DIR']=str(save_dir())
 # Existing installs may still cache an older migration helper. Refresh it
 # for both reinstall and restore without rebuilding unchanged game assets.
 shutil.copy2(RES/'patch/migrate_save_text.py',work/'patch/migrate_save_text.py')
 run(work/'patch/migrate_save_text.py',mode)
def install(data,skip_saves=False):
 no_game();config=read(RES/'supported.json');names=list(config['original_sha256'])
 home=data.parent/'.BearAndBreakfast-KR';status=home/'installed.json'
 if status.exists():
  state=read(status)
  if state['status']=='installed':
   for name,value in state['installed_sha256'].items():
    if sha(data/name)!=value:raise RuntimeError('설치 후 게임 파일이 변경되었습니다. Steam 무결성 검사를 한 뒤 다시 설치해 주세요.')
   migrate(Path(state['work']), 'ko',skip_saves)
   state['version']=VERSION;write(status,state)
   print(f'이미 패치가 설치되어 있습니다. v{VERSION}으로 저장 파일 표시 문구를 확인했습니다.');return
 for name,value in config['original_sha256'].items():
  if not (data/name).is_file() or sha(data/name)!=value:raise RuntimeError('지원하는 원본 게임 파일과 다릅니다: '+name+'\nSteam 무결성 검사로 원본을 복원해 주세요. 지원 빌드: 20292966')
 if not (Path(os.environ.get('WINDIR',r'C:\Windows'))/'Fonts/malgun.ttf').is_file():raise RuntimeError('Windows 맑은 고딕 폰트가 필요합니다.')
 stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f');work=home/stamp;backup=work/'original'
 shutil.copytree(RES,work)
 for name in names:
  dst=backup/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(data/name,dst)
 base_names=[n.removeprefix('StreamingAssets/') for n in names if n.startswith('StreamingAssets/')]
 originals={n:{'sha256':sha(backup/'StreamingAssets'/n),'size':(backup/'StreamingAssets'/n).stat().st_size} for n in base_names}
 write(work/'patch/manifest.json',{'game_streaming_assets':str(data/'StreamingAssets'),'backup':str(backup/'StreamingAssets'),'originals':originals})
 os.environ['BNBKR_GAME_DATA']=str(data)
 print('1/4 한글 텍스트와 폰트 생성 중...',flush=True);run(work/'patch/build_patch.py')
 print('2/4 텍스트·이름·분기 검증 중...',flush=True);run(work/'patch/verify_patch.py')
 preview=work/'preview';preview.mkdir()
 for name in base_names:
  dst=preview/'StreamingAssets'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(work/'patch/staged'/name,dst)
 shutil.copy2(backup/'sharedassets0.assets',preview/'sharedassets0.assets')
 resource=data/'sharedassets0.assets.resS'
 try:os.link(resource,preview/resource.name)
 except OSError:shutil.copy2(resource,preview/resource.name)
 os.environ['BNBKR_BUILD_GAME_DATA']=str(preview)
 print('3/4 한글 로고 생성 및 검증 중...',flush=True);run(work/'image_localization/logo_patch/build.py')
 logo=read(work/'image_localization/logo_patch/manifest.json');final={}
 for name in names:
  source=work/'image_localization/logo_patch/staged'/name if name in logo['after'] else work/'patch/staged'/name.removeprefix('StreamingAssets/')
  final[name]=source
 # Only now replace game files; all generated files have passed verification.
 no_game();changed=[];saves_backup=work/'save_transaction';saves_backup.mkdir()
 if not skip_saves and save_dir().exists():
  import re
  for p in save_dir().iterdir():
   if p.is_file() and re.fullmatch(r'Save\d+',p.name):shutil.copy2(p,saves_backup/p.name)
 try:
  print('4/4 설치 및 기존 퀘스트 표시 문구 수정 중...',flush=True)
  for name,source in final.items():
   target=data/name;tmp=target.with_name(target.name+'.bnbkr-tmp');shutil.copy2(source,tmp);os.replace(tmp,target);changed.append(name)
   assert sha(target)==sha(source)
  migrate(work,'ko',skip_saves)
  write(status,{'version':VERSION,'status':'installed','game_data':str(data),'work':str(work),'backup':str(backup),'original_sha256':config['original_sha256'],'installed_sha256':{n:sha(data/n) for n in names}})
 except BaseException:
  restore_files(data,backup,changed)
  for p in saves_backup.iterdir():shutil.copy2(p,save_dir()/p.name)
  raise
 print('설치 완료! 게임 언어를 English로 선택해 주세요. 게임 실행은 직접 해 주세요.')
def uninstall(data,skip_saves=False):
 no_game();status=data.parent/'.BearAndBreakfast-KR/installed.json'
 if not status.exists():raise RuntimeError('이 설치 프로그램의 설치 기록을 찾지 못했습니다.')
 state=read(status)
 if state['status']=='restored':print('이미 원복되었습니다.');return
 for name,value in state['installed_sha256'].items():
  if sha(data/name)!=value:raise RuntimeError('설치 후 게임 파일이 변경되어 자동 원복을 중단했습니다: '+name)
 for name,value in state['original_sha256'].items():
  if sha(Path(state['backup'])/name)!=value:raise RuntimeError('원본 백업 확인 실패: '+name)
 work=Path(state['work']);rollback=work/'uninstall_rollback';rollback.mkdir(exist_ok=True)
 for name in state['installed_sha256']:
  target=rollback/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(data/name,target)
 saves_backup=work/'uninstall_save_transaction'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f');saves_backup.mkdir(parents=True)
 if not skip_saves and save_dir().exists():
  import re
  for p in save_dir().iterdir():
   if p.is_file() and re.fullmatch(r'Save\d+',p.name):shutil.copy2(p,saves_backup/p.name)
 try:
  migrate(work,'en',skip_saves)
  restore_files(data,Path(state['backup']),state['original_sha256'])
  for name,value in state['original_sha256'].items():assert sha(data/name)==value
  state['status']='restored';write(status,state)
 except BaseException:
  restore_files(data,rollback,state['installed_sha256'])
  for p in saves_backup.iterdir():shutil.copy2(p,save_dir()/p.name)
  raise
 print('원복 완료. 현재 진행 상황은 유지하고 표시 문구와 게임 파일을 원본으로 복원했습니다.')
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--game',type=Path);parser.add_argument('--mode',choices=['install','restore']);parser.add_argument('--skip-saves',action='store_true',help=argparse.SUPPRESS);args=parser.parse_args()
 interactive=args.mode is None
 game=args.game or Path(sys.executable if getattr(sys,'frozen',False) else __file__).resolve().parent
 if not (game/'BearAndBreakfast_Data').is_dir():
  import tkinter as tk
  from tkinter import filedialog
  root=tk.Tk();root.withdraw();selected=filedialog.askdirectory(title='BearAndBreakfast.exe가 있는 게임 폴더를 선택하세요');root.destroy()
  if not selected:return
  game=Path(selected)
 if not (game/'BearAndBreakfast_Data').is_dir():raise RuntimeError('게임 폴더를 확인해 주세요.')
 mode=args.mode
 if mode is None:
  print(f'Bear and Breakfast 한국어 패치 v{VERSION}\n1: 설치 / 2: 원복 / 그 외: 종료')
  choice=input('선택: ').strip();mode={'1':'install','2':'restore'}.get(choice)
  if mode is None:return
 home=game/'.BearAndBreakfast-KR';home.mkdir(exist_ok=True)
 log=home/('installer_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.log')
 class Tee:
  def __init__(self,*streams):self.streams=streams
  def write(self,text):
   for s in self.streams:s.write(text);s.flush()
  def flush(self):
   for s in self.streams:s.flush()
 with log.open('w',encoding='utf-8') as f,contextlib.redirect_stdout(Tee(sys.stdout,f)),contextlib.redirect_stderr(Tee(sys.stderr,f)):
  try:(install if mode=='install' else uninstall)(game/'BearAndBreakfast_Data',args.skip_saves)
  except Exception:
   traceback.print_exc();print('처리하지 못했습니다. 로그:',log)
   if interactive:input('Enter 키로 닫기...')
   raise
 if interactive:input('Enter 키로 닫기...')
if __name__=='__main__':main()
