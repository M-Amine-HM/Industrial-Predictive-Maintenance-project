import { useEffect, useState } from "react";
import { api } from "./api";
import DiagnosePanel from "./components/DiagnosePanel";
import FleetPanel from "./components/FleetPanel";
import ReportPanel from "./components/ReportPanel";
import type { ModelInfo } from "./types";

type Tab = "diagnose" | "fleet" | "report";
const TABS: { id: Tab; label: string }[] = [
  { id: "diagnose", label: "Diagnose" },
  { id: "fleet", label: "Fleet scoring" },
  { id: "report", label: "Model report" },
];

function readTheme(): "light" | "dark" | null {
  try { return (localStorage.getItem("theme") as "light" | "dark" | null) ?? null; } catch { return null; }
}

export default function App() {
  const [tab, setTab] = useState<Tab>(() => (location.hash.slice(1) as Tab) || "diagnose");
  const [info, setInfo] = useState<ModelInfo | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [theme, setTheme] = useState<"light" | "dark" | null>(readTheme);

  useEffect(() => {
    api.modelInfo().then((i) => { setInfo(i); setOnline(true); }).catch(() => setOnline(false));
  }, []);

  useEffect(() => { location.hash = tab; }, [tab]);

  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try { if (theme) localStorage.setItem("theme", theme); } catch { /* ignore */ }
  }, [theme]);

  const isDark = theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.4" aria-hidden>
            <circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="2.6" fill="var(--accent)" stroke="none" />
            <path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3" />
          </svg>
          Machine Health Console
        </div>
        <nav className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t.id} role="tab" className="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
        </nav>
        <div className="topbar-right">
          <span className="conn">
            <span className="dot" style={{ background: online === null ? "var(--muted)" : online ? "var(--good)" : "var(--critical)" }} />
            <span className="conn-label">
              {online === null ? "Connecting…" : online ? `Model v${info?.model_version ?? "?"} online` : "API offline"}
            </span>
          </span>
          <button className="icon-btn" aria-label="Toggle colour theme" onClick={() => setTheme(isDark ? "light" : "dark")}>
            {isDark ? "☀" : "☾"}
          </button>
        </div>
      </header>
      <main>
        {online === false && (
          <div className="error">Cannot reach the API. Start it with <code>uvicorn app.main:app --port 8000</code> from the <code>backend/</code> folder.</div>
        )}
        {tab === "diagnose" && <DiagnosePanel info={info} />}
        {tab === "fleet" && <FleetPanel info={info} />}
        {tab === "report" && <ReportPanel info={info} />}
      </main>
    </>
  );
}
