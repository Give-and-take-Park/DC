# PyInstaller 빌드 스펙 파일
# 빌드 명령어: pyinstaller build/client.spec

block_cipher = None

a = Analysis(
    ["../app/main.py"],
    pathex=[],
    binaries=[],
    datas=[("../resources", "resources")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="DCClient",
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon="../resources/icon.ico",
)
