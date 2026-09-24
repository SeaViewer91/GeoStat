import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

import pkg from "./package.json";

// Tauri CLI가 개발 모드에서 설정하는 호스트 (모바일 디버깅용). 데스크톱에서는 비어 있음
const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [react()],
  // Tauri 로그가 가려지지 않도록 화면 지우기를 끔
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    watch: {
      // Rust·Python 소스 변경으로 프론트엔드가 다시 로드되지 않게 함
      ignored: ["**/src-tauri/**"],
    },
  },
  envPrefix: ["VITE_", "TAURI_ENV_"],
  // 브라우저 개발 모드에서 보여 줄 앱 버전
  define: { "import.meta.env.VITE_APP_VERSION": JSON.stringify(pkg.version) },
  build: {
    // macOS WKWebView(Safari 엔진) 기준
    target: "safari15",
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
    chunkSizeWarningLimit: 4000,
  },
});
