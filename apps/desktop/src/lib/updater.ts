// 자동 업데이트: GitHub Releases의 latest.json을 확인하고, 서명을 검증한 뒤 설치·재시작함 (Tauri 앱에서만)

import { isTauri } from "@tauri-apps/api/core";

import { t } from "../i18n";

export interface AvailableUpdate {
  version: string;
  notes: string;
  install: (onProgress: (fraction: number | null) => void) => Promise<void>;
}

/** 새 버전이 있으면 정보를, 없으면 null을 돌려줌. 네트워크 오류는 예외로 올림 */
export async function findUpdate(): Promise<AvailableUpdate | null> {
  if (!isTauri()) throw new Error(t("업데이트 확인은 설치한 앱에서만 할 수 있음"));
  const { check } = await import("@tauri-apps/plugin-updater");
  const update = await check();
  if (!update) return null;
  return {
    version: update.version,
    notes: update.body ?? "",
    install: async (onProgress) => {
      let total = 0;
      let received = 0;
      await update.download((event) => {
        if (event.event === "Started") {
          total = event.data.contentLength ?? 0;
          onProgress(total ? 0 : null);
        } else if (event.event === "Progress") {
          received += event.data.chunkLength;
          onProgress(total ? received / total : null);
        }
      });
      // 설치 전에 엔진을 끔. Windows는 실행 중인 엔진 파일을 덮어쓰지 못해 설치가 실패하기 때문임
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("shutdown_engine");
      await update.install(); // Windows는 여기서 설치 프로그램이 앱을 닫고 설치한 뒤 다시 켬
      const { relaunch } = await import("@tauri-apps/plugin-process");
      await relaunch();
    },
  };
}

/** 앱 버전 (Tauri 앱이면 번들 버전, 브라우저 개발 모드면 package.json 버전) */
export async function appVersion(): Promise<string> {
  if (isTauri()) {
    const { getVersion } = await import("@tauri-apps/api/app");
    return getVersion();
  }
  return import.meta.env.VITE_APP_VERSION ?? "dev";
}

/** 외부 브라우저로 링크를 엶 */
export async function openExternal(url: string): Promise<void> {
  if (isTauri()) {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(url);
  } else {
    window.open(url, "_blank", "noopener");
  }
}

/** 저장한 파일을 Finder·탐색기에서 선택된 상태로 보여줌 (Tauri 앱에서만) */
export async function revealInFolder(path: string): Promise<void> {
  if (!isTauri()) return;
  const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
  await revealItemInDir(path);
}
