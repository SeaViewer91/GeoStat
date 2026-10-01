"""4부(점 패턴) 그림에서 함께 쓰는 도구. 출동 점, 관찰창(시 경계), 인구 격자, 커널, 모의."""
import os

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from scipy import sparse
from scipy.spatial import cKDTree

from mapkit import DATA, load_dong


def window():
    """관찰창: 행정동을 합친 시 경계(바다 제외)"""
    return load_dong().union_all()


def events():
    ev = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
    return ev, np.c_[ev.geometry.x, ev.geometry.y]


def grid(win, g):
    """관찰창 안의 g m 격자 중심점과 (행, 열) 배열 모양"""
    x0, y0, x1, y1 = win.bounds
    gx = np.arange(x0 + g / 2, x1, g)
    gy = np.arange(y0 + g / 2, y1, g)
    GX, GY = np.meshgrid(gx, gy)
    inside = shapely.contains_xy(win, GX, GY)
    return np.c_[GX[inside], GY[inside]], inside, (gx, gy)


def kmat(pts, at, h, cut=4.0):
    """가우시안 커널 값 행렬 (점 × 평가 위치), 단위 1/m²"""
    sm = cKDTree(pts).sparse_distance_matrix(cKDTree(at), cut * h, output_type="coo_matrix")
    v = np.exp(-sm.data ** 2 / (2 * h * h)) / (2 * np.pi * h * h)
    return sparse.csr_matrix((v, (sm.row, sm.col)), shape=(len(pts), len(at)))


def edge_mass(G, cellA, h, at=None):
    """위치마다 커널 질량 가운데 관찰창 안에 드는 비율 (균일 경계 보정용)"""
    at = G if at is None else at
    return np.asarray(kmat(G, at, h).sum(0)).ravel() * cellA


def pop_grid():
    """100 m 인구·고령인구 격자 (값, 중심 좌표)"""
    with rasterio.open(os.path.join(DATA, "hanbit_pop100.tif")) as r:
        pop = r.read(1).astype(float)
        eld = r.read(2).astype(float)
        tr = r.transform
    pop[pop < 0] = 0
    eld[eld < 0] = 0
    return pop, eld, tr


def sim_csr(win, n, rng):
    x0, y0, x1, y1 = win.bounds
    out = np.empty((0, 2))
    while len(out) < n:
        q = rng.uniform([x0, y0], [x1, y1], size=(2 * n, 2))
        out = np.vstack([out, q[shapely.contains_xy(win, q[:, 0], q[:, 1])]])
    return out[:n]


def sim_weighted(weights, tr, n, rng, win=None):
    """래스터 셀 값에 비례하는 불균질 포아송(점 수 n 고정). 셀 안에서는 균일"""
    p = (weights / weights.sum()).ravel()
    out = np.empty((0, 2))
    while len(out) < n:
        m = n - len(out)
        idx = rng.choice(p.size, size=m, p=p)
        iy, ix = np.unravel_index(idx, weights.shape)
        x = tr.c + tr.a * (ix + rng.random(m))
        y = tr.f + tr.e * (iy + rng.random(m))
        q = np.c_[x, y]
        if win is not None:
            q = q[shapely.contains_xy(win, x, y)]
        out = np.vstack([out, q])
    return out[:n]


def nn_dist(P):
    d, _ = cKDTree(P).query(P, k=2)
    return d[:, 1]


def k_border(Q, win, R, lam_w=None):
    """경계 보정 K(r). 시 경계에서 r보다 가까운 점은 중심점으로 쓰지 않음. lam_w(점마다 강도)를 주면 불균질 K"""
    b = shapely.distance(win.boundary, shapely.points(Q))
    pairs = cKDTree(Q).query_pairs(R[-1], output_type="ndarray")
    d = np.hypot(*(Q[pairs[:, 0]] - Q[pairs[:, 1]]).T)
    i, j = pairs[:, 0], pairs[:, 1]
    out = np.full(len(R), np.nan)
    lam = len(Q) / win.area
    for k, r in enumerate(R):
        if r == 0:
            out[k] = 0.0
            continue
        m = d <= r
        if lam_w is None:
            nb = (b >= r).sum()
            out[k] = ((m & (b[i] >= r)).sum() + (m & (b[j] >= r)).sum()) / (lam * nb) if nb else np.nan
        else:
            w = 1 / lam_w
            den = w[b >= r].sum()
            out[k] = ((w[i] * w[j] * (m & (b[i] >= r))).sum() + (w[i] * w[j] * (m & (b[j] >= r))).sum()) / den if den else np.nan
    return out


def l_minus_r(K, R):
    return np.sqrt(np.maximum(K, 0) / np.pi) - R
