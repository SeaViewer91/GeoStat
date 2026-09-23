"""PyInstaller 런타임 훅: 번들 안의 GDAL·PROJ 데이터 경로를 지정함.

사용자 PC에 설치된 다른 GDAL/PROJ(예: Homebrew, QGIS)의 데이터를 잘못 참조하지 않도록
번들 경로를 우선 사용함.
"""

import os
import sys
from pathlib import Path

base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

gdal_data = base / "pyogrio" / "gdal_data"
if gdal_data.is_dir():
    os.environ["GDAL_DATA"] = str(gdal_data)

for proj_dir in (base / "pyproj" / "proj_dir" / "share" / "proj", base / "pyogrio" / "proj_data"):
    if (proj_dir / "proj.db").is_file():
        os.environ["PROJ_DATA"] = str(proj_dir)
        os.environ["PROJ_LIB"] = str(proj_dir)  # PROJ 9 이전 호환용
        break
