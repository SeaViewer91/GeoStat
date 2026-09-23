// 상단 도구 모음: 파일·프로젝트, 선택 도구, 배경지도

import { DATA_FILTER, PROJECT_FILTER, dirname, pickOpenPath, pickSavePath } from "../lib/dialogs";
import { useApp, type Basemap, type Tool } from "../store";

const TOOLS: { id: Tool; label: string; key: string; title: string }[] = [
  { id: "pan", label: "✋ 이동", key: "Esc", title: "지도 이동·클릭 선택 (Esc)" },
  { id: "box", label: "▭ 사각형", key: "B", title: "사각형 선택 (B). Shift를 누른 채 끌어도 됨" },
  { id: "lasso", label: "◌ 올가미", key: "L", title: "올가미 선택 (L). 중심점이 안에 든 피처를 고름" },
];

const BASEMAPS: { id: Basemap; label: string }[] = [
  { id: "none", label: "배경지도 없음" },
  { id: "positron", label: "밝은 지도" },
  { id: "liberty", label: "기본 지도" },
];

export async function openDataFlow() {
  const path = await pickOpenPath([DATA_FILTER], "데이터 열기");
  if (path) await useApp.getState().openFile(path);
}

export async function openProjectFlow() {
  const path = await pickOpenPath([PROJECT_FILTER], "프로젝트 열기");
  if (path) await useApp.getState().openProject(path);
}

export async function saveProjectFlow(saveAs = false) {
  const s = useApp.getState();
  if (s.order.length === 0) {
    s.notify("저장할 데이터가 없음");
    return;
  }
  let path = saveAs ? null : s.projectPath;
  if (!path) {
    const first = s.datasets[s.order[0]];
    const suggestion = first ? `${dirname(first.info.path)}/${first.info.name}.gstproj` : undefined;
    path = await pickSavePath([PROJECT_FILTER], "프로젝트 저장", suggestion);
  }
  if (path) await s.saveProject(path);
}

export function Toolbar() {
  const busy = useApp((s) => s.busy);
  const tool = useApp((s) => s.tool);
  const setTool = useApp((s) => s.setTool);
  const basemap = useApp((s) => s.basemap);
  const setBasemap = useApp((s) => s.setBasemap);
  const activeId = useApp((s) => s.activeId);
  const selectedCount = useApp((s) => (s.activeId ? s.datasets[s.activeId]?.selectedCount ?? 0 : 0));
  const clearSelection = useApp((s) => s.clearSelection);
  const invertSelection = useApp((s) => s.invertSelection);
  const projectPath = useApp((s) => s.projectPath);

  return (
    <header className="toolbar">
      <span className="brand" title={projectPath ?? undefined}>
        GeoStat
      </span>

      <div className="group">
        <button onClick={openDataFlow} disabled={!!busy} title="데이터 열기 (⌘O)">
          데이터 열기…
        </button>
        <button onClick={openProjectFlow} disabled={!!busy} title="프로젝트 열기 (⇧⌘O)">
          프로젝트 열기…
        </button>
        <button onClick={() => saveProjectFlow(false)} disabled={!!busy} title="프로젝트 저장 (⌘S)">
          저장
        </button>
        <button onClick={() => saveProjectFlow(true)} disabled={!!busy} title="다른 이름으로 저장 (⇧⌘S)">
          다른 이름으로…
        </button>
      </div>

      <div className="spacer" />

      <div className="segmented" role="group" aria-label="선택 도구">
        {TOOLS.map((t) => (
          <button
            key={t.id}
            className={tool === t.id ? "on" : ""}
            aria-pressed={tool === t.id}
            onClick={() => setTool(t.id)}
            title={t.title}
          >
            {t.label}
          </button>
        ))}
      </div>
      <button onClick={() => activeId && invertSelection(activeId)} disabled={!activeId} title="선택 반전">
        반전
      </button>
      <button
        onClick={() => activeId && clearSelection(activeId)}
        disabled={!activeId || selectedCount === 0}
        title="선택 해제"
      >
        선택 해제
      </button>

      <select
        aria-label="배경지도"
        value={basemap}
        onChange={(e) => setBasemap(e.target.value as Basemap)}
        title="배경지도 (OpenFreeMap, 인터넷 연결 필요)"
      >
        {BASEMAPS.map((b) => (
          <option key={b.id} value={b.id}>
            {b.label}
          </option>
        ))}
      </select>
    </header>
  );
}
