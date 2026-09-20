import "./index.css";
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { listen } from "@tauri-apps/api/event";
import type { StatusSnapshot, RulesPayload, Rule } from "./types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const DEFAULT_PORT = 8765;
let serverPort = DEFAULT_PORT;
const POLL_INTERVAL_MS = 2000;

export function baseUrl(): string {
  return `http://127.0.0.1:${serverPort}`;
}

let root: Root | null = null;
let currentStatus: StatusSnapshot | null = null;
let currentRules: RulesPayload | null = null;
let statusError: unknown = null;
let rulesError: unknown = null;

function getRoot(): Root | null {
  if (root) return root;
  const container = document.getElementById("status-container") || document.getElementById("root");
  if (!container) return null;
  root = createRoot(container);
  return root;
}

function renderServiciosCard(): React.ReactElement {
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
          "Servicios"
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
        { className: "flex flex-wrap gap-2 pb-3 border-b border-slate-800" },
        React.createElement(
          Badge,
          { variant: currentStatus.running ? "success" : "destructive" },
          `running: ${currentStatus.running}`
        ),
        React.createElement(
          Badge,
          { variant: currentStatus.agenthub_available ? "success" : "destructive" },
          `agenthub_available: ${currentStatus.agenthub_available}`
        ),
        React.createElement(
          Badge,
          { variant: currentStatus.codexbar_available ? "success" : "destructive" },
          `codexbar_available: ${currentStatus.codexbar_available}`
        )
      ),
      React.createElement(
        "div",
        { className: "space-y-1.5 font-mono text-sm text-slate-300" },
        React.createElement("div", null, `tick: ${currentStatus.tick}`),
        React.createElement("div", null, `has_system: ${currentStatus.has_system}`),
        React.createElement("div", null, `has_snapshot: ${currentStatus.has_snapshot}`),
        React.createElement("div", null, `has_state: ${currentStatus.has_state}`),
        React.createElement("div", null, `mood: ${currentStatus.mood ?? "null"}`)
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

function renderApp(): void {
  const currentRoot = getRoot();
  if (!currentRoot) return;

  currentRoot.render(
    React.createElement(
      "div",
      { className: "min-h-screen bg-slate-950 text-slate-50 p-6 flex justify-center items-start" },
      React.createElement(
        "div",
        { className: "grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-4xl" },
        renderServiciosCard(),
        renderMascotaCard()
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

async function setupSidecarListener(): Promise<void> {
  try {
    await listen<number>("moka-sidecar-ready", (event) => {
      const port = event.payload;
      if (typeof port === "number" && port > 0) {
        serverPort = port;
        void fetchAll();
      }
    });
  } catch (err) {
    console.warn("Outside Tauri or failed to listen to moka-sidecar-ready, falling back to 8765:", err);
  }
}

void setupSidecarListener();
void fetchAll();
setInterval(fetchAll, POLL_INTERVAL_MS);
