import { useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api";
import type { BatchResponse, BatchRow, DriftResponse, ModelInfo, Status } from "../types";
import { CLASS_COLOR, CLASS_LABEL, StatusPill, pct } from "./ui";

type SortKey = "row" | "failure_probability" | "rul_minutes";
const PAGE = 100;

const TEMPLATE_ROWS = [
  { Type: "M", "Air temperature": 298.1, "Process temperature": 308.6, "Rotational speed": 1551, Torque: 42.8, "Tool wear": 10 },
  { Type: "L", "Air temperature": 302.5, "Process temperature": 310.4, "Rotational speed": 1300, Torque: 55.0, "Tool wear": 80 },
  { Type: "L", "Air temperature": 299.0, "Process temperature": 309.5, "Rotational speed": 2800, Torque: 8.0, "Tool wear": 50 },
  { Type: "H", "Air temperature": 300.2, "Process temperature": 310.0, "Rotational speed": 1420, Torque: 48.5, "Tool wear": 215 },
];

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

const templates = {
  csv: () => {
    const cols = Object.keys(TEMPLATE_ROWS[0]);
    const lines = [cols.join(","), ...TEMPLATE_ROWS.map((r) => cols.map((c) => r[c as keyof typeof r]).join(","))];
    download("readings_template.csv", lines.join("\n") + "\n", "text/csv");
  },
  json: () => download("readings_template.json", JSON.stringify({ readings: TEMPLATE_ROWS }, null, 2), "application/json"),
};

export default function FleetPanel({ info }: { info: ModelInfo | null }) {
  const [res, setRes] = useState<BatchResponse | null>(null);
  const [drift, setDrift] = useState<DriftResponse | null>(null);
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [filter, setFilter] = useState<Status | "all">("alarm");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "failure_probability", desc: true });
  const [limit, setLimit] = useState(PAGE);
  const input = useRef<HTMLInputElement>(null);

  const upload = async (file: File) => {
    setBusy(true); setError(null); setFileName(file.name); setDrift(null);
    try {
      const [r, d] = await Promise.all([api.predictFile(file), api.driftFile(file).catch(() => null)]);
      setRes(r); setDrift(d); setLimit(PAGE);
      setFilter(r.n_alarms > 0 ? "alarm" : "all");
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, (e as Error).message));
      setRes(null);
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

  const maxRows = info?.limits.max_batch_rows ?? 20000;
  const maxMb = info?.limits.max_upload_mb ?? 5;

  return (
    <>
      <div className="page-head">
        <h1>Fleet scoring</h1>
        <p>Upload a <b>CSV</b> (columns: Type, Air temperature, Process temperature, Rotational speed, Torque, Tool wear;
          the raw AI4I file works as-is) or a <b>JSON</b> list of readings. Every row is validated: a wrong type, an
          out-of-range value or a bad file is rejected with the exact row and field.</p>
      </div>

      <div className={`drop ${over ? "over" : ""}`} role="button" tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) upload(f); }}>
        <strong>{busy ? `Scoring ${fileName}…` : "Drop a .csv or .json file here, or click to choose"}</strong>
        <p>{res ? `Last file: ${fileName}` : `Up to ${maxRows.toLocaleString()} rows · ${maxMb} MB`}</p>
        <input ref={input} type="file" accept=".csv,.json,text/csv,application/json" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
      </div>
      <div className="toolbar" style={{ marginTop: 10 }}>
        <span className="note">Need a starting point?</span>
        <button className="btn" onClick={templates.csv}>CSV template</button>
        <button className="btn" onClick={templates.json}>JSON template</button>
      </div>

      {error && <ErrorPanel error={error} />}

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

          {drift && <DriftCard drift={drift} />}

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

function ErrorPanel({ error }: { error: ApiError }) {
  return (
    <div className="error-panel" role="alert">
      <div className="error-head">
        <strong>{error.status === 400 ? "File rejected" : error.status === 413 ? "File too large" : "Request failed"}</strong>
        {error.status > 0 && <span className="tag breach">HTTP {error.status}</span>}
      </div>
      <p style={{ margin: "6px 0 0" }}>{error.message}</p>
      {error.details.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 10 }}>
          <table>
            <thead><tr><th>Row</th><th>Field</th><th>Problem</th></tr></thead>
            <tbody>
              {error.details.map((d, i) => (
                <tr key={i}><td className="num">{d.row ?? "–"}</td><td>{d.field}</td><td>{d.message}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error.requestId && <p className="note" style={{ margin: "8px 0 0" }}>Request ID: <code>{error.requestId}</code></p>}
    </div>
  );
}

const DRIFT_COLOR = { stable: "var(--good)", moderate: "var(--warning)", significant: "var(--critical)" } as const;
const DRIFT_TAG = { stable: "safe", moderate: "near", significant: "breach" } as const;

function DriftCard({ drift }: { drift: DriftResponse }) {
  if (drift.status === "insufficient_data") {
    return <div className="card note" style={{ marginBottom: 18 }}>Data drift: at least {drift.min_samples} rows are needed for a reliable check ({drift.n_samples} uploaded).</div>;
  }
  const scale = Math.max(0.3, ...drift.sensors.map((s) => s.psi));
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <h2>Data drift vs training data <span className={`tag ${DRIFT_TAG[drift.status]}`} style={{ marginLeft: 8, textTransform: "none", letterSpacing: 0 }}>{drift.status}</span></h2>
      <p className="sub">Population Stability Index per sensor · &lt; 0.1 stable · 0.1–0.25 moderate · ≥ 0.25 significant (predictions may be unreliable)</p>
      {drift.sensors.map((s) => (
        <div className="prob-row" key={s.sensor} style={{ gridTemplateColumns: "150px 1fr 150px" }}>
          <span className="name">{s.sensor}</span>
          <div className="hbar" style={{ position: "relative" }}>
            <div className="hbar-fill" style={{ width: `${(s.psi / scale) * 100}%`, background: DRIFT_COLOR[s.status] }} />
            <div className="meter-mark" style={{ left: `${(0.25 / scale) * 100}%`, top: -2, bottom: -2, width: 1, background: "var(--muted)" }} />
          </div>
          <span className="val num">PSI {s.psi.toFixed(3)} · μ {s.current_mean.toFixed(1)}</span>
        </div>
      ))}
    </div>
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
