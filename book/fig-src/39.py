"""39강 그림과 본문 수치.

- 39-cv.svg   : 교차검증 방법별 RMSE 추정(무작위 10겹, 공간 블록 10겹, 완충 LOO)과 실제 지도 오차. 집중 표본과 무작위 표본
- 39-maps.svg : 참 지표온도와, 집중 표본으로 학습한 랜덤 포레스트(공변량만, 공변량 + 좌표)의 예측 지도

과제: 시 안 육지의 50 m 지표온도를 표본점 600개로 학습해 시 전체를 예측함. 공변량은 100 m 격자 인구밀도(로그),
고령인구 비율, 해안까지 거리, 주요 도로까지 거리. 참값을 모두 알므로 지도 전체의 실제 오차를 계산할 수 있음.

실행 (GeoStat 엔진 환경에서, 5분 안팎):
    cd engine && uv run python ../book/fig-src/39.py
"""
import importlib
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from scipy import ndimage
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import DATA, MapFrame, colorbar, outline, png, ramp_rgb  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import rng  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
m38 = importlib.import_module("38")
OUT = os.path.join(HERE, "..", "fig")
COV = ["로그인구밀도", "고령비율", "해안거리", "도로거리"]
MODELS = ["선형 회귀", "RF(공변량)", "RF(공변량+좌표)"]
CVS = ["무작위 10겹", "공간 블록 10겹", "완충 LOO"]
N_TREE = 200


def covariates(F, z, tr):
    with rasterio.open(os.path.join(DATA, "hanbit_pop100.tif")) as r:
        pop, old = r.read(1).astype(float), r.read(2).astype(float)
    r_, c_ = F["row"] // 2, F["col"] // 2
    P, O = np.maximum(pop[r_, c_], 0), np.maximum(old[r_, c_], 0)
    sea = np.isnan(z)
    dsea = ndimage.distance_transform_edt(~sea) * 50
    roads = gpd.read_file(os.path.join(DATA, "hanbit_roads.gpkg"))
    rm = features.rasterize(((g, 1) for g in roads.geometry), out_shape=z.shape, transform=tr, all_touched=True)
    droad = ndimage.distance_transform_edt(rm == 0) * 50
    X = np.c_[np.log1p(P / 0.01), np.where(P > 0, O / np.maximum(P, 1e-9) * 100, 0), dsea[F["row"], F["col"]] / 1000, droad[F["row"], F["col"]] / 1000]
    print(f"[공변량] 셀 {len(X):,}개. 평균 {np.round(X.mean(0), 3).tolist()}, 지표온도와 상관 {np.round([np.corrcoef(X[:, j], F['z'])[0, 1] for j in range(4)], 3).tolist()}")
    return X


def samples(F, n=600):
    N = len(F["z"])
    r = rng("sample39")
    rand = r.choice(N, n, replace=False)
    t = cKDTree(np.c_[F["x"], F["y"]])
    centers = r.choice(N, 40, replace=False)
    clus = []
    for c in centers:
        near = t.query_ball_point([F["x"][c], F["y"][c]], 600)
        clus += list(r.choice(near, 15, replace=False))
    clus = np.array(clus)
    for nm, idx in (("집중", clus), ("무작위", rand)):
        P = np.c_[F["x"][idx], F["y"][idx]]
        d = cKDTree(P).query(P, 2)[0][:, 1]
        dm = t.query(P)  # noqa: F841
        far = cKDTree(P).query(np.c_[F["x"], F["y"]])[0]
        print(f"[표본 {nm}] {len(idx)}점, 가장 가까운 표본점까지 평균 {d.mean():.0f} m; 예측 셀에서 가장 가까운 표본점까지 평균 {far.mean():.0f} m, 최대 {far.max():.0f} m")
    return {"집중": clus, "무작위": rand}


def model(name, seed=0):
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    if name == "선형 회귀":
        return LinearRegression()
    return RandomForestRegressor(N_TREE, min_samples_leaf=2, n_jobs=2, random_state=seed, oob_score=True)


def design(X, F, idx, name):
    D = X[idx]
    if name == "RF(공변량+좌표)":
        D = np.c_[D, F["x"][idx] / 1000, F["y"][idx] / 1000]
    return D


def folds_random(n, r, k=10):
    f = np.arange(n) % k
    r.shuffle(f)
    return f


def folds_block(xy, r, k=10, size=3000):
    b = (np.floor(xy[:, 0] / size).astype(int) * 1000 + np.floor(xy[:, 1] / size).astype(int))
    ub, inv = np.unique(b, return_inverse=True)
    fb = np.arange(len(ub)) % k
    r.shuffle(fb)
    return fb[inv]


def cv_rmse(X, F, idx, name, folds):
    y = F["z"][idx]
    D = design(X, F, idx, name)
    pred = np.zeros(len(idx))
    for f in np.unique(folds):
        te = folds == f
        m = model(name).fit(D[~te], y[~te])
        pred[te] = m.predict(D[te])
    return float(np.sqrt(np.mean((pred - y) ** 2)))


def buffered_loo(X, F, idx, name, radius, r, m=120):
    y = F["z"][idx]
    D = design(X, F, idx, name)
    P = np.c_[F["x"][idx], F["y"][idx]]
    test = r.choice(len(idx), m, replace=False)
    err = []
    for i in test:
        keep = np.hypot(P[:, 0] - P[i, 0], P[:, 1] - P[i, 1]) > radius
        mm = model(name).fit(D[keep], y[keep])
        err.append(mm.predict(D[i:i + 1])[0] - y[i])
    return float(np.sqrt(np.mean(np.square(err))))


def true_rmse(X, F, idx, name, keep_pred=False):
    D = design(X, F, idx, name)
    m = model(name).fit(D, F["z"][idx])
    allD = X if name != "RF(공변량+좌표)" else np.c_[X, F["x"] / 1000, F["y"] / 1000]
    pred = m.predict(allD)
    out = float(np.sqrt(np.mean((pred - F["z"]) ** 2)))
    return (out, pred, m) if keep_pred else out


# ---------------------------------------------------------------- 손계산
def hand():
    z = np.array([3, 4, 6, 5, 7, 8, 7, 9, 10, 9.0])
    print("[손계산] 일렬의 10점(x = 1~10), 값 " + str(z.astype(int).tolist()) + ". 예측 = 남은 점 가운데 가장 가까운 왼쪽·오른쪽 값의 평균")

    def pred(i, avail):
        L = [j for j in avail if j < i]
        R = [j for j in avail if j > i]
        v = ([z[max(L)]] if L else []) + ([z[min(R)]] if R else [])
        return np.mean(v)
    e1 = [pred(i, [j for j in range(10) if j != i]) - z[i] for i in range(10)]
    blocks = [[0, 1, 2], [3, 4, 5], [6, 7, 8, 9]]
    e2 = []
    for b in blocks:
        for i in b:
            e2.append(pred(i, [j for j in range(10) if j not in b]) - z[i])
    print(f"  LOO 오차 {np.round(e1, 2).tolist()} → RMSE {np.sqrt(np.mean(np.square(e1))):.3f}")
    print(f"  블록(1~3, 4~6, 7~10)을 빼고 예측한 오차 {np.round(e2, 2).tolist()} → RMSE {np.sqrt(np.mean(np.square(e2))):.3f}")


# ---------------------------------------------------------------- 실행
def run(X, F, S):
    res = {}
    preds = {}
    from esda import Moran
    from libpysal.weights import KNN
    for sname, idx in S.items():
        xy = np.c_[F["x"][idx], F["y"][idx]]
        for mname in MODELS:
            r = rng(f"cv39-{sname}-{mname}")
            o = {}
            o["무작위 10겹"] = cv_rmse(X, F, idx, mname, folds_random(len(idx), r))
            o["공간 블록 10겹"] = cv_rmse(X, F, idx, mname, folds_block(xy, r))
            o["완충 LOO"] = buffered_loo(X, F, idx, mname, 2000, r)
            o["실제"], pred, m = true_rmse(X, F, idx, mname, keep_pred=True)
            res[(sname, mname)] = o
            preds[(sname, mname)] = pred
            dist = cKDTree(xy).query(np.c_[F["x"], F["y"]])[0]
            bins = [(0, 500), (500, 2000), (2000, 1e9)]
            parts = []
            for a, b in bins:
                mk = (dist >= a) & (dist < b)
                parts.append(f"{a / 1000:g}~{b / 1000:g} km {np.sqrt(np.mean((pred[mk] - F['z'][mk]) ** 2)):.3f} ({mk.mean():.0%})" if b < 1e9 else f"{a / 1000:g} km 이상 {np.sqrt(np.mean((pred[mk] - F['z'][mk]) ** 2)):.3f} ({mk.mean():.0%})")
            print(f"  [{sname}·{mname}] 가장 가까운 표본점까지 거리별 실제 RMSE: " + ", ".join(parts))
            txt = ", ".join(f"{k} {v:.3f}" for k, v in o.items())
            extra = ""
            if mname != "선형 회귀":
                resid = F["z"][idx] - m.oob_prediction_
                imp = np.round(m.feature_importances_, 3).tolist()
                extra = f"; OOB RMSE {np.sqrt(np.mean(resid ** 2)):.3f}, 중요도 {imp}"
            else:
                resid = F["z"][idx] - m.predict(design(X, F, idx, mname))
                extra = f"; 계수 {np.round(m.coef_, 3).tolist()}"
            w = KNN.from_array(xy, k=8)
            w.transform = "r"
            np.random.seed(123456789)
            mi = Moran(resid, w, permutations=999)
            print(f"  [{sname}·{mname}] {txt}{extra}; 잔차(OOB) Moran's I {mi.I:.3f} (p {mi.p_sim:.3f})")
    # 완충 반경의 근거: 무작위 표본 잔차의 상관 거리
    return res, preds


def fig_cv(res):
    W_, H = 720, 320
    c = res
    svg = Svg(W_, H, f"교차검증으로 추정한 RMSE(막대)와 시 전체 지도의 실제 RMSE(검은 가로선). 왼쪽: 40곳에 15점씩 모인 집중 표본. 무작위 10겹 교차검증은 실제 오차를 크게 과소평가함"
                     f"(RF 공변량+좌표: 추정 {c[('집중', 'RF(공변량+좌표)')]['무작위 10겹']:.2f}, 실제 {c[('집중', 'RF(공변량+좌표)')]['실제']:.2f}). 공간 블록과 완충 LOO가 실제에 더 가까움. "
                     f"오른쪽: 시 전체에서 단순 무작위로 뽑은 표본. 무작위 10겹이 실제와 비슷하고, 공간 블록·완충 LOO는 대체로 과대평가함")
    cls = ["f-mu", "f-ac", "f-bd"]
    ymax = max(max(o.values()) for o in res.values()) * 1.1
    for k, sname in enumerate(("집중", "무작위")):
        ax = Axes(svg, 60 + k * 340, 40, 280, 190, (-0.5, 2.5), (0, ymax))
        for g, mname in enumerate(MODELS):
            o = res[(sname, mname)]
            for j, cv in enumerate(CVS):
                v = o[cv]
                x0 = float(ax.X(g - 0.33 + j * 0.22))
                svg.rect(x0, float(ax.Y(v)), float(ax.X(0.2) - ax.X(0)), float(ax.Y(0) - ax.Y(v)), cls=f"s-bg {cls[j]}", width=0.5)
            yy = float(ax.Y(o["실제"]))
            svg.line(float(ax.X(g - 0.4)), yy, float(ax.X(g + 0.4)), yy, cls="s-fg", width=2.2)
            svg.text(float(ax.X(g)), 246, mname, size=10, cls="f-mu")
        ax.yaxis(label="RMSE (℃)")
        svg.text(ax.x0 + 140, 26, f"{sname} 표본 (600점)", size=12, weight="600")
    x = 120
    for j, cv in enumerate(CVS):
        svg.rect(x, H - 34, 12, 12, cls=f"s-mu {cls[j]}", width=0.5)
        svg.text(x + 18, H - 24, cv, size=11, anchor="start")
        x += 18 + len(cv) * 11 + 30
    svg.line(x, H - 28, x + 24, H - 28, cls="s-fg", width=2.2)
    svg.text(x + 30, H - 24, "실제 지도 RMSE", size=11, anchor="start")
    svg.save(os.path.join(OUT, "39-cv.svg"))


def fig_maps(F, z, tr, dong, win, preds, S):
    W_, H = 720, 280
    svg = Svg(W_, H, "왼쪽: 참 지표온도. 가운데: 40곳에 모인 집중 표본(점)으로 학습한 랜덤 포레스트(공변량만)의 예측. 인구밀도·해안·도로의 무늬를 따라 큰 경향은 잡지만, "
                     "참 지도의 잘고 얼룩덜룩한 무늬는 공변량에 없어 매끈하게 뭉개짐. 오른쪽: 같은 표본에 좌표를 더한 랜덤 포레스트. 표본 덩어리 둘레에서는 그 자리의 높낮이를 조금 더 따라가지만, "
                     "표본이 없는 넓은 곳에서는 공변량만의 예측과 거의 같음")
    mw = 220
    lo, hi = 26, 38
    items = [("참 지표온도", F["z"], None), ("RF(공변량)", preds[("집중", "RF(공변량)")], S["집중"]), ("RF(공변량+좌표)", preds[("집중", "RF(공변량+좌표)")], S["집중"])]
    for k, (title, v, pts) in enumerate(items):
        arr = np.full(z.shape, np.nan)
        arr[F["row"], F["col"]] = v
        fr = MapFrame(dong.total_bounds, 15 + k * (mw + 18), 36, mw)
        X0, Y0 = fr.xy(tr.c, tr.f)
        X1, Y1 = fr.xy(tr.c + z.shape[1] * 50, tr.f - z.shape[0] * 50)
        svg.add(f'<svg x="{fr.x:.1f}" y="{fr.y:.1f}" width="{mw:.1f}" height="{fr.h:.1f}" viewBox="{fr.x:.1f} {fr.y:.1f} {mw:.1f} {fr.h:.1f}" overflow="hidden">')
        svg.image_png(X0, Y0, X1 - X0, Y1 - Y0, png(ramp_rgb(arr, lo, hi), 440))
        svg.add("</svg>")
        outline(svg, fr, win, cls="s-mu", width=0.8)
        if pts is not None:
            for i in pts:
                X_, Y_ = fr.xy(F["x"][i], F["y"][i])
                svg.circle(X_, Y_, 1.2, cls="f-fg", width=0)
        svg.text(fr.x + mw / 2, fr.y - 8, title, size=12, weight="600")
    colorbar(svg, 260, H - 40, 200, lo, hi, [26, 28, 30, 32, 34, 36, 38], "지표온도 (℃)")
    svg.save(os.path.join(OUT, "39-maps.svg"))


if __name__ == "__main__":
    hand()
    F, z, tr, dong, win = m38.frame()
    X = covariates(F, z, tr)
    S = samples(F)
    res, preds = run(X, F, S)
    fig_cv(res)
    fig_maps(F, z, tr, dong, win, preds, S)
