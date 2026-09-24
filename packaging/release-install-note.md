

---

### 설치

**macOS** (macOS 14 이상, Apple Silicon)
1. `GeoStat_<버전>_aarch64.dmg`를 받아 열고 `GeoStat.app`을 응용 프로그램 폴더로 끌어 옮김
2. 처음 실행하면 "확인되지 않은 개발자" 경고가 뜸 (Apple 공증을 받지 않은 앱이라 그럼). 아래 중 하나로 한 번만 허용하면 됨
   - **시스템 설정 → 개인정보 보호 및 보안** 맨 아래의 **"그래도 열기"** 클릭
   - 또는 터미널에서 `xattr -dr com.apple.quarantine /Applications/GeoStat.app`

**Windows** (Windows 10·11, 64비트)
1. `GeoStat_<버전>_x64-setup.exe`를 받아 실행함. 관리자 권한 없이 현재 사용자에게 설치됨
2. 코드 서명 인증서가 없어 "Windows의 PC 보호" 창이 뜰 수 있음. **추가 정보 → 실행**을 누르면 됨

이후 새 버전은 앱이 알려 주며, **도움말 → 업데이트 확인**으로도 설치할 수 있음. `SHA256SUMS`로 받은 파일을 검증할 수 있음.

`.app.tar.gz`, `.sig`, `latest.json`은 앱의 자동 업데이트용 파일이라 직접 받을 필요 없음.
