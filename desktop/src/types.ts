export interface SystemTelemetry {
  cpu: number | null;
  ram: number | null;
  gpu: number | null;
}

export interface ScreenInfo {
  present: boolean;
  simulate: boolean;
  brightness: number;
}

export interface StatusSnapshot {
  tick: number;
  running: boolean;
  agenthub_available: boolean;
  codexbar_available: boolean;
  has_system: boolean;
  has_snapshot: boolean;
  has_state: boolean;
  mood: string | null;
  system?: SystemTelemetry;
  screen?: ScreenInfo;
}

export interface Rule {
  id: string;
  metric: string;
  op: string;
  value: number;
  mood: string;
  priority: number;
}

export interface RulesPayload {
  moods: string[];
  default_mood: string | null;
  rules: Rule[];
}

