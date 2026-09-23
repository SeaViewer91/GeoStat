/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 브라우저 개발 모드에서 붙을 엔진 주소 (예: http://127.0.0.1:8765). Tauri에서는 쓰지 않음 */
  readonly VITE_ENGINE_URL?: string;
  readonly VITE_ENGINE_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
