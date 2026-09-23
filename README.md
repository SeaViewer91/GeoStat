# GeoStat

macOS용 공간통계 분석 데스크톱 앱 — GeoDa 수준의 탐색적 공간자료분석(ESDA), 공간회귀, 공간군집화에
GWR/MGWR, 한국 좌표계·한글 UI, 래스터·대용량 데이터 지원을 더하는 것을 목표로 합니다.

> 🚧 개발 초기 단계입니다. 아직 설치 가능한 빌드가 없습니다.

## 주요 기능 (계획)

- **데이터 입력**: Shapefile, GeoPackage, GeoJSON, FlatGeobuf, CSV(좌표) — cp949 DBF 자동 처리, 한국 좌표계 프리셋
- **공간가중치**: Queen/Rook, 거리, KNN, 커널 — GeoDa `.gal`/`.gwt` 호환
- **ESDA**: Global/Local Moran's I, Getis-Ord Gi*, Local Geary, Join Count
- **연동 시각화**: 지도·히스토그램·산점도·박스플롯·Moran 산점도 간 선택 연동
- **공간회귀**: OLS 공간진단, Spatial Lag/Error, **GWR/MGWR**
- **공간군집화**: SKATER, Max-p, AZP, Region K-Means, Ward
- **래스터**: GeoTIFF/COG 표시, 존 통계

## 구조

| 구성 | 기술 |
|---|---|
| 앱 셸 | Tauri 2 (Rust) |
| UI | React + TypeScript, MapLibre GL + deck.gl |
| 분석 엔진 | Python (FastAPI) + PySAL (libpysal, esda, spreg, mgwr, spopt) |

자세한 내용은 [개발 계획서](docs/DEVELOPMENT_PLAN.md)를 참고하세요.

## 라이선스

[MIT](LICENSE)
