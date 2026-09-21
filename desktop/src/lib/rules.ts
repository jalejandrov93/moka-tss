import type { Rule, RulesPayload } from "../types";

export const DEFAULT_MOODS = [
  "durmiendo",
  "calma",
  "atenta",
  "agobiada",
  "alarmada",
  "error",
] as const;

export const DEFAULT_MOOD = "calma";

export const OPERATORS = [">=", ">", "<=", "<", "==", "!="] as const;
export type Operator = (typeof OPERATORS)[number];

export const RELEASE_OPERATORS: Record<Operator, Operator> = {
  ">=": "<",
  ">": "<=",
  "<=": ">",
  "<": ">=",
  "==": "!=",
  "!=": "==",
};

export const HIGH_DIRECTION_OPS: ReadonlySet<string> = new Set([">=", ">"]);
export const LOW_DIRECTION_OPS: ReadonlySet<string> = new Set(["<=", "<"]);

export const OPERATOR_FNS: Record<string, (a: number, b: number) => boolean> = {
  ">=": (a, b) => a >= b,
  ">": (a, b) => a > b,
  "<=": (a, b) => a <= b,
  "<": (a, b) => a < b,
  "==": (a, b) => a === b,
  "!=": (a, b) => a !== b,
};

export interface RuleConfig {
  id: string;
  metric: string;
  op: string;
  value: number;
  mood: string;
  priority?: number;
  for?: number;
  for_seconds?: number;
  release?: number;
  release_for?: number;
}

export interface RulesConfig {
  moods: string[];
  default_mood: string | null;
  rules: (Rule | RuleConfig)[];
}

export interface EvaluationResult {
  mood: string;
  winning_rule_id: string | null;
  fired: string[];
  fired_rule_ids?: string[];
}

export interface ValidationResult {
  valid: boolean;
  error: string | null;
  rule?: Rule;
}

export class RulesConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RulesConfigError";
  }
}

export function isMissingMetric(value: unknown): boolean {
  if (typeof value === "boolean") return true;
  if (typeof value !== "number") return true;
  return Number.isNaN(value);
}

function formatRaw(val: unknown): string {
  if (typeof val === "string") return `'${val}'`;
  return String(val);
}

function getRuleLabel(rule: unknown, index: number): string {
  if (rule && typeof rule === "object" && "id" in rule && (rule as Record<string, unknown>).id) {
    return String((rule as Record<string, unknown>).id);
  }
  return `<rule at index ${index}, no id>`;
}

export function validateRule(
  rule: unknown,
  indexOrMoods: number | string[] = 0,
  knownMoods: string[] = [...DEFAULT_MOODS]
): ValidationResult {
  let index = 0;
  let moods = knownMoods;
  if (Array.isArray(indexOrMoods)) {
    moods = indexOrMoods;
    index = 0;
  } else if (typeof indexOrMoods === "number") {
    index = indexOrMoods;
  }

  if (!rule || typeof rule !== "object" || Array.isArray(rule)) {
    const got = rule === null ? "NoneType" : Array.isArray(rule) ? "list" : typeof rule;
    return {
      valid: false,
      error: `Rule at index ${index} must be a mapping, got ${got}.`,
    };
  }

  const r = rule as Record<string, unknown>;
  const label = getRuleLabel(rule, index);

  if (!("id" in r) || r.id === null || r.id === undefined || r.id === "") {
    return {
      valid: false,
      error: `Rule '${label}' is missing required field 'id'.`,
    };
  }

  if (!("metric" in r) || r.metric === null || r.metric === undefined || r.metric === "") {
    return {
      valid: false,
      error: `Rule '${label}' is missing required field 'metric'.`,
    };
  }

  if (!("op" in r) || r.op === null || r.op === undefined || r.op === "") {
    return {
      valid: false,
      error: `Rule '${label}' is missing required field 'op'.`,
    };
  }

  const op = String(r.op);
  if (!(op in OPERATOR_FNS)) {
    const allowed = [...OPERATORS].sort().join(", ");
    return {
      valid: false,
      error: `Rule '${label}' has unknown field 'op' = '${op}'. Allowed operators: ${allowed}.`,
    };
  }

  if (!("value" in r) || r.value === null || r.value === undefined) {
    return {
      valid: false,
      error: `Rule '${label}' is missing required numeric field 'value'.`,
    };
  }

  if (typeof r.value === "boolean" || typeof r.value !== "number" || Number.isNaN(r.value)) {
    return {
      valid: false,
      error: `Rule '${label}' has a non-numeric value for field 'value': ${formatRaw(r.value)}.`,
    };
  }
  const value = Number(r.value);

  if (!("mood" in r) || r.mood === null || r.mood === undefined || r.mood === "") {
    return {
      valid: false,
      error: `Rule '${label}' is missing required field 'mood'.`,
    };
  }

  const mood = String(r.mood);
  if (!moods.includes(mood)) {
    const allowed = moods.join(", ");
    return {
      valid: false,
      error: `Rule '${label}' has unknown field 'mood' = '${mood}'. Declared moods: ${allowed}.`,
    };
  }

  let forSeconds = 0.0;
  if ("for" in r && r.for !== null && r.for !== undefined) {
    if (typeof r.for === "boolean" || typeof r.for !== "number" || Number.isNaN(r.for)) {
      return {
        valid: false,
        error: `Rule '${label}' has a non-numeric value for field 'for': ${formatRaw(r.for)}.`,
      };
    }
    if (Number(r.for) < 0) {
      return {
        valid: false,
        error: `Rule '${label}' has field 'for' = ${formatRaw(r.for)}, but it must be >= 0.`,
      };
    }
    forSeconds = Number(r.for);
  } else if ("for_seconds" in r && r.for_seconds !== null && r.for_seconds !== undefined) {
    if (
      typeof r.for_seconds === "boolean" ||
      typeof r.for_seconds !== "number" ||
      Number.isNaN(r.for_seconds)
    ) {
      return {
        valid: false,
        error: `Rule '${label}' has a non-numeric value for field 'for_seconds': ${formatRaw(r.for_seconds)}.`,
      };
    }
    if (Number(r.for_seconds) < 0) {
      return {
        valid: false,
        error: `Rule '${label}' has field 'for_seconds' = ${formatRaw(r.for_seconds)}, but it must be >= 0.`,
      };
    }
    forSeconds = Number(r.for_seconds);
  }

  let release = value;
  if ("release" in r && r.release !== null && r.release !== undefined) {
    if (
      typeof r.release === "boolean" ||
      typeof r.release !== "number" ||
      Number.isNaN(r.release)
    ) {
      return {
        valid: false,
        error: `Rule '${label}' has a non-numeric value for field 'release': ${formatRaw(r.release)}.`,
      };
    }
    release = Number(r.release);
  }

  let releaseFor = 0.0;
  if ("release_for" in r && r.release_for !== null && r.release_for !== undefined) {
    if (
      typeof r.release_for === "boolean" ||
      typeof r.release_for !== "number" ||
      Number.isNaN(r.release_for)
    ) {
      return {
        valid: false,
        error: `Rule '${label}' has a non-numeric value for field 'release_for': ${formatRaw(r.release_for)}.`,
      };
    }
    if (Number(r.release_for) < 0) {
      return {
        valid: false,
        error: `Rule '${label}' has field 'release_for' = ${formatRaw(r.release_for)}, but it must be >= 0.`,
      };
    }
    releaseFor = Number(r.release_for);
  }

  let priority = 0.0;
  if ("priority" in r && r.priority !== null && r.priority !== undefined) {
    if (
      typeof r.priority === "boolean" ||
      typeof r.priority !== "number" ||
      Number.isNaN(r.priority)
    ) {
      return {
        valid: false,
        error: `Rule '${label}' has a non-numeric value for field 'priority': ${formatRaw(r.priority)}.`,
      };
    }
    priority = Number(r.priority);
  }

  if (HIGH_DIRECTION_OPS.has(op) && release > value) {
    return {
      valid: false,
      error:
        `Rule '${label}' has 'release' (${release}) greater than 'value' (${value}) for op '${op}'. ` +
        `A release threshold above the firing threshold would let a single reading be simultaneously firing and releasing. ` +
        `Set release <= value.`,
    };
  }

  if (LOW_DIRECTION_OPS.has(op) && release < value) {
    return {
      valid: false,
      error:
        `Rule '${label}' has 'release' (${release}) less than 'value' (${value}) for op '${op}'. ` +
        `A release threshold below the firing threshold would let a single reading be simultaneously firing and releasing. ` +
        `Set release >= value.`,
    };
  }

  const validatedRule: Rule = {
    id: String(r.id),
    metric: String(r.metric),
    op,
    value,
    mood,
    priority,
    for: forSeconds,
    for_seconds: forSeconds,
    release,
    release_for: releaseFor,
  };

  return {
    valid: true,
    error: null,
    rule: validatedRule,
  };
}

export function buildRule(
  rule: unknown,
  index = 0,
  knownMoods: string[] = [...DEFAULT_MOODS]
): Rule {
  const result = validateRule(rule, index, knownMoods);
  if (!result.valid) {
    throw new RulesConfigError(result.error!);
  }
  return result.rule!;
}

export function validateRulesConfig(config: unknown): ValidationResult {
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    const got = config === null ? "NoneType" : Array.isArray(config) ? "list" : typeof config;
    return {
      valid: false,
      error: `Rules config must be a mapping, got ${got}.`,
    };
  }

  const c = config as Record<string, unknown>;
  if (!Array.isArray(c.moods) || c.moods.length === 0) {
    return {
      valid: false,
      error: "Rules config is missing a non-empty top-level 'moods' list.",
    };
  }

  const moods = c.moods.map(String);
  const defaultMood = c.default_mood ? String(c.default_mood) : null;
  if (!defaultMood || !moods.includes(defaultMood)) {
    return {
      valid: false,
      error: `Rules config 'default_mood' = '${defaultMood}' must be one of the declared 'moods': ${moods.join(", ")}.`,
    };
  }

  const rawRules = c.rules ?? [];
  if (!Array.isArray(rawRules)) {
    return {
      valid: false,
      error: "Rules config 'rules' must be a list.",
    };
  }

  const seenIds = new Set<string>();
  for (let i = 0; i < rawRules.length; i++) {
    const res = validateRule(rawRules[i], i, moods);
    if (!res.valid) {
      return res;
    }
    const ruleId = res.rule!.id;
    if (seenIds.has(ruleId)) {
      return {
        valid: false,
        error: `Duplicate rule id '${ruleId}': rule ids must be unique.`,
      };
    }
    seenIds.add(ruleId);
  }

  return {
    valid: true,
    error: null,
  };
}

export function evaluateRules(
  rulesOrConfig: (Rule | RuleConfig)[] | RulesConfig | RulesPayload,
  metrics: Record<string, number | null | undefined>,
  options?: { moods?: string[]; default_mood?: string | null } | string[]
): EvaluationResult {
  let ruleList: (Rule | RuleConfig)[] = [];
  let moods: string[] = [...DEFAULT_MOODS];
  let defaultMood: string = DEFAULT_MOOD;

  if (Array.isArray(rulesOrConfig)) {
    ruleList = rulesOrConfig;
    if (Array.isArray(options)) {
      moods = options;
    } else if (options && typeof options === "object") {
      if (options.moods && Array.isArray(options.moods)) moods = options.moods;
      if (options.default_mood) defaultMood = options.default_mood;
    }
  } else if (rulesOrConfig && typeof rulesOrConfig === "object") {
    if ("rules" in rulesOrConfig && Array.isArray(rulesOrConfig.rules)) {
      ruleList = rulesOrConfig.rules;
    }
    if ("moods" in rulesOrConfig && Array.isArray(rulesOrConfig.moods)) {
      moods = rulesOrConfig.moods;
    }
    if ("default_mood" in rulesOrConfig && rulesOrConfig.default_mood) {
      defaultMood = rulesOrConfig.default_mood;
    }
    if (Array.isArray(options)) {
      moods = options;
    } else if (options && typeof options === "object") {
      if (options.moods && Array.isArray(options.moods)) moods = options.moods;
      if (options.default_mood) defaultMood = options.default_mood;
    }
  }

  const firedRules: (Rule | RuleConfig)[] = [];

  for (const rule of ruleList) {
    if (!rule || typeof rule !== "object") continue;
    const metricVal = metrics[rule.metric];
    if (isMissingMetric(metricVal)) {
      continue;
    }

    const opFn = OPERATOR_FNS[rule.op];
    if (!opFn) continue;

    if (opFn(metricVal as number, rule.value)) {
      firedRules.push(rule);
    }
  }

  const firedIds = firedRules.map((r) => r.id);

  if (firedRules.length === 0) {
    return {
      mood: defaultMood,
      winning_rule_id: null,
      fired: [],
      fired_rule_ids: [],
    };
  }

  const moodRank = new Map<string, number>();
  moods.forEach((m, idx) => moodRank.set(m, idx));

  let winner = firedRules[0];
  for (let i = 1; i < firedRules.length; i++) {
    const candidate = firedRules[i];
    const prioCandidate = candidate.priority ?? 0;
    const prioWinner = winner.priority ?? 0;

    if (prioCandidate > prioWinner) {
      winner = candidate;
    } else if (prioCandidate === prioWinner) {
      const rankCandidate = moodRank.get(candidate.mood) ?? -1;
      const rankWinner = moodRank.get(winner.mood) ?? -1;

      if (rankCandidate > rankWinner) {
        winner = candidate;
      } else if (rankCandidate === rankWinner) {
        if (candidate.id < winner.id) {
          winner = candidate;
        }
      }
    }
  }

  return {
    mood: winner.mood,
    winning_rule_id: winner.id,
    fired: firedIds,
    fired_rule_ids: firedIds,
  };
}
