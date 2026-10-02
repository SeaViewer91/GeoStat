---
id: 37
part: 10
title: 질병 지도와 CAR 모형
app: code
version: 1
updated: 2026-10-02
status: draft
---

[목차](../README.md) · 이전: [36강 베이지안 사고와 계층 모형](36-bayesian-hierarchical.md) · 다음: [38강 공간 표본 설계](38-spatial-sampling.md)

# 37강 질병 지도와 CAR 모형

> 앱 지원: ○ GeoStat에 CAR·BYM 모형이 없어 코드(PyMC)로 함. 결과를 GeoPackage로 저장해 앱에서 지도로 봄 · 읽는 시간 약 50분

## 이 강에서 얻는 것

- 질병 지도의 기본 틀(관측 건수, 기대 건수, 상대위험, 랜덤효과)을 앎
- CAR 모형을 조건부 분포로 이해하고, ICAR의 정밀도 행렬이 왜 특이 행렬인지 손으로 확인함
- BYM과 BYM2 모형의 구조와 척도 인자, 혼합 모수 φ의 뜻을 앎
- PyMC로 BYM2를 적합하고, 사후 상대위험·초과 확률 지도를 만들어 EB 평활과 비교할 수 있음
- 공변량을 넣은 생태 회귀에서 공간 랜덤효과가 계수와 구간에 주는 영향(공간 교락)을 앎

## 들어가는 질문

36강의 계층 모형은 모든 동을 도시 전체의 평균 쪽으로 당겼음. 그런데 다솜23동의 이웃 동들은 출동이 기대보다 적은 곳(이웃의 SMR 0.82)이고, 마루16동의 이웃들은 기대보다 많은 곳(1.60)임. 출동 위험은 지표온도처럼 공간적으로 이어지는 요인의 영향을 받으므로, 작은 동의 불확실한 값은 도시 평균보다 이웃의 값 쪽으로 당기는 것이 더 그럴듯함. 14강의 공간 EB가 이 생각을 했지만, 이웃의 범위를 자기와 1차 이웃으로 정해 두고 창 안에서 다시 적률로 추정해, 다솜23동을 도시 평균 쪽 EB(14.80)보다 오히려 높은 1만 명당 30.28(시에서 가장 높음)로 남겼음.

이 강은 "이웃끼리 닮는다"를 확률 모형으로 넣는 방법인 CAR 모형과, 질병 지도의 표준이 된 BYM 모형을 다룸.

## 1. 질병 지도의 틀

질병 지도(disease mapping)는 작은 지역마다 질병의 위험을 추정해 지도로 그리는 일임. 출동도 같은 틀로 다룸. 동 i의 관측 건수 yᵢ, 인구 구조로 기대되는 건수 Eᵢ(14강의 간접 표준화), 상대위험 θᵢ로 다음과 같이 둠.

$$
y_i \sim \text{Poisson}(E_i\, \theta_i), \qquad \log \theta_i = \beta_0 + \mathbf x_i^\top \boldsymbol\beta + \text{(랜덤효과)}_i
$$

- SMR(yᵢ/Eᵢ)은 θᵢ의 최대우도 추정값임. 기대 건수가 작으면 불안정함
- 한빛시 2025년의 기대 건수는 1.05~22.78건이고, 5건 미만인 동이 40개, 출동 0건인 동이 7개임. SMR은 0.00~3.71
- θᵢ = 1이 도시 평균(연령 구조를 맞춘)이고, 1.2는 기대보다 20% 많다는 뜻임

랜덤효과에 무엇을 넣느냐로 모형이 갈림.

| 랜덤효과 | 뜻 | 당기는 방향 |
|---|---|---|
| 없음 | 공변량으로 다 설명됨 | 없음(과산포가 있으면 구간이 너무 좁음) |
| 독립(iid) 효과 vᵢ | 동마다 따로인 이질성 | 도시 평균 쪽(36강의 계층 모형과 같은 생각) |
| 공간 구조 효과 uᵢ(CAR) | 이웃끼리 닮은 부분 | 이웃의 값 쪽 |
| 둘 다(BYM, BYM2) | 이질성 + 공간 구조 | 자료가 정한 비율로 둘 다 |

## 2. CAR 모형

**조건부 자기회귀**(conditional autoregressive, CAR) 모형은 각 지역의 값을 "이웃의 값이 주어졌을 때"의 분포로 정의함(Besag 1974). 가장 많이 쓰는 **내재적 CAR**(intrinsic CAR, ICAR)는 다음과 같음.

$$
u_i \mid u_{-i} \sim N\!\left(\frac{1}{n_i}\sum_{j \sim i} u_j,\; \frac{\sigma^2}{n_i}\right)
$$

nᵢ는 이웃 수, j ∼ i는 i의 이웃 j를 뜻함. 지역 i의 값은 이웃 값의 평균 근처에 있고, 이웃이 많을수록 그 평균을 더 믿음(분산이 작음). 10강의 행 표준화 가중치로 구한 공간시차와 같은 평균임.

### 손으로 해 보기 1: 조건부 분포

이웃이 4개이고 그 값이 0.2, 0.1, 0.3, −0.2인 지역의 조건부 평균은 (0.2 + 0.1 + 0.3 − 0.2) / 4 = 0.100이고, 조건부 분산은 σ²/4임.

### 손으로 해 보기 2: 정밀도 행렬

조건부 분포를 모두 모으면 결합분포의 **정밀도 행렬**(공분산 행렬의 역행렬)이 Q = (D − W)/σ²가 됨. D는 이웃 수를 대각에 놓은 행렬, W는 0/1 인접 행렬임. 지역 네 개를 A–B–C–D로 일렬로 이으면 다음과 같음.

$$
D - W = \begin{pmatrix} 1 & -1 & 0 & 0 \\ -1 & 2 & -1 & 0 \\ 0 & -1 & 2 & -1 \\ 0 & 0 & -1 & 1 \end{pmatrix}
$$

- 행의 합이 모두 0이라 행렬식이 0임(고유값 0, 0.586, 2, 3.414). 역행렬이 없어 ICAR는 정상적인 확률분포가 아님(**내재적**, improper)
- 뜻은 "모든 값에 같은 상수를 더해도 밀도가 같다"임. ICAR는 이웃 사이의 차이만 정하고 전체 수준은 정하지 않음. 그래서 **합 0 제약**(Σuᵢ = 0)을 두고, 전체 수준은 절편 β₀가 맡음
- 합 0 제약 아래 네 지역의 주변 분산은 0.875, 0.375, 0.375, 0.875임. 이웃이 하나뿐인 양 끝이 가운데보다 두 배 넘게 큼. CAR의 분산은 지도 위의 위치(이웃의 수와 배치)에 따라 달라짐
- **고유 CAR**(proper CAR)는 Q = (D − ρW)/σ²로 두고 |ρ| < 1이면 역행렬이 있음. ρ = 0.9이면 행렬식 0.6061, 주변 분산 2.59, 1.963, 1.963, 2.59임. 다만 ρ가 1에 가깝지 않으면 이웃끼리의 닮음이 약하게 나와, 질병 지도에서는 ICAR나 아래의 BYM2를 더 씀

### CAR와 SAR

26강 공간오차 모형(SEM)의 오차 u = λWu + ε는 모든 지역을 한 식으로 동시에 정의하는 **동시 자기회귀**(simultaneous autoregressive, SAR) 과정임. 25강의 공간시차 모형을 부르는 약자 SAR과 글자가 같지만, 여기서는 오차 과정을 뜻함. CAR는 지역마다 조건부로 정의함(conditional). 둘 다 정규분포의 정밀도 행렬로 쓸 수 있지만 모양이 다름(SAR: (I − λW)ᵀ(I − λW), CAR: D − ρW). CAR의 정밀도 행렬은 이웃끼리만 0이 아닌 성긴 행렬이라, MCMC와 INLA에서 계산이 빠름. 그래서 계층 베이즈 모형에서는 CAR를 주로 씀.

## 3. BYM과 BYM2

**BYM 모형**(Besag, York & Mollié 1991)은 독립 효과와 ICAR 효과를 함께 넣음.

$$
\log \theta_i = \beta_0 + v_i + u_i, \qquad v_i \sim N(0, \sigma_v^2), \quad u \sim \text{ICAR}(\sigma_u^2)
$$

질병 지도의 표준 모형이 되었지만 두 가지 문제가 있음. 자료로는 vᵢ + uᵢ의 합만 알 수 있어 두 분산이 잘 분리되지 않고, ICAR의 분산 σᵤ²는 위에서 본 것처럼 지도마다 뜻이 달라 사전분포를 정하기 어려움.

**BYM2**(Riebler 외 2016)는 이것을 고쳐 다음과 같이 둠.

$$
\log \theta_i = \beta_0 + \mathbf x_i^\top \boldsymbol\beta + \sigma\left(\sqrt{1-\phi}\; v_i + \sqrt{\phi / s}\; u_i\right), \qquad v_i \sim N(0, 1),\; u \sim \text{ICAR}(1)
$$

- σ는 랜덤효과 전체의 표준편차, φ(0~1)는 그 가운데 **공간 구조가 차지하는 비율**임. 두 모수가 따로 해석됨
- s는 **척도 인자**로, ICAR의 주변 분산의 기하 평균임. u를 √s로 나눠 어느 지도에서나 "평균 분산 1"이 되게 맞춤. 일렬의 네 지역은 s = (0.875 × 0.375 × 0.375 × 0.875)^(1/4) = 0.5728이고, 한빛시 150개 동의 퀸 인접은 0.4132임
- 이렇게 맞추면 σ와 φ에 지도와 상관없는 사전분포를 줄 수 있음. 여기서는 σ ~ 반정규(0, 1), φ ~ 베타(1, 1)(균등)를 썼음. 원저자들은 복잡도 벌점(PC) 사전분포를 권함(Simpson 외 2017)

비슷한 목적의 **르루 모형**(Leroux, Lei & Breslow 2000)은 정밀도 행렬을 (1 − λ)I + λ(D − W)로 둬서 하나의 랜덤효과로 독립과 공간 구조 사이를 잇음.

## 4. 한빛시 출동의 질병 지도

2025년 출동 건수와 연령 표준화 기대 건수(65세 이상 1만 명당 25.72, 미만 8.11)로 다섯 모형을 적합했음. PyMC의 NUTS(36강의 HMC)로 체인 4개를 예열 2,000번 뒤 2,000번씩 뽑았고, 모든 모형에서 최대 R-hat 1.000, 최소 유효 표본 크기 1,051 이상, 발산 0이었음(`book/fig-src/37.py`).

![출동의 상대위험 지도(연령 표준화, 1이 도시 평균). 왼쪽 위: 원래의 SMR(관측 ÷ 기대). 인구 적은 동의 극단값이 많음(범위 0.00~3.71). 오른쪽 위: 포아송-감마 EB(도시 평균 쪽으로 당김, 0.62~1.71). 왼쪽 아래: BYM2 사후 평균(이웃과 도시 평균 쪽으로 당김, 0.67~1.93). 마루구 원도심과 가람·누리구 경계의 높은 덩어리, 북쪽 가장자리와 동쪽 다솜구의 낮은 곳이 또렷해짐. 오른쪽 아래: BYM2의 초과 확률 P(RR > 1). 0.95 이상은 8개 동](../fig/37-maps.svg)

- 포아송-감마 EB(36강의 방법을 SMR에 적용, a = b = 12.79)와 독립 효과 모형은 결과가 거의 같음. 둘 다 도시 평균 쪽으로 당김
- BYM2는 공간 비중 φ의 사후 평균이 0.79(95% 0.40~0.99)로, 랜덤효과의 대부분이 공간 구조였음. σ는 0.298(0.215~0.394)
- 독립 효과 모형의 랜덤효과 사후 평균에 Moran's I를 구하면 0.214(유사 p 0.001)로, 독립 효과만으로는 공간 구조가 남음

| 동 | 관측 / 기대 | SMR | 이웃의 SMR | EB | 독립 효과 | BYM2 (95% 구간) | BYM2 P(RR > 1) |
|---|---|---|---|---|---|---|---|
| 다솜23동 | 5 / 1.35 | 3.71 | 0.82 | 1.26 | 1.26 | 1.02 (0.60~1.64) | 0.465 |
| 다솜1동 | 4 / 1.42 | 2.81 | 0.61 | 1.18 | 1.16 | 0.93 (0.54~1.53) | 0.346 |
| 누리12동 | 0 / 1.05 | 0.00 | 0.59 | 0.92 | 0.91 | 0.78 (0.46~1.21) | 0.124 |
| 마루16동 | 31 / 12.75 | 2.43 | 1.60 | 1.71 | 1.77 | 1.93 (1.38~2.62) | 1.000 |

이웃의 SMR은 이웃 동들의 관측 합 ÷ 기대 합임.

- 다솜23동과 다솜1동은 EB에서 도시 평균보다 위(1.26, 1.18)에 남았지만, BYM2에서는 이웃이 낮아 1 근처나 그 아래로 내려감. 독립 효과 모형과 BYM2의 차이가 가장 큰 두 동임
- 누리12동(0건)은 EB에서 0.92로 올라왔지만 BYM2에서는 낮은 이웃 쪽 0.78에 머묾
- 마루16동은 이웃도 높아 BYM2(1.93)가 EB(1.71)보다 오히려 원자료 쪽에 가까움. 공간 모형은 "이웃이 받쳐 주는" 높은 값은 덜 당김
- 초과 확률 0.95 이상인 동은 EB 6개, BYM2 8개임. BYM2는 이웃이 함께 높은 가람33동과 마루13동을 더했음

BYM2의 사후 평균은 SMR과 상관 0.762, EB와 0.909임. 공간 모형으로 바꾸면 지도의 큰 그림은 같지만, 작은 동의 판정이 이웃에 따라 달라짐. 이웃 쪽으로 당기는 것이 늘 옳은 것은 아님. 주변과 정말 다른 작은 동(예: 경계 너머 환경이 다른 동)은 BYM2가 이웃에 묻어 버릴 수 있음. φ와 독립 효과가 이런 동에 여지를 남기지만, 의심스러운 동은 원자료와 함께 따로 살핌.

## 5. 공변량 넣기: 생태 회귀와 공간 교락

8강처럼 동의 평균 지표온도(온도편차 = 평균 − 30℃)를 공변량으로 넣었음. 포아송 회귀의 계수는 로그 상대위험이므로 exp(β)가 1℃당 상대위험임.

![왼쪽: 온도편차 1℃당 상대위험과 95% 신용구간. 랜덤효과 없는 포아송 회귀 1.122, 독립 랜덤효과 1.124, BYM2 1.124로 점추정은 거의 같고, 랜덤효과를 넣을수록 구간이 넓어짐(β의 사후 표준편차 0.0153 → 0.0192). 오른쪽: BYM2의 공간 비중 φ의 사후분포. 온도편차를 넣기 전(실선, 평균 0.79)에는 랜덤효과의 대부분이 공간 구조였지만, 넣은 뒤(점선, 평균 0.41)에는 넓게 퍼짐. 온도가 공간 구조의 상당 부분을 설명함](../fig/37-confound.svg)

| 모형 | 1℃당 상대위험 (95% 구간) | σ | φ |
|---|---|---|---|
| 포아송 회귀 | 1.122 (1.088~1.156) | | |
| 포아송 + 독립 효과 | 1.124 (1.086~1.162) | 0.189 | |
| 포아송 + BYM2 | 1.124 (1.082~1.168) | 0.188 | 0.41 (0.02~0.95) |

- 지표온도가 1℃ 높은 동은 연령 구조를 맞춘 출동 위험이 약 12% 높음
- 온도를 넣자 랜덤효과의 σ가 0.30에서 0.19로 줄고, φ가 0.79에서 0.41로 내려가며 넓게 퍼졌음. 온도가 공간 구조의 상당 부분을 설명했기 때문임. 독립 효과 모형의 랜덤효과에서도 Moran's I가 0.214에서 0.012(유사 p 0.365)로 사라짐
- 공간 랜덤효과를 넣으면 계수의 구간이 넓어짐. 랜덤효과 없는 포아송 회귀는 동끼리의 남은 닮음을 무시해 정밀도를 과대평가함(9강과 같은 문제)

**공간 교락**(spatial confounding)은 공변량이 공간적으로 매끈할 때, 공간 랜덤효과가 공변량과 같은 공간 패턴을 두고 다투어 계수가 크게 바뀌거나 구간이 지나치게 넓어지는 현상임(Reich, Hodges & Zadnik 2006; Hodges & Reich 2010). 한빛시에서는 점추정이 거의 바뀌지 않았지만, 늘 그런 것은 아님. 계수의 해석이 목적이면 랜덤효과 없는 모형, 독립 효과 모형, 공간 모형의 계수를 함께 보고함. 공변량과 겹치는 공간 패턴을 랜덤효과에서 빼는 제한 공간 회귀(restricted spatial regression)도 제안되었지만, 구간이 너무 좁아지는 문제가 지적되어(Khan & Calder 2022) 무엇이 옳은지는 아직 논쟁 중임.

공변량을 넣은 모형의 초과 확률은 온도의 효과까지 포함한 "전체 위험"에 대한 것임. BYM2 + 온도에서 P(RR > 1) ≥ 0.95인 동은 12개로, 가람·누리구의 더운 동(가람19·23·31동, 누리13·17동)과 마루18동이 더해지고 가람33동·누리26동은 빠짐. "온도로 설명되지 않는 위험"이 궁금하면 랜덤효과 exp(σ(…))의 초과 확률을 따로 봄. 또 동 단위의 관계를 개인의 관계로 읽으면 생태학적 오류임(8강).

## 6. 모형 비교

| 모형 | WAIC | 유효 모수 수 p_WAIC | elpd_loo (SE) | 파레토 k > 0.7인 동 |
|---|---|---|---|---|
| 포아송 회귀(온도) | 751.46 | 3.0 | −375.74 (15.40) | 0 |
| 독립 효과 | 762.22 | 42.8 | −388.94 (11.06) | 14 |
| BYM2 | 748.22 | 37.8 | −379.77 (11.03) | 11 |
| 독립 효과 + 온도 | 736.71 | 31.5 | −370.81 (12.32) | 5 |
| BYM2 + 온도 | 738.58 | 30.4 | −371.45 (12.35) | 1 |

- **WAIC**(Watanabe 2010)와 **LOO**(PSIS-LOO; Vehtari, Gelman & Gabry 2017)는 새 자료를 얼마나 잘 예측할지를 추정함. WAIC는 작을수록, elpd_loo는 클수록 좋음. 질병 지도 문헌에서는 **DIC**(Spiegelhalter 외 2002)도 많이 씀(R-INLA에서 `control.compute = list(dic = TRUE)`로 바로 구함)
- 공변량이 없을 때는 BYM2가 독립 효과보다 훨씬 나음(748.2 대 762.2). 공간 구조가 있다는 뜻임
- 온도를 넣으면 독립 효과와 BYM2의 차이(1.9)가 표준오차에 비해 작아 어느 쪽이 낫다고 하기 어려움. 온도가 공간 구조의 상당 부분을 설명했기 때문임
- 지역마다 랜덤효과가 하나씩 있는 모형에서는 한 지역을 빼면 그 지역의 랜덤효과 정보가 사라져, LOO의 근사(PSIS)가 불안정해짐. 파레토 k가 0.7을 넘는 동이 많으면 그 LOO 값을 믿기 어렵다는 경고임. 이때는 k가 큰 동만 실제로 빼고 다시 적합하거나, 39강의 공간 교차검증처럼 지역 묶음을 빼는 방식으로 비교함

## 7. 도구

| 도구 | 언어 | 특징 |
|---|---|---|
| R-INLA | R | BYM2·르루·시공간 모형을 몇 초에 적합함. 질병 지도의 사실상 표준 |
| CARBayes (Lee 2013) | R | CAR 계열 모형을 MCMC로 적합함 |
| brms, Stan | R, Python | `car()` 항이나 직접 쓴 ICAR(Morris 외 2019) |
| PyMC | Python | `pm.ICAR`. 이 강의 코드 |
| GeoDa, GeoStat | | CAR 모형 없음. EB 평활과 EB Moran까지 |

## 해 보기

GeoStat에는 CAR 모형이 없으므로 PyMC로 적합하고, 결과를 GeoPackage로 저장해 앱에서 지도로 봄. PyMC는 GeoStat 엔진 환경에 따로 얹어 씀(`book/fig-src/37.py`의 첫머리 참고). 적합에 몇 분 걸림.

### 코드로: BYM2

```python
import arviz as az
import geopandas as gpd
import numpy as np
import pymc as pm
import pytensor.tensor as pt
from libpysal.weights import Queen

dong = gpd.read_file("book/data/hanbit_dong.gpkg")
ev = gpd.read_file("book/data/hanbit_events.gpkg")
j = gpd.sjoin(ev, dong[["geometry"]], predicate="within")
cnt = lambda s: s.groupby(j["index_right"]).sum().reindex(dong.index, fill_value=0).to_numpy(float)  # noqa: E731
y, old = cnt(j["연령대"].notna()), cnt(j["연령대"] == "65+")
pop, p65 = dong["인구"].to_numpy(float), dong["고령인구"].to_numpy(float)

# 1) 연령 표준화 기대 건수 E와 SMR (14강)
E = p65 * old.sum() / p65.sum() + (pop - p65) * (y - old).sum() / (pop - p65).sum()
dong["SMR"] = y / E

# 2) BYM2의 척도 인자: ICAR 주변 분산의 기하 평균 (Riebler 외 2016)
A = Queen.from_dataframe(dong, use_index=False).full()[0]      # 0/1 인접 행렬
lam, V = np.linalg.eigh(np.diag(A.sum(1)) - A)                  # 첫 고유값이 0 (연결된 그래프)
scale = np.exp(np.mean(np.log((V[:, 1:] ** 2 / lam[1:]).sum(1))))

# 3) BYM2: log RR = b0 + sigma * (sqrt(1 - phi) * v + sqrt(phi / scale) * u)
with pm.Model():
    b0 = pm.Normal("b0", 0, 1)
    sigma = pm.HalfNormal("sigma", 1)
    phi = pm.Beta("phi", 1, 1)
    v = pm.Normal("v", 0, 1, shape=len(y))                      # 독립 효과
    u = pm.ICAR("u", W=A, sigma=1)                               # 공간 구조 효과 (합 0 제약)
    rr = pm.Deterministic("rr", pt.exp(b0 + sigma * (pt.sqrt(1 - phi) * v + pt.sqrt(phi / scale) * u)))
    pm.Poisson("y", mu=E * rr, observed=y)
    idata = pm.sample(2000, tune=2000, chains=4, target_accept=0.95, random_seed=20261002)

print(az.summary(idata, var_names=["b0", "sigma", "phi"]).round(3))
post = idata.posterior["rr"]
dong["RR"] = post.mean(("chain", "draw")).values
dong["P초과"] = (post > 1).mean(("chain", "draw")).values
print(f"척도 인자 {scale:.4f}, 발산 {int(idata.sample_stats['diverging'].sum())}")
print(dong.loc[dong["동이름"].isin(["다솜23동", "마루16동"]), ["동이름", "SMR", "RR", "P초과"]].round(3))
print("P초과 ≥ 0.95:", sorted(dong.loc[dong["P초과"] >= 0.95, "동이름"]))
```

- 확인: 척도 인자 0.4132, 발산 0. φ 사후 평균 0.79 안팎, 다솜23동 RR 1.02 안팎, 마루16동 1.93 안팎(P초과 1.0). P초과 ≥ 0.95는 8개 동(가람33동, 누리26동, 마루13·15·16·17·19·30동). MCMC 표본이라 소수 셋째 자리는 실행 환경에 따라 조금 다를 수 있음
- 앱에서 보기: `dong["logRR"] = np.log(dong["RR"])`를 더하고 `dong.to_file("hanbit_bym2.gpkg")`로 저장한 뒤 **파일 → 데이터 열기…** 메뉴로 엶. `logRR`을 **0 기준 발산 (계수·잔차)** 방법으로 칠하면 도시 평균(RR 1, logRR 0)을 가운데로 한 지도가 됨. `P초과`는 분위수 계급으로 칠하고, `SMR` 지도와 나란히 놓고 작은 동이 어디로 갔는지 봄
- 더 해 보기: `rr` 식에 `+ b1 * x`(x = 온도편차, b1 ~ 정규(0, 1))를 넣어 5절을 재현함. 온도편차는 31강 코드처럼 `exact_extract("book/data/hanbit_lst.tif", dong, "mean", output="pandas")["mean"] - 30`으로 만듦. `az.waic(idata)`와 `az.loo(idata)`를 쓰려면 `pm.sample(..., idata_kwargs={"log_likelihood": True})`로 뽑음

## 헷갈리는 쌍

- **CAR vs SAR(동시 자기회귀)**: 지역마다 이웃이 주어졌을 때의 조건부 분포로 정의함 대 모든 지역을 한 식으로 동시에 정의함(26강의 공간오차 과정. 25강의 공간시차 모형 SAR과는 다른 뜻)
- **ICAR vs 고유 CAR**: 정밀도 행렬이 특이 행렬이라 합 0 제약이 필요함 대 |ρ| < 1로 정상적인 분포가 됨
- **BYM vs BYM2**: 독립·공간 효과에 분산을 따로 둠(분리가 어렵고 사전분포를 정하기 어려움) 대 전체 σ와 공간 비중 φ로 나누고 척도를 맞춤
- **독립 효과 vs 공간 구조 효과**: 도시 평균 쪽으로 당김 대 이웃 쪽으로 당김
- **전체 위험 vs 잔차 위험**: 공변량의 효과를 포함한 상대위험 대 공변량으로 설명되지 않는 랜덤효과 부분

## 흔한 실수와 심사 지적

- **ICAR를 섬이나 떨어진 덩어리가 있는 지도에 그대로 씀**
  - 지적: "이웃이 없는 지역은 어떻게 처리했습니까?"
  - 대응: 이웃이 없는 지역은 공간 효과 없이 독립 효과만 두고, 덩어리마다 합 0 제약과 척도 인자를 따로 둠(Freni-Sterrantino 외 2018). 10강에서 섬을 먼저 확인함
- **BYM2에서 척도 인자를 빠뜨림**
  - 대응: 척도를 맞추지 않으면 φ와 σ의 사전분포가 지도마다 다른 뜻이 되고, φ를 "공간 비중"로 읽을 수 없음
- **공변량 없이 구한 φ를 "공간 효과의 크기"로 해석함**
  - 대응: φ는 공변량에 따라 크게 바뀜(한빛시 0.79 → 0.41). 어떤 공변량을 넣은 뒤의 φ인지 밝힘
- **랜덤효과 없는 포아송 회귀의 좁은 구간으로 계수를 보고함**
  - 대응: 과산포와 남은 공간 의존을 랜덤효과로 다루고, 모형별 계수를 비교해 공간 교락을 점검함
- **파레토 k 경고를 무시하고 LOO로 모형을 고름**
  - 대응: 경고가 많으면 WAIC·DIC와 함께 보고, 필요하면 지역을 실제로 빼고 다시 적합하거나 공간 교차검증을 함
- **사후 평균 지도만 냄**
  - 대응: 초과 확률이나 구간 폭 지도를 함께 냄. 질병 지도의 독자는 대개 "어디가 정말 높은가"를 묻기 때문임

## 보고서에는 이렇게 씀

> 2025년 행정동별 출동 건수를 연령 표준화 기대 건수(65세 이상과 미만의 도시 전체 비율에 의한 간접 표준화)를 노출량으로 하는 포아송 모형으로 분석하였다. 로그 상대위험에는 독립 랜덤효과와 내재적 CAR 공간 랜덤효과를 결합한 BYM2 모형(Riebler 외 2016)을 사용하였고, 공간 구조는 1차 퀸 인접으로 정의하였으며 이웃이 없는 행정동은 없었다(척도 인자 0.413). 사전분포는 절편과 온도 계수 N(0, 1), 전체 표준편차 σ ~ 반정규(0, 1), 공간 비중 φ ~ Beta(1, 1)로 두었다. PyMC의 NUTS로 체인 4개를 각 4,000회(예열 2,000회) 반복하였고, 모든 모수의 R-hat은 1.01 미만, 발산 전이는 없었다. 공변량이 없는 모형에서 φ의 사후 평균은 0.79(95% 신용구간 0.40~0.99)로 랜덤효과 변동의 대부분이 공간적으로 구조화되어 있었다. 도시 평균보다 위험이 높을 사후 확률이 0.95 이상인 행정동은 8개였고, 그 가운데 6개는 마루구 원도심에, 2개는 가람구·누리구 경계 부근에 있었다. 행정동 평균 지표온도를 공변량으로 넣으면 1℃당 상대위험은 1.12(95% 신용구간 1.08~1.17)였고, φ의 사후 평균은 0.41로 낮아졌다. 이 계수는 랜덤효과가 없는 포아송 회귀(1.12)와 비슷하여 공간 교락의 영향은 작았다. 행정동 단위의 연관이므로 개인 수준의 효과로 해석할 수 없다.

적어야 할 항목은 다음과 같음.

- 기대 건수의 계산(표준화 방법과 기준 집단)
- 랜덤효과의 구조(독립, CAR, BYM2)와 인접의 정의, 섬 처리, 척도 인자
- 모든 사전분포, 계산 방법(MCMC 설정과 진단, 또는 INLA)
- 사후 상대위험과 초과 확률(문턱), φ와 σ
- 공변량 계수의 모형별 비교(공간 교락 점검)와 모형 비교 지표

## 요약

- 질병 지도는 yᵢ ~ Poisson(Eᵢθᵢ)로 두고 log θᵢ에 공변량과 랜덤효과를 넣음. 독립 효과는 도시 평균 쪽으로, CAR 효과는 이웃 쪽으로 당김
- ICAR는 "이웃 평균 둘레의 정규분포"로 정의되고, 정밀도 행렬 D − W가 특이 행렬이라 합 0 제약이 필요함. 주변 분산은 지도 위의 위치에 따라 다름
- BYM2는 σ와 공간 비중 φ로 나누고 척도 인자로 맞춰 해석과 사전분포 설정이 쉬움. 한빛시 출동은 φ 0.79로 공간 구조가 컸음
- BYM2에서 다솜23동은 SMR 3.71 → 1.02(이웃이 낮음), 마루16동은 2.43 → 1.93(이웃도 높음)이 되었고, 초과 확률 0.95 이상은 8개 동이었음
- 지표온도 1℃당 상대위험은 모형과 상관없이 1.12였고, 공간 랜덤효과를 넣으면 구간이 넓어졌음. 온도를 넣자 φ가 0.41로 내려갔음

## 핵심 용어

| 한글 | 영문 | 비고 |
|---|---|---|
| 질병 지도 | Disease Mapping | |
| 기대 건수 | Expected Count | 간접 표준화 |
| 상대위험 | Relative Risk (RR) | |
| 조건부 자기회귀 | Conditional Autoregressive (CAR) | Besag 1974 |
| 내재적 CAR | Intrinsic CAR (ICAR) | 합 0 제약 |
| 고유 CAR | Proper CAR | |
| 정밀도 행렬 | Precision Matrix | 공분산의 역행렬 |
| BYM 모형 | Besag–York–Mollié Model | 1991 |
| BYM2 모형 | BYM2 | Riebler 외 2016 |
| 척도 인자 | Scaling Factor | ICAR 주변 분산의 기하 평균 |
| 공간 비중 | Mixing Parameter φ | |
| 르루 모형 | Leroux Model | |
| 복잡도 벌점 사전분포 | Penalized Complexity (PC) Prior | Simpson 외 2017 |
| 생태 회귀 | Ecological Regression | |
| 공간 교락 | Spatial Confounding | Hodges & Reich 2010 |
| WAIC / LOO / DIC | Widely Applicable IC / Leave-One-Out CV / Deviance IC | 모형 비교 지표 |
| 파레토 k | Pareto k | PSIS-LOO의 진단값 |

## 원전과 더 읽을거리

**원전**

- Besag, J. (1974). Spatial interaction and the statistical analysis of lattice systems. *Journal of the Royal Statistical Society: Series B*, 36(2), 192–225.
- Besag, J., York, J., & Mollié, A. (1991). Bayesian image restoration, with two applications in spatial statistics. *Annals of the Institute of Statistical Mathematics*, 43(1), 1–20.
- Riebler, A., Sørbye, S. H., Simpson, D., & Rue, H. (2016). An intuitive Bayesian spatial model for disease mapping that accounts for scaling. *Statistical Methods in Medical Research*, 25(4), 1145–1165.
- Leroux, B. G., Lei, X., & Breslow, N. (2000). Estimation of disease rates in small areas: A new mixed model for spatial dependence. In M. E. Halloran & D. Berry (Eds.), *Statistical Models in Epidemiology, the Environment, and Clinical Trials* (pp. 179–191). Springer.
- Reich, B. J., Hodges, J. S., & Zadnik, V. (2006). Effects of residual smoothing on the posterior of the fixed effects in disease-mapping models. *Biometrics*, 62(4), 1197–1206.
- Hodges, J. S., & Reich, B. J. (2010). Adding spatially-correlated errors can mess up the fixed effect you love. *The American Statistician*, 64(4), 325–334.
- Simpson, D., Rue, H., Riebler, A., Martins, T. G., & Sørbye, S. H. (2017). Penalising model component complexity: A principled, practical approach to constructing priors. *Statistical Science*, 32(1), 1–28.

**더 읽을거리**

- Lawson, A. B. (2018). *Bayesian Disease Mapping* (3rd ed.). Chapman & Hall/CRC.
- Morris, M., Wheeler-Martin, K., Simpson, D., Mooney, S. J., Gelman, A., & DiMaggio, C. (2019). Bayesian hierarchical spatial models: Implementing the Besag York Mollié model in Stan. *Spatial and Spatio-temporal Epidemiology*, 31, 100301.
- Lee, D. (2013). CARBayes: An R package for Bayesian spatial modeling with conditional autoregressive priors. *Journal of Statistical Software*, 55(13), 1–24.
- Freni-Sterrantino, A., Ventrucci, M., & Rue, H. (2018). A note on intrinsic conditional autoregressive models for disconnected graphs. *Spatial and Spatio-temporal Epidemiology*, 26, 25–34.
- Vehtari, A., Gelman, A., & Gabry, J. (2017). Practical Bayesian model evaluation using leave-one-out cross-validation and WAIC. *Statistics and Computing*, 27(5), 1413–1432.
- Spiegelhalter, D. J., Best, N. G., Carlin, B. P., & van der Linde, A. (2002). Bayesian measures of model complexity and fit. *Journal of the Royal Statistical Society: Series B*, 64(4), 583–639.
- Watanabe, S. (2010). Asymptotic equivalence of Bayes cross validation and widely applicable information criterion in singular learning theory. *Journal of Machine Learning Research*, 11, 3571–3594.
- Khan, K., & Calder, C. A. (2022). Restricted spatial regression methods: Implications for inference. *Journal of the American Statistical Association*, 117(537), 482–494.
- Moraga, P. (2019). *Geospatial Health Data: Modeling and Visualization with R-INLA and Shiny*. Chapman & Hall/CRC. 온라인 무료

## 연습

1. 이웃이 3개이고 그 공간 효과가 0.4, 0.1, 0.1인 지역이 있음. ICAR(σ = 0.3)에서 이 지역의 조건부 평균과 표준편차를 구하시오. 이웃이 6개이고 평균이 같다면 표준편차는 어떻게 되는가?

2. 일렬의 네 지역 A–B–C–D에서 양 끝 지역의 ICAR 주변 분산(0.875)이 가운데(0.375)보다 큰 까닭을 조건부 분포로 설명하시오.

3. BYM2에서 φ의 사후분포가 0과 1 사이에 넓게 퍼져 있음(공변량을 넣은 모형의 0.02~0.95). 이것은 모형이 잘못되었다는 뜻인가?

4. 어떤 보고서가 "BYM2 모형에서 다솜23동의 상대위험은 1.02로 도시 평균과 같다. 따라서 다솜23동은 출동 위험 관리 대상에서 제외한다"고 씀. 무엇을 더 확인해야 하는가?

5. 독립 효과 모형과 BYM2의 elpd_loo를 비교하려는데 파레토 k가 0.7을 넘는 동이 각각 14개, 11개였음. 이 비교를 어떻게 다루겠는가?

<details>
<summary>해답</summary>

1. 조건부 평균은 (0.4 + 0.1 + 0.1) / 3 = 0.2, 조건부 분산은 σ²/3 = 0.09/3 = 0.03이므로 표준편차는 √0.03 = 0.173. 이웃이 6개면 분산은 0.09/6 = 0.015, 표준편차는 0.122. 이웃이 많을수록 그 평균을 더 믿어 조건부 분포가 좁아짐.

2. 양 끝 지역은 이웃이 하나뿐이라 조건부 분산이 σ²/1로, 이웃이 둘인 가운데(σ²/2)의 두 배임. 한 이웃에만 묶여 있어 그 이웃에서 멀리 벗어날 수 있음. 합 0 제약 아래에서 이것이 주변 분산의 차이(0.875 대 0.375)로 나타남. 지도의 가장자리나 이웃이 적은 지역의 공간 효과가 더 크게 흔들리는 까닭이고, BYM2가 척도 인자로 이런 차이를 평균 내어 맞추는 까닭이기도 함.

3. 아님. 온도를 넣은 뒤 남은 랜덤효과는 σ 0.19로 작아, 그 작은 변동이 공간 구조인지 독립 효과인지를 150개 동의 자료로 가르기 어렵다는 뜻임. 이때 φ의 사후분포는 사전분포(균등)에 가깝게 넓어짐. φ를 단정적으로 해석하지 말고, 구간을 그대로 보고하며 "남은 변동의 구조는 자료로 정해지지 않았다"고 씀. 사전분포를 바꿔 민감도를 확인함.

4. (1) 사후분포의 폭: 95% 구간이 0.60~1.64로 넓어, "평균과 같다"가 아니라 "평균과 다르다고 할 증거가 부족하다"임. (2) 원자료: 5건 / 기대 1.35건으로 SMR 3.71이고, 값이 내려간 것은 이웃(SMR 0.82)이 낮기 때문임. 이웃과 정말 다른 동이면 공간 모형이 위험을 묻을 수 있음. (3) 다른 모형의 결과: 독립 효과 모형과 EB에서는 1.26이었음. (4) 여러 해의 자료: 35강의 시공간 스캔에서 다솜23동은 2018~2022년에 기대의 8.6배였음. 관리 대상 제외 같은 결정에는 한 해의 평활 값보다 이런 근거를 함께 봐야 함.

5. PSIS-LOO의 근사를 믿기 어렵다는 경고이므로 elpd_loo 차이만으로 고르지 않음. k가 큰 동을 실제로 하나씩 빼고 다시 적합해 그 동의 예측 밀도를 정확히 계산하거나(재적합 LOO), 공간적으로 묶은 지역을 빼는 교차검증(39강)을 함. 함께 WAIC를 보고하되 WAIC도 같은 이유로 불안정할 수 있음을 적음. 한빛시에서는 공변량이 없을 때 WAIC 차이(14.0)가 커서 BYM2가 낫다는 결론이 흔들리지 않지만, 온도를 넣은 두 모형의 차이(1.9)는 판단하기 어려움.

</details>

---

[목차](../README.md) · 이전: [36강 베이지안 사고와 계층 모형](36-bayesian-hierarchical.md) · 다음: [38강 공간 표본 설계](38-spatial-sampling.md)
