import { useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { BatchResponse, BatchRow, Status } from "../types";
import { CLASS_COLOR, CLASS_LABEL, StatusPill, pct } from "./ui";

type SortKey = "row" | "failure_probability" | "rul_minutes";
const PAGE = 100;

export default function FleetPanel() {
  const [res, setRes] = useState<BatchResponse | null>(null);
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [filter, setFilter] = useState<Status | "all">("alarm");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "failure_probability", desc: true });
  const [limit, setLimit] = useState(PAGE);
  const input = useRef<HTMLInputElement>(null);

  const upload = async (file: File) => {
    setBusy(true); setError(null); setFileName(file.name);
    try {
      const r = await api.predictCsv(file);
      setRes(r); setLimit(PAGE);
      setFilter(r.n_alarms > 0 ? "alarm" : "all");
    } catch (e) {
      setError((e as Error).message); setRes(null);
    } finally {
      setBusy(false);
    }
  };

  const rows = useMemo(() => {
    if (!res) return [];
    const f = filter === "all" ? res.rows : res.rows.filter((r) => r.status === filter);
    const dir = sort.desc ? -1 : 1;
    return [...f].sort((a, b) => dir * (a[sort.key] - b[sort.key]));
  }, [res, filter, sort]);

  const header = (key: SortKey, label: string, cls = "r") => (
    <th className={cls} onClick={() => setSort((s) => ({ key, desc: s.key === key ? !s.desc : true }))}
      aria-sort={sort.key === key ? (sort.desc ? "descending" : "ascending") : "none"}>
      {label}{sort.key === key ? (sort.desc ? " ↓" : " ↑") : ""}
    </th>
  );

  return (
    <>
      <div className="page-head">
        <h1>Fleet scoring</h1>
        <p>Upload a CSV of machine snapshots (columns: Type, Air temperature, Process temperature, Rotational speed,
          Torque, Tool wear). Extra columns are ignored, so the raw AI4I file works as-is.</p>
      </div>

      <div className={`drop ${over ? "over" : ""}`} role="button" tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) upload(f); }}>
        <strong>{busy ? `Scoring ${fileName}…` : "Drop a CSV here or click to choose a file"}</strong>
        <p>{res ? `Last file: ${fileName}` : "Up to 20,000 rows"}</p>
        <input ref={input} type="file" accept=".csv,text/csv" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
      </div>

      {error && <div className="error" style={{ marginTop: 14 }}>{error}</div>}

      {res && (
        <div style={{ marginTop: 18 }}>
          <div className="tiles num">
            <div className="tile"><div className="stat-label">Machines scored</div><div className="stat-value">{res.n_rows.toLocaleString()}</div></div>
            <div className="tile"><div className="stat-label">Alarms</div><div className="stat-value" style={{ color: "var(--critical)" }}>{res.n_alarms.toLocaleString()}</div><div className="hint">{pct(res.n_alarms / res.n_rows, 2)} of fleet</div></div>
            <div className="tile"><div className="stat-label">Tool advisories</div><div className="stat-value">{res.n_advisories.toLocaleString()}</div><div className="hint">wear ≥ 200 min, no alarm</div></div>
            <div className="tile">
              <div className="stat-label">Alarms by failure mode</div>
              <FailureMix counts={res.by_failure} total={res.n_alarms} />
            </div>
          </div>

          <div className="toolbar">
            <label htmlFor="flt" className="note">Show</label>
            <select id="flt" value={filter} onChange={(e) => { setFilter(e.target.value as Status | "all"); setLimit(PAGE); }}>
              <option value="alarm">Alarms ({res.n_alarms})</option>
              <option value="advisory">Advisories ({res.n_advisories})</option>
              <option value="ok">Healthy ({res.n_rows - res.n_alarms - res.n_advisories})</option>
              <option value="all">All ({res.n_rows})</option>
            </select>
            <span className="note">{rows.length.toLocaleString()} machines · click a column to sort</span>
          </div>

          <div className="table-wrap">
            <table className="num">
              <thead>
                <tr>
                  {header("row", "Row #", "")}
                  <th>Status</th>
                  <th>Predicted failure</th>
                  {header("failure_probability", "P(failure)")}
                  {header("rul_minutes", "RUL (min)")}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, limit).map((r: BatchRow) => (
                  <tr key={r.row}>
                    <td>{r.row + 1}</td>
                    <td><StatusPill status={r.status} /></td>
                    <td>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
                        <span style={{ width: 9, height: 9, borderRadius: 2, background: CLASS_COLOR[r.predicted_failure] }} />
                        {CLASS_LABEL[r.predicted_failure]}
                      </span>
                    </td>
                    <td className="r">{pct(r.failure_probability)}</td>
                    <td className="r">{Math.round(r.rul_minutes)}</td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={5} className="empty">No machines in this category</td></tr>}
              </tbody>
            </table>
          </div>
          {rows.length > limit && (
            <div style={{ textAlign: "center", marginTop: 12 }}>
              <button className="btn" onClick={() => setLimit((l) => l + PAGE * 5)}>Show more ({(rows.length - limit).toLocaleString()} remaining)</button>
            </div>
          )}
        </div>
      )}
    </>
  );
}

function FailureMix({ counts, total }: { counts: Record<string, number>; total: number }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (!total) return <div className="hint">No alarms</div>;
  return (
    <>
      <div style={{ display: "flex", height: 12, borderRadius: 4, overflow: "hidden", gap: 2, margin: "10px 0 8px" }}>
        {entries.map(([k, v]) => (
          <div key={k} title={`${CLASS_LABEL[k]}: ${v}`} style={{ flex: v, background: CLASS_COLOR[k] }} />
        ))}
      </div>
      <div className="legend" style={{ marginTop: 0 }}>
        {entries.map(([k, v]) => <span key={k}><i style={{ background: CLASS_COLOR[k] }} />{k} {v}</span>)}
      </div>
    </>
  );
}
