"""41강 그림과 본문 수치.

- 41-spec.svg   : 명세 곡선(다중 우주 분석). 출동률과 지표온도의 관계를 종속변수(원비율·EB)·공변량·모형·가중치를 바꿔 가며 54번 추정
- 41-robust.svg : 핫스폿의 강건성. EB 비율 LISA의 High-High를 가중치 4가지 × 보정 2가지로 구한 횟수, 순열 난수 시드 20가지로 유의 판정이 바뀌는 동

회귀·가중치·국지 통계는 GeoStat 엔진 함수로 계산해 앱과 같은 수치를 냄(앱의 순열 시드 123456789).

실행 (GeoStat 엔진 환경에서, 2분 안팎):
    cd engine && uv run python ../book/fig-src/41.py
"""
import itertools
import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import coefs, fit, load_dong, summ  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import esda_ops  # noqa: E402
from geostat_engine.analysis import weights as gw  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
SEED = 123456789
WSPEC = {"퀸": {"type": "queen"}, "퀸 2차": {"type": "queen", "order": 2, "include_lower": True}, "6-최근접": {"type": "knn", "k": 6}, "거리 3 km": {"type": "distance", "threshold": 3000}}
XSETS = {"온도": ["온도편차"], "온도+고령": ["온도편차", "고령비율"], "온도+고령+밀도": ["온도편차", "고령비율", "로그밀도c"]}
YS = {"원비율": "출동률", "EB": "R_EB"}
MODELS = {"OLS": "ols", "공간시차": "lag", "공간오차": "error"}


def load():
    d = load_dong()
    from esda.smoothing import Empirical_Bayes
    d["R_EB"] = Empirical_Bayes(d["PT_CNT"].to_numpy(float), d["인구"].to_numpy(float)).r.ravel() * 1e4
    Ws = {}
    for k, spec in WSPEC.items():
        W, _ = gw.build(d, spec)
        W.transform = "r"
        Ws[k] = W
        print(f"[가중치] {k}: 평균 이웃 수 {W.mean_neighbors:.2f}, 섬 {len(W.islands)}개")
    return d, Ws


# ---------------------------------------------------------------- 손계산: 빠진 변수 치우침
def hand(d):
    def ols(y, X):
        X = np.c_[np.ones(len(y)), X]
        return np.linalg.lstsq(X, y, rcond=None)[0]
    y = d["출동률"].to_numpy()
    t, a = d["온도편차"].to_numpy(), d["고령비율"].to_numpy()
    bs = ols(y, t)
    bl = ols(y, np.c_[t, a])
    dl = ols(a, t)
    print("[손계산] 빠진 변수 치우침: 출동률 ~ 온도편차 (짧은 식) 대 출동률 ~ 온도편차 + 고령비율 (긴 식)")
    print(f"  짧은 식 온도 계수 {bs[1]:.4f}; 긴 식 온도 {bl[1]:.4f}, 고령 {bl[2]:.4f}; 고령비율 ~ 온도편차의 기울기 δ {dl[1]:.4f}")
    print(f"  긴 식 온도 + 고령 × δ = {bl[1]:.4f} + {bl[2]:.4f} × {dl[1]:.4f} = {bl[1] + bl[2] * dl[1]:.4f} (짧은 식과 같음)")
    print(f"  온도편차와 고령비율의 상관 {np.corrcoef(t, a)[0, 1]:.4f}")
    print(f"  명세 수: 종속변수 2 × 공변량 3 × (OLS 1 + 공간시차 4 + 공간오차 4) = {2 * 3 * 9}")


# ---------------------------------------------------------------- 1. 명세 곡선
def multiverse(d, Ws):
    rows = []
    for (yk, yv), (xk, xv), (mk, mv) in itertools.product(YS.items(), XSETS.items(), MODELS.items()):
        wlist = [None] if mv == "ols" else list(Ws)
        for wk in wlist:
            rep, _ = fit(d, mv, yv, xv, Ws[wk] if wk else Ws["퀸"])
            c = coefs(rep)["온도편차"]
            s = summ(rep)
            tot = None
            if mv == "lag":
                tot = [r for r in rep["impacts"]["rows"] if r["name"] == "온도편차"][0]["total"]
            sp = s.get("ρ (공간시차 계수)", s.get("λ (공간오차 계수)"))
            rows.append(dict(y=yk, x=xk, model=mk, w=wk or "-", b=c["coef"], se=c["se"], p=c["p"], total=tot, sp=sp, aic=s.get("AIC")))
    df = pd.DataFrame(rows)
    df["est"] = np.where(df["total"].notna(), df["total"], df["b"])
    df = df.sort_values("est").reset_index(drop=True)
    print(f"[1] 명세 {len(df)}개. 온도편차 효과(공간시차는 총 효과): 범위 {df['est'].min():.3f}~{df['est'].max():.3f}, 중앙값 {df['est'].median():.3f}")
    print(f"  p < 0.05인 명세 {int((df['p'] < 0.05).sum())}개, 최대 p {df['p'].max():.2e}")
    for k in ("y", "x", "model", "w"):
        g = df.groupby(k)["est"].agg(["min", "median", "max", "count"])
        print(f"  {k}별: " + "; ".join(f"{i} {r['median']:.3f} ({r['min']:.3f}~{r['max']:.3f}, {int(r['count'])})" for i, r in g.iterrows()))
    sub = df[df["model"] != "OLS"]
    print(f"  공간 모수 범위 {sub['sp'].min():.3f}~{sub['sp'].max():.3f}")
    for _, r in df.iloc[[0, len(df) // 2, -1]].iterrows():
        print(f"  예: {r['y']} · {r['x']} · {r['model']} · {r['w']}: {r['est']:.3f} (계수 {r['b']:.3f}, SE {r['se']:.3f}, p {r['p']:.2e}, 공간 모수 {r['sp']})")
    base = df[(df["y"] == "원비율") & (df["x"] == "온도+고령") & (df["model"] == "OLS")].iloc[0]
    print(f"  8강의 기준 명세(원비율·온도+고령·OLS): {base['b']:.4f} (SE {base['se']:.4f})")
    return df


# ---------------------------------------------------------------- 2. 핫스폿 강건성
def hotspots(d, Ws):
    x = d["PT_CNT"].astype(float).rename("PT_CNT")
    base = d["인구"].astype(float).rename("인구")
    cnt = np.zeros(len(d), int)
    specs = []
    for wk, corr in itertools.product(Ws, ("none", "fdr")):
        r = esda_ops.local("lisa_eb", x, Ws[wk], 999, SEED, 0.05, corr, y=base)
        hh = r.cluster == 1
        cnt += hh
        specs.append((wk, corr, int(hh.sum()), int((r.cluster > 0).sum())))
    print("[2] EB 비율 LISA의 High-High (가중치 × 보정):")
    for s in specs:
        print(f"  {s[0]} · {s[1]}: HH {s[2]}개, 유의 전체 {s[3]}개")
    nm = d["동이름"].to_numpy()
    for k in range(8, 0, -1):
        if (cnt == k).any():
            print(f"  {k}/8 명세에서 HH: {sorted(nm[cnt == k].tolist())}")
    # 시드 민감도 (퀸, 보정 없음)
    sig = np.zeros((20, len(d)), bool)
    for i, sd in enumerate(range(1, 21)):
        r = esda_ops.local("lisa_eb", x, Ws["퀸"], 999, sd, 0.05, "none", y=base)
        sig[i] = r.cluster > 0
    k = sig.sum(0)
    flip = (k > 0) & (k < 20)
    print(f"[3] 시드 20가지(퀸, 보정 없음, 999회): 늘 유의 {int((k == 20).sum())}개, 때에 따라 유의 {int(flip.sum())}개, 유의 개수 범위 {sig.sum(1).min()}~{sig.sum(1).max()}")
    print(f"  때에 따라 유의한 동: " + ", ".join(f"{nm[i]}({k[i]}/20)" for i in np.where(flip)[0]))
    r0 = esda_ops.local("lisa_eb", x, Ws["퀸"], 999, SEED, 0.05, "none", y=base)
    print(f"  앱 시드 {SEED}: 유의 {int((r0.cluster > 0).sum())}개")
    r9 = [esda_ops.local("lisa_eb", x, Ws["퀸"], 9999, sd, 0.05, "none", y=base) for sd in range(1, 6)]
    s9 = np.array([r.cluster > 0 for r in r9])
    print(f"  순열 9,999회·시드 5가지: 유의 개수 {s9.sum(1).tolist()}, 때에 따라 유의 {int(((s9.sum(0) > 0) & (s9.sum(0) < 5)).sum())}개")
    return cnt, k


# ---------------------------------------------------------------- 그림
def fig_spec(df):
    W_, H = 720, 412
    n = len(df)
    svg = Svg(W_, H, f"명세 곡선. 출동률과 지표온도의 관계를 종속변수(원비율·EB 평활), 공변량(3가지), 모형(OLS·공간시차·공간오차), 공간가중치(4가지)를 바꿔 {n}번 추정해 효과 크기 순으로 늘어놓음. "
                     f"위: 온도편차 1℃당 효과와 95% 신뢰구간(공간시차는 총 효과, 구간은 계수의 것). 효과는 {df['est'].min():.2f}~{df['est'].max():.2f}로 모두 양수이고 모든 명세에서 유의함. "
                     f"아래: 각 명세의 선택. 효과의 크기를 가르는 것은 종속변수(EB 평활이면 작음)와 공변량이고, 모형과 가중치는 거의 영향이 없음")
    x0, w = 160, 540
    ax = Axes(svg, x0, 30, w, 170, (-0.5, n - 0.5), (0, max(df["b"] + 1.96 * df["se"]) * 1.05))
    cls = {"OLS": "f-mu", "공간시차": "f-bd", "공간오차": "f-ac"}
    scl = {"OLS": "s-mu", "공간시차": "s-bd", "공간오차": "s-ac"}
    for i, r in df.iterrows():
        X = float(ax.X(i))
        svg.line(X, float(ax.Y(r["b"] - 1.96 * r["se"])), X, float(ax.Y(r["b"] + 1.96 * r["se"])), cls=scl[r["model"]], width=1)
        svg.circle(X, float(ax.Y(r["est"])), 2.6, cls=cls[r["model"]], width=0)
    ax.yaxis(label="온도편차 1℃당 효과 (1만 명당)")
    svg.line(x0, float(ax.Y(0)), x0 + w, float(ax.Y(0)), cls="s-mu", width=0.6)
    rows = [("y", "원비율"), ("y", "EB"), ("x", "온도"), ("x", "온도+고령"), ("x", "온도+고령+밀도"), ("model", "OLS"), ("model", "공간시차"), ("model", "공간오차"),
            ("w", "퀸"), ("w", "퀸 2차"), ("w", "6-최근접"), ("w", "거리 3 km")]
    groups = {"y": "종속변수", "x": "공변량", "model": "모형", "w": "가중치"}
    y = 222
    last = None
    for key, val in rows:
        if key != last:
            y += 6
            svg.text(8, y + 8, groups[key], size=10, anchor="start", cls="f-mu", weight="600")
            last = key
        svg.text(x0 - 6, y + 8, val, size=10, anchor="end")
        for i, r in df.iterrows():
            on = r[key] == val
            svg.circle(float(ax.X(i)), y + 4, 2.2 if on else 1.0, cls="f-fg" if on else "f-mu", width=0)
        y += 13
    xl = 430
    for m in ("OLS", "공간시차", "공간오차"):
        svg.circle(xl, 14, 4, cls=cls[m], width=0)
        svg.text(xl + 8, 18, m, size=11, anchor="start")
        xl += 90
    svg.save(os.path.join(OUT, "41-spec.svg"))


def fig_robust(d, cnt, k):
    W_, H = 720, 300
    svg = Svg(W_, H, f"핫스폿의 강건성. 왼쪽: EB 비율 LISA의 High-High를 가중치 4가지(퀸, 퀸 2차, 6-최근접, 거리 3 km) × 보정 2가지(없음, FDR)로 구했을 때 HH로 나온 횟수(0~8). "
                     f"마루구 원도심의 다섯 동은 8번 모두 HH이고, 명세에 따라 1~6번 나오는 동들이 둘레에 있음. 오른쪽: 순열의 난수 시드만 20가지로 바꿨을 때(퀸, 보정 없음) "
                     f"유의하게 나온 횟수. 경계에 있는 {int(((k > 0) & (k < 20)).sum())}개 동은 시드에 따라 유의 여부가 바뀜")
    mw = 320
    seq = ["#f0f0f0", "#fff1e0", "#fdc98f", "#f98f45", "#d9530f", "#8c2d04"]
    for p, (vals, mx, title, labs) in enumerate(((cnt, 8, "HH로 나온 명세 수 (8가지 중)", ["0", "1~2", "3~4", "5~6", "7", "8"]),
                                                (k, 20, "유의하게 나온 시드 수 (20가지 중)", ["0", "1~5", "6~10", "11~15", "16~19", "20"]))):
        fr = MapFrame(d.total_bounds, 25 + p * (mw + 40), 36, mw)
        if p == 0:
            b = np.select([vals == 0, vals <= 2, vals <= 4, vals <= 6, vals == 7], [0, 1, 2, 3, 4], 5)
        else:
            b = np.select([vals == 0, vals <= 5, vals <= 10, vals <= 15, vals <= 19], [0, 1, 2, 3, 4], 5)
        draw(svg, fr, d.geometry, None, width=0.3, stroke="s-bg", fills=[seq[i] for i in b])
        outline(svg, fr, d.union_all(), cls="s-fg", width=0.8)
        svg.text(fr.x + mw / 2, 24, title, size=12, weight="600")
        x = fr.x
        for c, lab in zip(seq, labs):
            svg.rect(x, 36 + fr.h + 12, 12, 12, cls="s-mu", width=0.5, fill=c)
            svg.text(x + 16, 36 + fr.h + 22, lab, size=10, anchor="start")
            x += 16 + len(lab) * 7 + 12
    svg.save(os.path.join(OUT, "41-robust.svg"))


if __name__ == "__main__":
    d, Ws = load()
    hand(d)
    df = multiverse(d, Ws)
    cnt, k = hotspots(d, Ws)
    fig_spec(df)
    fig_robust(d, cnt, k)
