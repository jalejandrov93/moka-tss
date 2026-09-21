# Desktop Sidecar Contract (Tauri + Python)

> Status: in development. Rust-side spawn/parse validated on Windows only.

The Tauri desktop shell (`desktop/`) does not drive the display directly.
It launches the Python dashboard as a bundled sidecar and polls its local
HTTP status endpoint for rendering.

## Quick path

1. Bundle Python entry point as `binaries/moka-sidecar` (see `desktop/src-tauri/tauri.conf.json` → `bundle.externalBin`).
2. Tauri spawns it as `moka.py --no-tray` (tray disabled; the desktop shell owns the window).
3. Python starts the loopback config server, then prints `MOKA_READY port=<p>` on stdout (flushed).
4. Tauri parses that line to learn the panel port, then polls `GET /api/status` every 2s (`desktop/src/main.ts`).

## Details

| Topic | Contract |
|-------|----------|
| Sidecar binary | `externalBin: ["binaries/moka-sidecar"]` in `desktop/src-tauri/tauri.conf.json`. Tauri `shell` plugin spawns it. |
| Launch args | `moka.py --no-tray` — see `moka.py:41-44` (`--no-tray` → `tray_enabled=False`). Tray must stay off under Tauri to avoid a second window/icon owner. |
| Ready signal | Exact line `MOKA_READY port=<port>` on stdout, flushed (`library/moka_tss/app.py:54-70` `format_ready_line`, emitted in `MokaApp.run()` after `start_config_server()`). `<port>` is 1–65535; anything else raises `ValueError`. Tauri must read stdout line-delimited and match `MOKA_READY port=(\d+)`. |
| Emission point | Only when the config server started successfully (`port is not None`). No line = panel failed to bind; check logs (`Panel de configuración en http://127.0.0.1:%d`). |
| Consumed endpoint | `GET http://127.0.0.1:<port>/api/status` every 2000 ms (`desktop/src/main.ts:3-4`, `STATUS_URL` + `POLL_INTERVAL_MS`, `setInterval(fetchStatus, ...)`). Served by `library/moka_tss/webconfig.py:322-324` from `MokaApp._get_status` (`library/moka_tss/app.py`), which delegates directly to `status_snapshot()` (MD-2.2 resolved). |
| Services endpoint | `GET http://127.0.0.1:<port>/api/services` on-demand TCP probe endpoint (added in MD-2.9b). Served by `library/moka_tss/webconfig.py` routing to `probe_services(load_config(...).get('services', []))` from `library/moka_tss/services.py`. Returns `Array<{ name, port, health, reachable: boolean, latency_ms: number | null }>` for all configured services. Same loopback Host validation as `/api/status`. |
| WSL endpoint | `GET http://127.0.0.1:<port>/api/wsl` returns `{ available: boolean, distros: string[] }` from `library.moka_tss.wsl.wsl_status()`. On non-Windows `available=false`, distros empty. Same loopback Host validation as `/api/status`. |
| Theme endpoints | `GET /api/theme` returns the saved theme (`{ id, name, cards[], mascotVariant }`); `POST /api/theme` validates (non-empty id/name, cards with boolean visible, order int >= 0, optional string sensors) and saves atomically. Same Host/Origin/JSON checks as `/api/config`. |
| Status payload | `{ tick, running, agenthub_available, codexbar_available, has_system, has_snapshot, has_state, mood, system, screen, transmission, rule }` (12 keys) — see `desktop/src/types.ts` and `status_snapshot()`. Live `/api/status` serves all 12 keys (`mood` is `string | null`, added in MD-2.3; `system` is `{ cpu, ram, gpu }` and `screen` is `{ present, simulate, brightness }`, added in MD-2.8a; `transmission` is the screen transmission stats from `Screen.stats_snapshot()`, added in MD-4.2; `rule` is `{ winning_rule_id: string | null, fired: string[] }`, added in MD-5.1). Frontend renders `Error fetching status` on non-2xx or network failure. |
| Loopback only | Panel binds `127.0.0.1` exclusively (`library/moka_tss/webconfig.py:75`, `DEFAULT_HOST`). `Host` header must equal `127.0.0.1:<port>` on every request, including GET. Never expose on `0.0.0.0`. |
| Shutdown | Stopping the sidecar stops the loop, web server, tray, and screen (`MokaApp.stop()`). Tauri killing the sidecar process is the supported teardown; single-instance lock (`library/moka_tss/host.py`) prevents a second writer on the serial port. |

## Ports

| Port | Owner | Default source |
|------|-------|----------------|
| 8765 | Config panel + `/api/status` + `/api/services` (this sidecar) | `library/moka_tss/webconfig.py:80` (`DEFAULT_PORT`) |
| 8787 | codexbar snapshot | `library/sensors/moka_tss/codexbar.py:52` (`DEFAULT_BASE_URL`), overridable via `MOKA_CODEXBAR_URL` |
| 7777 | agent-hub state | `library/sensors/moka_tss/agenthub.py:42` (`DEFAULT_BASE_URL`), overridable via `MOKA_AGENTHUB_URL` |

8765 was chosen because it collides with neither 7777 nor 8787
(`library/moka_tss/webconfig.py:77-79`).

## Rust validation state (Windows-only)

- Present but uncompiled (Linux lacks the GTK toolchain; Windows compile pending): sidecar binary packaging placeholder (`tauri.conf.json` + `Cargo.lock` pinned), `windows_subsystem = "windows"` console suppression in `desktop/src-tauri/src/main.rs`. Covered by tests: the Python ready-signal (`tests/library/moka_tss/test_ready_signal.py`, added in `2e24370`).
- Not yet implemented in Rust: `Command::sidecar("moka-sidecar")` spawn with `--no-tray`, stdout line parsing for `MOKA_READY`, and port handoff to the frontend. Current `desktop/src-tauri/src/lib.rs` only registers `shell`, `autostart`, and `single-instance` plugins.
- Until that lands, the frontend polls the hardcoded `http://127.0.0.1:8765/api/status`; any non-default panel port will not be discovered. Non-Windows hosts are unvalidated.

## Checklist

- [ ] Sidecar spawned with `--no-tray` and stdout piped line-delimited.
- [ ] `MOKA_READY port=<p>` parsed before first `GET /api/status`.
- [ ] Poller targets the parsed port, not a hardcoded one, on `127.0.0.1` only.
- [ ] No second Python instance holds the serial-port lock.

## Next step

Implement the Tauri sidecar spawn + ready-line parse in `desktop/src-tauri/src/lib.rs` and replace the hardcoded `STATUS_URL` in `desktop/src/main.ts` with the discovered port.
