"""5부(지구통계) 그림에서 함께 쓰는 도구. 관측소 자료, 예측 격자, 베리오그램 모형, 크리깅."""
import os

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from scipy import ndimage
from scipy.special import gamma as gamma_fn
from scipy.special import kv

from mapkit import DATA, load_dong


def stations():
    st = gpd.read_file(os.path.join(DATA, "hanbit_stations.gpkg"))
    return st, np.c_[st.geometry.x, st.geometry.y], st["기온_8월평균"].to_numpy(float)


def window():
    return load_dong().union_all()


def grid(win, g):
    x0, y0, x1, y1 = win.bounds
    gx = np.arange(x0 + g / 2, x1, g)
    gy = np.arange(y0 + g / 2, y1, g)
    GX, GY = np.meshgrid(gx, gy)
    inside = shapely.contains_xy(win, GX, GY)
    return np.c_[GX[inside], GY[inside]], inside, (gx, gy)


def lst_smooth(sigma_m):
    """50 m 지표온도를 sigma_m 가우시안으로 평활한 래스터(바다는 평균으로 채운 뒤 평활)와 변환"""
    with rasterio.open(os.path.join(DATA, "hanbit_lst.tif")) as r:
        lst = r.read(1).astype(float)
        tr = r.transform
    lst[lst <= -9000] = np.nan
    fill = np.where(np.isnan(lst), np.nanmean(lst), lst)
    sm = ndimage.gaussian_filter(fill, sigma_m / 50.0) if sigma_m > 0 else fill
    return sm, tr


def sample(raster, tr, Q, cell=50.0):
    iy = np.clip(((tr.f - Q[:, 1]) / cell).astype(int), 0, raster.shape[0] - 1)
    ix = np.clip(((Q[:, 0] - tr.c) / cell).astype(int), 0, raster.shape[1] - 1)
    return raster[iy, ix]


def dist(A, B):
    return np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1])


# ---------------------------------------------------------------- 베리오그램 모형 (c0 너깃, c 부분 문턱값, a 실효 상관거리)
def sph(h, c0, c, a):
    h = np.asarray(h, float)
    return np.where(h == 0, 0.0, np.where(h < a, c0 + c * (1.5 * h / a - 0.5 * (h / a) ** 3), c0 + c))


def expo(h, c0, c, a):
    h = np.asarray(h, float)
    return np.where(h == 0, 0.0, c0 + c * (1 - np.exp(-3 * h / a)))


def gauss(h, c0, c, a):
    h = np.asarray(h, float)
    return np.where(h == 0, 0.0, c0 + c * (1 - np.exp(-3 * (h / a) ** 2)))


def matern(nu):
    from scipy.optimize import brentq

    def rho(u):
        return (2 ** (1 - nu) / gamma_fn(nu)) * u ** nu * kv(nu, u)

    k = brentq(lambda u: rho(u) - 0.05, 1e-3, 50)  # a에서 상관이 0.05가 되도록(a = 실효 상관거리)

    def f(h, c0, c, a):
        h = np.asarray(h, float)
        u = np.maximum(h, 1e-9) / a * k
        corr = rho(u)
        return np.where(h == 0, 0.0, c0 + c * (1 - corr))
    return f


def empirical(X, z, width, maxd):
    n = len(z)
    D = dist(X, X)
    iu = np.triu_indices(n, 1)
    d = D[iu]
    g = (0.5 * (z[:, None] - z[None]) ** 2)[iu]
    rows = []
    for a in np.arange(0, maxd, width):
        m = (d > a) & (d <= a + width)
        if m.sum():
            rows.append((d[m].mean(), g[m].mean(), int(m.sum())))
    return np.array(rows), d, g


def fit_wls(E, f, p0, lo=(0, 1e-6, 200), hi=(np.inf, np.inf, 1e5)):
    """Cressie(1985)의 가중 최소제곱: 가중치 N(h)/γ(h)²"""
    from scipy.optimize import least_squares

    h, g, nn = E.T
    r = least_squares(lambda p: np.sqrt(nn) * (f(h, *p) - g) / np.maximum(f(h, *p), 1e-9), p0, bounds=(lo, hi))
    return r.x, float((nn * ((f(h, *r.x) - g) / np.maximum(f(h, *r.x), 1e-9)) ** 2).sum())


# ---------------------------------------------------------------- 크리깅 (공분산 C(h) = 문턱값 − γ(h))
def krige(X, z, X0, vf, params, kind="ok", F=None, F0=None, mean=None):
    """kind: sk(단순, mean 필요), ok(정규), uk(보편: F, F0는 추세 설계행렬 열들)"""
    c0, c, a = params
    sill = c0 + c
    C = sill - vf(dist(X, X), *params)
    C0 = sill - vf(dist(X, X0), *params)
    n = len(z)
    if kind == "sk":
        w = np.linalg.solve(C, C0)
        pred = mean + w.T @ (z - mean)
        var = sill - np.sum(w * C0, axis=0)
        return pred, var
    if kind == "ok":
        F = np.ones((n, 1))
        F0 = np.ones((len(X0), 1))
    p = F.shape[1]
    A = np.zeros((n + p, n + p))
    A[:n, :n] = C
    A[:n, n:] = F
    A[n:, :n] = F.T
    B = np.vstack([C0, F0.T])
    sol = np.linalg.solve(A, B)
    w, mu = sol[:n], sol[n:]
    pred = w.T @ z
    var = sill - np.sum(w * C0, axis=0) - np.sum(mu * F0.T, axis=0)
    return pred, var
