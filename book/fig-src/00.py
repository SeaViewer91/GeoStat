"""0강 그림과 본문 수치.

- 00-same-values.svg : 같은 값 36개를 세 가지로 배치한 지도와 공통 히스토그램
- 00-false-positive.svg : 서로 관계없는 두 공간 변수의 상관 검정이 '유의'로 나오는 비율
- 00-heterogeneity.svg : 두 권역에서 관계 방향이 반대인 자료와 전체 회귀선
- 00-three-branches.svg : 공간 자료의 세 유형

실행: python book/fig-src/00.py  (본문에 쓰는 수치를 함께 출력함)
"""
import os
import sys

import numpy as np
from scipy import ndimage, stats

sys.path.insert(0, os.path.dirname(__file__))
from svglib import Svg  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "fig")
os.makedirs(OUT, exist_ok=True)


# ---------------------------------------------------------------- 공통
def rook(R, C):
    """R×C 격자의 룩 인접 이진 가중치"""
    n = R * C
    W = np.zeros((n, n))
    for r in range(R):
        for c in range(C):
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < R and 0 <= cc < C:
                    W[r * C + c, rr * C + cc] = 1
    return W


def moran(x, W):
    z = x - x.mean()
    return len(x) / W.sum() * (z @ W @ z) / (z @ z)


def qclass(v, edges):
    return int(np.searchsorted(edges, v, side="right"))


# ---------------------------------------------------------------- 1. 같은 값, 다른 지도
def fig_same_values():
    R = C = 6
    n = R * C
    W = rook(R, C)
    rng = np.random.default_rng(20260930)
    vals = np.sort(np.round(rng.normal(50, 10, n)))

    # (가) 모임: 왼쪽 위에서 오른쪽 아래로 갈수록 값이 작아지게 대각선 순서로 배치
    order = sorted(range(n), key=lambda k: (k // C + k % C, k // C))
    clustered = np.empty(n)
    clustered[order] = vals[::-1]

    # (나) 무작위: 무작위로 섞되, 모란 지수가 기댓값 −1/35 가까이 나온 배치를 씀
    expected = -1 / (n - 1)
    for seed in range(1000):
        cand = np.random.default_rng(seed).permutation(vals)
        if abs(moran(cand, W) - expected) < 0.01:
            random_ = cand
            break

    # (다) 엇갈림: 큰 값 18개는 바둑판의 검은 칸, 작은 값 18개는 흰 칸
    black = [k for k in range(n) if (k // C + k % C) % 2 == 0]
    white = [k for k in range(n) if (k // C + k % C) % 2 == 1]
    checker = np.empty(n)
    checker[black] = vals[n // 2:][::-1]
    checker[white] = vals[: n // 2]

    layouts = [("(가) 모여 있음", clustered), ("(나) 무작위", random_), ("(다) 엇갈림", checker)]
    Is = [moran(x, W) for _, x in layouts]
    edges = np.quantile(vals, [0.2, 0.4, 0.6, 0.8])

    s = Svg(720, 330, "같은 값 36개를 세 가지로 배치한 지도. 평균·표준편차·히스토그램은 같지만 모란 지수는 0.8대에서 −0.9대까지 다름")
    cell = 26
    x0s = [30, 230, 430]
    y0 = 40
    for (name, x), I, x0 in zip(layouts, Is, x0s):
        s.text(x0 + cell * C / 2, 26, name, size=13, weight="600")
        for k in range(n):
            r, c = divmod(k, C)
            s.rect(x0 + c * cell, y0 + r * cell, cell, cell, cls=f"s-bg q{qclass(x[k], edges)}", width=1)
        s.rect(x0, y0, cell * C, cell * R, cls="s-mu", width=1).parts[-1] = s.parts[-1].replace("/>", ' fill="none"/>')
        s.text(x0 + cell * C / 2, y0 + cell * R + 22, f"모란 지수 I = {I:.2f}", size=12)
    s.text(330, 256, "세 지도 모두 평균 {:.1f}, 표준편차 {:.1f}".format(vals.mean(), vals.std(ddof=1)), size=12, cls="f-mu")

    # 히스토그램 (세 지도 공통)
    hx, hy, hw, hh = 650, 40, 55, 156
    bins = np.arange(20, 81, 10)
    counts, _ = np.histogram(vals, bins)
    keep = np.nonzero(counts)[0]
    bins, counts = bins[keep[0]:keep[-1] + 2], counts[keep[0]:keep[-1] + 1]
    s.text(hx + hw / 2 - 4, 26, "값의 분포", size=13, weight="600")
    bh = hh / len(counts)
    for i, cnt in enumerate(counts):
        y = hy + hh - (i + 1) * bh
        s.rect(hx, y + 1, cnt / counts.max() * hw, bh - 2, cls="f-mu", width=0)
        s.text(hx - 4, y + bh / 2 + 4, f"{bins[i]}–{bins[i + 1] - 1}", size=10, anchor="end", cls="f-mu")
    s.text(hx + hw / 2 - 4, hy + hh + 22, "(세 지도 공통)", size=11, cls="f-mu")

    # 범례
    lx = 200
    for i in range(5):
        s.rect(lx + i * 56, 285, 56, 14, cls=f"s-bg q{i}", width=1)
    labs = ["낮음", "", "", "", "높음"]
    s.text(lx, 316, "낮음", size=11, anchor="start", cls="f-mu")
    s.text(lx + 5 * 56, 316, "높음", size=11, anchor="end", cls="f-mu")
    s.text(lx + 5 * 56 / 2, 316, "5분위", size=11, cls="f-mu")
    del labs
    s.save(os.path.join(OUT, "00-same-values.svg"))

    print("[그림1] 평균 {:.2f}, 표준편차 {:.2f}".format(vals.mean(), vals.std(ddof=1)))
    for (name, _), I in zip(layouts, Is):
        print(f"  {name}: I = {I:.3f}")
    print(f"  기댓값 −1/(n−1) = {expected:.3f}")


# ---------------------------------------------------------------- 2. 관계없는 두 변수의 거짓 유의
def smooth_field(rng, size, sigma, pad=24):
    z = rng.standard_normal((size + 2 * pad, size + 2 * pad))
    if sigma > 0:
        z = ndimage.gaussian_filter(z, sigma, mode="wrap")
    return z[pad:pad + size, pad:pad + size].ravel()


def fig_false_positive():
    size = 20
    n = size * size
    W = rook(size, size)
    reps = 2000
    sigmas = [0, 0.5, 0.6, 0.8, 1.5, 3]
    rates, Imeans, neffs = [], [], []
    rng = np.random.default_rng(7)
    for sg in sigmas:
        rej = 0
        Is = []
        for _ in range(reps):
            a = smooth_field(rng, size, sg)
            b = smooth_field(rng, size, sg)
            r, p = stats.pearsonr(a, b)
            rej += p < 0.05
            Is.append(moran(a, W))
        rates.append(rej / reps)
        Imeans.append(float(np.mean(Is)))
    # 예시 한 쌍 (sigma = 3)
    ex_rng = np.random.default_rng(11)
    for _ in range(200):
        a = smooth_field(ex_rng, size, 3)
        b = smooth_field(ex_rng, size, 3)
        r, p = stats.pearsonr(a, b)
        if r > 0.35 and p < 0.001:
            break
    ex = (a, b, r, p)

    s = Svg(720, 330, "서로 아무 관계 없이 따로 만든 두 공간 변수라도 공간 자기상관이 강할수록 상관 검정이 '유의'로 나오는 비율이 5%를 크게 넘음")
    # 왼쪽: 예시 한 쌍
    cell = 7.5
    for j, (name, f) in enumerate([("변수 A", ex[0]), ("변수 B", ex[1])]):
        x0 = 30 + j * 165
        edges = np.quantile(f, [0.2, 0.4, 0.6, 0.8])
        s.text(x0 + cell * size / 2, 26, name, size=13, weight="600")
        for k in range(n):
            r_, c_ = divmod(k, size)
            s.rect(x0 + c_ * cell, 40 + r_ * cell, cell + 0.4, cell + 0.4, cls=f"q{qclass(f[k], edges)}", width=0)
    s.text(172, 215, "따로 만든 두 변수인데도", size=12, cls="f-mu")
    s.text(172, 233, f"r = {ex[2]:.2f}, p < 0.001", size=13, weight="600")
    s.text(172, 251, "(칸 400개, 보통의 상관 검정으로 계산한 한 예)", size=11, cls="f-mu")

    # 오른쪽: 막대그래프
    gx, gy, gw, gh = 410, 40, 255, 180
    ymax = 0.8
    for t in [0, 0.2, 0.4, 0.6, 0.8]:
        y = gy + gh - t / ymax * gh
        s.line(gx, y, gx + gw, y, cls="s-mu", width=0.5, dash="2 3" if t else None)
        s.text(gx - 6, y + 4, f"{int(t * 100)}%", size=10, anchor="end", cls="f-mu")
    y5 = gy + gh - 0.05 / ymax * gh
    s.line(gx, y5, gx + gw, y5, cls="s-bd", width=1.2, dash="5 3")
    s.text(gx + gw + 4, y5 + 4, "5%", size=10, anchor="start", cls="f-bd")
    bw = gw / len(sigmas)
    for i, (rt, Im) in enumerate(zip(rates, Imeans)):
        x = gx + i * bw + bw * 0.2
        h = rt / ymax * gh
        s.rect(x, gy + gh - h, bw * 0.6, h, cls="f-ac", width=0)
        s.text(x + bw * 0.3, gy + gh - h - 5, f"{rt * 100:.0f}%", size=11, weight="600")
        s.text(x + bw * 0.3, gy + gh + 16, f"{abs(Im) if abs(Im) < 0.005 else Im:.2f}", size=11)
    s.text(gx + gw / 2, gy + gh + 36, "각 변수의 평균 모란 지수 (오른쪽일수록 강한 자기상관)", size=11, cls="f-mu")
    s.text(gx + gw / 2, 26, "p < 0.05로 '유의'가 나온 비율", size=13, weight="600")
    s.text(gx + gw / 2, gy + gh + 56, f"관계없는 두 변수 쌍을 단계마다 {reps:,}개씩 시험 (점선: 기대 5%)", size=11, cls="f-mu")
    s.save(os.path.join(OUT, "00-false-positive.svg"))

    print("[그림2] 격자 20×20, 반복", reps)
    for sg, rt, Im in zip(sigmas, rates, Imeans):
        print(f"  sigma={sg}: 평균 I = {Im:.3f}, 거짓 유의 비율 = {rt:.3f}")
    print(f"  예시 r = {ex[2]:.3f}, p = {ex[3]:.2e}")


# ---------------------------------------------------------------- 3. 공간 이질성
def fig_heterogeneity():
    rng = np.random.default_rng(3)
    nA = nB = 40
    dA = rng.uniform(0.2, 4.0, nA)
    dB = rng.uniform(0.2, 4.0, nB)
    pA = 980 - 70 * dA + rng.normal(0, 45, nA)   # 주거지 권역: 하천에 가까울수록 비쌈
    pB = 640 + 70 * dB + rng.normal(0, 45, nB)   # 공업지 권역: 하천에 가까울수록 쌈
    d = np.r_[dA, dB]
    p = np.r_[pA, pB]
    fa = stats.linregress(dA, pA)
    fb = stats.linregress(dB, pB)
    fall = stats.linregress(d, p)

    s = Svg(720, 320, "하천까지 거리와 ㎡당 주택 가격. 주거지 권역은 가까울수록 비싸고 공업지 권역은 가까울수록 싸서, 두 권역을 합쳐 구한 기울기는 0에 가까움")
    # 왼쪽: 개념 지도
    mx, my, mw, mh = 30, 40, 220, 220
    s.text(mx + mw / 2, 26, "가상 도시", size=13, weight="600")
    s.rect(mx, my, mw, mh, cls="s-mu f-sf", width=1)
    s.rect(mx + 1, my + 1, mw / 2 - 1, mh - 2, cls="f-acs", width=0)
    s.rect(mx + mw / 2, my + 1, mw / 2 - 1, mh - 2, cls="f-bds", width=0)
    s.path(f"M{mx},{my + 120} C{mx + 60},{my + 90} {mx + 110},{my + 150} {mx + 160},{my + 115} S{mx + 200},{my + 95} {mx + mw},{my + 110}",
           cls="s-ac", width=6)
    s.text(mx + mw / 4, my + 40, "주거지 권역", size=12, weight="600", cls="f-ac")
    s.text(mx + mw * 3 / 4, my + 40, "공업지 권역", size=12, weight="600", cls="f-bd")
    s.text(mx + mw / 2, my + mh - 14, "굵은 선: 하천", size=11, cls="f-mu")

    # 오른쪽: 산점도
    gx, gy, gw, gh = 340, 40, 340, 220
    xmin, xmax, ymin, ymax = 0, 4.2, 500, 1100
    X = lambda v: gx + (v - xmin) / (xmax - xmin) * gw  # noqa: E731
    Y = lambda v: gy + gh - (v - ymin) / (ymax - ymin) * gh  # noqa: E731
    s.rect(gx, gy, gw, gh, cls="s-mu", width=1).parts[-1] = s.parts[-1].replace("/>", ' fill="none"/>')
    for t in [600, 800, 1000]:
        s.text(gx - 6, Y(t) + 4, f"{t}", size=10, anchor="end", cls="f-mu")
    for t in [0, 1, 2, 3, 4]:
        s.text(X(t), gy + gh + 16, f"{t}", size=10, cls="f-mu")
    s.text(gx + gw / 2, gy + gh + 34, "하천까지 거리 (km)", size=11, cls="f-mu")
    s.text(gx + gw / 2, 26, "㎡당 가격 (만 원)", size=13, weight="600")
    for x_, y_ in zip(dA, pA):
        s.circle(X(x_), Y(y_), 3, cls="f-ac")
    for x_, y_ in zip(dB, pB):
        s.circle(X(x_), Y(y_), 3, cls="f-bd")
    for f, cls, dash in [(fa, "s-ac", None), (fb, "s-bd", None), (fall, "s-fg", "6 4")]:
        s.line(X(0.2), Y(f.intercept + f.slope * 0.2), X(4.0), Y(f.intercept + f.slope * 4.0), cls=cls, width=2, dash=dash)
    s.text(X(4.05), Y(fall.intercept + fall.slope * 4.0) - 6, "합친 선", size=11, anchor="end")
    s.save(os.path.join(OUT, "00-heterogeneity.svg"))

    print("[그림3] 기울기(만 원/km): 주거지 {:.1f}, 공업지 {:.1f}, 합침 {:.1f} (p = {:.2f}), 합친 r = {:.2f}".format(
        fa.slope, fb.slope, fall.slope, fall.pvalue, fall.rvalue))


# ---------------------------------------------------------------- 4. 세 갈래
def fig_three_branches():
    rng = np.random.default_rng(5)
    s = Svg(720, 300, "공간 자료의 세 유형. 연속 표면에서 뽑은 관측값, 구역마다 집계한 값, 사건이 일어난 위치 그 자체")
    pw = 200
    xs = [20, 260, 500]
    y0 = 40
    titles = ["연속 표면 (지구통계)", "면 자료 (격자·구역 자료)", "점 패턴"]
    subs = [["어디서나 값이 있는 현상을", "몇 곳에서 잰 자료"], ["정해진 구역마다", "하나씩 붙은 값"], ["사건이 일어난 위치", "그 자체가 자료"]]
    for x0, t, sb in zip(xs, titles, subs):
        s.text(x0 + pw / 2, 26, t, size=13, weight="600")
        s.text(x0 + pw / 2, y0 + pw + 22, sb[0], size=11, cls="f-mu")
        s.text(x0 + pw / 2, y0 + pw + 38, sb[1], size=11, cls="f-mu")

    # (1) 연속 표면 + 관측소
    g = 25
    z = ndimage.gaussian_filter(rng.standard_normal((g + 20, g + 20)), 4, mode="wrap")[10:10 + g, 10:10 + g]
    edges = np.quantile(z, [0.2, 0.4, 0.6, 0.8])
    c = pw / g
    for i in range(g):
        for j in range(g):
            cls = f"q{qclass(z[i, j], edges)}"
            s.add(f'<rect x="{xs[0] + j * c:.1f}" y="{y0 + i * c:.1f}" width="{c + 0.3:.1f}" height="{c + 0.3:.1f}" class="{cls}"/>')
    for _ in range(14):
        i, j = rng.integers(1, g - 1, 2)
        s.circle(xs[0] + (j + 0.5) * c, y0 + (i + 0.5) * c, 6.5, cls=f"s-fg q{qclass(z[i, j], edges)}", width=2.2)
    s.rect(xs[0], y0, pw, pw, cls="s-mu", width=1).parts[-1] = s.parts[-1].replace("/>", ' fill="none"/>')

    # (2) 불규칙한 구역: 5×5 격자의 내부 꼭짓점을 흔든 사각형
    k = 5
    P = np.zeros((k + 1, k + 1, 2))
    for i in range(k + 1):
        for j in range(k + 1):
            dx = dy = 0.0
            if 0 < i < k:
                dy = rng.uniform(-0.3, 0.3)
            if 0 < j < k:
                dx = rng.uniform(-0.3, 0.3)
            P[i, j] = (j + dx, i + dy)
    vals = ndimage.gaussian_filter(rng.standard_normal((k, k)), 1)
    edges = np.quantile(vals, [0.2, 0.4, 0.6, 0.8])
    sc = pw / k
    for i in range(k):
        for j in range(k):
            pts = [P[i, j], P[i, j + 1], P[i + 1, j + 1], P[i + 1, j]]
            s.polygon([(xs[1] + x * sc, y0 + y * sc) for x, y in pts], cls=f"s-fg q{qclass(vals[i, j], edges)}", width=1)

    # (3) 군집 점 과정
    cents = rng.uniform(0.15, 0.85, (4, 2))
    pts = []
    for cx, cy in cents:
        for _ in range(rng.poisson(12)):
            pts.append((cx + rng.normal(0, 0.05), cy + rng.normal(0, 0.05)))
    pts += [tuple(rng.uniform(0.03, 0.97, 2)) for _ in range(15)]
    s.rect(xs[2], y0, pw, pw, cls="s-mu f-sf", width=1)
    for x, y in pts:
        if 0.02 < x < 0.98 and 0.02 < y < 0.98:
            s.circle(xs[2] + x * pw, y0 + y * pw, 3, cls="f-fg")
    s.save(os.path.join(OUT, "00-three-branches.svg"))


if __name__ == "__main__":
    fig_same_values()
    fig_false_positive()
    fig_heterogeneity()
    fig_three_branches()
