import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { MachineType, ModelInfo, Prediction, Reading } from "../types";
import { CLASS_COLOR, CLASS_LABEL, StatusIcon, pct } from "./ui";

const DEFAULT: Reading = {
  type: "M", air_temperature: 300.0, process_temperature: 310.0,
  rotational_speed: 1500, torque: 40.0, tool_wear: 100,
};

type NumKey = Exclude<keyof Reading, "type">;
const FIELDS: { key: NumKey; label: string; unit: string; step: number; range: string; fallback: [number, number] }[] = [
  { key: "air_temperature", label: "Air temperature", unit: "K", step: 0.1, range: "Air temperature", fallback: [295, 305] },
  { key: "process_temperature", label: "Process temperature", unit: "K", step: 0.1, range: "Process temperature", fallback: [305, 314] },
  { key: "rotational_speed", label: "Rotational speed", unit: "rpm", step: 1, range: "Rotational speed", fallback: [1150, 2900] },
  { key: "torque", label: "Torque", unit: "Nm", step: 0.1, range: "Torque", fallback: [3, 77] },
  { key: "tool_wear", label: "Tool wear", unit: "min", step: 1, range: "Tool wear", fallback: [0, 255] },
];

const PRESETS: { kind: string; label: string; color: string }[] = [
  { kind: "healthy", label: "Healthy", color: "var(--c-none)" },
  { kind: "HDF", label: "Heat failure", color: "var(--c-hdf)" },
  { kind: "PWF", label: "Power failure", color: "var(--c-pwf)" },
  { kind: "OSF", label: "Overstrain", color: "var(--c-osf)" },
  { kind: "TWF", label: "Tool wear", color: "var(--c-twf)" },
  { kind: "random", label: "Random", color: "var(--muted)" },
];

const FEATURE_LABEL: Record<string, string> = {
  air_temp: "Air temp", process_temp: "Process temp", rpm: "Speed", torque: "Torque", tool_wear: "Tool wear",
  temp_diff: "ΔT (process − air)", power_W: "Power", wear_x_torque: "Wear × torque", osf_margin: "Overstrain margin",
  power_margin_low: "Margin to min power", power_margin_high: "Margin to max power", hdf_temp_margin: "ΔT margin",
  hdf_rpm_margin: "Speed margin (HDF)", tool_wear_margin: "Wear margin", type_ord: "Quality type",
};

export default function DiagnosePanel({ info }: { info: ModelInfo | null }) {
  const [reading, setReading] = useState<Reading>(DEFAULT);
  const [pred, setPred] = useState<Prediction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ctrl = useRef<AbortController | null>(null);

  // Live scoring, debounced while sliders move
  useEffect(() => {
    const t = setTimeout(() => {
      ctrl.current?.abort();
      ctrl.current = new AbortController();
      setBusy(true);
      api.predict(reading, ctrl.current.signal)
        .then((p) => { setPred(p); setError(null); })
        .catch((e: Error) => { if (e.name !== "AbortError") setError(e.message); })
        .finally(() => setBusy(false));
    }, 180);
    return () => clearTimeout(t);
  }, [reading]);

  const loadSample = async (kind: string) => {
    try { setReading(await api.sample(kind)); } catch (e) { setError((e as Error).message); }
  };

  const set = (k: NumKey, v: number) => setReading((r) => ({ ...r, [k]: v }));
  const dT = reading.process_temperature - reading.air_temperature;
  const power = (reading.torque * reading.rotational_speed * 2 * Math.PI) / 60;

  return (
    <>
      <div className="page-head">
        <h1>Machine diagnosis</h1>
        <p>Set the sensor readings or load a real machine from the AI4I dataset. The model raises an alarm only when the
          failure probability is above the threshold that keeps the false-alarm rate (FDR) low.</p>
      </div>
      <div className="grid-diagnose">
        <section className="card" aria-label="Sensor readings">
          <h2>Sensor readings</h2>
          <div className="presets">
            {PRESETS.map((p) => (
              <button key={p.kind} className="chip" onClick={() => loadSample(p.kind)} title={`Load a real ${p.label.toLowerCase()} machine`}>
                <span className="sw" style={{ background: p.color }} />{p.label}
              </button>
            ))}
          </div>
          <div className="field">
            <div className="field-head"><label>Product quality</label></div>
            <div className="segmented" role="group" aria-label="Product quality">
              {(["L", "M", "H"] as MachineType[]).map((t) => (
                <button key={t} aria-pressed={reading.type === t} onClick={() => setReading((r) => ({ ...r, type: t }))}>
                  {t === "L" ? "Low" : t === "M" ? "Medium" : "High"}
                </button>
              ))}
            </div>
          </div>
          {FIELDS.map((f) => {
            const r = info?.sensor_ranges[f.range];
            const [min, max] = r ? [Math.floor(r.min), Math.ceil(r.max)] : f.fallback;
            return (
              <div className="field" key={f.key}>
                <div className="field-head">
                  <label htmlFor={f.key}>{f.label}<span className="unit">{f.unit}</span></label>
                  <input type="number" className="num" step={f.step} value={reading[f.key]}
                    onChange={(e) => e.target.value !== "" && set(f.key, Number(e.target.value))} aria-label={`${f.label} value`} />
                </div>
                <input id={f.key} type="range" min={min} max={max} step={f.step} value={reading[f.key]}
                  onChange={(e) => set(f.key, Number(e.target.value))} />
              </div>
            );
          })}
          <div className="derived num">
            <span>ΔT <b>{dT.toFixed(1)} K</b></span>
            <span>Power <b>{Math.round(power).toLocaleString()} W</b></span>
            <span>Strain <b>{Math.round(reading.tool_wear * reading.torque).toLocaleString()}</b></span>
          </div>
        </section>

        <section className={busy && !pred ? "loading" : ""} aria-live="polite">
          {error && <div className="error">{error}</div>}
          {pred ? <Result pred={pred} /> : <div className="card empty">Scoring…</div>}
        </section>
      </div>
    </>
  );
}

function Result({ pred }: { pred: Prediction }) {
  const title = pred.status === "alarm"
    ? `${CLASS_LABEL[pred.predicted_failure]} failure predicted`
    : pred.status === "advisory" ? "Tool replacement advised" : "Operating normally";
  const text = pred.status === "alarm"
    ? `Stop and inspect: the failure probability is above the ${pct(pred.threshold, 0)} alarm threshold.`
    : pred.status === "advisory"
      ? "No imminent failure, but tool wear has entered the 200–240 min window where tool failures occur. Plan a replacement."
      : "No failure mechanism is close to its limit. No action needed.";
  const classes = Object.entries(pred.class_probabilities).sort((a, b) => b[1] - a[1]);
  const maxAbs = Math.max(...pred.drivers.map((d) => Math.abs(d.contribution)), 1e-6);

  return (
    <div className="result-grid">
      <div className={`banner ${pred.status} span-2`}>
        <div className="banner-icon"><StatusIcon status={pred.status} size={22} /></div>
        <div>
          <p className="banner-title">{title}</p>
          <p className="banner-text">{text}</p>
        </div>
        <div className="banner-stats num">
          <div><div className="stat-label">Failure probability</div><div className="stat-value">{pct(pred.failure_probability)}</div></div>
          <div><div className="stat-label">Remaining useful life</div><div className="stat-value">{Math.round(pred.rul_minutes)}<small>min</small></div></div>
        </div>
      </div>

      <div className="card">
        <h2>Alarm decision</h2>
        <div style={{ padding: "20px 0 6px" }}>
          <div className="meter">
            <div className="meter-fill" style={{ width: pct(pred.failure_probability), background: pred.alarm ? "var(--critical)" : "var(--accent)" }} />
            <div className="meter-mark" style={{ left: pct(pred.threshold) }}>
              <span className="meter-mark-label">threshold {pct(pred.threshold, 0)}</span>
            </div>
          </div>
        </div>
        <p className="note" style={{ marginTop: 12 }}>
          {pred.alarm
            ? <>Predicted failure mode: <b>{CLASS_LABEL[pred.predicted_failure]}</b>. </>
            : <>Highest-risk mode (still below threshold): <b>{CLASS_LABEL[pred.most_likely_failure]}</b>. </>}
          The threshold was tuned on cross-validation for FDR ≤ 2%, so an alarm here is almost always a real failure.
        </p>
        <h2 style={{ marginTop: 18 }}>Class probabilities</h2>
        {classes.map(([c, p]) => (
          <div className="prob-row" key={c}>
            <span className="name"><span className="sw" style={{ background: CLASS_COLOR[c] }} />{CLASS_LABEL[c]}</span>
            <div className="hbar"><div className="hbar-fill" style={{ width: pct(p), background: CLASS_COLOR[c] }} /></div>
            <span className="val num">{pct(p)}</span>
          </div>
        ))}
      </div>

      <div className="card">
        <h2>Physical failure mechanisms</h2>
        <p className="sub">How close each documented limit is (marker = limit)</p>
        {pred.mechanisms.map((m) => {
          const level = m.breached ? "breach" : m.utilisation >= 0.95 ? "near" : "safe";
          const fill = Math.min(m.utilisation / 1.5, 1);
          return (
            <div className="mech" key={m.mode}>
              <div className="mech-head">
                <span className="mech-name">
                  <span className="sw" style={{ width: 10, height: 10, borderRadius: 3, background: CLASS_COLOR[m.mode], display: "inline-block" }} />
                  {m.label}
                  <span className={`tag ${level}`}>{level === "breach" ? "Limit crossed" : level === "near" ? "Near limit" : "Safe"}</span>
                </span>
                <span className="mech-val num">{m.value.toLocaleString()} {m.unit}</span>
              </div>
              <div className="meter" style={{ height: 8 }}>
                <div className="meter-fill" style={{ width: `${fill * 100}%`, background: m.breached ? "var(--critical)" : level === "near" ? "var(--warning)" : "var(--axis)" }} />
                <div className="meter-mark" style={{ left: `${100 / 1.5}%` }} />
              </div>
              <div className="mech-meta" style={{ marginTop: 6 }}>Limit: {m.limit}</div>
            </div>
          );
        })}
      </div>

      {pred.drivers.length > 0 && (
        <div className="card span-2">
          <h2>Why this prediction: top drivers for “{CLASS_LABEL[pred.most_likely_failure]}”</h2>
          <p className="sub">SHAP contributions (log-odds) of the engineered features for this reading</p>
          {pred.drivers.map((d) => {
            const w = (Math.abs(d.contribution) / maxAbs) * 50;
            return (
              <div className="driver-row" key={d.feature}>
                <code title={d.feature}>{FEATURE_LABEL[d.feature] ?? d.feature}</code>
                <div className="driver-track">
                  <div className="driver-axis" />
                  <div className="driver-bar" style={{
                    width: `${w}%`, left: d.contribution >= 0 ? "50%" : `${50 - w}%`,
                    background: d.contribution >= 0 ? "var(--pos)" : "var(--neg)",
                  }} />
                </div>
                <span className="num" style={{ textAlign: "right", color: "var(--ink-2)" }}>
                  {d.contribution >= 0 ? "+" : ""}{d.contribution.toFixed(2)}
                </span>
              </div>
            );
          })}
          <div className="legend">
            <span><i style={{ background: "var(--pos)" }} />Pushes towards failure</span>
            <span><i style={{ background: "var(--neg)" }} />Pushes away from failure</span>
          </div>
        </div>
      )}
    </div>
  );
}
