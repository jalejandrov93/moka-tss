# Mascota Desktop — Tauri 2 + Python sidecar (V1)

> Feature document (ODD). Mirror en Engram: topic `odd/mascota-desktop/tasks`.
> Locator: `odd/tasks/mascota-desktop.md` · Rama: `feature/moka-tss` · Base: `71b5b35`
> Reversión consciente de D13: se acepta toolchain Tauri (Rust+Node) + doble binario con Python sidecar como V1. Panel web 8765 queda como fallback hasta dashboard nativo.

## Objetivo
Separar `MokaApp` en Core testeable + Host lifecycle + UI futura, dejando listo el contrato para Tauri sidecar sin romper SIMU/COM3 hoy.

## Alcance autorizado
- Refactor local Python bajo `library/moka_tss/`, sin tocar `library/lcd/`, sin nuevo toolchain aún.
- Slices pequeños (1 delegación agy `gemini-3.8-flash-high` por slice).
- TDD estricto: `python -m unittest discover -s tests -t .` + `python -m flake8`.

## Restricciones
- GPL-3.0-or-later, cabecera SPDX en `.py` nuevos.
- agy solo `gemini-3.8-flash-high`; copilot excluido (exhausted hasta 2026-10-01); codex último fallback (89%).
- Nunca aceptar entrega por autorreporte: verificar con `git status` + `find` + tests del padre.
- TDD mode: enabled (estricto). Runner: `python -m unittest discover -s tests -t .`.

## Tareas (slices pequeños)
- [x] MD-0.1 Mapa Core/UI: inventario `app.py` → tabla Core vs Host. Hecho 2026-09-20 vía agy gemini-3.8-flash-high (job 082505be). Sin código.
- [x] MD-0.2 Extraer `Host`: `InstanceLock` + lifecycle start/stop a módulo propio, `app.py` lo reusa. Hecho 2026-09-20 vía agy gemini-3.8-flash-high (job 84075d86). Commit `54d2c8d` mergeado a `feature/moka-tss`. Verificado por padre: 4 tests nuevos OK, suite 285 (solo 8 Rev C conocidos), flake8 limpio en nuevos.
- [x] MD-0.3 Contrato estado único: `status_snapshot()` JSON. Hecho 2026-09-20 vía agy gemini-3.8-flash-high (job adf07bc3). Commit `87e0b2d` mergeado a `feature/moka-tss`. Verificado por padre: 5 tests nuevos OK, suite 290 (solo 8 Rev C conocidos), flake8 repo-standard limpio en nuevo test.
- [x] MD-1.1 Recon scaffold: propuesta HTTP directo + eventos solo lifecycle. Hecha 2026-09-20 vía agy gemini-3.8-flash-high (job f21c5188). Decisión usuario: react-ts.
- [x] MD-1.2 Scaffold `desktop/`: plantilla Tauri v2 react-ts + plugins shell/autostart/single-instance + `externalBin: binaries/moka-sidecar` + `src/main.ts` placeholder que pinta `status_snapshot()`. Commit `94cd91d` mergeado a `feature/moka-tss`. Verificado por padre: JSONs válidos, capabilities corregido (faltaba `single-instance:default`), `.gitignore` cubre node_modules/target. Deuda: entry actual es vanilla `main.ts`; Fase 2 lo reemplaza por `main.tsx` React (deps react ya en package.json).
- [x] MD-1.3a Frontend valida: `npm install` + `tsc --noEmit` limpio + `vite build` OK. Commit `4453e47` (package-lock.json). Verificado por padre (tsc reproducido). Nota: primer intento agy devolvió éxito falso sin hacer nada (patrón HD-2); reintento con instrucción síncrona sí produjo salidas reales.
- [ ] MD-1.3b Rust compila: `cargo check` **BLOQUEADO ambiental** 2026-09-20 — sin `pkg-config` ni GTK/webkit dev en este Linux (verificado por padre). No es defecto de código. Validación Rust se hace en Windows (WebView2 nativo). Commit `08c837c` (Cargo.lock). NO instalar paquetes sistema sin autorización.
- [x] MD-1.7 Spawn sidecar en Rust (job 632f89fa, agy). Commit `a5e3ee1` (commiteado por padre, worker no commiteó). Mergeado. NO compilado — pendiente Windows.
- [x] MD-2.3 Mood end-to-end (job 64921189, agy). Merge `38e2c52`. Contrato ahora 8 claves (`mood`).
- [x] MD-3.2 Esquema `services` en webconfig (job fc386f11, opencode). Merges `7e5dcad`+`468f812`. Hallazgo padre: C901=15 regresión → fix `91ec06c` extrayendo `_validate_services`; tests quedaron sin commitear y se rescataron en `c9cb400`. Verificación conjunta final: 303 tests (solo 8 Rev C), lint CI 0.
- [x] MD-1.4 Sidecar ready-signal: `format_ready_line(port)` + `print(..., flush=True)` en `run()` tras config server. Hecho 2026-09-20 vía agy gemini-3.8-flash-high (job 29fac018). Commit `2e24370` mergeado a `feature/moka-tss`. Verificado por padre: 5 tests nuevos OK, suite 295 (solo 8 Rev C conocidos), flake8 limpio.
- [x] MD-1.5 Tray menu Rust (job 499639d7, agy). Commit `31adaf5` mergeado. Verificado por padre contra API Tauri v2 (MenuBuilder/TrayIconBuilder/include_image); single-instance ahora enfoca ventana. NO compilado (sin GTK en Linux) — compile pendiente en Windows.
- [x] MD-2.1 Propuesta dashboard Fase 2 (job 211dedcc, agy recon). Hallazgo útil: `/api/status` (4 claves de `_get_status`) no coincide con `StatusSnapshot` (7 claves) → registrado como MD-2.2.
- [x] MD-3.1 Diseño monitor WSL (job 4a6405f1, agy recon). Esquema YAML + cadencias (discovery 120-300s, TCP 5-10s, HTTP 15/60s) + mapeo Healthy/Slow/Stale/Unavailable guardado como insumo Fase 3.
- [x] MD-1.6 Docs contrato sidecar (opencode crasheó pero dejó `desktop/SIDECAR.md` + sección README; padre corrigió 2 imprecisiones y commiteó). Merge `07177c4` (merge real tras recuperar commit 60b6c47).
- [x] Audit MD-0..MD-1.4 adversarial (opencode). Veredicto padre: 0 bloqueos. #1 print-stdout es contrato deliberado (SIDECAR.md); #2/#3/#4 signal/stop preexistentes, anotados para Fase 8; #5 race lock teórica, sin acción.
- [x] MD-2.2 Alinear `/api/status` con `status_snapshot()` (7 claves). Hecho 2026-09-20 vía agy gemini-3.8-flash-high (job 49d41fca). Commit `97569fe` mergeado. Verificado por padre: 50 tests foco OK, suite completa solo 8 Rev C, flake8 limpio. Nota: reporte del worker vacío pero el diff era correcto y mínimo.
- [x] MD-1.7 Spawn sidecar en Rust (job 632f89fa, agy). Commit `a5e3ee1` (commiteado por padre). Mergeado. NO compilado — pendiente Windows.
- [x] MD-2.4 Puerto descubierto en frontend (job 3ffd7c48, agy). Commit `b400fee` mergeado. Verificado por padre (tsc reproducido): `listen('moka-sidecar-ready')` con await en try/catch, fallback 8765, fetch inmediato.
- [x] MD-2.5 Tailwind v3 cableado (job a0af38a7, agy). Commit `9051d71` mergeado. Verificado por padre: index.css con directivas, content paths, build emite CSS 4.23kB. Sin shadcn aún.

## Progreso
- 2026-09-20: creado documento, sin código aún. Rama `feature/moka-tss` @ `71b5b35`.
- [x] MD-2.6 shadcn + tarjeta Servicios (job 779cd86b, agy). Commit `8e7974a` mergeado. Verificado por padre: React createRoot + alias @ + Card/Badge dark, tsc+build OK. Nota: shims re-export en desktop/{components,lib}/ por convención; negaciones .gitignore porque `lib/` global los tapaba.
- [x] MD-2.7 Tarjeta IA solo lectura (job 01aef455, agy). Commit `0a70324` mergeado. Verificado por padre (tsc reproducido): helper baseUrl(), fetch /api/rules, Card Mascota con mood + lista reglas.
- [x] MD-2.8a Telemetría en snapshot (job 09b72017 reintento, agy; primer intento no-op). Commit `bd3f97d` mergeado. Verificado por padre: `_sanitize_metric` (None/bool/NaN→None), system{cpu,ram,gpu}+screen{present,simulate,brightness}, 47 tests foco OK, suite solo 8 Rev C, lint CI 0.
- [x] MD-2.8b Tarjeta Sistema/Turing (job 74467860, agy). Commit `4e987fa` mergeado. Verificado por padre (tsc reproducido): SystemTelemetry/ScreenInfo en types, barras con umbrales 75/90, estado Turing.
- [x] MD-2.9a Probador TCP de servicios (job e936a64a, agy). Commit `cc17306` mergeado. Verificado por padre: SPDX, 6 tests OK, lint CI 0.
- [x] MD-2.9b Endpoint /api/services (job 4f507fca reintento, agy; primer intento vacío). Commit `df97e7c` mergeado. Verificado por padre: 38 tests foco OK, suite solo 8 Rev C, lint CI 0.
- [x] MD-2.9c Tarjeta Servicios (job 551f50d0, agy). Commit `968b0c0` mergeado. Verificado por padre (tsc reproducido): ServiceStatus, poll 10s + refresh tras puerto, badges por reachable.
- [x] MD-3.3 Endpoint /api/wsl (opencode nemotron, agy falló 2 veces en este slice). Commit mergeado. Verificado por padre: 50 tests foco OK, suite solo 8 Rev C, lint CI 0. Mensaje de commit normalizado a feat(moka).
- [x] MD-3.4 Tarjeta WSL (job ea1d7425, agy). Commit `8dee40a` mergeado. Verificado por padre (tsc reproducido): WslStatus, fetch en ciclo services, Badge + lista distros.
- [x] MD-4.1 Brillo en vivo (job 34661e4e reintento, agy). Commit `1b73fed` mergeado. Verificado por padre: callback on_config_saved best-effort + _apply_saved_settings, 62 tests OK, lint CI 0 tras corregir E731/E306 del worker.
- [x] MD-4.2 Stats transmisión (opencode nemotron, agy falló 2 veces). Commits mergeados (worker + test padre con serial fake). Verificado por padre: 6 tests stats OK, suite solo 8 Rev C, lint CI 0.
- [x] MD-4.3 Tarjeta Transmisión (job 78b00b27, agy). Commit `862b5ba` mergeado. Verificado por padre (tsc reproducido): renderTransmisionCard en ciclo existente, null-safe.
- [ ] MD-4.4 Slider brillo (job 273bb299, agy, md-44-slider).
- [ ] MD-5.1 Rule info en snapshot (job 21fd0ff9, agy, md-51-rule).
- [ ] MD-6.1 Diseño editor reglas (job a38def22, agy recon).
- [ ] MD-8.1 Diseño recovery (job 8dea1a6f, opencode recon).
- [ ] MD-9.1 Flag --diagnostics vía Jules (job cd6f0b92, PR remoto).
- [x] MD-4.4 Slider brillo (job 273bb299, agy). Merge `6b3f053` (merge real tras borrar rama antes de tiempo, recuperado por hash — NO repetir). Verificado por padre (tsc reproducido): debounce 300ms, POST con Origin, guard stale, init desde /api/config.
- [x] MD-6.1 Diseño editor reglas (agy recon): UI lista+form+preview TS local, validaciones a espejar, slices MD-6.1..6.4.
- [x] MD-8.1 Diseño recovery (opencode recon): watchdog en step(), transiciones por subsistema, 5 acciones ordenadas, lista de NUNCAs.
- [ ] MD-5.1 Rule info (agy falló 2 veces; pivote opencode job fa7eab82, md-51-rule).
- [ ] MD-9.1 Flag --diagnostics vía Jules (job cd6f0b92).
- [x] MD-5.1 Rule info en snapshot (opencode nemotron, agy falló 2 veces). Commit mergeado (mensaje normalizado a feat(moka)). Verificado por padre: step usa evaluate_detailed, _evaluate_mood intacto, 62 tests OK, suite solo 8 Rev C, lint CI 0. Contrato ahora 12 claves.
- [x] MD-9.1 Flag --diagnostics vía Jules (PR #4, merge commit `10c6587`). Verificado por padre en worktree temporal (test + lint + ejecución real sin hardware) antes de fusionar.
- [ ] MD-4.5 Info pantalla en tarjeta (job df282dcd, agy, md-45-screenctl).
- [ ] MD-5.2 Tarjeta estado mascota (job eea2ef01, opencode, md-52-mascot).
- [ ] MD-6.1 Motor reglas TS (job 47280ccf, agy, md-61-rulets).
- [x] MD-4.5 Info pantalla (job df282dcd, agy). Merge `dff5fa2`. Fila orientación/refresh, verificado tsc.
- [x] MD-5.2 Tarjeta Mascota Detalle (job eea2ef01, opencode). Merge `c9914ca`. Mood + triggered-by + fired badges.
- [x] MD-6.1 Motor reglas TS (job 47280ccf, agy). Merge `41afc7f`. lib/rules.ts: validateRule + evaluateRules con tie-break idéntico (sin histéresis, para Preview).
- Gate fusionado: tsc + build OK en árbol combinado (268KB).
