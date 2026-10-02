"""부록 D 용어 대역표와 book/glossary.json 만들기.

- 강마다 있는 '핵심 용어' 표(한글 | 영문 | 비고)를 모두 모아, 한글 용어별로 합치고 처음 나온 강을 붙임
- 권장어와 이형(VARIANTS)은 이 파일에 직접 적어 둠. tools/check_terms.py가 본문에서 이형을 찾아 경고함
- 결과
    book/glossary.json                       용어 전체 (기계용)
    book/lessons/D-glossary.md 의 자동 생성 구역  가나다순 대역표

실행 (아무 Python 3):
    python3 book/fig-src/D.py
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BOOK = os.path.join(HERE, "..")
LESSONS = os.path.join(BOOK, "lessons")
START, END = "<!-- 용어표 자동 생성 시작 (fig-src/D.py) -->", "<!-- 용어표 자동 생성 끝 -->"

# 권장어 → 본문에서 피할 이형. 앱 UI 표기와 같게 고름 (구성안 8절)
VARIANTS = {
    "공간시차": ["공간지연", "공간래그"],
    "공간가중치": ["공간가중행렬", "공간 가중행렬"],
    "지리가중회귀": ["지리적 가중 회귀", "지리가중 회귀", "지리적 가중회귀"],
    "가변적 공간 단위 문제": ["가변 면적 단위 문제", "임의적 공간 단위 문제"],
    "베리오그램": ["배리오그램", "반변동도", "변동도"],
    "크리깅": ["크리징"],
    "핫스팟": ["핫스폿", "열점"],
    "콜드스팟": ["콜드스폿", "냉점"],
    "유효 표본 크기": ["실효 표본 수", "유효 표본 수", "유효표본크기"],
    "누락 변수 편향": ["빠진 변수 치우침", "누락변수 편의", "누락 변수 편의"],
    "다중검정": ["다중 검정"],
    "룩 인접": ["루크 인접", "룩 인접성"],
    "공간 자기상관": ["공간자기상관", "공간 자기 상관"],
    "경계 효과": ["가장자리 효과"],
    "단계구분도": ["코로플레스 지도", "코로플레스맵"],
    "최대우도": ["최우추정", "최대 우도"],
    "가중 최소제곱": ["가중최소제곱"],
    "모의 실험": ["모의실험"],
    "신용구간": ["신뢰 구간(베이즈)"],
}


def read_terms():
    rows = []
    for f in sorted(glob.glob(os.path.join(LESSONS, "[0-9][0-9]-*.md"))):
        lid = os.path.basename(f)[:2]
        s = open(f, encoding="utf-8").read()
        m = re.search(r"## 핵심 용어\n\n(.*?)\n\n", s, re.S)
        if not m:
            continue
        for line in m.group(1).splitlines()[2:]:
            c = [x.strip() for x in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
            if len(c) >= 2 and c[0]:
                rows.append((lid, c[0], c[1], c[2] if len(c) > 2 else ""))
    return rows


def merge(rows):
    out = {}
    for lid, ko, en, note in rows:
        note = re.sub(r"\s*<!--.*?-->", "", note).strip()
        e = out.setdefault(ko, {"ko": ko, "en": en, "notes": [], "lessons": []})
        if lid not in e["lessons"]:
            e["lessons"].append(lid)
        if note and note not in e["notes"] and not re.fullmatch(r"\d+(·\d+)*강", note):
            e["notes"].append(note)
        if len(en) > len(e["en"]) and en.lower().startswith(e["en"].lower()):  # 약어를 더한 쪽을 씀
            e["en"] = en
    for e in out.values():
        e["first"] = min(e["lessons"])
        e["variants"] = [v for k in variant_keys(e["ko"]) for v in VARIANTS[k]]
    return out


def bare(ko):
    """앞의 (…)를 뗀 표제어. (반)베리오그램 → 베리오그램"""
    return re.sub(r"^\(.*?\)", "", ko)


def variant_keys(ko):
    """표제어에 해당하는 VARIANTS의 권장어들. 띄어쓰기와 괄호 설명은 무시함"""
    parts = [re.sub(r"\s*\(.*?\)", "", x).replace(" ", "") for x in bare(ko).split("/")]
    return [k for k in VARIANTS if k.replace(" ", "") in parts]


def group_key(ko):
    ch = bare(ko)[0]
    if "가" <= ch <= "힣":
        cho = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"[(ord(ch) - 0xAC00) // 588]
        return {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}.get(cho, cho)
    return "영문·기호"


def lesson_label(lid):
    return f"{int(lid)}강"


def table(entries):
    groups = {}
    for e in sorted(entries.values(), key=lambda e: (group_key(e["ko"]) == "영문·기호", bare(e["ko"]))):
        groups.setdefault(group_key(e["ko"]), []).append(e)
    lines = []
    for g, es in groups.items():
        lines += [f"### {g}", "", "| 한글 | 영문 | 처음 나온 강 | 비고 |", "|---|---|---|---|"]
        for e in es:
            note = "; ".join(e["notes"])
            if e["variants"]:
                note = (note + "; " if note else "") + "이형: " + ", ".join(e["variants"])
            more = f" (외 {len(e['lessons']) - 1}개 강)" if len(e["lessons"]) > 1 else ""
            lines.append(f"| {e['ko']} | {e['en']} | {lesson_label(e['first'])}{more} | {note} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main():
    rows = read_terms()
    entries = merge(rows)
    missing = [k for k in VARIANTS if not any(k in variant_keys(ko) for ko in entries)]
    data = {"generated_by": "book/fig-src/D.py", "count": len(entries),
            "terms": sorted(entries.values(), key=lambda e: e["ko"]),
            "variants": VARIANTS}
    with open(os.path.join(BOOK, "glossary.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    path = os.path.join(LESSONS, "D-glossary.md")
    s = open(path, encoding="utf-8").read()
    a, b = s.index(START) + len(START), s.index(END)
    s = s[:a] + "\n\n" + table(entries) + "\n" + s[b:]
    open(path, "w", encoding="utf-8").write(s)
    by_en = {}
    for e in entries.values():
        by_en.setdefault(e["en"].lower(), []).append(e["ko"])
    dup = {k: v for k, v in by_en.items() if len(v) > 1}
    print(f"핵심 용어 표 {len(rows)}행 → 용어 {len(entries)}개 (강 {len(set(r[0] for r in rows))}개)")
    print(f"권장어 {len(VARIANTS)}개, 용어 표에 없는 권장어: {missing}")
    print(f"영문이 같은데 한글이 다른 용어: {dup}")
    groups = {}
    for e in entries.values():
        groups[group_key(e["ko"])] = groups.get(group_key(e["ko"]), 0) + 1
    print(f"묶음별 용어 수: {groups}")


if __name__ == "__main__":
    main()
