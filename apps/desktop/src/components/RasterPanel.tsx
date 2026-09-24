// 왼쪽 패널의 래스터 목록과 표시 설정 (밴드, 색상표, 값 범위, 투명도, 오버뷰)

import { useEffect, useState } from "react";

import type { RasterColormap, RasterStyle } from "../lib/engine";
import { useApp, type LoadedRaster } from "../store";

// 엔진 색상표와 같은 대표 색 (범례 미리보기용)
const COLORMAPS: { id: RasterColormap; label: string; stops: string[] }[] = [
  { id: "viridis", label: "Viridis", stops: ["#440154", "#3e4989", "#26828e", "#35b779", "#fde725"] },
  { id: "magma", label: "Magma", stops: ["#000004", "#440f76", "#9e2f7f", "#f1605d", "#fcfdbf"] },
  { id: "terrain", label: "지형 (Terrain)", stops: ["#333399", "#0294fa", "#00c966", "#fffe99", "#805c54", "#ffffff"] },
  { id: "gray", label: "회색조", stops: ["#000000", "#ffffff"] },
  { id: "rdylgn", label: "빨강–노랑–초록", stops: ["#a50026", "#f46d43", "#fee08b", "#a6d96a", "#006837"] },
  { id: "spectral", label: "Spectral", stops: ["#9e0142", "#f46d43", "#fee08b", "#abdda4", "#5e4fa2"] },
  { id: "blues", label: "파랑 (Blues)", stops: ["#f7fbff", "#9ecae1", "#4292c6", "#08306b"] },
  { id: "rdbu_r", label: "파랑–빨강 (발산)", stops: ["#053061", "#4393c3", "#f7f7f7", "#d6604d", "#67001f"] },
];

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  const a = Math.abs(v);
  if (a !== 0 && (a >= 1e6 || a < 1e-3)) return v.toExponential(2);
  return Number(v.toPrecision(5)).toString();
}

export function RasterPanel() {
  const rasterOrder = useApp((s) => s.rasterOrder);
  const rasters = useApp((s) => s.rasters);
  const { toggleRasterVisible, zoomToRaster, closeRaster } = useApp.getState();
  const [selected, setSelected] = useState<string | null>(null);
  const current = selected && rasters[selected] ? selected : (rasterOrder[0] ?? null);
  if (rasterOrder.length === 0) return null;

  return (
    <section className="panel" data-testid="raster-panel">
      <h2>래스터</h2>
      <ul className="layer-list">
        {rasterOrder.map((id) => {
          const r = rasters[id];
          if (!r) return null;
          return (
            <li
              key={id}
              className={id === current ? "active" : ""}
              onClick={() => setSelected(id)}
              data-testid="raster-item"
            >
              <input
                type="checkbox"
                checked={r.visible}
                onChange={() => toggleRasterVisible(id)}
                onClick={(e) => e.stopPropagation()}
                aria-label="래스터 표시"
              />
              <span className="geom">▦</span>
              <span className="name" title={r.info.path}>
                {r.info.name}
              </span>
              <span className="actions">
                <button title="전체 보기" onClick={() => zoomToRaster(id)}>
                  ⤢
                </button>
                <button title="닫기" onClick={() => closeRaster(id)}>
                  ✕
                </button>
              </span>
            </li>
          );
        })}
      </ul>
      {current && rasters[current] && <RasterStyleEditor key={current} raster={rasters[current]} />}
    </section>
  );
}

function RasterStyleEditor({ raster }: { raster: LoadedRaster }) {
  const { info, style } = raster;
  const setRasterStyle = useApp((s) => s.setRasterStyle);
  const buildOverviews = useApp((s) => s.buildOverviews);
  const busy = useApp((s) => s.busy);
  const rgb = style.bands.length === 3;
  // 입력 중인 값 범위 (적용 전)
  const [lo, setLo] = useState(style.vmin.map(fmt));
  const [hi, setHi] = useState(style.vmax.map(fmt));
  useEffect(() => {
    setLo(style.vmin.map(fmt));
    setHi(style.vmax.map(fmt));
  }, [style.vmin, style.vmax]);

  const set = (change: Partial<RasterStyle>) => setRasterStyle(info.id, change);

  const stretch = (bands: number[], kind: "pct" | "minmax") => {
    const vmin = bands.map((b) => {
      const st = info.stats[b - 1];
      return (kind === "pct" ? st?.p2 : st?.min) ?? 0;
    });
    const vmax = bands.map((b) => {
      const st = info.stats[b - 1];
      return (kind === "pct" ? st?.p98 : st?.max) ?? 1;
    });
    return { vmin, vmax };
  };

  const setBands = (bands: number[]) => set({ bands, ...stretch(bands, "pct") });

  const applyRange = () => {
    const vmin = lo.map(Number);
    const vmax = hi.map(Number);
    if (vmin.some((v) => !Number.isFinite(v)) || vmax.some((v) => !Number.isFinite(v))) return;
    set({ vmin, vmax });
  };

  const cmap = COLORMAPS.find((c) => c.id === style.colormap) ?? COLORMAPS[0];

  return (
    <div className="form raster-style">
      <div className="muted small">
        {info.width.toLocaleString()}×{info.height.toLocaleString()} · {info.count}밴드 · {info.dtype} · {info.crs} ·
        해상도 {fmt(info.res[0])}
        {info.nodata !== null ? ` · 값 없음 ${fmt(info.nodata)}` : ""}
      </div>
      {info.needs_overviews && (
        <div className="hint warn-text">
          오버뷰가 없어 축소 표시가 느림.{" "}
          <button className="link" disabled={!!busy} onClick={() => buildOverviews(info.id)}>
            오버뷰 만들기
          </button>{" "}
          (원본 옆에 .ovr 파일을 만듦)
        </div>
      )}
      {info.count >= 3 && (
        <label>
          표시 방식
          <select
            value={rgb ? "rgb" : "single"}
            onChange={(e) => setBands(e.target.value === "rgb" ? [1, 2, 3] : [style.bands[0] ?? 1])}
            aria-label="표시 방식"
          >
            <option value="rgb">RGB 합성</option>
            <option value="single">단일 밴드 + 색상표</option>
          </select>
        </label>
      )}
      <div className={rgb ? "grid3" : "grid2"}>
        {style.bands.map((b, i) => (
          <label key={i}>
            {rgb ? ["R", "G", "B"][i] : "밴드"}
            <select
              value={b}
              onChange={(e) => {
                const next = [...style.bands];
                next[i] = Number(e.target.value);
                setBands(next);
              }}
              aria-label={rgb ? `${["R", "G", "B"][i]} 밴드` : "밴드"}
            >
              {info.band_names.map((name, j) => (
                <option key={j} value={j + 1}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        ))}
        {!rgb && (
          <label>
            색상표
            <select
              value={style.colormap}
              onChange={(e) => set({ colormap: e.target.value as RasterColormap })}
              aria-label="색상표"
            >
              {COLORMAPS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {style.bands.map((b, i) => (
        <div className="row" key={i}>
          <span className="small muted band-tag">{rgb ? ["R", "G", "B"][i] : "범위"}</span>
          <input
            value={lo[i] ?? ""}
            onChange={(e) => setLo(lo.map((v, j) => (j === i ? e.target.value : v)))}
            onKeyDown={(e) => e.key === "Enter" && applyRange()}
            onBlur={applyRange}
            aria-label={`밴드 ${b} 최솟값`}
          />
          <span className="muted">~</span>
          <input
            value={hi[i] ?? ""}
            onChange={(e) => setHi(hi.map((v, j) => (j === i ? e.target.value : v)))}
            onKeyDown={(e) => e.key === "Enter" && applyRange()}
            onBlur={applyRange}
            aria-label={`밴드 ${b} 최댓값`}
          />
        </div>
      ))}
      <div className="row">
        <button onClick={() => set(stretch(style.bands, "pct"))} title="2~98% 백분위로 늘림 (이상값 영향 줄임)">
          2–98%
        </button>
        <button onClick={() => set(stretch(style.bands, "minmax"))}>최소–최대</button>
        <label className="check" title="범주 자료(토지피복 등)는 최근접을 씀">
          <input
            type="checkbox"
            checked={style.resampling === "nearest"}
            onChange={(e) => set({ resampling: e.target.checked ? "nearest" : "bilinear" })}
          />
          최근접 보간
        </label>
      </div>
      {!rgb && (
        <div className="raster-legend" data-testid="raster-legend">
          <div className="ramp" style={{ background: `linear-gradient(to right, ${cmap.stops.join(", ")})` }} />
          <div className="row small muted">
            <span>{fmt(style.vmin[0])}</span>
            <span className="spacer" />
            <span>{fmt(style.vmax[0])}</span>
          </div>
        </div>
      )}
      <label>
        투명도 {Math.round((1 - style.opacity) * 100)}%
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={style.opacity}
          onChange={(e) => set({ opacity: Number(e.target.value) })}
          aria-label="불투명도"
        />
      </label>
    </div>
  );
}
