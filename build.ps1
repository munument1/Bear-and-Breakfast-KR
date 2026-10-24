$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$resourcePath = Join-Path $PSScriptRoot 'resources'
python -m PyInstaller --noconfirm --clean --onefile --name BearAndBreakfast-KR-v0.1 --exclude-module torch --exclude-module pandas --exclude-module scipy --exclude-module matplotlib --exclude-module IPython --exclude-module pytest --exclude-module tensorflow --exclude-module fmod_toolkit --exclude-module pyfmodex --collect-all UnityPy --collect-all texture2ddecoder --hidden-import msgpack --hidden-import fontTools.ttLib --hidden-import PIL.Image --hidden-import tkinter --add-data "$resourcePath;resources" installer.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
