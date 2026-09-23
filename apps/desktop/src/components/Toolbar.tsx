// 상단 도구 모음: 파일 열기, 선택 도구

import { useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

import { useApp } from "../store";

// 파일 선택창에 보일 확장자 (엔진 SUPPORTED_EXTENSIONS와 맞춤)
const VECTOR_FILTER = {
  name: "공간 벡터 파일",
  extensions: ["shp", "gpkg", "geojson", "json", "fgb", "kml", "gml"],
};

interface Props {
  boxMode: boolean;
  onToggleBoxMode: () => void;
}

export function Toolbar({ boxMode, onToggleBoxMode }: Props) {
  const openPath = useApp((s) => s.openPath);
  const busy = useApp((s) => s.busy);
  const activeId = useApp((s) => s.activeId);
  const clearSelection = useApp((s) => s.clearSelection);
  const [manualPath, setManualPath] = useState("");

  const onOpen = async () => {
    if (!isTauri()) return; // 브라우저 모드에서는 경로 입력칸을 씀
    const picked = await open({ multiple: false, directory: false, filters: [VECTOR_FILTER] });
    if (typeof picked === "string") await openPath(picked);
  };

  return (
    <header className="toolbar">
      <span className="brand">GeoStat</span>

      {isTauri() ? (
        <button onClick={onOpen} disabled={!!busy}>
          파일 열기…
        </button>
      ) : (
        <form
          className="path-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (manualPath.trim()) void openPath(manualPath.trim());
          }}
        >
          <input
            aria-label="파일 경로"
            placeholder="파일 절대 경로 (브라우저 개발 모드)"
            value={manualPath}
            onChange={(e) => setManualPath(e.target.value)}
          />
          <button type="submit" disabled={!!busy}>
            열기
          </button>
        </form>
      )}

      <div className="spacer" />

      <button
        className={boxMode ? "toggle on" : "toggle"}
        onClick={onToggleBoxMode}
        title="사각형 선택 (B). Shift를 누른 채 끌어도 됨. ⌘를 누르면 기존 선택에 추가함"
        aria-pressed={boxMode}
      >
        ▭ 사각형 선택
      </button>
      <button onClick={() => activeId && clearSelection(activeId)} disabled={!activeId}>
        선택 해제
      </button>
    </header>
  );
}
