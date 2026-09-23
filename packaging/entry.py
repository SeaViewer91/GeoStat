"""PyInstaller 진입 스크립트. 패키지 상대 임포트 문제를 피하려고 별도 파일로 둠."""

from geostat_engine.__main__ import main

if __name__ == "__main__":
    main()
