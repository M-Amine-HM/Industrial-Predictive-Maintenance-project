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

export interface ModelInfo {
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
