import "./index.css";
import { listen } from "@tauri-apps/api/event";
import type { StatusSnapshot } from "./types";

const DEFAULT_PORT = 8765;
let statusUrl = `http://127.0.0.1:${DEFAULT_PORT}/api/status`;
const POLL_INTERVAL_MS = 2000;

function renderStatus(status: StatusSnapshot): void {
  const container = document.getElementById("status-container") || document.getElementById("root");
  if (!container) return;

  container.innerHTML = `
    <div class="font-mono" style="padding: 20px;">
      <h2>Moka TSS Status</h2>
      <ul>
        <li><strong>tick:</strong> ${status.tick}</li>
        <li><strong>running:</strong> ${status.running}</li>
        <li><strong>agenthub_available:</strong> ${status.agenthub_available}</li>
        <li><strong>codexbar_available:</strong> ${status.codexbar_available}</li>
        <li><strong>has_system:</strong> ${status.has_system}</li>
        <li><strong>has_snapshot:</strong> ${status.has_snapshot}</li>
        <li><strong>has_state:</strong> ${status.has_state}</li>
        <li><strong>mood:</strong> ${status.mood}</li>
      </ul>
    </div>
  `;
}

function renderError(error: unknown): void {
  const container = document.getElementById("status-container") || document.getElementById("root");
  if (!container) return;

  container.innerHTML = `
    <div class="font-mono" style="padding: 20px; color: red;">
      <h2>Moka TSS Status</h2>
      <p>Error fetching status: ${error instanceof Error ? error.message : String(error)}</p>
    </div>
  `;
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

