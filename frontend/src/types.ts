export type MachineType = "L" | "M" | "H";

export interface Reading {
  type: MachineType;
  air_temperature: number;
  process_temperature: number;
  rotational_speed: number;
  torque: number;
  tool_wear: number;
}

export type Status = "ok" | "advisory" | "alarm";

export interface Mechanism {
  mode: string;
  label: string;
  value: number;
  limit: string;
  unit: string;
  utilisation: number;
  breached: boolean;
}

export interface Driver {
  feature: string;
  value: number;
  contribution: number;
}

export interface Prediction {
  alarm: boolean;
  status: Status;
  failure_probability: number;
  predicted_failure: string;
  most_likely_failure: string;
  class_probabilities: Record<string, number>;
  rul_minutes: number;
  tool_replacement_advised: boolean;
  threshold: number;
  mechanisms: Mechanism[];
  drivers: Driver[];
}

export interface BatchRow {
  row: number;
  alarm: boolean;
  status: Status;
  failure_probability: number;
  predicted_failure: string;
  rul_minutes: number;
  tool_replacement_advised: boolean;
}

export interface BatchResponse {
  n_rows: number;
  n_alarms: number;
  n_advisories: number;
  by_failure: Record<string, number>;
  rows: BatchRow[];
}

export interface ErrorDetail {
  field: string;
  message: string;
  row?: number | null;
}

export interface SensorDrift {
  sensor: string;
  psi: number;
  status: "stable" | "moderate" | "significant";
  reference_mean: number;
  current_mean: number;
}

export interface DriftResponse {
  status: "insufficient_data" | "stable" | "moderate" | "significant";
  n_samples: number;
  min_samples: number;
  sensors: SensorDrift[];
}

export interface ModelInfo {
  model_version: string;
  mlflow: { run_id?: string; registered_model?: string; registered_version?: string; experiment?: string };
  limits: { max_batch_rows: number; max_upload_mb: number };
  classes: string[];
  threshold: number;
  fdr_target: number;
  twf_advisory_wear_min: number;
  features: string[];
  metrics: {
    classifier_test: Record<string, number>;
    classifier_test_macro_f1: number;
    rul_test: Record<string, number>;
  };
  sensor_ranges: Record<string, { min: number; max: number; median: number }>;
}

export interface Figure {
  name: string;
  url: string;
}
