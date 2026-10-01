"""32강 그림과 본문 수치.

- 32-chain.svg : 손계산. 한 줄로 이어진 여섯 지역의 비공간 군집과 연결 제약 군집
- 32-skater.svg : SKATER의 최소 신장 트리와 자른 가지(군집 4개)
- 32-methods.svg : 같은 네 변수로 만든 군집·지역 6가지 (비공간 K-평균, SKATER, Ward 공간 제약, AZP, Region K-Means, Max-p)
- 32-azp.svg : AZP를 시작점(시드) 30개로 돌린 결과의 군집 간 / 전체 비

변수는 31강과 같음(고령비율, 로그밀도, 온도편차, R_EB). 공간가중치는 퀸 인접.
앱 해 보기 수치는 GeoStat 엔진(cluster.prepare/run)으로 계산함 (앱과 같은 계산, 시드 123456789).

실행 (GeoStat 엔진 환경에서, 5분쯤 걸림):
    cd engine && uv run python ../book/fig-src/32.py
"""
import importlib
import os
import sys
import time
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import app_num  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
c31 = importlib.import_module("31")
OUT = os.path.join(HERE, "..", "fig")
V, CAT, run, zscore, fills = c31.V, c31.CAT, c31.run, c31.zscore, c31.fills
CAT12 = CAT + ["#7f3b08", "#2d004b", "#b2df8a", "#fb9a99"]
MAXP_T = 100000


def compact(d, lab):
    """지역별 폴스비-포퍼 지수 4πA/P² (원 = 1, 길쭉하거나 들쭉날쭉하면 작음)"""
    out = []
    for c in np.unique(lab):
        g = d[lab == c].union_all()
        out.append(4 * np.pi * g.area / g.length ** 2)
    return np.array(out)


# ---------------------------------------------------------------- 손계산
def hand():
    print("[손계산] 한 줄로 이어진 지역 6개, 값 1, 8, 2, 9, 2, 7을 두 묶음으로")
    x = np.array([1, 8, 2, 9, 2, 7.0])

    def ss(v):
        return ((v - v.mean()) ** 2).sum()

    tss = ss(x)
    lo, hi = x[x < 5], x[x >= 5]
    import itertools as _it
    best3 = min(((sum(ss(np.array(g)) for g in parts), parts) for cut in _it.combinations(range(1, 6), 2)
                 for parts in [np.split(np.sort(x), list(cut))]), key=lambda t: t[0])
    print(f"  (연습) 비공간 세 묶음 최적: {[g.tolist() for g in best3[1]]}, 군집 내 제곱합 {best3[0]:.3f}")
    print(f"  전체 제곱합 {tss:.3f}. 비공간(값만): {lo.tolist()}와 {hi.tolist()}, 군집 내 제곱합 {ss(lo) + ss(hi):.3f}, 비 {1 - (ss(lo) + ss(hi)) / tss:.4f}")
    for cut in range(1, 6):
        a, b = x[:cut], x[cut:]
        print(f"  연결 제약: 지역 1~{cut} | {cut + 1}~6 → 평균 {a.mean():.3f}, {b.mean():.3f}, 군집 내 제곱합 {ss(a) + ss(b):.3f}, 비 {1 - (ss(a) + ss(b)) / tss:.4f}")
    import itertools
    three = sorted((ss(x[:i]) + ss(x[i:j]) + ss(x[j:]), i, j) for i, j in itertools.combinations(range(1, 6), 2))
    print("  (연습) 세 구간: " + ", ".join(f"1~{i} | {i + 1}~{j} | {j + 1}~6 → {v:.3f}" for v, i, j in three[:4]))
    y = np.array([1, 2, 2, 8, 9, 7.0])
    a, b = y[:3], y[3:]
    print(f"  값이 1, 2, 2, 8, 9, 7로 이웃끼리 닮았다면: 지역 1~3 | 4~6 군집 내 제곱합 {ss(a) + ss(b):.3f} = 비공간과 같음")
    return x


# ---------------------------------------------------------------- 본문 수치
def numbers(d, W):
    from sklearn.metrics import adjusted_rand_score
    res = {}
    rk, lk = run(d, W, "kmeans", 4)
    res["kmeans"] = (rk, lk, 0.0)
    for meth in ("skater", "ward_spatial", "azp", "region_kmeans"):
        t = time.time()
        r, lab = run(d, W, meth, 4)
        res[meth] = (r, lab, time.time() - t)
    t = time.time()
    r, lab = run(d, W, "maxp", threshold=MAXP_T, threshold_column="인구")
    res["maxp"] = (r, lab, time.time() - t)
    print("[1] 방법별 결과 (표준화한 네 변수, 퀸 인접)")
    for meth, (r, lab, dt) in res.items():
        cp = compact(d, lab)
        print(f"  {meth}: 지역 {r['k']}개, 군집 간/전체 {app_num(r['ratio'])}, 크기 {[c['size'] for c in r['clusters']]}, 조각 {[c['fragments'] for c in r['clusters']]}, "
              f"폴스비-포퍼 평균 {cp.mean():.3f} ({cp.min():.2f}~{cp.max():.2f}), 비공간 K-평균과 ARI {adjusted_rand_score(lab, lk):.3f}, {dt:.1f}초")
        if meth in ("skater", "maxp", "ward_spatial"):
            for c in r["clusters"]:
                pop = int(d.loc[lab == c["id"], "인구"].sum())
                print(f"     지역 {c['id']}: 크기 {c['size']}, 인구 {pop:,}, SS {app_num(c['within_ss'], 3)}, 평균 {[app_num(m, 4) for m in c['means']]}")
            print(f"     요약 {[(s[0], s[1] if isinstance(s[1], str) else app_num(s[1])) for s in r['summary']]}")
    # 군집 수에 따른 비
    print("[2] 군집 수에 따른 군집 간/전체 비")
    for k in (2, 4, 6, 8):
        row = []
        for meth in ("kmeans", "skater", "ward_spatial", "region_kmeans"):
            r, _ = run(d, W, meth, k)
            row.append(f"{meth} {r['ratio']:.4f}")
        print(f"  k {k}: " + ", ".join(row))
    # SKATER 최소 크기
    r, lab = run(d, W, "skater", 4, floor=20)
    print(f"[3] SKATER 군집별 최소 피처 수 20: 크기 {[c['size'] for c in r['clusters']]}, 비 {app_num(r['ratio'])}")
    # 고출동 동이 어디로 갔는지
    hi = res["kmeans"][1] == 4
    for meth in ("skater", "ward_spatial", "azp", "region_kmeans", "maxp"):
        lab = res[meth][1]
        u, c = np.unique(lab[hi], return_counts=True)
        print(f"  K-평균 고출동형 14개 동이 {meth}에서 속한 지역: {dict(zip(u.tolist(), c.tolist()))}")
    return res


def azp_seeds(d, W, n=30):
    vals = []
    t = time.time()
    for s in range(n):
        r, _ = run(d, W, "azp", 4, seed=s + 1)
        vals.append(r["ratio"])
    vals = np.array(vals)
    print(f"[4] AZP 시드 1~5의 비 {np.round(vals[:5], 4).tolist()}")
    print(f"[4] AZP 시드 {n}개: 군집 간/전체 {vals.min():.4f}~{vals.max():.4f}, 중앙값 {np.median(vals):.4f} ({time.time() - t:.0f}초)")
    return vals


def maxp_variants(d, W):
    print("[5] Max-p 임계값")
    for th in (50000, 100000, 150000):
        t = time.time()
        r, lab = run(d, W, "maxp", threshold=th, threshold_column="인구")
        pops = [int(d.loc[lab == c, "인구"].sum()) for c in range(1, r["k"] + 1)]
        print(f"  인구 {th:,} 이상: 지역 {r['k']}개, 비 {r['ratio']:.4f}, 인구 {min(pops):,}~{max(pops):,}, {time.time() - t:.1f}초")


# ---------------------------------------------------------------- 그림
def fig_chain(x):
    W_, H = 720, 200
    s = Svg(W_, H, "한 줄로 이어진 지역 여섯 개(값 1, 8, 2, 9, 2, 7)를 두 묶음으로 나눈 결과. 위: 값만 보는 비공간 군집은 낮은 값(1, 2, 2)과 높은 값(8, 9, 7)으로 나눠 군집 내 제곱합이 2.67이지만, "
                   "두 묶음이 서로 엇갈려 흩어짐. 아래: 이웃끼리만 묶는 연결 제약에서는 이어진 구간으로만 나눌 수 있어, 가장 좋은 자르기(지역 1과 2~6)도 군집 내 제곱합이 45.2로 커짐")
    cols = {0: "#0072B2", 1: "#E69F00"}
    for row, (lab, title) in enumerate(((np.array([0, 1, 0, 1, 0, 1]), "비공간: 값이 비슷한 것끼리"), (np.array([0, 1, 1, 1, 1, 1]), "연결 제약: 이어진 구간끼리"))):
        y0 = 40 + row * 80
        s.text(20, y0 + 26, title, size=12, anchor="start", weight="600")
        for i, v in enumerate(x):
            xx = 250 + i * 72
            s.rect(xx, y0 + 4, 68, 36, cls="s-bg", width=1, fill=cols[int(lab[i])])
            s.add(f'<text x="{xx + 34}" y="{y0 + 28}" font-size="14" text-anchor="middle" fill="#ffffff" font-weight="600">{int(v)}</text>')
    s.text(250 + 3 * 72, H - 10, "지역 1 → 6 (옆 칸끼리만 이웃)", size=10, cls="f-mu")
    s.save(os.path.join(OUT, "32-chain.svg"))


def fig_skater(d, W, res):
    from scipy.sparse.csgraph import minimum_spanning_tree
    from sklearn.metrics.pairwise import manhattan_distances
    Z = zscore(d)
    A = W.sparse.copy()
    A.data[:] = 1
    D = A.multiply(manhattan_distances(Z)).tocsr()
    D.eliminate_zeros()
    T = minimum_spanning_tree(D).tocoo()
    lab = res["skater"][1]
    cent = d.geometry.centroid
    W_, H = 720, 300
    cut = [(i, j) for i, j in zip(T.row, T.col) if lab[i] != lab[j]]
    s = Svg(W_, H, f"SKATER. 왼쪽: 이웃한 동끼리 변수 차이(맨해튼 거리)를 길이로 둔 최소 신장 트리(가지 {T.nnz}개). 모든 동을 가장 비슷한 이웃끼리 한 번씩만 잇는 나무임. "
                   f"주황 굵은 선은 군집 4개를 만들려고 자른 가지 {len(cut)}개. 오른쪽: 자른 결과의 지역 4개. 나무를 잘라 만들므로 지역은 언제나 이어진 한 덩어리임")
    mw = 320
    for k in range(2):
        fr = MapFrame(d.total_bounds, 20 + k * (mw + 40), 36, mw)
        if k == 0:
            draw(s, fr, d.geometry, ["f-sf"] * len(d), width=0.3, stroke="s-mu")
            for i, j in zip(T.row, T.col):
                x1, y1 = fr.xy(cent.x[i], cent.y[i])
                x2, y2 = fr.xy(cent.x[j], cent.y[j])
                if lab[i] != lab[j]:
                    s.line(x1, y1, x2, y2, cls="s-bd", width=3.2)
                else:
                    s.line(x1, y1, x2, y2, cls="s-fg", width=1)
            s.text(fr.x + mw / 2, 24, "최소 신장 트리와 자른 가지", size=12, weight="600")
        else:
            draw(s, fr, d.geometry, None, width=0.3, stroke="s-bg", fills=fills(lab))
            s.text(fr.x + mw / 2, 24, f"SKATER 지역 4개 (비 {res['skater'][0]['ratio']:.3f})", size=12, weight="600")
        outline(s, fr, d.union_all(), cls="s-fg", width=0.8)
    s.save(os.path.join(OUT, "32-skater.svg"))
    print(f"[그림] 최소 신장 트리 가지 {T.nnz}개, 자른 가지 {len(cut)}개")


def fig_methods(d, res):
    W_, H = 720, 470
    order = [("kmeans", "K-평균 (비공간)"), ("skater", "SKATER"), ("ward_spatial", "Ward 공간 제약"),
             ("azp", "AZP"), ("region_kmeans", "Region K-Means"), ("maxp", f"Max-p (인구 {MAXP_T // 10000}만 이상)")]
    desc = ", ".join(f"{t} {res[m][0]['ratio']:.2f}" for m, t in order)
    s = Svg(W_, H, f"같은 네 변수(표준화)로 나눈 여섯 가지 결과. 제목 옆 숫자는 군집 간 / 전체 비({desc}). 비공간 K-평균은 비가 가장 크지만 군집이 여러 조각으로 흩어지고, "
                   "공간 제약 방법은 모두 이어진 지역을 만드는 대신 비가 작아짐. 방법마다 경계가 크게 다름. Max-p는 지역 수를 정하지 않고, 인구 10만 명 이상인 지역을 가능한 한 많이 만듦")
    mw = 220
    for n, (meth, title) in enumerate(order):
        r, lab, _ = res[meth]
        row, col = divmod(n, 3)
        fr = MapFrame(d.total_bounds, 15 + col * (mw + 14), 40 + row * 215, mw)
        pal = CAT12 if meth == "maxp" else CAT
        draw(s, fr, d.geometry, None, width=0.3, stroke="s-bg", fills=[pal[int(v) - 1] for v in lab])
        outline(s, fr, d.union_all(), cls="s-fg", width=0.8)
        s.text(fr.x + mw / 2, 28 + row * 215, f"{title} · {r['ratio']:.2f}", size=11.5, weight="600")
    s.save(os.path.join(OUT, "32-methods.svg"))


def fig_azp(vals, res):
    W_, H = 720, 220
    s = Svg(W_, H, f"AZP를 시작점(시드) {len(vals)}개로 돌린 결과의 군집 간 / 전체 비(점 하나가 시드 하나, 지역 4개). 시작 지역 배치에 따라 {vals.min():.2f}~{vals.max():.2f}로 크게 달라짐. "
                   "세로선은 같은 자료의 다른 방법(SKATER, Region K-Means, Ward 공간 제약)과 비공간 K-평균의 비. AZP는 지역 안의 모든 쌍의 거리를 줄이는 목적 함수를 써서 이 비를 직접 최대화하지 않음")
    ax = Axes(s, 60, 54, 620, 100, (0.3, 0.75), (-1, 1))
    r = c31.np.random.default_rng(5)
    for v in vals:
        s.circle(float(ax.X(v)), float(ax.Y(r.uniform(-0.5, 0.5))), 4, cls="f-ac s-bg", width=0.6)
    for n, (meth, lab, cls) in enumerate((("skater", "SKATER", "s-bd"), ("region_kmeans", "Region K-Means", "s-ok"), ("ward_spatial", "Ward 공간", "s-fg"), ("kmeans", "K-평균(비공간)", "s-mu"))):
        v = res[meth][0]["ratio"]
        ax.vline(v, cls=cls, width=2, dash="4 3" if meth == "kmeans" else None)
        s.text(float(ax.X(v)) + (-4 if n == 0 else 4), 30 if n == 0 else 46, f"{lab} {v:.2f}", size=10, cls="f-mu", anchor="end" if n == 0 else "start")
    ax.xaxis(ticks=[0.3, 0.4, 0.5, 0.6, 0.7], label="군집 간 / 전체 비")
    s.save(os.path.join(OUT, "32-azp.svg"))


if __name__ == "__main__":
    d, W = c31.load()
    x = hand()
    res = numbers(d, W)
    fig_chain(x)
    fig_skater(d, W, res)
    fig_methods(d, res)
    vals = azp_seeds(d, W)
    fig_azp(vals, res)
    maxp_variants(d, W)
