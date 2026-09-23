# P0 기술 검증 보고서

> 작성일: 2026-09-24 · 대상 커밋: P0 뼈대 구현 직후

## 1. 요약

| 항목 | 결과 | 검증 환경 |
|---|---|---|
| Python 엔진 ↔ Tauri 셸 연결 (랜덤 포트·토큰·준비 신호) | ✅ 통과 | Linux (Xvfb) |
| 앱 강제 종료 시 엔진 자동 종료 (stdin 감시) | ✅ 통과 | Linux |
| cp949 shapefile(.cpg 없음) 한글 판별·표시 | ✅ 통과 | pytest, 브라우저 |
| GeoArrow IPC 전송 + deck.gl 렌더링 | ✅ 통과 | 헤드리스 Chromium |
| 사각형 선택 (20만 폴리곤) | ✅ 통과 | 헤드리스 Chromium |
| PyInstaller onedir 빌드 + 번들 엔진 실행 | ✅ 통과 | Linux (.deb 번들로 확인) |
| **macOS 서명·공증** | ⏳ 미검증 | 맥 + Apple Developer 인증서 필요 |
| **macOS WKWebView 실제 렌더링** | ⏳ 미검증 | 맥에서 `npm run tauri dev` 필요 |

클라우드 Linux 환경에서 확인 가능한 항목은 모두 통과함. **P0의 핵심 리스크인 macOS 서명·공증은 아직 확인하지 못했으므로 P1 착수 전에 맥에서 반드시 확인해야 함.**

## 2. 측정값

Linux 클라우드 VM(2코어, GPU 없음, WebGL은 SwiftShader 소프트웨어 렌더링) 기준. 맥 GPU 환경에서는 렌더링이 훨씬 빠를 것으로 예상됨.

| 작업 | 1,600 폴리곤 | 200,000 폴리곤 |
|---|---|---|
| 엔진: 파일 열기 | 0.09초 | 0.95초 |
| 엔진: WGS84 변환 + GeoArrow 직렬화 | 0.03초 | 1.6초 |
| 전송 크기 | 0.1 MB | 17.6 MB |
| 프론트: 수신·파싱·범위 계산 | 26 ms | 1.8초 |
| 파일 열기 → 화면 표시 (전체) | 2.8초 | 5.6초 |
| 사각형 선택 계산 | 0.4 ms (208개) | 5.7 ms (92,861개) |

- 번들 엔진 시작 → 준비 신호: 약 1초
- 엔진 번들 크기: 391 MB (pyarrow 149 MB, GDAL 라이브러리 80 MB 차지)

## 3. 발견한 문제와 조치

| 문제 | 조치 |
|---|---|
| `@geoarrow/deck.gl-layers`가 `@geoarrow/deck.gl-geoarrow`로 이름이 바뀌고 이전 패키지는 더 이상 갱신되지 않음 | 새 패키지(0.4)로 교체함. 0.4는 레코드 배치 하나당 레이어 하나로 그리는 구조라 선택 색상도 배치별로 만들도록 수정함 |
| 폴리곤 삼각분할 워커를 기본값으로 CDN(jsdelivr)에서 받아옴 → 오프라인에서 동작하지 않고 CSP에도 걸림 | 워커 파일을 앱 번들에 포함하고 `_subLayerProps.fill.earcutWorkerUrl`로 지정함 |
| PyInstaller가 `pyogrio._geometry` 등 확장 모듈 간 임포트를 놓침 | spec에서 pyogrio·pyproj·shapely를 `collect_all`로 수집함. 스모크 테스트로 확인하도록 함 |
| 단일 Polygon만 있는 레이어는 `geoarrow.polygon`, 섞이면 `geoarrow.multipolygon`으로 나옴 | 프론트엔드가 두 타입을 모두 처리하므로 그대로 둠 |
| Tauri는 `resources` 안의 바이너리를 서명하지 않음 | `packaging/macos/sign-engine.sh`로 tauri build 전에 엔진을 미리 서명하도록 함 (맥에서 검증 필요) |

## 4. 맥에서 해야 할 확인 (P0 마무리)

1. **개발 모드 실행**: `cd engine && uv sync`, `cd apps/desktop && npm install && npm run tauri dev`
   - 파일 열기 대화상자 → `data/local/seoul_grid_cp949.shp` 열기 → 한글 속성, 지도 표시, 사각형 선택 확인
   - `perf_grid_200k.gpkg`로 렌더링·선택 체감 속도 확인
2. **서명 없는 번들**: `packaging/macos/release.sh --unsigned` → `GeoStat.app` 실행 확인
3. **서명·공증**: Apple Developer Program 가입 후 `APPLE_SIGNING_IDENTITY` 등 환경변수 설정 → `packaging/macos/release.sh`
   - 다른 맥에서 .dmg 설치·실행 (Gatekeeper 경고 없이 열리는지)
4. 결과를 이 문서에 추가하고 P1 착수 여부를 결정함

## 5. 이후 개선 과제

- 엔진 번들 용량 축소: pyarrow의 flight·gandiva·substrait 등 안 쓰는 라이브러리 제외 검토 (P6)
- 배경지도(MapLibre) 추가: P0에서는 범위를 줄이려고 빼 둠 (P1)
- 엔진이 실행 중 죽었을 때 자동 재시작·UI 알림 (P1)
- 20만 개 이상에서 지오메트리 전송 크기 줄이기: 표시용 단순화, 좌표 float32 변환 검토 (P5)
