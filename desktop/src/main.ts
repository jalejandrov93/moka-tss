import "./index.css";
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { listen } from "@tauri-apps/api/event";
import type { StatusSnapshot } from "./types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const DEFAULT_PORT = 8765;
let statusUrl = `http://127.0.0.1:${DEFAULT_PORT}/api/status`;
const POLL_INTERVAL_MS = 2000;

let root: Root | null = null;

function getRoot(): Root | null {
  if (root) return root;
  const container = document.getElementById("status-container") || document.getElementById("root");
  if (!container) return null;
  root = createRoot(container);
  return root;
}

function renderStatus(status: StatusSnapshot): void {
  const currentRoot = getRoot();
  if (!currentRoot) return;

  currentRoot.render(
    React.createElement(
      "div",
      { className: "min-h-screen bg-slate-950 text-slate-50 p-6 flex justify-center items-start" },
      React.createElement(
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
              { variant: status.running ? "success" : "destructive" },
              `running: ${status.running}`
            ),
            React.createElement(
              Badge,
              { variant: status.agenthub_available ? "success" : "destructive" },
              `agenthub_available: ${status.agenthub_available}`
            ),
            React.createElement(
              Badge,
              { variant: status.codexbar_available ? "success" : "destructive" },
              `codexbar_available: ${status.codexbar_available}`
            )
          ),
          React.createElement(
            "div",
            { className: "space-y-1.5 font-mono text-sm text-slate-300" },
            React.createElement("div", null, `tick: ${status.tick}`),
            React.createElement("div", null, `has_system: ${status.has_system}`),
            React.createElement("div", null, `has_snapshot: ${status.has_snapshot}`),
            React.createElement("div", null, `has_state: ${status.has_state}`),
            React.createElement("div", null, `mood: ${status.mood ?? "null"}`)
          )
        )
      )
    )
  );
}

function renderError(error: unknown): void {
  const currentRoot = getRoot();
  if (!currentRoot) return;

  currentRoot.render(
    React.createElement(
      "div",
      { className: "min-h-screen bg-slate-950 text-slate-50 p-6 flex justify-center items-start" },
      React.createElement(
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
            `Error fetching status: ${error instanceof Error ? error.message : String(error)}`
          )
        )
      )
    )
  );
}

async function fetchStatus(): Promise<void> {
  try {
    const response = await fetch(statusUrl);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = (await response.json()) as StatusSnapshot;
    renderStatus(data);
  } catch (err) {
    renderError(err);
  }
}

async function setupSidecarListener(): Promise<void> {
  try {
    await listen<number>("moka-sidecar-ready", (event) => {
      const port = event.payload;
      if (typeof port === "number" && port > 0) {
        statusUrl = `http://127.0.0.1:${port}/api/status`;
        void fetchStatus();
      }
    });
  } catch (err) {
    console.warn("Outside Tauri or failed to listen to moka-sidecar-ready, falling back to 8765:", err);
  }
}

void setupSidecarListener();
void fetchStatus();
setInterval(fetchStatus, POLL_INTERVAL_MS);
