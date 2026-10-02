"""36강 그림과 본문 수치.

- 36-update.svg : 다솜23동과 마루16동의 사전분포·가능도·사후분포 (포아송-감마 켤레, 사전분포는 14강 EB의 적률 추정)
- 36-mcmc.svg   : 완전 베이즈 계층 모형의 MCMC (메트로폴리스, 체인 4개). 흔적 그림과 초모수의 사후분포
- 36-sim.svg    : 참값을 아는 모의에서 원비율·EB·완전 베이즈의 평균제곱오차와 95% 구간의 포함률

자료는 2025년 행정동별 출동 건수(PT_CNT)와 인구. 비율은 1만 명당, 인구 n은 만 명 단위.

실행 (GeoStat 엔진 환경에서, 1~2분):
    cd engine && uv run python ../book/fig-src/36.py
"""
import os
import sys
import warnings

import numpy as np
from scipy import optimize, special, stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from plotkit import Axes  # noqa: E402
from regkit import load_dong, rng  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
FOCUS = ["다솜23동", "마루16동"]


def load():
    d = load_dong()
    y = d["PT_CNT"].to_numpy(float)
    n = d["인구"].to_numpy(float) / 1e4
    return d, y, n


def moments(y, n):
    """14강의 EB 적률 추정 (esda Empirical_Bayes와 같음)"""
    r = y / n
    beta = y.sum() / n.sum()
    s2 = (n * (r - beta) ** 2).sum() / n.sum()
    alpha = s2 - beta / n.mean()
    return beta, s2, alpha


def nb_loglik(a, b, y, n):
    """주변 가능도: θ ~ Gamma(a, b), y | θ ~ Poisson(nθ) 를 θ에 대해 적분한 음이항분포. a, b는 배열이어도 됨"""
    a = np.asarray(a, float)[..., None]
    b = np.asarray(b, float)[..., None]
    ll = special.gammaln(a + y) - special.gammaln(a) - special.gammaln(y + 1) + a * np.log(b / (b + n)) + y * np.log(n / (b + n))
    return ll.sum(-1)


def ab_from(u, v):
    """u = log μ (사전 평균 비율), v = log c (동 사이 변동계수) → 감마의 모양 a, 비율 b"""
    c = np.exp(v)
    a = 1 / c ** 2
    return a, a / np.exp(u)


def log_prior(u, v, kind="기본"):
    c = np.exp(v)
    lp_u = stats.norm.logpdf(u, np.log(10), 2)  # 1만 명당 비율의 로그: 평균 log 10, 표준편차 2 (매우 넓음)
    if kind == "기본":  # c ~ 반정규(0, 1)
        lp_c = stats.halfnorm.logpdf(c, scale=1)
    elif kind == "균등":  # c ~ U(0, 5)
        lp_c = np.where(c < 5, -np.log(5), -np.inf)
    else:  # "강한": c ~ 반정규(0, 0.05) — 동 사이 차이가 거의 없다고 믿는 사전분포
        lp_c = stats.halfnorm.logpdf(c, scale=0.05)
    return lp_u + lp_c + v  # v = log c 로 바꾼 야코비안


# ---------------------------------------------------------------- 손계산
def hand(d, y, n):
    beta, s2, alpha = moments(y, n)
    a, b = beta ** 2 / alpha, beta / alpha
    print("[손계산] 14강 EB를 감마 사전분포로 읽기")
    print(f"  β̂ {beta:.4f}, s² {s2:.4f}, n̄ {n.mean():.4f}, α̂ {alpha:.4f} → a = β̂²/α̂ {a:.4f}, b = β̂/α̂ {b:.4f}")
    print(f"  사전 평균 a/b {a / b:.3f}, 사전 표준편차 √a/b {np.sqrt(a) / b:.3f}, 변동계수 1/√a {1 / np.sqrt(a):.4f}")
    print(f"  사전 95% 구간 {stats.gamma.ppf(0.025, a, scale=1 / b):.2f}~{stats.gamma.ppf(0.975, a, scale=1 / b):.2f}")
    out = {}
    for nm in FOCUS + ["누리12동"]:
        i = int(np.where(d["동이름"] == nm)[0][0])
        A, B = a + y[i], b + n[i]
        lo, hi = stats.gamma.ppf([0.025, 0.975], A, scale=1 / B)
        rlo = stats.chi2.ppf(0.025, 2 * y[i]) / 2 / n[i] if y[i] > 0 else 0.0
        rhi = stats.chi2.ppf(0.975, 2 * y[i] + 2) / 2 / n[i]
        pex = stats.gamma.sf(beta, A, scale=1 / B)
        w = n[i] / (b + n[i])
        print(f"  {nm}: 건수 {y[i]:.0f}, 인구 {n[i] * 1e4:.0f} (n {n[i]:.4f}), 원비율 {y[i] / n[i]:.2f} (정확 포아송 95% {rlo:.2f}~{rhi:.2f})")
        print(f"     사후 Gamma({A:.2f}, {B:.4f}): 평균 {A / B:.2f}, 표준편차 {np.sqrt(A) / B:.2f}, 95% {lo:.2f}~{hi:.2f}, P(θ > β̂) {pex:.3f}, 가중치 n/(b+n) {w:.4f}")
        out[nm] = dict(y=y[i], n=n[i], A=A, B=B)
    eb = (a + y) / (b + n)
    from esda.smoothing import Empirical_Bayes
    chk = Empirical_Bayes(y, n * 1e4).r.ravel() * 1e4
    print(f"  사후 평균 = esda EB: {np.allclose(eb, chk)} (최대 차이 {np.abs(eb - chk).max():.2e})")
    pex = stats.gamma.sf(beta, a + y, scale=1 / (b + n))
    print(f"  P(θ > β̂) ≥ 0.95인 동 {int((pex >= 0.95).sum())}개: {d['동이름'][pex >= 0.95].tolist()}")
    print(f"  원비율 > β̂인 동 {int((y / n > beta).sum())}개")
    return a, b, beta, out


# ---------------------------------------------------------------- 주변 최대우도 (2형 최대우도)
def ml(y, n, beta):
    f = lambda p: -nb_loglik(*ab_from(*p), y, n)  # noqa: E731
    r = optimize.minimize(f, [np.log(beta), np.log(0.3)], method="Nelder-Mead", options={"xatol": 1e-9, "fatol": 1e-9, "maxiter": 5000})
    a, b = ab_from(*r.x)
    print(f"[주변 최대우도] μ {np.exp(r.x[0]):.4f}, c {np.exp(r.x[1]):.4f} → a {a:.3f}, b {b:.4f}, α = a/b² {a / b ** 2:.3f}, 로그 가능도 {-r.fun:.3f}")
    return a, b


# ---------------------------------------------------------------- MCMC
def metropolis(y, n, kind="기본", chains=4, warm=2000, keep=5000, step=(0.05, 0.25), seed="mcmc"):
    r = rng(f"{seed}-{kind}")
    starts = np.array([[np.log(5), np.log(0.05)], [np.log(25), np.log(1.0)], [np.log(8), np.log(0.6)], [np.log(18), np.log(0.1)]])[:chains]
    U = np.zeros((chains, keep))
    V = np.zeros((chains, keep))
    acc = np.zeros(chains)
    for ch in range(chains):
        u, v = starts[ch]
        lp = nb_loglik(*ab_from(u, v), y, n) + log_prior(u, v, kind)
        for t in range(warm + keep):
            uu, vv = u + step[0] * r.standard_normal(), v + step[1] * r.standard_normal()
            lpp = nb_loglik(*ab_from(uu, vv), y, n) + log_prior(uu, vv, kind)
            if np.log(r.uniform()) < lpp - lp:
                u, v, lp = uu, vv, lpp
                if t >= warm:
                    acc[ch] += 1
            if t >= warm:
                U[ch, t - warm], V[ch, t - warm] = u, v
    return U, V, acc / keep


def split_rhat(x):
    m, n = x.shape
    h = n // 2
    s = np.vstack([x[:, :h], x[:, h:2 * h]])
    W = s.var(1, ddof=1).mean()
    B = h * s.mean(1).var(ddof=1)
    return np.sqrt(((h - 1) / h * W + B / h) / W)


def ess(x):
    """유효 표본 수 (Geyer의 초기 양수 수열, Stan과 같은 식)"""
    m, n = x.shape
    xc = x - x.mean(1, keepdims=True)
    f = np.fft.rfft(xc, 2 * n, axis=1)
    acov = np.fft.irfft(f * np.conj(f), axis=1)[:, :n] / n
    W = x.var(1, ddof=1).mean()
    B = n * x.mean(1).var(ddof=1)
    vp = (n - 1) / n * W + B / n
    rho = 1 - (W - acov.mean(0) * n / (n - 1)) / vp
    rho[0] = 1
    tau, t = -1.0, 0
    while t + 1 < n:
        p = rho[t] + rho[t + 1]
        if p < 0:
            break
        tau += 2 * p
        t += 2
    return m * n / tau


def full_bayes(d, y, n, beta, a_eb, b_eb):
    print("[MCMC] 완전 베이즈: θᵢ ~ Gamma(a, b), log μ ~ N(log 10, 2²), c ~ 반정규(0, 1); 체인 4개 × (예열 2,000 + 5,000)")
    U, V, acc = metropolis(y, n)
    mu, c = np.exp(U), np.exp(V)
    for nm, x in (("μ", mu), ("c", c)):
        print(f"  {nm}: 사후 평균 {x.mean():.4f}, 95% {np.quantile(x, 0.025):.4f}~{np.quantile(x, 0.975):.4f}, 분할 R-hat {split_rhat(x):.4f}, ESS {ess(x):.0f}")
    print(f"  채택률 {np.round(acc, 3).tolist()}")
    a, b = ab_from(U.ravel(), V.ravel())
    alpha = a / b ** 2
    print(f"  α = a/b² 사후 평균 {alpha.mean():.3f}, 95% {np.quantile(alpha, 0.025):.3f}~{np.quantile(alpha, 0.975):.3f} (EB 적률 {a_eb / b_eb ** 2:.3f})")
    print(f"  EB 적률 c {1 / np.sqrt(a_eb):.4f}, μ {a_eb / b_eb:.4f}")
    r = rng("fb-theta")
    th = r.gamma(a[:, None] + y[None], 1 / (b[:, None] + n[None]))  # 초모수 표본마다 θ를 정확히 뽑음
    fb_mean = th.mean(0)
    eb_mean = (a_eb + y) / (b_eb + n)
    pfb = (th > beta).mean(0)
    print(f"  완전 베이즈 P(θ > β̂) ≥ 0.95인 동 {int((pfb >= 0.95).sum())}개: {d['동이름'][pfb >= 0.95].tolist()}")
    print(f"  동별 사후 평균: 완전 베이즈와 EB의 최대 차이 {np.abs(fb_mean - eb_mean).max():.3f}, 상관 {np.corrcoef(fb_mean, eb_mean)[0, 1]:.5f}")
    for nm in FOCUS:
        i = int(np.where(d["동이름"] == nm)[0][0])
        lo, hi = np.quantile(th[:, i], [0.025, 0.975])
        elo, ehi = stats.gamma.ppf([0.025, 0.975], a_eb + y[i], scale=1 / (b_eb + n[i]))
        print(f"  {nm}: 완전 베이즈 평균 {fb_mean[i]:.2f}, 95% {lo:.2f}~{hi:.2f} (폭 {hi - lo:.2f}) / EB 평균 {eb_mean[i]:.2f}, 95% {elo:.2f}~{ehi:.2f} (폭 {ehi - elo:.2f}), P(θ>β̂) {np.mean(th[:, i] > beta):.3f}")
    # 사전분포 민감도
    sens = {}
    for kind in ("균등", "강한"):
        U2, V2, _ = metropolis(y, n, kind=kind)
        a2, b2 = ab_from(U2.ravel(), V2.ravel())
        th2 = r.gamma(a2[:, None] + y[None], 1 / (b2[:, None] + n[None]))
        i = int(np.where(d["동이름"] == "다솜23동")[0][0])
        cc = np.exp(V2)
        print(f"  사전분포 {kind}: c 사후 평균 {cc.mean():.4f} (95% {np.quantile(cc, 0.025):.4f}~{np.quantile(cc, 0.975):.4f}), R-hat {split_rhat(cc):.4f}, "
              f"다솜23동 평균 {th2[:, i].mean():.2f}, 95% {np.quantile(th2[:, i], 0.025):.2f}~{np.quantile(th2[:, i], 0.975):.2f}, "
              f"동별 평균의 범위 {th2.mean(0).min():.2f}~{th2.mean(0).max():.2f}")
        sens[kind] = cc
    print(f"  (기본 사전분포의 동별 평균 범위 {fb_mean.min():.2f}~{fb_mean.max():.2f}, EB {eb_mean.min():.2f}~{eb_mean.max():.2f})")
    return U, V


# ---------------------------------------------------------------- 모의
GU = np.linspace(-0.6, 0.6, 61)  # log μ − log β̂ 둘레
GV = np.linspace(np.log(0.01), np.log(1.5), 81)


def grid_posterior(y, n):
    bh = np.log(y.sum() / n.sum())
    U, V = np.meshgrid(bh + GU, GV, indexing="ij")
    a, b = ab_from(U, V)
    lp = nb_loglik(a, b, y, n) + log_prior(U, V)
    w = np.exp(lp - lp.max()).ravel()
    return a.ravel(), b.ravel(), w / w.sum()


def simulate(y, n, a0, b0, R=400):
    """참 θᵢ ~ Gamma(a0, b0) (EB 적률 추정값), 인구는 실제 동 인구. 원비율·EB·완전 베이즈(격자 근사) 비교"""
    r = rng("sim36")
    N = len(n)
    q = np.digitize(n, np.quantile(n, [0.25, 0.5, 0.75]))  # 인구 4분위 0~3
    err = {k: np.zeros((R, N)) for k in ("원비율", "EB", "완전 베이즈")}
    cov = {k: np.zeros((R, N), bool) for k in err}
    width = {k: np.zeros((R, N)) for k in err}
    trues = np.zeros((R, N))
    hi_true = np.zeros((R, N), bool)
    cut = stats.gamma.ppf(0.9, a0, scale=1 / b0)
    for t in range(R):
        th = r.gamma(a0, 1 / b0, N)
        ys = r.poisson(n * th).astype(float)
        trues[t] = th
        hi_true[t] = th > cut
        raw = ys / n
        rlo = np.where(ys > 0, stats.chi2.ppf(0.025, 2 * ys) / 2 / n, 0.0)
        rhi = stats.chi2.ppf(0.975, 2 * ys + 2) / 2 / n
        bt, _, al = moments(ys, n)
        if al > 0:
            A, B = bt ** 2 / al + ys, bt / al + n
            eb = A / B
            elo, ehi = stats.gamma.ppf(0.025, A, scale=1 / B), stats.gamma.ppf(0.975, A, scale=1 / B)
        else:
            eb = elo = ehi = np.full(N, bt)
        ga, gb, gw = grid_posterior(ys, n)
        fb = (gw[:, None] * (ga[:, None] + ys) / (gb[:, None] + n)).sum(0)
        idx = r.choice(len(gw), 1500, p=gw)
        draws = r.gamma(ga[idx][:, None] + ys, 1 / (gb[idx][:, None] + n))
        flo, fhi = np.quantile(draws, [0.025, 0.975], axis=0)
        for k, (est, lo, hi) in {"원비율": (raw, rlo, rhi), "EB": (eb, elo, ehi), "완전 베이즈": (fb, flo, fhi)}.items():
            err[k][t] = est - th
            cov[k][t] = (lo <= th) & (th <= hi)
            width[k][t] = hi - lo
    print(f"[모의] 참 θ ~ Gamma({a0:.2f}, {b0:.4f}), 실제 인구, {R}회. 인구 4분위별 평균제곱오차 / 95% 구간 포함률 / 평균 폭")
    res = {}
    for k in err:
        mse = [float((err[k][:, q == g] ** 2).mean()) for g in range(4)]
        cv = [float(cov[k][:, q == g].mean()) for g in range(4)]
        wd = [float(width[k][:, q == g].mean()) for g in range(4)]
        tot = float((err[k] ** 2).mean())
        hic = float(cov[k][hi_true & (q == 0)[None]].mean())
        hic_all = float(cov[k][hi_true].mean())
        print(f"  {k}: MSE {np.round(mse, 2).tolist()} (전체 {tot:.2f}), 포함률 {np.round(cv, 3).tolist()} (전체 {cov[k].mean():.3f}), 폭 {np.round(wd, 1).tolist()}")
        print(f"     참 θ가 상위 10%(>{cut:.2f})인 경우 포함률: 전체 {hic_all:.3f}, 인구 1분위 {hic:.3f}")
        res[k] = dict(mse=mse, cov=cv, tot=tot, hic=hic, hic_all=hic_all)
    rel = res["EB"]["tot"] / res["원비율"]["tot"]
    print(f"  EB의 전체 MSE는 원비율의 {rel:.3f}배")
    # 순위: 참 상위 10개 동을 얼마나 맞히나
    return res, cut


# ---------------------------------------------------------------- 그림
def fig_update(out, a, b, beta):
    W_, H = 720, 310
    svg = Svg(W_, H, "포아송-감마 켤레로 본 베이즈 갱신. 점선: 사전분포 Gamma(13.37, 1.14)(14강 EB의 적률 추정, 모든 동에 같음). 회색: 가능도(자료만의 정보, 넓이를 1로 맞춤). 파란 실선: 사후분포. "
                     "왼쪽 다솜23동(인구 1,013명, 5건): 가능도가 넓어 사후분포가 사전분포 가까이에 있음(사후 평균 14.80). "
                     "오른쪽 마루16동: 가능도가 좁아 사후분포가 사전분포와 가능도의 중간쯤으로 크게 옮겨감(사후 평균 20.26). 세로 점선은 도시 전체 비율 11.73")
    xs = np.linspace(0.01, 70, 600)
    for k, nm in enumerate(FOCUS):
        o = out[nm]
        prior = stats.gamma.pdf(xs, a, scale=1 / b)
        lik = stats.gamma.pdf(xs, o["y"] + 1, scale=1 / o["n"])  # θ에 대한 가능도를 넓이 1로 (평평한 사전분포의 사후와 같은 꼴)
        post = stats.gamma.pdf(xs, o["A"], scale=1 / o["B"])
        ymax = max(prior.max(), lik.max(), post.max()) * 1.1
        ax = Axes(svg, 50 + k * 350, 46, 290, 190, (0, 70), (0, ymax))
        ax.curve(xs, prior, cls="s-mu", width=1.6, dash="5 4")
        ax.curve(xs, lik, cls="s-mu", width=2.2)
        ax.curve(xs, post, cls="s-ac", width=2.4)
        ax.vline(beta, cls="s-mu", width=1, dash="2 3")
        ax.xaxis(ticks=[0, 10, 20, 30, 40, 50, 60, 70], label="출동률 θ (1만 명당)")
        svg.text(ax.x0 + 145, 30, f"{nm}: {o['y']:.0f}건 / {o['n'] * 1e4:,.0f}명 (원비율 {o['y'] / o['n']:.2f})", size=12, weight="600")
        mx = float(ax.X(o["A"] / o["B"]))
        svg.text(mx + 8, float(ax.Y(post.max())) + 4, f"사후 평균 {o['A'] / o['B']:.2f}", size=10, cls="f-ac", anchor="start")
    y0 = H - 12
    x = 160
    for cls, dash, lab in (("s-mu", "5 4", "사전분포"), ("s-mu", None, "가능도"), ("s-ac", None, "사후분포")):
        svg.line(x, y0 - 4, x + 26, y0 - 4, cls=cls, width=2.2, dash=dash)
        svg.text(x + 32, y0, lab, size=11, anchor="start")
        x += 140
    svg.save(os.path.join(OUT, "36-update.svg"))


def fig_mcmc(U, V, a_eb, b_eb, a_ml, b_ml):
    W_, H = 720, 295
    c = np.exp(V)
    mu = np.exp(U)
    svg = Svg(W_, H, f"완전 베이즈 계층 모형의 MCMC(메트로폴리스, 체인 4개, 예열 뒤 5,000번씩). 왼쪽: 동 사이 변동계수 c의 흔적 그림. 처음 300번만 그림. 네 체인이 섞여 같은 범위를 오감(분할 R-hat {split_rhat(c):.3f}). "
                     f"가운데·오른쪽: 사전 평균 비율 μ와 변동계수 c의 사후분포. 세로선은 14강 EB의 적률 추정값(실선)과 주변 최대우도 추정값(점선). EB는 이 분포의 한 점만 쓰고 불확실성을 버림")
    cls = ["s-ac", "s-bd", "s-ok", "s-mu"]
    T = 300
    ax = Axes(svg, 50, 40, 250, 170, (0, T), (0, 0.6))
    for ch in range(4):
        ax.curve(np.arange(T), c[ch, :T], cls=cls[ch], width=0.9)
    ax.xaxis(ticks=[0, 100, 200, 300], label="반복")
    ax.yaxis(ticks=[0, 0.2, 0.4, 0.6], label="c")
    for k, (x, lab, lim, ticks, eb, mlv) in enumerate(((mu, "μ (1만 명당)", (9.5, 14.5), [10, 11, 12, 13, 14], a_eb / b_eb, a_ml / b_ml),
                                                         (c, "변동계수 c", (0, 0.5), [0, 0.1, 0.2, 0.3, 0.4, 0.5], 1 / np.sqrt(a_eb), 1 / np.sqrt(a_ml)))):
        edges = np.linspace(*lim, 41)
        h, _ = np.histogram(x.ravel(), edges)
        ax2 = Axes(svg, 350 + k * 190, 40, 160, 170, lim, (0, h.max() * 1.1))
        ax2.hist(h, edges, cls="s-bg f-ac", width=0.4)
        ax2.vline(eb, cls="s-bd", width=1.6)
        ax2.vline(mlv, cls="s-fg", width=1.2, dash="3 3")
        ax2.xaxis(ticks=ticks, label=lab)
    svg.line(360, H - 16, 386, H - 16, cls="s-bd", width=1.6)
    svg.text(392, H - 12, "EB 적률 추정", size=11, anchor="start")
    svg.line(510, H - 16, 536, H - 16, cls="s-fg", width=1.2, dash="3 3")
    svg.text(542, H - 12, "주변 최대우도", size=11, anchor="start")
    svg.save(os.path.join(OUT, "36-mcmc.svg"))


def fig_sim(res, cut):
    W_, H = 720, 300
    svg = Svg(W_, H, f"참값을 아는 모의 400회(참 출동률을 감마분포에서 뽑고, 실제 동 인구로 건수를 만듦). 왼쪽: 인구 4분위별 평균제곱오차. 인구가 적을수록 원비율의 오차가 크고, EB와 완전 베이즈가 크게 줄임. "
                     f"오른쪽: 95% 구간이 참값을 포함한 비율. 원비율(정확 포아송 구간)은 95%를 넘고, EB와 완전 베이즈는 평균으로 95% 가까이 맞음. "
                     f"그러나 참 비율이 상위 10%인 동만 보면, 인구 1분위에서 EB {res['EB']['hic']:.0%}, 완전 베이즈 {res['완전 베이즈']['hic']:.0%}로 크게 모자람(평균 쪽으로 당겨서)")
    keys = ["원비율", "EB", "완전 베이즈"]
    cls = ["f-mu", "f-bd", "f-ac"]
    groups = ["1분위", "2분위", "3분위", "4분위"]
    mx = max(max(res[k]["mse"]) for k in keys)
    ax = Axes(svg, 60, 40, 280, 180, (-0.5, 3.5), (0, mx * 1.08))
    for g in range(4):
        for j, k in enumerate(keys):
            x0 = float(ax.X(g - 0.3 + j * 0.2))
            v = res[k]["mse"][g]
            svg.rect(x0, float(ax.Y(v)), float(ax.X(0.18) - ax.X(0)), float(ax.Y(0) - ax.Y(v)), cls=f"s-bg {cls[j]}", width=0.5)
        svg.text(float(ax.X(g)), 236, groups[g], size=10, cls="f-mu")
    ax.yaxis(label="평균제곱오차")
    svg.text(200, 254, "인구 4분위 (1분위 = 가장 적음)", size=11, cls="f-mu")
    groups2 = groups + ["상위 10%·1분위"]
    ax2 = Axes(svg, 420, 40, 280, 180, (-0.5, 4.5), (0, 1.05))
    for g in range(5):
        for j, k in enumerate(keys):
            v = res[k]["cov"][g] if g < 4 else res[k]["hic"]
            x0 = float(ax2.X(g - 0.3 + j * 0.2))
            svg.rect(x0, float(ax2.Y(v)), float(ax2.X(0.18) - ax2.X(0)), float(ax2.Y(0) - ax2.Y(v)), cls=f"s-bg {cls[j]}", width=0.5)
        svg.text(float(ax2.X(g)), 236, groups2[g] if g < 4 else "상위 10%", size=10, cls="f-mu")
    svg.text(float(ax2.X(4)), 249, "(1분위)", size=10, cls="f-mu")
    ax2.vline(-0.5, cls="s-mu", width=0.5)
    svg.line(float(ax2.X(-0.5)), float(ax2.Y(0.95)), float(ax2.X(4.5)), float(ax2.Y(0.95)), cls="s-fg", width=1, dash="4 3")
    ax2.yaxis(ticks=[0, 0.25, 0.5, 0.75, 0.95], label="95% 구간 포함률")
    x = 150
    for c, k in zip(cls, keys):
        svg.rect(x, H - 31, 12, 12, cls=f"s-mu {c}", width=0.5)
        svg.text(x + 18, H - 21, k, size=11, anchor="start")
        x += 150
    svg.save(os.path.join(OUT, "36-sim.svg"))


if __name__ == "__main__":
    d, y, n = load()
    a, b, beta, out = hand(d, y, n)
    a_ml, b_ml = ml(y, n, beta)
    U, V = full_bayes(d, y, n, beta, a, b)
    fig_update(out, a, b, beta)
    fig_mcmc(U, V, a, b, a_ml, b_ml)
    res, cut = simulate(y, n, a, b)
    fig_sim(res, cut)
