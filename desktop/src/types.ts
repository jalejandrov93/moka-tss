export interface StatusSnapshot {
  tick: number;
  running: boolean;
  agenthub_available: boolean;
  codexbar_available: boolean;
  has_system: boolean;
  has_snapshot: boolean;
  has_state: boolean;
}
