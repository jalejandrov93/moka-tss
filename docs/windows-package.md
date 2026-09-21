# Empaquetado completo de Windows (Python sidecar + Tauri desktop)

Esta guía explica cómo generar el instalador de Windows completo para MOKA TSS:
- **Python sidecar** (`moka-sidecar.exe`): dashboard que controla la pantalla y expone API local.
- **Tauri desktop** (`MOKA TSS.msi` / `.exe`): shell React que lanza el sidecar y muestra la UI.

El resultado son instaladores en `desktop\src-tauri\target\release\bundle\`.

## Requisitos previos

| Herramienta | Versión mínima | Notas |
|-------------|----------------|-------|
| **Python** | 3.13+ | Debe estar en `PATH`. Verificado con `python --version`. |
| **Rust** | stable (1.78+) | `rustup default stable`. Verificado con `cargo --version`. |
| **Node.js** | 20+ (LTS) | Verificado con `node --version`. |
| **npm** | incluido con Node | Verificado con `npm --version`. |
| **WebView2 Runtime** | Evergreen Bootstrapper | Requerido por Tauri v2 en Windows. Descargar: <https://developer.microsoft.com/en-us/microsoft-edge/webview2/> |

> **Nota**: Python 3.13 es la versión donde ya se validó que `requirements.txt` instala limpio. Si usas otra versión, pueden aparecer problemas de dependencias nativas (p.ej. `pynacl`, `cryptography`).

## Orden de ejecución

Todo se hace con **un solo comando** desde la raíz del repositorio:

```powershell
powershell -ExecutionPolicy Bypass -File tools\package-windows.ps1
```

El script orquesta tres pasos internos:

1. **Python sidecar** → llama a `tools\build-moka-tss.ps1` (PyInstaller sobre `moka-tss.spec`), produce `dist\moka\moka.exe` y lo copia a `desktop\src-tauri\binaries\moka-sidecar.exe`.
2. **Frontend Tauri** → `npm install` + `npm run build` dentro de `desktop\` (compila React + TypeScript + Vite).
3. **Instalador Tauri** → `npx tauri build` (compila Rust, enlaza el sidecar, genera `.msi` y `.exe`).

### Omitir el sidecar (desarrollo iterativo del frontend)

Si solo cambias código React/TypeScript y el sidecar ya está construido:

```powershell
powershell -ExecutionPolicy Bypass -File tools\package-windows.ps1 -SkipSidecar
```

Esto salta el paso 1 y usa el `moka-sidecar.exe` existente en `desktop\src-tauri\binaries\`.

## Dónde salen los instaladores

Al terminar, los artefactos están en:

```text
desktop\src-tauri\target\release\bundle\
├── msi\MOKA TSS_0.1.0_x64_en-US.msi      # Windows Installer (recomendado)
└── nsis\MOKA TSS_0.1.0_x64-setup.exe     # NSIS installer (alternativo)
```

El nombre y versión vienen de `desktop\src-tauri\tauri.conf.json` (`productName`, `version`).

## Flujo de trabajo típico

```text
1. Clonar repositorio
2. Instalar prerrequisitos (Python 3.13, Rust stable, Node 20+, WebView2)
3. Crear venv Python:  C:\Python313\python.exe -m venv .venv
4. Ejecutar:  powershell -ExecutionPolicy Bypass -File tools\package-windows.ps1
5. Esperar ~5-10 min (primera vez descarga dependencias Rust + npm)
6. Tomar el .msi de desktop\src-tauri\target\release\bundle\msi\
7. Distribuir: el .msi instala la app completa (sidecar + frontend + recursos)
```

## Solución de problemas

### COM3 ocupado por `UsbMonitor.exe` (app original china)
La app oficial del fabricante abre el puerto serie en exclusiva.
- **Solución**: cerrar `UsbMonitor.exe` / `ExtendScreen.exe` desde el Administrador de tareas antes de lanzar el instalador o la app instalada.
- El sidecar intenta abrir `COM3` por defecto (configurable en `config.yaml` o CLI `--port`).

### SmartScreen muestra "origen desconocido" / "Windows protegió su PC"
El binario **no está firmado** con certificado de código (cuesta dinero y el proyecto no tiene uno).
- **Solución**: "Más información" → "Ejecutar de todas formas". Es comportamiento normal para software abierto sin firma EV.
- Para distribución interna, se puede firmar con `signtool` si se dispone de certificado.

### Se requiere ejecutar como administrador (LHM / temperaturas CPU)
LibreHardwareMonitor (DLLs en `external\LibreHardwareMonitor\`) necesita elevación para leer sensores de temperatura.
- **Síntoma**: CPU/RAM/GPU funcionan, pero temperaturas de CPU no aparecen.
- **Solución**: clic derecho en el acceso directo → "Ejecutar como administrador". Sin admin la app sigue funcionando con degradación explícita (solo faltan temperaturas).

### `npx tauri build` falla con error de vinculación (linker)
- Verificar que Rust toolchain es `stable` (`rustup default stable`).
- Verificar que Visual Studio Build Tools / Windows 10 SDK están instalados (el instalador de Rust `rustup-init.exe` ofrece instalarlos).
- Limpiar caché: `cargo clean` en `desktop\src-tauri\` y reintentar.

### `npm install` falla con errores de `node-gyp` / Python
- Tauri v2 usa algunas dependencias nativas. Asegurar Python 3.13 en `PATH` y `npm config set python "C:\Python313\python.exe"`.
- Borrar `node_modules` y `package-lock.json` en `desktop\` y reintentar.

### El sidecar no arranca (`MOKA_READY` no aparece)
- Verificar que `desktop\src-tauri\binaries\moka-sidecar.exe` existe y es ejecutable.
- Ejecutar manualmente: `.\desktop\src-tauri\binaries\moka-sidecar.exe --no-tray --simulate` → debe imprimir `MOKA_READY port=8765`.
- Si falla, revisar logs de Python (dependencias faltantes, puerto COM ocupado, etc.).

### Puerto del panel de configuración no es 8765
El contrato sidecar-Tauri usa `MOKA_READY port=<p>` en stdout. Hasta que el Rust lo parseé (`desktop/src-tauri/src/lib.rs` pendiente), el frontend sondea `http://127.0.0.1:8765/api/status` hardcodeado.
- Si cambias el puerto en `config.yaml` o CLI, la UI no descubrirá el sidecar hasta que se implemente el parseo en Rust.

## Estructura de archivos relevantes

```
tools/
├── build-moka-tss.ps1      # Build solo Python sidecar (PyInstaller)
└── package-windows.ps1     # ESTE ORQUESTADOR (sidecar + Tauri)

desktop/
├── package.json            # Scripts: dev, build, tauri
├── src-tauri/
│   ├── tauri.conf.json     # bundle.externalBin = ["binaries/moka-sidecar"]
│   ├── Cargo.toml          # Rust deps
│   └── binaries/           # ← sidecar copiado aquí (gitignored)
└── src/                    # React + TypeScript frontend

moka-tss.spec               # PyInstaller spec para sidecar
moka.py                     # Entry point Python (--no-tray para sidecar)
```

## Referencias

- Contrato sidecar: `desktop/SIDECAR.md`
- Build solo Python: `docs/build-exe.md`
- Configuración Tauri: `desktop/src-tauri/tauri.conf.json`
- Espec PyInstaller: `moka-tss.spec`