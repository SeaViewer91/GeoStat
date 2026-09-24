// 상단 도구 모음: 파일·프로젝트, 선택 도구, 배경지도

import { useEffect, useRef, useState } from "react";

import { platformKeys, t } from "../i18n";
import { DATA_FILTER, PROJECT_FILTER, dirname, pickOpenPath, pickSavePath } from "../lib/dialogs";
import { engine, type SampleInfo } from "../lib/engine";
import { renderMapPng } from "../lib/mapExport";
import { openExternal } from "../lib/updater";
import { useApp, type Basemap, type Tool } from "../store";

const REPO = "https://github.com/SeaViewer91/GeoStat";
/** 사용 설명서 주소 (영어 화면이면 영어판) */
export const manualUrl = (lang: string) => `${REPO}/blob/main/docs/${lang === "en" ? "manual.en.md" : "manual.md"}`;

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
  const path = await pickOpenPath([DATA_FILTER], t("데이터 열기"));
  if (path) await useApp.getState().openFile(path);
}

export async function openProjectFlow() {
  const path = await pickOpenPath([PROJECT_FILTER], t("프로젝트 열기"));
  if (path) await useApp.getState().openProject(path);
}

export async function saveProjectFlow(saveAs = false) {
  const s = useApp.getState();
  if (s.order.length === 0) {
    s.notify(t("저장할 데이터가 없음"));
    return;
  }
  let path = saveAs ? null : s.projectPath;
  if (!path) {
    const first = s.datasets[s.order[0]];
    const suggestion = first ? `${dirname(first.info.path)}/${first.info.name}.gstproj` : undefined;
    path = await pickSavePath([PROJECT_FILTER], t("프로젝트 저장"), suggestion);
  }
  if (path) await s.saveProject(path);
}

/** 지도 화면을 범례·출처와 함께 PNG로 저장함 */
export async function exportMapFlow() {
  const s = useApp.getState();
  const ds = s.activeId ? s.datasets[s.activeId] : undefined;
  const suggestion = ds ? `${dirname(ds.info.path)}/${ds.info.name}_${t("지도")}.png` : undefined;
  const path = await pickSavePath([{ name: t("PNG 이미지"), extensions: ["png"] }], t("지도 이미지 저장"), suggestion);
  if (!path) return;
  let data: string;
  try {
    data = renderMapPng({
      legend:
        ds?.theme && ds.visible ? { title: `${ds.info.name} · ${ds.theme.column}`, theme: ds.theme } : null,
      attribution: s.basemap !== "none" ? "© OpenStreetMap contributors · OpenFreeMap" : null,
    });
  } catch (err) {
    s.fail(err);
    return;
  }
  try {
    const r = await engine.saveImage(path, data);
    s.notify(t("지도 이미지를 저장함: {path}", { path: r.path }));
  } catch (err) {
    s.fail(err);
  }
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
        {t(label)} ▾
      </button>
      {open && (
        <div className="menu-list" role="menu" aria-label={t(label)}>
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
                <span>{t(item.label)}</span>
                {item.shortcut && <kbd>{platformKeys(item.shortcut)}</kbd>}
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
  const hasRaster = useApp((s) => s.rasterOrder.length > 0);
  const hasLayers = useApp((s) => s.order.length + s.rasterOrder.length > 0);
  const lang = useApp((s) => s.lang);
  const setLanguage = useApp((s) => s.setLanguage);
  const checkUpdate = useApp((s) => s.checkUpdate);
  const openSample = useApp((s) => s.openSample);
  const engineGeneration = useApp((s) => s.engineGeneration);
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  useEffect(() => {
    engine
      .samples()
      .then(setSamples)
      .catch(() => setSamples([]));
  }, [engineGeneration]);

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
          { label: "지도 이미지 저장 (PNG)…", onClick: () => void exportMapFlow(), disabled: !hasLayers || !!busy },
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
            label: "회귀 분석 (OLS · 공간회귀 · GWR · MGWR)…",
            onClick: () => {
              if (!activeId) return;
              onToggleCharts(true);
              showDialog({ kind: "regression", datasetId: activeId });
            },
            disabled: !activeId || !!busy,
          },
          {
            label: "군집 분석 (SKATER · Max-p · AZP · K-평균)…",
            onClick: () => {
              if (!activeId) return;
              onToggleCharts(true);
              showDialog({ kind: "cluster", datasetId: activeId });
            },
            disabled: !activeId || !!busy,
          },
          "-",
          {
            label: "존 통계 (래스터 → 폴리곤)…",
            onClick: () => activeId && showDialog({ kind: "zonal", datasetId: activeId }),
            disabled: !activeId || !!busy || !hasRaster,
          },
          {
            label: "격자 만들기 (정사각·육각)…",
            onClick: () => showDialog({ kind: "fishnet" }),
            disabled: !!busy || (!activeId && !hasRaster),
          },
          "-",
          {
            label: "계산 필드 추가…",
            onClick: () => activeId && showDialog({ kind: "field", datasetId: activeId }),
            disabled: !activeId,
          },
        ]}
      />
      <Menu
        label="도움말"
        items={[
          { label: "사용 설명서", onClick: () => void openExternal(manualUrl(lang)) },
          "-",
          ...samples.map((sample) => ({
            label: `${t("샘플")}: ${t(sample.name)}`,
            onClick: () => void openSample(sample.id),
            disabled: !!busy,
          })),
          "-" as const,
          { label: "업데이트 확인…", onClick: () => void checkUpdate(true) },
          {
            label: lang === "ko" ? "English (영어로 보기)" : "한국어 (Korean)",
            onClick: () => setLanguage(lang === "ko" ? "en" : "ko"),
          },
          "-",
          { label: "GeoStat 정보", onClick: () => showDialog({ kind: "about" }) },
        ]}
      />
      <button
        className={chartsOpen ? "on-soft" : ""}
        onClick={() => onToggleCharts()}
        title={t("차트 패널 (⌘J)")}
      >
        {t("차트")}
      </button>

      <div className="spacer" />

      <div className="segmented" role="group" aria-label={t("선택 도구")}>
        {TOOLS.map((tl) => (
          <button
            key={tl.id}
            className={tool === tl.id ? "on" : ""}
            aria-pressed={tool === tl.id}
            onClick={() => setTool(tl.id)}
            title={t(tl.title)}
          >
            {t(tl.label)}
          </button>
        ))}
      </div>
      <button onClick={() => activeId && invertSelection(activeId)} disabled={!activeId} title={t("선택 반전")}>
        {t("반전")}
      </button>
      <button
        onClick={() => activeId && clearSelection(activeId)}
        disabled={!activeId || selectedCount === 0}
        title={t("선택 해제")}
      >
        {t("선택 해제")}
      </button>

      <select
        aria-label={t("배경지도")}
        value={basemap}
        onChange={(e) => setBasemap(e.target.value as Basemap)}
        title={t("배경지도 (OpenFreeMap, 인터넷 연결 필요)")}
      >
        {BASEMAPS.map((b) => (
          <option key={b.id} value={b.id}>
            {t(b.label)}
          </option>
        ))}
      </select>
    </header>
  );
}
