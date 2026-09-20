# Generar `mascota.exe` en Windows

Esta guía explica cómo construir el ejecutable de Windows de Mascota: un solo
`mascota.exe` que se abre con doble clic, sin necesidad de ejecutar comandos
de Python para usarlo.

## Requisitos previos

- Windows 10 u 11 de 64 bits.
- Python 3.13 instalado en `C:\Python313` (es la versión donde ya se verificó
  que todo `requirements.txt` instala limpio).
- Un entorno virtual en `.\venv` dentro del repositorio:
  `C:\Python313\python.exe -m venv venv`.
- Conexión a internet para descargar las dependencias la primera vez.

## Cómo compilar

1. Abrir PowerShell en la raíz del repositorio.
2. Ejecutar:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\build-mascota.ps1
   ```

   El script instala las dependencias, corre PyInstaller sobre `mascota.spec`
   y comprueba que el ejecutable existe. Si algo falla, se detiene con un
   mensaje que indica qué paso falló.

## Dónde aparece el exe

Al terminar, el ejecutable está en:

```text
dist\mascota\mascota.exe
```

Ojo: no es un único archivo suelto, sino un ejecutable más su carpeta
(`onedir`). Para llevarlo a otra máquina, hay que copiar la carpeta `mascota`
completa, no solo el `.exe`.

## Cómo ejecutarlo

Doble clic sobre `mascota.exe`. La app vive en la bandeja del sistema (junto
al reloj): desde su ícono se abre el panel de configuración y se sale de la
app. No hace falta tener Python instalado en la máquina donde se ejecuta.

## Solución de problemas

- **SmartScreen o el antivirus lo bloquean o lo marcan como sospechoso.**
  El binario no está firmado con un certificado de código (firmar cuesta
  dinero y este proyecto no tiene uno). Es normal que SmartScreen muestre el
  aviso de "origen desconocido" y que algunos antivirus heurísticos
  sospechen de cualquier `.exe` que empaqueta Python. Hay que elegir
  "Más información" → "Ejecutar de todas formas". Si el antivirus lo pone en
  cuarentena, hay que añadir una excepción para la carpeta de la app.

- **La temperatura de CPU no aparece (pero sí CPU/RAM).**
  La temperatura de CPU solo la entrega LibreHardwareMonitor, que exige
  **ejecutar como administrador**. En cambio `nvidia-smi` (GPU) y `psutil`
  (CPU/RAM) funcionan sin elevación. Si solo faltan temperaturas, hay que
  cerrar la app y relanzar `mascota.exe` con "Ejecutar como administrador".
  Sin admin la app sigue funcionando, con degradación explícita.

- **El ícono de la bandeja no aparece y no hay ningún error.**
  Si al compilar no se empaquetó el backend de `pystray` para Windows
  (`pystray._win32`), la bandeja desaparece en silencio: `main.py` ignora el
  error de importación a propósito. `mascota.spec` ya lo incluye en
  `hiddenimports`, así que si pasa esto lo más probable es que el `.exe` se
  haya compilado con un spec modificado o desactualizado: reconstruir desde
  este repositorio sin tocar `hiddenimports`.

- **La pantalla no se encuentra (puertos COM vacíos).**
  Revisar que la pantalla esté conectada (es `COM3` en el equipo de
  referencia), que ninguna otra app tenga el puerto abierto (por ejemplo la
  app china original `UsbMonitor.exe`) y que el usuario tenga permiso sobre
  el puerto serie.

- **El build falla en `pip install`.**
  Normalmente es el venv: comprobar que existe `.\venv\Scripts\python.exe` y
  que se creó con `C:\Python313`. No usar el Python del sistema ni otro
  entorno: el script se niega a continuar sin ese venv a propósito.
