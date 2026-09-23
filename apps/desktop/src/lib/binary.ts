// 엔진과 주고받는 이진 배열(base64) 변환. JSON 숫자 배열보다 작고 빠름

function toBase64(bytes: Uint8Array): string {
  let s = "";
  const CHUNK = 0x8000; // 인자 개수 제한을 피하려고 나눠서 변환함
  for (let i = 0; i < bytes.length; i += CHUNK) {
    s += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(s);
}

function fromBase64(b64: string): Uint8Array {
  const s = atob(b64);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

/** Uint32 배열 → 리틀엔디언 base64 (행 번호 목록 전송용) */
export function encodeUint32(values: Uint32Array): string {
  const view = new DataView(new ArrayBuffer(values.length * 4));
  for (let i = 0; i < values.length; i++) view.setUint32(i * 4, values[i], true);
  return toBase64(new Uint8Array(view.buffer));
}

/** 리틀엔디언 Int16 base64 → Int16Array (계급 번호 수신용) */
export function decodeInt16(b64: string): Int16Array {
  const bytes = fromBase64(b64);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const out = new Int16Array(bytes.byteLength / 2);
  for (let i = 0; i < out.length; i++) out[i] = view.getInt16(i * 2, true);
  return out;
}

/** 선택 마스크에서 선택된 행 번호만 뽑음 */
export function maskToIds(mask: Uint8Array): Uint32Array {
  let n = 0;
  for (let i = 0; i < mask.length; i++) n += mask[i];
  const ids = new Uint32Array(n);
  let k = 0;
  for (let i = 0; i < mask.length; i++) if (mask[i]) ids[k++] = i;
  return ids;
}
