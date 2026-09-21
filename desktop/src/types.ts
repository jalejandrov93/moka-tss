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

export interface Transmission {
  frames_total: number;
  full_frames: number;
  partial_frames: number;
  tiles_sent_total: number;
  bytes_sent_total: number;
  last_elapsed_ms: number;
  last_tiles: number;
  last_kind: string;
}

export interface RuleInfo {
  winning_rule_id: string | null;
  fired: string[];
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
  transmission?: Transmission | null;
  rule?: RuleInfo;
}

export interface Rule {
  id: string;
  metric: string;
  op: string;
  value: number;
  mood: string;
  priority: number;
  for?: number;
  for_seconds?: number;
  release?: number;
  release_for?: number;
}

export interface RulesPayload {
  moods: string[];
  default_mood: string | null;
  rules: Rule[];
}

export interface ServiceStatus {
  name: string;
  port: number;
  health: string;
  reachable: boolean;
  latency_ms: number | null;
}

export interface WslStatus {
  available: boolean;
  distros: string[];
}

export interface AppConfig {
  brightness?: number;
  orientation?: string;
  refresh_interval_seconds?: number;
  services?: unknown[];
  hidden_providers?: string[];
  [key: string]: unknown;
}

export interface ThemeCard {
  id: string;
  visible: boolean;
  order: number;
  sensors?: string[];
}

export interface ThemeConfig {
  id: string;
  name: string;
  cards: ThemeCard[];
  mascotVariant: string;
}
