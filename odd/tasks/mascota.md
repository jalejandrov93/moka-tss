# Mascota — dashboard reactivo para la Turing Smart Screen 3.5"

> Feature document (ODD). Espejo en Engram: topic `odd/mascota/tasks`.
> Locator: `odd/tasks/mascota.md` · Rama: `feature/mascota` · Base: `upstream/main` @ `2b33ab4`

## Objetivo

Reemplazar la aplicación china `UsbMonitor.exe` por un dashboard propio, en español, que
muestre en la pantalla de 3.5" las cuotas de los agentes de IA, las métricas de `agent-hub`
y los sensores de la máquina, con una mascota de pixel art que **reacciona** al estado del
sistema según reglas de alerta declarativas.

## Problema

La app original está solo en chino, usa un formato de temas propietario
(.NET `BinaryFormatter` sobre `usb_hid.ThemeConfig`) y muestra información estática de
hardware. No conoce nada del ecosistema real de trabajo: cuotas de Claude/Codex/Antigravity/
Copilot, jobs de `agent-hub`, ni permite reglas de alerta.

## Por qué

Una pantalla con números es un widget que se vuelve mobiliario en dos días. Una mascota cuyo
estado ES el estado del sistema se percibe de reojo, sin leer: "Copilot al 100%" se capta
como incomodidad en la cara del sprite antes que como un dígito.

## Hardware y límites medidos

| Dato | Valor | Fuente |
| --- | --- | --- |
| Dispositivo | Turing Smart Screen 3.5" **Revision A** | `USB\VID_1A86&PID_5722\USB35INCHIPSV2` |
| Puerto | `COM3` (Windows), USB CDC | `Get-CimInstance Win32_PnPEntity` |
| Resolución | 320×480 retrato, RGB565 little-endian | `library/lcd/lcd_comm_rev_a.py` |
| Serial | 115200, `rtscts=True` | `library/lcd/lcd_comm.py:123` |
| Comandos | `RESET=101 CLEAR=102 TO_BLACK=103 SCREEN_OFF=108 SCREEN_ON=109 SET_BRIGHTNESS=110 SET_ORIENTATION=121 DISPLAY_PIXELS=195 DISPLAY_BITMAP=197` | `lcd_comm_rev_a.py:32-47` |
| Update parcial | `DisplayPILImage(image, x, y, w, h)` transmite solo esa región | `lcd_comm_rev_a.py` |
| Sin touch / sin LED backplate | El protocolo es unidireccional host→pantalla | `lcd_comm_rev_a.py` |

**Throughput: PENDIENTE DE MEDIR (T1).** Estimación upstream: frame completo 307.200 B en
~2-3 s (0,3-0,5 fps); sprite 64×64 = 8.192 B en ~0,06-0,08 s (~12-15 fps). El baudrate de
115200 es valor de handshake, no el techo real — a 115200 8N1 un frame tardaría ~27 s y se
miden 2-3 s. **Ningún diseño de layout se cierra hasta tener el número real de T1.**

## Decisiones tomadas

- **D1 — Layout: datos protagonistas.** Grid denso de cuotas + sensores; mascota de 64×64 en
  la esquina inferior derecha reaccionando. Decidido por el usuario 2026-09-19.
  Razón: máxima densidad de información y presupuesto de bytes holgado en el sprite.
- **D2 — Fork de `mathoudebine/turing-smart-screen-python`**, no reescritura. Su arquitectura
  ya separa sensores / render de temas / driver, y resuelve la capa cara (LibreHardwareMonitor).
  Remote `upstream` conservado para poder traer arreglos.
- **D3 — El renderer corre en Windows.** La pantalla es un framebuffer tonto en `COM3`, que
  vive en Windows. Desde WSL no se ve el puerto y `usbipd-win` no está instalado. Además los
  sensores reales (temperatura de CPU/GPU) solo existen del lado Windows: desde WSL se ve la
  VM, no el host.
- **D4 — WSL provee solo datos, por HTTP.** `.wslconfig` usa `networkingMode=mirrored`, así que
  Windows alcanza `127.0.0.1:8787` y `127.0.0.1:7777` directamente. Verificado en vivo (HTTP 200
  desde PowerShell). No hay trabajo de red pendiente.
- **D5 — Desarrollo con `REVISION: SIMU`.** Escribe a `screencap.png` sin hardware, así que
  todo se desarrolla y testea en worktrees de WSL; el hardware solo se toca en T9.
- **D6 — Punto de extensión de datos: `CustomDataSource`.** `library/sensors/sensors_custom.py`
  es la API oficial (`as_numeric()` / `as_string()` / `last_values()`), no hace falta tocar el
  core para inyectar codexbar ni agent-hub.

## Fuentes de datos (verificadas en vivo 2026-09-19)

- **codexbar** v0.60.3 · `http://127.0.0.1:8787`
  - `GET /health` (sin auth) · `GET /usage` (sin auth) · `GET /cost`
  - `GET /dashboard/v1/snapshot` — `Authorization: Bearer <~/.config/codexbar/dashboard-token>`
  - Snapshot: `providers[]` con `id`, `name`, `windows[]{kind,label,usedPercent,remainingPercent,resetAt}`,
    `display.accentColor`, `cost.last30DaysUSD`. `staleAfterSeconds: 180`. Poll-only, sin SSE.
  - Providers activos: `claude`, `codex`, `antigravity`, `opencodego`, `copilot`.
- **agent-hub** · `http://127.0.0.1:7777`
  - `GET /api/state` (jobs vivos) · `GET /api/metrics` · `GET /api/config` · `GET /api/quota`
  - **`GET /events` — SSE**, tail de `events.jsonl` con heartbeat de 15 s. Canal push preferido.
  - Sin auth; protegido por checks de loopback / `Host` / `Origin`.
- **Sensores locales** · LibreHardwareMonitor vía `pythonnet` (`HW_SENSORS: LHM`).

## Alcance autorizado

Dentro: fork y rama `feature/mascota`; adaptadores de datos; motor de reglas; assets y máquina
de estados de la mascota; compositor de blits parciales; tema YAML; documentación en español.

Fuera (requiere autorización nueva): publicar el fork; modificar `~/.wslconfig`; instalar el
driver PawnIO; desinstalar la app china; cualquier operación remota.

## Restricciones

- **Licencia GPL-3.0-or-later.** Mantener avisos, cabecera `SPDX-License-Identifier: GPL-3.0-or-later`
  en cada `.py` nuevo, marcar archivos modificados. Uso privado no obliga a distribuir.
- **Python 3.14 NO está soportado en Windows** por el upstream (`pythoncheck.py`: MIN 3.9 /
  MAX 3.14, pero el release 3.10.0 dice "Allow Python 3.14 for OS != Windows"). El default del
  usuario es 3.14 → **usar `C:\Python313`**.
- **LibreHardwareMonitor exige admin** (`IsUserAnAdmin()==0` → error y salida), desbloqueo de DLL
  y driver PawnIO. Conflictos reportados con anti-cheat. Sin admin: hay RAM/disco/red por psutil,
  pero **no hay temperatura de CPU ni GPU**.
- No romper el esquema de temas del upstream (convención de su `AGENTS.md`).
- Escrituras periódicas al display van por `library/scheduler.py`, nunca por loops paralelos ad-hoc.
- La 3.5" se calienta con brillo alto: no fijar brillo máximo por defecto.

## Modo TDD

- **Estado: habilitado (estricto).** Fuente: `~/.claude/CLAUDE.md` → "Strict TDD Mode: enabled".
- **Runner: `python -m unittest discover -s tests -t .`** (stdlib `unittest`, con golden files en
  `tests/library/lcd/golden/` y `serial_mock.py`).
- **Lint: `python -m flake8`** (workflow `lint-flake8.yml`).
- Ciclo obligatorio por tarea: RED observado → GREEN → REFACTOR. No se inventa evidencia.

## Estrategia de entrega

- Estrategia: `ask-on-risk` (default). **Pendiente**: elegir estrategia de cadena
  (`stacked-to-main` o `feature-branch-chain`) cuando el acumulado supere las ~400 líneas.
- Presupuesto: ~400 líneas autoradas por slice. Forecast inicial del feature: **~1.800-2.500**
  líneas → se esperan **5-6 slices**.
- Commits de unidad de trabajo en `feature/mascota`, Conventional Commits, sin atribución de IA.
  Push / PR / merge quedan como decisión del usuario.

## Tareas

Leyenda de ruta: `inline` = directo en el hilo padre · `deleg` = worker delegado.

- [ ] **T1 — Spike: medir throughput real en COM3.** Ruta: `inline`. Trigger: n/a (1 script).
  Medir en el equipo real el tiempo de un frame 320×480, un sprite 96×96 y uno de 64×64.
  Requiere cerrar `UsbMonitor.exe` (tiene tomado el COM3) y `pip install pyserial pillow` en 3.13.
  No es código de producción: script descartable bajo `tools/spike/`.
  Salida: tabla de bytes/tiempo/fps real, escrita en este documento.
  Check: los tres tiempos medidos, no estimados.

- [ ] **T2 — Entorno Windows reproducible.** Ruta: `inline`. Trigger: n/a.
  venv con `C:\Python313`, `requirements.txt` instalado, `REVISION: SIMU` corriendo y generando
  `screencap.png`. Documentar si LHM necesita admin en este equipo.
  Check: `python main.py` con SIMU produce `screencap.png`; `python -m unittest` en verde.

- [ ] **T3 — Adaptador codexbar → `CustomDataSource`.** Ruta: `deleg`. Trigger: escritura 2+ archivos.
  Lee `GET /dashboard/v1/snapshot` con bearer desde `~/.config/codexbar/dashboard-token`
  (nunca hardcodear el token). Un `CustomDataSource` por provider×ventana. Cache + degradación
  a último valor bueno hasta 15 min, como hace Quota-Arc. Timeout 30 s, poll 60 s.
  Check: tests `unittest` con HTTP mockeado, incluyendo 401, timeout y payload stale.

- [ ] **T4 — Adaptador agent-hub (métricas + SSE).** Ruta: `deleg`. Trigger: escritura 2+ archivos.
  `GET /api/state` para jobs vivos y `GET /api/metrics` para tasa de éxito; consumo de
  `GET /events` (SSE) en un hilo con reconexión y backoff.
  Check: tests con servidor SSE falso, incluyendo corte de conexión y heartbeat perdido.

- [ ] **T5 — Motor de reglas de alerta.** Ruta: `deleg`. Trigger: lógica nueva no trivial.
  Reglas declarativas en YAML: `cuando <métrica> <op> <umbral> durante <N>s → estado <ánimo>`.
  Histéresis para que no parpadee entre estados. Prioridad entre reglas en conflicto.
  Check: tests de tabla cubriendo histéresis, empate de prioridad y datos ausentes.

- [ ] **T6 — Assets y máquina de estados de la mascota.** Ruta: `deleg`. Trigger: 2+ archivos.
  Sprites pixel art 64×64, loops de 4-8 frames por estado (tranquila, atenta, agobiada,
  alarmada, durmiendo, error). Presupuesto por frame según T1.
  Check: cada estado tiene sus frames; test de que la máquina no queda sin transición válida.

- [ ] **T7 — Compositor de blits parciales.** Ruta: `deleg`. Trigger: núcleo de render.
  Fondo estático pintado una sola vez; solo se reenvían las regiones sucias (sprite + números
  que cambiaron). Cola serializada vía `library/scheduler.py`.
  Check: test con `serial_mock` que verifica que un cambio de un número **no** reenvía el fondo.

- [ ] **T8 — Tema `mascota` en YAML.** Ruta: `deleg`. Trigger: layout + assets.
  Layout de D1: cuotas arriba, sensores al medio, jobs + mascota abajo a la derecha. Colores
  tomados de `display.accentColor` de cada provider. Textos en español.
  Check: golden de `screencap.png` en SIMU.

- [ ] **T9 — Integración contra hardware real.** Ruta: `inline`. Trigger: n/a.
  Correr en Windows sobre COM3, ajustar intervalos con los números reales de T1, verificar
  temperatura de la pantalla con el brillo elegido.
  Check: sesión de 30 min sin desconexión de puerto ni corrupción de imagen.

- [ ] **T10 — Documentación en español + arranque automático.** Ruta: `deleg`. Trigger: docs + script.
  README propio en español, guía de instalación, y arranque con Windows.
  Check: seguir el README desde cero en una sesión limpia deja la pantalla andando.

## Criterios de aceptación

1. La pantalla muestra en español las cuotas de los 5 providers con su color de acento.
2. Muestra CPU / GPU / RAM (temperatura solo si hay admin; si no, degradación explícita).
3. Muestra los jobs vivos de agent-hub y reacciona a eventos SSE.
4. La mascota cambia de animación según reglas declarativas en YAML, con histéresis.
5. Un cambio de un número no repinta el fondo.
6. `python -m unittest discover -s tests -t .` en verde y `flake8` limpio.
7. Sobrevive a que `codexbar` o `agent-hub` estén caídos, sin crashear ni congelarse.

## Progreso

| Tarea | Estado | Evidencia | Tier RDD |
| --- | --- | --- | --- |
| T1 | pendiente | — | — |
| T2-T10 | pendiente | — | — |

**Estado RDD:** sin consultar todavía (`gentle-ai review mode status`). Se resuelve antes del
primer commit de unidad de trabajo.

## Siguiente paso

**T1 — el spike de medición.** Bloquea el diseño del layout y el presupuesto de animación:
todos los números de fps de arriba son estimaciones de reportes upstream, no mediciones de
este equipo. Requiere cerrar `UsbMonitor.exe` (PID observado 22560) porque retiene el COM3.
