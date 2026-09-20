import "./index.css";
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { listen } from "@tauri-apps/api/event";
import type { StatusSnapshot, RulesPayload, Rule, ServiceStatus, WslStatus } from "./types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

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

function getRoot(): Root | null {
  if (root) return root;
  const container = document.getElementById("status-container") || document.getElementById("root");
  if (!container) return null;
  root = createRoot(container);
  return root;
}

function renderServiciosCard(): React.ReactElement {
  if (servicesError) {
    return React.createElement(
      Card,
      { className: "w-full max-w-md bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400" },
          "Servicios"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400" },
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
      { className: "w-full max-w-md bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50" },
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
    { className: "w-full max-w-md bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      null,
      React.createElement(
        CardTitle,
        { className: "text-xl font-bold tracking-tight text-slate-50" },
        "Servicios"
      )
    ),
    React.createElement(
      CardContent,
      { className: "space-y-4" },
      React.createElement(
        "div",
        { className: "space-y-2" },
        React.createElement(
          "div",
          { className: "text-xs font-semibold text-slate-400 uppercase tracking-wider" },
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
                    className: "py-1.5 px-2.5 rounded bg-slate-900 border border-slate-800 text-slate-300 flex justify-between items-center",
                  },
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-1.5" },
                    React.createElement("span", { className: "font-semibold text-slate-200" }, svc.name),
                    React.createElement("span", { className: "text-slate-500 text-xs" }, `:${svc.port}`)
                  ),
                  React.createElement(
                    Badge,
                    { variant: svc.reachable ? "success" : "destructive" },
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
      { className: "w-full max-w-md bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400" },
          "Mascota"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400" },
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
      { className: "w-full max-w-md bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50" },
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
    { className: "w-full max-w-md bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      null,
      React.createElement(
        CardTitle,
        { className: "text-xl font-bold tracking-tight text-slate-50" },
        "Mascota"
      )
    ),
    React.createElement(
      CardContent,
      { className: "space-y-4" },
      React.createElement(
        "div",
        { className: "flex items-center justify-between pb-3 border-b border-slate-800" },
        React.createElement(
          "span",
          { className: "text-sm text-slate-400 font-medium" },
          "Mood actual"
        ),
        React.createElement(
          Badge,
          {
            variant: "default",
            className: "text-base font-bold px-3 py-1 uppercase tracking-wide",
          },
          moodDisplay
        )
      ),
      React.createElement(
        "div",
        { className: "space-y-2" },
        React.createElement(
          "div",
          { className: "text-xs font-semibold text-slate-400 uppercase tracking-wider" },
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
                    className: "py-1.5 px-2.5 rounded bg-slate-900 border border-slate-800 text-slate-300 flex justify-between items-center",
                  },
                  `${rule.id} → ${rule.mood}`
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
    { className: "space-y-1.5" },
    React.createElement(
      "div",
      { className: "flex justify-between text-xs font-mono text-slate-300" },
      React.createElement("span", { className: "font-semibold text-slate-400 uppercase tracking-wider" }, label),
      React.createElement("span", null, displayVal)
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
      { className: "w-full max-w-md bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400" },
          "Sistema"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400" },
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
      { className: "w-full max-w-md bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50" },
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

  return React.createElement(
    Card,
    { className: "w-full max-w-md bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      null,
      React.createElement(
        CardTitle,
        { className: "text-xl font-bold tracking-tight text-slate-50" },
        "Sistema"
      )
    ),
    React.createElement(
      CardContent,
      { className: "space-y-4" },
      React.createElement(
        "div",
        { className: "space-y-3" },
        renderMetricBar("CPU", system?.cpu),
        renderMetricBar("RAM", system?.ram),
        renderMetricBar("GPU", system?.gpu)
      ),
      React.createElement(
        "div",
        { className: "flex items-center justify-between pt-3 border-t border-slate-800 text-sm" },
        React.createElement(
          "div",
          { className: "flex items-center gap-2" },
          React.createElement("span", { className: "text-slate-400 font-medium" }, "Turing"),
          React.createElement(
            Badge,
            { variant: turingBadgeVariant },
            turingStateText
          )
        ),
        React.createElement(
          "span",
          { className: "font-mono text-xs text-slate-300" },
          `Brillo: ${brightnessDisplay}`
        )
      )
    )
  );
}

function renderWslCard(): React.ReactElement {
  if (wslError) {
    return React.createElement(
      Card,
      { className: "w-full max-w-md bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400" },
          "WSL"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400" },
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
      { className: "w-full max-w-md bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50" },
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
    { className: "w-full max-w-md bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      { className: "flex flex-row items-center justify-between space-y-0" },
      React.createElement(
        CardTitle,
        { className: "text-xl font-bold tracking-tight text-slate-50" },
        "WSL"
      ),
      React.createElement(
        Badge,
        { variant: currentWsl.available ? "success" : "destructive" },
        currentWsl.available ? "Running" : "no disponible"
      )
    ),
    React.createElement(
      CardContent,
      { className: "space-y-4" },
      React.createElement(
        "div",
        { className: "space-y-2" },
        React.createElement(
          "div",
          { className: "text-xs font-semibold text-slate-400 uppercase tracking-wider" },
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
                    className: "py-1.5 px-2.5 rounded bg-slate-900 border border-slate-800 text-slate-300 flex justify-between items-center",
                  },
                  React.createElement("span", { className: "font-semibold text-slate-200" }, distro)
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
      { className: "w-full max-w-md bg-slate-950 text-slate-50 border-red-900 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-red-400" },
          "Transmisión"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-2 font-mono text-sm text-red-400" },
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
      { className: "w-full max-w-md bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        null,
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50" },
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
      { className: "w-full max-w-md bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
      React.createElement(
        CardHeader,
        { className: "flex flex-row items-center justify-between space-y-0" },
        React.createElement(
          CardTitle,
          { className: "text-xl font-bold tracking-tight text-slate-50" },
          "Transmisión"
        ),
        React.createElement(
          Badge,
          { variant: "secondary" },
          "sin datos"
        )
      ),
      React.createElement(
        CardContent,
        { className: "space-y-4 font-mono text-sm text-slate-500 italic py-1" },
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
    { className: "w-full max-w-md bg-slate-950 text-slate-50 border-slate-800 shadow-xl" },
    React.createElement(
      CardHeader,
      { className: "flex flex-row items-center justify-between space-y-0" },
      React.createElement(
        CardTitle,
        { className: "text-xl font-bold tracking-tight text-slate-50" },
        "Transmisión"
      ),
      React.createElement(
        Badge,
        { variant: "default" },
        `${tx.frames_total} frames`
      )
    ),
    React.createElement(
      CardContent,
      { className: "space-y-4" },
      React.createElement(
        "div",
        { className: "space-y-2" },
        React.createElement(
          "div",
          { className: "space-y-1" },
          React.createElement(
            "div",
            { className: "flex justify-between text-xs font-mono" },
            React.createElement("span", { className: "font-semibold text-slate-400 uppercase tracking-wider" }, "Frames totales"),
            React.createElement("span", { className: "text-slate-200 font-semibold" }, String(tx.frames_total))
          ),
          React.createElement(
            "div",
            { className: "flex justify-between text-xs font-mono text-slate-400" },
            React.createElement("span", null, "Full / Partial"),
            React.createElement("span", null, `${tx.full_frames} full / ${tx.partial_frames} partial`)
          )
        ),
        React.createElement(
          "div",
          { className: "flex justify-between text-xs font-mono" },
          React.createElement("span", { className: "font-semibold text-slate-400 uppercase tracking-wider" }, "Tiles enviados"),
          React.createElement("span", { className: "text-slate-200 font-semibold" }, String(tx.tiles_sent_total))
        ),
        React.createElement(
          "div",
          { className: "flex justify-between text-xs font-mono" },
          React.createElement("span", { className: "font-semibold text-slate-400 uppercase tracking-wider" }, "KB/s aprox"),
          React.createElement("span", { className: "text-slate-200 font-semibold" }, `${kbAprox} KB/s`)
        )
      ),
      React.createElement(
        "div",
        { className: "flex items-center justify-between pt-3 border-t border-slate-800 text-sm" },
        React.createElement(
          "div",
          { className: "flex items-center gap-2" },
          React.createElement("span", { className: "text-slate-400 font-medium" }, "Último envío"),
          React.createElement(
            Badge,
            { variant: tx.last_kind === "full" ? "default" : "secondary" },
            tx.last_kind
          )
        ),
        React.createElement(
          "span",
          { className: "font-mono text-xs text-slate-300" },
          `${elapsedMs} ms (${tx.last_tiles} tiles)`
        )
      )
    )
  );
}

function renderApp(): void {
  const currentRoot = getRoot();
  if (!currentRoot) return;

  currentRoot.render(
    React.createElement(
      "div",
      { className: "min-h-screen bg-slate-950 text-slate-50 p-6 flex justify-center items-start" },
      React.createElement(
        "div",
        { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6 w-full max-w-[96rem]" },
        renderServiciosCard(),
        renderMascotaCard(),
        renderSistemaCard(),
        renderWslCard(),
        renderTransmisionCard()
      )
    )
  );
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

export async function fetchAll(): Promise<void> {
  await Promise.all([fetchStatus(), fetchRules()]);
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

async function setupSidecarListener(): Promise<void> {
  try {
    await listen<number>("moka-sidecar-ready", (event) => {
      const port = event.payload;
      if (typeof port === "number" && port > 0) {
        serverPort = port;
        void fetchAll();
        void pollServices();
      }
    });
  } catch (err) {
    console.warn("Outside Tauri or failed to listen to moka-sidecar-ready, falling back to 8765:", err);
  }
}

void setupSidecarListener();
void fetchAll();
void pollServices();
setInterval(fetchAll, POLL_INTERVAL_MS);
setInterval(pollServices, SERVICES_POLL_INTERVAL_MS);

