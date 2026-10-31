import { useEffect, useState } from "react";
import { api } from "../api";
import type { Figure, ModelInfo } from "../types";
import { pct } from "./ui";

const CAPTIONS: Record<string, string> = {
  "01_class_balance": "Class balance: 3.3% of machines fail",
  "02_sensor_kde": "Sensor distributions, healthy vs failure",
  "03_sensor_boxplots_by_type": "Sensor signature of each failure type",
  "04_failure_rate_by_type": "Failure rate by product quality",
  "05_pairplot": "Pairwise sensor relationships",
  "06_failure_mechanisms": "The three deterministic failure mechanisms",
  "07_twf_window": "Tool-wear failures occur only at 200–250 min",
  "08_mutual_information": "Engineered vs raw feature information",
  "09_feature_correlation": "Feature correlation (Spearman)",
  "10_anomaly_detection": "Unsupervised anomaly detection",
  "11_baseline_comparison": "Model comparison: raw vs engineered features",
  "12_optuna_history": "Optuna search with cost objective",
  "13_threshold_tuning": "FDR-driven threshold selection",
  "14_confusion_matrices": "Test-set confusion matrices",
  "15_pr_calibration": "Precision–recall and calibration",
  "16_shap_importance_by_class": "SHAP importance per failure class",
  "17_shap_beeswarm_HDF": "SHAP beeswarm: heat dissipation",
  "17_shap_beeswarm_OSF": "SHAP beeswarm: overstrain",
  "17_shap_beeswarm_PWF": "SHAP beeswarm: power",
  "18_lead_indicator_correlation": "Lead indicator: sensor correlations",
  "19_failure_rate_by_decile": "Failure rate across sensor deciles",
  "20_lead_indicator_shap": "Lead indicator: model attribution",
  "21_rul_distribution": "Remaining-useful-life distribution",
  "22_rul_regression": "RUL regression: predicted vs actual",
};

export default function ReportPanel({ info }: { info: ModelInfo | null }) {
  const [figs, setFigs] = useState<Figure[]>([]);
  const [open, setOpen] = useState<Figure | null>(null);

  useEffect(() => { api.figures().then(setFigs).catch(() => setFigs([])); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const m = info?.metrics.classifier_test;
  const tiles = m && info ? [
    { label: "False Discovery Rate", value: pct(m.FDR), hint: `target ≤ ${pct(info.fdr_target, 0)} · ${m.FP} false alarms` },
    { label: "Alarm precision", value: pct(m.Precision), hint: `${m.TP} true alarms` },
    { label: "Recall (all failures)", value: pct(m.Recall), hint: `${m.FN} missed (tool-wear failures)` },
    { label: "MCC", value: m.MCC.toFixed(3), hint: `PR-AUC ${m["PR-AUC"].toFixed(3)}` },
    { label: "Alarm threshold", value: info.threshold.toFixed(2), hint: "chosen on cross-validation" },
    { label: "RUL error (MAE)", value: `${info.metrics.rul_test["MAE (min)"].toFixed(2)} min`, hint: `R² ${info.metrics.rul_test["R²"].toFixed(4)}` },
  ] : [];

  return (
    <>
      <div className="page-head">
        <h1>Model report</h1>
        <p>Held-out test results (1,999 machines the model never saw) and the figures from the training notebook.</p>
      </div>
      <div className="tiles num">
        {tiles.map((t) => (
          <div className="tile" key={t.label}>
            <div className="stat-label">{t.label}</div>
            <div className="stat-value">{t.value}</div>
            <div className="hint">{t.hint}</div>
          </div>
        ))}
      </div>
      <div className="card" style={{ marginBottom: 18 }}>
        <h2>How to read these results</h2>
        <p className="note" style={{ margin: 0 }}>
          The model catches every heat, power and overstrain failure without a single false alarm on the test set.
          Tool-wear failures happen at a random point once wear passes 200 min (only ~5% of such tools fail), so they are
          handled by a <b>tool-replacement advisory</b> and the RUL estimate rather than an alarm. Alarming on them would
          multiply false stoppages.
        </p>
      </div>
      <div className="gallery">
        {figs.map((f) => (
          <button className="fig" key={f.name} onClick={() => setOpen(f)}>
            <img src={api.figureUrl(f.url)} alt={CAPTIONS[f.name] ?? f.name} loading="lazy" />
            <figcaption>{CAPTIONS[f.name] ?? f.name}</figcaption>
          </button>
        ))}
        {figs.length === 0 && <div className="empty">No figures available — run the notebook first.</div>}
      </div>
      {open && (
        <div className="lightbox" onClick={() => setOpen(null)} role="dialog" aria-label={CAPTIONS[open.name] ?? open.name}>
          <div>
            <img src={api.figureUrl(open.url)} alt={CAPTIONS[open.name] ?? open.name} />
            <p>{CAPTIONS[open.name] ?? open.name} · press Esc to close</p>
          </div>
        </div>
      )}
    </>
  );
}
