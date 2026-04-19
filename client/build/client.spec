# PyInstaller 빌드 스펙 파일
# 빌드 명령어 (client/ 디렉터리에서 실행):
#   .venv/Scripts/pyinstaller build/client.spec

block_cipher = None

a = Analysis(
    ["../app/main.py"],
    pathex=["../"],          # app 패키지 루트를 경로에 추가
    binaries=[],
    datas=[
        # QSS 스타일시트 — GUI 색상·레이아웃에 필수
        ("../app/ui/styles", "app/ui/styles"),
    ],
    hiddenimports=[
        # ── 계측기 드라이버 (데코레이터 기반 동적 등록, 자동 감지 안 됨) ──
        "app.instruments.drivers.lcr_meter.e4980a",
        "app.instruments.drivers.dc_source.b2901a",
        # ── 광학 설계분석 페이지 ──
        "app.ui.pages.optical_page",
        # ── PyVISA 백엔드 ──
        "pyvisa",
        "pyvisa.resources",
        "pyvisa.resources.gpib",
        # ── PyQt6 플러그인 ──
        "PyQt6.sip",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # 미사용 대형 모듈 제외 → 빌드 크기 감소
        "PyQt6.QtWebEngine",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtMultimedia",
        "PyQt6.QtBluetooth",
        "PyQt6.QtNfc",
        "PyQt6.Qt3DCore",
    ],
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
    icon="../app/ui/styles/icon.ico",
    name="RIMS",
    debug=False,
    strip=False,
    upx=False,       # UPX 압축 비활성화 — Qt 플러그인 지연 로딩 시 버벅거림 방지
    console=False,   # 콘솔 창 숨김 (GUI 전용)
)
