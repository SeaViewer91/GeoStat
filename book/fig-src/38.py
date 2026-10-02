"""38강 그림과 본문 수치.

- 38-designs.svg : 지표온도(참값) 위에 그린 다섯 가지 표본 설계의 한 번 실현 (n = 50)
- 38-perf.svg    : 설계별 성능. 시 평균 추정의 RMSE와 95% 구간 포함률, 크리깅 지도의 RMSE (n = 25, 50, 100)

모집단은 시 경계 안 육지의 50 m 지표온도 셀 전체(hanbit_lst.tif). 참값을 모두 알므로 설계마다 표본을 여러 번 뽑아
추정값을 참값과 비교함. 크리깅의 베리오그램은 별도의 예비 표본(무작위 500점)으로 한 번 추정해 모든 설계에 같이 씀.

실행 (GeoStat 엔진 환경에서, 몇 분):
    cd engine && uv run python ../book/fig-src/38.py
"""
import os
import sys
import warnings

import numpy as np
import rasterio
import shapely

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gskit import empirical, expo, fit_wls, krige  # noqa: E402
from mapkit import DATA, MapFrame, load_dong, outline, png, ramp_rgb  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import rng  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
DESIGNS = ["단순 무작위", "층화(구)", "계통", "GRTS", "공간 피복"]
CELL = 50.0


def frame():
    """모집단 틀: 시 안 육지 셀의 중심 좌표, 지표온도, 구, 래스터 행·열"""
    with rasterio.open(os.path.join(DATA, "hanbit_lst.tif")) as r:
        z = r.read(1).astype(float)
        tr = r.transform
    z[z <= -9000] = np.nan
    rows, cols = np.indices(z.shape)
    X = tr.c + (cols + 0.5) * CELL
    Y = tr.f - (rows + 0.5) * CELL
    dong = load_dong()
    win = dong.union_all()
    land = ~np.isnan(z) & shapely.contains_xy(win, X, Y)
    gu = np.full(z.shape, "", object)
    for g, geom in dong.dissolve("구").geometry.items():
        gu[shapely.contains_xy(geom, X, Y) & land] = g
    land &= gu != ""
    F = dict(x=X[land], y=Y[land], z=z[land], gu=gu[land], row=rows[land], col=cols[land])
    look = np.full(z.shape, -1, np.int64)
    look[land] = np.arange(land.sum())
    F["look"], F["x0"], F["y1"] = look, tr.c, tr.f
    return F, z, tr, dong, win


# ---------------------------------------------------------------- 설계
def srs(F, n, r):
    return r.choice(len(F["z"]), n, replace=False)


def stratified(F, n, r):
    """구별 비례 배분 층화 무작위 추출. 배분은 반올림(합이 n이 되게 조정)"""
    g, N = np.unique(F["gu"], return_counts=True)
    nh = np.maximum(2, np.round(n * N / N.sum()).astype(int))
    while nh.sum() > n:
        nh[np.argmax(nh)] -= 1
    while nh.sum() < n:
        nh[np.argmin(nh / N)] += 1
    idx = []
    for gg, k in zip(g, nh):
        pool = np.where(F["gu"] == gg)[0]
        idx += list(r.choice(pool, k, replace=False))
    return np.array(idx)


def systematic(F, n, r):
    """정사각 격자 + 무작위 시작점. 간격은 기대 표본 수가 n이 되게 정함. 바다에 떨어진 점은 버림(표본 수가 조금씩 다름)"""
    area = len(F["z"]) * CELL ** 2
    d = np.sqrt(area / n)
    x0, y0 = F["x"].min() - CELL / 2 + r.uniform(0, d), F["y"].min() - CELL / 2 + r.uniform(0, d)
    gx = np.arange(x0, F["x"].max() + CELL, d)
    gy = np.arange(y0, F["y"].max() + CELL, d)
    GX, GY = np.meshgrid(gx, gy)
    cols = np.floor((GX.ravel() - F["x0"]) / CELL).astype(int)
    rows = np.floor((F["y1"] - GY.ravel()) / CELL).astype(int)
    ok = (rows >= 0) & (rows < F["look"].shape[0]) & (cols >= 0) & (cols < F["look"].shape[1])
    idx = F["look"][rows[ok], cols[ok]]
    return idx[idx >= 0]


PERMS = np.array([[a, b, c, d] for a in range(4) for b in range(4) for c in range(4) for d in range(4) if len({a, b, c, d}) == 4])


def grts(F, n, r, L=10):
    """GRTS(Stevens & Olsen 2004), 같은 포함확률. 사분 트리 주소의 각 마디에서 사분면 순서를 무작위로 바꾸고,
    그 주소 순서로 늘어놓은 셀에서 계통 추출함"""
    row, col = F["row"], F["col"]
    addr = np.zeros(len(row), np.int64)
    prefix = np.zeros(len(row), np.int64)
    for lev in range(L):
        sh = L - 1 - lev
        dig = 2 * ((row >> sh) & 1) + ((col >> sh) & 1)
        u, inv = np.unique(prefix, return_inverse=True)
        p = PERMS[r.integers(0, 24, len(u))][inv, dig]
        addr = addr * 4 + p
        prefix = prefix * 4 + dig
    order = np.argsort(addr, kind="stable")
    N = len(order)
    step = N / n
    pos = (r.uniform(0, step) + step * np.arange(n)).astype(int)
    return order[pos]


def coverage(F, n, r):
    """공간 피복 표본(Walvoort 외 2010): 좌표의 k-평균 중심에서 가장 가까운 셀. 확률 표본이 아님"""
    from sklearn.cluster import KMeans
    sub = r.choice(len(F["z"]), 20000, replace=False)
    P = np.c_[F["x"][sub], F["y"][sub]]
    km = KMeans(n, n_init=1, random_state=int(r.integers(1 << 30))).fit(P)
    from scipy.spatial import cKDTree
    t = cKDTree(np.c_[F["x"], F["y"]])
    return t.query(km.cluster_centers_)[1]


FUN = dict(zip(DESIGNS, [srs, stratified, systematic, grts, coverage]))


# ---------------------------------------------------------------- 손계산
def hand():
    print("[손계산] 두 층의 층화 추정")
    W, yb, s, n = np.array([0.6, 0.4]), np.array([31.0, 33.0]), np.array([1.2, 0.8]), np.array([6, 4])
    est = (W * yb).sum()
    var = (W ** 2 * s ** 2 / n).sum()
    print(f"  추정 {est:.3f}, 분산 {var:.4f} = {W[0] ** 2 * s[0] ** 2 / n[0]:.4f} + {W[1] ** 2 * s[1] ** 2 / n[1]:.4f}, 표준오차 {np.sqrt(var):.4f}")
    print("[손계산] 포함확률: N = 1,000셀에서 n = 50 → π = 0.05, 호비츠-톰프슨 평균 = Σ(y/π)/N = ȳ")


# ---------------------------------------------------------------- 평가
def pilot_variogram(F):
    r = rng("pilot38")
    i = r.choice(len(F["z"]), 500, replace=False)
    X = np.c_[F["x"][i], F["y"][i]]
    E, _, _ = empirical(X, F["z"][i], 600, 12000)
    p, _ = fit_wls(E, expo, (0.3, 2.0, 5000))
    print(f"[베리오그램] 예비 표본 500점, 지수 모형: 너깃 {p[0]:.3f}, 부분 문턱값 {p[1]:.3f}, 실효 상관거리 {p[2]:.0f} m (너깃 비 {p[0] / (p[0] + p[1]):.2f})")
    return p


def evaluate(F, p, Rn=((25, 300), (50, 500), (100, 300))):
    mu = F["z"].mean()
    N = len(F["z"])
    print(f"[모집단] 셀 {N:,}개 (면적 {N * CELL ** 2 / 1e6:.1f} km²), 참 평균 {mu:.4f}℃, 표준편차 {F['z'].std():.4f}")
    g, Nh = np.unique(F["gu"], return_counts=True)
    print(f"  구별 셀 비율 {dict(zip(g, np.round(Nh / N, 3)))}, 구별 평균 {dict(zip(g, [round(F['z'][F['gu'] == x].mean(), 3) for x in g]))}")
    rv = rng("valid38")
    V = rv.choice(N, 3000, replace=False)
    XV = np.c_[F["x"][V], F["y"][V]]
    res = {}
    for n, R in Rn:
        r = rng(f"design38-{n}")
        for d in DESIGNS:
            est, cover, rmse_map, kv, sizes, mind = [], [], [], [], [], []
            for _ in range(R):
                idx = FUN[d](F, n, r)
                y = F["z"][idx]
                sizes.append(len(idx))
                if d == "층화(구)":
                    e, v = 0.0, 0.0
                    for gg, NN in zip(g, Nh):
                        m = F["gu"][idx] == gg
                        Wh = NN / N
                        e += Wh * y[m].mean()
                        v += Wh ** 2 * y[m].var(ddof=1) / m.sum() * (1 - m.sum() / NN)
                else:
                    e, v = y.mean(), y.var(ddof=1) / len(y) * (1 - len(y) / N)
                est.append(e)
                cover.append(abs(e - mu) <= 1.96 * np.sqrt(v))
                X = np.c_[F["x"][idx], F["y"][idx]]
                pred, var = krige(X, y, XV, expo, p)
                rmse_map.append(np.sqrt(np.mean((pred - F["z"][V]) ** 2)))
                kv.append(var.mean())
                D = np.hypot(X[:, None, 0] - X[None, :, 0], X[:, None, 1] - X[None, :, 1])
                np.fill_diagonal(D, np.inf)
                mind.append(D.min(1).mean())
            est = np.array(est)
            res[(d, n)] = dict(rmse=float(np.sqrt(np.mean((est - mu) ** 2))), bias=float(est.mean() - mu), cover=float(np.mean(cover)),
                               map=float(np.mean(rmse_map)), kv=float(np.mean(kv)), size=(min(sizes), max(sizes), float(np.mean(sizes))),
                               mind=float(np.mean(mind)))
            o = res[(d, n)]
            print(f"  n={n} {d}: 평균 추정 RMSE {o['rmse']:.4f} (치우침 {o['bias']:+.4f}), SRS 식 95% 구간 포함률 {o['cover']:.3f}, "
                  f"크리깅 RMSE {o['map']:.4f}, 평균 크리깅 분산 {o['kv']:.4f}, 가장 가까운 점까지 평균 {o['mind']:.0f} m, 표본 수 {o['size']}")
        b = res[("단순 무작위", n)]["rmse"]
        print(f"  n={n} 설계 효과(RMSE² 비, 단순 무작위 = 1): " + ", ".join(f"{d} {(res[(d, n)]['rmse'] / b) ** 2:.3f}" for d in DESIGNS))
    return res


def balance(F, n=50, R=300):
    """공간 균형의 척도: 보로노이 대신 '가장 가까운 표본점에 배정된 셀 수'의 분산(포함확률 합의 흔들림, Stevens & Olsen 2004 계열)"""
    from scipy.spatial import cKDTree
    N = len(F["z"])
    P = np.c_[F["x"], F["y"]]
    out = {}
    r = rng("balance38")
    for d in DESIGNS:
        vals = []
        for _ in range(R):
            idx = FUN[d](F, n, r)
            near = cKDTree(P[idx]).query(P)[1]
            cnt = np.bincount(near, minlength=len(idx)) * len(idx) / N  # 각 표본점의 몫 × (n/N) = 포함확률의 합
            vals.append(np.var(cnt))
        out[d] = float(np.mean(vals))
    print(f"[공간 균형] n={n}, 보로노이 포함확률 합의 분산(작을수록 고르게 퍼짐): " + ", ".join(f"{d} {v:.3f}" for d, v in out.items()))
    return out


def edge(F, win, R=100):
    """시 가장자리(해안·시 경계)까지 거리별 평균 지표온도와, 공간 피복 표본점이 가장자리 가까이에 놓이는 비율"""
    d = shapely.distance(win.boundary, shapely.points(F["x"], F["y"]))
    for a, b in ((0, 500), (500, 1000), (1000, 2000), (2000, 5000), (5000, 1e9)):
        m = (d >= a) & (d < b)
        print(f"[가장자리] {a / 1000:g}~{b / 1000:g} km: 셀 {m.mean():.1%}, 평균 지표온도 {F['z'][m].mean():.3f}")
    r = rng("edge38")
    near = [np.mean(d[coverage(F, 50, r)] < 1000) for _ in range(R)]
    near_s = [np.mean(d[srs(F, 50, r)] < 1000) for _ in range(R)]
    print(f"  가장자리 1 km 안: 셀 {np.mean(d < 1000):.1%}, 공간 피복 표본점 {np.mean(near):.1%}, 단순 무작위 표본점 {np.mean(near_s):.1%} (각 {R}회 평균)")


# ---------------------------------------------------------------- 그림
def fig_designs(F, z, tr, dong, win):
    W_, H = 720, 470
    svg = Svg(W_, H, "한빛시 지표온도(배경, 50 m)를 모집단으로 놓고 뽑은 다섯 가지 표본(각 50점 안팎)의 한 번 실현. 단순 무작위 표본은 몰리거나 빈 곳이 생김. "
                     "층화(구) 표본은 다섯 구에 면적 비례로 나눠 뽑음. 계통 표본은 정사각 격자에 무작위 시작점(바다에 떨어진 점은 버림). "
                     "GRTS는 사분 트리 주소를 무작위로 섞어 무작위성과 공간 균형을 함께 얻음. 공간 피복 표본은 좌표의 k-평균 중심이라 가장 고르지만 확률 표본이 아님")
    mw = 220
    lo, hi = 26, 38
    rgb = ramp_rgb(z, lo, hi)
    rgb[..., 3] = np.where(np.isnan(z), 0, 200)
    im = png(rgb, 440)
    x0, y1 = tr.c, tr.f
    x1, y0 = tr.c + z.shape[1] * CELL, tr.f - z.shape[0] * CELL
    panels = ["지표온도(모집단)"] + DESIGNS
    r = rng("show38")
    for k, title in enumerate(panels):
        fr = MapFrame(dong.total_bounds, 15 + (k % 3) * (mw + 18), 36 + (k // 3) * 215, mw)
        X0, Y0 = fr.xy(x0, y1)
        X1, Y1 = fr.xy(x1, y0)
        svg.add(f'<svg x="{fr.x:.1f}" y="{fr.y:.1f}" width="{mw:.1f}" height="{fr.h:.1f}" viewBox="{fr.x:.1f} {fr.y:.1f} {mw:.1f} {fr.h:.1f}" overflow="hidden">')
        svg.image_png(X0, Y0, X1 - X0, Y1 - Y0, im)
        svg.add("</svg>")
        outline(svg, fr, win, cls="s-mu", width=0.8)
        if title == "층화(구)":
            for geom in dong.dissolve("구").geometry:
                outline(svg, fr, geom, cls="s-fg", width=0.6)
        if k > 0:
            idx = FUN[title](F, 50, r)
            for i in idx:
                X_, Y_ = fr.xy(F["x"][i], F["y"][i])
                svg.circle(X_, Y_, 2.6, cls="f-fg s-bg", width=0.8)
            svg.text(fr.x + mw / 2, fr.y - 8, f"{title} (n = {len(idx)})", size=12, weight="600")
        else:
            svg.text(fr.x + mw / 2, fr.y - 8, title, size=12, weight="600")
    from mapkit import colorbar
    colorbar(svg, 260, 36 + 215 + fr.h + 22, 200, lo, hi, [26, 28, 30, 32, 34, 36, 38], "지표온도 (℃)")
    svg.save(os.path.join(OUT, "38-designs.svg"))


def fig_perf(res):
    W_, H = 720, 300
    svg = Svg(W_, H, "설계별 성능(모의, n = 25·50·100). 왼쪽: 시 평균 지표온도 추정의 RMSE. 공간적으로 고르게 퍼진 설계(계통, GRTS, 공간 피복)가 단순 무작위보다 작고, 층화(구)는 그 사이. "
                     "오른쪽: 표본점으로 정규 크리깅한 지도의 RMSE(검증 셀 3,000개). 고르게 퍼진 설계일수록 작고, 계통과 공간 피복이 가장 작음(거의 같음). 점선은 단순 무작위")
    ns = [25, 50, 100]
    cls = ["s-mu", "s-ok", "s-bd", "s-ac", "s-fg"]
    dash = ["4 3", None, None, None, None]
    for k, (key, lab) in enumerate((("rmse", "시 평균 추정 RMSE (℃)"), ("map", "크리깅 지도 RMSE (℃)"))):
        vals = [res[(d, n)][key] for d in DESIGNS for n in ns]
        ylim = (0, max(vals) * 1.1) if key == "rmse" else (1.0, max(vals) * 1.05)
        ax = Axes(svg, 70 + k * 330, 40, 230, 180, (np.log(20), np.log(125)), ylim)
        for j, d in enumerate(DESIGNS):
            xs = np.log(ns)
            ys = [res[(d, n)][key] for n in ns]
            ax.curve(xs, ys, cls=cls[j], width=2, dash=dash[j])
            for a, b in zip(xs, ys):
                svg.circle(float(ax.X(a)), float(ax.Y(b)), 3, cls=f"{cls[j].replace('s-', 'f-')} s-bg", width=0.6)
        ax.xaxis(ticks=list(np.log(ns)), label="표본 수 n", fmt=lambda t: f"{np.exp(t):.0f}")
        ax.yaxis(label=lab)
    x = 40
    for j, d in enumerate(DESIGNS):
        svg.line(x, H - 16, x + 24, H - 16, cls=cls[j], width=2, dash=dash[j])
        svg.text(x + 30, H - 12, d, size=11, anchor="start")
        x += 30 + len(d) * 12 + 30
    svg.save(os.path.join(OUT, "38-perf.svg"))


CACHE = os.path.join(HERE, "38-res.json")


if __name__ == "__main__":
    import json
    hand()
    F, z, tr, dong, win = frame()
    p = pilot_variogram(F)
    if os.path.exists(CACHE) and "--rerun" not in sys.argv:
        res = {tuple([k.split("|")[0], int(k.split("|")[1])]): v for k, v in json.load(open(CACHE, encoding="utf-8")).items()}
        print(f"[평가] {os.path.basename(CACHE)}에서 읽음 (다시 하려면 --rerun)")
        for (d, n), o in res.items():
            print(f"  n={n} {d}: " + ", ".join(f"{k} {v}" for k, v in o.items()))
    else:
        res = evaluate(F, p)
        balance(F)
        json.dump({f"{d}|{n}": v for (d, n), v in res.items()}, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    edge(F, win)
    fig_designs(F, z, tr, dong, win)
    fig_perf(res)
