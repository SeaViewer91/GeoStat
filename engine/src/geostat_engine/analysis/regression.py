"""회귀 분석: OLS(공간진단 포함), 공간시차·공간오차 모형(spreg), GWR·MGWR(mgwr).

실행은 두 단계로 나눔
  prepare() : 엔진 프로세스에서 데이터를 검사하고 계산에 필요한 배열만 모음
  run()     : 별도 작업 프로세스에서 계산함 (취소하려면 프로세스를 끝내면 됨)
결과는 JSON으로 보낼 수 있는 보고서(report)와 속성 테이블에 붙일 열(columns)로 돌려줌.
"""

from __future__ import annotations

import contextlib
import io
import math
import re
import warnings
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
import pandas as pd

from geostat_engine.errors import EngineError

Model = Literal["ols", "lag", "error", "gwr", "mgwr"]
MODELS: tuple[str, ...] = ("ols", "lag", "error", "gwr", "mgwr")
MODEL_LABELS = {
    "ols": "OLS (최소제곱)",
    "lag": "공간시차 모형 (Spatial Lag, ML)",
    "error": "공간오차 모형 (Spatial Error, ML)",
    "gwr": "지리가중회귀 (GWR)",
    "mgwr": "다중척도 지리가중회귀 (MGWR)",
}
DEFAULT_PREFIX = {"ols": "OLS", "lag": "LAG", "error": "ERR", "gwr": "GWR", "mgwr": "MGWR"}

# 이 관측치 수를 넘으면 ML 추정에 희소 행렬(LU) 방식을 씀 (full은 n×n 행렬을 만들어 메모리가 큼)
ML_FULL_MAX_N = 2000
# GWR·MGWR 최소 관측치 수 (대역폭 탐색에 필요한 이웃 수를 확보하기 위함)
GWR_MIN_N = 20
# GWR·MGWR 권장 최대 관측치 수 (넘으면 경고만 함)
GWR_WARN_N = 10000
MGWR_WARN_N = 5000

Progress = Callable[[float | None, str], None]


# ---- 준비 (엔진 프로세스) ------------------------------------------------------


def _numeric(frame: pd.DataFrame, name: str) -> np.ndarray:
    if name not in frame.columns:
        raise EngineError("column_not_found", f"열이 없음: {name}")
    s = frame[name]
    if not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s):
        raise EngineError("not_numeric", f"숫자 열이 아님: {name}")
    return s.to_numpy(dtype="float64", na_value=np.nan)


def safe_name(name: str) -> str:
    """결과 열 이름에 넣을 변수 이름 (공백·특수문자는 밑줄로 바꿈)."""
    return re.sub(r"[^\w가-힣]+", "_", name).strip("_") or "X"


def prepare(
    gdf, spec: dict[str, Any], weights: Any | None, coords: np.ndarray | None
) -> dict[str, Any]:
    model = spec.get("model")
    if model not in MODELS:
        raise EngineError("invalid_model", f"알 수 없는 모형: {model}")
    y_name = spec.get("y")
    x_names = list(dict.fromkeys(spec.get("x") or []))  # 순서 유지 중복 제거
    if not y_name or not x_names:
        raise EngineError("missing_variables", "종속변수와 독립변수를 하나 이상 골라야 함")
    if y_name in x_names:
        raise EngineError("invalid_variables", "종속변수를 독립변수로 함께 쓸 수 없음")

    frame = gdf.drop(columns=gdf.geometry.name)
    y = _numeric(frame, y_name)
    X = np.column_stack([_numeric(frame, x) for x in x_names])
    missing = np.isnan(y) | np.isnan(X).any(axis=1)
    if missing.any():
        raise EngineError(
            "missing_values",
            f"선택한 변수에 값 없는 행이 {int(missing.sum())}개 있음. 회귀 분석은 결측을 허용하지 않음",
        )
    n, k = X.shape
    if n <= k + 1:
        raise EngineError("too_few", f"관측치({n})가 변수 수({k})보다 충분히 많아야 함")
    for j, name in enumerate(x_names):
        if np.ptp(X[:, j]) == 0:
            raise EngineError("constant", f"'{name}'의 값이 모두 같음 (상수항과 겹침)")
    design = np.column_stack([np.ones(n), X])
    if np.linalg.matrix_rank(design) < design.shape[1]:
        raise EngineError(
            "collinear",
            "독립변수끼리 완전한 선형 관계가 있음 (예: 합이 일정한 비율 변수). 변수를 빼야 함",
        )

    notes: list[str] = []
    if model in ("lag", "error") and weights is None:
        raise EngineError("weights_required", "공간시차·공간오차 모형은 공간가중치가 필요함")
    if weights is not None:
        n_islands = sum(1 for i in range(weights.n) if weights.cardinalities[i] == 0)
        if n_islands:
            notes.append(f"이웃 없는 피처 {n_islands}개가 있어 공간 진단·추정이 왜곡될 수 있음")
    if model in ("gwr", "mgwr"):
        if coords is None:
            raise EngineError("coords_required", "GWR에는 좌표가 필요함")
        if n < GWR_MIN_N:
            raise EngineError(
                "too_few", f"GWR·MGWR은 관측치가 {GWR_MIN_N}개 이상이어야 함 (현재 {n}개)"
            )
        limit = GWR_WARN_N if model == "gwr" else MGWR_WARN_N
        if n > limit:
            notes.append(f"관측치가 {n:,}개라 계산이 오래 걸릴 수 있음 (권장 {limit:,}개 이하)")

    return {
        "model": model,
        "y_name": y_name,
        "x_names": x_names,
        "y": y,
        "X": X,
        "weights": weights,
        "coords": coords,
        "options": {
            "kernel": spec.get("kernel", "bisquare"),
            "fixed": bool(spec.get("fixed", False)),
            "criterion": spec.get("criterion", "AICc"),
            "bandwidth": spec.get("bandwidth"),
            "alpha": float(spec.get("alpha", 0.05)),
            "white_test": bool(spec.get("white_test", True)),
        },
        "notes": notes,
    }


# ---- 계산 (작업 프로세스) --------------------------------------------------------


def run(payload: dict[str, Any], progress: Progress) -> dict[str, Any]:
    model = payload["model"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if model == "ols":
            out = _ols(payload, progress)
        elif model in ("lag", "error"):
            out = _ml(payload, progress)
        else:
            out = _gwr(payload, progress)
    out["report"]["notes"] = payload["notes"] + out["report"].get("notes", [])
    return out


def _f(v: Any) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _coef_rows(names: list[str], betas, se, stats) -> list[dict[str, Any]]:
    return [
        {"name": n, "coef": _f(b), "se": _f(s), "stat": _f(t), "p": _f(p)}
        for n, b, s, (t, p) in zip(names, np.ravel(betas), np.ravel(se), stats, strict=True)
    ]


def _base_report(payload: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        "model": model,
        "title": MODEL_LABELS[model],
        "y": payload["y_name"],
        "x": payload["x_names"],
        "n": int(payload["X"].shape[0]),
        "summary": [],
        "coefficients": [],
        "stat_label": "t",
        "diagnostics": [],
        "local": None,
        "notes": [],
    }


def _diag(group: str, name: str, value: Any, p: Any = None, df: Any = None) -> dict[str, Any]:
    return {"group": group, "name": name, "value": _f(value), "p": _f(p), "df": _f(df)}


def _ols(payload: dict[str, Any], progress: Progress) -> dict[str, Any]:
    import spreg

    progress(None, "OLS 추정 중")
    y = payload["y"].reshape(-1, 1)
    X = payload["X"]
    w = payload["weights"]
    names = payload["x_names"]
    opts = payload["options"]
    kw: dict[str, Any] = {
        "name_y": payload["y_name"],
        "name_x": names,
        "white_test": opts["white_test"],
    }
    if w is not None:
        w.transform = "r"
        kw.update({"w": w, "spat_diag": True, "moran": True})
    m = spreg.OLS(y, X, **kw)

    rep = _base_report(payload, "ols")
    rep["summary"] = [
        ["관측치", m.n],
        ["변수 수 (상수 포함)", m.k],
        ["R²", _f(m.r2)],
        ["수정 R²", _f(m.ar2)],
        ["F 통계량", _f(m.f_stat[0])],
        ["F 유의확률", _f(m.f_stat[1])],
        ["로그우도", _f(m.logll)],
        ["AIC", _f(m.aic)],
        ["SC (BIC)", _f(m.schwarz)],
        ["잔차 분산 (σ²)", _f(m.sig2)],
    ]
    rep["coefficients"] = _coef_rows(m.name_x, m.betas, m.std_err, m.t_stat)
    d = rep["diagnostics"]
    d.append(_diag("다중공선성", "조건수 (Condition number)", m.mulColli))
    jb = m.jarque_bera
    d.append(_diag("정규성", "Jarque-Bera", jb["jb"], jb["pvalue"], jb["df"]))
    bp, kb = m.breusch_pagan, m.koenker_bassett
    d.append(_diag("이분산성", "Breusch-Pagan", bp["bp"], bp["pvalue"], bp["df"]))
    d.append(_diag("이분산성", "Koenker-Bassett", kb["kb"], kb["pvalue"], kb["df"]))
    if opts["white_test"] and getattr(m, "white", None):
        d.append(_diag("이분산성", "White", m.white["wh"], m.white["pvalue"], m.white["df"]))
    if w is not None:
        mi = m.moran_res
        d.append(_diag("공간 의존성", "잔차 Moran's I", mi[0], mi[2]))
        d.append(_diag("공간 의존성", "Moran's I (z)", mi[1]))
        for label, attr in (
            ("LM (lag)", "lm_lag"),
            ("Robust LM (lag)", "rlm_lag"),
            ("LM (error)", "lm_error"),
            ("Robust LM (error)", "rlm_error"),
            ("LM (SARMA)", "lm_sarma"),
        ):
            stat, p = getattr(m, attr)
            d.append(_diag("공간 의존성", label, stat, p, 2 if attr == "lm_sarma" else 1))
        rep["notes"].append(_lm_advice(m))
    if _f(m.mulColli) and m.mulColli > 30:
        rep["notes"].append("조건수가 30을 넘어 다중공선성이 의심됨")

    predy = np.ravel(m.predy)
    return {"report": rep, "columns": {"PRED": predy, "RESID": np.ravel(m.u)}}


def _lm_advice(m) -> str:
    """Anselin(2005)의 LM 검정 판단 절차를 한 문장으로 요약함."""
    p_lag, p_err = m.lm_lag[1], m.lm_error[1]
    alpha = 0.05
    if p_lag > alpha and p_err > alpha:
        return "LM 검정상 공간 의존성이 뚜렷하지 않음 → OLS로 충분할 수 있음"
    if p_lag <= alpha and p_err > alpha:
        return "LM-lag만 유의함 → 공간시차 모형을 검토할 만함"
    if p_err <= alpha and p_lag > alpha:
        return "LM-error만 유의함 → 공간오차 모형을 검토할 만함"
    r_lag, r_err = m.rlm_lag[1], m.rlm_error[1]
    if r_lag <= alpha < r_err:
        return "두 LM이 모두 유의하고 Robust LM-lag만 유의함 → 공간시차 모형을 검토할 만함"
    if r_err <= alpha < r_lag:
        return "두 LM이 모두 유의하고 Robust LM-error만 유의함 → 공간오차 모형을 검토할 만함"
    if r_lag <= r_err:
        return "두 Robust LM이 모두 유의함 → 값이 더 큰 공간시차 모형을 먼저 검토할 만함"
    return "두 Robust LM이 모두 유의함 → 값이 더 큰 공간오차 모형을 먼저 검토할 만함"


def _ml(payload: dict[str, Any], progress: Progress) -> dict[str, Any]:
    import spreg

    model = payload["model"]
    y = payload["y"].reshape(-1, 1)
    X = payload["X"]
    w = payload["weights"]
    w.transform = "r"
    n = X.shape[0]
    method = "full" if n <= ML_FULL_MAX_N else "LU"
    kw = {"name_y": payload["y_name"], "name_x": payload["x_names"], "method": method}

    progress(None, "비교용 OLS 추정 중")
    ols = spreg.OLS(y, X)
    progress(None, f"최대우도 추정 중 ({method})")
    if model == "lag":
        m = spreg.ML_Lag(y, X, w, **kw)
        param, param_name = m.rho, "ρ (공간시차 계수)"
    else:
        m = spreg.ML_Error(y, X, w, **kw)
        param, param_name = m.lam, "λ (공간오차 계수)"

    rep = _base_report(payload, model)
    rep["stat_label"] = "z"
    lr = 2 * (m.logll - ols.logll)
    from scipy import stats

    rep["summary"] = [
        ["관측치", m.n],
        [param_name, _f(param)],
        ["유사 R² (Pseudo R²)", _f(m.pr2)],
        ["로그우도", _f(m.logll)],
        ["AIC", _f(m.aic)],
        ["SC (BIC)", _f(m.schwarz)],
        ["OLS 로그우도", _f(ols.logll)],
        ["OLS AIC", _f(ols.aic)],
        ["잔차 분산 (σ²)", _f(m.sig2)],
        ["추정 방식", method],
    ]
    names = list(m.name_x)
    names[-1] = "ρ (W_y)" if model == "lag" else "λ"
    rep["coefficients"] = _coef_rows(names, m.betas, m.std_err, m.z_stat)
    rep["diagnostics"].append(
        _diag("모형 비교", "우도비 검정 (vs OLS)", lr, stats.chi2.sf(lr, 1), 1)
    )
    # 잔차 이분산성 (Breusch-Pagan): 잔차 제곱을 독립변수에 회귀해 계산함
    u = np.ravel(m.u)
    bp = _breusch_pagan(u, X)
    rep["diagnostics"].append(_diag("이분산성", "Breusch-Pagan", bp[0], bp[1], X.shape[1]))
    if model == "lag":
        rep["notes"].append(
            "공간시차 모형의 계수는 파급효과 때문에 한계효과와 같지 않음 (직접·간접 효과 해석 필요)"
        )
    return {"report": rep, "columns": {"PRED": np.ravel(m.predy), "RESID": u}}


def _breusch_pagan(u: np.ndarray, X: np.ndarray) -> tuple[float, float]:
    from scipy import stats

    # BP = (잔차 제곱/σ² 을 독립변수에 회귀한 설명 제곱합) / 2
    n = len(u)
    g = u**2 / (u @ u / n)
    Z = np.column_stack([np.ones(n), X])
    coef, *_ = np.linalg.lstsq(Z, g, rcond=None)
    fitted = Z @ coef
    bp = 0.5 * float(((fitted - g.mean()) ** 2).sum())
    return bp, float(stats.chi2.sf(bp, X.shape[1]))


class _VerboseCapture(io.TextIOBase):
    """mgwr이 print로 내보내는 진행 메시지를 받아 진행률로 바꿈."""

    _soc = re.compile(r"Current iteration:\s*(\d+)\s*,\s*SOC:\s*([0-9.eE+-]+)")
    _bw = re.compile(r"Bandwidth:\s*([0-9.eE+-]+)\s*,\s*score:\s*([0-9.eE+-]+)")

    def __init__(self, progress: Progress, tol: float, stage: str) -> None:
        self.progress = progress
        self.tol = tol
        self.stage = stage
        self.first_soc: float | None = None
        self._buf = ""

    def write(self, s: str) -> int:
        # print는 인수마다 따로 write를 부르므로 줄 단위로 모아서 해석함
        self._buf += s
        *lines, self._buf = self._buf.split("\n")
        for line in lines:
            m = self._soc.search(line)
            if m:
                it, soc = int(m.group(1)), float(m.group(2))
                if self.first_soc is None:
                    self.first_soc = soc
                frac = None
                if self.first_soc and soc > 0 and self.first_soc > self.tol:
                    span = math.log(self.first_soc) - math.log(self.tol)
                    frac = min(0.99, max(0.0, (math.log(self.first_soc) - math.log(soc)) / span))
                self.progress(frac, f"{self.stage}: 반복 {it}, 수렴도 {soc:.2e}")
                continue
            m = self._bw.search(line)
            if m:
                self.progress(None, f"{self.stage}: 대역폭 {float(m.group(1)):,.1f} 평가 중")
        return len(s)


def _gwr(payload: dict[str, Any], progress: Progress) -> dict[str, Any]:
    from mgwr.gwr import GWR, MGWR
    from mgwr.sel_bw import Sel_BW

    model = payload["model"]
    opts = payload["options"]
    coords = payload["coords"]
    y = payload["y"].reshape(-1, 1)
    X = payload["X"]
    n, k = X.shape
    names = ["상수"] + payload["x_names"]
    kernel, fixed, criterion = opts["kernel"], opts["fixed"], opts["criterion"]
    n_jobs = -1 if n >= 3000 else 1
    # mgwr의 적응 대역폭 기본 최솟값은 40+2(k+1)개 이웃이라 작은 자료에서는 탐색 범위를 직접 줌
    bw_range: dict[str, Any] = {}
    default_min = 40 + 2 * (k + 1)
    if not fixed and n <= default_min:
        # 황금분할 탐색은 최솟값 설정을 무시하므로 작은 자료는 1씩 늘리는 구간 탐색을 씀
        lo, hi = max(k + 3, n // 3), n - 1
        bw_range = {"search_method": "interval", "interval": 1, "bw_min": lo, "bw_max": hi}

    if model == "mgwr":
        # MGWR은 변수 척도를 맞추려고 표준화한 값으로 추정함 (mgwr 권장)
        y_fit = (y - y.mean()) / y.std()
        X_fit = (X - X.mean(axis=0)) / X.std(axis=0)
        progress(0.0, "MGWR 대역폭 탐색 시작")
        sel = Sel_BW(coords, y_fit, X_fit, multi=True, kernel=kernel, fixed=fixed, n_jobs=n_jobs)
        tol = 1e-5
        cap = _VerboseCapture(progress, tol, "MGWR 역적합")
        with contextlib.redirect_stdout(cap):
            multi_range: dict[str, Any] = {}
            if bw_range:
                # 작은 자료: 초기 대역폭을 먼저 구간 탐색으로 구해 넘기고 변수별 탐색 범위도 제한함
                init = Sel_BW(coords, y_fit, X_fit, kernel=kernel, fixed=fixed, n_jobs=n_jobs)
                init_bw = init.search(criterion=criterion, **bw_range)
                multi_range = {
                    "search_method": "interval",
                    "interval": 1,
                    "init_multi": init_bw,
                    "multi_bw_min": [bw_range["bw_min"]],
                    "multi_bw_max": [bw_range["bw_max"]],
                }
            sel.search(criterion=criterion, verbose=True, tol_multi=tol, **multi_range)
        progress(0.99, "MGWR 결과 계산 중")
        res = MGWR(coords, y_fit, X_fit, sel, kernel=kernel, fixed=fixed, n_jobs=n_jobs).fit()
        bws = [float(b) for b in np.ravel(sel.bw[0])]
    else:
        X_fit, y_fit = X, y
        bw = opts.get("bandwidth")
        if bw is None:
            progress(None, "GWR 대역폭 탐색 중")
            sel = Sel_BW(coords, y, X, kernel=kernel, fixed=fixed, n_jobs=n_jobs)
            cap = _VerboseCapture(progress, 1e-6, "GWR")
            with contextlib.redirect_stdout(cap):
                bw = sel.search(criterion=criterion, verbose=True, **bw_range)
        progress(None, f"GWR 적합 중 (대역폭 {float(bw):,.1f})")
        res = GWR(coords, y, X, bw, kernel=kernel, fixed=fixed, n_jobs=n_jobs).fit()
        bws = [float(bw)] * (k + 1)

    params = np.asarray(res.params)
    tvals = np.asarray(res.tvalues)
    alpha = opts["alpha"]
    # 다중검정 보정(da Silva & Fotheringham 2016)을 반영해 유의하지 않은 t값은 0으로 만듦
    filtered = np.asarray(res.filter_tvals(alpha=alpha))
    sig = (filtered != 0).astype("int8")

    rep = _base_report(payload, model)
    unit = "개 이웃" if not fixed else " (거리 단위)"
    rep["summary"] = [
        ["관측치", n],
        ["커널", f"{kernel} · {'고정' if fixed else '적응'} 대역폭"],
        [
            "대역폭 선택 기준",
            criterion if opts.get("bandwidth") is None or model == "mgwr" else "직접 지정",
        ],
    ]
    if model == "gwr":
        rep["summary"].append(["대역폭", f"{bws[0]:,.1f}{unit}"])
    rep["summary"] += [
        ["R²", _f(res.R2)],
        ["수정 R²", _f(res.adj_R2)],
        ["AICc", _f(res.aicc)],
        ["AIC", _f(res.aic)],
        ["유효 모수 수 (ENP)", _f(res.ENP)],
        ["잔차 제곱합", _f(res.resid_ss)],
    ]
    if model == "mgwr":
        rep["notes"].append("MGWR 계수는 표준화한 변수 기준임 (단위 1 표준편차당 변화)")

    adj_alpha = np.ravel(res.adj_alpha) if model == "gwr" else None
    local_rows = []
    for j, name in enumerate(names):
        b = params[:, j]
        q = np.percentile(b, [0, 25, 50, 75, 100])
        local_rows.append(
            {
                "name": name,
                "bandwidth": bws[j],
                "mean": _f(b.mean()),
                "sd": _f(b.std()),
                "min": _f(q[0]),
                "q1": _f(q[1]),
                "median": _f(q[2]),
                "q3": _f(q[3]),
                "max": _f(q[4]),
                "pct_significant": _f(sig[:, j].mean() * 100),
            }
        )
    rep["local"] = local_rows
    rep["diagnostics"].append(
        _diag(
            "지역 추정",
            "보정 유의수준 (상수 기준)" if adj_alpha is not None else "유의수준",
            adj_alpha[1] if adj_alpha is not None else alpha,
        )
    )

    columns: dict[str, np.ndarray] = {}
    for j, name in enumerate(names):
        key = "CONST" if j == 0 else safe_name(name)
        columns[f"B_{key}"] = params[:, j]
        columns[f"T_{key}"] = tvals[:, j]
        columns[f"SIG_{key}"] = sig[:, j]
    if model == "gwr":
        columns["R2"] = np.ravel(res.localR2)
        columns["PRED"] = np.ravel(res.predy)
        columns["RESID"] = np.ravel(res.resid_response)
    else:
        # 표준화 척도의 예측값을 원래 척도로 되돌림
        pred = np.ravel(res.predy) * y.std() + y.mean()
        columns["PRED"] = pred
        columns["RESID"] = np.ravel(y) - pred
    return {"report": rep, "columns": columns}


# ---- 보고서 텍스트 ---------------------------------------------------------------


def _fmt(v: Any, digits: int = 6) -> str:
    if v is None:
        return "-"
    if isinstance(v, str):
        return v
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and abs(v) < 1e12):
        return f"{int(v):,}"
    if abs(v) < 1e-4 and v != 0:
        return f"{v:.3e}"
    return f"{v:,.{digits}g}"


def report_text(report: dict[str, Any], description: str = "") -> str:
    """GeoDa 회귀 보고서처럼 읽기 쉬운 텍스트로 만듦."""
    lines = [
        "=" * 72,
        f"GeoStat 회귀 분석 보고서 — {report['title']}",
        "=" * 72,
        f"종속변수: {report['y']}",
        f"독립변수: {', '.join(report['x'])}",
    ]
    if description:
        lines.append(f"설정: {description}")
    lines.append("")
    for label, value in report["summary"]:
        lines.append(f"  {label:<24}{_fmt(value)}")
    if report["coefficients"]:
        stat = report["stat_label"]
        lines += [
            "",
            "-" * 72,
            f"{'변수':<20}{'계수':>14}{'표준오차':>14}{stat + '값':>10}{'유의확률':>12}",
            "-" * 72,
        ]
        for r in report["coefficients"]:
            lines.append(
                f"{r['name']:<20}{_fmt(r['coef']):>14}{_fmt(r['se']):>14}"
                f"{_fmt(r['stat'], 4):>10}{_fmt(r['p'], 4):>12}"
            )
    if report.get("local"):
        lines += ["", "-" * 72, "지역 계수 요약", "-" * 72]
        lines.append(
            f"{'변수':<14}{'대역폭':>10}{'평균':>12}{'최소':>12}{'중앙값':>12}{'최대':>12}{'유의%':>8}"
        )
        for r in report["local"]:
            lines.append(
                f"{r['name']:<14}{_fmt(r['bandwidth'], 5):>10}{_fmt(r['mean'], 5):>12}{_fmt(r['min'], 5):>12}"
                f"{_fmt(r['median'], 5):>12}{_fmt(r['max'], 5):>12}{_fmt(r['pct_significant'], 3):>8}"
            )
    if report["diagnostics"]:
        lines += ["", "-" * 72, "진단", "-" * 72]
        group = None
        for d in report["diagnostics"]:
            if d["group"] != group:
                group = d["group"]
                lines.append(f"[{group}]")
            df = f" (df={_fmt(d['df'])})" if d["df"] is not None else ""
            p = f"  p={_fmt(d['p'], 4)}" if d["p"] is not None else ""
            lines.append(f"  {d['name']}{df}: {_fmt(d['value'])}{p}")
    if report.get("notes"):
        lines += ["", "참고"] + [f"  · {n}" for n in report["notes"] if n]
    lines.append("")
    return "\n".join(lines)
