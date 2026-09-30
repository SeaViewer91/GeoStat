"""2부(통계) 그림에서 함께 쓰는 좌표축·히스토그램 도구. svglib.Svg 위에 그림."""
import numpy as np


def nice_ticks(lo, hi, n=5):
    """보기 좋은 눈금 값"""
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / n
    mag = 10 ** np.floor(np.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=10 * mag)
    start = np.ceil(lo / step) * step
    ticks = np.arange(start, hi + step * 1e-9, step)
    return [float(round(t, 10)) for t in ticks]


def fmt_tick(t):
    if abs(t) >= 1000:
        out = f"{t:,.0f}"
    elif float(t).is_integer():
        out = f"{int(t)}"
    else:
        out = f"{t:g}"
    return out.replace("-", "−")  # 본문과 같은 빼기 기호


class Axes:
    """x0,y0 = 왼쪽 위, w,h = 그림 영역. xlim/ylim = 자료 범위"""

    def __init__(self, s, x0, y0, w, h, xlim, ylim):
        self.s, self.x0, self.y0, self.w, self.h = s, x0, y0, w, h
        self.xlim, self.ylim = xlim, ylim

    def X(self, v):
        return self.x0 + (np.asarray(v, float) - self.xlim[0]) / (self.xlim[1] - self.xlim[0]) * self.w

    def Y(self, v):
        return self.y0 + self.h - (np.asarray(v, float) - self.ylim[0]) / (self.ylim[1] - self.ylim[0]) * self.h

    def xaxis(self, ticks=None, label=None, fmt=fmt_tick, size=10):
        s = self.s
        yb = self.y0 + self.h
        s.line(self.x0, yb, self.x0 + self.w, yb, cls="s-mu", width=1)
        for t in ticks if ticks is not None else nice_ticks(*self.xlim):
            if self.xlim[0] - 1e-9 <= t <= self.xlim[1] + 1e-9:
                x = float(self.X(t))
                s.line(x, yb, x, yb + 4, cls="s-mu", width=1)
                s.text(x, yb + 15, fmt(t).replace("-", "−"), size=size, cls="f-mu")
        if label:
            s.text(self.x0 + self.w / 2, yb + 32, label, size=11, cls="f-mu")

    def yaxis(self, ticks=None, label=None, fmt=fmt_tick, size=10, grid=False):
        s = self.s
        s.line(self.x0, self.y0, self.x0, self.y0 + self.h, cls="s-mu", width=1)
        for t in ticks if ticks is not None else nice_ticks(*self.ylim):
            if self.ylim[0] - 1e-9 <= t <= self.ylim[1] + 1e-9:
                y = float(self.Y(t))
                s.line(self.x0 - 4, y, self.x0, y, cls="s-mu", width=1)
                if grid:
                    s.line(self.x0, y, self.x0 + self.w, y, cls="s-mu", width=0.4, dash="2 3")
                s.text(self.x0 - 7, y + 4, fmt(t).replace("-", "−"), size=size, anchor="end", cls="f-mu")
        if label:
            s.text(self.x0 - 8, self.y0 - 10, label, size=11, anchor="start", cls="f-mu")

    def hist(self, counts, edges, cls="s-bg f-mu", width=0.6):
        for c, a, b in zip(counts, edges[:-1], edges[1:]):
            if c <= 0:
                continue
            x1, x2 = float(self.X(a)), float(self.X(b))
            y = float(self.Y(c))
            self.s.rect(x1, y, x2 - x1, self.y0 + self.h - y, cls=cls, width=width)

    def vline(self, v, cls="s-ac", width=1.5, dash=None, top=None):
        x = float(self.X(v))
        self.s.line(x, self.y0 if top is None else top, x, self.y0 + self.h, cls=cls, width=width, dash=dash)

    def curve(self, xs, ys, cls="s-fg", width=1.5, dash=None):
        pts = [(float(self.X(a)), float(self.Y(b))) for a, b in zip(xs, ys)]
        d = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in pts)
        if dash:
            self.s.add(f'<path d="{d}" class="{cls}" stroke-width="{width}" fill="none" stroke-dasharray="{dash}"/>')
        else:
            self.s.path(d, cls=cls, width=width)
