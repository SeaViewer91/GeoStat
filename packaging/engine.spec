# -*- mode: python ; coding: utf-8 -*-
# GeoStat 엔진 PyInstaller 설정 (onedir)
#
# onefile은 실행할 때마다 임시 폴더에 압축을 풀어 시작이 느리고, macOS 서명·공증 시
# 내부 바이너리를 서명할 수 없어 쓰지 않음.
#
# 실행: packaging/build-engine.sh

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

hiddenimports = []
# uvicorn은 문자열로 모듈을 불러오는 부분이 많아 정적 분석으로 잡히지 않음
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("geostat_engine")

datas = []
binaries = []
# 컴파일 확장 모듈끼리 서로 임포트하는 경우(pyogrio._io → pyogrio._geometry, rasterio._base →
# rasterio.serde 등)와 GDAL(gdal_data)·PROJ(proj.db) 데이터 파일까지 통째로 모음
for pkg in ("pyogrio", "pyproj", "shapely", "rasterio", "exactextract"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    # SPECPATH: 이 spec 파일이 있는 폴더 (PyInstaller가 제공함)
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[os.path.join(SPECPATH, "rthook_geodata.py")],
    # 엔진에 필요 없는 무거운 패키지는 제외해 번들 용량을 줄임
    excludes=["tkinter", "matplotlib", "IPython", "notebook", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="geostat-engine",
    debug=False,
    strip=False,
    upx=False,  # UPX 압축 바이너리는 macOS 서명·공증에서 문제를 일으킴
    console=True,
    # 서명은 packaging/macos/sign-engine.sh에서 일괄 처리함
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="geostat-engine",
)
