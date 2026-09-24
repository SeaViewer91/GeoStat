# GeoStat

macOS용 공간통계 분석 데스크톱 앱임. GeoDa 수준의 탐색적 공간자료분석(ESDA), 공간회귀, 공간군집화에
GWR/MGWR, 한국 좌표계·한글 UI, 래스터·대용량 데이터 지원을 더하는 것을 목표로 함.

> 🚧 개발 초기 단계임. 아직 설치 가능한 빌드는 없음.

## 설치 (릴리스 이후)

[Releases](https://github.com/SeaViewer91/GeoStat/releases)에서 `.dmg`를 받아 `GeoStat.app`을 응용 프로그램 폴더로 옮김.

macOS 14(Sonoma) 이상, Apple Silicon 맥이 필요함.

Apple 공증을 받지 않은 앱이라 첫 실행 때 "확인되지 않은 개발자" 경고가 뜸. 아래 중 하나로 한 번만 허용하면 됨.

- **시스템 설정 → 개인정보 보호 및 보안** 맨 아래의 **"그래도 열기"** 클릭
- 또는 터미널에서 `xattr -dr com.apple.quarantine /Applications/GeoStat.app` 실행

## 주요 기능

✅ 구현됨 · 🚧 개발 예정

- ✅ **데이터 입력**: Shapefile, GeoPackage, GeoJSON, FlatGeobuf, CSV·엑셀(X·Y 좌표) 지원. cp949 DBF·CSV 자동 처리, 한국 좌표계 프리셋 제공
- ✅ **주제도**: 분위수·등간격·자연 분류·표준편차·백분위·박스·0 기준 발산·고유값 지도, 범례 클릭 선택, 배경지도(OpenFreeMap)
- ✅ **속성 테이블**: 정렬, 선택 연동, 계산 필드(식), 내보내기(GeoPackage·Shapefile·GeoJSON·CSV, 좌표계 변환)
- ✅ **선택**: 클릭·사각형·올가미, 지도·테이블·범례 간 연동
- ✅ **프로젝트**: `.gstproj`로 저장·열기 (원본 경로와 작업 과정을 기록해 재현함)
- ✅ **공간가중치**: Queen/Rook(고차), 거리, KNN, 커널. 연결성 히스토그램, 섬 탐지, GeoDa `.gal`/`.gwt` 호환
- ✅ **ESDA**: Moran's I(단변량·이변량), LISA, Getis-Ord Gi*, Local Geary, Join Count. FDR·Bonferroni 보정, 군집·유의성 지도
- ✅ **연동 차트**: 히스토그램·산점도·박스플롯·Moran 산점도와 지도·테이블 간 선택 연동
- ✅ **공간회귀**: OLS(공간진단·LM 검정·White 강건 표준오차), Spatial Lag/Error(ML·GM), 직접·간접 효과, **GWR/MGWR**(유의성 마스크 계수 지도), 모형 비교표(AICc·잔차 Moran's I), 진행률·취소, 텍스트 보고서
- ✅ **공간군집화**: SKATER, Max-p, AZP, Region K-Means, Ward(공간 제약)와 비교용 K-평균·계층적 군집. 군집 지도, 군집별 프로필·제곱합 비, 공간 조각 수
- ✅ **래스터**: GeoTIFF/COG 표시(색상표·RGB 합성·오버뷰), 존 통계(면적 가중), 정사각·육각 격자 만들기 → 격자 단위 ESDA

## 사용법

| 동작 | 방법 |
|---|---|
| 데이터 열기 / 프로젝트 열기 | ⌘O / ⇧⌘O |
| 프로젝트 저장 / 다른 이름으로 | ⌘S / ⇧⌘S |
| 사각형 선택 | B, 또는 Shift를 누른 채 끌기 |
| 올가미 선택 | L (피처 중심점 기준) |
| 선택 도구 해제 | Esc |
| 기존 선택에 추가 | ⌘를 누른 채 클릭·끌기 |
| 속성 테이블 열기·닫기 | ⌘T |
| 차트 패널 열기·닫기 | ⌘J |

계산 필드 식은 pandas 문법을 씀. 한글·공백이 있는 열 이름은 백틱으로 감쌈 (예: `` `인구` / `면적` * 1000 ``, `` log(`소득`) ``, `` (`인구` > 5000) * 1 ``).

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
packaging/build-engine.sh    # 엔진만 PyInstaller로 빌드하고 스모크 테스트함
packaging/macos/release.sh   # 엔진 빌드 → ad-hoc 서명 → .app/.dmg 생성
```

### 성능 측정

```bash
cd engine && uv run python ../scripts/benchmark.py --n 100000   # 열기·가중치·LISA·GWR 시간을 표로 출력함
```

### 샘플 데이터 생성

```bash
cd engine && uv run python ../scripts/make_sample_data.py   # data/local/ 에 생성됨
```

## 라이선스

[MIT](LICENSE)
