"""35강 그림과 본문 수치.

- 35-panel.svg : 패널 회귀 계수(고령비율, 폭염일수)와 95% 신뢰구간. 합동 OLS, 고정효과, 공간 패널(고정효과 시차·오차, 확률효과 오차)
- 35-scan.svg : 시공간 스캔 통계로 찾은 군집 (시간 보정 포아송 모형, 시공간 순열 모형)

자료는 book/data/hanbit_dong_panel.gpkg. 공간 패널 모형은 spreg(Panel_FE_Lag 등), 포아송 고정효과 모형과
시공간 스캔 통계는 이 스크립트에서 numpy로 직접 계산함.

실행 (GeoStat 엔진 환경에서, 몇 분 걸림):
    cd engine && uv run python ../book/fig-src/35.py
"""
import contextlib
import importlib
import io
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
from regkit import queen, rng  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
m33 = importlib.import_module("33")
OUT = os.path.join(HERE, "..", "fig")
YEARS = m33.YEARS
XN = ["고령비율", "폭염일수"]


def quiet(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def load():
    p = m33.load()
    p["고령비율"] = p["고령인구"] / p["인구"] * 100
    p = p.sort_values(["연도", "동코드"]).reset_index(drop=True)  # 연도별로 쌓음 (spreg 패널 순서)
    d25 = p[p["연도"] == 2025].reset_index(drop=True)
    return p, d25, queen(d25)


# ---------------------------------------------------------------- 손계산
def hand():
    print("[손계산] 고정효과(동 안 편차): 동 A, B의 두 해")
    df = pd.DataFrame({"동": ["A", "A", "B", "B"], "x": [10, 12, 20, 22.0], "y": [5, 6, 2, 3.0]})
    b_pool = np.polyfit(df["x"], df["y"], 1)[0]
    dm = df.groupby("동").transform("mean")
    xw, yw = df["x"] - dm["x"], df["y"] - dm["y"]
    df2 = df.copy()
    df2.loc[df2["동"] == "B", "y"] = [4, 3.0]
    dm2 = df2.groupby("동").transform("mean")
    xw2, yw2 = df2["x"] - dm2["x"], df2["y"] - dm2["y"]
    print(f"  (연습) B를 (20, 4), (22, 3)으로: 합동 OLS {np.polyfit(df2['x'], df2['y'], 1)[0]:.3f}, 고정효과 {(xw2 * yw2).sum() / (xw2 ** 2).sum():.3f}")
    print(f"  합동 OLS 기울기 {b_pool:.3f}; 동 평균을 뺀 x {xw.tolist()}, y {yw.tolist()}, 고정효과 기울기 {(xw * yw).sum() / (xw ** 2).sum():.3f}")
    print("[손계산] 시공간 스캔의 로그우도비: 원기둥 안 관측 30건, 기댓값 18건, 전체 1,000건")
    c, e, C = 30, 18, 1000
    llr = c * np.log(c / e) + (C - c) * np.log((C - c) / (C - e))
    print(f"  LLR = 30 ln(30/18) + 970 ln(970/982) = {c * np.log(c / e):.3f} + {(C - c) * np.log((C - c) / (C - e)):.3f} = {llr:.3f}, 상대위험 {(c / e) / ((C - c) / (C - e)):.3f}")


# ---------------------------------------------------------------- 1. 패널 회귀
def within(p, cols):
    g = p.groupby("동코드")[cols].transform("mean")
    return p[cols] - g


def fe_ols(p):
    """고정효과(동 안 편차) OLS와 동 단위 군집 강건 표준오차"""
    Xw = within(p, XN).to_numpy()
    yw = within(p, ["출동률"]).to_numpy().ravel()
    b = np.linalg.lstsq(Xw, yw, rcond=None)[0]
    e = yw - Xw @ b
    n, k = len(p["동코드"].unique()), Xw.shape[1]
    XtX = np.linalg.inv(Xw.T @ Xw)
    meat = np.zeros((k, k))
    for _, idx in p.groupby("동코드").indices.items():
        s = Xw[idx].T @ e[idx]
        meat += np.outer(s, s)
    N = len(yw)
    V = XtX @ meat @ XtX * (n / (n - 1)) * ((N - 1) / (N - k - n))
    Vc = XtX * (e @ e) / (N - n - k)  # 고전적 표준오차 (동 수만큼 자유도를 뺌)
    return b, np.sqrt(np.diag(V)), np.sqrt(np.diag(Vc))


def pooled_cluster(p):
    X = np.c_[np.ones(len(p)), p[XN].to_numpy()]
    y = p["출동률"].to_numpy()
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    XtX = np.linalg.inv(X.T @ X)
    meat = np.zeros((3, 3))
    for _, idx in p.groupby("동코드").indices.items():
        s = X[idx].T @ e[idx]
        meat += np.outer(s, s)
    n, N = p["동코드"].nunique(), len(y)
    V = XtX @ meat @ XtX * (n / (n - 1)) * ((N - 1) / (N - 3))
    Vc = XtX * (e @ e) / (N - 3)
    return b, np.sqrt(np.diag(V)), np.sqrt(np.diag(Vc))


def panel(p, d25, W):
    import spreg
    y = p[["출동률"]].to_numpy()
    X = p[XN].to_numpy()
    res = {}
    b, se_cl, se_c = pooled_cluster(p)
    print("[1] 패널 회귀 (y = 출동률, x = 고령비율, 폭염일수; 동 150 × 연도 10)")
    print(f"  합동 OLS: 상수 {b[0]:.3f}, 고령비율 {b[1]:.4f} (보통 SE {se_c[1]:.4f}, 동 군집 강건 SE {se_cl[1]:.4f}), 폭염일수 {b[2]:.4f} (보통 {se_c[2]:.4f}, 군집 {se_cl[2]:.4f})")
    res["합동 OLS"] = (b[1:], se_cl[1:])
    bf, sef_cl, sef_c = fe_ols(p)
    print(f"  고정효과(동): 고령비율 {bf[0]:.4f} (보통 SE {sef_c[0]:.4f}, 군집 SE {sef_cl[0]:.4f}), 폭염일수 {bf[1]:.4f} (보통 {sef_c[1]:.4f}, 군집 {sef_cl[1]:.4f})")
    res["고정효과"] = (bf, sef_cl)
    models = {"고정효과 + 공간시차": spreg.Panel_FE_Lag, "고정효과 + 공간오차": spreg.Panel_FE_Error,
              "확률효과 + 공간오차": spreg.Panel_RE_Error}
    fitted = {}
    for name, cls in models.items():
        m = quiet(cls, y, X, W, name_x=XN)
        fitted[name] = m
        nm = list(m.name_x)
        b = m.betas.ravel()
        se = np.sqrt(np.diag(m.vm))
        sp = nm[-1] if "RE" not in name else nm[-2]
        txt = ", ".join(f"{a} {bb:.4f} ({s:.4f})" for a, bb, s in zip(nm, b, se))
        print(f"  {name}: {txt}")
        i1, i2 = nm.index("고령비율"), nm.index("폭염일수")
        res[name] = (np.array([b[i1], b[i2]]), np.array([se[i1], se[i2]]))
        del sp
    lml, lme = spreg.panel_LMlag(y, X, W), spreg.panel_LMerror(y, X, W)
    # spreg 1.9.1의 panel_LMlag는 분모의 T × tr(W'W + WW)를 tr(·)²로 잘못 씀 → 직접 계산 (Anselin, Le Gallo & Jayet 2008)
    from scipy import sparse
    T_, n_ = len(YEARS), W.n
    Xc = np.c_[np.ones(len(y)), X]
    yv = y.ravel()
    bo = np.linalg.lstsq(Xc, yv, rcond=None)[0]
    u = yv - Xc @ bo
    s2 = float(u @ u) / (len(yv) - Xc.shape[1])  # spreg OLS의 sig2와 같게
    Wnt = sparse.kron(sparse.identity(T_), W.sparse).tocsr()
    Wd = W.full()[0]
    trw = np.trace(Wd @ Wd) + np.trace(Wd.T @ Wd)
    wxb = Wnt @ (Xc @ bo)
    M = np.eye(len(y)) - Xc @ np.linalg.inv(Xc.T @ Xc) @ Xc.T
    J = (float(wxb @ M @ wxb) + T_ * trw * s2) / s2
    lm_lag = float(u @ (Wnt @ yv)) ** 2 / (s2 ** 2 * J)
    lm_err = (float(u @ (Wnt @ u)) / s2) ** 2 / (T_ * trw)
    print(f"  직접 계산(합동 OLS 잔차): LM-lag {lm_lag:.3f} (p {stats.chi2.sf(lm_lag, 1):.2e}), LM-error {lm_err:.3f} (spreg와 같은지 확인)")
    rl, re_ = spreg.panel_rLMlag(y, X, W), spreg.panel_rLMerror(y, X, W)
    print(f"  패널 LM: LM-lag {lml[0]:.3f} (p {lml[1]:.4f}), LM-error {lme[0]:.3f} (p {lme[1]:.2e}), 강건 LM-lag {rl[0]:.3f} (p {rl[1]:.4f}), 강건 LM-error {re_[0]:.3f} (p {re_[1]:.4f})")
    h = spreg.panel_Hausman(fitted["고정효과 + 공간오차"], fitted["확률효과 + 공간오차"])
    print(f"  하우스만 검정(공간오차 고정효과 대 확률효과): {h[0]:.3f} (p {h[1]:.4f})")
    # 연도별 잔차 Moran (고정효과)
    from esda import Moran
    Xw = within(p, XN).to_numpy()
    yw = within(p, ["출동률"]).to_numpy().ravel()
    e = yw - Xw @ bf
    E = e.reshape(len(YEARS), -1)
    mi = [Moran(E[t], W, permutations=0).I for t in range(len(YEARS))]
    print(f"  고정효과 잔차의 연도별 Moran's I {np.round(mi, 3).tolist()} (평균 {np.mean(mi):.3f})")
    from scipy import sparse as _sp
    Wnt2 = _sp.kron(_sp.identity(len(YEARS)), W.sparse).tocsr()
    Wd2 = W.full()[0]
    trw2 = np.trace(Wd2 @ Wd2) + np.trace(Wd2.T @ Wd2)
    s2e = float(e @ e) / len(e)
    lm_fe = (float(e @ (Wnt2 @ e)) / s2e) ** 2 / (len(YEARS) * trw2)
    print(f"  고정효과 잔차로 같은 식의 LM-error(근사) {lm_fe:.2f}")
    # 고령비율의 동 안 변동
    sd_w = within(p, ["고령비율"]).to_numpy().std()
    print(f"  고령비율 표준편차: 전체 {p['고령비율'].std(ddof=0):.3f}, 동 안 {sd_w:.3f}; 동 사이 상관(10년 평균 고령비율과 동 고정효과): 아래 참고")
    return res


def poisson_fe(p):
    """포아송 고정효과(동 더미) + 오프셋 log(인구). IRLS"""
    dongs = p["동코드"].astype("category")
    D = pd.get_dummies(dongs.cat.codes).to_numpy(float)
    X = np.c_[p[XN].to_numpy(), D]
    y = p["출동건수"].to_numpy(float)
    off = np.log(p["인구"].to_numpy(float))
    b = np.zeros(X.shape[1])
    b[2:] = np.log((y.sum() + 0.5) / np.exp(off).sum())
    for _ in range(100):
        eta = off + X @ b
        mu = np.exp(eta)
        z = eta - off + (y - mu) / mu
        WX = X * mu[:, None]
        bn = np.linalg.solve(X.T @ WX, WX.T @ z)
        if np.max(np.abs(bn - b)) < 1e-10:
            b = bn
            break
        b = bn
    mu = np.exp(off + X @ b)
    V = np.linalg.inv(X.T @ (X * mu[:, None]))
    se = np.sqrt(np.diag(V))[:2]
    disp = ((y - mu) ** 2 / mu).sum() / (len(y) - X.shape[1])
    print("[2] 포아송 고정효과(동 더미, 오프셋 log 인구)")
    for j, n in enumerate(XN):
        print(f"  {n}: {b[j]:.4f} (SE {se[j]:.4f}, 과산포 보정 SE {se[j] * np.sqrt(disp):.4f}) → 1 단위당 {np.expm1(b[j]) * 100:.1f}% "
              f"(95% 구간 {np.expm1(b[j] - 1.96 * se[j]) * 100:.1f}~{np.expm1(b[j] + 1.96 * se[j]) * 100:.1f}%)")
    print(f"  피어슨 과산포 지수 {disp:.3f}")
    return b[:2], se


# ---------------------------------------------------------------- 2. 시공간 스캔 통계
def scan(p, d25, R=999, max_pop=0.1, max_len=5):
    n, T = len(d25), len(YEARS)
    C = p.pivot(index="동코드", columns="연도", values="출동건수").to_numpy(float)
    P = p.pivot(index="동코드", columns="연도", values="인구").to_numpy(float)
    cen = np.c_[d25.geometry.centroid.x, d25.geometry.centroid.y]
    D = np.sqrt(((cen[:, None] - cen[None]) ** 2).sum(-1))
    order = np.argsort(D, 1)
    pop25 = P[:, -1]
    K = int(np.max([np.searchsorted(np.cumsum(pop25[order[i]]), max_pop * pop25.sum(), side="right") for i in range(n)]))
    kmax = np.array([np.searchsorted(np.cumsum(pop25[order[i]]), max_pop * pop25.sum(), side="right") for i in range(n)])
    windows = [(a, b) for a in range(T) for b in range(a, min(T, a + max_len))]
    tot = C.sum()

    def expected(model, Cm):
        if model == "poisson":  # 해마다의 전체 비율로 (시간 보정)
            return P * (Cm.sum(0) / P.sum(0))
        return np.outer(Cm.sum(1), Cm.sum(0)) / Cm.sum()  # 시공간 순열: 동 합계 × 연도 합계 / 전체

    def best(Cm, Em, keep=False):
        # 원기둥(중심 i, 가까운 동 k개, 연도 창)의 관측·기대 합
        cs = np.cumsum(Cm[order], axis=1)[:, :K]  # (n, K, T)
        es = np.cumsum(Em[order], axis=1)[:, :K]
        ct = np.concatenate([np.zeros((n, K, 1)), np.cumsum(cs, 2)], 2)
        et = np.concatenate([np.zeros((n, K, 1)), np.cumsum(es, 2)], 2)
        c = np.stack([ct[:, :, b + 1] - ct[:, :, a] for a, b in windows], 2)
        e = np.stack([et[:, :, b + 1] - et[:, :, a] for a, b in windows], 2)
        ok = (np.arange(K)[None, :, None] < kmax[:, None, None]) & (c > e)
        with np.errstate(divide="ignore", invalid="ignore"):
            llr = np.where(ok, c * np.log(c / e) + (tot - c) * np.log((tot - c) / (tot - e)), 0.0)
        llr = np.nan_to_num(llr)
        if keep:
            return llr, c, e
        return llr.max()

    out = {}
    r = rng("scan")
    for model in ("poisson", "permutation"):
        E = expected(model, C)
        llr, c, e = best(C, E, keep=True)
        # 겹치지 않는 군집 3개까지
        found = []
        used = np.zeros(n, bool)
        flat = np.argsort(-llr, axis=None)
        for f in flat[:200000]:
            i, k, w = np.unravel_index(f, llr.shape)
            if llr[i, k, w] <= 0:
                break
            members = order[i, :k + 1]
            if used[members].any():
                continue
            found.append((i, k, w, llr[i, k, w], c[i, k, w], e[i, k, w], members))
            used[members] = True
            if len(found) == 3:
                break
        # 몬테카를로: 귀무가설 아래 자료를 R번 만들어 최대 LLR의 분포를 구함
        mx = np.zeros(R)
        if model == "poisson":
            for t in range(R):
                Cs = np.column_stack([r.multinomial(int(C[:, j].sum()), P[:, j] / P[:, j].sum()) for j in range(T)]).astype(float)
                mx[t] = best(Cs, expected("poisson", Cs))
        else:
            dong_idx = np.repeat(np.repeat(np.arange(n), T), C.astype(int).ravel())
            year_idx = np.repeat(np.tile(np.arange(T), n), C.astype(int).ravel())
            for t in range(R):
                yr = r.permutation(year_idx)
                Cs = np.zeros((n, T))
                np.add.at(Cs, (dong_idx, yr), 1)
                mx[t] = best(Cs, expected("permutation", Cs))
        print(f"[3] 시공간 스캔 ({'시간 보정 포아송' if model == 'poisson' else '시공간 순열'} 모형, 최대 인구 {max_pop:.0%}, 최대 {max_len}년, 몬테카를로 {R}회)")
        rows = []
        for i, k, w, L, cc, ee, mem in found:
            pv = (1 + (mx >= L).sum()) / (R + 1)
            a, b = windows[w]
            names = d25["동이름"][mem].tolist()
            rr = (cc / ee) / ((tot - cc) / (tot - ee))
            print(f"  중심 {d25['동이름'][i]}, 동 {k + 1}개 {names}, {YEARS[a]}~{YEARS[b]}년, 관측 {cc:.0f} / 기대 {ee:.1f}, 상대위험 {rr:.2f}, LLR {L:.2f}, p {pv:.3f}")
            rows.append(dict(members=mem, years=(YEARS[a], YEARS[b]), obs=cc, exp=ee, rr=rr, llr=L, p=pv, center=d25["동이름"][i]))
        print(f"  귀무 분포 최대 LLR의 95% 분위 {np.quantile(mx, 0.95):.2f}")
        out[model] = rows
    return out


# ---------------------------------------------------------------- 그림
def fig_panel(res):
    W_, H = 720, 260
    names = list(res)
    svg = Svg(W_, H, "패널 회귀 계수와 95% 신뢰구간(y = 동별 출동률). 왼쪽 고령비율: 합동 OLS는 동 사이의 차이(고령 동은 시원함)에 섞여 작게 나오고, 동 고정효과를 넣은 모형들은 동 안의 변화로 추정해 4배 안팎으로 큼. "
                     "오른쪽 폭염일수: 모든 모형이 비슷함(도시 전체가 함께 겪는 연도 변화로 추정되므로). 합동 OLS와 고정효과는 동 군집 강건 표준오차, 공간 패널은 최대우도 표준오차")
    for k, (j, lab, lim, ticks) in enumerate(((0, "고령비율 계수", (-0.1, 0.65), [0, 0.2, 0.4, 0.6]), (1, "폭염일수 계수", (0.15, 0.4), [0.2, 0.3, 0.4]))):
        ax = Axes(svg, 200 + k * 270, 36, 220, 170, lim, (-0.6, len(names) - 0.4))
        for i, nm in enumerate(names):
            b, se = res[nm]
            yy = float(ax.Y(len(names) - 1 - i))
            svg.line(float(ax.X(b[j] - 1.96 * se[j])), yy, float(ax.X(b[j] + 1.96 * se[j])), yy, cls="s-ac", width=2)
            svg.circle(float(ax.X(b[j])), yy, 4.5, cls="f-ac s-bg", width=1)
            if k == 0:
                svg.text(190, yy + 4, nm, size=11, anchor="end")
        ax.vline(0, cls="s-mu", width=1, dash="3 3") if lim[0] < 0 else None
        ax.xaxis(ticks=ticks, label=lab)
    svg.save(os.path.join(OUT, "35-panel.svg"))


def fig_scan(d25, out):
    W_, H = 720, 330
    pa, pe = out["poisson"], out["permutation"]
    svg = Svg(W_, H, f"시공간 스캔 통계로 찾은 군집(유의한 것만 칠함). 왼쪽: 해마다의 도시 전체 비율로 기대 건수를 정한 포아송 모형. 가장 가능성 높은 군집은 {pa[0]['center']} 중심 동 {len(pa[0]['members'])}개의 "
                     f"{pa[0]['years'][0]}~{pa[0]['years'][1]}년(상대위험 {pa[0]['rr']:.2f}). 오른쪽: 동마다의 평소 수준과 해마다의 수준을 모두 기대 건수에 넣은 시공간 순열 모형. "
                     f"평소보다 특정 기간에 늘어난 곳만 찾음. 유의한 군집이 없었음(가장 가능성 높은 군집은 {pe[0]['center']} 중심 동 {len(pe[0]['members'])}개의 {pe[0]['years'][0]}~{pe[0]['years'][1]}년, 상대위험 {pe[0]['rr']:.2f}, p {pe[0]['p']:.3f})")
    mw = 310
    cols = ["#d6604d", "#f4a582", "#92c5de"]
    for k, (rows, title) in enumerate(((pa, "시간 보정 포아송 모형"), (pe, "시공간 순열 모형"))):
        fr = MapFrame(d25.total_bounds, 30 + k * (mw + 40), 36, mw)
        fills = ["#eeeeee"] * len(d25)
        for j, r in enumerate(rows):
            if r["p"] <= 0.05:
                for m in r["members"]:
                    fills[m] = cols[j]
        draw(svg, fr, d25.geometry, None, width=0.3, stroke="s-bg", fills=fills)
        outline(svg, fr, d25.union_all(), cls="s-fg", width=0.8)
        svg.text(fr.x + mw / 2, 24, title, size=12, weight="600")
        y = 36 + fr.h + 18
        if not any(r["p"] <= 0.05 for r in rows):
            svg.text(fr.x, y, f"유의한 군집 없음 (가장 가능성 높은 군집 p {rows[0]['p']:.3f})", size=10, anchor="start", cls="f-mu")
        for j, r in enumerate(rows):
            if r["p"] <= 0.05:
                svg.rect(fr.x, y - 10, 12, 12, cls="s-mu", width=0.5, fill=cols[j])
                svg.text(fr.x + 18, y, f"{r['years'][0]}~{r['years'][1]}년 · 동 {len(r['members'])}개 · 상대위험 {r['rr']:.2f} · p {r['p']:.3f}", size=10, anchor="start")
                y += 17
    svg.save(os.path.join(OUT, "35-scan.svg"))


if __name__ == "__main__":
    hand()
    p, d25, W = load()
    res = panel(p, d25, W)
    poisson_fe(p)
    out = scan(p, d25)
    fig_panel(res)
    fig_scan(d25, out)
