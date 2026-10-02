"""부록 B 그림과 수치: 수학 준비의 손계산과 한빛시 예.

- 일렬로 이은 네 지역의 가중치 행렬로 공간 시차, Moran's I(이차형식), (I − ρW)⁻¹, 고유값
- 한빛시 퀸 가중치의 고유값과 ρ의 허용 범위
- 공간시차 모형의 집중 로그우도 곡선과 최댓값 (GeoStat 엔진의 추정값과 비교)
- B-loglik.svg

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/B.py
"""
import os
import sys
import warnings

import numpy as np
from scipy import optimize, stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from plotkit import Axes  # noqa: E402
from regkit import dense, fit, load_dong, queen, summ  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")


def small():
    A = np.array([[0, 1, 0, 0], [1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0]], float)
    W = A / A.sum(1, keepdims=True)
    x = np.array([1, 3, 5, 9.0])
    print("[손계산] 일렬의 네 지역 A–B–C–D, 행 표준화 W")
    print(np.round(W, 3))
    print(f"  x = {x.tolist()}, 공간 시차 Wx = {np.round(W @ x, 3).tolist()}")
    z = x - x.mean()
    n, S0 = len(x), W.sum()
    print(f"  z = {z.tolist()}, z'Wz = {z @ W @ z:.3f}, z'z = {z @ z:.3f}, S0 = {S0:.0f}, Moran's I = (n/S0)·z'Wz/z'z = {n / S0 * (z @ W @ z) / (z @ z):.4f}")
    M = np.linalg.inv(np.eye(4) - 0.5 * W)
    print("  (I − 0.5W)⁻¹ =")
    print(np.round(M, 3))
    print(f"  행 합 {np.round(M.sum(1), 3).tolist()} (= 1/(1 − 0.5) = 2)")
    S = np.eye(4) + 0.5 * W + 0.25 * W @ W + 0.125 * W @ W @ W
    print(f"  급수 I + 0.5W + 0.25W² + 0.125W³의 (1,1) 원소 {S[0, 0]:.3f}, 정확한 값 {M[0, 0]:.3f}")
    lam = np.sort(np.linalg.eigvals(W).real)
    print(f"  W의 고유값 {np.round(lam, 3).tolist()} → ρ의 범위 ({1 / lam[0]:.3f}, {1 / lam[-1]:.3f})")
    print(f"  log|I − 0.5W| = Σ log(1 − 0.5λ) = {np.sum(np.log(1 - 0.5 * lam)):.4f}, 직접 {np.log(np.linalg.det(np.eye(4) - 0.5 * W)):.4f}")
    y = np.array([2, 4, 6.0])
    s2 = y.var()
    ll = stats.norm.logpdf(y, y.mean(), np.sqrt(s2)).sum()
    print(f"[손계산] y = (2, 4, 6)의 정규 로그우도: 평균 4, 최대우도 분산 {s2:.4f} → log L = {ll:.4f} = −(3/2)log(2π·{s2:.4f}) − 3/2; AIC(모수 2) {-2 * ll + 4:.4f}")
    yp, n_ = np.array([3, 5, 1.0]), np.array([1.0, 2.0, 0.5])
    lam_hat = yp.sum() / n_.sum()
    llp = stats.poisson.logpmf(yp, lam_hat * n_).sum()
    print(f"[손계산] 포아송: 건수 (3, 5, 1), 노출 (1, 2, 0.5) → 비율의 최대우도 {lam_hat:.4f} = 9/3.5, log L {llp:.4f}")


def hanbit():
    d = load_dong()
    W = queen(d)
    Wd = dense(W)
    lam = np.linalg.eigvals(Wd).real
    print(f"[한빛시 퀸 W, 행 표준화] 고유값 최소 {lam.min():.4f}, 최대 {lam.max():.4f} → ρ의 범위 ({1 / lam.min():.4f}, 1)")
    y = d["출동률"].to_numpy()
    X = np.c_[np.ones(len(y)), d[["온도편차", "고령비율"]].to_numpy()]
    n = len(y)
    Wy = Wd @ y

    def cll(rho):
        e = (y - rho * Wy) - X @ np.linalg.lstsq(X, y - rho * Wy, rcond=None)[0]
        s2 = e @ e / n
        return -n / 2 * np.log(2 * np.pi * s2) - n / 2 + np.sum(np.log(1 - rho * lam))
    grid = np.linspace(1 / lam.min() + 0.01, 0.99, 300)
    vals = np.array([cll(r) for r in grid])
    r = optimize.minimize_scalar(lambda t: -cll(t), bounds=(1 / lam.min() + 1e-6, 0.999), method="bounded", options={"xatol": 1e-8})
    rep, _ = fit(d, "lag", "출동률", ["온도편차", "고령비율"], W)
    s = summ(rep)
    print(f"[집중 로그우도] 출동률 ~ 온도편차 + 고령비율의 공간시차 모형: 최대 ρ {r.x:.4f}, log L {-r.fun:.4f}")
    print(f"  GeoStat 엔진: ρ {s['ρ (공간시차 계수)']:.4f}, 로그우도 {s['로그우도']:.4f}")
    print(f"  ρ = 0 (OLS)일 때 log L {cll(0):.4f}, ρ = 0.5일 때 {cll(0.5):.4f}")
    return grid, vals, r.x, -r.fun, lam


def figure(grid, vals, rho, ll, lam):
    W_, H = 720, 280
    svg = Svg(W_, H, (f"공간시차 모형(출동률 ~ 온도편차 + 고령비율, 한빛시 퀸 가중치)의 집중 로그우도를 ρ에 따라 그림. 최댓값은 ρ = {rho:.3f}(로그우도 {ll:.2f})로 0 근처임. ".replace("-", "−") +
                     f"ρ가 1에 가까워지면 log|I − ρW|가 급히 작아져 로그우도가 떨어짐. 왼쪽 끝의 세로 점선은 W의 가장 작은 고유값으로 정해지는 ρ의 하한 1/λmin = {1 / lam.min():.3f}".replace("-", "−")))
    lo = max(vals.min(), ll - 40)
    ax = Axes(svg, 80, 30, 580, 190, (-1.85, 1.05), (lo, ll + 3))
    m = vals >= lo
    ax.curve(grid[m], vals[m], cls="s-ac", width=2)
    ax.vline(rho, cls="s-bd", width=1.2, dash="4 3")
    ax.vline(1 / lam.min(), cls="s-mu", width=1, dash="2 3")
    ax.vline(1.0, cls="s-mu", width=1, dash="2 3")
    svg.circle(float(ax.X(rho)), float(ax.Y(ll)), 4, cls="f-bd", width=0)
    svg.text(float(ax.X(rho)) + 8, float(ax.Y(ll)) + 14, f"최대 ρ = {rho:.3f}".replace("-", "−"), size=11, anchor="start", cls="f-bd")
    ax.xaxis(ticks=[-1.5, -1, -0.5, 0, 0.5, 1], label="ρ")
    ax.yaxis(label="집중 로그우도")
    svg.save(os.path.join(OUT, "B-loglik.svg"))


if __name__ == "__main__":
    small()
    out = hanbit()
    figure(*out)
