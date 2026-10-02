"""부록 A 그림: 방법 선택 지도 (자료의 꼴 → 질문 → 방법과 강).

- A-map.svg

실행 (아무 Python 3, 이 폴더의 svglib만 씀):
    python3 book/fig-src/A.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from svglib import Svg  # noqa: E402

OUT = os.path.join(HERE, "..", "fig")

TREE = [
    ("면 자료", "구역마다 값 (행정동, 격자)", [
        ("값이 어떤 모양으로 퍼졌나", "단계구분도, 박스 지도", "5"),
        ("비율의 분모가 작은가", "EB 평활, SMR, BYM2", "14·36·37"),
        ("이웃끼리 닮았나 (전체)", "Moran's I, Geary's C", "11"),
        ("어디서 닮았나 (국지)", "LISA, Gi*, EB 비율 LISA", "12~14"),
        ("높은 곳이 몰렸나 (검정)", "공간 스캔 통계", "15"),
        ("설명변수와의 관계는", "OLS → 공간시차·오차", "8·24~27"),
        ("관계가 곳마다 다른가", "체제, GWR, MGWR", "28~30"),
        ("비슷한 곳끼리 묶기", "K-평균, SKATER, Max-p", "31·32"),
    ]),
    ("점 패턴", "사건의 위치 자체", [
        ("어디에 많은가", "방격, 커널 밀도", "16·17"),
        ("무작위보다 몰렸나", "G·F, Ripley K·L, 쌍상관", "18"),
        ("무엇이 강도를 정하나", "비균질 포아송, 군집 과정", "19"),
    ]),
    ("연속 표면", "관측소 값으로 전체 표면", [
        ("가까울수록 얼마나 닮나", "베리오그램", "21"),
        ("관측 안 한 곳의 값은", "크리깅, 회귀 크리깅", "22"),
        ("기준을 넘을 확률은", "조건부 시뮬레이션, 지시자 크리깅", "23"),
    ]),
    ("시공간", "구역 × 시점 패널, 시공간 점", [
        ("어떻게 바뀌어 왔나", "Moran 추이, 기간별 LISA", "33·34"),
        ("효과의 크기는", "고정효과, 공간 패널, 포아송 패널", "35"),
        ("어디서 언제 높았나", "시공간 스캔, 떠오르는 핫스팟", "34·35"),
    ]),
    ("표본·래스터", "조사 설계, 예측 지도, 영상", [
        ("어디를 잴 것인가", "확률 표본, GRTS, 공간 피복", "38"),
        ("예측 지도는 얼마나 맞나", "공간 교차검증, 독립 검증", "39·40"),
        ("픽셀을 어떻게 다루나", "집계, 유효 표본 크기", "40"),
    ]),
]


def main():
    rows = sum(len(t[2]) for t in TREE)
    W_, H = 720, 60 + rows * 26 + len(TREE) * 14
    svg = Svg(W_, H, "방법 선택 지도. 왼쪽에서 자료의 꼴(면 자료, 점 패턴, 연속 표면, 시공간, 표본·래스터)을 고르고, 가운데에서 묻고 싶은 질문을 고르면, "
                     "오른쪽에 쓸 방법과 그 방법을 다룬 강 번호가 있음. 모든 갈래의 앞에는 1~10강의 공통 단계(좌표계, 단위, 분모, 지도, 검정)가 있고, "
                     "뒤에는 41~42강의 연구 설계와 보고가 있음")
    svg.text(16, 22, "공통 앞 단계: 좌표계(2) · 단위와 MAUP(3) · 자료 준비(4) · 지도(5) · 추정과 검정(6~9) · 공간가중치(10)", size=11, anchor="start", cls="f-mu")
    y = 46
    for name, desc, items in TREE:
        h = len(items) * 26
        svg.rect(16, y, 130, h - 6, cls="s-ac f-acs", width=1.2, rx=6)
        svg.text(81, y + h / 2 - 6, name, size=13, weight="600")
        svg.text(81, y + h / 2 + 10, desc, size=9, cls="f-mu")
        for i, (q, m, les) in enumerate(items):
            yy = y + i * 26 + 10
            svg.line(146, y + h / 2 - 3, 170, yy, cls="s-mu", width=0.8)
            svg.rect(170, yy - 10, 230, 20, cls="s-mu f-sf", width=0.6, rx=4)
            svg.text(178, yy + 4, q, size=11, anchor="start")
            svg.line(400, yy, 418, yy, cls="s-mu", width=0.8)
            svg.text(422, yy + 4, m, size=11, anchor="start")
            svg.text(704, yy + 4, f"{les}강", size=11, anchor="end", cls="f-ac", weight="600")
        y += h + 14
    svg.text(16, H - 8, "공통 뒤 단계: 민감도 분석·재현성·인과의 한계(41) · 방법 절 쓰기와 심사 대응(42)", size=11, anchor="start", cls="f-mu")
    svg.save(os.path.join(OUT, "A-map.svg"))
    print(f"질문 {rows}개, 갈래 {len(TREE)}개, 높이 {H}")


if __name__ == "__main__":
    main()
