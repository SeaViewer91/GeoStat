# GeoStat 개발 계획서 (v0.1 초안)

> macOS용 설치형 공간통계 분석 소프트웨어 — GeoDa 수준의 ESDA·공간회귀·군집화에 GWR/MGWR, 한국 좌표계, 래스터·대용량 지원을 더한 도구
> 작성일: 2026-09-23 · 작성: 박수호 + Claude

---

## 1. 목표와 범위

### 1.1 제품 목표
- shp / GeoPackage / GeoJSON / FlatGeobuf / CSV(좌표) 입력 → 지도·그래프 기반 탐색적 공간자료분석(ESDA) → 공간회귀·지역화까지 **한 앱에서** 수행
- GeoDa의 핵심 UX인 **연동 시각화(linked brushing)** 재현
- GeoDa 대비 차별점
  1. **GWR/MGWR 통합** — 대역폭 선택, 지역 계수 지도, 유의성 마스킹까지 GUI로
  2. **한국 환경 기본 지원** — EPSG:5186/5179/5174 등, cp949 DBF 자동 처리, 한글 UI(한/영 전환)
  3. **래스터·대용량** — GeoTIFF/COG 존 통계, 수십만 피처 WebGL 렌더링
- **외부 공개 배포** — GitHub 공개 레포 + GitHub Releases로 .dmg 배포 (앱스토어 등재·Apple 공증은 하지 않음)

### 1.2 비목표 (1.0 이전에는 하지 않음)
- 편집 GIS 기능(디지타이징, 토폴로지 편집) — QGIS 영역
- 시공간(space-time) 모델, 베이지안 공간모형(INLA 등)
- Windows/Linux 빌드 (구조는 크로스플랫폼으로 두되 검증·배포는 macOS만)

---

## 2. 아키텍처

### 2.1 전체 구조

```
┌──────────────────────── GeoStat.app ────────────────────────┐
│  Tauri 2 (Rust 셸)                                           │
│   ├─ 창/메뉴/파일 다이얼로그, 엔진 프로세스 수명주기 관리      │
│   └─ 엔진 포트·인증토큰 발급 → 프론트엔드에 전달              │
│                                                              │
│  프론트엔드 (WebView: React + TypeScript + Vite)             │
│   ├─ 지도: MapLibre GL + deck.gl (GeoArrow 바이너리 레이어)   │
│   ├─ 차트: 히스토그램/산점도/박스/Moran 산점도/PCP (Canvas)   │
│   ├─ 전역 선택 상태 스토어 (Zustand, Uint8Array 비트마스크)   │
│   └─ 속성 테이블 (가상 스크롤), 분석 대화상자, 결과 리포트     │
│               ▲  HTTP(JSON) + Arrow IPC / SSE(진행률)         │
│               ▼  127.0.0.1:<랜덤포트>, Bearer 토큰            │
│  분석 엔진 (Python 사이드카, 번들된 독립 런타임)              │
│   ├─ FastAPI + uvicorn                                       │
│   ├─ I/O: pyogrio(GDAL), pyproj, rasterio, exactextract      │
│   ├─ 통계: libpysal, esda, spreg, mgwr, spopt, mapclassify   │
│   └─ 세션 메모리: dataset_id → GeoDataFrame, weights_id → W  │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 핵심 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 엔진 통신 | 로컬 FastAPI (랜덤 포트 + 토큰) | 익숙한 스택, 디버깅 용이(브라우저·curl로 직접 호출 가능), 엔진 단독 테스트 가능 |
| 대용량 전송 | 지오메트리·컬럼은 **Arrow IPC(GeoArrow)**, 소형 결과만 JSON | GeoJSON 직렬화는 수십만 폴리곤에서 수 초~수십 초 소요. GeoArrow는 deck.gl에 거의 무복사로 전달 |
| 장시간 작업 | Job 큐 + SSE 진행률 + 취소 | MGWR, 999회 순열검정, 군집화는 수십 초~수 분 |
| 상태 소유권 | 데이터·가중치·모델은 **엔진이 소유**, 선택(selection)은 **프론트가 소유** | 브러싱은 60fps가 필요하므로 왕복 통신 없이 프론트에서 처리 |
| 분류(classification) | 엔진의 mapclassify로 계산, 경계값만 전달 | GeoDa와 결과 일치(Natural Breaks, Box map 등) |
| 프로젝트 파일 | `.gstproj` = 폴더형 번들(JSON 메타 + GeoPackage + 가중치 .gal/.gwt) | 재현성, GeoDa 가중치 파일과 호환 |
| 앱 라이선스 | MIT 또는 BSD-3 | PySAL 생태계(BSD)와 정합. **GPL 의존성(pygeoda/libgeoda) 번들 금지** — 필요 시 별도 판단 |

### 2.3 연동 시각화(linked brushing) 설계
- 모든 뷰는 `datasetId`별 **공유 선택 비트마스크**를 구독
- 지도 사각형/올가미 선택, 차트 브러시, 테이블 행 선택 → 스토어 갱신 → 전 뷰가 하이라이트만 다시 그림(데이터 재전송 없음)
- deck.gl `updateTriggers`로 색상 버퍼만 갱신, 차트는 Canvas 재렌더
- 엔진이 선택을 알아야 하는 경우(“선택을 변수로 저장”, “선택 영역만 분석”)에만 인덱스 배열 전송

### 2.4 저장소 구조

```
GeoStat/
├─ apps/desktop/
│  ├─ src/                 # React 프론트엔드
│  │  ├─ map/              # MapLibre + deck.gl 레이어
│  │  ├─ views/            # histogram, scatter, box, moran, pcp, table
│  │  ├─ dialogs/          # 가중치, ESDA, 회귀, 군집 설정창
│  │  ├─ store/            # selection, datasets, jobs
│  │  └─ i18n/             # ko, en
│  └─ src-tauri/           # Rust: 엔진 spawn, 메뉴, 업데이터
├─ engine/
│  ├─ geostat_engine/
│  │  ├─ api/              # FastAPI 라우터
│  │  ├─ io/               # 벡터/래스터 로딩, 인코딩·CRS 처리
│  │  ├─ weights/          # 생성/저장/요약
│  │  ├─ esda/  regression/  cluster/  raster/
│  │  ├─ jobs/             # 작업 큐, 진행률, 취소
│  │  └─ report/           # 결과 리포트(텍스트/HTML)
│  └─ tests/               # 참조 데이터 기반 수치 검증
├─ packaging/              # PyInstaller spec, ad-hoc 서명·릴리스 스크립트
├─ docs/                   # 본 계획서, 사용자 매뉴얼
└─ .github/workflows/      # CI 빌드·릴리스
```

---

## 3. 기능 명세

### 3.1 데이터 입출력
- 벡터: Shapefile, GeoPackage(다중 레이어 선택), GeoJSON, FlatGeobuf, KML, CSV/XLSX(X·Y 컬럼 지정)
- **인코딩**: `.cpg` 우선 → 없으면 UTF-8 시도 → 실패 시 cp949/euc-kr 자동 판별, 사용자 수동 지정
- **CRS**: `.prj` 해석, 없으면 사용자 지정. 한국 프리셋(5186 중부원점, 5179 UTM-K, 5174 구 Bessel, 32652, 4326)
  - 거리 기반 가중치·GWR 실행 시 **지리좌표계면 경고 + 투영 변환 제안**
- 속성 테이블: 정렬·필터, 계산 필드(표현식), 결과 변수 자동 추가(LISA 군집, 잔차 등)
- 내보내기: GeoPackage/Shapefile/GeoJSON/CSV, 지도·차트 PNG/SVG

### 3.2 지도
- 주제도: Quantile, Equal Interval, Natural Breaks(Fisher-Jenks), Std. Deviation, Percentile, **Box map**, Unique values
- 배경지도: OSM 등 타일(오프라인 시 배경 없이 동작)
- 선택 도구: 클릭/사각형/올가미, Shift 추가 선택
- 다중 지도 창(분할 뷰)

### 3.3 공간가중치
- Contiguity: Queen / Rook, 고차 인접(order k, 누적 포함)
- 거리: 임계거리(최소 연결 거리 자동 제안), KNN, 커널(Gaussian, Bisquare 등, 고정/적응 대역폭)
- 행 표준화 옵션, **섬(islands) 탐지·경고**
- 연결성 히스토그램, 지도상 이웃 표시
- `.gal` / `.gwt` / `.kwt` 읽기·쓰기(GeoDa 호환)

### 3.4 탐색적 공간자료분석(ESDA)
| 분석 | 구현(esda) | 출력 |
|---|---|---|
| Global Moran's I (단변량/이변량) | `Moran`, `Moran_BV` | Moran 산점도, 순열 분포, 유의확률 |
| Local Moran (LISA) | `Moran_Local`, `Moran_Local_BV` | 군집지도(HH/LL/HL/LH), 유의성 지도 |
| Getis-Ord Gi / Gi* | `G_Local` | 핫스팟/콜드스팟 지도 |
| Local Geary | `Geary_Local` | 군집지도 |
| Join Count (이진변수) | `Join_Counts` | 통계표 |
| 다중검정 보정 | FDR, Bonferroni | 유의수준 선택 UI |

- 순열 횟수(99/199/499/999/9999), 난수 시드 고정 → 결과 재현

### 3.5 공간회귀
- **OLS + 공간진단**: Moran's I(잔차), LM-Lag, LM-Error, Robust LM, LM-SARMA, 다중공선성·이분산 진단 (`spreg.OLS(spat_diag=True, moran=True)`)
- **공간시차/오차 모형**: ML_Lag, ML_Error, GM_Lag(2SLS), GM_Error(Het) — GeoDa 리포트 형식의 결과표
- **GWR / MGWR** (`mgwr`)
  - 커널(bisquare/gaussian/exponential), 고정/적응 대역폭, AICc/CV 기준 대역폭 탐색
  - 지역 계수·t값·지역 R² 지도, **다중검정 보정된 t값으로 비유의 지역 마스킹**
  - MGWR 변수별 대역폭 표, OLS·GWR·MGWR 비교표(AICc, R²)
  - 잔차에 대한 Moran's I 자동 계산
- 모든 모형: 잔차·예측값을 속성 테이블 변수로 저장

### 3.6 공간군집화(지역화)
- SKATER, Max-p, AZP, Region K-Means, Ward(공간 제약) — `spopt`
- 결과: 군집지도, 군집별 변수 요약, 군집 내/간 분산 비
- REDCAP, SCHC는 spopt 미지원 → **자체 구현 또는 2차 버전으로 연기** (pygeoda는 GPL이라 번들 불가)

### 3.7 래스터·대용량
- GeoTIFF/COG 불러오기, 엔진 내부 타일 서버(rio-tiler)로 지도에 표시
- **존 통계**: 폴리곤별 평균/합/분산/분위수 등을 속성으로 추가 (exactextract)
- 래스터 → 격자(fishnet) 집계 후 ESDA 적용 워크플로
- 성능 목표 (M 시리즈 맥북 기준)

| 작업 | 목표 |
|---|---|
| 폴리곤 10만 개 로딩·지도 표시 | < 5초 |
| 폴리곤 50만 개 표시·브러싱 | 30fps 이상 |
| Queen 가중치 10만 개 | < 10초 |
| LISA 999회 순열, 10만 개 | < 30초 (numba 사용) |
| GWR 1만 개 | < 1분 / MGWR는 진행률·취소 필수, 권장 규모 안내 |

---

## 4. 개발 단계와 일정

1인 개발 + AI 코딩 보조 전제의 추정치. 각 단계 끝에 동작하는 빌드를 만든다.

| 단계 | 기간 | 산출물 | 완료 기준 |
|---|---|---|---|
| **P0. 기술 검증 스파이크** | 1~1.5주 | Tauri↔Python 엔진 연결, 엔진 번들 빌드, 20만 폴리곤 GeoArrow 렌더링 | 맥에서 개발 모드로 shp를 띄움 ✅ |
| **P1. 데이터·지도 기반** | 2~3주 | 파일 열기(인코딩·CRS), 속성 테이블, 주제도 7종, 프로젝트 저장 | 한글 DBF shp가 깨지지 않고 열림 |
| **P2. 가중치 + ESDA + 연동 시각화** | 3주 | 가중치 관리자, Moran/LISA/Gi*/Local Geary, 히스토그램·산점도·박스·Moran 산점도 연동 | **v0.1 공개 알파** — 참조 데이터 결과가 GeoDa와 일치 |
| **P3. 공간회귀 + GWR/MGWR** | 3주 | OLS 진단, Lag/Error 모형, GWR/MGWR, 결과 리포트 | spreg·mgwr 참조 결과와 수치 일치 |
| **P4. 공간군집화** | 2주 | SKATER, Max-p, AZP, Region K-Means, Ward | 군집 결과·요약 리포트 |
| **P5. 래스터·대용량 최적화** | 2주 | COG 표시, 존 통계, 성능 목표 달성 | 3.7 성능표 충족 |
| **P6. 배포 완성** | 1.5주 | 태그 푸시 시 GitHub Actions로 .dmg 빌드·릴리스, 자동 업데이트, 한/영 UI, 매뉴얼, 샘플 데이터 | **v1.0 릴리스** |

총 약 15~17주. **P0를 가장 먼저** 한 이유: Tauri↔Python 엔진 연결과 번들링이 이 스택의 최대 리스크이며, 기능 개발 후에 발견하면 되돌리기 비싸기 때문임.

---

## 5. 패키징·배포 (macOS)

### 5.1 Python 엔진 번들
- **PyInstaller onedir** 방식(onefile은 실행 시 임시폴더 압축해제 → 서명·속도 문제)
  - 대안: python-build-standalone + uv로 재배치 가능한 런타임 구성 — P0에서 두 방식 비교
- onedir 폴더를 Tauri `bundle.resources`로 포함, Rust에서 직접 spawn (Tauri `externalBin`은 단일 실행파일 전제)
- GDAL/PROJ 데이터 경로(`GDAL_DATA`, `PROJ_DATA`)를 번들 내부로 지정
- 예상 용량: 앱 300~500MB (GDAL, numpy/scipy, numba/llvmlite 포함)

### 5.2 서명 정책 (Apple Developer 미가입)
- 배포 범위는 GitHub 공개 레포·Releases까지로 함. 앱스토어 등재와 Apple 공증은 하지 않음 (Developer Program 불필요)
- 대신 **ad-hoc 서명**(`codesign -s -`)을 적용함. Apple Silicon은 서명이 전혀 없는 바이너리를 실행하지 않고,
  번들 서명이 없으면 인터넷에서 받은 앱이 "손상됨"으로 표시되기 때문임
- 사용자는 첫 실행 때 Gatekeeper 확인을 한 번 거쳐야 함 → README에 설치 안내를 둠
  - 시스템 설정 → 개인정보 보호 및 보안 → "그래도 열기", 또는 `xattr -dr com.apple.quarantine /Applications/GeoStat.app`
- 나중에 공증이 필요해지면 `packaging/macos/sign-engine.sh`에 Developer ID를 넣고 공증 단계만 추가하면 되도록 구조를 유지함

### 5.3 아키텍처·업데이트
- Apple Silicon(arm64) 우선. Intel iMac 지원이 필요하면 x86_64 별도 빌드(유니버설 바이너리는 Python 번들 때문에 비권장)
- Tauri updater 플러그인 + GitHub Releases, 업데이트 매니페스트 서명 (Tauri 자체 서명키 사용, Apple 인증서와 무관함)
- GitHub Actions macOS 러너에서 빌드·ad-hoc 서명·릴리스 자동화 (v 태그 푸시 시)

---

## 6. 품질 보증

- **수치 검증(가장 중요)**: libpysal 예제 데이터(Columbus, Baltimore, Guerry, NCOVR 등)로
  GeoDa 및 R `spdep`/`spatialreg`/`GWmodel` 결과와 비교, 허용오차 명시한 회귀 테스트
- 엔진: pytest (API 단위 + 통계 수치), 프론트: Vitest + Playwright(주요 흐름 E2E)
- 한글 인코딩 테스트셋: cp949 shp, `.cpg` 유무, 한글 컬럼명·경로
- 성능 벤치마크를 CI에서 추적 (3.7 목표 대비 회귀 감지)

---

## 7. 리스크와 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| 미공증 앱에 대한 Gatekeeper 경고 | 첫 실행 불편 | ad-hoc 서명으로 "손상됨" 오류는 피하고, README에 "그래도 열기" 절차 안내 |
| MGWR 계산 시간(대규모 n) | 사용성 저하 | 진행률·취소, 규모 경고, 표본 추출 옵션, 추후 병렬화 |
| 대용량 WebGL 메모리 | 크래시 | GeoArrow 바이너리, 지오메트리 단순화(줌별), 50만 초과 시 경고 |
| GPL 의존성 유입 | 라이선스 충돌 | 의존성 라이선스 CI 점검(pip-licenses), pygeoda 미사용 |
| PySAL 패키지 API 변경 | 유지보수 부담 | 버전 고정(lock), 엔진 내부 어댑터 계층으로 격리 |
| 번들 용량 과다 | 다운로드 부담 | 불필요 모듈 제외, 래스터 기능 의존성 최소화 |

---

## 8. 진행 현황

### P0. 기술 검증 — 완료 (2026-09-24)

- [x] 저장소 초기화: `apps/desktop`(Tauri 2 + React + TS), `engine`(uv 프로젝트)
- [x] 엔진: FastAPI `/health`, `/datasets/open`(pyogrio) → GeoArrow 응답
- [x] Tauri: 엔진 spawn(랜덤 포트·토큰), 종료 시 정리
- [x] 프론트: deck.gl GeoArrow 레이어로 20만 폴리곤 렌더링 + 사각형 선택
- [x] PyInstaller onedir 빌드 + 스모크 테스트 (Linux)
- [x] **맥에서** 개발 모드 실행 확인 — 서명·공증은 하지 않기로 함 (5.2 참고)
- [x] 결과를 `docs/spike-report.md`에 기록함

### P1. 데이터·지도 기반 — 1차 구현 (2026-09-24)

- [x] 파일 열기: 여러 레이어 GeoPackage는 레이어 선택, CSV·엑셀은 X·Y 열·좌표계 지정 (cp949 CSV, 좌표계 추정)
- [x] 좌표계 없는 자료 → 좌표계 지정 대화상자 (한국 좌표계 프리셋 11종)
- [x] 주제도 7종: 분위수·등간격·자연 분류·표준편차·백분위·박스·고유값 + 범례 (범례 클릭 → 해당 계급 선택)
- [x] 배경지도: OpenFreeMap(밝은 지도·기본 지도), 기본값은 "없음"
- [x] 속성 테이블: 가상 스크롤(20만 행), 열 정렬, 선택 연동, "선택 항목만" 보기
- [x] 계산 필드: pandas eval 식, 프로젝트에 식으로 저장해 재계산
- [x] 선택 도구: 클릭·사각형·올가미(중심점 기준), 반전·해제
- [x] 여러 레이어: 표시·순서·전체 보기·닫기
- [x] 내보내기: GeoPackage·Shapefile(UTF-8/CP949)·GeoJSON·FlatGeobuf·CSV, 좌표계 변환 저장
- [x] 프로젝트 저장·열기 (`.gstproj`, 상대 경로 저장으로 폴더째 이동 가능)
- [ ] 다중 지도 창(분할 뷰) — P2의 연동 차트와 함께 진행
- [ ] 지도 이미지(PNG) 내보내기
- [ ] 속성 조건 검색(필터)으로 선택
- [ ] 엔진이 실행 중 종료됐을 때 알림·재시작
- [ ] 맥에서 배경지도·대화상자 동작 확인 (클라우드 환경은 타일 서버 접속이 막혀 확인 못 함)

### P2. 가중치 + ESDA + 연동 시각화 — 1차 구현 (2026-09-24)

- [x] 공간가중치: 퀸·룩(차수, 하위 차수 포함), KNN, 거리(최소 거리 자동 제안, 역거리), 커널(고정·적응)
  - 경위도 자료는 UTM으로 임시 변환해 m 단위로 계산함
  - 요약: 이웃 수 분포(연결성 히스토그램), 섬 탐지·선택, 선택 피처의 이웃 선택
  - GeoDa `.gal`·`.gwt` 저장·불러오기 (ID 1..n)
- [x] 전역: Moran's I(단변량·이변량), 순열 검정 기준 분포, Join Count — Columbus 자료로 GeoDa 값(I=0.500189)과 일치 확인
- [x] 국지: LISA(단변량·이변량), Gi*, Local Geary — 유의수준, FDR·Bonferroni 보정, 결과 열(접두어_I·_CL·_P) 저장
- [x] 군집 지도(GeoDa 색 관례)·유의성 지도, 주제도 위 선택 피처 외곽선 강조
- [x] 연동 차트: 히스토그램·산점도(회귀선, 선택 회귀선)·박스플롯·Moran 산점도, 브러시 선택과 마우스오버
- [x] 프로젝트에 가중치 명세·분석 설정 저장 → 다시 열면 같은 시드로 재실행해 결과 재현
- [x] 엔진 시작 시 numba JIT 예열, 2만 개 이상은 순열 검정 병렬 처리 (번들에서도 동작 확인)
- [ ] 다중 지도 창(분할 뷰)
- [ ] 오래 걸리는 계산의 진행률·취소 (P3의 MGWR과 함께 작업 큐로 구현)
- [ ] 조건부 지도·평행좌표 등 추가 차트

### P3. 공간회귀 + GWR/MGWR — 1차 구현 (2026-09-24)

- [x] 작업 큐: 회귀 계산을 별도 프로세스(multiprocessing spawn)에서 실행, 진행률 표시·취소 (번들에서도 동작 확인)
- [x] OLS: 계수표, R²·AIC 등, 다중공선성·정규성(JB)·이분산성(BP·KB·White), 공간진단(잔차 Moran's I, LM·Robust LM·SARMA)과 모형 선택 안내
  - Columbus(HOVAL ~ INC + CRIME) 결과가 GeoDa 값과 일치 (R² 0.3495, 잔차 Moran's I 0.1713)
- [x] 공간시차·공간오차 모형 (spreg ML, n>2000이면 희소 LU 방식), 우도비 검정
- [x] GWR·MGWR (mgwr): 커널·고정/적응 대역폭·선택 기준, 지역 계수·t값·유의 여부(다중검정 보정)·지역 R² 열 저장
  - 작은 자료(n ≤ 40+2k)에서는 구간 탐색으로 대역폭을 찾음 (mgwr 기본 탐색 범위 문제 회피)
- [x] 계수 지도: 유의하지 않은 지역을 회색으로 가리고, 계급 경계는 유의한 피처로만 구함
- [x] 결과 보고서 카드(계수·진단·지역 계수 요약), 텍스트 보고서 저장, 잔차 지도·잔차 Moran's I
- [x] 프로젝트: 보고서와 결과 열을 `.gstcache` 폴더에 캐시해 다시 열 때 재계산하지 않음 (캐시가 없으면 재계산)

#### P3 보완 (2026-09-24) — 계획 3.5 항목 중 빠졌던 부분

- [x] GM 추정: 공간시차 GM_Lag(2SLS, 도구변수 WX, Anselin-Kelejian 검정), 공간오차 GM_Error_Het(이분산 강건 GMM). spreg 결과와 계수 일치
- [x] OLS White 이분산 강건 표준오차 (선택)
- [x] 공간시차 모형(ML·GM)의 직접·간접·총 효과 표 (n ≤ 2000은 역행렬 정확 계산, 그 이상은 멱급수 근사)
- [x] 잔차 Moran's I 자동 계산: 가중치를 고르면 모든 모형(GWR·MGWR 포함)에서 순열 999회 검정
- [x] 모형 비교표 (결과 패널): R², 로그우도, AICc, 잔차 Moran's I. 같은 종속변수·관측치 묶음에서 AICc 최소 모형 표시, 탭 구분 복사
  - AICc는 σ²를 모수로 넣어 mgwr와 같은 식으로 계산함 (OLS AICc가 mgwr 전역 회귀 AICc와 일치)
  - MGWR은 표준화 척도로 추정하므로 로그우도·AICc·잔차 제곱합을 원래 척도로 환산함 (AICc + 2n·ln σ_y)
- [x] 0 기준 발산 지도(zero_centered): 음수=파랑·양수=빨강, 부호별 분위수 구분. GWR 계수 지도 기본값으로 씀
- [ ] HAC 강건 표준오차 (커널 가중치 필요, 후순위)

### P4. 공간군집화 — 1차 구현 (2026-09-24)

- [x] 공간 제약 군집 (spopt 0.7): SKATER, Max-p, AZP, Region K-Means, Ward(공간 제약). 비교용 비공간 군집: K-평균, 계층적 군집(Ward)
  - 회귀와 같은 작업 큐에서 실행 (진행 표시·취소), 난수 시드 고정으로 재현 가능
  - 변수 표준화(z) 선택, SKATER 최소 피처 수, Max-p 임계값 변수·최소 합계(없으면 피처 수)
  - 이웃 그래프가 여러 조각이면 AZP·Max-p·Region K-Means는 실행 전에 거부하고, SKATER·Ward는 경고 후 실행
- [x] 결과: 군집 번호 열(`<접두어>_GRP`, 큰 군집부터 1번), 고유값 군집 지도
- [x] 군집 보고서 카드: 전체·군집 내·군집 간 제곱합과 비, 군집별 크기·군집 내 SS·변수 평균(표준화 평균으로 색칠한 프로필), 공간 조각 수
  - 행을 누르면 지도에서 그 군집을 선택함. 비공간 군집은 가중치를 고르면 몇 조각으로 흩어졌는지 보여줌
- [x] 텍스트 보고서 저장, 프로젝트 저장 시 결과 캐시(`.gstcache`) → 다시 열 때 재계산하지 않음
- 성능 (1,600개 격자, 변수 2개, 8군집): Ward 0.6초, SKATER 약 13초, Region K-Means 약 50초, AZP 약 3분, Max-p 10분 이상. 400개 격자에서는 Max-p 약 51초, AZP 약 8초
  - 관측치가 많으면 대화상자에서 경고함 (Max-p 500, AZP·Region K-Means 1,000, SKATER 5,000개 초과)
- [ ] REDCAP, SCHC (spopt 미지원, 자체 구현 필요) — 후순위
- [ ] 대용량용 Max-p 가속 (반복 횟수 조절 옵션 등)

### P5. 래스터·대용량 — 1차 구현 (2026-09-24)

- [x] 래스터 열기 (GeoTIFF·COG·IMG·VRT·ASC·JP2, rasterio): 크기·밴드·좌표계·값 없음·밴드 통계(축소본 기준 2/98% 백분위)
- [x] 지도 표시: 엔진이 웹 메르카토르 256px 타일을 PNG로 만들고 deck.gl TileLayer로 그림
  - rio-tiler 대신 rasterio WarpedVRT로 직접 구현함 (rio-tiler는 pystac 등 의존성이 많아 번들이 커짐). PNG도 zlib로 직접 인코딩
  - 단일 밴드 + 색상표 8종, RGB 합성, 값 범위(2–98%·최소–최대·직접 입력), 투명도, 최근접/쌍선형 보간, 범례
  - 축소 표시 때 알맞은 오버뷰 단계를 골라 읽음. 오버뷰가 없는 큰 래스터(긴 변 4,096px 초과)는 '오버뷰 만들기'로 원본 옆에 .ovr을 만듦 (원본 파일은 바꾸지 않음)
  - 12,000×12,000 float32 래스터: 오버뷰 없이 z8 타일 약 4초 → 오버뷰 뒤 30ms 안팎
- [x] 존 통계 (exactextract, 면적 가중): 평균·합계·최솟값·최댓값·표준편차·중앙값·사분위·셀 수·최빈값·값 종류 수. 작업 큐에서 5,000개씩 나눠 진행률 표시
  - 폴리곤 좌표계가 달라도 래스터 좌표계로 바꿔 계산. 래스터 밖·값 없는 폴리곤은 빈 값
- [x] 격자 만들기: 정사각·육각, 래스터 또는 레이어 범위, 폴리곤과 겹치는 셀만 남기기, GeoPackage로 저장 후 열기, 만든 뒤 존 통계 바로 계산 → ESDA 흐름
- [x] 프로젝트: 래스터 경로·표시 설정 저장, 존 통계 결과 캐시(없으면 래스터 경로로 재계산)
- [x] 대용량: 50만 피처 초과 시 경고, 성능 측정 스크립트(`scripts/benchmark.py`)
- [x] CI: main 푸시 때 macOS에서 엔진 번들을 빌드하고 스모크 테스트를 돌림 (pyogrio·rasterio의 GDAL 동시 번들 확인)
  - 첫 실행에서 실제로 충돌을 잡음: pyproj가 rasterio의 libproj(기호 이름을 바꿔 빌드한 것)를 불러와 엔진이 시작되지 않았음. PyInstaller가 휠마다 들고 오는 같은 이름의 dylib을 하나로 합치기 때문임
  - 해결: macOS 번들 빌드 때 전용 가상환경(복사 방식)에서 `<패키지>/.dylibs/` 라이브러리 이름을 패키지별로 바꾸고 참조 경로를 고친 뒤 ad-hoc 재서명함 (`packaging/macos/dedupe_dylibs.py`). 이후 macOS 스모크 테스트 통과

성능 측정 (클라우드 2코어 x86 기준, 보로노이 폴리곤 10만 개, `scripts/benchmark.py`)

| 작업 | 시간 | 목표 (M 시리즈) |
|---|---:|---|
| 열기 + 지오메트리 전송 | 1.6초 | < 5초 ✅ |
| Queen 가중치 | 6.3초 | < 10초 ✅ |
| LISA 999회 순열 | 29초 | < 30초 ✅ (코어가 많으면 더 빠름) |
| GWR 1만 개 (대역폭 탐색 포함) | 147초 | < 1분 — 2코어 기준 미달, 8코어 이상에서 재측정 필요 |

- 지도 렌더링 fps는 GPU가 필요해 클라우드에서 측정하지 못함 → 맥에서 확인 필요
- 엔진 번들 용량: 695MB → 817MB (rasterio가 GDAL을 따로 들고 옴). pyogrio와 GDAL을 하나로 합치는 방안은 P6에서 검토
- [ ] 줌별 지오메트리 단순화 (50만 개 이상에서 필요하면)
- [ ] 점 자료를 격자로 세는 집계 (공간 결합)

### 다음: P6. 배포 완성

---

## 부록: 주요 의존성

- 프론트: React, TypeScript, Vite, MapLibre GL, deck.gl, @geoarrow/deck.gl-geoarrow (구 @geoarrow/deck.gl-layers), apache-arrow, Zustand, i18next
- 셸: Tauri 2 (+ updater, dialog, fs 플러그인)
- 엔진: FastAPI, uvicorn, geopandas, shapely 2, pyogrio, pyproj, pyarrow, geoarrow-pyarrow, libpysal, esda, spreg, mgwr, spopt, mapclassify, numba, rasterio, rio-tiler, exactextract
