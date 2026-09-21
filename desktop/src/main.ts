import "./index.css";
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { listen } from "@tauri-apps/api/event";
import { App } from "./App";
import {
  type StatusSnapshot,
  type RulesPayload,
  type Rule,
  type ServiceStatus,
  type WslStatus,
  type AppConfig,
  type ThemeConfig,
  type MascotVariant,
  MASCOT_OPTIONS,
  isMascotVariant,
} from "./types";
export { MASCOT_OPTIONS, isMascotVariant, type MascotVariant };
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RuleList, RuleForm, RulePreviewCard } from "@/components/rules";
import { type RuleConfig, DEFAULT_MOODS } from "@/lib/rules";
import {
  loadVisible,
  saveVisible,
  getAllCardIds,
  getCardLabel,
  getDefaultTheme,
  getOrderedVisibleCards,
  updateThemeCardVisibility,
  type CardId,
} from "@/lib/dashboard";
import { pickImageFile, fileToThemeBackground } from "@/lib/image";

const DEFAULT_PORT = 8765;
let serverPort = DEFAULT_PORT;
const POLL_INTERVAL_MS = 2000;
const SERVICES_POLL_INTERVAL_MS = 10000;

export function baseUrl(): string {
  return `http://127.0.0.1:${serverPort}`;
}

let root: Root | null = null;
let currentStatus: StatusSnapshot | null = null;
let currentRules: RulesPayload | null = null;
let currentServices: ServiceStatus[] | null = null;
let currentWsl: WslStatus | null = null;
let statusError: unknown = null;
let rulesError: unknown = null;
let servicesError: unknown = null;
let wslError: unknown = null;
export let currentConfig: AppConfig | null = null;
let isBrightnessInitialized = false;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
export let sliderBrightness = 100;
export let brightnessStatus: "idle" | "applied" | "error" = "idle";
export let brightnessStatusText = "";
export let mascotStatus: "idle" | "applied" | "error" = "idle";
export let mascotStatusText = "";
export let editingRule: RuleConfig | null = null;
export let originalRuleId: string | null = null;
export let rulesSaveError: string | null = null;
export let visibleCards: CardId[] = loadVisible();
export let pendingBackgroundDataUrl: string | null = null;
export let backgroundError: string | null = null;
const BG_STORAGE_KEY = "moka.theme.backgroundImage";

export function loadSavedBackground(): string | undefined {
  try {
    return localStorage.getItem(BG_STORAGE_KEY) || undefined;
  } catch {
    return undefined;
  }
}

export function saveStoredBackground(bg: string | null | undefined): void {
  try {
    if (bg) {
      localStorage.setItem(BG_STORAGE_KEY, bg);
    } else {
      localStorage.removeItem(BG_STORAGE_KEY);
    }
  } catch {
    // Ignore storage errors
  }
}

export let currentTheme: ThemeConfig = {
  ...getDefaultTheme(),
  backgroundImage: loadSavedBackground(),
};
let themeDebounceTimer: ReturnType<typeof setTimeout> | null = null;

function getRoot(): Root | null {
  if (root) return root;
  const container = document.getElementById("root") || document.getElementById("status-container");
  if (!container) return null;
  root = createRoot(container);
  return root;
}

export function getStatusInfo(): {
  text: string;
  variant: "success" | "secondary" | "destructive";
  mood: string | null;
  serverPort: number;
} {
  let text = "No presente";
  let variant: "success" | "secondary" | "destructive" = "destructive";

  if (currentStatus?.screen?.simulate) {
    text = "Simulada";
    variant = "secondary";
  } else if (currentStatus?.screen?.present) {
    text = "Conectada";
    variant = "success";
  } else {
    text = "No presente";
    variant = "destructive";
  }

  return {
    text,
    variant,
    mood: currentStatus?.mood ?? null,
    serverPort,
  };
}

function renderServiciosCard(): React.ReactElement {
  if (servicesError) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400 truncate" },
          "Servicios"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400 break-words" },
        React.createElement(
          "p",
          null,
          `Error fetching services: ${servicesError instanceof Error ? servicesError.message : String(servicesError)}`
        )
      )
    );
  }

  if (!currentServices) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
          "Servicios"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-4 font-mono text-sm text-slate-400" },
        "Cargando servicios..."
      )
    );
  }

  const servicesList = Array.isArray(currentServices) ? currentServices : [];

  return React.createElement(
    Card,
    { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      null,
      React.createElement(
        CardTitle,
        { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
        "Servicios"
      )
    ),
    React.createElement(
      CardContent,
      { className: "space-y-4 min-w-0" },
      React.createElement(
        "div",
        { className: "space-y-2 min-w-0" },
        React.createElement(
          "div",
          { className: "text-xs font-semibold text-slate-400 uppercase tracking-wider truncate" },
          `Servicios (${servicesList.length})`
        ),
        React.createElement(
          "div",
          { className: "max-h-48 overflow-y-auto space-y-1.5 pr-1 font-mono text-xs text-slate-300" },
          servicesList.length === 0
            ? React.createElement(
                "div",
                { className: "text-slate-500 italic py-1" },
                "sin servicios configurados"
              )
            : servicesList.map((svc: ServiceStatus) => {
                const latencyDisplay = svc.reachable
                  ? `${typeof svc.latency_ms === "number" ? svc.latency_ms : 0} ms`
                  : "cerrado";

                return React.createElement(
                  "div",
                  {
                    key: `${svc.name}-${svc.port}`,
                    className: "py-1.5 px-2.5 rounded bg-slate-900 border border-slate-800 text-slate-300 flex justify-between items-center gap-2 min-w-0",
                  },
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-1.5 min-w-0 overflow-hidden" },
                    React.createElement("span", { className: "font-semibold text-slate-200 truncate" }, svc.name),
                    React.createElement("span", { className: "text-slate-500 text-xs shrink-0" }, `:${svc.port}`)
                  ),
                  React.createElement(
                    Badge,
                    { variant: svc.reachable ? "success" : "destructive", className: "shrink-0" },
                    latencyDisplay
                  )
                );
              })
        )
      )
    )
  );
}

function renderMascotaCard(): React.ReactElement {
  if (rulesError) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400 truncate" },
          "Mascota"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400 break-words" },
        React.createElement(
          "p",
          null,
          `Error fetching rules: ${rulesError instanceof Error ? rulesError.message : String(rulesError)}`
        )
      )
    );
  }

  if (!currentRules) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
          "Mascota"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-4 font-mono text-sm text-slate-400" },
        "Cargando reglas..."
      )
    );
  }

  const rawMood = currentStatus?.mood ?? currentRules.default_mood ?? "null";
  const moodDisplay = String(rawMood).toUpperCase();
  const rulesList = Array.isArray(currentRules.rules) ? currentRules.rules : [];

  return React.createElement(
    Card,
    { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      null,
      React.createElement(
        CardTitle,
        { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
        "Mascota"
      )
    ),
    React.createElement(
      CardContent,
      { className: "space-y-4 min-w-0" },
      React.createElement(
        "div",
        { className: "flex items-center justify-between pb-3 border-b border-slate-800 gap-2 min-w-0" },
        React.createElement(
          "span",
          { className: "text-sm text-slate-400 font-medium truncate" },
          "Mood actual"
        ),
        React.createElement(
          Badge,
          {
            variant: "default",
            className: "text-base font-bold px-3 py-1 uppercase tracking-wide shrink-0 truncate max-w-[60%]",
          },
          moodDisplay
        )
      ),
      React.createElement(
        "div",
        { className: "space-y-2 min-w-0" },
        React.createElement(
          "div",
          { className: "text-xs font-semibold text-slate-400 uppercase tracking-wider truncate" },
          `Reglas (${rulesList.length})`
        ),
        React.createElement(
          "div",
          { className: "max-h-48 overflow-y-auto space-y-1.5 pr-1 font-mono text-xs text-slate-300" },
          rulesList.length === 0
            ? React.createElement(
                "div",
                { className: "text-slate-500 italic py-1" },
                "Sin reglas configuradas"
              )
            : rulesList.map((rule: Rule) =>
                React.createElement(
                  "div",
                  {
                    key: rule.id,
                    className: "py-1.5 px-2.5 rounded bg-slate-900 border border-slate-800 text-slate-300 flex justify-between items-center gap-2 min-w-0",
                  },
                  React.createElement("span", { className: "font-semibold text-slate-200 truncate" }, rule.id),
                  React.createElement("span", { className: "text-slate-400 shrink-0" }, `→ ${rule.mood}`)
                )
              )
        )
      )
    )
  );
}

function renderMascotaDetailCard(): React.ReactElement {
  if (statusError) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400 truncate" },
          "Mascota Detalle"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400 break-words" },
        React.createElement(
          "p",
          null,
          `Error fetching status: ${statusError instanceof Error ? statusError.message : String(statusError)}`
        )
      )
    );
  }

  if (!currentStatus) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
          "Mascota Detalle"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-4 font-mono text-sm text-slate-400" },
        "Cargando estado..."
      )
    );
  }

  const mood = currentStatus.mood ?? "null";
  const rule = currentStatus.rule;
  const winningRuleId = rule?.winning_rule_id ?? "default";
  const fired = rule?.fired ?? [];

  return React.createElement(
    Card,
    { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      null,
      React.createElement(
        CardTitle,
        { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
        "Mascota Detalle"
      )
    ),
    React.createElement(
      CardContent,
      { className: "space-y-4 min-w-0" },
      React.createElement(
        "div",
        { className: "text-center py-4 min-w-0 overflow-hidden" },
        React.createElement(
          "span",
          { className: "text-5xl font-bold uppercase tracking-wider text-slate-100 truncate block break-words" },
          String(mood).toUpperCase()
        )
      ),
      React.createElement(
        "div",
        { className: "pt-3 border-t border-slate-800 min-w-0" },
        React.createElement(
          "div",
          { className: "text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 truncate" },
          "Triggered by"
        ),
        React.createElement(
          Badge,
          { variant: "default", className: "text-base font-medium px-3 py-1.5 max-w-full truncate inline-block" },
          winningRuleId
        )
      ),
      React.createElement(
        "div",
        { className: "pt-3 border-t border-slate-800 min-w-0" },
        React.createElement(
          "div",
          { className: "text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 truncate" },
          `Reglas activas (${fired.length})`
        ),
        React.createElement(
          "div",
          { className: "max-h-36 overflow-y-auto flex flex-wrap gap-1.5 pr-1" },
          fired.length === 0
            ? React.createElement(
                "span",
                { className: "text-slate-500 italic text-xs" },
                "sin reglas activas"
              )
            : fired.map((id: string) =>
                React.createElement(
                  Badge,
                  { key: id, variant: "secondary", className: "text-xs px-2 py-0.5 truncate max-w-full" },
                  id
                )
              )
        )
      )
    )
  );
}

function renderMetricBar(label: string, value: number | null | undefined): React.ReactElement {
  const isAvailable = value !== null && value !== undefined && !Number.isNaN(value);
  const displayVal = isAvailable ? `${Number(value.toFixed(1))}%` : "n/d";
  const widthPercent = isAvailable ? Math.min(100, Math.max(0, value)) : 0;

  let colorClass = "bg-slate-700";
  if (isAvailable) {
    if (value >= 90) {
      colorClass = "bg-red-500";
    } else if (value >= 75) {
      colorClass = "bg-amber-500";
    } else {
      colorClass = "bg-emerald-500";
    }
  }

  return React.createElement(
    "div",
    { className: "space-y-1.5 min-w-0" },
    React.createElement(
      "div",
      { className: "flex justify-between text-xs font-mono text-slate-300 gap-2 min-w-0" },
      React.createElement("span", { className: "font-semibold text-slate-400 uppercase tracking-wider truncate" }, label),
      React.createElement("span", { className: "shrink-0" }, displayVal)
    ),
    React.createElement(
      "div",
      { className: "h-2 w-full overflow-hidden rounded-full bg-slate-800" },
      React.createElement("div", {
        className: `h-full rounded-full transition-all duration-300 ${colorClass}`,
        style: { width: `${widthPercent}%` },
      })
    )
  );
}

function renderSistemaCard(): React.ReactElement {
  if (statusError) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400 truncate" },
          "Sistema"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400 break-words" },
        React.createElement(
          "p",
          null,
          `Error fetching status: ${statusError instanceof Error ? statusError.message : String(statusError)}`
        )
      )
    );
  }

  if (!currentStatus) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
          "Sistema"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-4 font-mono text-sm text-slate-400" },
        "Cargando sistema..."
      )
    );
  }

  const system = currentStatus.system;
  const screen = currentStatus.screen;

  let turingStateText = "No presente";
  let turingBadgeVariant: "success" | "secondary" | "destructive" = "destructive";

  if (screen?.simulate) {
    turingStateText = "Simulada";
    turingBadgeVariant = "secondary";
  } else if (screen?.present) {
    turingStateText = "Conectada";
    turingBadgeVariant = "success";
  } else {
    turingStateText = "No presente";
    turingBadgeVariant = "destructive";
  }

  const brightnessDisplay =
    screen && typeof screen.brightness === "number"
      ? `${screen.brightness}%`
      : "n/d";

  const orientationDisplay =
    currentConfig && typeof currentConfig.orientation === "string" && currentConfig.orientation.trim() !== ""
      ? currentConfig.orientation.trim()
      : "n/d";

  const refreshDisplay =
    currentConfig && typeof currentConfig.refresh_interval_seconds === "number" && !Number.isNaN(currentConfig.refresh_interval_seconds) && currentConfig.refresh_interval_seconds > 0
      ? `${currentConfig.refresh_interval_seconds}s`
      : "n/d";

  return React.createElement(
    Card,
    { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      null,
      React.createElement(
        CardTitle,
        { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
        "Sistema"
      )
    ),
    React.createElement(
      CardContent,
      { className: "space-y-4 min-w-0" },
      React.createElement(
        "div",
        { className: "space-y-3 min-w-0" },
        renderMetricBar("CPU", system?.cpu),
        renderMetricBar("RAM", system?.ram),
        renderMetricBar("GPU", system?.gpu)
      ),
      React.createElement(
        "div",
        { className: "flex items-center justify-between pt-3 border-t border-slate-800 text-sm gap-2 min-w-0" },
        React.createElement(
          "div",
          { className: "flex items-center gap-2 min-w-0" },
          React.createElement("span", { className: "text-slate-400 font-medium shrink-0" }, "Turing"),
          React.createElement(
            Badge,
            { variant: turingBadgeVariant, className: "shrink-0" },
            turingStateText
          )
        )
      ),
      React.createElement(
        "div",
        { className: "flex items-center justify-between text-sm gap-2 min-w-0" },
        React.createElement("span", { className: "text-slate-400 font-medium shrink-0" }, "Pantalla"),
        React.createElement(
          "span",
          { className: "font-mono text-xs text-slate-300 truncate text-right", title: `${orientationDisplay} · ${refreshDisplay} · Brillo: ${brightnessDisplay}` },
          `${orientationDisplay} · ${refreshDisplay} · Brillo: ${brightnessDisplay}`
        )
      ),
      React.createElement(
        "div",
        { className: "space-y-1.5 pt-2 border-t border-slate-800 min-w-0" },
        React.createElement(
          "div",
          { className: "flex items-center justify-between text-xs font-mono gap-2 min-w-0" },
          React.createElement(
            "label",
            { htmlFor: "brightness-slider", className: "font-semibold text-slate-400 uppercase tracking-wider truncate" },
            "Control de brillo"
          ),
          React.createElement(
            "div",
            { className: "flex items-center gap-2 shrink-0" },
            brightnessStatusText
              ? React.createElement(
                  Badge,
                  {
                    variant: brightnessStatus === "applied" ? "success" : "destructive",
                    className: "text-[10px] px-1.5 py-0 font-mono shrink-0",
                  },
                  brightnessStatusText
                )
              : null,
            React.createElement(
              "span",
              { className: "text-slate-200 font-semibold" },
              `${sliderBrightness}%`
            )
          )
        ),
        React.createElement("input", {
          key: "brightness-slider",
          id: "brightness-slider",
          type: "range",
          min: 0,
          max: 100,
          value: sliderBrightness,
          onChange: handleBrightnessChange,
          className: "w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500",
        })
      )
    )
  );
}

function renderWslCard(): React.ReactElement {
  if (wslError) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400 truncate" },
          "WSL"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400 break-words" },
        React.createElement(
          "p",
          null,
          `Error fetching WSL: ${wslError instanceof Error ? wslError.message : String(wslError)}`
        )
      )
    );
  }

  if (!currentWsl) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
          "WSL"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-4 font-mono text-sm text-slate-400" },
        "Cargando WSL..."
      )
    );
  }

  const distrosList = Array.isArray(currentWsl.distros) ? currentWsl.distros : [];

  return React.createElement(
    Card,
    { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      { className: "flex flex-row items-center justify-between space-y-0 gap-2 min-w-0" },
      React.createElement(
        CardTitle,
        { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
        "WSL"
      ),
      React.createElement(
        Badge,
        { variant: currentWsl.available ? "success" : "destructive", className: "shrink-0" },
        currentWsl.available ? "Running" : "no disponible"
      )
    ),
    React.createElement(
      CardContent,
      { className: "space-y-4 min-w-0" },
      React.createElement(
        "div",
        { className: "space-y-2 min-w-0" },
        React.createElement(
          "div",
          { className: "text-xs font-semibold text-slate-400 uppercase tracking-wider truncate" },
          `Distros (${distrosList.length})`
        ),
        React.createElement(
          "div",
          { className: "max-h-48 overflow-y-auto space-y-1.5 pr-1 font-mono text-xs text-slate-300" },
          distrosList.length === 0
            ? React.createElement(
                "div",
                { className: "text-slate-500 italic py-1" },
                "sin distros"
              )
            : distrosList.map((distro: string) =>
                React.createElement(
                  "div",
                  {
                    key: distro,
                    className: "py-1.5 px-2.5 rounded bg-slate-900 border border-slate-800 text-slate-300 flex justify-between items-center gap-2 min-w-0",
                  },
                  React.createElement("span", { className: "font-semibold text-slate-200 truncate" }, distro)
                )
              )
        )
      )
    )
  );
}

function renderTransmisionCard(): React.ReactElement {
  if (statusError) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400 truncate" },
          "Transmisión"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400 break-words" },
        React.createElement(
          "p",
          null,
          `Error fetching status: ${statusError instanceof Error ? statusError.message : String(statusError)}`
        )
      )
    );
  }

  if (!currentStatus) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
          "Transmisión"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-4 font-mono text-sm text-slate-400" },
        "Cargando transmisión..."
      )
    );
  }

  const tx = currentStatus.transmission;

  if (!tx) {
    return React.createElement(
      Card,
      { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        { className: "flex flex-row items-center justify-between space-y-0 gap-2 min-w-0" },
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
          "Transmisión"
        ),
        React.createElement(
          Badge,
          { variant: "secondary", className: "shrink-0" },
          "sin datos"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-4 font-mono text-sm text-slate-500 italic py-1 break-words" },
        "sin datos"
      )
    );
  }

  const kbAprox = typeof tx.bytes_sent_total === "number"
    ? (tx.bytes_sent_total / 1024).toFixed(1)
    : "0.0";
  const elapsedMs = typeof tx.last_elapsed_ms === "number"
    ? Number(tx.last_elapsed_ms.toFixed(1))
    : 0;

  return React.createElement(
    Card,
    { className: "w-full min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      { className: "flex flex-row items-center justify-between space-y-0 gap-2 min-w-0" },
      React.createElement(
        CardTitle,
        { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
        "Transmisión"
      ),
      React.createElement(
        Badge,
        { variant: "default", className: "shrink-0" },
        `${tx.frames_total} frames`
      )
    ),
    React.createElement(
      CardContent,
      { className: "space-y-4 min-w-0" },
      React.createElement(
        "div",
        { className: "space-y-2 min-w-0" },
        React.createElement(
          "div",
          { className: "space-y-1 min-w-0" },
          React.createElement(
            "div",
            { className: "flex justify-between text-xs font-mono gap-2 min-w-0" },
            React.createElement("span", { className: "font-semibold text-slate-400 uppercase tracking-wider shrink-0" }, "Frames totales"),
            React.createElement("span", { className: "text-slate-200 font-semibold truncate text-right" }, String(tx.frames_total))
          ),
          React.createElement(
            "div",
            { className: "flex justify-between text-xs font-mono text-slate-400 gap-2 min-w-0" },
            React.createElement("span", { className: "shrink-0" }, "Full / Partial"),
            React.createElement("span", { className: "truncate text-right" }, `${tx.full_frames} full / ${tx.partial_frames} partial`)
          )
        ),
        React.createElement(
          "div",
          { className: "flex justify-between text-xs font-mono gap-2 min-w-0" },
          React.createElement("span", { className: "font-semibold text-slate-400 uppercase tracking-wider shrink-0" }, "Tiles enviados"),
          React.createElement("span", { className: "text-slate-200 font-semibold truncate text-right" }, String(tx.tiles_sent_total))
        ),
        React.createElement(
          "div",
          { className: "flex justify-between text-xs font-mono gap-2 min-w-0" },
          React.createElement("span", { className: "font-semibold text-slate-400 uppercase tracking-wider shrink-0" }, "KB/s aprox"),
          React.createElement("span", { className: "text-slate-200 font-semibold truncate text-right" }, `${kbAprox} KB/s`)
        )
      ),
      React.createElement(
        "div",
        { className: "flex items-center justify-between pt-3 border-t border-slate-800 text-sm gap-2 min-w-0" },
        React.createElement(
          "div",
          { className: "flex items-center gap-2 min-w-0" },
          React.createElement("span", { className: "text-slate-400 font-medium shrink-0" }, "Último envío"),
          React.createElement(
            Badge,
            { variant: tx.last_kind === "full" ? "default" : "secondary", className: "shrink-0" },
            tx.last_kind
          )
        ),
        React.createElement(
          "span",
          { className: "font-mono text-xs text-slate-300 truncate text-right" },
          `${elapsedMs} ms (${tx.last_tiles} tiles)`
        )
      )
    )
  );
}

export function handleEditRule(rule: RuleConfig): void {
  editingRule = { ...rule };
  originalRuleId = rule.id;
  rulesSaveError = null;
  renderApp();
}

export function handleCreateRule(): void {
  const fallbackMood = currentRules?.moods?.[0] ?? DEFAULT_MOODS[0];
  editingRule = {
    id: "",
    metric: "",
    op: ">=",
    value: 0,
    mood: fallbackMood,
    priority: 0,
  };
  originalRuleId = null;
  rulesSaveError = null;
  renderApp();
}

export function handleCancelEdit(): void {
  editingRule = null;
  originalRuleId = null;
  rulesSaveError = null;
  renderApp();
}

export async function saveRules(payload: RulesPayload): Promise<boolean> {
  try {
    const response = await fetch(`${baseUrl()}/api/rules`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Origin": baseUrl(),
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const errorData = (await response.json()) as { error?: string };
        if (errorData && typeof errorData.error === "string" && errorData.error.trim() !== "") {
          message = errorData.error;
        }
      } catch {
        // fallback to status code
      }
      rulesSaveError = message;
      renderApp();
      return false;
    }

    rulesSaveError = null;
    await fetchRules();
    renderApp();
    return true;
  } catch (err) {
    rulesSaveError = err instanceof Error ? err.message : String(err);
    renderApp();
    return false;
  }
}

export async function handleSaveRule(rule: RuleConfig): Promise<void> {
  if (!currentRules) return;

  const currentRulesList = Array.isArray(currentRules.rules) ? currentRules.rules : [];
  const ruleAsRule: Rule = {
    id: rule.id,
    metric: rule.metric,
    op: rule.op,
    value: rule.value,
    mood: rule.mood,
    priority: typeof rule.priority === "number" ? rule.priority : 0,
    ...(rule.for !== undefined ? { for: rule.for } : {}),
    ...(rule.for_seconds !== undefined ? { for_seconds: rule.for_seconds } : {}),
    ...(rule.release !== undefined ? { release: rule.release } : {}),
    ...(rule.release_for !== undefined ? { release_for: rule.release_for } : {}),
  };

  let updatedRules: Rule[];
  if (originalRuleId) {
    const exists = currentRulesList.some((r) => r.id === originalRuleId);
    if (exists) {
      updatedRules = currentRulesList.map((r) => (r.id === originalRuleId ? ruleAsRule : r));
    } else {
      updatedRules = [...currentRulesList, ruleAsRule];
    }
  } else {
    const exists = currentRulesList.some((r) => r.id === rule.id);
    if (exists) {
      updatedRules = currentRulesList.map((r) => (r.id === rule.id ? ruleAsRule : r));
    } else {
      updatedRules = [...currentRulesList, ruleAsRule];
    }
  }

  const payload: RulesPayload = {
    moods: currentRules.moods ?? [...DEFAULT_MOODS],
    default_mood: currentRules.default_mood ?? null,
    rules: updatedRules,
  };

  const success = await saveRules(payload);
  if (success) {
    editingRule = null;
    originalRuleId = null;
    renderApp();
  }
}

export async function handleDeleteRule(id: string): Promise<void> {
  const ok = window.confirm(`¿Eliminar regla "${id}"?`);
  if (!ok) return;

  if (!currentRules) return;

  const currentRulesList = Array.isArray(currentRules.rules) ? currentRules.rules : [];
  const updatedRules = currentRulesList.filter((r) => r.id !== id);

  const payload: RulesPayload = {
    moods: currentRules.moods ?? [...DEFAULT_MOODS],
    default_mood: currentRules.default_mood ?? null,
    rules: updatedRules,
  };

  const success = await saveRules(payload);
  if (success && editingRule?.id === id) {
    editingRule = null;
    originalRuleId = null;
    renderApp();
  }
}

export function renderReglasCard(): React.ReactElement {
  if (rulesError) {
    return React.createElement(
      Card,
      { className: "w-full col-span-1 md:col-span-2 xl:col-span-3 min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400 truncate" },
          "Reglas"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400 break-words" },
        React.createElement(
          "p",
          null,
          `Error fetching rules: ${rulesError instanceof Error ? rulesError.message : String(rulesError)}`
        )
      )
    );
  }

  if (!currentRules) {
    return React.createElement(
      Card,
      { className: "w-full col-span-1 md:col-span-2 xl:col-span-3 min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
          "Reglas"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-4 font-mono text-sm text-slate-400" },
        "Cargando reglas..."
      )
    );
  }

  const rulesList = Array.isArray(currentRules.rules) ? currentRules.rules : [];
  const moodsList = Array.isArray(currentRules.moods) && currentRules.moods.length > 0
    ? currentRules.moods
    : [...DEFAULT_MOODS];

  return React.createElement(
    Card,
    { className: "w-full col-span-1 md:col-span-2 xl:col-span-3 min-w-0 overflow-hidden bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      { className: "flex flex-row items-center justify-between pb-4 border-b border-slate-800 gap-4 min-w-0" },
      React.createElement(
        "div",
        { className: "min-w-0" },
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
          "Reglas"
        ),
        React.createElement(
          "p",
          { className: "text-xs text-slate-400 mt-1 truncate" },
          `Configuración y evaluación de alertas (${rulesList.length} reglas)`
        )
      ),
      React.createElement(
        Button,
        {
          size: "sm",
          onClick: handleCreateRule,
          className: "bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs px-3 py-1.5 shrink-0",
        },
        "+ Nueva Regla"
      )
    ),
    React.createElement(
      CardContent,
      { className: "pt-6 space-y-6 min-w-0" },
      rulesSaveError
        ? React.createElement(
            "div",
            {
              className: "p-3.5 rounded-lg border border-red-600/80 bg-red-950/60 text-red-200 text-xs font-mono space-y-1 shadow-sm break-words",
            },
            React.createElement(
              "p",
              { className: "font-bold text-red-100 font-sans" },
              "Error al guardar reglas en el servidor:"
            ),
            React.createElement("p", null, rulesSaveError)
          )
        : null,
      editingRule !== null
        ? React.createElement(
            "div",
            { className: "p-4 rounded-lg bg-slate-900/60 border border-slate-800 flex justify-center min-w-0 overflow-hidden" },
            React.createElement(RuleForm, {
              initial: editingRule,
              moods: moodsList,
              onSubmit: handleSaveRule,
              onCancel: handleCancelEdit,
            })
          )
        : null,
      React.createElement(
        "div",
        { className: "grid grid-cols-1 lg:grid-cols-2 gap-6 items-start min-w-0" },
        React.createElement(RuleList, {
          rules: rulesList,
          onEdit: handleEditRule,
          onDelete: handleDeleteRule,
        }),
        React.createElement(RulePreviewCard, {
          rules: rulesList as RuleConfig[],
          moods: moodsList,
        })
      )
    )
  );
}

export const cardRenderers: Record<CardId, () => React.ReactElement> = {
  servicios: renderServiciosCard,
  mascota: renderMascotaCard,
  "mascota-detalle": renderMascotaDetailCard,
  sistema: renderSistemaCard,
  transmision: renderTransmisionCard,
  wsl: renderWslCard,
  reglas: renderReglasCard,
};

export function handleToggleCardVisibility(cardId: CardId, checked: boolean): void {
  if (checked) {
    if (!visibleCards.includes(cardId)) {
      visibleCards = [...visibleCards, cardId];
    }
  } else {
    visibleCards = visibleCards.filter((id) => id !== cardId);
  }
  saveVisible(visibleCards);

  currentTheme = updateThemeCardVisibility(currentTheme, cardId, checked);
  debouncedSaveTheme(currentTheme);

  renderApp();
}

export async function handleMascotVariantChange(
  e: React.ChangeEvent<HTMLSelectElement>
): Promise<void> {
  const nextVariant = e.target.value;
  const validVariant: MascotVariant = isMascotVariant(nextVariant) ? nextVariant : "default";
  const nextTheme: ThemeConfig = {
    ...currentTheme,
    mascotVariant: validVariant,
  };
  currentTheme = nextTheme;
  mascotStatus = "idle";
  mascotStatusText = "";
  renderApp();

  try {
    const success = await saveTheme(nextTheme);
    if (currentTheme.mascotVariant === validVariant) {
      if (success) {
        mascotStatus = "applied";
        mascotStatusText = "Aplicado";
      } else {
        mascotStatus = "error";
        mascotStatusText = "Error";
      }
      renderApp();
    }
  } catch (err) {
    console.error("Failed to update mascot variant:", err);
    if (currentTheme.mascotVariant === validVariant) {
      mascotStatus = "error";
      mascotStatusText = "Error";
      renderApp();
    }
  }
}

export async function handlePickBackgroundImage(): Promise<void> {
  try {
    backgroundError = null;
    const file = await pickImageFile();
    if (!file) return;
    const dataUrl = await fileToThemeBackground(file);
    pendingBackgroundDataUrl = dataUrl;
    backgroundError = null;
    renderApp();
  } catch (err) {
    backgroundError = err instanceof Error ? err.message : String(err);
    renderApp();
  }
}

export async function handleFileInputChange(
  e: React.ChangeEvent<HTMLInputElement>
): Promise<void> {
  const file = e.target.files?.[0];
  if (!file) return;
  try {
    backgroundError = null;
    const maxSize = 2 * 1024 * 1024; // 2MB
    if (file.size > maxSize) {
      throw new Error(`File size ${(file.size / 1024 / 1024).toFixed(2)}MB exceeds 2MB limit`);
    }
    const dataUrl = await fileToThemeBackground(file);
    pendingBackgroundDataUrl = dataUrl;
    backgroundError = null;
    renderApp();
  } catch (err) {
    backgroundError = err instanceof Error ? err.message : String(err);
    renderApp();
  } finally {
    e.target.value = "";
  }
}

export async function handleConfirmBackground(): Promise<void> {
  if (!pendingBackgroundDataUrl) return;
  const nextTheme: ThemeConfig = {
    ...currentTheme,
    backgroundImage: pendingBackgroundDataUrl,
  };
  currentTheme = nextTheme;
  pendingBackgroundDataUrl = null;
  backgroundError = null;
  renderApp();
  await saveTheme(nextTheme);
  renderApp();
}

export function handleCancelPendingBackground(): void {
  pendingBackgroundDataUrl = null;
  backgroundError = null;
  renderApp();
}

export async function handleRemoveBackground(): Promise<void> {
  const nextTheme: ThemeConfig = {
    ...currentTheme,
    backgroundImage: null,
  };
  currentTheme = nextTheme;
  pendingBackgroundDataUrl = null;
  backgroundError = null;
  renderApp();
  await saveTheme(nextTheme);
  renderApp();
}

export function renderTemaCard(): React.ReactElement {
  const allCards = getAllCardIds();
  const activeThumbnail = pendingBackgroundDataUrl || currentTheme.backgroundImage;
  const currentVariant = isMascotVariant(currentTheme.mascotVariant)
    ? currentTheme.mascotVariant
    : "default";

  return React.createElement(
    Card,
    {
      className:
        "w-full max-w-[96rem] bg-slate-950 text-slate-50 border-slate-800 shadow-xl min-w-0 overflow-hidden",
    },
    React.createElement(
      CardHeader,
      {
        className:
          "flex flex-row items-center justify-between pb-4 border-b border-slate-800 gap-4 min-w-0",
      },
      React.createElement(
        "div",
        { className: "min-w-0" },
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50 truncate" },
          "Tema"
        ),
        React.createElement(
          "p",
          { className: "text-xs text-slate-400 mt-1 truncate" },
          "Personalización visual, fondo y visibilidad de tarjetas"
        )
      ),
      React.createElement(
        "div",
        { className: "flex items-center gap-2 shrink-0" },
        React.createElement("span", { className: "text-xs text-slate-400 font-medium" }, "Tema:"),
        React.createElement(
          Badge,
          { variant: "default", className: "text-xs font-semibold px-2.5 py-0.5" },
          currentTheme.name || currentTheme.id || "Por defecto"
        )
      )
    ),
    React.createElement(
      CardContent,
      { className: "pt-6 space-y-6 min-w-0" },
      backgroundError
        ? React.createElement(
            "div",
            {
              className:
                "p-3 rounded-lg border border-red-600/80 bg-red-950/60 text-red-200 text-xs font-mono space-y-1 shadow-sm break-words",
            },
            React.createElement("p", { className: "font-bold text-red-100 font-sans" }, "Error de fondo:"),
            React.createElement("p", null, backgroundError)
          )
        : null,
      React.createElement(
        "div",
        { className: "grid grid-cols-1 md:grid-cols-2 gap-6 items-start min-w-0" },
        React.createElement(
          "div",
          { className: "space-y-2 min-w-0" },
          React.createElement(
            "div",
            { className: "flex items-center justify-between text-xs font-mono gap-2 min-w-0" },
            React.createElement(
              "label",
              {
                htmlFor: "mascot-variant-select",
                className: "font-semibold text-slate-400 uppercase tracking-wider truncate",
              },
              "Variante de Mascota"
            ),
            mascotStatusText
              ? React.createElement(
                  Badge,
                  {
                    variant: mascotStatus === "applied" ? "success" : "destructive",
                    className: "text-[10px] px-1.5 py-0 font-mono shrink-0",
                  },
                  mascotStatusText
                )
              : null
          ),
          React.createElement(
            "select",
            {
              id: "mascot-variant-select",
              value: currentVariant,
              onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void handleMascotVariantChange(e),
              className:
                "h-9 w-full rounded-md bg-slate-900 border border-slate-800 text-slate-200 text-xs px-3 py-1 font-mono focus:outline-none focus:ring-1 focus:ring-slate-400 cursor-pointer",
            },
            MASCOT_OPTIONS.map((opt) =>
              React.createElement("option", { key: opt.value, value: opt.value }, opt.label)
            )
          ),
          React.createElement(
            "p",
            { className: "text-[11px] text-slate-500 font-mono" },
            `Variante activa: ${currentVariant}`
          )
        ),
        React.createElement(
          "div",
          { className: "space-y-2 min-w-0" },
          React.createElement(
            "label",
            {
              htmlFor: "theme-bg-file-input",
              className: "text-xs font-semibold text-slate-400 uppercase tracking-wider block truncate",
            },
            "Fondo de Pantalla"
          ),
          React.createElement(
            "div",
            { className: "flex flex-wrap items-center gap-4 min-w-0" },
            activeThumbnail
              ? React.createElement(
                  "div",
                  {
                    className:
                      "flex items-center gap-3 p-2 bg-slate-900/60 rounded-lg border border-slate-800 shrink-0 min-w-0",
                  },
                  React.createElement("img", {
                    src: activeThumbnail,
                    alt: "Miniatura fondo",
                    className: "w-20 h-12 object-cover rounded border border-slate-700 shadow-inner shrink-0",
                  }),
                  React.createElement(
                    "div",
                    { className: "flex flex-col gap-1.5 min-w-0" },
                    React.createElement(
                      "span",
                      { className: "text-xs font-mono text-slate-300 truncate" },
                      pendingBackgroundDataUrl ? "Vista previa (sin confirmar)" : "Fondo activo"
                    ),
                    React.createElement(
                      "div",
                      { className: "flex items-center gap-1.5 flex-wrap" },
                      pendingBackgroundDataUrl
                        ? [
                            React.createElement(
                              Button,
                              {
                                key: "confirm-bg",
                                size: "sm",
                                onClick: () => void handleConfirmBackground(),
                                className:
                                  "h-7 text-xs bg-emerald-600 hover:bg-emerald-500 text-white px-2.5 shrink-0",
                              },
                              "Confirmar"
                            ),
                            React.createElement(
                              Button,
                              {
                                key: "cancel-bg",
                                size: "sm",
                                variant: "outline",
                                onClick: handleCancelPendingBackground,
                                className: "h-7 text-xs px-2.5 shrink-0",
                              },
                              "Cancelar"
                            ),
                          ]
                        : [
                            React.createElement(
                              Button,
                              {
                                key: "change-bg",
                                size: "sm",
                                variant: "outline",
                                onClick: () => void handlePickBackgroundImage(),
                                className: "h-7 text-xs px-2.5 shrink-0",
                              },
                              "Cambiar"
                            ),
                            React.createElement(
                              Button,
                              {
                                key: "remove-bg",
                                size: "sm",
                                variant: "destructive",
                                onClick: () => void handleRemoveBackground(),
                                className: "h-7 text-xs px-2.5 shrink-0",
                              },
                              "Quitar"
                            ),
                          ]
                    )
                  )
                )
              : React.createElement(
                  "div",
                  {
                    className:
                      "w-20 h-12 rounded border border-dashed border-slate-800 bg-slate-900/40 flex items-center justify-center text-[10px] text-slate-500 font-mono shrink-0",
                  },
                  "Sin fondo"
                ),
            React.createElement(
              "div",
              { className: "flex flex-col gap-2 min-w-0" },
              React.createElement("input", {
                id: "theme-bg-file-input",
                type: "file",
                accept: "image/png,image/jpeg,image/webp",
                onChange: (e: React.ChangeEvent<HTMLInputElement>) => void handleFileInputChange(e),
                className:
                  "text-xs text-slate-400 file:mr-2 file:py-1 file:px-2.5 file:rounded file:border-0 file:text-xs file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 cursor-pointer",
              }),
              React.createElement(
                "span",
                { className: "text-[11px] text-slate-500" },
                "PNG, JPEG o WebP (máx 2MB, WebP ≤400KB)"
              )
            )
          )
        )
      ),
      React.createElement(
        "div",
        { className: "space-y-2 pt-4 border-t border-slate-800 min-w-0" },
        React.createElement(
          "div",
          { className: "text-xs font-semibold text-slate-400 uppercase tracking-wider truncate" },
          "Visibilidad de tarjetas"
        ),
        React.createElement(
          "div",
          { className: "flex flex-wrap items-center gap-3 min-w-0" },
          allCards.map((cardId) =>
            React.createElement(
              "label",
              {
                key: cardId,
                className:
                  "flex items-center gap-2 text-sm text-slate-300 cursor-pointer hover:text-slate-100 transition-colors shrink-0",
              },
              React.createElement("input", {
                type: "checkbox",
                checked: visibleCards.includes(cardId),
                onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
                  handleToggleCardVisibility(cardId, e.target.checked);
                },
                className:
                  "w-4 h-4 rounded border-slate-700 bg-slate-800 text-emerald-500 focus:ring-emerald-500 focus:ring-2",
              }),
              getCardLabel(cardId)
            )
          )
        )
      )
    )
  );
}

export function renderCustomizeBar(): React.ReactElement {
  return renderTemaCard();
}

export function renderApp(): void {
  const currentRoot = getRoot();
  if (!currentRoot) return;
  currentRoot.render(React.createElement(App));
}

export async function fetchStatus(): Promise<void> {
  try {
    const response = await fetch(`${baseUrl()}/api/status`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    currentStatus = (await response.json()) as StatusSnapshot;
    statusError = null;
  } catch (err) {
    statusError = err;
  }
}

export async function fetchRules(): Promise<void> {
  try {
    const response = await fetch(`${baseUrl()}/api/rules`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    currentRules = (await response.json()) as RulesPayload;
    rulesError = null;
  } catch (err) {
    rulesError = err;
  }
}

export function handleBrightnessChange(e: React.ChangeEvent<HTMLInputElement>): void {
  const nextValue = Math.min(100, Math.max(0, parseInt(e.target.value, 10) || 0));
  sliderBrightness = nextValue;
  brightnessStatus = "idle";
  brightnessStatusText = "";
  renderApp();

  if (debounceTimer !== null) {
    clearTimeout(debounceTimer);
  }

  debounceTimer = setTimeout(() => {
    debounceTimer = null;
    void sendBrightness(nextValue);
  }, 300);
}

export async function sendBrightness(val: number): Promise<void> {
  try {
    const response = await fetch(`${baseUrl()}/api/config`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Origin": baseUrl(),
      },
      body: JSON.stringify({ brightness: val }),
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const saved = (await response.json()) as AppConfig;
    if (val === sliderBrightness) {
      if (typeof saved.brightness === "number") {
        sliderBrightness = saved.brightness;
      }
      currentConfig = saved;
      brightnessStatus = "applied";
      brightnessStatusText = "Aplicado";
      void fetchStatus().then(renderApp);
    }
  } catch (err) {
    console.error("Failed to update brightness:", err);
    if (val === sliderBrightness) {
      brightnessStatus = "error";
      brightnessStatusText = "Error";
    }
  }
  renderApp();
}

export async function fetchConfig(): Promise<void> {
  try {
    const response = await fetch(`${baseUrl()}/api/config`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    currentConfig = (await response.json()) as AppConfig;
    if (!isBrightnessInitialized && typeof currentConfig.brightness === "number") {
      sliderBrightness = currentConfig.brightness;
      isBrightnessInitialized = true;
    }
  } catch (err) {
    console.warn("Error fetching config:", err);
  }
}

export async function fetchAll(): Promise<void> {
  await Promise.all([fetchStatus(), fetchRules(), fetchConfig()]);
  renderApp();
}

export async function fetchServices(): Promise<void> {
  try {
    const response = await fetch(`${baseUrl()}/api/services`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    currentServices = (await response.json()) as ServiceStatus[];
    servicesError = null;
  } catch (err) {
    servicesError = err;
  }
}

export async function fetchWsl(): Promise<void> {
  try {
    const response = await fetch(`${baseUrl()}/api/wsl`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    currentWsl = (await response.json()) as WslStatus;
    wslError = null;
  } catch (err) {
    wslError = err;
  }
}

export async function pollServices(): Promise<void> {
  await Promise.all([fetchServices(), fetchWsl()]);
  renderApp();
}

export async function fetchTheme(): Promise<void> {
  try {
    const response = await fetch(`${baseUrl()}/api/theme`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = (await response.json()) as ThemeConfig;
    if (data && typeof data.id === "string" && Array.isArray(data.cards)) {
      const mascotVariant = isMascotVariant(data.mascotVariant)
        ? data.mascotVariant
        : "default";
      currentTheme = {
        ...data,
        mascotVariant,
        backgroundImage:
          data.backgroundImage ?? loadSavedBackground() ?? currentTheme?.backgroundImage,
      };
    } else {
      currentTheme = {
        ...getDefaultTheme(),
        backgroundImage: loadSavedBackground(),
      };
    }
  } catch (err) {
    console.warn("Error fetching theme, using default:", err);
    currentTheme = {
      ...getDefaultTheme(),
      backgroundImage: loadSavedBackground(),
    };
  }
  visibleCards = getOrderedVisibleCards(currentTheme);
  saveVisible(visibleCards);
}

export async function saveTheme(theme: ThemeConfig): Promise<boolean> {
  saveStoredBackground(theme.backgroundImage);
  try {
    const response = await fetch(`${baseUrl()}/api/theme`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Origin": baseUrl(),
      },
      body: JSON.stringify(theme),
    });
    if (!response.ok) {
      console.warn(`Failed to save theme: HTTP ${response.status}`);
      return false;
    }
    const saved = (await response.json()) as ThemeConfig;
    if (saved && typeof saved.id === "string") {
      const mascotVariant = isMascotVariant(saved.mascotVariant)
        ? saved.mascotVariant
        : isMascotVariant(theme.mascotVariant)
          ? theme.mascotVariant
          : "default";
      currentTheme = {
        ...theme,
        ...saved,
        mascotVariant,
        backgroundImage:
          theme.backgroundImage ?? saved.backgroundImage ?? loadSavedBackground(),
      };
    }
    return true;
  } catch (err) {
    console.warn("Best-effort POST /api/theme failed:", err);
    return false;
  }
}

export function debouncedSaveTheme(theme: ThemeConfig, delayMs = 300): void {
  if (themeDebounceTimer !== null) {
    clearTimeout(themeDebounceTimer);
  }
  themeDebounceTimer = setTimeout(() => {
    themeDebounceTimer = null;
    void saveTheme(theme);
  }, delayMs);
}

async function setupSidecarListener(): Promise<void> {
  try {
    await listen<number>("moka-sidecar-ready", (event) => {
      const port = event.payload;
      if (typeof port === "number" && port > 0) {
        serverPort = port;
        isBrightnessInitialized = false;
        void fetchTheme().then(renderApp);
        void fetchAll();
        void pollServices();
      }
    });
  } catch (err) {
    console.warn("Outside Tauri or failed to listen to moka-sidecar-ready, falling back to 8765:", err);
  }
}

void setupSidecarListener();
renderApp();
void fetchTheme().then(renderApp);
void fetchAll();
void pollServices();
setInterval(fetchAll, POLL_INTERVAL_MS);
setInterval(pollServices, SERVICES_POLL_INTERVAL_MS);

