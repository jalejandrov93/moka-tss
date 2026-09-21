import * as React from "react";
import { evaluateRules, validateRule, RuleConfig, EvaluationResult } from "@/lib/rules";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface RulePreviewCardProps {
  rules: RuleConfig[];
  moods: string[];
}

interface SimulatedMetrics {
  cpu: number;
  gpu: number;
  quota: number;
  jobs: number;
}

const DEFAULT_METRICS: SimulatedMetrics = {
  cpu: 50,
  gpu: 30,
  quota: 100,
  jobs: 10,
};

const METRIC_LABELS: Record<keyof SimulatedMetrics, string> = {
  cpu: "CPU %",
  gpu: "GPU %",
  quota: "Quota %",
  jobs: "Jobs",
};

export function RulePreviewCard({ rules, moods }: RulePreviewCardProps) {
  const [metrics, setMetrics] = React.useState<SimulatedMetrics>(DEFAULT_METRICS);
  const [evaluation, setEvaluation] = React.useState<EvaluationResult | null>(null);
  const [validationError, setValidationError] = React.useState<string | null>(null);

  // Validate rules on mount and when rules/moods change
  React.useEffect(() => {
    let error: string | null = null;
    for (let i = 0; i < rules.length; i++) {
      const result = validateRule(rules[i], i, moods);
      if (!result.valid) {
        error = result.error;
        break;
      }
    }
    setValidationError(error);
  }, [rules, moods]);

  // Evaluate rules when metrics change and rules are valid
  React.useEffect(() => {
    if (validationError || rules.length === 0) {
      setEvaluation(null);
      return;
    }

    const metricsRecord: Record<string, number> = {
      cpu: metrics.cpu,
      gpu: metrics.gpu,
      quota: metrics.quota,
      jobs: metrics.jobs,
    };

    const result = evaluateRules(rules, metricsRecord, { moods });
    setEvaluation(result);
  }, [metrics, rules, moods, validationError]);

  const handleMetricChange = (key: keyof SimulatedMetrics, value: number) => {
    setMetrics((prev) => ({ ...prev, [key]: value }));
  };

  const moodColors: Record<string, string> = {
    durmiendo: "bg-blue-600",
    calma: "bg-emerald-600",
    atenta: "bg-amber-500",
    agobiada: "bg-orange-500",
    alarmada: "bg-red-600",
    error: "bg-slate-600",
  };

  if (validationError) {
    return (
      <Card className="w-full max-w-2xl min-w-0 overflow-hidden">
        <CardHeader>
          <CardTitle className="text-slate-50 truncate">Rule Preview</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 min-w-0 break-words">
          <div className="p-4 rounded-lg border border-red-600 bg-red-950/50 text-red-200">
            <p className="font-medium">Configuration Error</p>
            <p className="text-sm mt-1">{validationError}</p>
          </div>
          <div className="text-sm text-slate-400">
            Fix the rule configuration above to enable preview.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-2xl min-w-0 overflow-hidden">
      <CardHeader>
        <CardTitle className="text-slate-50 truncate">Rule Preview</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Metrics Sliders */}
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-slate-300">Simulated Metrics</h3>
          {(Object.keys(DEFAULT_METRICS) as Array<keyof SimulatedMetrics>).map((key) => (
            <div key={key} className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-400 text-sm">{METRIC_LABELS[key]}</span>
                <span className="text-slate-50 font-mono text-sm">{metrics[key]}</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={metrics[key]}
                onChange={(e) => handleMetricChange(key, Number(e.target.value))}
                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-slate-400"
              />
            </div>
          ))}
        </div>

        {/* Evaluation Result */}
        {evaluation && (
          <div className="space-y-4 p-4 rounded-lg border border-slate-800 bg-slate-950/50">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 text-sm">Current Mood</span>
              <Badge
                variant="default"
                className={cn(
                  "text-lg px-4 py-2 font-semibold",
                  moodColors[evaluation.mood] || "bg-slate-600"
                )}
              >
                {evaluation.mood}
              </Badge>
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-slate-400">Winning Rule ID</span>
                <p className="text-slate-50 font-mono mt-1">
                  {evaluation.winning_rule_id ?? "—"}
                </p>
              </div>
              <div>
                <span className="text-slate-400">Fired Rules</span>
                <p className="text-slate-50 font-mono mt-1">
                  {evaluation.fired.length > 0
                    ? evaluation.fired.join(", ")
                    : "—"}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Rules List */}
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-slate-300">Rules ({rules.length})</h3>
          {rules.length === 0 ? (
            <p className="text-slate-500 text-sm">No rules configured</p>
          ) : (
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {rules.map((rule) => {
                const isFired = evaluation?.fired.includes(rule.id) ?? false;
                const isWinner = evaluation?.winning_rule_id === rule.id;
                return (
                  <Badge
                    key={rule.id}
                    variant={isWinner ? "success" : isFired ? "secondary" : "outline"}
                    className={cn(
                      "w-full justify-start gap-2 text-xs min-w-0 overflow-hidden",
                      isWinner && "font-medium"
                    )}
                  >
                    <span className="font-mono truncate max-w-[100px] shrink-0">{rule.id}</span>
                    <span className="text-slate-400 truncate shrink-0">
                      {rule.metric} {rule.op} {rule.value}
                    </span>
                    <span className="text-slate-500 shrink-0">→</span>
                    <span className="capitalize truncate shrink-0">{rule.mood}</span>
                    {rule.priority && (
                      <span className="text-slate-400">p:{rule.priority}</span>
                    )}
                    {rule.for_seconds && (
                      <span className="text-slate-400">for:{rule.for_seconds}s</span>
                    )}
                    {isWinner && (
                      <span className="text-emerald-400 text-xs">● winner</span>
                    )}
                    {isFired && !isWinner && (
                      <span className="text-amber-400 text-xs">● fired</span>
                    )}
                  </Badge>
                );
              })}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}