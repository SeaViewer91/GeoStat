// 대화상자 공용 부품: 모달 틀, 변수·가중치·순열 선택

import { Fragment, type ReactNode } from "react";

import { t } from "../i18n";
import { useApp, type LoadedDataset } from "../store";

export function Modal({
  title,
  children,
  onClose,
  footer,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  footer: ReactNode;
}) {
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-label={title}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && onClose()}
      >
        <h3>{title}</h3>
        <div className="modal-body">{children}</div>
        <div className="modal-footer">{footer}</div>
      </div>
    </div>
  );
}

export const close = () => useApp.getState().showDialog(null);

/** 번역문의 {이름} 자리에 강조·코드 같은 요소를 넣음 (언어마다 어순이 달라도 됨) */
export function tx(ko: string, parts: Record<string, ReactNode>): ReactNode[] {
  return t(ko)
    .split(/\{(\w+)\}/)
    .map((s, i) => (i % 2 ? <Fragment key={i}>{parts[s] ?? `{${s}}`}</Fragment> : s));
}

export function NumericSelect({
  ds,
  value,
  onChange,
  label,
}: {
  ds: LoadedDataset;
  value: string;
  onChange: (v: string) => void;
  label: string;
}) {
  const cols = ds.info.columns.filter((c) => c.kind === "numeric");
  return (
    <label>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
        {cols.map((c) => (
          <option key={c.name} value={c.name}>
            {c.name}
            {c.origin !== "data" ? t(" (계산)") : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

export function WeightsSelect({ ds, value, onChange }: { ds: LoadedDataset; value: string; onChange: (v: string) => void }) {
  return (
    <label>
      {t("공간가중치")}
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={t("공간가중치")}>
        {ds.weights.map((w) => (
          <option key={w.id} value={w.id}>
            {w.name} — {w.description}
          </option>
        ))}
      </select>
    </label>
  );
}

export function NoWeights({ datasetId }: { datasetId: string }) {
  return (
    <div className="notice-box">
      {t("공간가중치가 아직 없음.")}{" "}
      <button className="link" onClick={() => useApp.getState().showDialog({ kind: "weights", datasetId })}>
        {t("가중치 만들기…")}
      </button>
    </div>
  );
}

export const firstNumeric = (ds: LoadedDataset | undefined) =>
  ds?.info.columns.find((c) => c.kind === "numeric")?.name ?? "";

export function PermutationSelect({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <label>
      {t("순열 횟수 (유사 p값 계산)")}
      <select value={value} onChange={(e) => onChange(Number(e.target.value))} aria-label={t("순열 횟수")}>
        {[99, 199, 499, 999, 9999].map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
    </label>
  );
}
