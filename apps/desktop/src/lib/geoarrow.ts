// GeoArrow 테이블 보조 함수 (피처 범위 계산, 사각형 선택, 색상 버퍼 생성)

import * as arrow from "apache-arrow";

export type RGBA = [number, number, number, number];

/** 지오메트리 열 이름. 엔진은 항상 "geometry"로 보냄 */
export const GEOMETRY_COLUMN = "geometry";

/**
 * 피처별 경위도 범위(minx, miny, maxx, maxy)를 계산함. 결과 길이 = 행 수 × 4.
 *
 * GeoArrow의 점·선·면은 모두 "List 중첩 + 마지막 FixedSizeList[2] 좌표" 구조임.
 * 각 행의 좌표는 중첩 오프셋을 끝까지 따라가면 하나의 연속 구간이 되므로,
 * 행마다 [시작, 끝) 좌표 구간만 구해 최솟값·최댓값을 훑음.
 */
export function computeFeatureBounds(table: arrow.Table): Float64Array {
  const column = table.getChild(GEOMETRY_COLUMN);
  if (!column) throw new Error("geometry 열이 없음");

  const out = new Float64Array(table.numRows * 4);
  let row = 0;
  for (const chunk of column.data) {
    // 리스트 단계별 오프셋을 모으고 좌표 버퍼까지 내려감
    const offsetLevels: Int32Array[] = [];
    const levelOffsets: number[] = [];
    let data: arrow.Data = chunk;
    while (data.type.typeId === arrow.Type.List) {
      offsetLevels.push(data.valueOffsets as Int32Array);
      levelOffsets.push(data.offset);
      data = data.children[0];
    }
    if (data.type.typeId !== arrow.Type.FixedSizeList) {
      throw new Error(`지원하지 않는 GeoArrow 구조: ${String(data.type)}`);
    }
    const dim = (data.type as arrow.FixedSizeList).listSize;
    const coordsData = data.children[0];
    const coords = coordsData.values as Float64Array;
    const coordBase = (data.offset + coordsData.offset / dim) | 0;

    for (let i = 0; i < chunk.length; i++, row++) {
      let start = i;
      let end = i + 1;
      for (let lv = 0; lv < offsetLevels.length; lv++) {
        const offs = offsetLevels[lv];
        const base = levelOffsets[lv];
        start = offs[base + start];
        end = offs[base + end];
      }
      let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
      for (let c = start; c < end; c++) {
        const k = (coordBase + c) * dim;
        const x = coords[k];
        const y = coords[k + 1];
        if (x < minx) minx = x;
        if (x > maxx) maxx = x;
        if (y < miny) miny = y;
        if (y > maxy) maxy = y;
      }
      const o = row * 4;
      out[o] = minx;
      out[o + 1] = miny;
      out[o + 2] = maxx;
      out[o + 3] = maxy;
    }
  }
  return out;
}

/**
 * 사각형과 범위가 겹치는 피처 번호를 반환함.
 * 화면 픽셀 기반(GPU picking)과 달리 아주 작은 피처도 빠짐없이 잡힘.
 */
export function featuresInBox(
  bounds: Float64Array,
  box: [number, number, number, number],
): Uint32Array {
  const [bx0, by0, bx1, by1] = box;
  const n = bounds.length / 4;
  const hits = new Uint32Array(n);
  let count = 0;
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    // 빈 지오메트리(Infinity 범위)는 비교에서 자연히 제외됨
    if (bounds[o] <= bx1 && bounds[o + 2] >= bx0 && bounds[o + 1] <= by1 && bounds[o + 3] >= by0) {
      hits[count++] = i;
    }
  }
  return hits.slice(0, count);
}

/**
 * 선택 상태에 따른 RGBA 색상 데이터를 레코드 배치별로 만듦.
 * GeoArrow 레이어는 배치 하나당 레이어 하나로 그리므로 배치 길이에 맞춰 조각을 나눔.
 */
export function buildColorData(
  table: arrow.Table,
  selection: Uint8Array,
  base: RGBA,
  selected: RGBA,
): arrow.Data<arrow.FixedSizeList<arrow.Uint8>>[] {
  const n = table.numRows;
  const rgba = new Uint8Array(n * 4);
  for (let i = 0; i < n; i++) {
    const c = selection[i] ? selected : base;
    const o = i * 4;
    rgba[o] = c[0];
    rgba[o + 1] = c[1];
    rgba[o + 2] = c[2];
    rgba[o + 3] = c[3];
  }

  const type = new arrow.FixedSizeList(4, new arrow.Field("rgba", new arrow.Uint8(), false));
  const chunks: arrow.Data<arrow.FixedSizeList<arrow.Uint8>>[] = [];
  let offset = 0;
  for (const batch of table.batches) {
    const len = batch.numRows;
    const child = arrow.makeData({
      type: new arrow.Uint8(),
      data: rgba.subarray(offset * 4, (offset + len) * 4),
    });
    chunks.push(arrow.makeData({ type, length: len, nullCount: 0, child }));
    offset += len;
  }
  return chunks;
}

/** 레코드 배치별 시작 행 번호. 레이어별 picking index를 전체 행 번호로 바꿀 때 씀 */
export function batchOffsets(table: arrow.Table): number[] {
  const offsets: number[] = [];
  let acc = 0;
  for (const batch of table.batches) {
    offsets.push(acc);
    acc += batch.numRows;
  }
  return offsets;
}
