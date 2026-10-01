"""22강 그림과 본문 수치.

- 22-maps.svg : 정규 크리깅(가우시안 모형) 예측과 크리깅 표준편차, 회귀 크리깅(1 km 평활 지표온도) 예측
- 22-cv.svg : 교차검증 RMSE 비교(20강의 결정론적 보간 포함)와 크리깅 표준화 오차의 분포

베리오그램 모형은 21강의 가우시안(너깃 0.046, 부분 문턱값 0.81, 실효 상관거리 9.5 km)을 다시 적합해 씀.
회귀 크리깅: 기온을 1 km 평활 지표온도로 회귀(일반 최소제곱)하고, 잔차를 정규 크리깅(잔차 베리오그램)해 더함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/22.py
"""
import os
import sys
import warnings

import numpy as np
import shapely
from scipy.interpolate import RBFInterpolator

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gskit import dist, empirical, fit_wls, gauss, grid, krige, lst_smooth, sample, sph, stations, window  # noqa: E402
from mapkit import MapFrame, colorbar, load_dong, outline, png, ramp_rgb, to_array  # noqa: E402
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
WIN = window()
ST, X, Z = stations()
N = len(Z)
G, INSIDE, (GXS, GYS) = grid(WIN, 250.0)
LO, HI = 23.0, 26.8


def models():
    E, _, _ = empirical(X, Z, 1500.0, 15000.0)
    pg, _ = fit_wls(E, gauss, [0.05, 0.7, 9000])
    ps, _ = fit_wls(E, sph, [0.05, 0.7, 9000])
    sm, tr = lst_smooth(1000)
    xs = sample(sm, tr, X)
    A = np.c_[np.ones(N), xs]
    b = np.linalg.lstsq(A, Z, rcond=None)[0]
    res = Z - A @ b
    Er, _, _ = empirical(X, res, 1500.0, 15000.0)
    pr, _ = fit_wls(Er, sph, [0.015, 0.002, 3000])
    print(f"[0] 가우시안 {np.round(pg, 4).tolist()}, 구형 {np.round(ps, 4).tolist()}, 잔차 구형 {np.round(pr, 5).tolist()}, 회귀 {np.round(b, 4).tolist()}")
    return pg, ps, pr, (sm, tr, b)


def hand():
    print("[손계산] 관측소 두 곳(0 km, 4 km), 예측 지점 1 km. 구형 모형 너깃 0, 문턱값 1, 상관거리 10 km")
    g = lambda h: sph(np.array(h) * 1000.0, 0, 1, 10000)  # noqa: E731
    g01, g03, g12 = float(g(1)), float(g(3)), float(g(4))
    A = np.array([[0, g12, 1], [g12, 0, 1], [1, 1, 0]], float)
    rhs = np.array([g01, g03, 1])
    w1, w2, mu = np.linalg.solve(A, rhs)
    var = w1 * g01 + w2 * g03 + mu
    print(f"  γ(1) = {g01:.4f}, γ(3) = {g03:.4f}, γ(4) = {g12:.4f}")
    print(f"  가중치 w1 = {w1:.4f}, w2 = {w2:.4f}, 라그랑주 μ = {mu:.4f}, 크리깅 분산 = {var:.4f} (표준편차 {np.sqrt(var):.3f})")
    for z1, z2 in ((25.0, 24.0),):
        print(f"  값 {z1}, {z2}이면 예측 {w1 * z1 + w2 * z2:.3f}")
    # IDW p=2와 비교
    w = np.array([1 / 1 ** 2, 1 / 3 ** 2])
    print(f"  IDW p=2 가중치 {np.round(w / w.sum(), 4).tolist()}")
    # 셋째 관측소가 첫째 바로 옆(0.2 km)에 있으면
    pts = np.array([0.0, 0.2, 4.0])
    D = np.abs(pts[:, None] - pts[None])
    A3 = np.ones((4, 4))
    A3[:3, :3] = g(D)
    A3[3, 3] = 0
    r3 = np.r_[g(np.abs(pts - 1.0)), 1]
    sol = np.linalg.solve(A3, r3)
    print(f"  관측소를 0.2 km에 하나 더 두면(0, 0.2, 4 km) 가중치 {np.round(sol[:3], 4).tolist()} (가림 효과)")


def cv(method):
    e, v = [], []
    for i in range(N):
        m = np.arange(N) != i
        p, var = method(X[m], Z[m], X[i:i + 1], m)
        e.append(p[0] - Z[i])
        v.append(var[0] if var is not None else np.nan)
    e, v = np.array(e), np.array(v)
    return e, v


def numbers(pg, ps, pr, rk):
    sm, tr, b = rk
    xs_all = sample(sm, tr, X)
    res_all = Z - (b[0] + b[1] * xs_all)

    def ok(vf, p):
        return lambda Xt, zt, X0, m: krige(Xt, zt, X0, vf, p, "ok")

    def sk(Xt, zt, X0, m):
        return krige(Xt, zt, X0, gauss, pg, "sk", mean=zt.mean())

    def uk(Xt, zt, X0, m):
        F = np.c_[np.ones(len(Xt)), (Xt - X.mean(0)) / 1000]
        F0 = np.c_[np.ones(len(X0)), (X0 - X.mean(0)) / 1000]
        return krige(Xt, zt, X0, gauss, pg, "uk", F=F, F0=F0)

    def rkm(Xt, zt, X0, m):
        x = xs_all[m]
        A = np.c_[np.ones(len(x)), x]
        bb = np.linalg.lstsq(A, zt, rcond=None)[0]
        r = zt - A @ bb
        x0 = sample(sm, tr, X0)
        pr_, vr = krige(Xt, r, X0, sph, pr, "ok")
        return bb[0] + bb[1] * x0 + pr_, vr

    def reg(Xt, zt, X0, m):
        x = xs_all[m]
        A = np.c_[np.ones(len(x)), x]
        bb, _, _, _ = np.linalg.lstsq(A, zt, rcond=None)
        r = zt - A @ bb
        s2 = r.var(ddof=2)
        x0 = sample(sm, tr, X0)
        A0 = np.c_[np.ones(len(x0)), x0]
        var = s2 * (1 + np.sum(A0 @ np.linalg.inv(A.T @ A) * A0, axis=1))
        return A0 @ bb, var

    def tps(Xt, zt, X0, m):
        return RBFInterpolator(Xt / 1000, zt, kernel="thin_plate_spline")(X0 / 1000), None

    def idw2(Xt, zt, X0, m):
        w = 1 / dist(X0, Xt) ** 2
        return (w * zt).sum(1) / w.sum(1), None

    print("[1] 교차검증 (RMSE, MAE, 평균 오차, 표준화 오차의 평균, 표준화 오차 제곱 평균)")
    out = {}
    for name, f in (("IDW p=2", idw2), ("박판 스플라인", tps), ("단순 크리깅", sk), ("정규 크리깅(구형)", ok(sph, ps)), ("정규 크리깅(가우시안)", ok(gauss, pg)),
                    ("보편 크리깅(선형 추세)", uk), ("지표온도 회귀", reg), ("회귀 크리깅", rkm)):
        e, v = cv(f)
        out[name] = (e, v)
        z = e / np.sqrt(v) if not np.isnan(v).all() else None
        extra = f", 표준화 오차 평균 {z.mean():+.3f}, 제곱 평균 {np.mean(z ** 2):.3f}, |표준화 오차|>1.96 {int((np.abs(z) > 1.96).sum())}개" if z is not None else ""
        print(f"  {name}: RMSE {np.sqrt(np.mean(e ** 2)):.3f}, MAE {np.mean(np.abs(e)):.3f}, 평균 오차 {e.mean():+.3f}{extra}")
    print(f"  회귀 크리깅 잔차의 구형 모형: 부분 문턱값 {pr[1]:.5f} → 잔차 크리깅의 기여가 거의 없음")
    # 지도
    pred_ok, var_ok = krige(X, Z, G, gauss, pg, "ok")
    xg = sample(sm, tr, G)
    rp, rv = krige(X, res_all, G, sph, pr, "ok")
    pred_rk = b[0] + b[1] * xg + rp
    print(f"[2] 정규 크리깅 지도: 예측 {pred_ok.min():.2f}~{pred_ok.max():.2f}, 표준편차 {np.sqrt(var_ok.min()):.3f}~{np.sqrt(var_ok.max()):.3f} (중앙값 {np.median(np.sqrt(var_ok)):.3f})")
    print(f"  회귀 크리깅 지도: 예측 {pred_rk.min():.2f}~{pred_rk.max():.2f}, 표준편차 {np.sqrt(rv.min()):.3f}~{np.sqrt(rv.max()):.3f}")
    i = np.argmax(var_ok)
    print(f"  크리깅 표준편차가 가장 큰 곳 ({G[i, 0]:.0f}, {G[i, 1]:.0f}), 가장 가까운 관측소까지 {dist(G[i:i + 1], X).min():.0f} m")
    dmin = dist(G, X).min(1)
    for lo_, hi_ in ((0, 500), (500, 1500), (1500, 3000), (3000, 10000)):
        m = (dmin >= lo_) & (dmin < hi_)
        print(f"    가장 가까운 관측소 {lo_}~{hi_} m인 격자점 {m.sum()}개: 크리깅 표준편차 평균 {np.sqrt(var_ok[m]).mean():.3f}")
    # 관측소 자리에서 너깃 효과
    p0, v0 = krige(X, Z, X[:1], gauss, pg, "ok")
    print(f"  관측소 S01 자리에서 정규 크리깅 예측 {p0[0]:.3f} (관측 {Z[0]}), 표준편차 {np.sqrt(v0[0]):.3f}")
    return out, (pred_ok, var_ok, pred_rk, rv)


def block(pg):
    print("[3] 블록 크리깅: 행정동 평균 기온")
    dong = load_dong()
    sill = pg[0] + pg[1]
    Cxx = sill - gauss(dist(X, X), *pg)
    n = N
    A = np.ones((n + 1, n + 1))
    A[:n, :n] = Cxx
    A[n, n] = 0
    Ainv = np.linalg.inv(A)
    rows = []
    for k, geom in enumerate(dong.geometry):
        Q, _, _ = grid(geom, 250.0)
        if len(Q) < 4:
            Q, _, _ = grid(geom, 100.0)
        if len(Q) < 1:
            c = geom.representative_point()
            Q = np.array([[c.x, c.y]])
        Cxb = (sill - gauss(dist(X, Q), *pg)).mean(1)
        Cbb = (sill - gauss(dist(Q, Q), *pg)).mean()
        sol = Ainv @ np.r_[Cxb, 1]
        w, mu = sol[:n], sol[n]
        pb = w @ Z
        vb = Cbb - w @ Cxb - mu
        c = geom.centroid
        pp, vp = krige(X, Z, np.array([[c.x, c.y]]), gauss, pg, "ok")
        rows.append((dong["동이름"][k], geom.area / 1e6, len(Q), pb, vb, pp[0], vp[0]))
    pb = np.array([r[3] for r in rows])
    vb = np.array([r[4] for r in rows])
    pp = np.array([r[5] for r in rows])
    vp = np.array([r[6] for r in rows])
    ar = np.array([r[1] for r in rows])
    print(f"  150개 동: 블록 예측 {pb.min():.2f}~{pb.max():.2f}, 중심점 예측 {pp.min():.2f}~{pp.max():.2f}, 두 예측의 차이 최대 {np.abs(pb - pp).max():.3f}℃, 0.1℃ 넘는 동 {int((np.abs(pb - pp) > 0.1).sum())}개")
    print(f"  블록 표준편차 {np.sqrt(vb.min()):.3f}~{np.sqrt(vb.max()):.3f} (중앙값 {np.median(np.sqrt(vb)):.3f}), 중심점 표준편차 {np.sqrt(vp.min()):.3f}~{np.sqrt(vp.max()):.3f} (중앙값 {np.median(np.sqrt(vp)):.3f})")
    order = np.argsort(ar)
    for idx in (order[0], order[len(order) // 2], order[-1]):
        r = rows[idx]
        print(f"   {r[0]}: 면적 {r[1]:.2f} km², 점 {r[2]}개, 블록 {r[3]:.3f} (표준편차 {np.sqrt(r[4]):.3f}), 중심점 {r[5]:.3f} (표준편차 {np.sqrt(r[6]):.3f})")
    k = int(np.argmax(np.abs(pb - pp)))
    r = rows[k]
    print(f"   차이가 가장 큰 동 {r[0]}: 면적 {r[1]:.2f} km², 블록 {r[3]:.3f}, 중심점 {r[5]:.3f}")
    return rows


# ---------------------------------------------------------------- 그림
def place(s, fr, vals, fn, lo, hi):
    arr = to_array(vals, INSIDE)
    g = GXS[1] - GXS[0]
    X0, Y0 = fr.xy(GXS[0] - g / 2, GYS[-1] + g / 2)
    X1, Y1 = fr.xy(GXS[-1] + g / 2, GYS[0] - g / 2)
    s.image_png(X0, Y0, X1 - X0, Y1 - Y0, png(fn(arr, lo, hi), int(2 * (X1 - X0))))


def gray_rgb(v, lo, hi):
    t = np.nan_to_num(np.clip((v - lo) / (hi - lo), 0, 1))
    c = (245 - 190 * t)[..., None]
    rgb = np.concatenate([c, c, c + 8 * (1 - t)[..., None]], -1)
    a = np.where(np.isnan(v), 0, 255)[..., None]
    return np.concatenate([rgb, a], -1).astype(np.uint8)


def fig_maps(maps):
    pred_ok, var_ok, pred_rk, rv = maps
    W_, H = 720, 300
    s = Svg(W_, H, "왼쪽: 정규 크리깅(가우시안 베리오그램)으로 예측한 8월 평균 기온. 가운데: 크리깅 표준편차. 관측소(점)에서 멀수록, 특히 시 가장자리에서 커짐. "
                   "오른쪽: 회귀 크리깅(1 km 평활 지표온도 + 잔차 크리깅). 관측소 사이에서도 지표온도의 무늬를 따라가, 동쪽 해안의 더운 곳처럼 관측소가 놓치는 세부가 나타남")
    mw = 220
    fr = [MapFrame(WIN.bounds, 15 + k * (mw + 13), 40, mw) for k in range(3)]
    titles = ["정규 크리깅 예측", "크리깅 표준편차", "회귀 크리깅 예측"]
    place(s, fr[0], pred_ok, ramp_rgb, LO, HI)
    place(s, fr[1], np.sqrt(var_ok), gray_rgb, 0.25, 0.5)
    place(s, fr[2], pred_rk, ramp_rgb, LO, HI)
    for k in range(3):
        s.text(fr[k].x + mw / 2, 26, titles[k], size=12, weight="600")
        outline(s, fr[k], WIN, cls="s-mu", width=0.8)
        for x, y in X:
            X_, Y_ = fr[k].xy(x, y)
            s.circle(X_, Y_, 1.6, cls="s-bg", width=0, fill="#1c2330" if k != 1 else "#c2410c")
    y = 40 + fr[0].h + 22
    colorbar(s, 30, y, 200, LO, HI, [23, 24, 25, 26], "기온 (℃)")
    v = np.linspace(0.25, 0.5, 200)[None, :].repeat(6, 0)
    s.image_png(fr[1].x + 10, y, 200, 10, png(gray_rgb(v, 0.25, 0.5)))
    for t in (0.25, 0.3, 0.4, 0.5):
        X_ = fr[1].x + 10 + (t - 0.25) / 0.25 * 200
        s.line(X_, y + 10, X_, y + 14, cls="s-mu", width=1)
        s.text(X_, y + 25, f"{t:g}", size=10, cls="f-mu")
    s.text(fr[1].x + 110, y - 5, "표준편차 (℃)", size=10, cls="f-mu")
    s.save(os.path.join(OUT, "22-maps.svg"))


def fig_cv(out):
    names = ["IDW p=2", "박판 스플라인", "단순 크리깅", "정규 크리깅(구형)", "정규 크리깅(가우시안)", "보편 크리깅(선형 추세)", "지표온도 회귀", "회귀 크리깅"]
    W_, H = 720, 300
    s = Svg(W_, H, "왼쪽: 교차검증 RMSE. 지표온도를 쓰는 두 방법이 공간 보간만 하는 방법들보다 오차가 3분의 1 이하임. 오른쪽: 정규 크리깅(가우시안)의 표준화 오차"
                   "(오차 ÷ 크리깅 표준편차)의 분포와 표준정규분포. 표준편차가 오차의 크기를 대체로 잘 나타냄")
    ax = Axes(s, 190, 30, 170, 230, (0, 0.65), (-0.5, len(names) - 0.5))
    s.text(260, 18, "교차검증 RMSE (℃)", size=12, weight="600")
    for k, nm in enumerate(names):
        e = out[nm][0]
        v = np.sqrt(np.mean(e ** 2))
        y = float(ax.Y(len(names) - 1 - k))
        s.rect(float(ax.X(0)), y - 8, float(ax.X(v)) - float(ax.X(0)), 16, cls="s-bg f-ac" if "회귀" not in nm else "s-bg f-bd", width=0.5)
        s.text(float(ax.X(0)) - 6, y + 4, nm, size=10, anchor="end")
        s.text(float(ax.X(v)) + 4, y + 4, f"{v:.3f}", size=10, anchor="start")
    ax.xaxis(ticks=[0, 0.2, 0.4, 0.6], label="℃")
    e, v = out["정규 크리깅(가우시안)"]
    z = e / np.sqrt(v)
    edges = np.arange(-3.5, 3.6, 0.5)
    h = np.histogram(z, edges)[0]
    ax2 = Axes(s, 450, 40, 240, 200, (-3.5, 3.5), (0, max(h.max(), 10) * 1.2))
    s.text(570, 22, "표준화 오차 (정규 크리깅, 가우시안)", size=12, weight="600")
    ax2.hist(h, edges, width=0.5)
    xs = np.linspace(-3.5, 3.5, 141)
    ax2.curve(xs, N * 0.5 * np.exp(-xs ** 2 / 2) / np.sqrt(2 * np.pi), cls="s-bd", width=1.6)
    ax2.xaxis(ticks=[-3, -2, -1, 0, 1, 2, 3], label="오차 ÷ 크리깅 표준편차")
    ax2.yaxis(ticks=list(range(0, int(max(h.max(), 10) * 1.2) + 1, 2)), label="관측소 수")
    s.save(os.path.join(OUT, "22-cv.svg"))


if __name__ == "__main__":
    pg, ps, pr, rk = models()
    hand()
    out, maps = numbers(pg, ps, pr, rk)
    block(pg)
    fig_maps(maps)
    fig_cv(out)
