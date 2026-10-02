"""34강 그림과 본문 수치.

- 34-moran.svg : 연도별 전역 Moran's I (원비율 출동률, EB Moran)
- 34-lisa.svg : 기간별 LISA. High-High였던 해의 수와 Low-Low였던 해의 수 지도
- 34-markov.svg : 공간 마르코프. 이웃(공간 시차)의 계급별로 나눈 출동률 계급 전이 확률
- 34-diff.svg : 차분 LISA. 2016→2025 한 해끼리와, 2016~2018 평균→2023~2025 평균
- 34-ehsa.svg : 떠오르는 핫스팟 분석(Gi* z의 추세)으로 나눈 동의 유형

자료는 book/data/hanbit_dong_panel.gpkg. 앱 해 보기 수치는 GeoStat 엔진(timeseries.pivot_long, esda_ops.moran/local,
timeseries.transitions)으로 계산함 (앱과 같은 계산, 순열 999회, 시드 123456789).

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/34.py
"""
import importlib
import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import queen  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import esda_ops as eo  # noqa: E402
from geostat_engine.analysis import fields  # noqa: E402
from geostat_engine.analysis import timeseries as ts  # noqa: E402

warnings.filterwarnings("ignore")
m33 = importlib.import_module("33")
OUT = os.path.join(HERE, "..", "fig")
YEARS = m33.YEARS
SEED = 123456789
QUAD = ["HH", "LH", "LL", "HL"]


def load():
    p = m33.load()
    wide, groups, _ = ts.pivot_long(p, "동코드", "연도", ["인구", "고령인구", "출동건수", "출동률"])
    names = p[p["연도"] == 2025].set_index("동코드").loc[wide["동코드"], ["구", "동이름"]].reset_index(drop=True)
    wide["구"], wide["동이름"] = names["구"], names["동이름"]
    return p, wide, queen(wide)


def R(wide):
    return wide[[f"출동률_{y}" for y in YEARS]].to_numpy()


# ---------------------------------------------------------------- 손계산
def hand():
    print("[손계산 1] LISA 사분면 전이: 동 하나의 5년 사분면 HH, HH, LH, HH, HH")
    seq = ["HH", "HH", "LH", "HH", "HH"]
    pairs = list(zip(seq[:-1], seq[1:]))
    print(f"  전이 {pairs}: HH→HH {pairs.count(('HH', 'HH'))}, HH→LH {pairs.count(('HH', 'LH'))}, LH→HH {pairs.count(('LH', 'HH'))}")
    print("[손계산 2] 맨-켄달 추세: Gi* z = 0.5, 1.2, 0.9, 2.1, 2.4")
    z = np.array([0.5, 1.2, 0.9, 2.1, 2.4])
    s = sum(np.sign(z[j] - z[i]) for i in range(len(z)) for j in range(i + 1, len(z)))
    n = len(z)
    var = n * (n - 1) * (2 * n + 5) / 18
    zz = (s - np.sign(s)) / np.sqrt(var)
    print(f"  S = {s:.0f} (쌍 {n * (n - 1) // 2}개), Var(S) = {var:.2f}, z = {zz:.3f}, p = {2 * stats.norm.sf(abs(zz)):.3f}")


# ---------------------------------------------------------------- 1. Moran 추이
def moran_trend(wide, W):
    rows = []
    for y in YEARS:
        r = eo.moran(wide[f"출동률_{y}"], W, 999, SEED)
        e = eo.moran(wide[f"출동건수_{y}"], W, 999, SEED, rate_base=wide[f"인구_{y}"])
        rows.append(dict(연도=y, I=r.I, z=r.z_sim, p=r.p_sim, 평균=wide[f"출동률_{y}"].mean(), EB_I=e.I, EB_p=e.p_sim))
    df = pd.DataFrame(rows)
    print("[1] 연도별 전역 Moran's I (출동률 원비율, 퀸, 순열 999) 와 EB Moran's I")
    print(df.round(4).to_string(index=False))
    print("  셋째 자리: I " + ", ".join(f"{v:.3f}" for v in df["I"]) + " | p " + ", ".join(f"{v:.3f}" for v in df["p"]))
    print("  셋째 자리: EB I " + ", ".join(f"{v:.3f}" for v in df["EB_I"]) + " | p " + ", ".join(f"{v:.3f}" for v in df["EB_p"]))
    print(f"  원비율 p ≤ 0.05인 해 {(df['p'] <= 0.05).sum()}개, EB p ≤ 0.05인 해 {(df['EB_p'] <= 0.05).sum()}개")
    pool = wide[[f"출동건수_{y}" for y in YEARS]].sum(1) / wide[[f"인구_{y}" for y in YEARS]].sum(1) * 10000
    r = eo.moran(pool, W, 999, SEED)
    e = eo.moran(wide[[f"출동건수_{y}" for y in YEARS]].sum(1), W, 999, SEED, rate_base=wide[[f"인구_{y}" for y in YEARS]].sum(1))
    print(f"  열 해를 합친 출동률: Moran's I {r.I:.4f} (p {r.p_sim:.3f}), EB Moran's I {e.I:.4f} (p {e.p_sim:.3f})")
    return df


# ---------------------------------------------------------------- 2. 기간별 LISA
def lisa_time(wide, W):
    cl = []
    for y in YEARS:
        L = eo.local("lisa", wide[f"출동률_{y}"], W, 999, SEED, 0.05, "none")
        cl.append(np.asarray(L.cluster))
    rep = ts.transitions(cl, [str(y) for y in YEARS])
    print("[2] 기간별 LISA (α 0.05, 보정 없음)")
    cnt = pd.DataFrame(rep["counts"], index=YEARS, columns=rep["categories"])
    print(cnt.to_string())
    M = pd.DataFrame(rep["matrix"], index=rep["categories"], columns=rep["categories"])
    print("  전이표(앞 → 뒤, 9번의 인접 연도 합)\n" + M.to_string())
    print(f"  군집이 한 번 이상 바뀐 동 {rep['n_changed']}개, 모든 기간 같은 유의 군집 {rep['n_stable_cluster']}개, 한 번도 바뀌지 않은 동 {150 - rep['n_changed']}개")
    C = np.vstack(cl)
    hh, ll = (C == 1).sum(0), (C == 2).sum(0)
    top = np.argsort(-hh)[:8]
    print("  High-High 해가 많은 동: " + ", ".join(f"{wide['동이름'][i]} {hh[i]}" for i in top))
    print("  다솜18~24동 High-High 해: " + ", ".join(f"{wide['동이름'][i]} {hh[i]}" for i in range(len(wide)) if wide['동이름'][i] in [f"다솜{k}동" for k in range(18, 25)]))
    print("  누리6·13·14·16·17·26동 High-High 해: " + ", ".join(f"{wide['동이름'][i]} {hh[i]}" for i in range(len(wide)) if wide['동이름'][i] in [f"누리{k}동" for k in (6, 13, 14, 16, 17, 26)]))
    print(f"  High-High가 5년 이상 {int((hh >= 5).sum())}개 동, Low-Low가 5년 이상 {int((ll >= 5).sum())}개 동, 한 번이라도 High-High {int((hh > 0).sum())}개 동")
    hhrow = M.loc["High-High"]
    print(f"  High-High 다음 해: 그대로 {hhrow['High-High']}, 유의하지 않음 {hhrow['유의하지 않음']}, Low-High {hhrow['Low-High']} (High-High에서 출발 {hhrow.sum()}번, 유지 {hhrow['High-High'] / hhrow.sum() * 100:.1f}%)")
    # FDR
    clf = [np.asarray(eo.local("lisa", wide[f"출동률_{y}"], W, 999, SEED, 0.05, "fdr").cluster) for y in YEARS]
    print(f"  FDR 보정: 해마다 유의한 동 수 {[int((c != 0).sum()) for c in clf]}")
    return C, rep


# ---------------------------------------------------------------- 3. LISA 마르코프와 공간 마르코프
def quadrants(Rm, W):
    Wd = W.full()[0]
    Wd = Wd / Wd.sum(1, keepdims=True)
    Z = (Rm - Rm.mean(0)) / Rm.std(0)
    L = Wd @ Z
    q = np.where(Z >= 0, np.where(L >= 0, 0, 3), np.where(L >= 0, 1, 2))  # 0 HH, 1 LH, 2 LL, 3 HL
    return q, Z, L


def lisa_markov(Rm, W):
    q, _, _ = quadrants(Rm, W)
    T = np.zeros((4, 4), int)
    for t in range(q.shape[1] - 1):
        np.add.at(T, (q[:, t], q[:, t + 1]), 1)
    P = T / T.sum(1, keepdims=True)
    print("[3] LISA 마르코프 (Moran 산점도 사분면, 유의성과 관계없이)")
    print(pd.DataFrame(T, index=QUAD, columns=QUAD).to_string())
    print(pd.DataFrame(P, index=QUAD, columns=QUAD).round(3).to_string())
    vals, vecs = np.linalg.eig(P.T)
    st = np.real(vecs[:, np.argmin(np.abs(vals - 1))])
    st = st / st.sum()
    print(f"  유지 확률 {np.round(np.diag(P), 3).tolist()}, 정상 분포 {np.round(st, 3).tolist()}, 처음 해 분포 {np.round(np.bincount(q[:, 0], minlength=4) / len(q), 3).tolist()}")
    # 같은 이동 유형(둘 다 그대로, 자기만, 이웃만, 둘 다)
    own = (q[:, :-1] // 1)
    hi_own = np.isin(q, [0, 3])
    hi_lag = np.isin(q, [0, 1])
    so, sl = hi_own[:, 1:] != hi_own[:, :-1], hi_lag[:, 1:] != hi_lag[:, :-1]
    print(f"  이동 유형: 둘 다 그대로 {np.mean(~so & ~sl) * 100:.1f}%, 자기만 바뀜 {np.mean(so & ~sl) * 100:.1f}%, 이웃만 바뀜 {np.mean(~so & sl) * 100:.1f}%, 둘 다 바뀜 {np.mean(so & sl) * 100:.1f}%")
    del own
    return T, P


def spatial_markov(Rm, W, k=3):
    Wd = W.full()[0]
    Wd = Wd / Wd.sum(1, keepdims=True)
    br = np.quantile(Rm, np.linspace(0, 1, k + 1)[1:-1])
    cls = np.digitize(Rm, br)
    lag = Wd @ Rm
    lbr = np.quantile(lag, np.linspace(0, 1, k + 1)[1:-1])
    lcls = np.digitize(lag, lbr)
    T = np.zeros((k, k, k), int)  # 이웃 계급, 앞 계급, 뒤 계급
    for t in range(Rm.shape[1] - 1):
        np.add.at(T, (lcls[:, t], cls[:, t], cls[:, t + 1]), 1)
    Tall = T.sum(0)
    P = T / np.maximum(T.sum(2, keepdims=True), 1)
    Pall = Tall / Tall.sum(1, keepdims=True)
    names = ["낮음", "중간", "높음"]
    print(f"[4] 공간 마르코프 (출동률을 열 해 전체의 3분위 {np.round(br, 2).tolist()}로, 이웃 평균을 3분위 {np.round(lbr, 2).tolist()}로)")
    print("  이웃을 나누지 않은 전이 확률\n" + pd.DataFrame(Pall, index=names, columns=names).round(3).to_string())
    for g in range(k):
        print(f"  이웃 {names[g]} (전이 {T[g].sum()}번)\n" + pd.DataFrame(P[g], index=names, columns=names).round(3).to_string())
    # 동질성 우도비 검정 (Bickenbach & Bode 2003)
    lr = 0.0
    dof = 0
    for g in range(k):
        for i in range(k):
            ni = T[g, i].sum()
            if ni == 0:
                continue
            for j in range(k):
                if T[g, i, j] > 0:
                    lr += 2 * T[g, i, j] * np.log(P[g, i, j] / Pall[i, j])
            dof += (np.sum(Pall[i] > 0) - 1)
    dof -= (k - 1) * k  # 전체 행렬의 모수만큼 뺌
    print(f"  동질성 우도비 검정: LR {lr:.2f}, 자유도 {dof}, p {stats.chi2.sf(lr, dof):.4f}")
    dg = np.concatenate([np.diag(Pall)] + [np.diag(P[g]) for g in range(k)])
    print(f"  대각선 확률 범위 {dg.min():.3f}~{dg.max():.3f}")
    return P, Pall, T, br, lbr, stats.chi2.sf(lr, dof)


# ---------------------------------------------------------------- 4. 차분 LISA
def diff_lisa(wide, W):
    out = {}
    d1 = wide["출동률_2025"] - wide["출동률_2016"]
    a = wide[[f"출동률_{y}" for y in (2016, 2017, 2018)]].mean(1)
    b = wide[[f"출동률_{y}" for y in (2023, 2024, 2025)]].mean(1)
    s = wide.copy()
    s["전기"] = fields.evaluate(s, "(`출동률_2016` + `출동률_2017` + `출동률_2018`) / 3")
    s["후기"] = fields.evaluate(s, "(`출동률_2023` + `출동률_2024` + `출동률_2025`) / 3")
    d3 = s["후기"] - s["전기"]
    assert np.allclose(d3, b - a)
    print("[5] 차분 LISA")
    for name, v in (("2016→2025", d1), ("전기(2016~18)→후기(2023~25)", d3)):
        mi = eo.moran(v, W, 999, SEED)
        L = eo.local("lisa", v, W, 999, SEED, 0.05, "none")
        c = np.asarray(L.cluster)
        out[name] = c
        hh = [wide["동이름"][i] for i in np.where(c == 1)[0]]
        names = ["유의하지 않음", "High-High", "Low-Low", "Low-High", "High-Low"]
        ds = {wide["동이름"][i]: names[c[i]] for i in range(len(c)) if wide["동이름"][i] in [f"다솜{k}동" for k in range(18, 25)]}
        print(f"    다솜18~24동: {ds}")
        print(f"  {name}: 차분 Moran's I {mi.I:.4f} (p {mi.p_sim:.3f}), 군집 수 {np.bincount(c, minlength=6)[:5].tolist()}, High-High {hh}")
        print(f"    변화량 범위 {v.min():.2f}~{v.max():.2f}, 평균 {v.mean():.3f}")
    return out, d1, d3


# ---------------------------------------------------------------- 5. 떠오르는 핫스팟 분석
def mann_kendall(x):
    n = len(x)
    s = sum(np.sign(x[j] - x[i]) for i in range(n) for j in range(i + 1, n))
    var = n * (n - 1) * (2 * n + 5) / 18
    z = (s - np.sign(s)) / np.sqrt(var) if s != 0 else 0.0
    return s, z, 2 * stats.norm.sf(abs(z))


def ehsa(wide, W, alpha=0.05):
    """ESRI 떠오르는 핫스팟 분석의 핫스팟 쪽 규칙을 단순화해 구현 (Gi*: 자기 포함 이진 가중치, 정규 근사 z)"""
    from esda.getisord import G_Local
    Rm = R(wide)
    Zg = np.column_stack([G_Local(Rm[:, k], W, star=True, transform="B", permutations=0).Zs for k in range(len(YEARS))])
    hot = (Zg > stats.norm.ppf(1 - alpha / 2))
    n = len(YEARS)
    labels = []
    for i in range(len(wide)):
        h = hot[i]
        _, mkz, mkp = mann_kendall(Zg[i])
        up, down = mkp <= alpha and mkz > 0, mkp <= alpha and mkz < 0
        frac = h.mean()
        if not h.any():
            labels.append("핫스팟 아님")
        elif h[-1] and h[:-1].sum() == 0:
            labels.append("새로운")
        elif h[-1] and frac >= 0.9 and up:
            labels.append("강해지는")
        elif h[-1] and frac >= 0.9 and down:
            labels.append("약해지는")
        elif h[-1] and frac >= 0.9:
            labels.append("지속")
        elif h[-1]:
            run = 0
            for v in h[::-1]:
                if not v:
                    break
                run += 1
            labels.append("연속" if h[:n - run].sum() == 0 else "산발")
        elif frac >= 0.9:
            labels.append("과거")
        else:
            labels.append("핫스팟 아님")  # 마지막 해가 핫스팟이 아니고 90% 미만: ESRI의 '패턴 없음'(산발은 마지막 해가 핫스팟이어야 함)
    lab = pd.Series(labels)
    print("[6] 떠오르는 핫스팟 분석 (Gi* z, 맨-켄달 추세, α 0.05)")
    print("  " + ", ".join(f"{k} {v}" for k, v in lab.value_counts().items()))
    for k in ("강해지는", "지속", "새로운", "연속", "산발", "과거"):
        idx = np.where(lab == k)[0]
        if len(idx):
            print(f"   {k}: " + ", ".join(f"{wide['동이름'][i]}({int(hot[i].sum())}해, 마지막 해 {'핫' if hot[i, -1] else '아님'}, MK z {mann_kendall(Zg[i])[1]:.2f})" for i in idx[:14]))
    mk = [mann_kendall(Zg[i]) for i in range(len(wide))]
    up = np.array([p <= alpha and z > 0 for s, z, p in mk])
    dn = np.array([p <= alpha and z < 0 for s, z, p in mk])
    print(f"  Gi* z가 유의하게 커지는 동(MK p ≤ 0.05) {up.sum()}개: " + ", ".join(wide["동이름"][i] for i in np.where(up)[0]))
    print(f"  작아지는 동 {dn.sum()}개: " + ", ".join(wide["동이름"][i] for i in np.where(dn)[0]))
    return lab, Zg, hot, up


# ---------------------------------------------------------------- 그림
def fig_moran(df):
    W_, H = 720, 260
    svg = Svg(W_, H, "연도별 전역 Moran's I(퀸 인접, 순열 999회). 파랑은 원비율 출동률, 주황은 인구를 고려한 EB Moran's I. 속이 찬 점은 유사 p ≤ 0.05. "
                     "원비율의 I는 작은 수의 흔들림 때문에 해마다 −0.03~0.12로 크게 오르내리고 열 해 가운데 다섯 해만 유의하지만, EB Moran's I는 여덟 해에서 유의함")
    ax = Axes(svg, 70, 36, 600, 180, (2015.5, 2025.5), (-0.05, 0.2))
    for key, pk, cls, fcls in (("I", "p", "s-ac", "f-ac"), ("EB_I", "EB_p", "s-bd", "f-bd")):
        ax.curve(df["연도"].to_numpy(), df[key].to_numpy(), cls=cls, width=2)
        for _, r in df.iterrows():
            filled = r[pk] <= 0.05
            svg.circle(float(ax.X(r["연도"])), float(ax.Y(r[key])), 4.5, cls=f"{fcls if filled else 'f-bg'} {cls}", width=1.6)
    ax.curve(np.array([2015.5, 2025.5]), np.array([0, 0]), cls="s-mu", width=1, dash="3 3")
    ax.xaxis(ticks=YEARS, fmt=lambda t: f"{int(t)}")
    ax.yaxis(ticks=[0, 0.05, 0.1, 0.15, 0.2], label="Moran's I")
    x = 230
    for cls, lab in (("s-ac", "원비율 출동률"), ("s-bd", "EB Moran (건수 ÷ 인구)")):
        svg.line(x, H - 14, x + 24, H - 14, cls=cls, width=2)
        svg.text(x + 30, H - 10, lab, size=10, anchor="start")
        x += 190
    svg.save(os.path.join(OUT, "34-moran.svg"))


def fig_lisa(wide, C):
    W_, H = 720, 280
    hh, ll = (C == 1).sum(0), (C == 2).sum(0)
    svg = Svg(W_, H, "기간별 LISA(원비율 출동률, α 0.05, 보정 없음)를 열 해 동안 모은 것. 왼쪽: High-High로 나온 해의 수. 다솜구 동쪽 해안과 마루구 남쪽의 몇 동은 대부분의 해에 High-High임. "
                     "오른쪽: Low-Low로 나온 해의 수. 한 해만 나온 동이 많아, 한 해의 LISA 지도는 우연한 무늬를 많이 담고 있음")
    mw = 310
    bins = [1, 3, 5, 8]
    for k, (v, title) in enumerate(((hh, "High-High였던 해의 수"), (ll, "Low-Low였던 해의 수"))):
        cls = ["f-sf" if t == 0 else f"q{int(np.digitize(t, bins))}" for t in v]
        fr = MapFrame(wide.total_bounds, 30 + k * (mw + 40), 36, mw)
        draw(svg, fr, wide.geometry, cls, width=0.3, stroke="s-mu")
        outline(svg, fr, wide.union_all(), cls="s-fg", width=0.8)
        svg.text(fr.x + mw / 2, 24, title, size=12, weight="600")
    x = 170
    for k, lab in enumerate(["0", "1~2", "3~4", "5~7", "8~10"]):
        svg.rect(x, H - 22, 12, 12, cls="s-mu " + ("f-sf" if k == 0 else f"q{k}"), width=0.5)
        svg.text(x + 16, H - 12, lab + "해", size=10, anchor="start")
        x += 74
    svg.save(os.path.join(OUT, "34-lisa.svg"))


def fig_markov(P, Pall, LR_P):
    W_, H = 720, 250
    names = ["낮음", "중간", "높음"]
    svg = Svg(W_, H, f"공간 마르코프. 동의 출동률 계급(열 해 전체의 3분위)이 다음 해에 어떻게 바뀌는지를 이웃 평균의 계급별로 나눈 전이 확률. 칸의 숫자는 앞 해 계급(행)에서 다음 해 계급(열)으로 갈 확률. "
                     f"높은 동이 높게 남을 확률은 이웃이 높을 때 {P[2, 2, 2]:.2f}, 낮을 때 {P[0, 2, 2]:.2f}로 조금 다르지만, 네 행렬이 모두 대각선이 조금 진할 뿐 비슷하고 이 차이는 우연으로 설명됨(동질성 검정 p {LR_P:.2f})")
    mats = [(Pall, "이웃 구분 없음")] + [(P[g], f"이웃 {names[g]}") for g in range(3)]
    cw = 42
    for m, (M, title) in enumerate(mats):
        x0 = 22 + m * 172
        y0 = 60
        svg.text(x0 + 1.5 * cw + 14, 30, title, size=12, weight="600")
        for j, nm in enumerate(names):
            svg.text(x0 + 30 + j * cw + cw / 2, y0 - 6, nm, size=9, cls="f-mu")
            svg.text(x0 + 26, y0 + j * cw + cw / 2 + 4, nm, size=9, anchor="end", cls="f-mu")
        for i in range(3):
            for j in range(3):
                v = M[i, j]
                q = min(4, int(v * 5))
                svg.rect(x0 + 30 + j * cw, y0 + i * cw, cw - 2, cw - 2, cls=f"s-bg q{q}", width=0.5)
                col = "#ffffff" if q >= 3 else "#1c2330"
                svg.add(f'<text x="{x0 + 30 + j * cw + (cw - 2) / 2:.1f}" y="{y0 + i * cw + cw / 2 + 4:.1f}" font-size="11" text-anchor="middle" fill="{col}">{v:.2f}</text>')
    svg.text(360, H - 30, "행: 앞 해의 계급 → 열: 다음 해의 계급", size=10, cls="f-mu")
    svg.save(os.path.join(OUT, "34-markov.svg"))


def fig_diff(wide, out):
    W_, H = 720, 285
    CL = {0: "#eeeeee", 1: "#ff0000", 2: "#0000ff", 3: "#a7adf9", 4: "#f4ada8"}
    keys = list(out)
    svg = Svg(W_, H, "차분 LISA(출동률 변화량, α 0.05). 빨강은 변화량이 크고 이웃도 큰 High-High(함께 늘어난 곳), 파랑은 함께 줄어든 Low-Low, 옅은 색은 이상치. "
                     "왼쪽: 2016년과 2025년 두 해만 비교. 오른쪽: 앞뒤 세 해의 평균(2016~2018 → 2023~2025)을 비교. 두 해의 우연이 덜 섞인 오른쪽에서도 누리구와 마루구 남쪽의 함께 늘어난 곳이 남음")
    mw = 310
    for k, key in enumerate(keys):
        fr = MapFrame(wide.total_bounds, 30 + k * (mw + 40), 36, mw)
        draw(svg, fr, wide.geometry, None, width=0.3, stroke="s-bg", fills=[CL[int(c)] for c in out[key]])
        outline(svg, fr, wide.union_all(), cls="s-fg", width=0.8)
        svg.text(fr.x + mw / 2, 24, key.replace("(2016~18)", "").replace("(2023~25)", "") if k else key, size=12, weight="600")
    x = 150
    for c, lab in ((1, "High-High"), (2, "Low-Low"), (3, "Low-High"), (4, "High-Low"), (0, "유의하지 않음")):
        svg.rect(x, H - 22, 12, 12, cls="s-mu", width=0.5, fill=CL[c])
        svg.text(x + 16, H - 12, lab, size=10, anchor="start")
        x += 34 + len(lab) * 6.5
    svg.save(os.path.join(OUT, "34-diff.svg"))


def fig_ehsa(wide, lab, up):
    W_, H = 720, 300
    cats = ["강해지는", "지속", "연속", "새로운", "산발", "과거", "핫스팟 아님"]  # 차가운 곳(콜드스폿)은 따지지 않음
    col = {"강해지는": "#b2182b", "지속": "#d6604d", "연속": "#f4a582", "새로운": "#fddbc7", "산발": "#e7a9c9", "과거": "#8073ac", "핫스팟 아님": "#eeeeee"}
    cnt = lab.value_counts()
    svg = Svg(W_, H, "떠오르는 핫스팟 분석. 해마다 Gi* 핫스팟 여부(α 0.05)와 Gi* z의 열 해 추세(맨-켄달 검정)로 동을 나눔. "
                     f"다솜구 동쪽 해안에는 거의 모든 해에 핫스팟이던 지속 핫스팟({cnt.get('지속', 0)}개)과, 마지막 해에만 빠진 과거 핫스팟({cnt.get('과거', 0)}개)이 있음. "
                     f"마루구 남쪽에는 몇 해만 나타난 산발 핫스팟과 마지막 해에 처음 나타난 새로운 핫스팟이 모임. 검은 점(Gi* z가 유의하게 커지는 동 {int(up.sum())}개)은 마루구 남쪽과 누리구에 몰려 있음")
    fr = MapFrame(wide.total_bounds, 20, 30, 420)
    draw(svg, fr, wide.geometry, None, width=0.3, stroke="s-bg", fills=[col[v] for v in lab])
    outline(svg, fr, wide.union_all(), cls="s-fg", width=0.8)
    cen = wide.geometry.centroid
    for i in np.where(up)[0]:
        x, y = fr.xy(cen.x[i], cen.y[i])
        svg.circle(x, y, 3.2, cls="s-bg", width=1, fill="#1c2330")
    y = 50
    for c in cats:
        n = int(cnt.get(c, 0))
        svg.rect(470, y - 11, 14, 14, cls="s-mu", width=0.5, fill=col[c])
        svg.text(492, y, f"{c} 핫스팟 ({n}개)" if c != "핫스팟 아님" else f"핫스팟 아님 ({n}개)", size=11, anchor="start")
        y += 26
    svg.circle(477, y - 4, 3.2, cls="s-bg", width=1, fill="#1c2330")
    svg.text(492, y, f"Gi* z 증가 추세 ({int(up.sum())}개)", size=11, anchor="start")
    svg.save(os.path.join(OUT, "34-ehsa.svg"))


if __name__ == "__main__":
    hand()
    p, wide, W = load()
    df = moran_trend(wide, W)
    C, rep = lisa_time(wide, W)
    Rm = R(wide)
    lisa_markov(Rm, W)
    P, Pall, T, br, lbr, lrp = spatial_markov(Rm, W)
    out, d1, d3 = diff_lisa(wide, W)
    lab, Zg, hot, up = ehsa(wide, W)
    fig_moran(df)
    fig_lisa(wide, C)
    fig_markov(P, Pall, lrp)
    fig_diff(wide, out)
    fig_ehsa(wide, lab, up)
