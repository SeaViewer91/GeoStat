---
id: F
part: appendix
title: 더 읽을거리
app: none
version: 1
updated: 2026-10-02
status: draft
---

[목차](../README.md) · 이전: [부록 E 도구별 차이와 결과 재현](E-tools-reproducibility.md) · 다음: [부록 G 예제 자료](G-example-data.md)

# 부록 F 더 읽을거리

> 이 책 다음에 읽을 교과서와 온라인 자료를 갈래별로 고르고, 어느 강 다음에 읽으면 좋은지 적음

각 강의 "원전과 더 읽을거리"는 그 강의 방법에 대한 논문과 장을 적었음. 이 부록은 한 권의 책 단위로, 이 책을 마친 뒤 어디로 가면 좋은지를 정리함. 온라인에서 무료로 읽을 수 있는 책은 따로 표시했음.

## 1. 읽는 순서

1. **이 책과 같은 높이의 개론**으로 다른 설명을 한 번 더 읽음. 같은 개념을 다른 예로 보면 빈 곳이 메워짐(2절)
2. **자기 자료의 갈래**를 깊게 다룬 교과서 한 권을 고름(3절). 면 자료면 공간계량경제와 질병 지도, 점이면 점 패턴, 관측소면 지구통계
3. **도구의 문서**를 함께 읽음(4절). 기본값과 옵션의 뜻은 결국 문서와 원전에 있음

## 2. 개론과 전반

| 책 | 어떤 책인가 | 이 책의 어디와 |
|---|---|---|
| Anselin, L. (2024). *An Introduction to Spatial Data Science with GeoDa* (Vols. 1–2). CRC Press. **온라인 무료**(lanselin.github.io/introbook_vol1, introbook_vol2) | GeoDa를 만든 저자가 탐색적 공간 자료 분석과 군집을 차례로 설명함. 앱의 사용법과 개념이 함께 있어 GeoStat 사용자에게 가장 가까움 | 3부, 5강, 8부 |
| Rey, S. J., Arribas-Bel, D., & Wolf, L. J. (2023). *Geographic Data Science with Python*. CRC Press. **온라인 무료** | PySAL 개발자들의 책. 이 책의 "코드로" 절과 같은 라이브러리를 씀 | 3부, 6부, 8부 |
| Pebesma, E., & Bivand, R. (2023). *Spatial Data Science: With Applications in R*. CRC Press. **온라인 무료** | R의 sf·stars 개발자들의 책. 자료 구조, 래스터, 데이터 큐브에서 통계 모형까지 | 1부, 40강 |
| O'Sullivan, D., & Unwin, D. J. (2010). *Geographic Information Analysis* (2nd ed.). Wiley. | 지리학 쪽 개론. 수식이 적고 개념 설명이 친절함 | 0~5부 |
| Bivand, R. S., Pebesma, E., & Gómez-Rubio, V. (2013). *Applied Spatial Data Analysis with R* (2nd ed.). Springer. | R로 하는 공간 분석의 고전. 면 자료·점·지구통계를 고루 다룸 | 3~6부 |
| Haining, R. (2003). *Spatial Data Analysis: Theory and Practice*. Cambridge University Press. | 자료의 질, 탐색, 모형을 통계학의 틀로 정리함 | 1~3부, 6부 |
| Cressie, N. (1993). *Statistics for Spatial Data* (Rev. ed.). Wiley. | 세 갈래(지구통계, 격자 자료, 점 패턴)를 한 틀로 묶은 기준서. 수학적으로 어려움 | 0강, 4·5부 |

## 3. 갈래별 교과서

### 면 자료와 공간 회귀 (3부, 6부)

- Cliff, A. D., & Ord, J. K. (1981). *Spatial Processes: Models & Applications*. Pion. 공간 자기상관 검정의 고전
- Anselin, L. (1988). *Spatial Econometrics: Methods and Models*. Kluwer Academic. 공간시차·공간오차 모형과 LM 검정의 원전
- LeSage, J., & Pace, R. K. (2009). *Introduction to Spatial Econometrics*. Chapman & Hall/CRC. 직접·간접·총 효과와 계산법(25강)
- Elhorst, J. P. (2014). *Spatial Econometrics: From Cross-Sectional Data to Spatial Panels*. Springer. 모형 계보와 공간 패널(26강, 35강)
- Arbia, G. (2014). *A Primer for Spatial Econometrics: With Applications in R*. Palgrave Macmillan. 짧은 입문서

### 비율과 질병 지도 (14강, 36~37강)

- Waller, L. A., & Gotway, C. A. (2004). *Applied Spatial Statistics for Public Health Data*. Wiley. 보건 자료의 비율, 군집 탐지, 점 패턴을 한 권에
- Lawson, A. B. (2018). *Bayesian Disease Mapping: Hierarchical Modeling in Spatial Epidemiology* (3rd ed.). Chapman & Hall/CRC.
- Moraga, P. (2019). *Geospatial Health Data: Modeling and Visualization with R-INLA and Shiny*. Chapman & Hall/CRC. **온라인 무료**
- Moraga, P. (2023). *Spatial Statistics for Data Science: Theory and Practice with R*. Chapman & Hall/CRC. **온라인 무료**

### 공간 이질성과 영역화 (7~8부)

- Fotheringham, A. S., Brunsdon, C., & Charlton, M. (2002). *Geographically Weighted Regression: The Analysis of Spatially Varying Relationships*. Wiley. GWR의 기준서(29강)
- Oshan, T. M., Li, Z., Kang, W., Wolf, L. J., & Fotheringham, A. S. (2019). mgwr: A Python implementation of multiscale geographically weighted regression for investigating process spatial heterogeneity and scale. *ISPRS International Journal of Geo-Information*, 8(6), 269. GeoStat 엔진이 쓰는 mgwr의 설명(30강)
- Duque, J. C., Ramos, R., & Suriñach, J. (2007). Supervised regionalization methods: A survey. *International Regional Science Review*, 30(3), 195–220. 영역화 방법의 지도(32강)

### 점 패턴 (4부)

- Baddeley, A., Rubak, E., & Turner, R. (2015). *Spatial Point Patterns: Methodology and Applications with R*. Chapman & Hall/CRC. spatstat 개발자들의 책. 점 패턴의 사실상 표준서
- Diggle, P. J. (2013). *Statistical Analysis of Spatial and Spatio-Temporal Point Patterns* (3rd ed.). Chapman & Hall/CRC.
- Illian, J., Penttinen, A., Stoyan, H., & Stoyan, D. (2008). *Statistical Analysis and Modelling of Spatial Point Patterns*. Wiley.

### 지구통계 (5부)

- Isaaks, E. H., & Srivastava, R. M. (1989). *An Introduction to Applied Geostatistics*. Oxford University Press. 손계산 위주의 친절한 입문서
- Webster, R., & Oliver, M. A. (2007). *Geostatistics for Environmental Scientists* (2nd ed.). Wiley. 환경 자료의 베리오그램과 크리깅 실무
- Diggle, P. J., & Ribeiro, P. J., Jr. (2007). *Model-based Geostatistics*. Springer. 지구통계를 확률 모형과 가능도로 다룸
- Chilès, J.-P., & Delfiner, P. (2012). *Geostatistics: Modeling Spatial Uncertainty* (2nd ed.). Wiley. 깊이 있는 참고서

### 시공간과 베이즈 (9~10부)

- Wikle, C. K., Zammit-Mangion, A., & Cressie, N. (2019). *Spatio-Temporal Statistics with R*. Chapman & Hall/CRC. **온라인 무료**
- Cressie, N., & Wikle, C. K. (2011). *Statistics for Spatio-Temporal Data*. Wiley. 시공간 통계의 기준서
- Banerjee, S., Carlin, B. P., & Gelfand, A. E. (2014). *Hierarchical Modeling and Analysis for Spatial Data* (2nd ed.). Chapman & Hall/CRC. 공간 계층 베이즈의 기준서
- Blangiardo, M., & Cameletti, M. (2015). *Spatial and Spatio-temporal Bayesian Models with R-INLA*. Wiley.
- Gómez-Rubio, V. (2020). *Bayesian Inference with INLA*. Chapman & Hall/CRC. **온라인 무료**
- Gelman, A., Carlin, J. B., Stern, H. S., Dunson, D. B., Vehtari, A., & Rubin, D. B. (2013). *Bayesian Data Analysis* (3rd ed.). Chapman & Hall/CRC. **저자 누리집에서 PDF 무료**. 베이즈 통계 일반(36강)

### 표본 설계와 공간 데이터 과학 (11부)

- Brus, D. J. (2022). *Spatial Sampling with R*. Chapman & Hall/CRC. **온라인 무료**. 38강의 설계를 모두 다룸
- de Gruijter, J., Brus, D. J., Bierkens, M. F. P., & Knotters, M. (2006). *Sampling for Natural Resource Monitoring*. Springer.
- Lovelace, R., Nowosad, J., & Muenchow, J. (2025). *Geocomputation with R* (2nd ed.). Chapman & Hall/CRC. **온라인 무료**. 공간 교차검증을 포함한 통계 학습의 장이 있음(39강)

## 4. 도구의 문서

| 도구 | 문서 | 특히 볼 곳 |
|---|---|---|
| GeoDa | GeoDa Center의 워크북(geodacenter.github.io) | 가중치, LISA, 군집. Anselin의 실습 노트 |
| PySAL | pysal.org의 각 패키지 문서(libpysal, esda, spreg, mgwr, spopt, pointpats) | 함수마다의 기본값과 참고 문헌 |
| R | spdep, spatialreg, spatstat, gstat, GWmodel의 매뉴얼과 비네트 | r-spatial.org의 글 |
| ArcGIS Pro | 공간 통계 도구 상자(Spatial Statistics toolbox)의 "How ... works" 문서 | 도구마다의 수식과 기본값 |
| R-INLA | r-inla.org | 모형(bym2 등)과 사전분포 |
| SaTScan | satscan.org의 사용자 안내서 | 스캔 통계의 설정 |

도구마다 기본값이 달라 같은 자료에서도 결과가 조금씩 다름. 그 차이와 맞추는 법은 부록 E에 정리했음.

## 5. 학술지

공간통계 방법은 다음 학술지에서 주로 발표됨. 새 방법을 쓰기 전에 그 방법의 원 논문과, 그 방법을 비판하거나 비교한 후속 논문을 함께 찾아 읽음.

- *Geographical Analysis*, *Journal of Geographical Systems*, *International Journal of Geographical Information Science*: 공간 분석 방법 일반
- *Spatial Statistics*, *Journal of Agricultural, Biological and Environmental Statistics*: 통계학 쪽의 공간 방법
- *Spatial and Spatio-temporal Epidemiology*, *International Journal of Health Geographics*: 질병 지도와 보건
- *Regional Science and Urban Economics*, *Spatial Economic Analysis*, *Papers in Regional Science*: 공간계량경제
- *Mathematical Geosciences*, *Geoderma*: 지구통계와 토양·환경
- *Remote Sensing of Environment*: 원격탐사 산출물과 정확도 평가

---

[목차](../README.md) · 이전: [부록 E 도구별 차이와 결과 재현](E-tools-reproducibility.md) · 다음: [부록 G 예제 자료](G-example-data.md)
