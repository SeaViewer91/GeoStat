// 지도 뷰: 배경지도(MapLibre) 위에 deck.gl GeoArrow 레이어로 피처를 그리고 선택을 처리함

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DeckGL, { type DeckGLRef } from "@deck.gl/react";
import { WebMercatorViewport, type Layer, type PickingInfo } from "@deck.gl/core";
import { GeoArrowPathLayer, GeoArrowPolygonLayer, GeoArrowScatterplotLayer } from "@geoarrow/deck.gl-geoarrow";
import { TileLayer } from "@deck.gl/geo-layers";
import { BitmapLayer } from "@deck.gl/layers";
import { Map as BaseMap } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
// 삼각분할 워커를 CDN 대신 앱에 포함시킴 (오프라인 동작, CSP 준수)
// 패키지 exports에 없는 파일이라 상대 경로로 가져옴
import earcutWorkerUrl from "../../node_modules/@geoarrow/geoarrow-js/dist/earcut-worker.min.js?url";

import {
  batchOffsets,
  featureColors,
  featuresInBox,
  featuresInPolygon,
  outlineData,
  splitColorData,
  type RGBA,
} from "../lib/geoarrow";
import { engine } from "../lib/engine";
import { DEFAULT_FILL, MISSING_COLOR, SELECTED_FILL, classColors } from "../lib/palette";
import { useApp, type Basemap, type LoadedDataset, type LoadedRaster, type SelectMode } from "../store";

const OUTLINE_COLOR: RGBA = [255, 255, 255, 110];
const OUTLINE_ON_BASEMAP: RGBA = [60, 60, 60, 120];
// 주제도 위 선택 피처의 외곽선 (지도 선택색보다 진하게 해 흐려진 채움색과 구분함)
const OUTLINE_SELECTED: RGBA = [20, 20, 20, 255];

// OpenFreeMap: API 키 없이 쓸 수 있는 OpenStreetMap 벡터 타일
const BASEMAP_STYLE: Record<Exclude<Basemap, "none">, string> = {
  positron: "https://tiles.openfreemap.org/styles/positron",
  liberty: "https://tiles.openfreemap.org/styles/liberty",
};

// 이 픽셀 이하로 끌면 영역 선택이 아니라 클릭으로 간주함
const DRAG_THRESHOLD_PX = 4;

type Gesture =
  { kind: "box"; x0: number; y0: number; x1: number; y1: number } | { kind: "lasso"; points: [number, number][] };

export function MapCanvas() {
  const deckRef = useRef<DeckGLRef>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const datasets = useApp((s) => s.datasets);
  const order = useApp((s) => s.order);
  const rasters = useApp((s) => s.rasters);
  const rasterOrder = useApp((s) => s.rasterOrder);
  const activeId = useApp((s) => s.activeId);
  const tool = useApp((s) => s.tool);
  const basemap = useApp((s) => s.basemap);
  const view = useApp((s) => s.view);
  const setView = useApp((s) => s.setView);
  const fitRequest = useApp((s) => s.fitRequest);
  const select = useApp((s) => s.select);
  const setActive = useApp((s) => s.setActive);

  const [gesture, setGesture] = useState<Gesture | null>(null);
  const shiftDown = useShiftKey();
  // Shift를 누르는 동안은 임시로 사각형 선택이 됨
  const areaTool = tool === "lasso" ? "lasso" : tool === "box" || shiftDown ? "box" : null;

  // 범위 이동 요청 처리
  useEffect(() => {
    const el = containerRef.current;
    if (!fitRequest || !el) return;
    const [minx, miny, maxx, maxy] = fitRequest.bounds;
    const vp = new WebMercatorViewport({ width: el.clientWidth, height: el.clientHeight });
    const { longitude, latitude, zoom } = vp.fitBounds(
      [
        [minx, miny],
        [maxx, maxy],
      ],
      { padding: 40 },
    );
    setView({ longitude, latitude, zoom: Math.min(zoom, 18) });
  }, [fitRequest, setView]);

  // 레이어 목록 앞쪽이 위에 그려지도록 역순으로 쌓음. 래스터는 항상 벡터 아래에 둠
  const layers = useMemo(() => {
    const out: Layer[] = [];
    for (const id of [...rasterOrder].reverse()) {
      const r = rasters[id];
      if (r?.visible) out.push(makeRasterLayer(r));
    }
    for (const id of [...order].reverse()) {
      const ds = datasets[id];
      if (ds?.table && ds.visible) out.push(...makeLayers(ds, basemap !== "none"));
    }
    return out;
  }, [datasets, order, basemap, rasters, rasterOrder]);

  const active = activeId ? datasets[activeId] : undefined;

  // ---- 클릭 선택 ------------------------------------------------------------

  const onClick = useCallback(
    (info: PickingInfo, event: { srcEvent: MouseEvent }) => {
      if (areaTool) return;
      const additive = event.srcEvent.metaKey || event.srcEvent.ctrlKey;
      const parsed = info.layer ? parseLayerId(info.layer.id) : null;
      if (parsed && info.index >= 0) {
        const ds = useApp.getState().datasets[parsed.datasetId];
        if (!ds?.table) return;
        // 레이어는 레코드 배치 단위이므로 배치 시작 행 번호를 더해 전체 행 번호로 바꿈
        const row = batchOffsets(ds.table)[parsed.batch] + info.index;
        if (parsed.datasetId !== activeId) setActive(parsed.datasetId);
        select(parsed.datasetId, [row], additive ? "toggle" : "replace");
      } else if (!additive && activeId) {
        select(activeId, [], "replace"); // 빈 곳 클릭 → 선택 해제
      }
    },
    [areaTool, activeId, select, setActive],
  );

  // ---- 사각형·올가미 선택 ------------------------------------------------------

  const localPoint = (e: React.PointerEvent): [number, number] => {
    const rect = containerRef.current!.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (!areaTool || e.button !== 0) return;
    const [x, y] = localPoint(e);
    (e.target as Element).setPointerCapture(e.pointerId);
    setGesture(areaTool === "box" ? { kind: "box", x0: x, y0: y, x1: x, y1: y } : { kind: "lasso", points: [[x, y]] });
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!gesture) return;
    const [x, y] = localPoint(e);
    if (gesture.kind === "box") {
      setGesture({ ...gesture, x1: x, y1: y });
    } else {
      const [lx, ly] = gesture.points[gesture.points.length - 1];
      if (Math.hypot(x - lx, y - ly) >= 3) setGesture({ kind: "lasso", points: [...gesture.points, [x, y]] });
    }
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (!gesture) return;
    setGesture(null);
    const deck = deckRef.current?.deck;
    if (!active?.bounds || !active.centroids || !deck) return;
    const viewport = deck.getViewports()[0];
    const mode: SelectMode = e.metaKey || e.ctrlKey ? "add" : "replace";
    const t0 = performance.now();
    let hits: Uint32Array;

    if (gesture.kind === "box") {
      const { x0, y0, x1, y1 } = gesture;
      if (Math.abs(x1 - x0) < DRAG_THRESHOLD_PX && Math.abs(y1 - y0) < DRAG_THRESHOLD_PX) return;
      // 화면 사각형의 두 모서리를 경위도로 역투영해 범위 검색함
      const [lon0, lat0] = viewport.unproject([Math.min(x0, x1), Math.max(y0, y1)]);
      const [lon1, lat1] = viewport.unproject([Math.max(x0, x1), Math.min(y0, y1)]);
      hits = featuresInBox(active.bounds, [lon0, lat0, lon1, lat1]);
    } else {
      if (gesture.points.length < 3) return;
      const polygon = gesture.points.map((p) => viewport.unproject(p).slice(0, 2) as [number, number]);
      hits = featuresInPolygon(active.centroids, polygon);
    }
    select(active.info.id, hits, mode);
    console.info(
      `[geostat] ${gesture.kind === "box" ? "사각형" : "올가미"} 선택 ${hits.length}개, ${(performance.now() - t0).toFixed(1)}ms`,
    );
  };

  return (
    <div ref={containerRef} className="map-canvas" data-testid="map-canvas">
      <DeckGL
        ref={deckRef}
        viewState={view}
        onViewStateChange={({ viewState: vs }) => {
          const { longitude, latitude, zoom } = vs as typeof view;
          setView({ longitude, latitude, zoom });
        }}
        controller={{ dragPan: !areaTool, doubleClickZoom: !areaTool }}
        layers={layers}
        onClick={onClick}
        getCursor={({ isDragging, isHovering }) =>
          areaTool ? "crosshair" : isDragging ? "grabbing" : isHovering ? "pointer" : "grab"
        }
      >
        {basemap !== "none" && (
          <BaseMap mapStyle={BASEMAP_STYLE[basemap]} reuseMaps attributionControl={{ compact: true }} />
        )}
      </DeckGL>
      <div
        className="map-overlay"
        style={{ pointerEvents: areaTool ? "auto" : "none" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        {gesture?.kind === "box" && (
          <div
            className="drag-box"
            style={{
              left: Math.min(gesture.x0, gesture.x1),
              top: Math.min(gesture.y0, gesture.y1),
              width: Math.abs(gesture.x1 - gesture.x0),
              height: Math.abs(gesture.y1 - gesture.y0),
            }}
          />
        )}
        {gesture?.kind === "lasso" && (
          <svg className="lasso">
            <polygon points={gesture.points.map((p) => p.join(",")).join(" ")} />
          </svg>
        )}
      </div>
    </div>
  );
}

// 레이어 id 형식: ds-<데이터셋 id>-b<배치 번호>
function parseLayerId(layerId: string): { datasetId: string; batch: number } | null {
  const m = /^ds-([^-]+)-b(\d+)/.exec(layerId);
  return m ? { datasetId: m[1], batch: Number(m[2]) } : null;
}

/** 레코드 배치마다 레이어 하나를 만듦 (@geoarrow/deck.gl-geoarrow 0.4는 배치 단위 레이어임) */
function makeLayers(ds: LoadedDataset, onBasemap: boolean): Layer[] {
  const { info, table, selection, selectedCount, theme } = ds;
  if (!table) return [];
  const themeColors = theme
    ? {
        classes: theme.classes,
        colors: classColors(theme.scheme, theme.labels, 225, theme.colors),
        missing: MISSING_COLOR,
      }
    : null;
  const rgba = featureColors(info.n_rows, selection, selectedCount, themeColors, DEFAULT_FILL, SELECTED_FILL);
  const colors = splitColorData(table, rgba);
  // 주제도가 있을 때만 선택 외곽선을 따로 줌 (단일 색 지도는 채움색으로 선택을 표시함)
  const outline = theme
    ? outlineData(table, selection, selectedCount, onBasemap ? OUTLINE_ON_BASEMAP : OUTLINE_COLOR, OUTLINE_SELECTED)
    : null;
  // 색이 바뀌면 GPU 버퍼만 다시 만들도록 트리거를 줌
  const trigger = [selection, theme];

  return table.batches.map((batch, b) => {
    const common = {
      id: `ds-${info.id}-b${b}`,
      data: batch,
      pickable: true,
      updateTriggers: { getFillColor: trigger, getColor: trigger, getLineColor: trigger, getLineWidth: trigger },
    };
    switch (info.geometry_type) {
      case "polygon":
        return new GeoArrowPolygonLayer({
          ...common,
          filled: true,
          stroked: true,
          getFillColor: colors[b],
          getLineColor: outline ? outline.colors[b] : onBasemap ? OUTLINE_ON_BASEMAP : OUTLINE_COLOR,
          ...(outline ? { getLineWidth: outline.widths[b] } : {}),
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 0.5,
          _subLayerProps: { fill: { earcutWorkerUrl, earcutWorkerPoolSize: 4 } },
        });
      case "line":
        return new GeoArrowPathLayer({
          ...common,
          getColor: colors[b],
          widthUnits: "pixels",
          widthMinPixels: 1.5,
        });
      case "point":
        return new GeoArrowScatterplotLayer({
          ...common,
          getFillColor: colors[b],
          stroked: true,
          getLineColor: outline ? outline.colors[b] : [255, 255, 255, 180],
          ...(outline ? { getLineWidth: outline.widths[b] } : {}),
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 0.5,
          radiusUnits: "pixels",
          getRadius: 4,
          radiusMinPixels: 2,
        });
    }
  });
}

/** 래스터: 엔진이 만든 256px 타일을 받아 그림. 표시 설정이 바뀌면 레이어 id가 바뀌어 타일을 새로 받음 */
function makeRasterLayer(r: LoadedRaster): Layer {
  const { info, style } = r;
  const key = [
    style.bands.join("."),
    style.vmin.join("."),
    style.vmax.join("."),
    style.colormap,
    style.resampling,
  ].join("|");
  return new TileLayer<ImageBitmap | null>({
    id: `raster-${info.id}-${key}`,
    extent: info.bounds_wgs84,
    tileSize: 256,
    minZoom: 0,
    maxZoom: 22,
    maxRequests: 8,
    opacity: style.opacity,
    getTileData: ({ index, signal }) => engine.rasterTile(info.id, index, style, signal),
    renderSubLayers: (props) => {
      const { boundingBox } = props.tile;
      if (!props.data) return null;
      return new BitmapLayer({
        id: `${props.id}-bitmap`,
        image: props.data,
        bounds: [boundingBox[0][0], boundingBox[0][1], boundingBox[1][0], boundingBox[1][1]],
        opacity: style.opacity,
      });
    },
  });
}

/** Shift 키를 누르고 있는 동안 true */
function useShiftKey(): boolean {
  const [down, setDown] = useState(false);
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === "Shift" && setDown(true);
    const off = (e: KeyboardEvent) => e.key === "Shift" && setDown(false);
    const reset = () => setDown(false);
    window.addEventListener("keydown", on);
    window.addEventListener("keyup", off);
    window.addEventListener("blur", reset);
    return () => {
      window.removeEventListener("keydown", on);
      window.removeEventListener("keyup", off);
      window.removeEventListener("blur", reset);
    };
  }, []);
  return down;
}
