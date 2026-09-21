import type { RuleConfig } from "@/lib/rules";
import type { Rule } from "@/types";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface RuleListProps {
  rules: (RuleConfig | Rule)[];
  onEdit?: (rule: RuleConfig) => void;
  onDelete?: (id: string) => void;
  className?: string;
}

const MOOD_COLORS: Record<string, string> = {
  durmiendo: "bg-blue-600 text-white",
  calma: "bg-emerald-600 text-white",
  atenta: "bg-amber-500 text-slate-950",
  agobiada: "bg-orange-500 text-white",
  alarmada: "bg-red-600 text-white",
  error: "bg-slate-600 text-white",
};

export function RuleList({
  rules,
  onEdit,
  onDelete,
  className,
}: RuleListProps) {
  const hasActions = Boolean(onEdit || onDelete);

  return (
    <Card className={cn("w-full min-w-0 overflow-hidden bg-slate-950 border-slate-800 text-slate-50 shadow-xl", className)}>
      <CardHeader className="flex flex-row items-center justify-between pb-4 gap-2 min-w-0">
        <div className="min-w-0">
          <CardTitle className="text-xl font-bold tracking-tight text-slate-50 truncate">Rules</CardTitle>
          <CardDescription className="text-xs text-slate-400 mt-1 truncate">
            Configured evaluation rules ({rules.length})
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="min-w-0">
        {rules.length === 0 ? (
          <div className="py-8 text-center text-sm text-slate-500 italic">
            No rules configured
          </div>
        ) : (
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-xs font-semibold uppercase tracking-wider text-slate-400">
                  <th className="py-3 px-4">ID</th>
                  <th className="py-3 px-4">Condition</th>
                  <th className="py-3 px-4">Mood</th>
                  <th className="py-3 px-4 text-center">Priority</th>
                  {hasActions && (
                    <th className="py-3 px-4 text-right">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                {rules.map((rule) => {
                  const moodClass = MOOD_COLORS[rule.mood] || "bg-slate-700 text-slate-100";
                  const priorityVal = typeof rule.priority === "number" ? rule.priority : 0;
                  const conditionText = `${rule.metric} ${rule.op} ${rule.value}`;

                  return (
                    <tr
                      key={rule.id}
                      className="hover:bg-slate-900/50 transition-colors"
                    >
                      <td className="py-3 px-4 font-semibold text-slate-200 truncate max-w-[120px]" title={rule.id}>
                        {rule.id}
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        <span className="bg-slate-900 px-2 py-1 rounded border border-slate-800 break-all">
                          {conditionText}
                        </span>
                        {rule.for_seconds ? (
                          <span className="ml-2 text-slate-500 text-[11px] font-sans shrink-0">
                            for {rule.for_seconds}s
                          </span>
                        ) : null}
                      </td>
                      <td className="py-3 px-4 font-sans">
                        <Badge
                          variant="default"
                          className={cn("capitalize px-2.5 py-0.5 text-xs font-medium border-transparent", moodClass)}
                        >
                          {rule.mood}
                        </Badge>
                      </td>
                      <td className="py-3 px-4 text-center text-slate-300">
                        {priorityVal}
                      </td>
                      {hasActions && (
                        <td className="py-3 px-4 text-right font-sans">
                          <div className="flex items-center justify-end gap-2">
                            {onEdit && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => onEdit(rule as RuleConfig)}
                                className="h-7 px-2.5 text-xs text-slate-200 hover:text-white"
                              >
                                Edit
                              </Button>
                            )}
                            {onDelete && (
                              <Button
                                variant="destructive"
                                size="sm"
                                onClick={() => onDelete(rule.id)}
                                className="h-7 px-2.5 text-xs"
                              >
                                Delete
                              </Button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
