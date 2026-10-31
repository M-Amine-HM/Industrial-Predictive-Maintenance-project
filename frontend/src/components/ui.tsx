import type { Status } from "../types";

export const CLASS_COLOR: Record<string, string> = {
  "No Failure": "var(--c-none)",
  TWF: "var(--c-twf)",
  HDF: "var(--c-hdf)",
  PWF: "var(--c-pwf)",
  OSF: "var(--c-osf)",
};

export const CLASS_LABEL: Record<string, string> = {
  "No Failure": "No failure",
  TWF: "Tool wear",
  HDF: "Heat dissipation",
  PWF: "Power",
  OSF: "Overstrain",
};

export const STATUS_LABEL: Record<Status, string> = { ok: "Healthy", advisory: "Advisory", alarm: "Alarm" };

export function StatusIcon({ status, size = 20 }: { status: Status; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2.4, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  if (status === "ok") return <svg {...common}><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>;
  if (status === "advisory") return <svg {...common}><path d="M12 3l9.5 17h-19z" /><path d="M12 10v4.5M12 17.5v.01" /></svg>;
  return <svg {...common}><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.5v.01" /></svg>;
}

export function StatusPill({ status }: { status: Status }) {
  return (
    <span className={`pill ${status}`}>
      <span style={{ color: status === "ok" ? "var(--good)" : status === "advisory" ? "var(--warning)" : "var(--critical)", display: "inline-flex" }}>
        <StatusIcon status={status} size={14} />
      </span>
      {STATUS_LABEL[status]}
    </span>
  );
}

export const pct = (v: number, digits = 1) => `${(v * 100).toFixed(digits)}%`;
