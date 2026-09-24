// 상단 도구 모음: 파일·프로젝트, 선택 도구, 배경지도

import { useEffect, useRef, useState } from "react";

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

type MenuItem = { label: string; onClick: () => void; disabled?: boolean; shortcut?: string } | "-";

/** 간단한 드롭다운 메뉴. 바깥을 누르거나 Esc를 누르면 닫힘 */
function Menu({ label, items }: { label: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div className="menu" ref={ref}>
      <button className={open ? "on-soft" : ""} onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open}>
        {label} ▾
      </button>
      {open && (
        <div className="menu-list" role="menu" aria-label={label}>
          {items.map((item, i) =>
            item === "-" ? (
              <div key={i} className="menu-sep" role="separator" />
            ) : (
              <button
                key={item.label}
                role="menuitem"
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  item.onClick();
                }}
              >
                <span>{item.label}</span>
                {item.shortcut && <kbd>{item.shortcut}</kbd>}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}

interface ToolbarProps {
  chartsOpen: boolean;
  onToggleCharts: (open?: boolean) => void;
}

export function Toolbar({ chartsOpen, onToggleCharts }: ToolbarProps) {
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
  const showDialog = useApp((s) => s.showDialog);

  return (
    <header className="toolbar">
      <span className="brand" title={projectPath ?? undefined}>
        GeoStat
      </span>

      <Menu
        label="파일"
        items={[
          { label: "데이터 열기…", shortcut: "⌘O", onClick: openDataFlow, disabled: !!busy },
          { label: "프로젝트 열기…", shortcut: "⇧⌘O", onClick: openProjectFlow, disabled: !!busy },
          "-",
          { label: "프로젝트 저장", shortcut: "⌘S", onClick: () => saveProjectFlow(false), disabled: !!busy },
          { label: "다른 이름으로 저장…", shortcut: "⇧⌘S", onClick: () => saveProjectFlow(true), disabled: !!busy },
          "-",
          {
            label: "레이어 내보내기…",
            onClick: () => activeId && showDialog({ kind: "export", datasetId: activeId }),
            disabled: !activeId,
          },
        ]}
      />
      <Menu
        label="공간 분석"
        items={[
          {
            label: "공간가중치 만들기…",
            onClick: () => activeId && showDialog({ kind: "weights", datasetId: activeId }),
            disabled: !activeId || !!busy,
          },
          "-",
          {
            label: "Moran's I · Moran 산점도…",
            onClick: () => {
              if (!activeId) return;
              onToggleCharts(true);
              showDialog({ kind: "moran", datasetId: activeId });
            },
            disabled: !activeId || !!busy,
          },
          {
            label: "국지 통계 (LISA · Gi* · Local Geary)…",
            onClick: () => activeId && showDialog({ kind: "local", datasetId: activeId }),
            disabled: !activeId || !!busy,
          },
          {
            label: "Join Count (이진 변수)…",
            onClick: () => activeId && showDialog({ kind: "joincount", datasetId: activeId }),
            disabled: !activeId || !!busy,
          },
          "-",
          {
            label: "계산 필드 추가…",
            onClick: () => activeId && showDialog({ kind: "field", datasetId: activeId }),
            disabled: !activeId,
          },
        ]}
      />
      <button className={chartsOpen ? "on-soft" : ""} onClick={() => onToggleCharts()} title="차트 패널 (⌘J)">
        차트
      </button>

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
