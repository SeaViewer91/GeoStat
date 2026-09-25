// 0.10 대화상자: 점 집계, 비율 지도(EB), 시간 변수 묶음, 시공간 분석, 기간별 자료 만들기, 보고서 내보내기

import { useEffect, useState } from "react";

import { t } from "../i18n";
import { dirname, pickSavePath } from "../lib/dialogs";
import {
  engine,
  type AggregateSpec,
  type MoranSeries,
  type RateMethod,
  type TimeGroup,
} from "../lib/engine";
import { renderMapPng } from "../lib/mapExport";
import { revealInFolder } from "../lib/updater";
import { useApp, type LoadedDataset } from "../store";
import {
  Modal,
  NoWeights,
  NumericSelect,
  PermutationSelect,
  WeightsSelect,
  close,
} from "./dialogKit";

const numericCols = (ds: LoadedDataset | undefined) =>
  ds?.info.columns.filter((c) => c.kind === "numeric").map((c) => c.name) ?? [];

// ---- 점 집계 (공간 결합) ------------------------------------------------------------

const AGG_STATS: { id: AggregateSpec["stats"][number]["stat"]; label: string }[] = [
  { id: "sum", label: "합계" },
  { id: "mean", label: "평균" },
  { id: "min", label: "최솟값" },
  { id: "max", label: "최댓값" },
  { id: "median", label: "중앙값" },
  { id: "std", label: "표준편차" },
];

export function AggregateDialog({ datasetId }: { datasetId: string }) {
  const datasets = useApp((s) => s.datasets);
  const order = useApp((s) => s.order);
  const runAggregate = useApp((s) => s.runAggregate);
  const busy = useApp((s) => s.busy);
  const target = datasets[datasetId];
  const others = order.filter((id) => id !== datasetId && datasets[id]);
  const [sourceId, setSourceId] = useState(
    others.find((id) => datasets[id].info.geometry_type === "point") ?? others[0] ?? "",
  );
  const source = datasets[sourceId];
  const [count, setCount] = useState(true);
  const [density, setDensity] = useState(false);
  const [stats, setStats] = useState<AggregateSpec["stats"]>([]);
  const [prefix, setPrefix] = useState("");
  const srcCols = numericCols(source);
  useEffect(() => {
    // 원본을 바꾸면 없는 열을 쓰는 통계는 뺌
    setStats((cur) => cur.filter((s) => srcCols.includes(s.column)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceId]);
  if (!target) return null;
  const isPolygon = target.info.geometry_type === "polygon";

  const submit = async () => {
    const ok = await runAggregate(datasetId, {
      source_id: sourceId,
      count,
      density,
      stats,
      prefix: prefix.trim() || "PT",
    });
    if (ok) close();
  };

  return (
    <Modal
      title={t("점 집계 (점 → 폴리곤)")}
      onClose={close}
      footer={
        <>
          <button onClick={close}>{t("취소")}</button>
          <button
            className="primary"
            onClick={() => void submit()}
            disabled={!isPolygon || !sourceId || (!count && !density && stats.length === 0) || !!busy}
          >
            {busy ? t("계산 중…") : t("실행")}
          </button>
        </>
      }
    >
      <div className="form">
        <p className="hint">
          {t(
            "점 레이어(조사 지점·탐지 결과 등)를 '{target}'의 폴리곤마다 모아 개수·합계 등을 열로 붙임. 두 레이어의 좌표계가 달라도 자동으로 맞춤.",
            { target: target.info.name },
          )}
        </p>
        {!isPolygon && (
          <div className="notice-box">
            {t("집계 대상은 폴리곤 레이어여야 함. 레이어 목록에서 격자·행정구역 레이어를 먼저 고르거나, 공간 분석 → 격자 만들기로 격자를 만듦.")}
          </div>
        )}
        {others.length === 0 ? (
          <div className="notice-box">{t("집계할 점 레이어를 먼저 열어야 함")}</div>
        ) : (
          <label>
            {t("점 레이어 (원본)")}
            <select value={sourceId} onChange={(e) => setSourceId(e.target.value)} aria-label={t("점 레이어")}>
              {others.map((id) => (
                <option key={id} value={id}>
                  {datasets[id].info.name} ({t("{n}개", { n: datasets[id].info.n_rows })})
                </option>
              ))}
            </select>
          </label>
        )}
        {source && source.info.geometry_type !== "point" && (
          <p className="hint warn-text">{t("점이 아닌 레이어는 각 피처의 대표점으로 셈")}</p>
        )}
        <label className="check">
          <input type="checkbox" checked={count} onChange={(e) => setCount(e.target.checked)} />
          {t("개수 (_CNT)")}
        </label>
        <label className="check">
          <input type="checkbox" checked={density} onChange={(e) => setDensity(e.target.checked)} />
          {t("밀도: ㎢당 개수 (_DENS)")}
        </label>
        <div className="field-label">{t("원본 속성 통계")}</div>
        {stats.map((s, i) => (
          <div className="row" key={i}>
            <select
              value={s.column}
              onChange={(e) => setStats(stats.map((x, j) => (j === i ? { ...x, column: e.target.value } : x)))}
              aria-label={t("원본 열")}
            >
              {srcCols.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select
              value={s.stat}
              onChange={(e) =>
                setStats(stats.map((x, j) => (j === i ? { ...x, stat: e.target.value as typeof s.stat } : x)))
              }
              aria-label={t("통계")}
            >
              {AGG_STATS.map((st) => (
                <option key={st.id} value={st.id}>
                  {t(st.label)}
                </option>
              ))}
            </select>
            <button className="link" onClick={() => setStats(stats.filter((_, j) => j !== i))} aria-label={t("빼기")}>
              ✕
            </button>
          </div>
        ))}
        <div>
          <button
            onClick={() => setStats([...stats, { column: srcCols[0], stat: "sum" }])}
            disabled={srcCols.length === 0}
          >
            + {t("통계 추가")}
          </button>
        </div>
        <label>
          {t("결과 열 접두어")}
          <input value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder="PT" />
        </label>
        <p className="hint">
          {t(
            "결과 열: {p}_CNT, {p}_DENS, {p}_SUM_<열> 등. 폴리곤 경계 위의 점은 한 폴리곤에만 셈. 점이 없는 폴리곤의 개수·합계는 0, 평균 등은 값 없음.",
            { p: prefix.trim() || "PT" },
          )}
        </p>
      </div>
    </Modal>
  );
}

// ---- 비율 지도·EB 보정 ------------------------------------------------------------

const RATE_METHODS: { id: RateMethod; label: string; hint: string; name: string }[] = [
  { id: "raw", label: "원비율", hint: "분자 ÷ 분모 그대로", name: "R_RAW" },
  {
    id: "excess_risk",
    label: "초과위험",
    hint: "관측 ÷ 기대 사건 수 (기대 = 분모 × 전체 비율). 1보다 크면 전체 평균보다 높음",
    name: "R_EXCESS",
  },
  {
    id: "eb",
    label: "경험적 베이즈(EB) 평활",
    hint: "분모가 작아 불안정한 비율을 전체 평균 쪽으로 당김",
    name: "R_EB",
  },
  { id: "spatial_rate", label: "공간 비율", hint: "(자신 + 이웃의 분자 합) ÷ (자신 + 이웃의 분모 합)", name: "R_SPATIAL" },
  {
    id: "spatial_eb",
    label: "공간 EB 평활",
    hint: "분모가 작아 불안정한 비율을 이웃 평균 쪽으로 당김",
    name: "R_SEB",
  },
];

export function RatesDialog({ datasetId }: { datasetId: string }) {
  const ds = useApp((s) => s.datasets[datasetId]);
  const runRates = useApp((s) => s.runRates);
  const busy = useApp((s) => s.busy);
  const cols = numericCols(ds);
  const [method, setMethod] = useState<RateMethod>("eb");
  const [event, setEvent] = useState(cols[0] ?? "");
  const [base, setBase] = useState(cols[1] ?? cols[0] ?? "");
  const [weightsId, setWeightsId] = useState(ds?.activeWeightsId ?? ds?.weights[0]?.id ?? "");
  const [multiplier, setMultiplier] = useState(1);
  const [name, setName] = useState("");
  if (!ds) return null;
  const meta = RATE_METHODS.find((m) => m.id === method)!;
  const needsW = method === "spatial_rate" || method === "spatial_eb";

  const submit = async () => {
    const ok = await runRates(datasetId, {
      method,
      event,
      base,
      weights_id: needsW ? weightsId : null,
      multiplier,
      name: name.trim() || meta.name,
    });
    if (ok) close();
  };

  return (
    <Modal
      title={t("비율 지도 · EB 보정")}
      onClose={close}
      footer={
        <>
          <button onClick={close}>{t("취소")}</button>
          <button
            className="primary"
            onClick={() => void submit()}
            disabled={!event || !base || event === base || (needsW && !weightsId) || !!busy}
          >
            {t("실행")}
          </button>
        </>
      }
    >
      <div className="form">
        <p className="hint">
          {t("CPUE·발생률·밀도처럼 분모가 있는 값은 분모가 작은 곳에서 크게 튐. EB 평활은 이런 곳의 비율을 평균 쪽으로 당겨 안정화함.")}
        </p>
        <label>
          {t("방법")}
          <select value={method} onChange={(e) => setMethod(e.target.value as RateMethod)} aria-label={t("방법")}>
            {RATE_METHODS.map((m) => (
              <option key={m.id} value={m.id}>
                {t(m.label)}
              </option>
            ))}
          </select>
        </label>
        <p className="hint">{t(meta.hint)}</p>
        <NumericSelect ds={ds} value={event} onChange={setEvent} label={t("분자 (사건 수·어획량 등)")} />
        <NumericSelect ds={ds} value={base} onChange={setBase} label={t("분모 (모집단·노력량 등)")} />
        {needsW && (ds.weights.length ? <WeightsSelect ds={ds} value={weightsId} onChange={setWeightsId} /> : <NoWeights datasetId={ds.info.id} />)}
        <div className="grid2">
          {method !== "excess_risk" && (
            <label>
              {t("단위 (곱할 값)")}
              <select value={multiplier} onChange={(e) => setMultiplier(Number(e.target.value))} aria-label={t("단위")}>
                {[1, 100, 1000, 10000, 100000].map((m) => (
                  <option key={m} value={m}>
                    {m === 1 ? t("그대로") : t("{n}당", { n: m })}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            {t("결과 열 이름")}
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder={meta.name} />
          </label>
        </div>
        <p className="hint">
          {t("분모는 모두 0보다 커야 함. 같은 이름으로 다시 실행하면 이전 결과를 대체함. EB Moran's I는 Moran 산점도·국지 통계에서 'EB 비율'을 고름.")}
        </p>
      </div>
    </Modal>
  );
}

// ---- 시간 변수 묶음 ----------------------------------------------------------------

/** 열 이름 끝의 기간(연도 등)을 기간 이름으로 씀. 없으면 열 이름 그대로 */
function guessLabel(column: string): string {
  const m = column.match(/((?:19|20)\d{2}(?:[_\-.]?\d{1,2})?)$/);
  return m ? m[1] : column;
}

export function TimeGroupsDialog({ datasetId }: { datasetId: string }) {
  const ds = useApp((s) => s.datasets[datasetId]);
  const saveGroups = useApp((s) => s.setTimeGroups);
  const fail = useApp((s) => s.fail);
  const notify = useApp((s) => s.notify);
  const [groups, setGroups] = useState<TimeGroup[]>(ds?.info.time_groups ?? []);
  if (!ds) return null;
  const cols = numericCols(ds);

  const update = (i: number, g: TimeGroup) => setGroups(groups.map((x, j) => (j === i ? g : x)));
  const guess = async () => {
    try {
      const found = await engine.guessTimeGroups(datasetId);
      const fresh = found.filter((g) => !groups.some((x) => x.name === g.name));
      setGroups([...groups, ...fresh]);
      notify(fresh.length ? t("시간 변수 묶음 {n}개를 찾음", { n: fresh.length }) : t("열 이름에서 기간을 찾지 못함"));
    } catch (err) {
      fail(err);
    }
  };
  const move = (g: TimeGroup, k: number, d: -1 | 1): TimeGroup => {
    const columns = [...g.columns];
    const labels = [...g.labels];
    const j = k + d;
    [columns[k], columns[j]] = [columns[j], columns[k]];
    [labels[k], labels[j]] = [labels[j], labels[k]];
    return { ...g, columns, labels };
  };

  const submit = async () => {
    if (await saveGroups(datasetId, groups)) close();
  };

  return (
    <Modal
      title={t("시간 변수 묶음")}
      onClose={close}
      footer={
        <>
          <button onClick={close}>{t("취소")}</button>
          <button className="primary" onClick={() => void submit()}>
            {t("저장")}
          </button>
        </>
      }
    >
      <div className="form">
        <p className="hint">
          {t("같은 변수의 기간별 열(예: 어획량_2022, 어획량_2023)을 한 묶음으로 지정함. 주제도에서 기간을 넘겨 보고, 시공간 분석(Moran 추이·기간별 LISA)에 씀. 프로젝트에 함께 저장됨.")}
        </p>
        <div className="row">
          <button onClick={() => void guess()}>{t("열 이름에서 자동으로 찾기")}</button>
          <button
            onClick={() =>
              setGroups([
                ...groups,
                { name: t("묶음{n}", { n: groups.length + 1 }), columns: cols.slice(0, 2), labels: cols.slice(0, 2).map(guessLabel) },
              ])
            }
            disabled={cols.length < 2}
          >
            + {t("직접 추가")}
          </button>
        </div>
        {groups.length === 0 && <p className="muted">{t("아직 묶음이 없음")}</p>}
        {groups.map((g, i) => (
          <fieldset key={i} className="group-box">
            <div className="row">
              <input
                value={g.name}
                onChange={(e) => update(i, { ...g, name: e.target.value })}
                aria-label={t("묶음 이름")}
                placeholder={t("묶음 이름")}
              />
              <div className="spacer" />
              <button className="link" onClick={() => setGroups(groups.filter((_, j) => j !== i))}>
                {t("묶음 삭제")}
              </button>
            </div>
            <table className="result-table compact">
              <thead>
                <tr>
                  <th>{t("기간 이름")}</th>
                  <th>{t("열")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {g.columns.map((c, k) => (
                  <tr key={k}>
                    <td>
                      <input
                        value={g.labels[k]}
                        onChange={(e) => update(i, { ...g, labels: g.labels.map((x, j) => (j === k ? e.target.value : x)) })}
                        aria-label={t("기간 이름")}
                        size={8}
                      />
                    </td>
                    <td>
                      <select
                        value={c}
                        onChange={(e) =>
                          update(i, {
                            ...g,
                            columns: g.columns.map((x, j) => (j === k ? e.target.value : x)),
                            labels: g.labels.map((x, j) => (j === k && x === guessLabel(c) ? guessLabel(e.target.value) : x)),
                          })
                        }
                        aria-label={t("열")}
                      >
                        {cols.map((name) => (
                          <option key={name} value={name}>
                            {name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="nowrap">
                      <button className="link" disabled={k === 0} onClick={() => update(i, move(g, k, -1))} title={t("위로")}>
                        ↑
                      </button>
                      <button
                        className="link"
                        disabled={k === g.columns.length - 1}
                        onClick={() => update(i, move(g, k, 1))}
                        title={t("아래로")}
                      >
                        ↓
                      </button>
                      <button
                        className="link"
                        onClick={() =>
                          update(i, {
                            ...g,
                            columns: g.columns.filter((_, j) => j !== k),
                            labels: g.labels.filter((_, j) => j !== k),
                          })
                        }
                        title={t("빼기")}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button
              onClick={() => {
                const next = cols.find((c) => !g.columns.includes(c)) ?? cols[0];
                update(i, { ...g, columns: [...g.columns, next], labels: [...g.labels, guessLabel(next)] });
              }}
            >
              + {t("기간 추가")}
            </button>
          </fieldset>
        ))}
      </div>
    </Modal>
  );
}

// ---- 시공간 분석 -------------------------------------------------------------------

export function TimeSeriesDialog({ datasetId }: { datasetId: string }) {
  const ds = useApp((s) => s.datasets[datasetId]);
  const runLisaTime = useApp((s) => s.runLisaTime);
  const runLocal = useApp((s) => s.runLocal);
  const showDialog = useApp((s) => s.showDialog);
  const busy = useApp((s) => s.busy);
  const fail = useApp((s) => s.fail);
  const groups = ds?.info.time_groups ?? [];
  const [groupName, setGroupName] = useState(groups[0]?.name ?? "");
  const [weightsId, setWeightsId] = useState(ds?.activeWeightsId ?? ds?.weights[0]?.id ?? "");
  const [permutations, setPermutations] = useState(999);
  const [alpha, setAlpha] = useState(0.05);
  const [correction, setCorrection] = useState<"none" | "fdr" | "bonferroni">("none");
  const [series, setSeries] = useState<MoranSeries | null>(null);
  const [running, setRunning] = useState(false);
  const group = groups.find((g) => g.name === groupName);
  const [from, setFrom] = useState(0);
  const [to, setTo] = useState(Math.max(0, (group?.columns.length ?? 1) - 1));
  useEffect(() => {
    setSeries(null);
    setFrom(0);
    setTo(Math.max(0, (group?.columns.length ?? 1) - 1));
  }, [groupName, group?.columns.length]);
  if (!ds) return null;

  if (groups.length === 0) {
    return (
      <Modal title={t("시공간 분석")} onClose={close} footer={<button onClick={close}>{t("닫기")}</button>}>
        <div className="notice-box">
          {t("시간 변수 묶음이 없음. 기간별 열을 묶거나, 긴 형태·기간별 파일을 기간별 자료로 바꾼 뒤 씀.")}
          <div className="row">
            <button className="link" onClick={() => showDialog({ kind: "timegroups", datasetId })}>
              {t("시간 변수 묶음…")}
            </button>
            <button className="link" onClick={() => showDialog({ kind: "reshape", datasetId })}>
              {t("기간별 자료 만들기…")}
            </button>
          </div>
        </div>
      </Modal>
    );
  }

  const moranTrend = async () => {
    setRunning(true);
    try {
      setSeries(await engine.moranSeries(datasetId, { group: groupName, weights_id: weightsId, permutations }));
    } catch (err) {
      fail(err);
    } finally {
      setRunning(false);
    }
  };

  const lisaTime = async () => {
    const ok = await runLisaTime(datasetId, {
      group: groupName,
      weights_id: weightsId,
      permutations,
      alpha,
      correction,
      prefix: "TLISA",
    });
    if (ok) close();
  };

  const diffLisa = async () => {
    if (!group) return;
    const ok = await runLocal(datasetId, {
      method: "lisa",
      column: group.columns[to],
      column_base: group.columns[from],
      weights_id: weightsId,
      permutations,
      alpha,
      correction,
      prefix: `DLISA_${group.labels[from]}_${group.labels[to]}`,
    });
    if (ok) close();
  };

  const p = (v: number | null) => (v === null ? "–" : v < 0.001 ? v.toExponential(1) : v.toFixed(3));

  return (
    <Modal title={t("시공간 분석")} onClose={close} footer={<button onClick={close}>{t("닫기")}</button>}>
      <div className="form">
        <div className="grid2">
          <label>
            {t("시간 변수 묶음")}
            <select value={groupName} onChange={(e) => setGroupName(e.target.value)} aria-label={t("시간 변수 묶음")}>
              {groups.map((g) => (
                <option key={g.name} value={g.name}>
                  {g.name} ({g.labels[0]}–{g.labels[g.labels.length - 1]})
                </option>
              ))}
            </select>
          </label>
          <PermutationSelect value={permutations} onChange={setPermutations} />
        </div>
        {ds.weights.length ? <WeightsSelect ds={ds} value={weightsId} onChange={setWeightsId} /> : <NoWeights datasetId={ds.info.id} />}
        <div className="grid2">
          <label>
            {t("유의수준 α")}
            <select value={alpha} onChange={(e) => setAlpha(Number(e.target.value))} aria-label={t("유의수준")}>
              {[0.1, 0.05, 0.01, 0.001].map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("다중검정 보정")}
            <select value={correction} onChange={(e) => setCorrection(e.target.value as typeof correction)} aria-label={t("다중검정 보정")}>
              <option value="none">{t("없음")}</option>
              <option value="fdr">FDR (Benjamini-Hochberg)</option>
              <option value="bonferroni">Bonferroni</option>
            </select>
          </label>
        </div>

        <h4>{t("1. 전역 Moran's I 추이")}</h4>
        <div className="row">
          <button onClick={() => void moranTrend()} disabled={!weightsId || running || !!busy}>
            {running ? t("계산 중…") : t("기간별 Moran's I 계산")}
          </button>
        </div>
        {series && (
          <>
            <TrendLine rows={series.rows.map((r) => ({ label: r.label, value: r.I, p: r.p_sim }))} />
            <table className="result-table compact" data-testid="moran-series">
              <thead>
                <tr>
                  <th>{t("기간")}</th>
                  <th>Moran&apos;s I</th>
                  <th>z</th>
                  <th>{t("유사 p")}</th>
                  <th>{t("평균")}</th>
                </tr>
              </thead>
              <tbody>
                {series.rows.map((r) => (
                  <tr key={r.label}>
                    <td>{r.label}</td>
                    <td>{r.I.toFixed(4)}</td>
                    <td>{r.z_sim === null ? "–" : r.z_sim.toFixed(2)}</td>
                    <td>{p(r.p_sim)}</td>
                    <td>{r.mean.toPrecision(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        <h4>{t("2. 기간별 LISA와 군집 전이")}</h4>
        <p className="hint">
          {t("기간마다 LISA를 계산해 TLISA_<기간>_CL 열과 군집이 바뀐 횟수(TLISA_CHG)를 저장하고, 결과 패널에 군집 전이표를 보여줌.")}
        </p>
        <div className="row">
          <button className="primary" onClick={() => void lisaTime()} disabled={!weightsId || !!busy}>
            {t("기간별 LISA 실행")}
          </button>
        </div>

        <h4>{t("3. 두 기간의 차분 LISA")}</h4>
        <p className="hint">{t("변화량(뒤 기간 − 앞 기간)이 주변과 함께 크게 늘거나 준 곳을 찾음 (GeoDa 차분 Moran과 같음).")}</p>
        {group && (
          <div className="grid2">
            <label>
              {t("앞 기간")}
              <select value={from} onChange={(e) => setFrom(Number(e.target.value))} aria-label={t("앞 기간")}>
                {group.labels.map((lb, i) => (
                  <option key={lb} value={i}>
                    {lb}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("뒤 기간")}
              <select value={to} onChange={(e) => setTo(Number(e.target.value))} aria-label={t("뒤 기간")}>
                {group.labels.map((lb, i) => (
                  <option key={lb} value={i}>
                    {lb}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
        <div className="row">
          <button onClick={() => void diffLisa()} disabled={!weightsId || from === to || !!busy}>
            {t("차분 LISA 실행")}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/** 기간별 값 꺾은선 (유의한 기간은 채운 점, 아니면 빈 점) */
export function TrendLine({ rows }: { rows: { label: string; value: number; p?: number | null }[] }) {
  const w = 420;
  const h = 120;
  const pad = { l: 40, r: 12, t: 10, b: 22 };
  const vals = rows.map((r) => r.value);
  let lo = Math.min(0, ...vals);
  let hi = Math.max(...vals);
  if (hi - lo < 1e-9) hi = lo + 1;
  const span = hi - lo;
  lo -= span * 0.05;
  hi += span * 0.05;
  const x = (i: number) => pad.l + (rows.length === 1 ? 0 : (i / (rows.length - 1)) * (w - pad.l - pad.r));
  const y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo)) * (h - pad.t - pad.b);
  return (
    <svg className="trend" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={t("기간별 추이")}>
      <line x1={pad.l} x2={w - pad.r} y1={y(0)} y2={y(0)} className="axis zero" />
      <text x={pad.l - 4} y={y(hi) + 4} textAnchor="end" className="tick">
        {hi.toPrecision(2)}
      </text>
      <text x={pad.l - 4} y={y(lo)} textAnchor="end" className="tick">
        {lo.toPrecision(2)}
      </text>
      <polyline points={rows.map((r, i) => `${x(i)},${y(r.value)}`).join(" ")} className="line" />
      {rows.map((r, i) => (
        <g key={r.label}>
          <circle cx={x(i)} cy={y(r.value)} r={4} className={r.p !== undefined && r.p !== null && r.p <= 0.05 ? "dot sig" : "dot"}>
            <title>{`${r.label}: ${r.value.toFixed(4)}`}</title>
          </circle>
          <text x={x(i)} y={h - 6} textAnchor="middle" className="tick">
            {r.label}
          </text>
        </g>
      ))}
    </svg>
  );
}

// ---- 기간별 자료 만들기 (긴 형태 → 넓은 형태, 기간별 파일 잇기) ----------------------------

export function ReshapeDialog({ datasetId }: { datasetId: string }) {
  const datasets = useApp((s) => s.datasets);
  const order = useApp((s) => s.order);
  const reshape = useApp((s) => s.reshape);
  const mergePeriods = useApp((s) => s.mergePeriods);
  const busy = useApp((s) => s.busy);
  const ds = datasets[datasetId];
  const [mode, setMode] = useState<"pivot" | "merge">("pivot");
  const allCols = ds?.info.columns.map((c) => c.name) ?? [];
  const [idCol, setIdCol] = useState(allCols[0] ?? "");
  const [timeCol, setTimeCol] = useState(
    allCols.find((c) => /연도|년도|year|date|기간|시기/i.test(c)) ?? allCols[1] ?? "",
  );
  const [values, setValues] = useState<string[]>([]);
  // 기간별 파일: 첫 행이 기준(지오메트리) 자료
  const [parts, setParts] = useState(() =>
    order
      .filter((id) => datasets[id])
      .slice(0, 6)
      .map((id) => ({ dataset_id: id, id_column: datasets[id].info.columns[0]?.name ?? "", label: guessLabel(datasets[id].info.name) })),
  );
  if (!ds) return null;

  const toggle = (c: string) => setValues(values.includes(c) ? values.filter((x) => x !== c) : [...values, c]);
  // 기간별 파일에서 고를 수 있는 값 열: 모든 자료에 있는 숫자 열
  const commonNumeric =
    parts.length === 0
      ? []
      : numericCols(datasets[parts[0].dataset_id]).filter((c) =>
          parts.every((p) => numericCols(datasets[p.dataset_id]).includes(c)),
        );
  const candidates = mode === "pivot" ? numericCols(ds).filter((c) => c !== idCol && c !== timeCol) : commonNumeric;
  const shown = values.filter((v) => candidates.includes(v));

  const submit = async () => {
    const base = mode === "pivot" ? ds : datasets[parts[0]?.dataset_id];
    if (!base) return;
    const path = await pickSavePath(
      [{ name: "GeoPackage", extensions: ["gpkg"] }],
      t("기간별 자료 저장 위치"),
      `${dirname(base.info.path)}/${t("{name}_기간별.gpkg", { name: base.info.name })}`,
    );
    if (!path) return;
    const ok =
      mode === "pivot"
        ? await reshape("pivot", { dataset_id: datasetId, id_column: idCol, time_column: timeCol, value_columns: shown, path })
        : await mergePeriods({ parts, value_columns: shown, path });
    if (ok) close();
  };

  const labelsOk = new Set(parts.map((p) => p.label.trim())).size === parts.length && parts.every((p) => p.label.trim());

  return (
    <Modal
      title={t("기간별 자료 만들기")}
      onClose={close}
      footer={
        <>
          <button onClick={close}>{t("취소")}</button>
          <button
            className="primary"
            onClick={() => void submit()}
            disabled={
              shown.length === 0 ||
              !!busy ||
              (mode === "pivot" ? !idCol || !timeCol || idCol === timeCol : parts.length < 2 || !labelsOk)
            }
          >
            {t("만들기…")}
          </button>
        </>
      }
    >
      <div className="form">
        <div className="segmented" role="group" aria-label={t("자료 형태")}>
          <button className={mode === "pivot" ? "on" : ""} onClick={() => setMode("pivot")}>
            {t("긴 형태 (ID·기간·값 행)")}
          </button>
          <button className={mode === "merge" ? "on" : ""} onClick={() => setMode("merge")}>
            {t("기간별 파일 잇기")}
          </button>
        </div>
        {mode === "pivot" ? (
          <>
            <p className="hint">
              {t("같은 지점·격자가 기간마다 한 행씩 반복되는 '{name}'을 ID당 한 행, 기간별 열(값_2022, 값_2023 …)로 바꿈. 지오메트리는 ID의 첫 행 것을 씀.", {
                name: ds.info.name,
              })}
            </p>
            <div className="grid2">
              <label>
                {t("ID 열 (지점·격자 구분)")}
                <select value={idCol} onChange={(e) => setIdCol(e.target.value)} aria-label={t("ID 열")}>
                  {allCols.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
              <label>
                {t("기간 열 (연도 등)")}
                <select value={timeCol} onChange={(e) => setTimeCol(e.target.value)} aria-label={t("기간 열")}>
                  {allCols.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
            </div>
          </>
        ) : (
          <>
            <p className="hint">
              {t("기간별로 나뉜 자료(2022.shp, 2023.shp …)를 공통 ID로 이어 붙임. 첫 줄 자료의 지오메트리를 씀. 필요한 자료를 먼저 모두 열어 둠.")}
            </p>
            <table className="result-table compact">
              <thead>
                <tr>
                  <th>{t("자료")}</th>
                  <th>{t("ID 열")}</th>
                  <th>{t("기간 이름")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {parts.map((p, i) => {
                  const pds = datasets[p.dataset_id];
                  return (
                    <tr key={i}>
                      <td>
                        <select
                          value={p.dataset_id}
                          onChange={(e) =>
                            setParts(
                              parts.map((x, j) =>
                                j === i
                                  ? {
                                      dataset_id: e.target.value,
                                      id_column: datasets[e.target.value]?.info.columns.some((c) => c.name === x.id_column)
                                        ? x.id_column
                                        : (datasets[e.target.value]?.info.columns[0]?.name ?? ""),
                                      label: guessLabel(datasets[e.target.value]?.info.name ?? ""),
                                    }
                                  : x,
                              ),
                            )
                          }
                          aria-label={t("자료")}
                        >
                          {order.map((id) => (
                            <option key={id} value={id}>
                              {datasets[id]?.info.name}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select
                          value={p.id_column}
                          onChange={(e) => setParts(parts.map((x, j) => (j === i ? { ...x, id_column: e.target.value } : x)))}
                          aria-label={t("ID 열")}
                        >
                          {pds?.info.columns.map((c) => (
                            <option key={c.name}>{c.name}</option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          value={p.label}
                          size={8}
                          onChange={(e) => setParts(parts.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))}
                          aria-label={t("기간 이름")}
                        />
                      </td>
                      <td>
                        <button className="link" onClick={() => setParts(parts.filter((_, j) => j !== i))} title={t("빼기")}>
                          ✕
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div>
              <button
                onClick={() => {
                  const id = order.find((x) => !parts.some((p) => p.dataset_id === x)) ?? order[0];
                  if (!id) return;
                  setParts([
                    ...parts,
                    { dataset_id: id, id_column: parts[0]?.id_column ?? "", label: guessLabel(datasets[id].info.name) },
                  ]);
                }}
              >
                + {t("자료 추가")}
              </button>
            </div>
            {!labelsOk && <p className="hint warn-text">{t("기간 이름은 비어 있거나 겹치면 안 됨")}</p>}
          </>
        )}
        <div className="field-label">{t("기간별 열로 만들 값 (숫자 열)")}</div>
        <div className="check-list">
          {candidates.length === 0 && <span className="muted">{t("(해당 열 없음)")}</span>}
          {candidates.map((c) => (
            <label key={c} className="check">
              <input type="checkbox" checked={values.includes(c)} onChange={() => toggle(c)} />
              {c}
            </label>
          ))}
        </div>
        <p className="hint">{t("결과는 GeoPackage로 저장해 새 레이어로 열고, 값마다 시간 변수 묶음을 자동으로 만듦.")}</p>
      </div>
    </Modal>
  );
}

// ---- 분석 보고서 내보내기 ------------------------------------------------------------

export function ReportDialog() {
  const datasets = useApp((s) => s.datasets);
  const order = useApp((s) => s.order);
  const activeId = useApp((s) => s.activeId);
  const charts = useApp((s) => s.charts);
  const basemap = useApp((s) => s.basemap);
  const fail = useApp((s) => s.fail);
  const notify = useApp((s) => s.notify);
  const active = activeId ? datasets[activeId] : undefined;
  const [title, setTitle] = useState(t("{name} 분석 보고서", { name: active?.info.name ?? "GeoStat" }));
  const [format, setFormat] = useState<"html" | "docx">("docx");
  const [scope, setScope] = useState<"active" | "all">("active");
  const [withMap, setWithMap] = useState(true);
  const [withMoran, setWithMoran] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const morans = charts.filter((c) => c.kind === "moran" && c.moran && (scope === "all" || c.datasetId === activeId));

  const submit = async () => {
    const ext = format === "docx" ? "docx" : "html";
    const base = active ?? datasets[order[0]];
    const path = await pickSavePath(
      [{ name: format === "docx" ? t("Word 문서") : "HTML", extensions: [ext] }],
      t("보고서 저장"),
      base ? `${dirname(base.info.path)}/${title.replace(/[\\/:*?"<>|]/g, "_")}.${ext}` : undefined,
    );
    if (!path) return;
    setSaving(true);
    try {
      const images: { data: string; caption: string }[] = [];
      if (withMap) {
        try {
          const png = renderMapPng({
            legend:
              active?.theme && active.visible
                ? { title: `${active.info.name} · ${active.theme.column}`, theme: active.theme }
                : null,
            attribution: basemap !== "none" ? "© OpenStreetMap contributors · OpenFreeMap" : null,
          });
          images.push({ data: png, caption: active?.theme ? `${active.info.name} · ${active.theme.column}` : t("지도") });
        } catch {
          notify(t("지도를 그림으로 만들지 못해 지도 없이 저장함"));
        }
      }
      const ids = scope === "all" ? order : activeId ? [activeId] : [];
      const r = await engine.exportReport({
        path,
        format,
        title,
        datasets: ids.map((id) => ({ dataset_id: id })),
        images,
        morans: withMoran
          ? morans.map((c) => ({
              dataset: datasets[c.datasetId]?.info.name ?? "",
              column: c.moran!.column + (c.moran!.column_y ? ` × ${c.moran!.column_y}` : ""),
              weights: c.moran!.weights,
              I: c.moran!.I,
              expected: c.moran!.expected,
              z_sim: c.moran!.z_sim,
              p_sim: c.moran!.p_sim,
              permutations: c.moran!.permutations,
            }))
          : [],
      });
      setSaved(r.path);
      notify(t("보고서를 저장함: {path}", { path: r.path }));
    } catch (err) {
      fail(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={t("분석 보고서 내보내기")}
      onClose={close}
      footer={
        <>
          {saved && <button onClick={() => void revealInFolder(saved).catch(fail)}>{t("폴더에서 보기")}</button>}
          <button onClick={close}>{t("닫기")}</button>
          <button className="primary" onClick={() => void submit()} disabled={saving || order.length === 0}>
            {saving ? t("저장 중…") : t("저장…")}
          </button>
        </>
      }
    >
      <div className="form">
        <p className="hint">
          {t("자료 정보, 공간가중치, 시간 변수 묶음, 실행한 분석(국지 통계·회귀·군집·점 집계·비율 등)의 결과표와 현재 지도를 한 문서로 모음. 엔진이 만드는 표와 설명은 한국어로 나옴.")}
        </p>
        <label>
          {t("제목")}
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <div className="grid2">
          <label>
            {t("형식")}
            <select value={format} onChange={(e) => setFormat(e.target.value as typeof format)} aria-label={t("형식")}>
              <option value="docx">{t("Word 문서 (.docx)")}</option>
              <option value="html">{t("HTML (.html)")}</option>
            </select>
          </label>
          <label>
            {t("범위")}
            <select value={scope} onChange={(e) => setScope(e.target.value as typeof scope)} aria-label={t("범위")}>
              <option value="active">{t("활성 레이어만")}</option>
              <option value="all">{t("모든 레이어")}</option>
            </select>
          </label>
        </div>
        <label className="check">
          <input type="checkbox" checked={withMap} onChange={(e) => setWithMap(e.target.checked)} />
          {t("현재 지도 그림 넣기 (범례 포함)")}
        </label>
        <label className="check">
          <input type="checkbox" checked={withMoran} onChange={(e) => setWithMoran(e.target.checked)} disabled={morans.length === 0} />
          {t("차트 패널의 Moran's I 결과 넣기 ({n}개)", { n: morans.length })}
        </label>
        {saved && <p className="hint">{t("저장함: {path}", { path: saved })}</p>}
      </div>
    </Modal>
  );
}

