"""용어 점검: book/glossary.json의 이형(variants)이 본문에 쓰였는지 찾음.

코드 블록과 부록 D(용어 대역표 자체)는 건너뜀. 이형이 꼭 필요한 문장(예: "공간지연이라고도 함")은
줄 끝에 <!-- 용어 허용 --> 주석을 달면 건너뜀.

실행:
    python3 book/tools/check_terms.py
"""
import glob
import json
import os
import re
import sys

BOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def main():
    g = json.load(open(os.path.join(BOOK, "glossary.json"), encoding="utf-8"))
    found = 0
    for p in sorted(glob.glob(os.path.join(BOOK, "lessons", "*.md"))):
        if os.path.basename(p).startswith("D-"):
            continue
        s = open(p, encoding="utf-8").read()
        s = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), s, flags=re.S)
        for i, line in enumerate(s.splitlines(), 1):
            if "용어 허용" in line:
                continue
            for good, bads in g["variants"].items():
                for bad in bads:
                    if bad in line:
                        found += 1
                        print(f"{os.path.basename(p)}:{i}: '{bad}' → '{good}'")
    print(f"이형 {found}건")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
