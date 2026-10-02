"""40강 그림과 본문 수치.

- 40-scale.svg    : 50 m 지표온도를 100 m·500 m·2 km 블록 평균으로 묶은 지도와, 셀 크기에 따른 표준편차·Moran's I
- 40-accuracy.svg : 자기상관과 정확도 평가. 왼쪽: 400픽셀로 시 평균을 추정할 때 표본 배치별 실제 오차와 순진한 표준오차.
                    오른쪽: 고온 픽셀 분류(랜덤 포레스트)의 정확도를 평가 방법별로 추정한 값과 실제 지도 정확도

앱과 같은 수치(격자 만들기 + 존 통계 + 퀸 가중치 + Moran's I)는 GeoStat 엔진 함수로 계산함.
블록 평균의 Moran's I는 래스터 행·열로 직접 계산함(공통 변을 가진 블록을 이웃으로, 행 표준화).

실행 (GeoStat 엔진 환경에서, 몇 분):
    cd engine && uv run python ../book/fig-src/40.py
"""
import importlib
import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import DATA, MapFrame, colorbar, outline, png, ramp_rgb  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import rng  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
m38 = importlib.import_module("38")
m39 = importlib.import_module("39")
OUT = os.path.join(HERE, "..", "fig")
SIZES = [50, 100, 200, 500, 1000, 2000]
HOT = 32.0


# ---------------------------------------------------------------- 손계산
def hand():
    A = np.array([[30, 31, 33, 34], [31, 32, 34, 35], [28, 29, 31, 31], [29, 30, 32, 33.0]])
    B = A.reshape(2, 2, 2, 2).transpose(0, 2, 1, 3).reshape(4, 4)  # 블록마다 한 줄
    bm = B.mean(1)
    within = B.var(1).mean()
    print("[손계산] 4×4 픽셀을 2×2 블록 네 개로 묶기")
    print(f"  블록 평균 {bm.tolist()}, 전체 분산 {A.var():.4f} = 블록 사이 분산 {bm.var():.4f} + 블록 안 분산의 평균 {within:.4f}")
    for n, rho in ((100, 0.8), (100, 0.5), (400, 0.95)):
        print(f"  AR(1) 실효 표본 수: n {n}, ρ {rho} → n(1 − ρ)/(1 + ρ) = {n * (1 - rho) / (1 + rho):.1f}")


# ---------------------------------------------------------------- 1. 셀 크기
def shift(A, dr, dc, fill):
    out = np.full(A.shape, fill, dtype=A.dtype)
    rs = slice(max(dr, 0), A.shape[0] + min(dr, 0))
    rd = slice(max(-dr, 0), A.shape[0] + min(-dr, 0))
    cs = slice(max(dc, 0), A.shape[1] + min(dc, 0))
    cd = slice(max(-dc, 0), A.shape[1] + min(-dc, 0))
    out[rd, cd] = A[rs, cs]
    return out


def rook_moran(M):
    """2차원 배열(NaN = 없음)의 룩 인접·행 표준화 Moran's I. 이웃이 없는 칸은 뺌"""
    ok = ~np.isnan(M)
    D = ((1, 0), (-1, 0), (0, 1), (0, -1))
    nb = sum(shift(ok, dr, dc, False).astype(int) for dr, dc in D)
    use = ok & (nb > 0)
    z = np.where(use, M - M[use].mean(), 0.0)
    lag = sum(shift(z, dr, dc, 0.0) for dr, dc in D)
    return float((z[use] * lag[use] / nb[use]).sum() / (z[use] ** 2).sum()), int(use.sum())


def scale(F, z):
    land = np.full(z.shape, np.nan)
    land[F["row"], F["col"]] = F["z"]
    out = {}
    print("[1] 블록 평균 (시 안 육지 셀만 평균, 룩 인접 Moran's I)")
    for s in SIZES:
        k = s // 50
        R, C = int(np.ceil(z.shape[0] / k)), int(np.ceil(z.shape[1] / k))
        pad = np.full((R * k, C * k), np.nan)
        pad[:z.shape[0], :z.shape[1]] = land
        blk = pad.reshape(R, k, C, k).transpose(0, 2, 1, 3).reshape(R, C, k * k)
        cnt = (~np.isnan(blk)).sum(-1)
        M = np.where(cnt > 0, np.nansum(blk, -1) / np.maximum(cnt, 1), np.nan)
        I, nuse = rook_moran(M)
        v = M[~np.isnan(M)]
        w = cnt[~np.isnan(M)]
        wmean = (v * w).sum() / w.sum()
        between = (w * (v - wmean) ** 2).sum() / w.sum()
        out[s] = dict(n=int((~np.isnan(M)).sum()), sd=float(v.std()), between=float(between), I=I, M=M, mean=float(wmean))
        print(f"  {s} m: 셀 {out[s]['n']:,}개, 셀 값 표준편차 {v.std():.4f}, 범위 {v.min():.2f}~{v.max():.2f}, 면적 가중 블록 사이 분산 {between:.4f}, Moran's I {I:.4f} (이웃 있는 셀 {nuse:,})")
    tot = F["z"].var()
    print(f"  50 m 전체 분산 {tot:.4f}. 블록 사이 + 블록 안: " + ", ".join(f"{s} m {out[s]['between']:.3f} + {tot - out[s]['between']:.3f}" for s in SIZES[1:]))
    return out


def app_grids():
    """앱과 같은 계산: 격자 만들기(폴리곤과 겹치는 셀만) + 존 통계 평균 + 퀸 가중치 + Moran's I(순열 999, 시드 123456789)"""
    import geopandas as gpd

    from geostat_engine.analysis import esda_ops, grid, zonal
    from geostat_engine.analysis import weights as gw
    dong = gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))
    LST = os.path.join(DATA, "hanbit_lst.tif")
    R_ = type("R", (), {"path": LST, "info": {"count": 1, "crs": "EPSG:5186"}})
    print("[2] 앱과 같은 계산: 격자 + 존 통계(평균) + 퀸 + Moran's I")
    res = {}
    for s in (500, 1000, 2000):
        g = grid.make_grid(tuple(dong.total_bounds), dong.crs, s, clip=dong.union_all())
        pl = zonal.prepare(g, R_(), {"stats": ["mean"], "band": 1})
        g["ZS_MEAN"] = zonal.run(pl, lambda *_: None)["columns"]["MEAN"]
        ok = g["ZS_MEAN"].notna()
        g = g[ok].reset_index(drop=True)
        W, _ = gw.build(g, {"type": "queen"})
        m = esda_ops.moran(g["ZS_MEAN"], W, 999, 123456789)
        I, p = m.I if hasattr(m, "I") else m["I"], m.p_sim if hasattr(m, "p_sim") else m["p_sim"]
        res[s] = (len(g), I, p, int((~ok).sum()))
        print(f"  {s} m: 셀 {len(g)}개 (값 없는 셀 {int((~ok).sum())}개 제외), ZS_MEAN 표준편차 {g['ZS_MEAN'].std(ddof=0):.4f}, Moran's I {I:.4f} (유사 p {p:.3f})")
    d = dong.copy()
    pl = zonal.prepare(d, R_(), {"stats": ["mean"], "band": 1})
    d["ZS_MEAN"] = zonal.run(pl, lambda *_: None)["columns"]["MEAN"]
    W, _ = gw.build(d, {"type": "queen"})
    m = esda_ops.moran(d["ZS_MEAN"], W, 999, 123456789)
    I, p = m.I if hasattr(m, "I") else m["I"], m.p_sim if hasattr(m, "p_sim") else m["p_sim"]
    print(f"  행정동 150개: ZS_MEAN 표준편차 {d['ZS_MEAN'].std(ddof=0):.4f}, Moran's I {I:.4f} (유사 p {p:.3f})")
    return res


# ---------------------------------------------------------------- 2. 자기상관과 정확도 평가
def neff(F, z, R=2000):
    mu, sig2 = F["z"].mean(), F["z"].var()
    look = np.full(z.shape, -1)
    look[F["row"], F["col"]] = np.arange(len(F["z"]))
    r = rng("neff40")
    out = {}

    def blocks(k, m):
        """k×k 픽셀 정사각형 m개(모두 육지 안). 겹치지 않게 뽑음"""
        idx = []
        used = set()
        while len(idx) < m:
            rr, cc = r.integers(0, z.shape[0] - k), r.integers(0, z.shape[1] - k)
            sub = look[rr:rr + k, cc:cc + k]
            if (sub < 0).any() or (rr // k, cc // k) in used:
                continue
            used.add((rr // k, cc // k))
            idx.append(sub.ravel())
        return np.concatenate(idx)
    designs = {"무작위 400픽셀": lambda: r.choice(len(F["z"]), 400, replace=False),
               "5×5 묶음 16개": lambda: blocks(5, 16),
               "20×20 한 덩어리": lambda: blocks(20, 1)}
    print(f"[3] 400픽셀로 시 평균 추정 ({R}회). 참 평균 {mu:.4f}, 픽셀 분산 {sig2:.4f}")
    for nm, f in designs.items():
        est, se = [], []
        for _ in range(R):
            i = f()
            est.append(F["z"][i].mean())
            se.append(F["z"][i].std(ddof=1) / np.sqrt(len(i)))
        est, se = np.array(est), np.array(se)
        mse = np.mean((est - mu) ** 2)
        cov = np.mean(np.abs(est - mu) <= 1.96 * se)
        out[nm] = dict(rmse=float(np.sqrt(mse)), se=float(se.mean()), neff=float(sig2 / mse), cover=float(cov))
        print(f"  {nm}: 실제 RMSE {np.sqrt(mse):.4f}, 순진한 표준오차(s/√400) 평균 {se.mean():.4f}, 95% 구간 포함률 {cov:.3f}, 실효 표본 수 σ²/MSE {sig2 / mse:.1f}")
    return out


def accuracy(F, z, tr):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold, KFold
    X = m39.covariates(F, z, tr)
    y = (F["z"] >= HOT).astype(int)
    print(f"[4] 고온 픽셀 분류(지표온도 ≥ {HOT}℃). 시 안 육지 픽셀의 고온 비율 {y.mean():.4f}")
    look = np.full(z.shape, -1)
    look[F["row"], F["col"]] = np.arange(len(y))
    r = rng("acc40")
    polys, used = [], set()
    while len(polys) < 40:  # 500 m 정사각형 훈련 구역 40개 (픽셀 100개씩)
        rr, cc = r.integers(0, z.shape[0] - 10), r.integers(0, z.shape[1] - 10)
        sub = look[rr:rr + 10, cc:cc + 10]
        if (sub < 0).any() or (rr // 10, cc // 10) in used:
            continue
        used.add((rr // 10, cc // 10))
        polys.append(sub.ravel())
    idx = np.concatenate(polys)
    grp = np.repeat(np.arange(40), 100)
    Xt, yt = X[idx], y[idx]
    print(f"  훈련 픽셀 {len(idx):,}개(구역 40개), 고온 비율 {yt.mean():.3f}, 고온 픽셀이 섞인 구역 {int(np.sum([0 < yt[grp == g].mean() < 1 for g in range(40)]))}개")

    def clf():
        return RandomForestClassifier(300, min_samples_leaf=2, n_jobs=2, random_state=0)
    res = {}
    for nm, splitter, groups in (("픽셀 무작위 5겹", KFold(5, shuffle=True, random_state=1), None), ("구역 단위 5겹", GroupKFold(5), grp)):
        pred = np.zeros(len(yt), int)
        for a, b in splitter.split(Xt, yt, groups):
            pred[b] = clf().fit(Xt[a], yt[a]).predict(Xt[b])
        res[nm] = float((pred == yt).mean())
    m = clf().fit(Xt, yt)
    allp = m.predict(X)
    res["실제 지도 정확도"] = float((allp == y).mean())
    v = r.choice(len(y), 1000, replace=False)
    res["독립 확률 표본 1,000"] = float((allp[v] == y[v]).mean())
    se = np.sqrt(res["독립 확률 표본 1,000"] * (1 - res["독립 확률 표본 1,000"]) / 1000)
    for k, val in res.items():
        print(f"  {k}: 전체 정확도 {val:.4f}")
    print(f"  독립 표본의 표준오차 {se:.4f} (95% {res['독립 확률 표본 1,000'] - 1.96 * se:.3f}~{res['독립 확률 표본 1,000'] + 1.96 * se:.3f})")
    tpv = ((allp[v] == 1) & (y[v] == 1)).sum()
    print(f"  독립 표본 1,000: 고온 {int(y[v].sum())}픽셀, 생산자 정확도 {tpv / y[v].sum():.4f}, 사용자 정확도 {tpv / max(allp[v].sum(), 1):.4f}")
    tp = ((allp == 1) & (y == 1)).sum()
    print(f"  실제 지도: 고온 생산자 정확도(재현율) {tp / y.sum():.4f}, 사용자 정확도(정밀도) {tp / max(allp.sum(), 1):.4f}, 예측 고온 비율 {allp.mean():.4f}")
    return res


# ---------------------------------------------------------------- 그림
def fig_scale(sc, dong, win, tr):
    W_, H = 720, 470
    svg = Svg(W_, H, f"같은 지표온도를 셀 크기만 바꿔 블록 평균으로 묶음. 위: 100 m, 500 m, 2 km. 셀이 커질수록 국지적인 뜨거운 점과 차가운 점이 평균에 묻히고 큰 경향만 남음. "
                     f"아래 왼쪽: 셀 값의 표준편차가 50 m {sc[50]['sd']:.2f}℃에서 2 km {sc[2000]['sd']:.2f}℃로 줄어듦(지원 효과). "
                     f"아래 오른쪽: 이웃 셀끼리의 Moran's I는 50 m {sc[50]['I']:.2f}에서 2 km {sc[2000]['I']:.2f}으로 바뀜. 자기상관의 크기는 셀 크기와 함께 읽어야 함")
    mw = 220
    lo, hi = 26, 38
    for k, s in enumerate((100, 500, 2000)):
        M = sc[s]["M"]
        fr = MapFrame(dong.total_bounds, 15 + k * (mw + 18), 36, mw)
        X0, Y0 = fr.xy(tr.c, tr.f)
        X1, Y1 = fr.xy(tr.c + M.shape[1] * s, tr.f - M.shape[0] * s)
        svg.add(f'<svg x="{fr.x:.1f}" y="{fr.y:.1f}" width="{mw:.1f}" height="{fr.h:.1f}" viewBox="{fr.x:.1f} {fr.y:.1f} {mw:.1f} {fr.h:.1f}" overflow="hidden">')
        rgb = ramp_rgb(np.repeat(np.repeat(M, max(1, 400 // M.shape[1]), 0), max(1, 400 // M.shape[1]), 1), lo, hi)
        svg.image_png(X0, Y0, X1 - X0, Y1 - Y0, png(rgb, 440))
        svg.add("</svg>")
        outline(svg, fr, win, cls="s-mu", width=0.8)
        svg.text(fr.x + mw / 2, fr.y - 8, f"{s:,} m 셀 ({sc[s]['n']:,}개)" if s < 1000 else f"{s // 1000} km 셀 ({sc[s]['n']:,}개)", size=12, weight="600")
    fh = MapFrame(dong.total_bounds, 0, 0, mw).h
    colorbar(svg, 260, 36 + fh + 22, 200, lo, hi, [26, 28, 30, 32, 34, 36, 38], "지표온도 (℃)")
    y0 = 36 + fh + 80
    xs = np.log(SIZES)
    for k, (key, lab, ylim) in enumerate((("sd", "셀 값의 표준편차 (℃)", (0, 2.6)), ("I", "Moran's I (룩 인접)", (0, 1.05)))):
        ax = Axes(svg, 80 + k * 330, y0, 240, H - y0 - 50, (np.log(40), np.log(2500)), ylim)
        ax.curve(xs, [sc[s][key] for s in SIZES], cls="s-ac", width=2)
        for s in SIZES:
            svg.circle(float(ax.X(np.log(s))), float(ax.Y(sc[s][key])), 3, cls="f-ac s-bg", width=0.6)
        ax.xaxis(ticks=list(xs), label="셀 크기 (m)", fmt=lambda t: f"{np.exp(t):,.0f}")
        ax.yaxis(label=lab)
    svg.save(os.path.join(OUT, "40-scale.svg"))


def fig_accuracy(ne, acc):
    W_, H = 720, 300
    a = acc
    svg = Svg(W_, H, f"왼쪽: 400픽셀로 시 평균 지표온도를 추정할 때의 실제 RMSE(막대)와 순진한 표준오차 s/√400(점). 픽셀이 붙어 있을수록 실제 오차가 커지는데 순진한 표준오차는 작아짐. "
                     f"20×20 한 덩어리의 400픽셀은 독립 픽셀 {ne['20×20 한 덩어리']['neff']:.1f}개만큼의 정보임. "
                     f"오른쪽: 고온 픽셀 분류의 정확도. 훈련 구역 안에서 픽셀을 무작위로 나눈 교차검증은 {a['픽셀 무작위 5겹']:.3f}로 실제 지도 정확도({a['실제 지도 정확도']:.3f}, 점선)를 크게 부풀림. "
                     f"구역 단위로 나눈 교차검증도 {a['구역 단위 5겹']:.3f}로 여전히 높음(훈련 구역이 시 전체를 대표하지 않음). 시 전체에서 무작위로 뽑은 독립 표본 1,000픽셀({a['독립 확률 표본 1,000']:.3f})만 실제와 맞음")
    keys = list(ne)
    mx = max(max(o["rmse"], o["se"]) for o in ne.values()) * 1.15
    ax = Axes(svg, 70, 40, 260, 180, (-0.5, 2.5), (0, mx))
    for i, k in enumerate(keys):
        o = ne[k]
        x0 = float(ax.X(i - 0.3))
        svg.rect(x0, float(ax.Y(o["rmse"])), float(ax.X(0.6) - ax.X(0)), float(ax.Y(0) - ax.Y(o["rmse"])), cls="s-bg f-ac", width=0.5)
        svg.circle(float(ax.X(i)), float(ax.Y(o["se"])), 4.5, cls="f-bd s-bg", width=1)
        svg.text(float(ax.X(i)), 236, k, size=10, cls="f-mu")
        svg.text(float(ax.X(i)), float(ax.Y(o["rmse"])) - 6, f"n_eff {o['neff']:.0f}" if o["neff"] >= 10 else f"n_eff {o['neff']:.1f}", size=10)
    ax.yaxis(label="시 평균 추정 오차 (℃)")
    svg.rect(80, H - 30, 12, 12, cls="s-mu f-ac", width=0.5)
    svg.text(98, H - 20, "실제 RMSE", size=11, anchor="start")
    svg.circle(196, H - 24, 4.5, cls="f-bd s-bg", width=1)
    svg.text(206, H - 20, "순진한 표준오차", size=11, anchor="start")
    names = ["픽셀 무작위 5겹", "구역 단위 5겹", "독립 확률 표본 1,000"]
    labs = ["픽셀 무작위 5겹", "구역 단위 5겹", "독립 확률 표본"]
    lo = 0.5
    ax2 = Axes(svg, 440, 40, 250, 180, (-0.5, 2.5), (lo, 1.0))
    for i, (k, lab) in enumerate(zip(names, labs)):
        v = a[k]
        svg.rect(float(ax2.X(i - 0.3)), float(ax2.Y(v)), float(ax2.X(0.6) - ax2.X(0)), float(ax2.Y(lo) - ax2.Y(v)), cls="s-bg f-mu", width=0.5)
        svg.text(float(ax2.X(i)), float(ax2.Y(v)) - 6, f"{v:.3f}", size=10)
        svg.text(float(ax2.X(i)), 236, lab, size=10, cls="f-mu")
    yy = float(ax2.Y(a["실제 지도 정확도"]))
    svg.line(float(ax2.X(-0.5)), yy, float(ax2.X(2.5)), yy, cls="s-fg", width=1.6, dash="5 3")
    svg.line(460, H - 24, 486, H - 24, cls="s-fg", width=1.6, dash="5 3")
    svg.text(492, H - 20, f"실제 지도 정확도 {a['실제 지도 정확도']:.3f}", size=11, anchor="start")
    ax2.yaxis(ticks=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0], label="전체 정확도")
    svg.save(os.path.join(OUT, "40-accuracy.svg"))


if __name__ == "__main__":
    hand()
    F, z, tr, dong, win = m38.frame()
    sc = scale(F, z)
    app_grids()
    ne = neff(F, z)
    acc = accuracy(F, z, tr)
    fig_scale(sc, dong, win, tr)
    fig_accuracy(ne, acc)
