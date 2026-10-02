---
id: D
part: appendix
title: 용어 대역표
app: none
version: 1
updated: 2026-10-02
status: draft
---

[목차](../README.md) · 이전: [부록 C 기호·수식표](C-symbols.md) · 다음: [부록 E 도구별 차이와 결과 재현](E-tools-reproducibility.md)

# 부록 D 용어 대역표

> 0~42강의 "핵심 용어" 표를 모두 모아 가나다순으로 정리함. 권장어와 이형, 같은 방법을 도구마다 어떻게 부르는지도 함께 적음

공간통계의 한국어 용어는 문헌과 도구마다 다름. 같은 spatial lag을 공간시차, 공간지연, 공간래그로 쓰고, hot spot을 핫스팟, 핫스폿, 열점으로 씀. 이 책은 다음 원칙으로 한 가지를 골라 썼음.

- GeoStat 화면의 표기와 책의 표기를 같게 함. 독자가 책에서 읽은 말을 메뉴에서 그대로 찾을 수 있어야 하기 때문임
- 처음 나올 때 영문을 함께 적음. 영문 문헌과 다른 도구의 도움말을 찾아볼 때 쓰는 열쇠임
- 같은 개념은 책 전체에서 한 이름으로 씀

이 표는 `book/fig-src/D.py`가 각 강의 "핵심 용어" 표에서 자동으로 만들고, 같은 내용을 `book/glossary.json`에 기계가 읽는 꼴로 저장함. `book/tools/check_terms.py`는 본문에서 이형이 쓰인 곳을 찾아 알려 줌.

## 1. 권장어와 이형

| 권장어 | 피하는 이형 | 고른 까닭 |
|---|---|---|
| 공간 시차(Wy), 공간시차 모형 | 공간지연, 공간래그 | 시계열의 시차(lag)와 같은 생각임. 앱처럼 이웃 값의 가중 평균(변수)은 "공간 시차", 모형 이름은 "공간시차 모형"으로 띄어 씀 |
| 공간가중치 | 공간가중행렬 | 행렬이 아닌 이웃 목록으로도 저장하므로 "가중치"가 넓음. 앱 메뉴의 "공간가중치 만들기" |
| 지리가중회귀 | 지리적 가중 회귀 | 짧고 앱 표기와 같음 |
| 가변적 공간 단위 문제 | 가변 면적 단위 문제 | 면적만이 아니라 구획(경계)의 문제도 포함함 |
| 베리오그램 | 배리오그램, 반변동도 | 외래어 표기를 따르고, 반변동도는 잘 쓰이지 않음. 엄밀히는 세미베리오그램(γ)이지만 관례대로 베리오그램이라 부름(21강) |
| 크리깅 | 크리징 | 인명 Krige에서 옴 |
| 핫스팟, 콜드스팟 | 핫스폿, 열점 | 앱 화면의 표기를 따름 |
| 유효 표본 크기 | 실효 표본 수, 유효 표본 수 | 9강에서 정의한 말. MCMC의 ESS(36강)도 같은 말로 씀 |
| 누락 변수 편향 | 빠진 변수 치우침, 누락 변수 편의 | 8강에서 정의한 말 |
| 편향 | 편의 | bias. 본문에서는 풀어 쓴 "치우침"도 같은 뜻으로 씀. "편의 표본"(convenience sample, 38강)의 편의는 다른 말임 |
| 다중검정 | 다중 검정 | 붙여 씀 |
| 유의수준, 가중 최소제곱, 모의 실험 | 유의 수준, 가중최소제곱, 모의실험 | 띄어쓰기를 한 가지로 맞춤. 23강의 조건부 시뮬레이션은 지구통계의 용어라 "시뮬레이션"으로 씀 |
| 룩 인접 | 루크 인접 | 앱 화면의 "룩 인접 (Rook)" |
| 경계 효과 | 가장자리 효과 | 17·18강의 경계 보정과 같은 말 |
| 표시(mark), 표지(label) | | 둘은 다른 말임. 점마다 붙은 값이나 범주가 표시이고(표시 점 패턴, 표시 상관 함수), 무작위 표지 검정은 위치를 두고 범주 이름표만 섞는 귀무가설임(18강) |
| 최근린, 최근접 이웃 | | 점 패턴의 거리 함수에서는 최근린(최근린 거리, 16·18강), 공간가중치에서는 k-최근접 이웃(10강)으로 씀 |
| 국지, 지역 | | local. 국지 통계(LISA, Gi\*)는 "국지", GWR의 지역 계수·지역 R²는 GWR 문헌의 관례대로 "지역"으로 씀(29~30강) |
| 단계구분도 | 코로플레스 지도 | 지도학의 관례 |
| Moran's I | 모란 지수, 모란의 I | 본문은 대부분 원어로 씀. 0~5강 본문은 모란 지수, 11~13강의 용어 표는 모란의 I(국지 모란의 I, 이변량 모란의 I)로 적었음. 둘은 같은 말임 |

## 2. 도구마다 다른 이름

같은 방법이 도구마다 다른 이름의 메뉴나 함수로 들어 있음. 다른 도구의 결과와 비교할 때는 이름보다 기본값의 차이가 더 중요함(부록 E).

| 방법 | GeoStat 메뉴 | GeoDa 메뉴 | PySAL | R |
|---|---|---|---|---|
| 공간가중치 | 공간 분석 → 공간가중치 만들기… | Tools → Weights Manager | `libpysal.weights`의 `Queen`, `Rook`, `KNN`, `DistanceBand` | spdep `poly2nb`, `knearneigh`, `dnearneigh`, `nb2listw` |
| 전역 Moran's I | 공간 분석 → Moran's I · Moran 산점도… | Space → Univariate Moran's I | esda `Moran` | spdep `moran.test`, `moran.mc` |
| Geary's C(전역) | 코드(11강) | 없음 | esda `Geary` | spdep `geary.test`, `geary.mc` |
| Join Count(전역) | 공간 분석 → Join Count (이진 변수)… | 없음(국지만 있음) | esda `Join_Counts` | spdep `joincount.test`, `joincount.mc` |
| 국지 Join Count | 코드(13강) | Space → Univariate Local Join Count | esda `Join_Counts_Local` | spdep `local_joincount_uni` |
| LISA(국지 Moran) | 공간 분석 → 국지 통계 (LISA · Gi\* · Local Geary)… → Local Moran (LISA) | Space → Univariate Local Moran's I | esda `Moran_Local` | spdep `localmoran`, `localmoran_perm` |
| Gi\* | 같은 창 → Getis-Ord Gi\* | Space → Local G\* | esda `G_Local(star=True)` | spdep `localG`, `localG_perm` |
| Local Geary | 같은 창 → Local Geary | Space → Univariate Local Geary | esda `Geary_Local`(값이 spdep의 n/(n − 1)배) | spdep `localC`, `localC_perm` |
| EB 평활, EB Moran | 공간 분석 → 비율 지도 · EB 보정… | Map → Rates-Calculated Map → Empirical Bayes, Space → Moran's I with EB Rate | esda `smoothing.Empirical_Bayes`, `Moran_Rate` | spdep `EBest`, `EBImoran.mc` |
| 공간시차·공간오차 모형 | 공간 분석 → 회귀 분석 (OLS · 공간회귀 · GWR · MGWR)… | Regression | spreg `OLS`, `ML_Lag`, `ML_Error` | spatialreg `lagsarlm`, `errorsarlm` |
| GWR, MGWR | 같은 창 | 없음 | mgwr `GWR`, `MGWR`, `Sel_BW` | GWmodel `gwr.basic`, `bw.gwr`, spgwr `gwr` |
| 영역화, 군집 | 공간 분석 → 군집 분석 (SKATER · Max-p · AZP · K-평균)… | Clusters → skater, AZP, max-p, K Means | spopt `Skater`, `AZP`, `MaxPHeuristic`, scikit-learn `KMeans` | rgeoda `skater`, `azp_greedy`, `maxp_greedy`, stats `kmeans` |
| 시공간 탐색 | 시공간 → 시공간 분석 (Moran 추이·기간별 LISA·차분 LISA)… | Space → Differential Moran's I 등 | giddy `Spatial_Markov` | sfdep `emerging_hotspot_analysis` |
| K 함수, 포락선 | 코드(18강) | 없음 | pointpats `distance_statistics.k`, `k_test` | spatstat `Kest`, `envelope` |
| 베리오그램, 크리깅 | 코드(21~23강) | 없음 | PyKrige, scikit-gstat | gstat `variogram`, `fit.variogram`, `krige` |
| 공간 스캔 통계 | 코드(15강) | 없음 | 직접 구현 | SaTScan(별도 프로그램), smerc |

GeoDa의 메뉴 이름은 판에 따라 조금씩 다름. ArcGIS Pro에서는 공간 통계 도구 상자(Spatial Statistics)의 Spatial Autocorrelation (Global Moran's I), Cluster and Outlier Analysis (Anselin Local Moran's I), Hot Spot Analysis (Getis-Ord Gi\*), Geographically Weighted Regression (GWR)과, 시공간 패턴 마이닝 도구 상자(Space Time Pattern Mining)의 Emerging Hot Spot Analysis가 각각에 해당함.

## 3. 가나다순 대역표

"처음 나온 강"은 그 용어가 핵심 용어 표에 처음 실린 강임. 같은 용어를 여러 강의 표에 실었으면 나머지 강의 수를 "(외 N개 강)"으로 적음.

<!-- 용어표 자동 생성 시작 (fig-src/D.py) -->

### ㄱ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 가능도 | Likelihood | 36강 |  |
| 가림 효과 | Screening Effect | 22강 |  |
| 가변적 공간 단위 문제 | Modifiable Areal Unit Problem (MAUP) | 0강 (외 1개 강) | 가변 면적 단위 문제라고도 함; 이형: 가변 면적 단위 문제, 임의적 공간 단위 문제 |
| 가변적 시간 단위 문제 | Modifiable Temporal Unit Problem (MTUP) | 33강 | Cheng & Adepeju 2014 |
| 가산값 | False Easting / False Northing | 2강 |  |
| 가우스 과정 | Gaussian Process | 30강 |  |
| 가장 가능성 높은 군집 | Most Likely Cluster | 15강 |  |
| 가족별 오류율 | Family-wise Error Rate (FWER) | 7강 |  |
| 가중 최소제곱 | Weighted Least Squares (WLS) | 8강 (외 1개 강) | Cressie 1985; 이형: 가중최소제곱 |
| 가중 평균 | Weighted Mean | 6강 |  |
| 가짜 상관 | Spurious Correlation | 9강 |  |
| 간섭 | Interference (Spillover) | 41강 |  |
| 간접 표준화 | Indirect Standardization | 14강 | 기준 비율 × 구역 인구 구조 |
| 간접 효과 | Indirect Effect (Spillover) | 25강 |  |
| 강건 LM 검정 | Robust LM Test | 24강 | Anselin 외 1996 |
| 강건 표준오차 | Robust (Heteroskedasticity-consistent) Standard Error | 8강 | White 1980 |
| 강도 | Intensity | 16강 | 단위 면적당 기대 점 수 |
| 강도 함수 | Intensity Function λ(x) | 17강 |  |
| 개인주의적 오류 | Individualistic (Atomistic) Fallacy | 3강 |  |
| 객체 관점 / 장 관점 | Object View / Field View | 1강 |  |
| 거리 임계값 | Distance Band (Threshold) | 10강 |  |
| 거짓 발견율 | False Discovery Rate (FDR) | 7강 |  |
| 검정력 | Power | 7강 | 1 − β |
| 검정통계량 | Test Statistic | 7강 |  |
| 게리맨더링 | Gerrymandering | 3강 |  |
| 결정계수 | Coefficient of Determination (R²) | 8강 |  |
| 결측값 | Missing Value | 4강 |  |
| 경계 보정 | Edge Correction | 17강 | Diggle 1985 균일 보정 |
| 경계 효과 | Edge Effect | 4강 (외 1개 강) | 이형: 가장자리 효과 |
| 경험적 베이즈 / 완전 베이즈 | Empirical / Full Bayes | 36강 |  |
| 경험적 베이즈 평활 | Empirical Bayes (EB) Smoothing | 14강 | Clayton & Kaldor 1987 |
| 계급 | Class | 5강 | 같은 색으로 칠하는 값의 구간 |
| 계급 구분 | Classification | 42강 |  |
| 계수 / 절편 | Coefficient / Intercept | 8강 |  |
| 계수별 유효 모수 수 | Covariate-specific ENP (ENPⱼ) | 30강 | Yu 외 2020 |
| 계층 군집 | Hierarchical Clustering | 31강 |  |
| 계층 모형 | Hierarchical Model | 36강 | 다층 모형 |
| 계통 추출 | Systematic Sampling | 38강 |  |
| 고유 CAR | Proper CAR | 37강 |  |
| 고유벡터 공간 필터 | Eigenvector Spatial Filtering (ESF) | 27강 | Griffith 2003 |
| 고정 대역폭 | Fixed Bandwidth | 29강 | 거리 |
| 고정 순위 크리깅 | Fixed Rank Kriging (FRK) | 40강 |  |
| 고정효과 / 확률효과 | Fixed / Random Effects | 35강 |  |
| 고차 인접 | Higher-order Contiguity | 10강 | 이웃의 이웃 |
| 공간 Chow 검정 | Spatial Chow Test | 28강 | Anselin 1990 |
| 공간 EB 평활 | Spatial EB Smoothing | 14강 | 이웃 쪽으로 |
| 공간 결합 | Spatial Join | 4강 | 위치로 붙임 |
| 공간 고정효과 | Spatial Fixed Effects | 27강 |  |
| 공간 교락 | Spatial Confounding | 37강 | Hodges & Reich 2010 |
| 공간 군집 | Spatial Cluster | 12강 | HH, LL |
| 공간 균형 추출 | Spatially Balanced Sampling | 38강 |  |
| 공간 누설 | Spatial Leakage | 39강 | 공간 과적합 |
| 공간 더빈 모형 | Spatial Durbin Model (SDM) | 26강 | 전역적 파급 |
| 공간 더빈 오차 모형 | Spatial Durbin Error Model (SDEM) | 26강 |  |
| 공간 마르코프 | Spatial Markov | 34강 | Rey 2001 |
| 공간 변이 계수 모형 | Spatially Varying Coefficient Model (SVC) | 30강 | Gelfand 외 2003 |
| 공간 블록 교차검증 | Spatial Block Cross-validation | 39강 | Roberts 외 2017 |
| 공간 비율 | Spatial Rate | 14강 | 창 안의 합 ÷ 합 |
| 공간 비정상성 | Spatial Nonstationarity | 0강 (외 1개 강) | 관계(계수)가 장소마다 달라지는 것 |
| 공간 비중 | Mixing Parameter φ | 37강 |  |
| 공간 스캔 통계 | Spatial Scan Statistic | 15강 | Kulldorff 1997 |
| 공간 승수 | Spatial Multiplier | 25강 | (I − ρW)⁻¹ |
| 공간 시차 | Spatial Lag | 10강 | Wy, 이웃 값의 가중합; 이형: 공간지연, 공간래그 |
| 공간 의존성 | Spatial Dependence | 0강 (외 1개 강) |  |
| 공간 이분산 | Spatial Heteroskedasticity | 28강 |  |
| 공간 이상치 | Spatial Outlier | 12강 | HL, LH |
| 공간 이질성 | Spatial Heterogeneity | 0강 (외 1개 강) | Anselin 1988 |
| 공간 자기상관 | Spatial Autocorrelation | 0강 (외 2개 강) | 이형: 공간자기상관, 공간 자기 상관 |
| 공간 자기회귀 과정 | Simultaneous Autoregressive (SAR) Process | 9강 | x = (I − ρW)⁻¹ε, 25~26강 |
| 공간 자료 | Spatial Data | 0강 |  |
| 공간 제약 군집화 | Spatially Constrained Clustering | 32강 |  |
| 공간 척도 | Spatial Scale | 30강 |  |
| 공간 체제 | Spatial Regimes | 28강 | PySAL: OLS_Regimes |
| 공간 패널 모형 | Spatial Panel Model | 27강 (외 1개 강) | Elhorst 2003; Elhorst 2014 |
| 공간 평활 계수 | Spatial Smoothing Scalar | 13강 | L_XX |
| 공간 피복 표본 | Spatial Coverage Sample | 38강 | Walvoort 외 2010 |
| 공간 필터 | Spatial Filter | 26강 | (I − λW) |
| 공간 회귀 불연속 | Geographic Regression Discontinuity | 41강 | Keele & Titiunik 2015 |
| 공간 효과 | Spatial Effects | 0강 | 의존성과 이질성을 함께 이르는 말 (Anselin 1988) |
| 공간가중치 (행렬) | Spatial Weights (Matrix) | 10강 | W; 이형: 공간가중행렬, 공간 가중행렬 |
| 공간계량경제학 | Spatial Econometrics | 0강 |  |
| 공간시차 X 모형 | Spatial Lag of X (SLX) | 26강 | 국지적 파급 |
| 공간시차 모형 | Spatial Lag Model (SAR) | 24강 (외 1개 강) | GeoDa: Spatial Lag, PySAL: ML_Lag·GM_Lag |
| 공간오차 모형 | Spatial Error Model (SEM) | 24강 (외 1개 강) | GeoDa: Spatial Error, PySAL: ML_Error·GM_Error_Het |
| 공간통계학 | Spatial Statistics | 0강 |  |
| 공통인수 제약 | Common Factor Restriction | 26강 | θ = −ρβ |
| 과대산포 | Overdispersion | 27강 | 분산 > 평균 |
| 관찰창 | Observation Window | 16강 |  |
| 교란 변수 | Confounder | 8강 |  |
| 교차 K 함수 | Cross-K Function | 18강 |  |
| 교차검증 | Cross-Validation | 20강 (외 1개 강) | LOOCV; k겹, LOO |
| 교환 가능성 | Exchangeability | 7강 | 순열 검정의 가정 |
| 구조의 불안정 | Structural Instability | 28강 | 계수의 지역 차이 |
| 구형·지수·가우시안 모형 | Spherical, Exponential, Gaussian Models | 21강 |  |
| 구획 효과 | Zoning Effect | 3강 |  |
| 국소 최적 | Local Optimum | 31강 |  |
| 국지 G 통계량 | Getis-Ord Gi, Gi\* | 13강 | Gi\*는 자기 자신 포함 |
| 국지 기어리 | Local Geary's c | 13강 | Anselin 1995, 2019 |
| 국지 모란의 I | Local Moran's I | 12강 |  |
| 국지 조인 카운트 | Local Join Count | 13강 | Anselin & Li 2019 |
| 국지 피벗 방법 | Local Pivotal Method | 38강 | Grafström 외 2012 |
| 국지적 공간 연관 지표 | Local Indicators of Spatial Association (LISA) | 12강 | Anselin 1995 |
| 군집 강건 표준오차 | Cluster-robust Standard Error | 35강 |  |
| 군집 과정 | Cluster Process | 19강 | Neyman–Scott |
| 군집 내 제곱합 | Within-cluster Sum of Squares (WSS) | 31강 |  |
| 군집 분석 | Cluster Analysis | 31강 | 비지도 학습 |
| 군집 전이표 | Cluster Transition Table | 34강 | GeoStat 기간별 LISA |
| 군집 지도 | Cluster Map | 12강 | HH, LL, HL, LH |
| 군집 탐지 | Cluster Detection | 15강 |  |
| 군집 프로필 | Cluster Profile | 31강 |  |
| 귀무가설 | Null Hypothesis (H₀) | 7강 |  |
| 귀무분포 | Null Distribution | 7강 |  |
| 근사해법 | Heuristic | 32강 |  |
| 기대 건수 | Expected Count | 37강 | 간접 표준화 |
| 기어리의 C | Geary's C | 11강 | Geary 1954, 기댓값 1 |
| 기하평균 | Geometric Mean | 6강 | 로그의 평균을 되돌린 값 |
| 긴 형태 / 넓은 형태 | Long / Wide Format | 33강 |  |
| 깔때기 그림 | Funnel Plot | 6강 |  |

### ㄴ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 내생성 | Endogeneity | 25강 |  |
| 내재 정상성 | Intrinsic Stationarity | 20강 |  |
| 내재적 CAR | Intrinsic CAR (ICAR) | 37강 | 합 0 제약 |
| 내포량 | Intensive Variable | 1강 | 밀도, 비율, 평균 |
| 너깃 | Nugget | 21강 | c₀ |
| 노출 인구 | Population at Risk | 3강 | 알맞은 분모 |
| 누락 변수 편향 | Omitted Variable Bias | 8강 (외 1개 강) | 이형: 빠진 변수 치우침, 누락변수 편의, 누락 변수 편의 |

### ㄷ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 다변량 국지 기어리 | Multivariate Local Geary | 13강 |  |
| 다수준 모형 | Multilevel Model | 3강 | 개인과 지역 효과를 함께 추정 |
| 다중 우주 분석 | Multiverse Analysis | 41강 | Steegen 외 2016 |
| 다중검정 | Multiple Testing | 7강 | 이형: 다중 검정 |
| 다중검정 보정 | Multiple Testing Correction | 12강 | FDR, Bonferroni |
| 다중공선성 | Multicollinearity | 8강 |  |
| 다중척도 지리가중회귀 | Multiscale GWR (MGWR) | 30강 | Fotheringham 외 2017 |
| 단계구분도 | Choropleth Map | 1강 (외 1개 강) | 구역을 값의 계급으로 칠한 지도; 이형: 코로플레스 지도, 코로플레스맵 |
| 단순 무작위 추출 | Simple Random Sampling (SRS) | 38강 |  |
| 단순·정규·보편 크리깅 | Simple, Ordinary, Universal Kriging | 22강 |  |
| 단순화 | Simplification | 4강 | 꼭짓점 줄이기 |
| 대권거리 / 측지선 거리 | Great-circle Distance / Geodesic Distance | 2강 |  |
| 대역폭 | Bandwidth | 17강 (외 1개 강) |  |
| 대역폭 불확실성 | Bandwidth Uncertainty | 30강 | Li 외 2020 |
| 대체 | Imputation | 4강 | 결측을 채우는 것 |
| 덴드로그램 | Dendrogram | 31강 |  |
| 도구변수 | Instrumental Variable | 25강 | WX, W²X |
| 독립 | Independence | 9강 |  |
| 동 안 편차 | Within Transformation | 35강 |  |
| 동적 공간 패널 | Dynamic Spatial Panel | 35강 |  |
| 등간격 분류 | Equal Interval Classification | 5강 | 값의 범위를 같은 폭으로 |
| 등방성 / 이방성 | Isotropy / Anisotropy | 20강 |  |
| 등분산성 / 이분산성 | Homoskedasticity / Heteroskedasticity | 8강 |  |
| 떠오르는 핫스팟 분석 | Emerging Hot Spot Analysis | 34강 | ESRI |

### ㄹ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 라그랑주 승수 | Lagrange Multiplier | 22강 | 가중치 합 조건 |
| 라그랑주 승수 검정 | Lagrange Multiplier (LM) Test | 24강 | 스코어 검정 |
| 랜덤 포레스트 | Random Forest | 39강 | Breiman 2001 |
| 로그 가우시안 콕스 과정 | Log-Gaussian Cox Process (LGCP) | 19강 |  |
| 로그우도비 | Log-Likelihood Ratio (LLR) | 15강 |  |
| 로버스트 | Robust | 6강 | 극단값에 덜 흔들림 |
| 룩 / 퀸 인접 | Rook / Queen Contiguity | 10강 |  |
| 르루 모형 | Leroux Model | 37강 |  |
| 리의 L | Lee's L | 13강 | Lee 2001, 대칭 |

### ㅁ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 마르코프 연쇄 | Markov Chain | 34강 |  |
| 마르코프 연쇄 몬테카를로 | Markov Chain Monte Carlo (MCMC) | 36강 |  |
| 마테른 모형 | Matérn Model | 21강 | 매끄러움 ν |
| 맥락 효과 | Contextual Effect | 3강 | 지역 자체의 조건이 개인의 결과에 주는 효과 |
| 맨-켄달 추세 검정 | Mann-Kendall Trend Test | 34강 | Mann 1945, Kendall 1975 |
| 메트로폴리스 알고리즘 | Metropolis Algorithm | 36강 | Metropolis 외 1953 |
| 면 자료 | Lattice Data, Areal Data | 0강 | 격자 자료, 구역 자료라고도 함 |
| 면적 가중 보간 | Areal Weighting Interpolation | 1강 |  |
| 면적 내삽 | Areal Interpolation | 33강 | Goodchild & Lam 1980 |
| 명세 곡선 | Specification Curve | 41강 | Simonsohn 외 2020 |
| 모란 고유벡터 지도 | Moran's Eigenvector Maps (MEM) | 27강 | Dray 외 2006 |
| 모란 산점도 | Moran Scatterplot | 11강 | 기울기 = I |
| 모란 지수 | Moran's I | 0강 |  |
| 모란의 I | Moran's I | 11강 | Moran 1950 |
| 모의 포락선 | Simulation Envelope | 18강 |  |
| 모자 행렬 | Hat Matrix | 29강 | ŷ = Sy |
| 모집단 / 표본 | Population / Sample | 6강 |  |
| 모집단 틀 | Sampling Frame | 38강 |  |
| 모형 기반 추론 | Model-based Inference | 38강 |  |
| 몬테카를로 검정 | Monte Carlo Test | 15강 |  |
| 무작위 결측 | MAR (Missing At Random) | 4강 | 관측된 다른 변수로 결측이 설명됨 |
| 무작위 표지 | Random Labelling | 17강 |  |
| 무조건부 시뮬레이션 | Unconditional Simulation | 23강 |  |
| 문턱값 | Sill | 21강 | c₀ + c |
| 민감도 분석 | Sensitivity Analysis | 3강 (외 3개 강) |  |

### ㅂ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 박스 지도 | Box Map | 5강 | 사분위수와 1.5 IQR 울타리 |
| 박판 스플라인 | Thin Plate Spline | 20강 |  |
| 반복 가능성 | Replicability | 41강 |  |
| 방격 밀도 | Quadrat Density | 17강 | 앱: 점 집계의 _DENS |
| 방격법 | Quadrat Method | 16강 |  |
| 방법 절 / 결과 절 | Methods / Results Section | 42강 |  |
| 방위 표시 | North Arrow | 42강 |  |
| 버먼–터너 근사 | Berman–Turner Approximation | 19강 | 셀 포아송 회귀 |
| (반)베리오그램 | (Semi)variogram | 21강 | γ(h); 이형: 배리오그램, 반변동도, 변동도 |
| 베리오그램 구름 | Variogram Cloud | 21강 |  |
| 벡터 / 래스터 | Vector / Raster | 1강 |  |
| 벤야미니–호흐베르크 | Benjamini–Hochberg (BH) | 7강 | FDR 통제 |
| 변동계수 | Coefficient of Variation (CV) | 6강 | 표준편차 ÷ 평균 |
| 보고 지침 | Reporting Guideline | 42강 | STROBE 등 |
| 보로노이 분할 | Voronoi Tessellation | 3강 | 티센 다각형과 같음 |
| 보조 자료 비례 내삽 | Dasymetric Interpolation | 33강 | Mennis 2003 |
| 보충 자료 | Supplementary Material | 42강 |  |
| 복잡도 벌점 사전분포 | Penalized Complexity (PC) Prior | 37강 | Simpson 외 2017 |
| 본페로니 보정 | Bonferroni Correction | 7강 | α / m |
| 부분 잔차 | Partial Residual | 30강 |  |
| 부분 합동 | Partial Pooling | 36강 |  |
| 부트스트랩 | Bootstrap | 6강 | 복원 추출로 표본분포를 흉내 냄 |
| 분리형 공분산 | Separable Covariance | 35강 |  |
| 분산 대 평균 비 | Variance-to-Mean Ratio (VMR) | 16강 |  |
| 분산 분해 | Variance Decomposition | 33강 |  |
| 분산 적합도 | Goodness of Variance Fit (GVF) | 5강 | 1 − 계급 안 제곱합 ÷ 전체 제곱합 |
| 분산 팽창 계수 | Variance Inflation Factor (VIF) | 8강 |  |
| 분석 계획서 | Analysis Plan | 41강 | 사전 등록 |
| 분위수 분류 | Quantile Classification | 5강 | 계급마다 개수가 같게 |
| 불균질 K 함수 | Inhomogeneous K Function | 18강 | Baddeley et al. 2000 |
| 불균질 포아송 과정 | Inhomogeneous Poisson Process | 16강 | 1차 성질 |
| 불균질 포아송 모형 | Inhomogeneous Poisson Model | 19강 | 로그선형 강도 |
| 브러싱 | Brushing | 5강 | 한 창에서 골라 모든 창에 표시 |
| 블록 부트스트랩 | Block Bootstrap | 39강 | Lahiri 2003 |
| 블록 크리깅 | Block Kriging | 22강 | 지원 변경 |
| 블록 평균 | Block Average | 40강 | 집계 |
| 비무작위 결측 | MNAR (Missing Not At Random) | 4강 | 빠진 값 자체가 결측을 결정 |
| 빈 공간 함수 | Empty Space Function F | 18강 |  |

### ㅅ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 사례–대조 | Case–Control | 17강 |  |
| 사분면 | Quadrant (HH, LL, LH, HL) | 11강 |  |
| 사분위 범위 | Interquartile Range (IQR) | 5강 (외 1개 강) | Q3 − Q1 |
| 사전 등록 | Preregistration | 42강 |  |
| 사전분포 / 사후분포 | Prior / Posterior Distribution | 36강 |  |
| 상관거리 | Range | 21강 | 실효 상관거리 |
| 상대 강도(상대 위험) | Relative Intensity (Relative Risk) | 17강 | Kelsall & Diggle 1995 |
| 상대위험 | Relative Risk (RR) | 15강 (외 1개 강) | 창 안 O/E ÷ 창 밖 O/E |
| 상호작용 항 | Interaction Term | 28강 |  |
| 생산자 정확도 / 사용자 정확도 | Producer's / User's Accuracy | 40강 | 재현율 / 정밀도 |
| 생태 회귀 | Ecological Regression | 37강 |  |
| 생태학적 상관 | Ecological Correlation | 3강 | 집계 단위에서 구한 상관 |
| 생태학적 오류 | Ecological Fallacy | 3강 | Robinson 1950 |
| 선거구 획정 | Redistricting | 32강 |  |
| 설계 기반 / 모형 기반 추론 | Design-based / Model-based Inference | 6강 |  |
| 설계 기반 추론 | Design-based Inference | 38강 |  |
| 설계 효과 | Design Effect | 38강 |  |
| 섬 | Island (Isolate) | 4강 (외 1개 강) | 이웃이 없는 구역 |
| 성가신 의존 | Nuisance Dependence | 24강 | 공간오차 |
| 속성 | Attribute | 1강 |  |
| 속성 결합 | Attribute Join | 4강 | 키로 붙임 |
| 수정 t검정 | Modified t-test | 9강 | Clifford 외 1989, Dutilleul 1993 |
| 수정 랜드 지수 | Adjusted Rand Index (ARI) | 31강 | Hubert & Arabie 1985 |
| 수정 아카이케 정보 기준 | Corrected AIC (AICc) | 29강 | Hurvich 외 1998 |
| 수축 | Shrinkage | 14강 | 평균 쪽으로 당김 |
| 순서 관계 문제 | Order Relation Problem | 23강 | 확률이 0~1을 벗어남 |
| 순수 너깃 | Pure Nugget | 21강 | 공간 구조 없음 |
| 순열 검정 | Permutation Test | 7강 | 공간통계에서는 무작위화 가정을 흉내 내는 데 씀 (11강) |
| 순차 / 발산 / 질적 색 | Sequential / Diverging / Qualitative | 5강 |  |
| 순차 가우시안 시뮬레이션 | Sequential Gaussian Simulation (SGS) | 23강 |  |
| 스타인의 역설 | Stein's Paradox | 36강 | 수축 추정 |
| 시간 변수 묶음 | Time Variable Group | 33강 | GeoStat |
| 시공간 가중치 | Space-time Weights | 33강 |  |
| 시공간 상호작용 | Space-time Interaction | 35강 | Knorr-Held 2000 |
| 시공간 순열 모형 | Space-time Permutation Model | 35강 | Kulldorff 외 2005 |
| 시공간 스캔 통계 | Space-time Scan Statistic | 35강 | Kulldorff 2001 |
| 시공간 크리깅 | Space-time Kriging | 35강 |  |
| 신뢰구간 | Confidence Interval (CI) | 6강 |  |
| 신뢰구간 포함 확률 | Coverage Probability | 9강 | 신뢰구간이 참값을 포함하는 비율 |
| 신용구간 | Credible Interval | 36강 | 이형: 신뢰 구간(베이즈) |
| 실루엣 계수 | Silhouette Coefficient | 31강 | Rousseeuw 1987 |
| 실질적 의존 | Substantive Dependence | 24강 | 파급, 공간시차 |
| 실질적 중요성 | Practical Significance | 42강 |  |
| 실험 베리오그램 | Empirical (Experimental) Variogram | 21강 |  |
| 실현값 | Realization | 23강 |  |
| 쌍상관함수 | Pair Correlation Function g(r) | 18강 | K의 미분을 2πr로 나눈 것 |

### ㅇ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 아웃오브백 오차 | Out-of-bag (OOB) Error | 39강 | 랜덤 포레스트 |
| 아카이케 정보 기준 | Akaike Information Criterion (AIC) / corrected AIC (AICc) | 8강 | 작을수록 좋음 |
| 야코비 항 | Jacobian Term | 25강 | ln\|I − ρW\| |
| 억제 과정 | Inhibition Process | 19강 |  |
| 역거리 가중 | Inverse Distance Weighting (IDW) | 10강 (외 1개 강) | 1/d, 1/d²; Shepard 1968 |
| 역적합 | Backfitting | 30강 | Buja 외 1989 |
| 연결 성분 | Connected Component | 10강 |  |
| 연동 시각화 | Linked Views | 5강 |  |
| 연령 표준화 | Age Standardization | 3강 |  |
| 연속 표면 자료 | Geostatistical Data | 0강 | 지구통계 자료라고도 함 |
| 영역화 | Regionalization | 32강 |  |
| 오차 행렬 | Error (Confusion) Matrix | 40강 |  |
| 오프셋 | Offset | 27강 | ln(인구) |
| 완전 공간 무작위 | Complete Spatial Randomness (CSR) | 16강 | 균질 포아송 과정 |
| 완전 무작위 결측 | MCAR (Missing Completely At Random) | 4강 | 결측이 어떤 값과도 무관 |
| 완충 LOO | Buffered Leave-one-out | 39강 |  |
| 완충 구역 | Buffer Zone | 4강 | 이웃 계산에만 쓰는 바깥 구역 |
| 왜도 | Skewness | 6강 |  |
| 외부 표류 크리깅 | Kriging with External Drift | 22강 |  |
| 외삽 | Extrapolation | 39강 |  |
| 외연량 | Extensive Variable | 1강 | 합치면 더해지는 양 |
| 외연량 / 내포량 | Extensive / Intensive Variable | 33강 |  |
| 우도 교차검증 | Likelihood Cross-Validation | 17강 |  |
| 원 카토그램 | Dorling Cartogram | 5강 | 구역을 원으로 |
| 원비율 | Raw Rate | 14강 | 사건 수 ÷ 분모 |
| 웹 메르카토르 | Web Mercator (EPSG:3857) | 2강 |  |
| 위상 | Topology | 4강 | 경계를 공유하는 관계 |
| 유사 p값 | Pseudo p-value | 7강 | (M + 1)/(R + 1) |
| 유의성 지도 | Significance Map | 12강 | 유사 p값의 크기 |
| 유의수준 | Significance Level (α) | 7강 |  |
| 유클리드 거리 | Euclidean Distance | 31강 |  |
| 유한 모집단 수정 | Finite Population Correction | 38강 |  |
| 유효 모수 수 | Effective Number of Parameters (ENP) | 29강 | tr(S) |
| 유효 표본 크기 | Effective Sample Size (n_eff) | 0강 (외 3개 강) | 이형: 실효 표본 수, 유효 표본 수, 유효표본크기 |
| 음이항 회귀 | Negative Binomial Regression (NB2) | 27강 | 분산 μ + αμ² |
| 의사반복 | Pseudoreplication | 9강 | Hurlbert 1984 |
| 이방성 | Anisotropy | 21강 | 기하 이방성 |
| 이변량 모란의 I | Bivariate Moran's I | 13강 | 자기 x × 이웃 y |
| 이분산 강건 GM | Heteroskedasticity-robust GMM | 26강 | Kelejian & Prucha 2010 |
| 이중차분 | Difference-in-Differences | 41강 |  |
| 이진 / 행 표준화 | Binary / Row-standardized | 10강 |  |
| 인과 도표 | Directed Acyclic Graph (DAG) | 41강 | Pearl 2009 |
| 인접 | Contiguity | 4강 (외 1개 강) | 퀸·룩 인접, 10강 |
| 일반 G | General G (Getis-Ord) | 11강 | 핫스팟·콜드스팟 구별 |
| 일반 둥지 모형 | General Nesting Spatial Model (GNS) | 26강 | Elhorst 2010 |

### ㅈ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 자동 구역화 절차 | Automatic Zoning Procedure (AZP) | 32강 | Openshaw 1977 |
| 자료 중복 | Data Redundancy (Declustering) | 20강 | 크리깅이 고려함 |
| 자연 분류 | Natural Breaks (Jenks, Fisher-Jenks) | 5강 | 계급 안 제곱합을 가장 작게 |
| 자연 실험 | Natural Experiment | 41강 |  |
| 작은 수 문제 | Small Number Problem | 14강 |  |
| 잔차 / 오차 | Residual / Error | 8강 |  |
| 잔차 Moran's I | Moran's I for Residuals | 24강 | Cliff & Ord 1981 |
| 재현 자료 | Replication Package | 42강 |  |
| 재현성 | Reproducibility | 41강 |  |
| 적용 가능 영역 | Area of Applicability (AOA) | 39강 | Meyer & Pebesma 2021 |
| 적응 대역폭 | Adaptive Bandwidth | 17강 (외 1개 강) | 이웃 수 |
| 전역 / 국지 | Global / Local | 11강 |  |
| 전역 포락선 검정 | Global Envelope Test | 18강 |  |
| 전이 확률 행렬 | Transition Probability Matrix | 34강 |  |
| 점 과정 | Point Process | 16강 | 점 패턴을 만드는 확률 규칙 |
| 점 집계 | Point Aggregation, Spatial Join | 1강 | GeoStat: 점 집계 |
| 점 패턴 | Spatial Point Pattern | 0강 (외 1개 강) | 사건 위치의 모음 |
| 정각 / 정적 / 정거 투영 | Conformal / Equal-area / Equidistant Projection | 2강 |  |
| 정규 Q-Q 그림 | Normal Q-Q Plot | 8강 |  |
| 정규 가정 / 무작위화 / 순열 | Normality / Randomization / Permutation | 11강 |  |
| 정규 근사 | Normal Approximation | 13강 | 순열과 대비 |
| 정규 점수 변환 | Normal Score Transform | 23강 |  |
| 정규분포 / 로그정규분포 / 포아송분포 | Normal / Log-normal / Poisson | 6강 |  |
| 정밀도 행렬 | Precision Matrix | 37강 | 공분산의 역행렬 |
| 정상 분포 | Stationary Distribution | 34강 |  |
| 정확도 평가 | Accuracy Assessment | 40강 |  |
| 조건부 순열 | Conditional Permutation | 12강 | 기준 구역의 값을 고정 |
| 조건부 시뮬레이션 | Conditional Simulation | 23강 | Journel 1974 |
| 조건부 자기회귀 | Conditional Autoregressive (CAR) | 37강 | Besag 1974 |
| 조건수 | Condition Number | 8강 | 30 넘으면 주의 |
| 조인 카운트 | Join Count (BB, BW, WW) | 11강 | 범주 자료 |
| 존 통계 | Zonal Statistics | 1강 | GeoStat: 존 통계 |
| 좌표 특징 | Coordinates as Features | 39강 |  |
| 좌표계 | Coordinate Reference System (CRS) | 2강 |  |
| 좌표계 변환 | Reproject / Transform | 2강 | GeoStat: 내보내기에서 변환 |
| 좌표계 지정 | Assign / Define Projection | 2강 | GeoStat: 좌표계 지정 |
| 주변 가능도 | Marginal Likelihood | 36강 | 2형 최대우도 |
| 중심극한정리 | Central Limit Theorem | 6강 |  |
| 중심화 | Centering | 8강 | 기준값을 뺌 |
| 중첩 교차검증 | Nested Cross-validation | 39강 |  |
| 지구통계 | Geostatistics | 20강 | Krige 1951, Matheron 1963 |
| 지리 좌표계 | Geographic Coordinate System | 2강 | 경위도 |
| 지리가중회귀 | Geographically Weighted Regression (GWR) | 29강 | Brunsdon 외 1996; 이형: 지리적 가중 회귀, 지리가중 회귀, 지리적 가중회귀 |
| 지시자 크리깅 | Indicator Kriging | 23강 | Journel 1983 |
| 지역 R² | Local R² | 29강 |  |
| 지역 다중공선성 | Local Multicollinearity | 29강 | Wheeler & Tiefelsdorf 2005 |
| 지역 조건수 | Local Condition Number | 29강 |  |
| 지오데모그래픽스 | Geodemographics | 31강 | 지역 유형 분류 |
| 지오메트리 | Geometry | 1강 |  |
| 지오코딩 | Geocoding | 4강 | 주소를 좌표로 바꿈 |
| 지원 | Support | 1강 (외 1개 강) | 값이 대표하는 공간 범위. 3강; 점, 셀, 블록 |
| 지원 변경 | Change of Support | 1강 (외 1개 강) |  |
| 지원 효과 | Support Effect | 40강 | 1강의 지원 |
| 직접 효과 | Direct Effect | 25강 | LeSage & Pace 2009 |
| 질병 지도 | Disease Mapping | 37강 |  |
| 집중 로그우도 | Concentrated Log-likelihood | 25강 |  |

### ㅊ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 차분 Moran's I / 차분 LISA | Differential Moran's I / LISA | 34강 |  |
| 창 | Window | 15강 | 원형, 타원, 유연한 창 |
| 척도 인자 | Scaling Factor | 37강 | ICAR 주변 분산의 기하 평균 |
| 척도 효과 | Scale Effect | 3강 | 집계 효과(aggregation effect)라고도 함 |
| 초과 확률 | Exceedance Probability | 23강 (외 1개 강) | 1 − Φ((T − Ẑ)/σ_K); P(θ > 기준) |
| 초과위험 | Excess Risk | 14강 | 관측 ÷ 기대 |
| 초사전분포 | Hyperprior | 36강 |  |
| 초점 검정 | Focused Test | 15강 | 미리 정한 지점 주변 |
| 촐레스키 분해 | Cholesky Decomposition | 23강 | C = LLᵀ |
| 총 효과 | Total Effect | 25강 |  |
| 최근린 거리 | Nearest Neighbour Distance | 16강 | Clark–Evans R |
| 최근린 거리 함수 | Nearest Neighbour Distance Function G | 18강 |  |
| 최근접 이웃 가우스 과정 | Nearest-Neighbor Gaussian Process (NNGP) | 40강 | Datta 외 2016 |
| 최근접 이웃 거리 맞춤 | Nearest Neighbour Distance Matching (NNDM) | 39강 | Milà 외 2022 |
| 최대우도 / 로그우도 | Maximum Likelihood / Log-likelihood | 8강 | 이형: 최우추정, 최대 우도 |
| 최량 선형 불편 예측 | Best Linear Unbiased Prediction (BLUP) | 22강 |  |
| 최소 대비 | Minimum Contrast | 19강 |  |
| 최소 신장 트리 | Minimum Spanning Tree | 32강 |  |
| 최소제곱법 | Ordinary Least Squares (OLS) | 8강 |  |
| 추세 | Trend (First-order Effect) | 11강 |  |
| 축약형 | Reduced Form | 25강 |  |
| 축척 계수 | Scale Factor | 2강 |  |
| 축척 막대 | Scale Bar | 42강 |  |
| 측정 척도 (명목·서열·등간·비율) | Levels of Measurement (Nominal, Ordinal, Interval, Ratio) | 1강 | Stevens 1946 |
| 측지 기준계 | Geodetic Datum | 2강 | Korea 2000(KGD2002), 한국측지계 1985 |
| 층화 무작위 추출 | Stratified Random Sampling | 38강 |  |

### ㅋ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 카토그램 | Cartogram | 5강 | 크기를 다른 양에 비례하게 |
| 커널 | Kernel | 10강 (외 1개 강) | 고정·적응 대역폭; bisquare, gaussian, exponential |
| 커널 밀도 추정 | Kernel Density Estimation (KDE) | 17강 |  |
| 켤레 사전분포 | Conjugate Prior | 36강 | 포아송-감마 |
| 코렐로그램 | Correlogram | 11강 | 거리·차수별 자기상관 |
| 코크리깅 | Cokriging | 22강 |  |
| 콕스 과정 | Cox Process | 19강 | 강도가 확률적 |
| 크로네커 곱 | Kronecker Product | 33강 |  |
| 크리게의 관계 | Krige's Relation | 40강 | 분산의 분해 |
| 크리깅 | Kriging | 22강 | Krige 1951, Matheron 1963; 이형: 크리징 |
| 크리깅 분산 | Kriging Variance | 22강 |  |
| 키 | Key | 4강 | 두 표를 잇는 공통 열 |

### ㅌ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 타원체 | Ellipsoid | 2강 | GRS80, WGS 84, Bessel 1841 |
| 탐색적 공간 자료 분석 | Exploratory Spatial Data Analysis (ESDA) | 5강 |  |
| 탐욕 알고리즘 | Greedy Algorithm | 23강 | 하나씩 최선을 고름 |
| 텍사스 명사수의 오류 | Texas Sharpshooter Fallacy | 15강 | 사후 가설 |
| 토블러의 지리학 제1법칙 | Tobler's First Law of Geography | 0강 |  |
| 투영 좌표계 | Projected Coordinate System | 2강 |  |
| 특수→일반 / 일반→특수 | Specific-to-general / General-to-specific | 26강 |  |
| 틈 / 겹침 | Gap / Overlap (Sliver) | 4강 | 경계가 어긋나 생긴 작은 조각 |
| 티센 다각형 | Thiessen (Voronoi) Polygon | 20강 |  |

### ㅍ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 파급 | Spillover | 24강 |  |
| 파레토 k | Pareto k | 37강 | PSIS-LOO의 진단값 |
| 팔꿈치 방법 | Elbow Method | 31강 |  |
| 패널 자료 | Panel Data | 33강 | 고정 단위의 시계열 |
| 편향 | Bias | 24강 |  |
| 평균 / 중앙값 | Mean / Median | 6강 |  |
| 평활 잔차 | Smoothed Residual | 19강 | Baddeley et al. 2005 |
| 평활 편향 | Smoothing Bias | 29강 |  |
| 평활 효과 | Smoothing Effect | 23강 | 크리깅 지도의 변동이 실제보다 작음 |
| 포아송 회귀 | Poisson Regression | 27강 | 일반화 선형 모형 |
| 포함확률 | Inclusion Probability | 38강 |  |
| 폴스비-포퍼 지수 | Polsby-Popper Score | 32강 | 4πA/P² |
| 표본분포 | Sampling Distribution | 6강 |  |
| 표시 상관 함수 | Mark Correlation Function | 18강 |  |
| 표시 점 패턴 | Marked Point Pattern | 16강 | 연령대 등 |
| 표준오차 | Standard Error (SE) | 6강 | 추정값의 흔들림 |
| 표준편차 | Standard Deviation (SD) | 6강 | 개별 값의 퍼짐 |
| 표준편차 지도 | Standard Deviation Map | 5강 | 평균 ± σ, 2σ로 끊음 |
| 표준화 | Standardization | 31강 | z점수 |
| 표준화 계수 | Standardized Coefficient | 30강 |  |
| 표준화 사망비 | Standardized Mortality Ratio (SMR) | 14강 | 간접 표준화 |
| 표준화 오차 | Standardized Error | 22강 | 제곱 평균이 1이면 적절 |
| 피벗 / 언피벗 | Pivot / Melt | 33강 |  |
| 피처 | Feature | 1강 | 지오메트리 + 속성 |

### ㅎ

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 하버사인 공식 | Haversine Formula | 2강 |  |
| 하우스만 검정 | Hausman Test | 35강 | 고정효과 대 확률효과 |
| 합동 OLS | Pooled OLS | 35강 |  |
| 핫스팟 / 콜드스팟 | Hot Spot / Cold Spot | 12강 (외 1개 강) | Gi\* z의 부호; 이형: 핫스폿, 열점, 콜드스폿, 냉점 |
| 해밀토니안 몬테카를로 | Hamiltonian Monte Carlo (HMC, NUTS) | 36강 | Stan, PyMC |
| 해상도 | Resolution | 1강 (외 1개 강) | 래스터 셀의 크기; 셀 크기 |
| 행정동 / 법정동 | Administrative Dong / Legal Dong | 4강 |  |
| 허용 오차 인접 | Fuzzy Contiguity | 4강 | 구역을 조금 넓혀 겹치면 이웃. PySAL `fuzzy_contiguity` |
| 호비츠-톰프슨 추정량 | Horvitz–Thompson Estimator | 38강 | 1952 |
| 혼란 변수 / 매개 변수 / 충돌 변수 | Confounder / Mediator / Collider | 41강 |  |
| 확률장 | Random Field | 20강 |  |
| 확장법 | Expansion Method | 28강 | Casetti 1972 |
| 회귀 크리깅 | Regression Kriging | 22강 | Hengl et al. 2007 |
| 횡메르카토르 | Transverse Mercator (TM) | 2강 | 한국 국가 좌표계의 투영법 |
| 효과 크기 | Effect Size | 42강 |  |
| 효율성 | Efficiency | 24강 |  |
| 흔적 그림 | Trace Plot | 36강 |  |
| 희소 행렬 | Sparse Matrix | 10강 | 비영 비율 |

### 영문·기호

| 한글 | 영문 | 처음 나온 강 | 비고 |
|---|---|---|---|
| 1종 오류 / 2종 오류 | Type I / Type II Error | 7강 | 거짓 양성 / 거짓 음성 |
| 2단계 최소제곱 | Two-stage Least Squares (2SLS) | 25강 | GM 추정 |
| 2차 군집 | Secondary Cluster | 15강 |  |
| 2차 정상성 | Second-Order Stationarity | 20강 |  |
| BYM 모형 | Besag–York–Mollié Model | 37강 | 1991 |
| BYM2 모형 | BYM2 | 37강 | Riebler 외 2016 |
| Chow 검정 | Chow Test | 28강 | Chow 1960 |
| EB Moran's I | EB Moran's I | 14강 | Assunção & Reis 1999 |
| EPSG 코드 | EPSG Code | 2강 | 좌표계 번호 |
| GRTS | Generalized Random Tessellation Stratified | 38강 | Stevens & Olsen 2004 |
| INLA | Integrated Nested Laplace Approximation | 36강 | Rue 외 2009 |
| J 함수 | J Function | 18강 | van Lieshout & Baddeley 1996 |
| K 함수 | Ripley's K Function | 18강 | Ripley 1976 |
| K-평균 | K-means | 31강 | MacQueen 1967, Lloyd 1982 |
| L 함수 | L Function | 18강 | Besag 1977 |
| LISA 마르코프 | LISA Markov | 34강 | Rey 2001 |
| LM-SARMA | LM-SARMA | 24강 | 두 의존 동시 검정 |
| Max-p 지역화 | Max-p Regionalization | 32강 | Duque 외 2012 |
| R-hat | Potential Scale Reduction Factor | 36강 | Gelman & Rubin 1992 |
| REDCAP | Regionalization with Dynamically Constrained Agglomerative Clustering and Partitioning | 32강 | Guo 2008 |
| SAC, SARAR | Spatial Autoregressive Combined | 26강 | 시차 + 오차 |
| SKATER | Spatial 'K'luster Analysis by Tree Edge Removal | 32강 | Assunção 외 2006 |
| Strauss 과정 | Strauss Process | 19강 | 하드코어는 γ = 0 |
| Thomas 과정 | Thomas Process | 19강 | 자식이 정규분포로 퍼짐 |
| WAIC / LOO / DIC | Widely Applicable IC / Leave-One-Out CV / Deviance IC | 37강 | 모형 비교 지표 |
| Ward 방법 | Ward's Method | 31강 | Ward 1963 |
| k-최근접 이웃 | k-Nearest Neighbors (KNN) | 10강 | 비대칭 |
| p값 | p-value | 7강 |  |

<!-- 용어표 자동 생성 끝 -->

---

[목차](../README.md) · 이전: [부록 C 기호·수식표](C-symbols.md) · 다음: [부록 E 도구별 차이와 결과 재현](E-tools-reproducibility.md)
