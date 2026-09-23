// 지도 뷰: deck.gl GeoArrow 레이어로 피처를 그리고 클릭·사각형 선택을 처리함

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DeckGL, { type DeckGLRef } from "@deck.gl/react";
import { WebMercatorViewport, type Layer, type MapViewState, type PickingInfo } from "@deck.gl/core";
import {
  GeoArrowPathLayer,
  GeoArrowPolygonLayer,
  GeoArrowScatterplotLayer,
} from "@geoarrow/deck.gl-geoarrow";
// 삼각분할 워커를 CDN 대신 앱에 포함시킴 (오프라인 동작, CSP 준수)
// 패키지 exports에 없는 파일이라 상대 경로로 가져옴
import earcutWorkerUrl from "../../node_modules/@geoarrow/geoarrow-js/dist/earcut-worker.min.js?url";

import { batchOffsets, buildColorData, featuresInBox, type RGBA } from "../lib/geoarrow";
import { useApp, type LoadedDataset, type SelectMode } from "../store";

const BASE_COLOR: RGBA = [70, 130, 180, 210];
const SELECTED_COLOR: RGBA = [255, 196, 0, 235];
const OUTLINE_COLOR: RGBA = [255, 255, 255, 90];

// 이 픽셀 이하로 끌면 사각형 선택이 아니라 클릭으로 간주함
const DRAG_THRESHOLD_PX = 4;

const INITIAL_VIEW: MapViewState = { longitude: 127.8, latitude: 36.3, zoom: 6 };

interface DragBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export function MapCanvas({ boxMode }: { boxMode: boolean }) {
  const deckRef = useRef<DeckGLRef>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const activeId = useApp((s) => s.activeId);
  const ds = useApp((s) => (s.activeId ? s.datasets[s.activeId] : undefined));
  const select = useApp((s) => s.select);

  const [viewState, setViewState] = useState<MapViewState>(INITIAL_VIEW);
  const [drag, setDrag] = useState<DragBox | null>(null);
  const shiftDown = useShiftKey();
  const boxActive = boxMode || shiftDown;

  // 데이터셋이 바뀌면 전체 범위로 이동함
  useEffect(() => {
    const bounds = ds?.info.bounds_wgs84;
    const el = containerRef.current;
    if (!bounds || !el) return;
    const [minx, miny, maxx, maxy] = bounds;
    const vp = new WebMercatorViewport({ width: el.clientWidth, height: el.clientHeight });
    const { longitude, latitude, zoom } = vp.fitBounds(
      [
        [minx, miny],
        [maxx, maxy],
      ],
      { padding: 40 },
    );
    setViewState({ longitude, latitude, zoom: Math.min(zoom, 18) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  const layers = useMemo(() => (ds ? makeLayers(ds) : []), [ds]);
  const offsets = useMemo(() => (ds ? batchOffsets(ds.table) : []), [ds?.table]);

  // ---- 선택 처리 ------------------------------------------------------------

  const modeFor = (e: { metaKey: boolean; ctrlKey: boolean }): SelectMode =>
    e.metaKey || e.ctrlKey ? "add" : "replace";

  const onClick = useCallback(
    (info: PickingInfo, event: { srcEvent: MouseEvent }) => {
      if (!ds || boxActive) return;
      const additive = event.srcEvent.metaKey || event.srcEvent.ctrlKey;
      if (info.index >= 0 && info.layer) {
        // 레이어는 레코드 배치 단위이므로 배치 시작 행 번호를 더해 전체 행 번호로 바꿈
        const row = offsets[batchIndexOf(info.layer.id)] + info.index;
        select(ds.info.id, [row], additive ? "toggle" : "replace");
      } else if (!additive) {
        select(ds.info.id, [], "replace"); // 빈 곳 클릭 → 선택 해제
      }
    },
    [ds, boxActive, select, offsets],
  );

  const localPoint = (e: React.PointerEvent) => {
    const rect = containerRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (!boxActive || e.button !== 0) return;
    const { x, y } = localPoint(e);
    (e.target as Element).setPointerCapture(e.pointerId);
    setDrag({ x0: x, y0: y, x1: x, y1: y });
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag) return;
    const { x, y } = localPoint(e);
    setDrag({ ...drag, x1: x, y1: y });
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (!drag) return;
    setDrag(null);
    const deck = deckRef.current?.deck;
    if (!ds || !deck) return;
    const w = Math.abs(drag.x1 - drag.x0);
    const h = Math.abs(drag.y1 - drag.y0);
    if (w < DRAG_THRESHOLD_PX && h < DRAG_THRESHOLD_PX) return;

    // 화면 사각형의 두 모서리를 경위도로 역투영해 범위 검색함
    const viewport = deck.getViewports()[0];
    const [lon0, lat0] = viewport.unproject([Math.min(drag.x0, drag.x1), Math.max(drag.y0, drag.y1)]);
    const [lon1, lat1] = viewport.unproject([Math.max(drag.x0, drag.x1), Math.min(drag.y0, drag.y1)]);
    const t0 = performance.now();
    const hits = featuresInBox(ds.bounds, [lon0, lat0, lon1, lat1]);
    select(ds.info.id, hits, modeFor(e));
    console.info(`[geostat] 사각형 선택 ${hits.length}개, ${(performance.now() - t0).toFixed(1)}ms`);
  };

  return (
    <div ref={containerRef} className="map-canvas" data-testid="map-canvas">
      <DeckGL
        ref={deckRef}
        viewState={viewState}
        onViewStateChange={({ viewState: vs }) => setViewState(vs as MapViewState)}
        controller={{ dragPan: !boxActive, doubleClickZoom: !boxActive }}
        layers={layers}
        onClick={onClick}
        getCursor={({ isDragging, isHovering }) =>
          boxActive ? "crosshair" : isDragging ? "grabbing" : isHovering ? "pointer" : "grab"
        }
      />
      <div
        className="map-overlay"
        style={{ pointerEvents: boxActive ? "auto" : "none", cursor: "crosshair" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        {drag && (
          <div
            className="drag-box"
            style={{
              left: Math.min(drag.x0, drag.x1),
              top: Math.min(drag.y0, drag.y1),
              width: Math.abs(drag.x1 - drag.x0),
              height: Math.abs(drag.y1 - drag.y0),
            }}
          />
        )}
      </div>
    </div>
  );
}

// 레이어 id 형식: ds-<데이터셋 id>-b<배치 번호>
function batchIndexOf(layerId: string): number {
  const m = /-b(\d+)(?:-|$)/.exec(layerId);
  return m ? Number(m[1]) : 0;
}

/** 레코드 배치마다 레이어 하나를 만듦 (@geoarrow/deck.gl-geoarrow 0.4는 배치 단위 레이어임) */
function makeLayers(ds: LoadedDataset): Layer[] {
  const { info, table, selection } = ds;
  const colors = buildColorData(table, selection, BASE_COLOR, SELECTED_COLOR);
  return table.batches.map((batch, b) => {
    const common = {
      id: `ds-${info.id}-b${b}`,
      data: batch,
      pickable: true,
      updateTriggers: { getFillColor: selection, getColor: selection },
    };
    switch (info.geometry_type) {
      case "polygon":
        return new GeoArrowPolygonLayer({
          ...common,
          filled: true,
          stroked: true,
          getFillColor: colors[b],
          getLineColor: OUTLINE_COLOR,
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
          radiusUnits: "pixels",
          getRadius: 3,
          radiusMinPixels: 2,
        });
    }
  });
}

/** Shift 키를 누르고 있는 동안 true. 누르는 동안 임시로 사각형 선택 모드가 됨 */
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
