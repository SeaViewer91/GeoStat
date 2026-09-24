"""PyInstaller 진입 스크립트.

esda는 순열 검정을 joblib(loky) 하위 프로세스로 병렬 처리함. loky는 파이썬 인터프리터를
`python -m <모듈>` 또는 `python -c <코드>` 형태로 다시 실행하는데, 번들에서는 sys.executable이
엔진 실행 파일이므로 이 인수들이 엔진으로 들어옴. 그래서 joblib·loky 관련 호출만 인터프리터처럼 처리해 줌.
"""

import multiprocessing
import runpy
import sys

# 하위 프로세스로 실행을 허용하는 모듈·코드 (엔진이 아닌 임의 코드를 실행하지 않도록 제한함)
_ALLOWED_PREFIXES = ("joblib.", "loky.")


def _interpreter_args() -> tuple[str, str, list[str]] | None:
    """`[-플래그...] -m 모듈 ...` 또는 `[-플래그...] -c 코드 ...` 형태면 (방식, 대상, 나머지 인수)를 반환함."""
    args = sys.argv[1:]
    i = 0
    while i < len(args) and args[i].startswith("-") and args[i] not in ("-m", "-c"):
        i += 1  # -B, -E 같은 인터프리터 플래그는 건너뜀
    if i + 1 < len(args) and args[i] in ("-m", "-c"):
        return args[i], args[i + 1], args[i + 2 :]
    return None


def _run_child(kind: str, target: str, rest: list[str]) -> None:
    if kind == "-m":
        if not target.startswith(_ALLOWED_PREFIXES):
            sys.exit(f"허용하지 않는 모듈: {target}")
        sys.argv = [sys.argv[0], *rest]
        runpy.run_module(target, run_name="__main__", alter_sys=True)
    else:
        if "joblib" not in target and "loky" not in target:
            sys.exit("허용하지 않는 코드")
        sys.argv = ["-c", *rest]
        exec(compile(target, "<string>", "exec"), {"__name__": "__main__"})  # noqa: S102


if __name__ == "__main__":
    # multiprocessing 방식의 하위 프로세스 처리 (PyInstaller 권장)
    multiprocessing.freeze_support()

    child = _interpreter_args()
    if child is not None:
        _run_child(*child)
        sys.exit(0)

    from geostat_engine.__main__ import main

    main()
