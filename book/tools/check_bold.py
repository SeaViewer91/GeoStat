"""GitHub(CommonMark)에서 적용되지 않는 굵게(**…**)를 찾음.

CommonMark의 강조 규칙상, 닫는 **의 바로 앞이 문장부호이고 바로 뒤가 글자(한글 조사 등)이면
닫는 구분자로 인정되지 않음. 여는 **도 마찬가지로 바로 뒤가 문장부호이고 바로 앞이 글자면 인정되지 않음.
예: **구역 통계(zonal statistics)**라고  →  GitHub에서 굵게가 풀림

사용: python book/tools/check_bold.py book/lessons/*.md
나중에 lint(book/tools/)에 합칠 예정임.
"""
import re
import sys
import unicodedata


def is_punct(ch: str) -> bool:
    return unicodedata.category(ch)[0] in ("P", "S")


def is_space(ch: str) -> bool:
    return ch == "" or ch.isspace()


def check_line(line: str):
    problems = []
    for m in re.finditer(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", line):
        before = line[m.start() - 1] if m.start() > 0 else ""
        after = line[m.end()] if m.end() < len(line) else ""
        inner = m.group(1)
        first, last = inner[0], inner[-1]
        # 여는 **: 뒤가 문장부호면 앞이 공백·문장부호여야 함
        if is_punct(first) and not (is_space(before) or is_punct(before)):
            problems.append((m.group(0), "여는 ** 뒤가 문장부호인데 앞에 글자가 붙음"))
        # 닫는 **: 앞이 문장부호면 뒤가 공백·문장부호여야 함
        if is_punct(last) and not (is_space(after) or is_punct(after)):
            problems.append((m.group(0) + after, "닫는 ** 앞이 문장부호인데 뒤에 글자가 붙음"))
    return problems


def main(paths):
    n = 0
    for p in paths:
        in_code = False
        for i, line in enumerate(open(p, encoding="utf-8"), 1):
            if line.lstrip().startswith("```"):
                in_code = not in_code
            if in_code:
                continue
            for frag, why in check_line(line.rstrip("\n")):
                print(f"{p}:{i}: {why}: {frag}")
                n += 1
    print(f"굵게 문제 {n}건")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
