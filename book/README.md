# 처음 만나는 공간통계학 (가제)

GeoStat으로 따라 하는 공간통계학 입문서임. 공간정보·지리학을 전공하지 않은 연구자와 실무자가 공간통계학 전반을 처음부터 이해하는 것을 목표로 함.

> **집필 중**임. 아래 목차에서 링크가 있는 강만 공개되었고, 모든 강은 검수 전 초안(draft)임.

## 읽는 방법

- **GitHub에서 바로 읽기**: 아래 목차의 링크를 누름
- **내려받아 읽기 (HTML)**: [`html/book.html`](html/book.html)을 열고 오른쪽 위 **다운로드**(Download raw file) 버튼으로 받은 뒤 브라우저로 엶. 수식·그림이 파일 하나에 모두 들어 있어 인터넷 없이 읽을 수 있음. 강별 파일은 [`html/`](html/) 폴더에 있음
- 인쇄하거나 PDF로 저장하려면 HTML을 브라우저에서 열고 인쇄함

## 목차

앱 지원: ● 앱에서 전부 따라 할 수 있음 / ◐ 일부만 가능 / ○ 코드(Python)로 실습

| 강 | 제목 | 앱 | 상태 |
|---|---|---|---|
| **0부** | **들어가며** | | |
| 0 | [공간통계학이란 무엇인가](lessons/00-what-is-spatial-statistics.md) | - | 초안 |
| **1부** | **공간 자료** | | |
| 1 | [공간 자료의 세 얼굴](lessons/01-three-faces-of-spatial-data.md) | ● | 초안 |
| 2 | [좌표계와 거리](lessons/02-coordinates-and-distance.md) | ● | 초안 |
| 3 | [척도와 단위의 문제](lessons/03-scale-and-units.md) | ◐ | 초안 |
| 4 | [공간 자료 준비](lessons/04-preparing-spatial-data.md) | ● | 초안 |
| 5 | [지도로 탐색하기](lessons/05-mapping-and-exploration.md) | ● | 초안 |
| **2부** | **통계 다시 보기** | | |
| 6 | [요약·분포·추정](lessons/06-summary-distribution-estimation.md) | ◐ | 초안 |
| 7 | [검정의 논리와 순열 검정](lessons/07-testing-and-permutation.md) | ◐ | 초안 |
| 8 | [회귀분석과 진단](lessons/08-regression-and-diagnostics.md) | ● | 초안 |
| 9 | [독립 가정이 깨질 때](lessons/09-when-independence-fails.md) | ○ | 초안 |
| **3부** | **공간 자기상관** | | |
| 10 | [이웃 정하기: 공간가중치](lessons/10-spatial-weights.md) | ● | 초안 |
| 11 | [전역 공간 자기상관](lessons/11-global-autocorrelation.md) | ◐ | 초안 |
| 12 | [국지 공간 자기상관 I: LISA](lessons/12-lisa.md) | ● | 초안 |
| 13 | [국지 공간 자기상관 II](lessons/13-local-statistics.md) | ◐ | 초안 |
| 14 | [비율 자료와 작은 수 문제](lessons/14-rates-small-numbers.md) | ● | 초안 |
| 15 | [공간 군집 탐지](lessons/15-cluster-detection.md) | ○ | 초안 |
| **4부** | **점 패턴** | | |
| 16 | [점 패턴의 기초](lessons/16-point-pattern-basics.md) | ◐ | 초안 |
| 17 | [강도 추정](lessons/17-intensity.md) | ◐ | 초안 |
| 18 | [점 사이의 상호작용](lessons/18-interaction.md) | ○ | 초안 |
| 19 | [점 과정 모형](lessons/19-point-process-models.md) | ○ | 초안 |
| **5부** | **지구통계** | | |
| 20 | [연속 표면과 확률장](lessons/20-continuous-surfaces.md) | ○ | 초안 |
| 21 | [베리오그램](lessons/21-variogram.md) | ○ | 초안 |
| 22 | [크리깅](lessons/22-kriging.md) | ○ | 초안 |
| 23 | [불확실성과 시뮬레이션](lessons/23-uncertainty-simulation.md) | ○ | 초안 |
| **6부** | **공간 회귀** | | |
| 24 | [왜 공간 회귀인가](lessons/24-why-spatial-regression.md) | ● | 초안 |
| 25 | [공간시차 모형](lessons/25-spatial-lag.md) | ● | 초안 |
| 26 | [공간오차 모형과 모형 계보](lessons/26-spatial-error-and-family.md) | ◐ | 초안 |
| 27 | [공간 회귀의 확장](lessons/27-spatial-regression-extensions.md) | ◐ | 초안 |
| **7부** | **공간 이질성** | | |
| 28 | [공간 비정상성](lessons/28-spatial-nonstationarity.md) | ◐ | 초안 |
| 29 | [지리가중회귀(GWR)](lessons/29-gwr.md) | ● | 초안 |
| 30 | [MGWR과 해석](lessons/30-mgwr.md) | ● | 초안 |
| **8부** | **영역화** | | |
| 31 | [군집 분석 기초](lessons/31-clustering-basics.md) | ● | 초안 |
| 32 | [공간 제약 군집화](lessons/32-spatially-constrained-clustering.md) | ◐ | 초안 |
| **9부** | **시공간** | | |
| 33 | [시공간 자료의 구조](lessons/33-spatiotemporal-data.md) | ● | 초안 |
| 34 | [시공간 탐색](lessons/34-spatiotemporal-exploration.md) | ◐ | 초안 |
| 35 | [시공간 모형 개요](lessons/35-spatiotemporal-models.md) | ○ | 초안 |
| **10부** | **베이지안 공간 모형** | | |
| 36 | 베이지안 사고와 계층 모형 | ◐ | |
| 37 | 질병 지도와 CAR 모형 | ○ | |
| **11부** | **공간 데이터 과학** | | |
| 38 | 공간 표본 설계 | ○ | |
| 39 | 공간 교차검증과 머신러닝 | ○ | |
| 40 | 격자·래스터 자료와 공간통계 | ◐ | |
| **12부** | **연구와 보고** | | |
| 41 | 공간 분석 연구 설계 | ● | |
| 42 | 쓰고 읽기 | ● | |
| **부록** | | | |
| A | 방법 선택 지도 | | |
| B | 수학 준비 | | |
| C | 기호·수식표 | | |
| D | 용어 대역표 | | |
| E | 도구별 차이와 결과 재현 | | |
| F | 더 읽을거리 | | |
| G | 예제 자료 | | |

## 폴더 구성

```
book/
├── README.md        이 파일 (표지·목차)
├── lessons/         강별 원본 (md)
├── fig/             그림 (SVG)
├── fig-src/         그림과 본문 수치를 만드는 스크립트
├── data/            예제 자료와 생성 스크립트
├── html/            md에서 자동으로 만든 HTML (직접 고치지 않음)
└── tools/           HTML 빌드, 점검 스크립트
```

## 오류 신고

틀린 내용이나 깨진 수식·그림을 발견하면 [이슈](https://github.com/SeaViewer91/GeoStat/issues)로 알려 주면 반영함.

## 라이선스

본문과 그림은 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ko), 스크립트는 저장소의 MIT 라이선스를 따름.
