// 영어 사전(src/i18n/en.ts)에 빠진 화면 문구가 없는지 확인함 (CI에서 실행)
//
// 확인 대상
//   1. t("…"), tx("…") 호출의 한국어 문구
//   2. 화면에 그릴 때 t()로 번역하는 상수 배열의 label·hint 값 (한글이 든 것만)
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const root = new URL("../src/", import.meta.url).pathname;
const en = readFileSync(join(root, "i18n/en.ts"), "utf8");
const keys = new Set([...en.matchAll(/^\s+("(?:[^"\\]|\\.)*"):/gm)].map((m) => JSON.parse(m[1])));

const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (name !== "i18n") walk(p);
    } else if (/\.(ts|tsx)$/.test(name)) files.push(p);
  }
})(root);

const hangul = /[가-힣]/;
const missing = new Map();
const add = (key, file) => {
  if (!keys.has(key)) missing.set(key, file.replace(root, "src/"));
};
for (const file of files) {
  // "…" + "…"로 이어 쓴 긴 문구는 하나로 합쳐서 봄
  const src = readFileSync(file, "utf8").replace(/"\s*\+\s*"/g, "");
  for (const m of src.matchAll(/\btx?\(\s*("(?:[^"\\]|\\.)*")/g)) {
    const key = JSON.parse(m[1]);
    if (hangul.test(key)) add(key, file);
  }
  for (const m of src.matchAll(/\b(?:label|hint):\s*("(?:[^"\\]|\\.)*")/g)) {
    const key = JSON.parse(m[1]);
    if (hangul.test(key)) add(key, file);
  }
}

if (missing.size) {
  console.error(`영어 사전에 없는 문구 ${missing.size}개:`);
  for (const [k, f] of missing) console.error(`  ${f}: ${JSON.stringify(k)}`);
  process.exit(1);
}
console.log(`번역 확인: 사전 ${keys.size}개, 누락 없음`);
