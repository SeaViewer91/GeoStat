"""책 그림(SVG) 공통 도구. VisionDrill 자습서 그림 도구를 바탕으로 함.

규칙
- 색은 클래스로만 지정 (s-* = 선, f-* = 채움, q0~q4 = 순차 색 단계, d0~d5 = 발산 색 단계)
- 색 체계 자체를 보여 주는 견본처럼 자료 색을 직접 지정해야 할 때만 fill 인자를 씀 (모드와 관계없이 같은 색)
- 라이트·다크 모드는 SVG 안의 prefers-color-scheme으로 바꿈. GitHub에서 이미지로 볼 때와
  HTML 판에 직접 넣었을 때 모두 같은 규칙으로 동작함
- 배경은 투명하게 두지 않고 f-bg 사각형으로 명시함 (GitHub 테마와 OS 설정이 다를 때도 읽히게)
- 자료 값을 나타내는 순차 색(q0~q4)은 모드와 관계없이 같은 색을 씀 (값의 뜻이 바뀌지 않게)
- id 속성은 쓰지 않음 (HTML 판에서 한 페이지에 그림 여러 개가 들어갈 때 충돌)
- 크기는 viewBox로만 정함
"""
from html import escape

STYLE = """<style>
.gsfig{font-family:system-ui,-apple-system,'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif}
.gsfig .s-fg{stroke:#1c2330}.gsfig .s-mu{stroke:#8a93a3}.gsfig .s-ac{stroke:#2563eb}.gsfig .s-bd{stroke:#c2410c}.gsfig .s-ok{stroke:#15803d}.gsfig .s-bg{stroke:#ffffff}
.gsfig .f-fg{fill:#1c2330}.gsfig .f-mu{fill:#5a6475}.gsfig .f-ac{fill:#2563eb}.gsfig .f-acs{fill:#e6eefe}.gsfig .f-bd{fill:#c2410c}
.gsfig .f-bds{fill:#fdeee6}.gsfig .f-ok{fill:#15803d}.gsfig .f-sf{fill:#f0f2f5}.gsfig .f-bg{fill:#ffffff}
.gsfig .d0{fill:#2166ac}.gsfig .d1{fill:#67a9cf}.gsfig .d2{fill:#d1e5f0}.gsfig .d3{fill:#fddbc7}.gsfig .d4{fill:#ef8a62}.gsfig .d5{fill:#b2182b}
.gsfig .q0{fill:#fff1e0}.gsfig .q1{fill:#fdc98f}.gsfig .q2{fill:#f98f45}.gsfig .q3{fill:#d9530f}.gsfig .q4{fill:#8c2d04}
@media (prefers-color-scheme:dark){
.gsfig .s-fg{stroke:#e6e9ef}.gsfig .s-mu{stroke:#737c8c}.gsfig .s-ac{stroke:#6d9bff}.gsfig .s-bd{stroke:#fb8b5b}.gsfig .s-ok{stroke:#4ade80}.gsfig .s-bg{stroke:#1a1e26}
.gsfig .f-fg{fill:#e6e9ef}.gsfig .f-mu{fill:#a7afbd}.gsfig .f-ac{fill:#6d9bff}.gsfig .f-acs{fill:#1f2b45}.gsfig .f-bd{fill:#fb8b5b}
.gsfig .f-bds{fill:#3a2218}.gsfig .f-ok{fill:#4ade80}.gsfig .f-sf{fill:#222733}.gsfig .f-bg{fill:#1a1e26}}
</style>"""


class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label, self.parts = w, h, label, []

    def add(self, s):
        self.parts.append(s)
        return self

    def line(self, x1, y1, x2, y2, cls="s-fg", width=1.5, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="{cls}" stroke-width="{width}"{d}/>')

    def rect(self, x, y, w, h, cls="s-fg f-acs", width=1.5, rx=0, fill=None):
        f = f' fill="{fill}"' if fill else ""
        return self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" class="{cls}" stroke-width="{width}"{f}/>')

    def circle(self, cx, cy, r, cls="f-bd", width=1, fill=None):
        f = f' fill="{fill}"' if fill else ""
        return self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.2f}" class="{cls}" stroke-width="{width}"{f}/>')

    def polygon(self, pts, cls="s-fg f-acs", width=1, fill=None):
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        f = f' fill="{fill}"' if fill else ""
        return self.add(f'<polygon points="{p}" class="{cls}" stroke-width="{width}"{f}/>')

    def path(self, d, cls="s-fg", width=1.5, fill="none"):
        f = "" if "f-" in cls else f' fill="{fill}"'
        return self.add(f'<path d="{d}" class="{cls}" stroke-width="{width}"{f}/>')

    def image_png(self, x, y, w, h, png_bytes):
        """래스터 그림을 PNG로 넣음 (data URI). 셀 수가 많은 래스터를 사각형 수천 개 대신 그림 하나로 넣기 위함"""
        import base64
        b64 = base64.b64encode(png_bytes).decode("ascii")
        return self.add(f'<image x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                        f'preserveAspectRatio="none" style="image-rendering:pixelated" href="data:image/png;base64,{b64}"/>')

    def text(self, x, y, s, cls="f-fg", size=13, anchor="middle", weight=None):
        w = f' font-weight="{weight}"' if weight else ""
        return self.add(f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}" text-anchor="{anchor}"{w}>{escape(s)}</text>')

    def save(self, path):
        body = "\n".join(self.parts)
        bg = f'<rect x="0" y="0" width="{self.w}" height="{self.h}" class="f-bg"/>'
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" class="gsfig" viewBox="0 0 {self.w} {self.h}" '
               f'role="img" aria-label="{escape(self.label)}">\n{STYLE}\n{bg}\n{body}\n</svg>\n')
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
