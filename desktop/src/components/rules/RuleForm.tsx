import * as React from "react";
import {
  type RuleConfig,
  validateRule,
  OPERATORS,
  DEFAULT_MOODS,
  DEFAULT_MOOD,
} from "@/lib/rules";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface RuleFormProps {
  initial?: Partial<RuleConfig> | null;
  moods?: string[];
  onSubmit: (rule: RuleConfig) => void;
  onCancel?: () => void;
  className?: string;
}

interface RuleFormState {
  id: string;
  metric: string;
  op: string;
  value: string;
  mood: string;
  priority: string;
  for_seconds: string;
  release: string;
  release_for: string;
}

const MOOD_COLORS: Record<string, string> = {
  durmiendo: "bg-blue-600 text-white",
  calma: "bg-emerald-600 text-white",
  atenta: "bg-amber-500 text-slate-950",
  agobiada: "bg-orange-500 text-white",
  alarmada: "bg-red-600 text-white",
  error: "bg-slate-600 text-white",
};

function initFormState(
  initial?: Partial<RuleConfig> | null,
  fallbackMood: string = DEFAULT_MOOD
): RuleFormState {
  return {
    id: initial?.id ?? "",
    metric: initial?.metric ?? "",
    op: initial?.op ?? ">=",
    value:
      initial?.value !== undefined && initial?.value !== null
        ? String(initial.value)
        : "",
    mood: initial?.mood ?? fallbackMood,
    priority:
      initial?.priority !== undefined && initial?.priority !== null
        ? String(initial.priority)
        : "0",
    for_seconds:
      initial?.for_seconds !== undefined && initial?.for_seconds !== null
        ? String(initial.for_seconds)
        : initial?.for !== undefined && initial?.for !== null
        ? String(initial.for)
        : "",
    release:
      initial?.release !== undefined && initial?.release !== null
        ? String(initial.release)
        : "",
    release_for:
      initial?.release_for !== undefined && initial?.release_for !== null
        ? String(initial.release_for)
        : "",
  };
}

function validateField(
  fieldName: keyof RuleFormState,
  formData: RuleFormState,
  moods: string[]
): string | null {
  const baseValid: Record<string, unknown> = {
    id: "dummy_valid_id",
    metric: "cpu",
    op: ">=",
    value: 50,
    mood: moods[0] ?? DEFAULT_MOOD,
    priority: 0,
    for_seconds: 0,
    release: 50,
    release_for: 0,
  };

  switch (fieldName) {
    case "id": {
      const res = validateRule({ ...baseValid, id: formData.id.trim() }, 0, moods);
      return res.valid ? null : res.error;
    }
    case "metric": {
      const res = validateRule({ ...baseValid, metric: formData.metric.trim() }, 0, moods);
      return res.valid ? null : res.error;
    }
    case "op": {
      const res = validateRule({ ...baseValid, op: formData.op }, 0, moods);
      return res.valid ? null : res.error;
    }
    case "value": {
      const raw = formData.value.trim();
      const num = raw === "" ? null : Number(raw);
      const res = validateRule({ ...baseValid, value: num }, 0, moods);
      return res.valid ? null : res.error;
    }
    case "mood": {
      const res = validateRule({ ...baseValid, mood: formData.mood }, 0, moods);
      return res.valid ? null : res.error;
    }
    case "priority": {
      const raw = formData.priority.trim();
      if (raw === "") return null;
      const num = Number(raw);
      const res = validateRule({ ...baseValid, priority: num }, 0, moods);
      return res.valid ? null : res.error;
    }
    case "for_seconds": {
      const raw = formData.for_seconds.trim();
      if (raw === "") return null;
      const num = Number(raw);
      const res = validateRule({ ...baseValid, for_seconds: num }, 0, moods);
      return res.valid ? null : res.error;
    }
    case "release": {
      const raw = formData.release.trim();
      if (raw === "") return null;
      const num = Number(raw);
      const valRaw = formData.value.trim();
      const valNum = valRaw === "" ? 50 : Number(valRaw);
      const res = validateRule(
        {
          ...baseValid,
          id: formData.id.trim() || "dummy_valid_id",
          op: formData.op || ">=",
          value: isNaN(valNum) ? 50 : valNum,
          release: num,
        },
        0,
        moods
      );
      return res.valid ? null : res.error;
    }
    case "release_for": {
      const raw = formData.release_for.trim();
      if (raw === "") return null;
      const num = Number(raw);
      const res = validateRule({ ...baseValid, release_for: num }, 0, moods);
      return res.valid ? null : res.error;
    }
    default:
      return null;
  }
}

function validateAllFields(
  formData: RuleFormState,
  moods: string[]
): Record<string, string> {
  const errors: Record<string, string> = {};
  const fields: (keyof RuleFormState)[] = [
    "id",
    "metric",
    "op",
    "value",
    "mood",
    "priority",
    "for_seconds",
    "release",
    "release_for",
  ];

  for (const field of fields) {
    const err = validateField(field, formData, moods);
    if (err) {
      errors[field] = err;
    }
  }

  // Also validate the full candidate object using validateRule directly
  const rawRule: Record<string, unknown> = {
    id: formData.id.trim(),
    metric: formData.metric.trim(),
    op: formData.op,
    value: formData.value.trim() === "" ? null : Number(formData.value.trim()),
    mood: formData.mood,
  };
  if (formData.priority.trim() !== "") {
    rawRule.priority = Number(formData.priority.trim());
  }
  if (formData.for_seconds.trim() !== "") {
    rawRule.for_seconds = Number(formData.for_seconds.trim());
  }
  if (formData.release.trim() !== "") {
    rawRule.release = Number(formData.release.trim());
  }
  if (formData.release_for.trim() !== "") {
    rawRule.release_for = Number(formData.release_for.trim());
  }

  const fullResult = validateRule(rawRule, 0, moods);
  if (!fullResult.valid && fullResult.error) {
    let matched = false;
    for (const f of fields) {
      if (fullResult.error.includes(`'${f}'`)) {
        if (!errors[f]) errors[f] = fullResult.error;
        matched = true;
      }
    }
    if (!matched) {
      errors.general = fullResult.error;
    }
  }

  return errors;
}

export function RuleForm({
  initial,
  moods,
  onSubmit,
  onCancel,
  className,
}: RuleFormProps) {
  const availableMoods =
    moods && moods.length > 0 ? moods : [...DEFAULT_MOODS];
  const defaultMood = availableMoods[0] ?? DEFAULT_MOOD;

  const [formData, setFormData] = React.useState<RuleFormState>(() =>
    initFormState(initial, defaultMood)
  );
  const [touched, setTouched] = React.useState<Record<string, boolean>>({});
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    setFormData(initFormState(initial, defaultMood));
    setTouched({});
    setErrors({});
  }, [initial, defaultMood]);

  const handleChange = (field: keyof RuleFormState, val: string) => {
    const nextData = { ...formData, [field]: val };
    setFormData(nextData);
    setTouched((prev) => ({ ...prev, [field]: true }));

    const updatedErrors = validateAllFields(nextData, availableMoods);
    setErrors(updatedErrors);
  };

  const handleBlur = (field: keyof RuleFormState) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    const updatedErrors = validateAllFields(formData, availableMoods);
    setErrors(updatedErrors);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const allTouched: Record<string, boolean> = {
      id: true,
      metric: true,
      op: true,
      value: true,
      mood: true,
      priority: true,
      for_seconds: true,
      release: true,
      release_for: true,
    };
    setTouched(allTouched);

    const currentErrors = validateAllFields(formData, availableMoods);
    setErrors(currentErrors);

    if (Object.keys(currentErrors).length > 0) {
      return;
    }

    const valNum = Number(formData.value.trim());
    const candidate: RuleConfig = {
      id: formData.id.trim(),
      metric: formData.metric.trim(),
      op: formData.op,
      value: valNum,
      mood: formData.mood,
    };

    if (formData.priority.trim() !== "") {
      candidate.priority = Number(formData.priority.trim());
    }
    if (formData.for_seconds.trim() !== "") {
      const sec = Number(formData.for_seconds.trim());
      candidate.for = sec;
      candidate.for_seconds = sec;
    }
    if (formData.release.trim() !== "") {
      candidate.release = Number(formData.release.trim());
    }
    if (formData.release_for.trim() !== "") {
      candidate.release_for = Number(formData.release_for.trim());
    }

    const finalResult = validateRule(candidate, 0, availableMoods);
    if (!finalResult.valid) {
      setErrors((prev) => ({
        ...prev,
        general: finalResult.error ?? "Invalid rule configuration.",
      }));
      return;
    }

    onSubmit(candidate);
  };

  const inputClass = (hasError: boolean) =>
    cn(
      "w-full rounded-md border bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-1 transition-colors",
      hasError
        ? "border-red-600 focus:border-red-600 focus:ring-red-600"
        : "border-slate-800 focus:border-slate-600 focus:ring-slate-400"
    );

  const isEditing = Boolean(initial?.id);

  return (
    <Card
      className={cn(
        "w-full max-w-2xl min-w-0 overflow-hidden bg-slate-950 border-slate-800 text-slate-50 shadow-xl",
        className
      )}
    >
      <CardHeader>
        <CardTitle className="text-xl font-bold tracking-tight text-slate-50 truncate">
          {isEditing ? "Edit Rule" : "New Rule"}
        </CardTitle>
        <CardDescription className="text-xs text-slate-400 mt-1 truncate">
          {isEditing
            ? `Modify configuration for rule '${initial?.id}'`
            : "Define a condition and target mood"}
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit} noValidate>
        <CardContent className="space-y-4">
          {errors.general && (
            <div className="p-3 rounded-lg border border-red-600 bg-red-950/50 text-red-200 text-xs">
              {errors.general}
            </div>
          )}

          {/* ID and Mood row */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="rule-id"
                className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1"
              >
                Rule ID <span className="text-red-400">*</span>
              </label>
              <input
                id="rule-id"
                type="text"
                value={formData.id}
                onChange={(e) => handleChange("id", e.target.value)}
                onBlur={() => handleBlur("id")}
                placeholder="e.g. cpu_alarmada"
                className={inputClass(Boolean(touched.id && errors.id))}
              />
              {touched.id && errors.id && (
                <p className="text-xs text-red-400 mt-1 font-sans">
                  {errors.id}
                </p>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label
                  htmlFor="rule-mood"
                  className="text-xs font-semibold text-slate-300 uppercase tracking-wider"
                >
                  Mood <span className="text-red-400">*</span>
                </label>
                <Badge
                  variant="default"
                  className={cn(
                    "text-[10px] px-2 py-0 border-transparent capitalize font-medium",
                    MOOD_COLORS[formData.mood] || "bg-slate-700 text-slate-100"
                  )}
                >
                  {formData.mood}
                </Badge>
              </div>
              <select
                id="rule-mood"
                value={formData.mood}
                onChange={(e) => handleChange("mood", e.target.value)}
                onBlur={() => handleBlur("mood")}
                className={inputClass(Boolean(touched.mood && errors.mood))}
              >
                {availableMoods.map((m) => (
                  <option key={m} value={m} className="bg-slate-900 text-slate-100">
                    {m}
                  </option>
                ))}
              </select>
              {touched.mood && errors.mood && (
                <p className="text-xs text-red-400 mt-1 font-sans">
                  {errors.mood}
                </p>
              )}
            </div>
          </div>

          {/* Metric, Operator, Value row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label
                htmlFor="rule-metric"
                className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1"
              >
                Metric <span className="text-red-400">*</span>
              </label>
              <input
                id="rule-metric"
                type="text"
                list="rule-metric-suggestions"
                value={formData.metric}
                onChange={(e) => handleChange("metric", e.target.value)}
                onBlur={() => handleBlur("metric")}
                placeholder="e.g. cpu, ram, gpu"
                className={inputClass(Boolean(touched.metric && errors.metric))}
              />
              <datalist id="rule-metric-suggestions">
                <option value="cpu" />
                <option value="ram" />
                <option value="gpu" />
                <option value="quota" />
                <option value="jobs" />
              </datalist>
              {touched.metric && errors.metric && (
                <p className="text-xs text-red-400 mt-1 font-sans">
                  {errors.metric}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="rule-op"
                className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1"
              >
                Operator <span className="text-red-400">*</span>
              </label>
              <select
                id="rule-op"
                value={formData.op}
                onChange={(e) => handleChange("op", e.target.value)}
                onBlur={() => handleBlur("op")}
                className={inputClass(Boolean(touched.op && errors.op))}
              >
                {OPERATORS.map((op) => (
                  <option key={op} value={op} className="bg-slate-900 text-slate-100">
                    {op}
                  </option>
                ))}
              </select>
              {touched.op && errors.op && (
                <p className="text-xs text-red-400 mt-1 font-sans">
                  {errors.op}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="rule-value"
                className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1"
              >
                Threshold Value <span className="text-red-400">*</span>
              </label>
              <input
                id="rule-value"
                type="number"
                step="any"
                value={formData.value}
                onChange={(e) => handleChange("value", e.target.value)}
                onBlur={() => handleBlur("value")}
                placeholder="e.g. 80"
                className={inputClass(Boolean(touched.value && errors.value))}
              />
              {touched.value && errors.value && (
                <p className="text-xs text-red-400 mt-1 font-sans">
                  {errors.value}
                </p>
              )}
            </div>
          </div>

          {/* Priority & For_seconds row */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="rule-priority"
                className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1"
              >
                Priority
              </label>
              <input
                id="rule-priority"
                type="number"
                step="any"
                value={formData.priority}
                onChange={(e) => handleChange("priority", e.target.value)}
                onBlur={() => handleBlur("priority")}
                placeholder="0"
                className={inputClass(Boolean(touched.priority && errors.priority))}
              />
              {touched.priority && errors.priority && (
                <p className="text-xs text-red-400 mt-1 font-sans">
                  {errors.priority}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="rule-for-seconds"
                className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1"
              >
                Duration (seconds)
              </label>
              <input
                id="rule-for-seconds"
                type="number"
                min="0"
                step="any"
                value={formData.for_seconds}
                onChange={(e) => handleChange("for_seconds", e.target.value)}
                onBlur={() => handleBlur("for_seconds")}
                placeholder="e.g. 5"
                className={inputClass(Boolean(touched.for_seconds && errors.for_seconds))}
              />
              {touched.for_seconds && errors.for_seconds && (
                <p className="text-xs text-red-400 mt-1 font-sans">
                  {errors.for_seconds}
                </p>
              )}
            </div>
          </div>

          {/* Release & Release_for row */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-slate-800/80">
            <div>
              <label
                htmlFor="rule-release"
                className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1"
              >
                Release Threshold
              </label>
              <input
                id="rule-release"
                type="number"
                step="any"
                value={formData.release}
                onChange={(e) => handleChange("release", e.target.value)}
                onBlur={() => handleBlur("release")}
                placeholder="Optional hysteresis release value"
                className={inputClass(Boolean(touched.release && errors.release))}
              />
              {touched.release && errors.release && (
                <p className="text-xs text-red-400 mt-1 font-sans">
                  {errors.release}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="rule-release-for"
                className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1"
              >
                Release Duration (seconds)
              </label>
              <input
                id="rule-release-for"
                type="number"
                min="0"
                step="any"
                value={formData.release_for}
                onChange={(e) => handleChange("release_for", e.target.value)}
                onBlur={() => handleBlur("release_for")}
                placeholder="Optional release time in seconds"
                className={inputClass(Boolean(touched.release_for && errors.release_for))}
              />
              {touched.release_for && errors.release_for && (
                <p className="text-xs text-red-400 mt-1 font-sans">
                  {errors.release_for}
                </p>
              )}
            </div>
          </div>
        </CardContent>

        <CardFooter className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
          {onCancel && (
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              className="text-slate-300"
            >
              Cancel
            </Button>
          )}
          <Button type="submit">
            {isEditing ? "Save Changes" : "Create Rule"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
