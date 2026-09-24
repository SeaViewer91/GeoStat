// 화면 문구 번역 (한국어 ↔ 영어)
//
// gettext 방식: 코드에는 한국어 문구를 그대로 쓰고 t()로 감쌈. 영어 사전(en.ts)에 같은 한국어 문구를 키로 한
// 번역이 있으면 영어로, 없으면 한국어 그대로 보여줌. {n} 같은 자리표시자는 vars 값으로 바꿈.
// 엔진이 만드는 오류 메시지·보고서는 번역하지 않음 (한국어).

import { EN } from "./en";

export type Lang = "ko" | "en";

const STORAGE_KEY = "geostat.lang";

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "ko" || saved === "en") return saved;
  } catch {
    // 저장소를 못 쓰면 시스템 언어를 따름
  }
  return navigator.language?.toLowerCase().startsWith("ko") ? "ko" : "en";
}

let current: Lang = initialLang();

export function getLang(): Lang {
  return current;
}

export function setLang(lang: Lang): void {
  current = lang;
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // 무시함
  }
  document.documentElement.lang = lang;
}

type Vars = Record<string, string | number>;

/** 한국어 문구를 현재 언어로 바꿈. vars의 값은 {이름} 자리에 들어감 */
export function t(ko: string, vars?: Vars): string {
  const text = current === "en" ? (EN[ko] ?? ko) : ko;
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, key: string) => {
    const v = vars[key];
    if (v === undefined) return m;
    return typeof v === "number" ? v.toLocaleString(current === "ko" ? "ko-KR" : "en-US") : v;
  });
}

document.documentElement.lang = current;
