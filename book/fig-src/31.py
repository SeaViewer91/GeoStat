"""31강 그림과 본문 수치.

- 31-scale.svg : K-평균(k = 4) 군집 지도. 변수 표준화 대 원래 값
- 31-k.svg : 군집 수 k에 따른 군집 간/전체 비와 실루엣 계수 (K-평균, Ward)
- 31-dendro.svg : Ward 계층 군집의 덴드로그램과 k = 4 자르기
- 31-profile.svg : K-평균(k = 4) 군집 지도와 군집 프로필(표준화 평균)

변수는 행정동의 고령비율, 로그밀도 = log(인구 / 면적_km2), 온도편차(8강), 출동률의 EB 평활 R_EB(14강, 1만 명당).
원비율 출동률로 군집한 결과는 비교용으로 계산함.
앱 해 보기 수치는 GeoStat 엔진(cluster.prepare/run)으로 계산함 (앱과 같은 계산, 시드 123456789).

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/31.py
"""
import os
import sys
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import app_num, load_dong, queen  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import cluster as gc  # noqa: E402
from geostat_engine.analysis import fields  # noqa: E402
from geostat_engine.analysis import rates  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
V = ["고령비율", "로그밀도", "온도편차", "R_EB"]
VRAW = ["고령비율", "로그밀도", "온도편차", "출동률"]
CAT = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#999999", "#F0E442"]


def load():
    d = load_dong()
    d["로그밀도"] = fields.evaluate(d, "log(`인구` / `면적_km2`)")
    d["R_EB"] = rates.compute("eb", d["PT_CNT"], d["인구"], multiplier=10000)
    return d, queen(d)


def run(d, W, method, k=4, std=True, variables=V, **kw):
    p = gc.prepare(d, {"method": method, "variables": variables, "n_clusters": k, "standardize": std, "seed": 123456789, **kw}, W)
    out = gc.run(p, lambda *a: None)
    return out["report"], np.asarray(out["columns"]["GRP"])


def zscore(d, variables=V):
    X = d[variables].to_numpy()
    return (X - X.mean(0)) / X.std(0)


# ---------------------------------------------------------------- 손계산
def hand(d):
    print("[손계산 1] 표준화와 거리")
    sd = d[["고령비율", "로그밀도"]].to_numpy().std(0)
    A, B, C = np.array([20, 8.0]), np.array([21, 6.0]), np.array([26, 8.1])
    for nm, s in (("원래 값", np.ones(2)), ("표준화", sd)):
        ab = np.sqrt((((A - B) / s) ** 2).sum())
        ac = np.sqrt((((A - C) / s) ** 2).sum())
        print(f"  {nm}: 나누는 값 {np.round(s, 3).tolist()}, A–B {ab:.3f}, A–C {ac:.3f}")
    sd3 = d[["고령비율", "로그밀도", "R_EB"]].to_numpy().std(0)
    A3, B3, C3 = np.array([20, 8.0, 11]), np.array([21, 6.0, 15]), np.array([26, 8.1, 11.5])
    print(f"  (연습) R_EB 11, 15, 11.5를 더해 표준화(나누는 값 {np.round(sd3, 3).tolist()}): A–B {np.sqrt((((A3 - B3) / sd3) ** 2).sum()):.3f}, A–C {np.sqrt((((A3 - C3) / sd3) ** 2).sum()):.3f}")
    print("[손계산 2] 1차원 K-평균: 점 1, 2, 4, 7, 9, 10, 시작 중심 1과 4")
    x = np.array([1, 2, 4, 7, 9, 10.0])
    c = np.array([1.0, 4.0])
    for it in range(1, 5):
        lab = np.argmin(np.abs(x[:, None] - c[None, :]), 1)
        newc = np.array([x[lab == j].mean() for j in range(2)])
        wss = sum(((x[lab == j] - newc[j]) ** 2).sum() for j in range(2))
        print(f"  반복 {it}: 배정 {lab.tolist()}, 새 중심 {np.round(newc, 3).tolist()}, 군집 내 제곱합 {wss:.3f}")
        if np.allclose(newc, c):
            break
        c = newc
    tss = ((x - x.mean()) ** 2).sum()
    print(f"  전체 제곱합 {tss:.3f}, 군집 간/전체 비 {1 - wss / tss:.4f}")
    a = np.mean([3, 2])
    b = np.mean([3, 5, 6])
    print(f"  점 4의 실루엣: a = {a:.3f}, b = {b:.3f}, s = {(b - a) / max(a, b):.3f}")
    from sklearn.metrics import silhouette_samples
    s = silhouette_samples(x[:, None], lab)
    print(f"  모든 점의 실루엣 {np.round(s, 3).tolist()}, 평균 {s.mean():.3f}")


# ---------------------------------------------------------------- 본문 수치
def numbers(d, W):
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score

    print("[0] 변수 요약")
    print(d[V].describe().round(3).to_string())
    print(d[V].corr().round(3).to_string())
    from esda import Moran
    print("  퀸 가중치 Moran's I: " + ", ".join(f"{v} {Moran(d[v], W, permutations=0).I:.3f}" for v in V) + f"; 가람1동 로그밀도 {d.loc[0, '로그밀도']:.3f}")
    Z = zscore(d)
    res = {}
    print("[1] k에 따른 지표 (표준화)")
    for k in range(2, 9):
        rk, lk = run(d, W, "kmeans", k)
        rh, lh = run(d, W, "hierarchical", k)
        res[k] = dict(km=(rk, lk), hc=(rh, lh), sk=silhouette_score(Z, lk), sh=silhouette_score(Z, lh))
        print(f"  k {k}: K-평균 비 {rk['ratio']:.4f} 실루엣 {res[k]['sk']:.4f} 크기 {[c['size'] for c in rk['clusters']]} 조각 {[c['fragments'] for c in rk['clusters']]} | "
              f"Ward 비 {rh['ratio']:.4f} 실루엣 {res[k]['sh']:.4f} 크기 {[c['size'] for c in rh['clusters']]} | ARI {adjusted_rand_score(lk, lh):.3f}")
    rk, lk = res[4]["km"]
    print("[2] K-평균 k = 4 (앱 카드)")
    for row in rk["summary"]:
        print(f"  {row[0]}: {app_num(row[1]) if not isinstance(row[1], str) else row[1]}")
    for c in rk["clusters"]:
        print(f"  군집 {c['id']}: 크기 {c['size']}, 조각 {c['fragments']}, SS {app_num(c['within_ss'], 3)}, 평균 {[app_num(m, 4) for m in c['means']]}, z {[round(z, 2) for z in c['z_means']]}")
    print(f"  군집 4의 동 수 {int((lk == 4).sum())}, 구 {d.loc[lk == 4, '구'].value_counts().to_dict()}")
    rw, lw = run(d, W, "kmeans", 4, variables=VRAW)
    print("[2b] 원비율 출동률로 한 K-평균 k = 4")
    for c in rw["clusters"]:
        print(f"  군집 {c['id']}: 크기 {c['size']}, 조각 {c['fragments']}, 평균 {[app_num(m, 4) for m in c['means']]}, z {[round(z, 2) for z in c['z_means']]}")
    small = d[lw == 4]
    print(f"  작은 군집의 동: {small['동이름'].tolist()}, 인구 {small['인구'].tolist()}, 출동 건수 {small['PT_CNT'].tolist()}, R_EB {np.round(small['R_EB'], 2).tolist()}")
    print(f"  비율 {app_num(rw['ratio'])}, R_EB 결과와의 ARI {adjusted_rand_score(lk, lw):.3f}; 출동률 범위 {d['출동률'].min():.2f}~{d['출동률'].max():.2f}, R_EB 범위 {d['R_EB'].min():.2f}~{d['R_EB'].max():.2f}")
    rh, lh = res[4]["hc"]
    print("[3] Ward k = 4 (앱 카드)")
    for c in rh["clusters"]:
        print(f"  군집 {c['id']}: 크기 {c['size']}, 조각 {c['fragments']}, 평균 {[app_num(m, 4) for m in c['means']]}")
    print(f"  Ward 군집 간/전체 비 {app_num(rh['ratio'])}")
    import pandas as pd
    print("  K-평균(행) × Ward(열) 교차표\n" + pd.crosstab(lk, lh).to_string())
    # 표준화 안 함
    rr, lr = run(d, W, "kmeans", 4, std=False)
    print("[4] 표준화하지 않은 K-평균 k = 4")
    print(f"  요약 {[(r[0], app_num(r[1]) if not isinstance(r[1], str) else r[1]) for r in rr['summary']]}")
    for c in rr["clusters"]:
        print(f"  군집 {c['id']}: 크기 {c['size']}, 조각 {c['fragments']}, 평균 {[app_num(m, 4) for m in c['means']]}")
    X = d[V].to_numpy()
    print(f"  변수별 분산 {np.round(X.var(0), 3).tolist()} → 전체 제곱합에서 차지하는 몫 {np.round(X.var(0) / X.var(0).sum() * 100, 1).tolist()}%")
    print(f"  표준화와 원래 값 결과의 ARI {adjusted_rand_score(lk, lr):.3f}")
    # 상관이 큰 변수
    r3, l3 = run(d, W, "kmeans", 4, variables=["고령비율", "온도편차", "R_EB"])
    print(f"[5] 로그밀도를 뺀 3변수 K-평균 k = 4: 크기 {[c['size'] for c in r3['clusters']]}, 4변수와의 ARI {adjusted_rand_score(lk, l3):.3f}")
    # 국소 최적
    wss = np.array([KMeans(4, n_init=1, random_state=s).fit(Z).inertia_ for s in range(200)])
    best = wss.min()
    print(f"[6] 시작점 200개(n_init = 1): 서로 다른 해 {len(np.unique(np.round(wss, 3)))}개, 최솟값 {best:.3f} 도달 {int(np.isclose(wss, best, atol=1e-3).sum())}번, 최댓값 {wss.max():.3f}; 앱(n_init 50) 군집 내 제곱합 {rk['summary'][4][1]:.3f}")
    # 안정성: 동을 하나씩 빼고 다시 군집
    return res, lk, lr, lh


# ---------------------------------------------------------------- 그림
def fills(lab):
    return [CAT[int(v) - 1] for v in lab]


def legend(s, x, y, labels):
    for k, lab in enumerate(labels):
        s.rect(x, y - 10, 12, 12, cls="s-mu", width=0.5, fill=CAT[k])
        s.text(x + 16, y, lab, size=10, anchor="start")
        x += 26 + len(lab) * 6.5
    return x


def fig_scale(d, lk, lr, res):
    W_, H = 720, 285
    s = Svg(W_, H, "K-평균(군집 4개) 결과를 지도에 칠한 것. 왼쪽: 네 변수를 표준화(z점수)한 결과. 오른쪽: 원래 값 그대로 쓴 결과. 원래 값에서는 분산이 가장 큰 고령비율이 전체 제곱합의 4분의 3을 차지해, "
                   "군집이 거의 고령비율의 높낮이 띠로만 나뉨. 군집 번호는 크기 순서라 두 지도의 같은 색이 같은 뜻은 아님. 비공간 군집이라 같은 군집이 여러 조각으로 흩어짐")
    mw = 300
    for k, (lab, title) in enumerate(((lk, "표준화 (z점수)"), (lr, "원래 값"))):
        fr = MapFrame(d.total_bounds, 40 + k * (mw + 40), 36, mw)
        draw(s, fr, d.geometry, None, width=0.3, stroke="s-bg", fills=fills(lab))
        outline(s, fr, d.union_all(), cls="s-fg", width=0.8)
        s.text(fr.x + mw / 2, 24, title, size=12, weight="600")
    legend(s, 250, H - 12, ["군집 1", "군집 2", "군집 3", "군집 4"])
    s.save(os.path.join(OUT, "31-scale.svg"))


def fig_k(res):
    W_, H = 720, 270
    ks = np.array(sorted(res))
    s = Svg(W_, H, "군집 수 k에 따른 두 지표(표준화한 네 변수). 왼쪽: 군집 간 제곱합 / 전체 제곱합 비. k가 커질수록 계속 커지므로 꺾이는 곳(팔꿈치)을 찾지만 뚜렷하지 않음. "
                   f"오른쪽: 평균 실루엣 계수. K-평균은 k = 2에서 가장 크고({res[2]['sk']:.3f}), Ward는 k = 2와 3이 거의 같음({res[2]['sh']:.4f}, {res[3]['sh']:.4f}). 파랑 실선은 K-평균, 주황 점선은 Ward 계층 군집")
    for p, (key_k, key_h, lim, ticks, title) in enumerate((("km", "hc", (0.4, 0.9), [0.4, 0.5, 0.6, 0.7, 0.8, 0.9], "군집 간 / 전체 비"),
                                                          ("sk", "sh", (0.2, 0.45), [0.2, 0.25, 0.3, 0.35, 0.4, 0.45], "평균 실루엣 계수"))):
        ax = Axes(s, 70 + p * 355, 40, 270, 180, (1.7, 8.3), lim)
        for key, cls, dash in ((key_k, "s-ac", None), (key_h, "s-bd", "5 3")):
            v = np.array([res[k][key][0]["ratio"] if key in ("km", "hc") else res[k][key] for k in ks])
            ax.curve(ks, v, cls=cls, width=2, dash=dash)
            for k, vv in zip(ks, v):
                s.circle(float(ax.X(k)), float(ax.Y(vv)), 3, cls=f"{'f-ac' if cls == 's-ac' else 'f-bd'} s-bg", width=0.6)
        ax.xaxis(ticks=list(ks), label="군집 수 k")
        ax.yaxis(ticks=ticks)
        s.text(float(ax.X(5)), 28, title, size=12, weight="600")
    s.save(os.path.join(OUT, "31-k.svg"))


def fig_dendro(d):
    from scipy.cluster.hierarchy import dendrogram, linkage
    Z = zscore(d)
    L = linkage(Z, "ward")
    dn = dendrogram(L, no_plot=True)
    hs = L[:, 2]
    cut = (hs[-4] + hs[-3]) / 2  # 군집 4개가 남는 높이
    W_, H = 720, 300
    s = Svg(W_, H, f"Ward 계층 군집의 덴드로그램(표준화한 네 변수, 행정동 150개). 아래 끝이 동 하나이고, 위로 갈수록 가장 적게 손해 보는 두 군집을 합침. 세로 길이는 병합 거리 √(2Δ)로, 합칠 때 늘어난 군집 내 제곱합 Δ가 클수록 김. "
                   f"주황 점선({cut:.1f})에서 자르면 군집 4개가 남음. 맨 위의 병합({hs[-1]:.1f})이 특히 길어 덴드로그램만 보면 군집 2개가 가장 뚜렷하고, 군집 4개가 남는 높이 구간({hs[-4]:.1f}~{hs[-3]:.1f})은 좁음")
    ax = Axes(s, 60, 24, 640, 236, (0, 1500), (0, hs.max() * 1.05))
    for xs, ys in zip(dn["icoord"], dn["dcoord"]):
        pts = [(float(ax.X(x)), float(ax.Y(y))) for x, y in zip(xs, ys)]
        s.path("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts), cls="s-fg", width=0.8)
    ax.curve(np.array([0, 1500]), np.array([cut, cut]), cls="s-bd", width=1.5, dash="5 3")
    ax.yaxis(label="병합 거리")
    s.text(380, H - 14, "행정동 150개 (덴드로그램 순서)", size=10, cls="f-mu")
    s.save(os.path.join(OUT, "31-dendro.svg"))
    print(f"[그림] 덴드로그램 마지막 병합 거리 {np.round(hs[-5:], 2).tolist()}, 자르는 높이 {cut:.2f}; 맨 위 병합의 Δ = {hs[-1] ** 2 / 2:.1f} (= 0.4825 × 600?)")


def fig_profile(d, rk, lk):
    W_, H = 720, 300
    s = Svg(W_, H, "왼쪽: 표준화한 네 변수로 만든 K-평균 군집 4개의 지도. 오른쪽: 군집 프로필. 칸의 숫자는 군집 평균(원래 단위), 색은 표준화 평균(빨강은 전체 평균보다 높음, 파랑은 낮음). "
                   "군집 2는 밀도·온도가 높고 고령비율이 낮은 도심형, 군집 3은 그 반대인 외곽형, 군집 1은 중간, 군집 4는 도심형 가운데 출동률(EB 평활)이 특히 높은 14개 동임")
    fr = MapFrame(d.total_bounds, 20, 40, 300)
    draw(s, fr, d.geometry, None, width=0.3, stroke="s-bg", fills=fills(lk))
    outline(s, fr, d.union_all(), cls="s-fg", width=0.8)
    s.text(170, 26, "K-평균 군집 4개", size=12, weight="600")
    x0, y0, cw, rh = 360, 60, 80, 34
    s.text(x0 + 10, y0 - 10, "크기", size=11, weight="600")
    for j, h in enumerate(V):
        s.text(x0 + 30 + j * cw + (cw - 4) / 2, y0 - 10, h, size=11, weight="600")
    for i, c in enumerate(rk["clusters"]):
        y = y0 + i * rh
        s.rect(x0 - 26, y + 9, 14, 14, cls="s-mu", width=0.5, fill=CAT[i])
        s.text(x0 + 10, y + 21, f"{c['size']}", size=11)
        for j, (m, z) in enumerate(zip(c["means"], c["z_means"])):
            cls = "d" + str(int(np.digitize(z, [-1, -0.5, 0, 0.5, 1])))
            xx = x0 + 30 + j * cw
            s.rect(xx, y + 2, cw - 4, rh - 4, cls=f"s-bg {cls}", width=0.5)
            txt = "#ffffff" if cls in ("d0", "d5") else "#1c2330"
            s.add(f'<text x="{xx + (cw - 4) / 2:.1f}" y="{y + 21:.1f}" font-size="11" text-anchor="middle" fill="{txt}">{app_num(m, 4)}</text>')
    yb = y0 + 4 * rh + 26
    labs = ["z < −1", "−1~−0.5", "−0.5~0", "0~0.5", "0.5~1", "z ≥ 1"]
    x = x0 - 20
    for k, lab in enumerate(labs):
        s.rect(x, yb - 10, 12, 12, cls=f"s-mu d{k}", width=0.5)
        s.text(x + 15, yb, lab, size=9, anchor="start")
        x += 22 + len(lab) * 5.6
    s.save(os.path.join(OUT, "31-profile.svg"))


if __name__ == "__main__":
    d, W = load()
    hand(d)
    res, lk, lr, lh = numbers(d, W)
    fig_scale(d, lk, lr, res)
    fig_k(res)
    fig_dendro(d)
    fig_profile(d, res[4]["km"][0], lk)
