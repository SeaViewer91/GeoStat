"""23강 그림과 본문 수치.

- 23-sims.svg : 정규 크리깅 예측과 조건부 시뮬레이션 실현값 3개
- 23-exceed.svg : 기준 기온을 넘을 확률(크리깅 정규 근사 대 시뮬레이션), 기준을 넘는 면적과 그 안에 사는 고령인구의 분포
- 23-design.svg : 새 관측소 5곳을 어디에 둘까(평균 크리깅 분산 최소화 대 고령인구 가중)

베리오그램은 21~22강의 가우시안 모형(너깃 0.046, 부분 문턱값 0.81, 실효 상관거리 9.5 km)을 다시 적합해 씀.
조건부 시뮬레이션: 격자와 관측소 자리에서 무조건부 가우시안 장을 촐레스키 분해로 만들고,
"관측값의 크리깅 + (무조건부 장 − 무조건부 장의 관측소 값으로 한 크리깅)"으로 관측값에 맞춤.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/23.py
"""
import os
import sys
import warnings

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gskit import dist, empirical, fit_wls, gauss, grid, krige, sph, stations, window  # noqa: E402
from mapkit import MapFrame, colorbar, outline, png, ramp_rgb, to_array  # noqa: E402
from plotkit import Axes  # noqa: E402
from ppkit import pop_grid  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
WIN = window()
ST, X, Z = stations()
N = len(Z)
GS = 250.0
G, INSIDE, (GXS, GYS) = grid(WIN, GS)
M = len(G)
LO, HI = 23.0, 26.8
T = 25.5          # 기준 기온
NSIM = 500
CELL = GS * GS / 1e6  # 격자 한 칸 면적 km²


def model():
    E, _, _ = empirical(X, Z, 1500.0, 15000.0)
    p, _ = fit_wls(E, gauss, [0.05, 0.7, 9000])
    print(f"[0] 가우시안 모형: 너깃 {p[0]:.4f}, 부분 문턱값 {p[1]:.4f}, 실효 상관거리 {p[2]:.0f} m, 문턱값 {p[0] + p[1]:.4f}")
    return p


def ok_weights(Xs, X0, p):
    """정규 크리깅 가중치(관측소 × 예측점)와 크리깅 분산"""
    n = len(Xs)
    sill = p[0] + p[1]
    A = np.ones((n + 1, n + 1))
    A[:n, :n] = sill - gauss(dist(Xs, Xs), *p)
    A[n, n] = 0
    C0 = sill - gauss(dist(Xs, X0), *p)
    sol = np.linalg.solve(A, np.vstack([C0, np.ones((1, len(X0)))]))
    w, mu = sol[:n], sol[n]
    var = sill - np.sum(w * C0, 0) - mu
    return w, var


def simulate(p, rng):
    P = np.vstack([G, X])
    sill = p[0] + p[1]
    C = sill - gauss(dist(P, P), *p)
    L = np.linalg.cholesky(C + 1e-8 * np.eye(len(P)))
    U = L @ rng.standard_normal((len(P), NSIM))       # 무조건부 장 (평균 0)
    Ug, Ux = U[:M], U[M:]
    w, var = ok_weights(X, G, p)
    pred = w.T @ Z
    S = pred[:, None] + Ug - w.T @ Ux                 # 조건부 시뮬레이션
    return pred, var, S, U


def hand():
    print("[손계산] 크리깅 예측 25.2℃, 표준편차 0.30℃인 곳이 25.5℃를 넘을 확률")
    z = (25.5 - 25.2) / 0.30
    print(f"  z = {z:.2f}, P = 1 − Φ({z:.2f}) = {1 - norm.cdf(z):.4f}")
    for m_, s_ in ((25.4, 0.3), (25.6, 0.3), (25.2, 0.15)):
        print(f"  예측 {m_}, 표준편차 {s_}: P = {1 - norm.cdf((25.5 - m_) / s_):.4f}")
    m4 = np.array([25.6, 25.3, 25.2, 25.1])
    p4 = 1 - norm.cdf((25.5 - m4) / 0.3)
    print(f"  칸 넷(예측 {m4.tolist()}, 표준편차 0.3): 확률 {np.round(p4, 3).tolist()}, 합 {p4.sum():.3f}; 예측이 25.5를 넘는 칸 {(m4 > 25.5).sum()}개")
    print(f"  [연습] 예측 25.0, 표준편차 0.4: P(>25.5) = {1 - norm.cdf(1.25):.4f}, P(>24.5) = {1 - norm.cdf(-1.25):.4f}")


def pop_to_grid():
    pop, eld, tr = pop_grid()
    rows, cols = np.nonzero(pop > 0)
    cx = tr.c + (cols + 0.5) * tr.a
    cy = tr.f + (rows + 0.5) * tr.e
    _, idx = cKDTree(G).query(np.c_[cx, cy])
    gp = np.bincount(idx, weights=pop[rows, cols], minlength=M)
    ge = np.bincount(idx, weights=eld[rows, cols], minlength=M)
    return gp, ge


def numbers(p, pred, var, S, U):
    sd = np.sqrt(var)
    print(f"[1] 격자 {GS:.0f} m, 점 {M}개, 시뮬레이션 {NSIM}회")
    print(f"  관측소 중 {T}℃ 넘는 곳 {(Z > T).sum()}곳 / {N}")
    # 재현성 점검: 관측소 자리에서 조건부 시뮬레이션 = 관측값
    w, _ = ok_weights(X, X, p)
    Ss = (w.T @ Z)[:, None] + U[M:] - w.T @ U[M:]
    print(f"  관측소 자리 조건부 시뮬레이션과 관측값의 차이 최대 {np.abs(Ss - Z[:, None]).max():.2e}")
    # 시뮬레이션 평균·표준편차 대 크리깅
    print(f"  시뮬레이션 평균과 크리깅 예측의 차이: 평균 절대 {np.abs(S.mean(1) - pred).mean():.4f}, 최대 {np.abs(S.mean(1) - pred).max():.3f}")
    print(f"  시뮬레이션 표준편차와 크리깅 표준편차: 상관 {np.corrcoef(S.std(1), sd)[0, 1]:.3f}, 비 중앙값 {np.median(S.std(1) / sd):.3f}")
    # 지도 전체의 퍼짐: 크리깅 지도는 매끈함
    print(f"  격자값의 표준편차: 크리깅 지도 {pred.std():.3f}, 실현값 평균 {S.std(0).mean():.3f} (범위 {S.std(0).min():.3f}~{S.std(0).max():.3f}), 관측소 {Z.std():.3f}")
    print(f"  격자 최댓값: 크리깅 {pred.max():.2f}, 실현값 중앙값 {np.median(S.max(0)):.2f} (90% 구간 {np.quantile(S.max(0), 0.05):.2f}~{np.quantile(S.max(0), 0.95):.2f})")
    print(f"  격자 최솟값: 크리깅 {pred.min():.2f}, 실현값 중앙값 {np.median(S.min(0)):.2f}")
    # 실현값의 베리오그램 재현 (관측소와 같은 간격의 점 몇 개로)
    rng = np.random.default_rng(3)
    sub = rng.choice(M, 600, replace=False)
    Es = [empirical(G[sub], S[sub, k], 1500.0, 15000.0)[0] for k in range(20)]
    gm = np.mean([e[:, 1] for e in Es], 0)
    hh = Es[0][:, 0]
    print("  실현값 20개의 경험 베리오그램 평균 대 모형 (거리 km: 경험 / 모형)")
    print("   " + ", ".join(f"{h / 1000:.1f}: {g:.3f}/{float(gauss(h, *p)):.3f}" for h, g in zip(hh[::2], gm[::2])))
    # 초과 확률
    pk = 1 - norm.cdf((T - pred) / sd)
    ps = (S > T).mean(1)
    print(f"[2] {T}℃ 초과 확률: 크리깅 정규 근사와 시뮬레이션의 차이 평균 절대 {np.abs(pk - ps).mean():.4f}, 최대 {np.abs(pk - ps).max():.3f}")
    for a, b in ((0.0, 0.05), (0.05, 0.5), (0.5, 0.95), (0.95, 1.01)):
        m = (ps >= a) & (ps < b)
        print(f"   시뮬레이션 확률 {a:.2f}~{b:.2f}: 면적 {m.sum() * CELL:.1f} km²")
    print(f"   확률 0.9 이상 {np.sum(ps >= 0.9) * CELL:.1f} km², 0.5 이상 {np.sum(ps >= 0.5) * CELL:.1f} km², 0.1 이상 {np.sum(ps >= 0.1) * CELL:.1f} km²")
    # 면적
    a_k = np.sum(pred > T) * CELL
    a_s = (S > T).sum(0) * CELL
    print(f"  {T}℃ 넘는 면적: 크리깅 지도 {a_k:.1f} km², 실현값 중앙값 {np.median(a_s):.1f} (평균 {a_s.mean():.1f}, 90% 구간 {np.quantile(a_s, 0.05):.1f}~{np.quantile(a_s, 0.95):.1f}), 확률 합 {pk.sum() * CELL:.1f}")
    for t2 in (25.0, 26.0):
        ak2 = np.sum(pred > t2) * CELL
        as2 = (S > t2).sum(0) * CELL
        print(f"   기준 {t2}℃: 크리깅 {ak2:.1f} km², 실현값 중앙값 {np.median(as2):.1f} (90% {np.quantile(as2, 0.05):.1f}~{np.quantile(as2, 0.95):.1f})")
    # 고령인구 노출
    gp, ge = pop_to_grid()
    print(f"  인구 격자 합: 전체 {gp.sum():.0f}, 고령 {ge.sum():.0f}")
    e_k = ge[pred > T].sum()
    e_s = np.array([ge[S[:, k] > T].sum() for k in range(NSIM)])
    e_p = (ge * pk).sum()
    print(f"  {T}℃ 넘는 곳의 고령인구: 크리깅 지도 {e_k:.0f}명, 실현값 중앙값 {np.median(e_s):.0f} (90% 구간 {np.quantile(e_s, 0.05):.0f}~{np.quantile(e_s, 0.95):.0f}), 확률 가중 합 {e_p:.0f}")
    print(f"  고령인구 중 {T}℃ 넘는 곳 비율: 크리깅 {e_k / ge.sum():.1%}, 실현값 90% {np.quantile(e_s, 0.05) / ge.sum():.1%}~{np.quantile(e_s, 0.95) / ge.sum():.1%}")
    # 지시자 크리깅
    I = (Z > T).astype(float)
    Ei, _, _ = empirical(X, I, 1500.0, 15000.0)
    pi_, _ = fit_wls(Ei, sph, [0.02, 0.1, 8000])
    pik, _ = krige(X, I, G, sph, pi_, "ok")
    print(f"[3] 지시자 베리오그램(구형): 너깃 {pi_[0]:.4f}, 부분 문턱값 {pi_[1]:.4f}, 상관거리 {pi_[2]:.0f} m; 지시자 비율 {I.mean():.3f}, 분산 {I.var():.4f}")
    print(f"  지시자 크리깅 값 범위 {pik.min():.3f}~{pik.max():.3f} (0 미만 {np.sum(pik < 0)}개, 1 초과 {np.sum(pik > 1)}개 점), 시뮬레이션 확률과 상관 {np.corrcoef(np.clip(pik, 0, 1), ps)[0, 1]:.3f}")
    return pk, ps, a_k, a_s, e_k, e_s, ge, pik


def design(p, ge, k_add=5):
    print(f"[4] 새 관측소 {k_add}곳 배치 (후보: 1 km 격자점)")
    cand, _, _ = grid(WIN, 1000.0)
    _, var0 = ok_weights(X, G, p)
    wts = {"평균 크리깅 분산": np.ones(M) / M, "고령인구 가중": ge / ge.sum()}
    res = {}
    for name, wt in wts.items():
        cur = X.copy()
        hist = [float(np.sum(wt * var0))]
        chosen = []
        for _ in range(k_add):
            best = None
            for c in cand:
                if dist(c[None], cur).min() < 1.0:
                    continue
                _, v = ok_weights(np.vstack([cur, c]), G, p)
                o = float(np.sum(wt * v))
                if best is None or o < best[0]:
                    best = (o, c)
            cur = np.vstack([cur, best[1]])
            chosen.append(best[1])
            hist.append(best[0])
        _, v1 = ok_weights(cur, G, p)
        chosen = np.array(chosen)
        dmin = dist(chosen, X).min(1)
        print(f"  [{name}] 목적함수 {hist[0]:.4f} → " + " → ".join(f"{h:.4f}" for h in hist[1:]))
        print(f"   크리깅 표준편차: 평균 {np.sqrt(var0).mean():.3f} → {np.sqrt(v1).mean():.3f}, 최대 {np.sqrt(var0).max():.3f} → {np.sqrt(v1).max():.3f}; 고령인구 가중 평균 {np.sum(ge / ge.sum() * np.sqrt(var0)):.3f} → {np.sum(ge / ge.sum() * np.sqrt(v1)):.3f}")
        print(f"   고른 자리 {np.round(chosen).astype(int).tolist()}, 기존 관측소까지 거리 {np.round(dmin).astype(int).tolist()} m")
        res[name] = (chosen, v1, hist)
    # 무작위 5곳과 비교
    rng = np.random.default_rng(11)
    rr = []
    for _ in range(200):
        ok_c = cand[dist(cand, X).min(1) > 1.0]
        c = ok_c[rng.choice(len(ok_c), k_add, replace=False)]
        _, v = ok_weights(np.vstack([X, c]), G, p)
        rr.append(v.mean())
    rr = np.array(rr)
    print(f"  무작위 {k_add}곳 200번: 평균 크리깅 분산 중앙값 {np.median(rr):.4f} (범위 {rr.min():.4f}~{rr.max():.4f})")
    # 관측소 하나를 빼면
    loss = []
    for i in range(N):
        _, v = ok_weights(np.delete(X, i, 0), G, p)
        loss.append(v.mean() - var0.mean())
    loss = np.array(loss)
    print(f"  관측소 하나를 뺄 때 평균 크리깅 분산 증가: 최소 {loss.min():.5f} ({ST['관측소ID'][int(np.argmin(loss))]}), 최대 {loss.max():.5f} ({ST['관측소ID'][int(np.argmax(loss))]})")
    return res, var0


# ---------------------------------------------------------------- 그림
def place(s, fr, vals, fn, lo, hi):
    arr = to_array(vals, INSIDE)
    X0, Y0 = fr.xy(GXS[0] - GS / 2, GYS[-1] + GS / 2)
    X1, Y1 = fr.xy(GXS[-1] + GS / 2, GYS[0] - GS / 2)
    s.image_png(X0, Y0, X1 - X0, Y1 - Y0, png(fn(arr, lo, hi), int(2 * (X1 - X0))))


def gray_rgb(v, lo, hi):
    t = np.nan_to_num(np.clip((v - lo) / (hi - lo), 0, 1))
    c = (245 - 190 * t)[..., None]
    rgb = np.concatenate([c, c, c + 8 * (1 - t)[..., None]], -1)
    a = np.where(np.isnan(v), 0, 255)[..., None]
    return np.concatenate([rgb, a], -1).astype(np.uint8)


def gray_bar(s, x, y, w, lo, hi, ticks, label, fmt=lambda t: f"{t:g}"):
    v = np.linspace(lo, hi, 200)[None, :].repeat(6, 0)
    s.image_png(x, y, w, 10, png(gray_rgb(v, lo, hi)))
    for t in ticks:
        X_ = x + (t - lo) / (hi - lo) * w
        s.line(X_, y + 10, X_, y + 14, cls="s-mu", width=1)
        s.text(X_, y + 25, fmt(t), size=10, cls="f-mu")
    s.text(x + w / 2, y - 5, label, size=10, cls="f-mu")


def station_dots(s, fr, color="#1c2330", r=1.6, halo=False):
    for x, y in X:
        X_, Y_ = fr.xy(x, y)
        if halo:
            s.add(f'<circle cx="{X_:.1f}" cy="{Y_:.1f}" r="{r:.2f}" fill="{color}" stroke="#ffffff" stroke-width="0.8"/>')
        else:
            s.circle(X_, Y_, r, cls="s-bg", width=0, fill=color)


def fig_sims(pred, S):
    W_, H = 720, 250
    s = Svg(W_, H, "왼쪽: 정규 크리깅 예측(22강). 나머지 셋: 같은 베리오그램과 같은 관측값을 따르는 조건부 시뮬레이션 실현값. 관측소 자리에서는 모두 관측값과 같고, "
                   "관측소 사이에서는 실현값마다 다르게 출렁임(자잘한 얼룩은 너깃 몫). 크리깅 지도는 이런 실현값 수백 개의 평균이라 그 어느 것보다 매끈함")
    mw = 165
    fr = [MapFrame(WIN.bounds, 12 + k * (mw + 10), 34, mw) for k in range(4)]
    titles = ["크리깅 예측", "실현값 1", "실현값 2", "실현값 3"]
    vals = [pred, S[:, 0], S[:, 1], S[:, 2]]
    for k in range(4):
        place(s, fr[k], vals[k], ramp_rgb, LO, HI)
        outline(s, fr[k], WIN, cls="s-mu", width=0.8)
        station_dots(s, fr[k], r=1.3)
        s.text(fr[k].x + mw / 2, 22, titles[k], size=12, weight="600")
    colorbar(s, 260, 34 + fr[0].h + 20, 200, LO, HI, [23, 24, 25, 26], "8월 평균 기온 (℃)")
    s.save(os.path.join(OUT, "23-sims.svg"))


def fig_exceed(pk, ps, a_k, a_s, e_k, e_s):
    W_, H = 720, 356
    s = Svg(W_, H, f"왼쪽: 8월 평균 기온이 {T}℃를 넘을 확률(시뮬레이션 {NSIM}회 가운데 넘은 비율). 확률이 0에 가까운 곳이 시의 대부분이고, 1에 가까운 두 덩어리 둘레에 그 사이 값의 띠가 있음. "
                   f"가운데: 크리깅 예측과 표준편차에서 정규분포로 계산한 확률과의 비교. 가우시안 시뮬레이션이므로 거의 같은 것이 당연함. 오른쪽: {T}℃를 넘는 면적과 그 안에 사는 65세 이상 인구의 분포. "
                   "세로선은 크리깅 지도 한 장으로 센 값")
    fr = MapFrame(WIN.bounds, 15, 34, 230)
    place(s, fr, ps, ramp_rgb, 0, 1)
    outline(s, fr, WIN, cls="s-mu", width=0.8)
    station_dots(s, fr, r=2.0, halo=True)
    s.text(fr.x + 115, 22, f"{T}℃ 넘을 확률", size=12, weight="600")
    colorbar(s, 40, 34 + fr.h + 20, 180, 0, 1, [0, 0.5, 1], "확률")
    # 산점도 대신 두 확률 비교를 작은 축으로
    ax0 = Axes(s, 305, 70, 120, 120, (0, 1), (0, 1))
    s.text(365, 22, "두 확률의 비교", size=12, weight="600")
    sub = np.arange(0, len(pk), 9)
    for a, b in zip(pk[sub], ps[sub]):
        s.circle(float(ax0.X(a)), float(ax0.Y(b)), 1.3, cls="f-fg", width=0)
    ax0.curve(np.array([0, 1]), np.array([0, 1]), cls="s-bd", width=1, dash="3 3")
    ax0.xaxis(ticks=[0, 0.5, 1], label="정규 근사")
    ax0.yaxis(ticks=[0, 0.5, 1], label="시뮬레이션")
    # 면적 분포
    edges = np.linspace(np.floor(min(a_s.min(), a_k) / 5) * 5, np.ceil(max(a_s.max(), a_k) / 5) * 5, 25)
    h = np.histogram(a_s, edges)[0]
    ax1 = Axes(s, 480, 40, 210, 95, (edges[0], edges[-1]), (0, h.max() * 1.25))
    s.text(585, 22, f"{T}℃ 넘는 면적", size=12, weight="600")
    ax1.hist(h, edges, width=0.5)
    ax1.vline(a_k, cls="s-bd", width=1.6)
    ax1.xaxis(label="km²")
    s.text(float(ax1.X(a_k)) + 3, 52, "크리깅 지도", size=10, anchor="start", cls="f-bd")
    ee = e_s / 1000
    edges = np.linspace(np.floor(min(ee.min(), e_k / 1000) / 5) * 5, np.ceil(max(ee.max(), e_k / 1000) / 5) * 5, 25)
    h = np.histogram(ee, edges)[0]
    ax2 = Axes(s, 480, 220, 210, 95, (edges[0], edges[-1]), (0, h.max() * 1.25))
    s.text(585, 200, "그 안의 65세 이상 인구", size=12, weight="600")
    ax2.hist(h, edges, width=0.5)
    ax2.vline(e_k / 1000, cls="s-bd", width=1.6)
    ax2.xaxis(label="천 명")
    s.save(os.path.join(OUT, "23-exceed.svg"))


def fig_design(res, var0, ge):
    W_, H = 720, 300
    s = Svg(W_, H, "새 관측소 5곳을 하나씩 차례로 고른 결과(배경은 5곳을 더한 뒤의 크리깅 표준편차). 왼쪽: 시 전체의 평균 크리깅 분산을 가장 줄이는 자리. "
                   "관측소가 듬성한 가장자리로 감. 가운데: 65세 이상 인구로 가중한 분산을 줄이는 자리. 사람이 많은 곳의 빈틈으로 감. 오른쪽: 관측소를 더할 때 목적함수가 줄어드는 정도")
    mw = 220
    fr = [MapFrame(WIN.bounds, 15 + k * (mw + 13), 40, mw) for k in range(2)]
    names = ["평균 크리깅 분산", "고령인구 가중"]
    for k, nm in enumerate(names):
        chosen, v1, _ = res[nm]
        place(s, fr[k], np.sqrt(v1), gray_rgb, 0.25, 0.5)
        outline(s, fr[k], WIN, cls="s-mu", width=0.8)
        station_dots(s, fr[k])
        for j, (x, y) in enumerate(chosen):
            X_, Y_ = fr[k].xy(x, y)
            s.circle(X_, Y_, 6, cls="s-bg", width=0, fill="#c2410c")
            s.add(f'<text x="{X_:.1f}" y="{Y_ + 3.2:.1f}" font-size="9" font-weight="700" text-anchor="middle" fill="#ffffff">{j + 1}</text>')
        s.text(fr[k].x + mw / 2, 26, f"{nm} 최소화", size=12, weight="600")
    gray_bar(s, 120, 40 + fr[0].h + 22, 220, 0.25, 0.5, [0.25, 0.3, 0.4, 0.5], "크리깅 표준편차 (℃)", fmt=lambda t: f"{t:g}")
    ax = Axes(s, 530, 50, 160, 170, (0, 5), (0.8, 1.01))
    s.text(610, 26, "목적함수 (처음 = 1)", size=12, weight="600")
    for nm, cls, dash in ((names[0], "s-ac", None), (names[1], "s-bd", "5 3")):
        hst = np.array(res[nm][2])
        ax.curve(np.arange(6), hst / hst[0], cls=cls, width=1.8, dash=dash)
    ax.xaxis(ticks=[0, 1, 2, 3, 4, 5], label="더한 관측소 수")
    ax.yaxis(ticks=[0.8, 0.9, 1])
    s.line(520, 262, 540, 262, cls="s-ac", width=2)
    s.text(544, 266, "평균 분산", size=10, anchor="start")
    s.line(610, 262, 630, 262, cls="s-bd", width=2, dash="5 3")
    s.text(634, 266, "고령인구 가중", size=10, anchor="start")
    s.save(os.path.join(OUT, "23-design.svg"))


if __name__ == "__main__":
    p = model()
    hand()
    rng = np.random.default_rng(23)
    pred, var, S, U = simulate(p, rng)
    pk, ps, a_k, a_s, e_k, e_s, ge, pik = numbers(p, pred, var, S, U)
    res, var0 = design(p, ge)
    fig_sims(pred, S)
    fig_exceed(pk, ps, a_k, a_s, e_k, e_s)
    fig_design(res, var0, ge)
