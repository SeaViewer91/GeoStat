"""8강 그림과 본문 수치.

- 08-confound.svg : 고령비율과 출동률. 단순회귀선(음의 기울기)과, 지표온도를 통제한 다중회귀선(양의 기울기)
- 08-residuals.svg : 다중회귀 잔차 진단 (예측값 대 잔차, 인구 대 잔차, 정규 Q-Q)
- 08-coef.svg : 모형에 따라 고령비율·온도편차 계수와 95% 신뢰구간이 어떻게 달라지는지

회귀는 GeoStat 엔진의 regression.prepare/run(앱과 같은 spreg OLS)으로 계산함.
온도편차 = 동 평균 지표온도(존 통계 평균) − 30, 로그밀도c = log(인구밀도) − 8.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/08.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import aggregate as agg  # noqa: E402
from geostat_engine.analysis import regression as rg  # noqa: E402
from geostat_engine.analysis import weights as gw  # noqa: E402
from geostat_engine.analysis import zonal  # noqa: E402

warnings.filterwarnings("ignore")
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "fig")
LST = os.path.join(DATA, "hanbit_lst.tif")

dong = gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))
events = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
dong["PT_CNT"] = agg.aggregate(dong, events, stats=[], count=True, density=False).columns["CNT"]
pl = zonal.prepare(dong, type("R", (), {"path": LST, "info": {"count": 1, "crs": "EPSG:5186"}})(), {"stats": ["mean"], "band": 1})
dong["ZS_MEAN"] = zonal.run(pl, lambda *_: None)["columns"]["MEAN"]
dong["출동률"] = dong["PT_CNT"] / dong["인구"] * 10000
dong["고령비율"] = dong["고령인구"] / dong["인구"] * 100
dong["온도편차"] = dong["ZS_MEAN"] - 30
dong["로그밀도"] = np.log(dong["인구"] / dong["면적_km2"])
dong["로그밀도c"] = dong["로그밀도"] - 8
W, _ = gw.build(dong, {"type": "queen"})


def ols(xs, y="출동률", robust=None, w=None):
    payload = rg.prepare(dong, {"model": "ols", "y": y, "x": xs, "robust": robust}, w, None)
    out = rg.run(payload, lambda *a: None)
    return out["report"], out["columns"]


def show(rep):
    s = dict(rep["summary"])
    print(f"  R² {s['R²']:.4f}, 수정 R² {s['수정 R²']:.4f}, F {s['F 통계량']:.2f} (p {s['F 유의확률']:.2g}), 로그우도 {s['로그우도']:.3f}, "
          f"AIC {s['AIC']:.2f}, AICc {s['AICc']:.2f}, SC {s['SC (BIC)']:.2f}, σ² {s['잔차 분산 (σ²)']:.3f}, 표준오차 {s['표준오차']}")
    for c in rep["coefficients"]:
        print(f"    {c['name']}: 계수 {c['coef']:.4f}, 표준오차 {c['se']:.4f}, t {c['stat']:.3f}, p {c['p']:.4g}")
    for d in rep["diagnostics"]:
        pv = f", p {d['p']:.3g}" if d["p"] is not None else ""
        dfv = f", 자유도 {d['df']:.0f}" if d["df"] is not None else ""
        print(f"    [{d['group']}] {d['name']}: {d['value']:.4f}{dfv}{pv}")
    for n in rep["notes"]:
        print(f"    참고: {n}")
    f = rep["fit"]
    if f.get("moran_i") is not None:
        print(f"    모형 비교용 잔차 I {f['moran_i']:.4f}, 순열 p {f['moran_p']}")


def vif(cols):
    X = dong[cols].to_numpy(float)
    out = {}
    for j, c in enumerate(cols):
        A = np.column_stack([np.ones(len(X)), np.delete(X, j, 1)])
        b = np.linalg.lstsq(A, X[:, j], rcond=None)[0]
        r2 = 1 - ((X[:, j] - A @ b) ** 2).sum() / ((X[:, j] - X[:, j].mean()) ** 2).sum()
        out[c] = 1 / (1 - r2)
    return out


# ---------------------------------------------------------------- 수치
def numbers():
    print("[손계산] x = 1..5, y = 2, 4, 5, 4, 6")
    x = np.arange(1, 6.0)
    y = np.array([2, 4, 5, 4, 6.0])
    b = ((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum()
    a = y.mean() - b * x.mean()
    e = y - (a + b * x)
    print(f"  Sxy {((x - x.mean()) * (y - y.mean())).sum():.2f}, Sxx {((x - x.mean()) ** 2).sum():.2f}, 기울기 {b:.2f}, 절편 {a:.2f}, "
          f"잔차 {e.round(2).tolist()}, 잔차제곱합 {(e ** 2).sum():.2f}, 전체제곱합 {((y - y.mean()) ** 2).sum():.2f}, R² {1 - (e ** 2).sum() / ((y - y.mean()) ** 2).sum():.3f}")

    print("[상관] ", dong[["출동률", "고령비율", "ZS_MEAN", "로그밀도"]].corr().round(3).to_dict())
    models = {
        "M1": ["고령비율"],
        "M2": ["온도편차"],
        "M3": ["고령비율", "온도편차"],
        "M4": ["고령비율", "온도편차", "로그밀도c"],
    }
    reps = {}
    for k, xs in models.items():
        print(f"[{k}] 출동률 ~ {' + '.join(xs)} (퀸 가중치로 공간 진단)")
        rep, cols = ols(xs, w=W)
        show(rep)
        reps[k] = (rep, cols)
    print("[M3 강건] White 이분산 강건 표준오차")
    rep, _ = ols(models["M3"], robust="white", w=W)
    show(rep)
    reps["M3r"] = (rep, None)

    print("[조건수] 원래 지표온도(ZS_MEAN)를 그대로 쓰면")
    import spreg
    for xs in (["고령비율", "ZS_MEAN"], ["고령비율", "온도편차"], ["온도편차"], ["ZS_MEAN"]):
        m = spreg.OLS(dong[["출동률"]].to_numpy(), dong[xs].to_numpy())
        print(f"  {xs}: 조건수 {m.mulColli:.2f}, 계수 {np.round(m.betas.ravel(), 4).tolist()}")
    print(f"  VIF (고령비율, 온도편차): {({k: round(v, 2) for k, v in vif(['고령비율', '온도편차']).items()})}")
    print(f"  VIF (M4): {({k: round(v, 2) for k, v in vif(['고령비율', '온도편차', '로그밀도c']).items()})}")

    print("[누락 변수 편향] 단순회귀 기울기 = b고령 + b온도 × δ (δ = 온도편차를 고령비율에 회귀한 기울기)")
    d = np.polyfit(dong["고령비율"], dong["온도편차"], 1)[0]
    b1 = [c["coef"] for c in reps["M3"][0]["coefficients"]]
    print(f"  δ = {d:.4f}; {b1[1]:.4f} + {b1[2]:.4f} × {d:.4f} = {b1[1] + b1[2] * d:.4f} (단순회귀 {reps['M1'][0]['coefficients'][1]['coef']:.4f})")

    print("[잔차] M3")
    u = np.asarray(reps["M3"][1]["RESID"])
    small = dong["인구"] < 3000
    print(f"  잔차 왜도 {stats.skew(u):.2f}, 최대 잔차 {u.max():.2f} ({dong['동이름'].iloc[int(np.argmax(u))]}), 최소 {u.min():.2f} ({dong['동이름'].iloc[int(np.argmin(u))]})")
    print(f"  인구 3천 명 미만 {small.sum()}개 동의 잔차 표준편차 {u[small].std(ddof=1):.2f}, 나머지 {(~small).sum()}개 {u[~small].std(ddof=1):.2f}")
    A = np.column_stack([np.ones(150), 1 / dong["인구"]])
    e2 = u ** 2
    bb = np.linalg.lstsq(A, e2, rcond=None)[0]
    r2 = 1 - ((e2 - A @ bb) ** 2).sum() / ((e2 - e2.mean()) ** 2).sum()
    print(f"  잔차 제곱을 1/인구에 회귀한 코엔커형 검정: nR² = {150 * r2:.2f}, p = {stats.chi2.sf(150 * r2, 1):.2g}")

    print("[WLS] 인구로 가중한 최소제곱")
    wt = dong["인구"].to_numpy(float)
    A = np.column_stack([np.ones(150), dong["고령비율"], dong["온도편차"]])
    sw = np.sqrt(wt)
    bw = np.linalg.lstsq(A * sw[:, None], dong["출동률"].to_numpy() * sw, rcond=None)[0]
    ew = dong["출동률"].to_numpy() * sw - (A * sw[:, None]) @ bw
    cov = (ew ** 2).sum() / (150 - 3) * np.linalg.inv((A * sw[:, None]).T @ (A * sw[:, None]))
    se = np.sqrt(np.diag(cov))
    for nm, bv, sv in zip(("상수", "고령비율", "온도편차"), bw, se):
        print(f"    {nm}: 계수 {bv:.4f}, 표준오차 {sv:.4f}, t {bv / sv:.2f}")
    reps["WLS"] = (bw, se)

    print("[변환] log(출동률 + 1) ~ 고령비율 + 온도편차")
    dong["로그출동률"] = np.log(dong["출동률"] + 1)
    rep, _ = ols(["고령비율", "온도편차"], y="로그출동률")
    show(rep)
    print(f"  온도편차 계수 → 1℃당 (출동률+1)이 약 {np.expm1(rep['coefficients'][2]['coef']):.1%} 늘어남")
    return reps


# ---------------------------------------------------------------- 그림 1. 교란
def fig_confound(reps):
    W_, H = 720, 330
    s = Svg(W_, H, "행정동 고령비율과 출동률. 점의 색은 동 평균 지표온도의 세 구간. 회색 점선은 고령비율만 넣은 단순회귀선(기울기 −0.14), "
                   "색 실선은 지표온도를 함께 넣은 다중회귀에서 각 온도 구간의 평균 온도일 때의 선(기울기 +0.37)")
    ax = Axes(s, 60, 30, 440, 250, (10, 38), (0, 52))
    ax.yaxis(ticks=[0, 10, 20, 30, 40, 50], label="출동률 (1만 명당)", grid=True)
    ax.xaxis(ticks=[10, 15, 20, 25, 30, 35], label="고령비율 (%)")
    t = dong["온도편차"].to_numpy()
    cuts = np.percentile(t, [100 / 3, 200 / 3])
    grp = np.digitize(t, cuts)
    cls = ["s-ac f-acs", "s-ok f-bg", "s-bd f-bds"]
    for g in range(3):
        m = grp == g
        for xv, yv in zip(dong["고령비율"][m], dong["출동률"][m]):
            s.circle(float(ax.X(xv)), float(ax.Y(min(yv, 52))), 3.2, cls=cls[g], width=1.1)
    c1 = [c["coef"] for c in reps["M1"][0]["coefficients"]]
    ax.curve([10, 38], [c1[0] + c1[1] * 10, c1[0] + c1[1] * 38], cls="s-mu", width=1.6, dash="6 4")
    c3 = [c["coef"] for c in reps["M3"][0]["coefficients"]]
    lines = []
    for g in range(3):
        m = grp == g
        tm = t[m].mean()
        xr = np.percentile(dong["고령비율"][m], [5, 95])
        ys = c3[0] + c3[1] * xr + c3[2] * tm
        lines.append((tm, xr, ys))
    # 색 실선: 굵게, 테두리 대신 같은 계열 진한 선
    for g, (tm, xr, ys) in enumerate(lines):
        s.line(float(ax.X(xr[0])), float(ax.Y(ys[0])), float(ax.X(xr[1])), float(ax.Y(ys[1])), cls="s-fg", width=3.6)
        s.line(float(ax.X(xr[0])), float(ax.Y(ys[0])), float(ax.X(xr[1])), float(ax.Y(ys[1])), cls="s-bd" if g == 2 else "s-ac" if g == 0 else "s-ok", width=2.2)
    # 범례
    lx = 540
    s.text(lx, 40, "동 평균 지표온도", size=11, anchor="start", weight="600")
    labels = [f"낮음 (평균 {30 + lines[0][0]:.1f}℃)", f"중간 ({30 + lines[1][0]:.1f}℃)", f"높음 ({30 + lines[2][0]:.1f}℃)"]
    lcls = ["s-ac", "s-ok", "s-bd"]
    for g in range(3):
        y = 60 + g * 34
        s.circle(lx + 6, y, 4, cls=cls[g], width=1.1)
        s.line(lx + 16, y, lx + 36, y, cls=lcls[g], width=2.2)
        s.text(lx + 42, y + 4, labels[g], size=11, anchor="start")
    s.line(lx + 16, 170, lx + 36, 170, cls="s-mu", width=1.6, dash="6 4")
    s.text(lx + 42, 174, "단순회귀 (고령비율만)", size=11, anchor="start")
    s.text(lx, 210, f"단순회귀 기울기 {c1[1]:+.2f}".replace("-", "−"), size=11, anchor="start", cls="f-mu")
    s.text(lx, 228, f"다중회귀 기울기 {c3[1]:+.2f}", size=11, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "08-confound.svg"))


# ---------------------------------------------------------------- 그림 2. 잔차 진단
def fig_residuals(reps):
    W_, H = 720, 270
    cols = reps["M3"][1]
    u = np.asarray(cols["RESID"])
    f = np.asarray(cols["PRED"])
    s = Svg(W_, H, "다중회귀(출동률 ~ 고령비율 + 온도편차)의 잔차 진단. 왼쪽: 예측값과 잔차. 가운데: 행정동 인구와 잔차로, 인구가 적은 동일수록 "
                   "잔차가 크게 흩어짐(이분산). 오른쪽: 정규 Q-Q 그림으로, 점이 대각선에서 위로 휘면 오른쪽 꼬리가 긴 것임")
    # 왼쪽
    ax = Axes(s, 50, 36, 180, 170, (0, 25), (-20, 40))
    s.text(ax.x0 + 90, 20, "예측값 대 잔차", size=12, weight="600")
    ax.yaxis(ticks=[-20, 0, 20, 40])
    ax.xaxis(ticks=[0, 10, 20], label="예측값")
    ax.curve([0, 25], [0, 0], cls="s-mu", width=1)
    for a, b in zip(f, u):
        s.circle(float(ax.X(a)), float(ax.Y(b)), 2.4, cls="s-mu f-sf", width=0.6)
    # 가운데
    ax = Axes(s, 290, 36, 180, 170, (0, 19000), (-20, 40))
    s.text(ax.x0 + 90, 20, "인구 대 잔차", size=12, weight="600")
    ax.yaxis(ticks=[-20, 0, 20, 40])
    ax.xaxis(ticks=[0, 5000, 10000, 15000], label="행정동 인구", fmt=lambda t: f"{t / 1000:.0f}천" if t else "0")
    ax.curve([0, 19000], [0, 0], cls="s-mu", width=1)
    for a, b in zip(dong["인구"], u):
        s.circle(float(ax.X(a)), float(ax.Y(b)), 2.4, cls="s-mu f-sf", width=0.6)
    # 오른쪽 Q-Q
    z = (u - u.mean()) / u.std(ddof=1)
    zs = np.sort(z)
    th = stats.norm.ppf((np.arange(1, 151) - 0.5) / 150)
    ax = Axes(s, 530, 36, 170, 170, (-3, 3), (-3, 6.5))
    s.text(ax.x0 + 85, 20, "정규 Q-Q", size=12, weight="600")
    ax.yaxis(ticks=[-2, 0, 2, 4, 6])
    ax.xaxis(ticks=[-3, -2, -1, 0, 1, 2, 3], label="정규분포 분위수")
    ax.curve([-3, 3], [-3, 3], cls="s-ac", width=1.2)
    for a, b in zip(th, zs):
        s.circle(float(ax.X(a)), float(ax.Y(b)), 2.4, cls="s-mu f-sf", width=0.6)
    s.text(40, 250, "세로축: 잔차 (출동률, 1만 명당)", size=10, anchor="start", cls="f-mu")
    s.text(700, 250, "세로축: 표준화 잔차", size=10, anchor="end", cls="f-mu")
    s.save(os.path.join(OUT, "08-residuals.svg"))


# ---------------------------------------------------------------- 그림 3. 계수 비교
def fig_coef(reps):
    W_, H = 720, 270
    s = Svg(W_, H, "모형에 따른 계수와 95% 신뢰구간. 왼쪽 고령비율 계수는 온도편차를 넣으면 음수에서 양수로 바뀌고, 오른쪽 온도편차 계수는 "
                   "로그밀도를 함께 넣으면(M4) 커지면서 구간도 넓어짐(다중공선성). 강건은 White 표준오차, WLS는 인구 가중")
    rows = [("M1: 고령비율만", "M1"), ("M2: 온도편차만", "M2"), ("M3: 둘 다", "M3"), ("M3 + 강건 표준오차", "M3r"),
            ("M3 + 인구 가중 (WLS)", "WLS"), ("M4: M3 + 로그밀도", "M4")]
    panels = [("고령비율 계수", "고령비율", (-0.6, 0.9), [-0.5, 0, 0.5]), ("온도편차 계수", "온도편차", (-0.5, 4.5), [0, 1, 2, 3, 4])]
    for pi, (title, var, lim, ticks) in enumerate(panels):
        ax = Axes(s, 190 + pi * 270, 40, 230, 190, lim, (0, len(rows)))
        s.text(ax.x0 + 115, 22, title, size=12, weight="600")
        ax.xaxis(ticks=ticks, fmt=lambda t: f"{t:g}")
        ax.curve([0, 0], [0, len(rows)], cls="s-mu", width=1)
        for ri, (label, key) in enumerate(rows):
            y = float(ax.Y(len(rows) - ri - 0.5))
            if pi == 0:
                s.text(180, y + 4, label, size=11, anchor="end")
            if key == "WLS":
                bw, se = reps["WLS"]
                j = {"고령비율": 1, "온도편차": 2}[var]
                bval, sval, dfree = bw[j], se[j], 147
            else:
                rep = reps[key][0]
                row = next((c for c in rep["coefficients"] if c["name"] == var), None)
                if row is None:
                    continue
                bval, sval, dfree = row["coef"], row["se"], rep["n"] - len(rep["coefficients"])
            q = stats.t.ppf(0.975, dfree)
            s.line(float(ax.X(bval - q * sval)), y, float(ax.X(bval + q * sval)), y, cls="s-fg", width=1.6)
            s.circle(float(ax.X(bval)), y, 4, cls="s-fg f-bd", width=0.8)
    s.save(os.path.join(OUT, "08-coef.svg"))


if __name__ == "__main__":
    reps = numbers()
    fig_confound(reps)
    fig_residuals(reps)
    fig_coef(reps)
