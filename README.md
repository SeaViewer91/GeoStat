# GeoStat

macOS용 공간통계 분석 데스크톱 앱임. GeoDa 수준의 탐색적 공간자료분석(ESDA), 공간회귀, 공간군집화에
GWR/MGWR, 한국 좌표계·한글 UI, 래스터·대용량 데이터 지원을 더하는 것을 목표로 함.

> 🚧 개발 초기 단계임. 아직 설치 가능한 빌드는 없음.

## 주요 기능 (계획)

- **데이터 입력**: Shapefile, GeoPackage, GeoJSON, FlatGeobuf, CSV(좌표) 지원. cp949 DBF 자동 처리, 한국 좌표계 프리셋 제공
- **공간가중치**: Queen/Rook, 거리, KNN, 커널 지원. GeoDa `.gal`/`.gwt`와 호환됨
- **ESDA**: Global/Local Moran's I, Getis-Ord Gi*, Local Geary, Join Count 제공
- **연동 시각화**: 지도·히스토그램·산점도·박스플롯·Moran 산점도 간 선택이 연동됨
- **공간회귀**: OLS 공간진단, Spatial Lag/Error, **GWR/MGWR** 제공
- **공간군집화**: SKATER, Max-p, AZP, Region K-Means, Ward 제공
- **래스터**: GeoTIFF/COG 표시, 존 통계 산출

## 구조

| 구성 | 기술 |
|---|---|
| 앱 셸 | Tauri 2 (Rust) |
| UI | React + TypeScript, deck.gl (GeoArrow 레이어) |
| 분석 엔진 | Python (FastAPI) + PySAL (libpysal, esda, spreg, mgwr, spopt) |

```
GeoStat/
├─ apps/desktop/      # Tauri 셸(src-tauri)과 React 프론트엔드(src)
├─ engine/            # Python 분석 엔진 (uv 프로젝트)
├─ packaging/         # 엔진 번들링·서명·공증 스크립트
├─ scripts/           # 샘플 데이터 생성 등 개발 보조 스크립트
└─ docs/              # 개발 계획서 등 문서
```

자세한 내용은 [개발 계획서](docs/DEVELOPMENT_PLAN.md) 참고.

## 개발 환경 구성 (macOS)

### 필요 도구

- [Rust](https://rustup.rs) (stable)
- Node.js 20 이상
- [uv](https://docs.astral.sh/uv/) (Python 버전·의존성 관리)
- Xcode Command Line Tools (`xcode-select --install`)

### 실행

```bash
# 1. 엔진 의존성 설치 (Python 3.12 자동 설치됨)
cd engine && uv sync && cd ..

# 2. 프론트엔드 의존성 설치
cd apps/desktop && npm install

# 3. 개발 모드 실행 (엔진이 자동으로 함께 실행됨)
npm run tauri dev
```

엔진만 따로 띄워 디버깅하려면 아래와 같이 실행함. 이때 앱은 엔진을 새로 띄우지 않고 지정한 주소에 붙음.

```bash
cd engine && uv run geostat-engine --port 8765 --token dev
# 다른 터미널에서
cd apps/desktop && GEOSTAT_ENGINE_URL=http://127.0.0.1:8765 GEOSTAT_ENGINE_TOKEN=dev npm run tauri dev
```

### 테스트

```bash
cd engine && uv run pytest
cd apps/desktop && npm run typecheck
```

### 앱 번들 빌드

```bash
packaging/build-engine.sh             # 엔진만 PyInstaller로 빌드하고 스모크 테스트함
packaging/macos/release.sh --unsigned # 서명 없는 .app/.dmg (로컬 확인용)
packaging/macos/release.sh            # 서명·공증 포함. 필요한 환경변수는 스크립트 주석 참고
```

### 샘플 데이터 생성

```bash
cd engine && uv run python ../scripts/make_sample_data.py   # data/local/ 에 생성됨
```

## 라이선스

[MIT](LICENSE)
