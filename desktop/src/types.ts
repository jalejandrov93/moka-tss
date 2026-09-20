export interface StatusSnapshot {
  tick: number;
  running: boolean;
  agenthub_available: boolean;
  codexbar_available: boolean;
  has_system: boolean;
  has_snapshot: boolean;
  has_state: boolean;
  mood: string | null;
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

