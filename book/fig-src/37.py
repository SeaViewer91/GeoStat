"""37강 그림과 본문 수치.

- 37-maps.svg    : 연령 표준화 SMR, 포아송-감마 EB, BYM2 사후 상대위험, BYM2 초과 확률 P(RR > 1)
- 37-confound.svg: 온도편차 계수(1℃당 상대위험)의 모형별 비교와 BYM2의 공간 비율 φ의 사후분포

자료는 2025년 행정동별 출동 건수와 연령 표준화 기대 건수(14강의 간접 표준화: 65세 이상과 미만의 도시 전체 비율).
모형은 PyMC(NUTS)로 적합함. 결과 요약은 37-fit.npz에 저장해 두고 다시 쓰며, 지우면 새로 적합함.

실행 (GeoStat 엔진 환경에 PyMC를 얹어서, 처음에는 몇 분 걸림):
    cd engine && uv run --with "pymc==5.28.5" --with "arviz==0.23.4" python ../book/fig-src/37.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import DATA, load_dong, queen  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
CACHE = os.path.join(HERE, "37-fit.npz")
SEED = 20261002


def load():
    d = load_dong()
    ev = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
    j = gpd.sjoin(ev, d[["geometry"]], predicate="within")
    old = (j["연령대"] == "65+").groupby(j["index_right"]).sum().reindex(d.index, fill_value=0).to_numpy(float)
    y = d["PT_CNT"].to_numpy(float)
    pop, p65 = d["인구"].to_numpy(float), d["고령인구"].to_numpy(float)
    r65, ru = old.sum() / p65.sum(), (y - old).sum() / (pop - p65).sum()
    E = p65 * r65 + (pop - p65) * ru
    W = queen(d)
    A = (W.full()[0] > 0).astype(float)
    return d, y, E, A, W, (r65, ru)


# ---------------------------------------------------------------- 손계산
def hand(A):
    print("[손계산] ICAR의 조건부 분포: 이웃 4개의 값 0.2, 0.1, 0.3, −0.2")
    u = np.array([0.2, 0.1, 0.3, -0.2])
    print(f"  조건부 평균 {u.mean():.3f}, 조건부 분산 σ²/4")
    print("[손계산] 일렬로 이은 네 지역 A–B–C–D의 정밀도 행렬 Q = D − W")
    Wt = np.array([[0, 1, 0, 0], [1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0]], float)
    Q = np.diag(Wt.sum(1)) - Wt
    print(Q.astype(int))
    print(f"  행 합 {Q.sum(1).tolist()}, 행렬식 {np.linalg.det(Q):.3g}, 고유값 {np.round(np.linalg.eigvalsh(Q), 3).tolist()}")
    Qp = np.diag(Wt.sum(1)) - 0.9 * Wt
    print(f"  고유 CAR(ρ = 0.9) Q = D − 0.9W 의 행렬식 {np.linalg.det(Qp):.4f}, 공분산 대각 {np.round(np.diag(np.linalg.inv(Qp)), 3).tolist()}")
    g = ginv_diag(Q)
    print(f"  ICAR(합 0 제약) 주변 분산 {np.round(g, 4).tolist()}, 기하 평균(척도 인자) {np.exp(np.mean(np.log(g))):.4f}")


def ginv_diag(Q):
    """합 0 제약 아래 ICAR의 주변 분산 = Q의 일반화 역행렬 대각 (영 고유값 하나를 뺌, 연결된 그래프)"""
    lam, V = np.linalg.eigh(Q)
    keep = lam > 1e-8 * lam.max()
    return (V[:, keep] ** 2 / lam[keep]).sum(1)


def scaling_factor(A):
    Q = np.diag(A.sum(1)) - A
    return float(np.exp(np.mean(np.log(ginv_diag(Q)))))


# ---------------------------------------------------------------- 모형 적합
def fit_all(d, y, E, A):
    import arviz as az
    import pymc as pm
    import pytensor.tensor as pt

    x = d["온도편차"].to_numpy(float)
    s = scaling_factor(A)
    print(f"  BYM2 척도 인자(한빛시 퀸 인접) {s:.4f}")
    res = {}
    idatas = {}

    def run(name, cov, kind):
        with pm.Model():
            b0 = pm.Normal("b0", 0, 1)
            eta = b0 + pt.log(E)
            if cov:
                b1 = pm.Normal("b1", 0, 1)
                eta = eta + b1 * x
            if kind == "iid":
                sig = pm.HalfNormal("sigma", 1)
                v = pm.Normal("v", 0, 1, shape=len(y))
                re = pm.Deterministic("re", sig * v)
                eta = eta + re
            elif kind == "bym2":
                sig = pm.HalfNormal("sigma", 1)
                phi = pm.Beta("phi", 1, 1)
                v = pm.Normal("v", 0, 1, shape=len(y))
                u = pm.ICAR("u", W=A, sigma=1)
                re = pm.Deterministic("re", sig * (pt.sqrt(1 - phi) * v + pt.sqrt(phi / s) * u))
                pm.Deterministic("re_s", sig * pt.sqrt(phi / s) * u)
                eta = eta + re
            pm.Deterministic("rr", pt.exp(eta - pt.log(E)))
            pm.Poisson("y", mu=pt.exp(eta), observed=y)
            idata = pm.sample(2000, tune=2000, chains=4, cores=2, target_accept=0.95, random_seed=SEED,
                              progressbar=False, idata_kwargs={"log_likelihood": True})
        post = idata.posterior
        names = [v for v in ("b0", "b1", "sigma", "phi") if v in post]
        sm = az.summary(idata, var_names=names + (["re"] if kind else []))
        div = int(idata.sample_stats["diverging"].sum())
        rr = post["rr"].stack(s=("chain", "draw")).values  # (N, S)
        out = dict(rr_mean=rr.mean(1), rr_lo=np.quantile(rr, 0.025, 1), rr_hi=np.quantile(rr, 0.975, 1), pex=(rr > 1).mean(1),
                   rhat=float(sm["r_hat"].max()), ess=float(sm["ess_bulk"].min()), div=div)
        for v in names:
            dr = post[v].values.ravel()
            out[v] = dr
        if kind:
            out["re_mean"] = post["re"].mean(("chain", "draw")).values
        if kind == "bym2":
            out["re_s_mean"] = post["re_s"].mean(("chain", "draw")).values
        loo = az.loo(idata)
        waic = az.waic(idata)
        out["elpd_loo"], out["se_loo"], out["p_loo"] = float(loo.elpd_loo), float(loo.se), float(loo.p_loo)
        out["waic"], out["p_waic"] = float(-2 * waic.elpd_waic), float(waic.p_waic)
        out["pareto_k_bad"] = int((loo.pareto_k.values > 0.7).sum())
        res[name] = out
        idatas[name] = idata
        print(f"  [{name}] 최대 R-hat {out['rhat']:.3f}, 최소 ESS {out['ess']:.0f}, 발산 {div}, elpd_loo {out['elpd_loo']:.2f} (SE {out['se_loo']:.2f}, p_loo {out['p_loo']:.1f}, k>0.7 {out['pareto_k_bad']}), WAIC {out['waic']:.2f}")

    print("[적합] PyMC NUTS, 체인 4개 × (예열 2,000 + 2,000), target_accept 0.95")
    run("포아송", True, None)
    run("독립", False, "iid")
    run("BYM2", False, "bym2")
    run("독립+온도", True, "iid")
    run("BYM2+온도", True, "bym2")
    flat = {}
    for m, o in res.items():
        for k, v in o.items():
            flat[f"{m}|{k}"] = np.asarray(v, np.float32) if np.ndim(v) else np.asarray(v)
    flat["scale"] = np.array(s)
    np.savez_compressed(CACHE, **flat)
    return res


def load_cache():
    z = np.load(CACHE)
    res = {}
    for k in z.files:
        if "|" not in k:
            continue
        m, v = k.split("|")
        res.setdefault(m, {})[v] = z[k] if z[k].ndim else z[k].item()
    return res


# ---------------------------------------------------------------- 요약
def report(d, y, E, W, rates, res):
    from esda import Moran
    nm = d["동이름"].to_numpy()
    smr = y / E
    r65, ru = rates
    print(f"[자료] 65세 이상 {r65 * 1e4:.2f}, 미만 {ru * 1e4:.2f} (1만 명당). 기대 건수 합 {E.sum():.1f}, 범위 {E.min():.2f}~{E.max():.2f}, SMR 범위 {smr.min():.2f}~{smr.max():.2f}")
    print(f"  기대 건수 5 미만인 동 {int((E < 5).sum())}개, 출동 0건인 동 {int((y == 0).sum())}개")
    # 포아송-감마 EB (상대위험, 적률)
    beta = y.sum() / E.sum()
    s2 = (E * (smr - beta) ** 2).sum() / E.sum()
    alpha = s2 - beta / E.mean()
    a, b = beta ** 2 / alpha, beta / alpha
    eb = (a + y) / (b + E)
    print(f"  포아송-감마 EB(SMR): β̂ {beta:.4f}, α̂ {alpha:.4f}, a {a:.3f}, b {b:.3f}, EB 범위 {eb.min():.3f}~{eb.max():.3f}")
    res["EB"] = dict(rr_mean=eb, pex=stats.gamma.sf(1, a + y, scale=1 / (b + E)))
    def I(v):
        np.random.seed(123456789)
        return Moran(v, W, permutations=999)
    m = I(smr)
    print(f"  SMR Moran's I {m.I:.4f} (p {m.p_sim:.3f})")
    for k in ("독립", "BYM2", "독립+온도", "BYM2+온도"):
        o = res[k]
        txt = ", ".join(f"{v} {np.mean(o[v]):.3f} ({np.quantile(o[v], 0.025):.3f}~{np.quantile(o[v], 0.975):.3f})" for v in ("b1", "sigma", "phi") if v in o)
        mi = I(o["re_mean"])
        print(f"  [{k}] {txt}; 상대위험 범위 {o['rr_mean'].min():.3f}~{o['rr_mean'].max():.3f}; 랜덤효과 사후 평균의 Moran's I {mi.I:.4f} (p {mi.p_sim:.3f})")
    o = res["포아송"]
    print(f"  [포아송] b1 {np.mean(o['b1']):.4f} ({np.quantile(o['b1'], 0.025):.4f}~{np.quantile(o['b1'], 0.975):.4f})")
    print("  온도편차 1℃당 상대위험 exp(b1):")
    for k in ("포아송", "독립+온도", "BYM2+온도"):
        e = np.exp(res[k]["b1"])
        print(f"    {k}: {e.mean():.4f} (95% {np.quantile(e, 0.025):.4f}~{np.quantile(e, 0.975):.4f}), 사후 sd(b1) {np.std(res[k]['b1']):.4f}")
    print("  모형 비교 (elpd_loo 클수록 좋음, WAIC 작을수록 좋음):")
    for k in ("포아송", "독립", "BYM2", "독립+온도", "BYM2+온도"):
        o = res[k]
        print(f"    {k}: elpd_loo {o['elpd_loo']:.2f} (SE {o['se_loo']:.2f}), p_loo {o['p_loo']:.1f}, WAIC {o['waic']:.2f}, p_waic {o['p_waic']:.1f}")
    print("  초과 확률:")
    for k in ("EB", "독립", "BYM2", "BYM2+온도"):
        pe = res[k]["pex"]
        print(f"    {k}: P(RR>1) ≥ 0.95 {int((pe >= 0.95).sum())}개 {sorted(nm[pe >= 0.95].tolist())}; ≥ 0.8 {int((pe >= 0.8).sum())}개")
    for dn in ("다솜23동", "마루16동", "누리12동", "다솜1동"):
        i = int(np.where(nm == dn)[0][0])
        nb = W.neighbors[i]
        print(f"  {dn}: 관측 {y[i]:.0f}, 기대 {E[i]:.2f}, SMR {smr[i]:.3f}, 이웃 SMR(합 기준) {y[nb].sum() / E[nb].sum():.3f}, EB {eb[i]:.3f}, "
              f"독립 {res['독립']['rr_mean'][i]:.3f}, BYM2 {res['BYM2']['rr_mean'][i]:.3f} ({res['BYM2']['rr_lo'][i]:.3f}~{res['BYM2']['rr_hi'][i]:.3f}), "
              f"P(RR>1) {res['BYM2']['pex'][i]:.3f}")
    # 독립 모형과 BYM2의 차이가 큰 동
    diff = res["BYM2"]["rr_mean"] - res["독립"]["rr_mean"]
    o = np.argsort(-np.abs(diff))[:5]
    print("  독립 대 BYM2 차이가 큰 동:", [(nm[i], round(float(smr[i]), 2), round(float(res['독립']['rr_mean'][i]), 3), round(float(res['BYM2']['rr_mean'][i]), 3)) for i in o])
    print(f"  BYM2 상대위험과 SMR의 상관 {np.corrcoef(res['BYM2']['rr_mean'], smr)[0, 1]:.3f}, EB와의 상관 {np.corrcoef(res['BYM2']['rr_mean'], eb)[0, 1]:.3f}")
    return smr, eb


# ---------------------------------------------------------------- 그림
RR_BREAKS = [1 / 1.5, 1 / 1.2, 1, 1.2, 1.5]
RR_LAB = ["0.67 미만", "0.67~0.83", "0.83~1", "1~1.2", "1.2~1.5", "1.5 이상"]


def fig_maps(d, smr, eb, res):
    o = res["BYM2"]
    W_, H = 720, int(34 + 2 * (MapFrame(d.total_bounds, 0, 0, 300).h + 36) + 34)
    svg = Svg(W_, H, f"출동의 상대위험 지도(연령 표준화, 1이 도시 평균). 왼쪽 위: 원래의 SMR(관측 ÷ 기대). 인구 적은 동의 극단값이 많음(범위 {smr.min():.2f}~{smr.max():.2f}). "
                     f"오른쪽 위: 포아송-감마 EB(도시 평균 쪽으로 당김, {eb.min():.2f}~{eb.max():.2f}). 왼쪽 아래: BYM2 사후 평균(이웃과 도시 평균 쪽으로 당김, {o['rr_mean'].min():.2f}~{o['rr_mean'].max():.2f}). "
                     f"마루구 원도심과 가람·누리구 경계의 높은 덩어리, 북쪽 가장자리와 동쪽 다솜구의 낮은 곳이 또렷해짐. 오른쪽 아래: BYM2의 초과 확률 P(RR > 1). 0.95 이상은 {int((o['pex'] >= 0.95).sum())}개 동")
    mw = 300
    panels = [("SMR (원자료)", smr), ("포아송-감마 EB", eb), ("BYM2 사후 평균", o["rr_mean"]), ("BYM2 초과 확률 P(RR > 1)", None)]
    fh = MapFrame(d.total_bounds, 0, 0, mw).h
    for k, (title, v) in enumerate(panels):
        fr = MapFrame(d.total_bounds, 40 + (k % 2) * (mw + 60), 34 + (k // 2) * (fh + 36), mw)
        if v is not None:
            cls = [f"d{int(np.searchsorted(RR_BREAKS, x, side='right'))}" for x in v]
        else:
            p = o["pex"]
            cls = ["q0" if x < 0.2 else "q1" if x < 0.8 else "q3" if x < 0.95 else "q4" for x in p]
        draw(svg, fr, d.geometry, cls, width=0.3)
        outline(svg, fr, d.union_all(), cls="s-fg", width=0.8)
        svg.text(fr.x + mw / 2, fr.y - 8, title, size=12, weight="600")
    y0 = 34 + 2 * (fh + 36) + 4
    x = 40
    svg.text(x, y0, "상대위험:", size=10, anchor="start", cls="f-mu")
    x += 52
    for j, lab in enumerate(RR_LAB):
        svg.rect(x, y0 - 10, 12, 12, cls=f"s-mu d{j}", width=0.5)
        svg.text(x + 16, y0, lab, size=10, anchor="start")
        x += 16 + len(lab) * 6.5 + 14
    y0 += 20
    x = 40
    svg.text(x, y0, "초과 확률:", size=10, anchor="start", cls="f-mu")
    x += 52
    for c, lab in (("q0", "0.2 미만"), ("q1", "0.2~0.8"), ("q3", "0.8~0.95"), ("q4", "0.95 이상")):
        svg.rect(x, y0 - 10, 12, 12, cls=f"s-mu {c}", width=0.5)
        svg.text(x + 16, y0, lab, size=10, anchor="start")
        x += 16 + len(lab) * 6.5 + 14
    svg.save(os.path.join(OUT, "37-maps.svg"))


def fig_confound(res):
    W_, H = 720, 260
    keys = ["포아송", "독립+온도", "BYM2+온도"]
    labs = ["포아송 회귀 (랜덤효과 없음)", "포아송 + 독립 랜덤효과", "포아송 + BYM2"]
    e = {k: np.exp(res[k]["b1"]) for k in keys}
    sd = {k: np.std(res[k]["b1"]) for k in keys}
    ph1, ph2 = res["BYM2"]["phi"], res["BYM2+온도"]["phi"]
    svg = Svg(W_, H, f"왼쪽: 온도편차 1℃당 상대위험과 95% 신용구간. 랜덤효과 없는 포아송 회귀 {e['포아송'].mean():.3f}, 독립 랜덤효과 {e['독립+온도'].mean():.3f}, "
                     f"BYM2 {e['BYM2+온도'].mean():.3f}로 점추정은 거의 같고, 랜덤효과를 넣을수록 구간이 넓어짐(β의 사후 표준편차 {sd['포아송']:.4f} → {sd['BYM2+온도']:.4f}). "
                     f"오른쪽: BYM2의 공간 비율 φ의 사후분포. 온도편차를 넣기 전(실선, 평균 {ph1.mean():.2f})에는 랜덤효과의 대부분이 공간 구조였지만, "
                     f"넣은 뒤(점선, 평균 {ph2.mean():.2f})에는 넓게 퍼짐. 온도가 공간 구조의 상당 부분을 설명함")
    ax = Axes(svg, 230, 40, 220, 150, (0.98, 1.2), (-0.6, 2.6))
    for i, (k, lab) in enumerate(zip(keys, labs)):
        yy = float(ax.Y(2 - i))
        lo, hi = np.quantile(e[k], [0.025, 0.975])
        svg.line(float(ax.X(lo)), yy, float(ax.X(hi)), yy, cls="s-ac", width=2)
        svg.circle(float(ax.X(e[k].mean())), yy, 4.5, cls="f-ac s-bg", width=1)
        svg.text(220, yy + 4, lab, size=11, anchor="end")
    ax.vline(1, cls="s-mu", width=1, dash="3 3")
    ax.xaxis(ticks=[1, 1.05, 1.1, 1.15, 1.2], label="1℃당 상대위험 exp(β)")
    edges = np.linspace(0, 1, 26)
    h1, _ = np.histogram(res["BYM2"]["phi"], edges, density=True)
    h2, _ = np.histogram(res["BYM2+온도"]["phi"], edges, density=True)
    ax2 = Axes(svg, 510, 40, 180, 150, (0, 1), (0, max(h1.max(), h2.max()) * 1.1))
    mids = (edges[:-1] + edges[1:]) / 2
    ax2.curve(np.r_[0, mids, 1], np.r_[h1[0], h1, h1[-1]], cls="s-ac", width=2)
    ax2.curve(np.r_[0, mids, 1], np.r_[h2[0], h2, h2[-1]], cls="s-bd", width=2, dash="5 3")
    ax2.xaxis(ticks=[0, 0.25, 0.5, 0.75, 1], label="공간 비율 φ")
    svg.line(520, H - 16, 546, H - 16, cls="s-ac", width=2)
    svg.text(552, H - 12, "BYM2", size=11, anchor="start")
    svg.line(600, H - 16, 626, H - 16, cls="s-bd", width=2, dash="5 3")
    svg.text(632, H - 12, "BYM2 + 온도", size=11, anchor="start")
    svg.save(os.path.join(OUT, "37-confound.svg"))


if __name__ == "__main__":
    d, y, E, A, W, rates = load()
    hand(A)
    if os.path.exists(CACHE) and "--refit" not in sys.argv:
        res = load_cache()
        print(f"[적합] {os.path.basename(CACHE)}에서 읽음 (다시 적합하려면 --refit)")
    else:
        res = fit_all(d, y, E, A)
    smr, eb = report(d, y, E, W, rates, res)
    fig_maps(d, smr, eb, res)
    fig_confound(res)
