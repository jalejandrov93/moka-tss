# Créditos de arte — sprites de la mascota

## Fuente

- **Obra**: "[LPC] Cats and Dogs"
- **Autor**: bluecarrot16
- **URL**: http://opengameart.org/content/lpc-cats-and-dogs
- **Licencias del recurso original** (tal como figuran en la página de OpenGameArt,
  verificado 2026-09-19): CC-BY 3.0 / CC-BY-SA 3.0 / GPL 3.0 / GPL 2.0 / OGA-BY 3.0.
  Se usa bajo **GPL 3.0**, compatible con la licencia de este proyecto
  (GPL-3.0-or-later).
- **Atribución exigida por el autor** (texto de la propia página): `"[LPC] Cats
  and Dogs" Artist: bluecarrot16 License: CC-BY 3.0 / GPL 3.0 / GPL 2.0 / OGA-BY
  3.0 Please link to opengameart: http://opengameart.org/content/lpc-cats-and-dogs`

Del recurso original solo se descargó `cat.png` (512x256, hoja de sprites de un
gato en 4 variantes de color x múltiples poses, 32x32 px por cuadro). No se usó
`dog.png`: la mascota de este proyecto es un único personaje (el gato), no
requiere la variante de perro.

## Archivos versionados en este directorio

Ocho recortes de 32x32 px de la variante de color "tan/dorado" de `cat.png`
(ninguna otra columna/fila de la hoja original se commitea; solo estos ocho
cuadros base):

| Archivo | Pose de origen (fila, columna de `cat.png`) | Descripción |
| --- | --- | --- |
| `sleep_a.png` | fila 0, columna 7 | tumbado, cabeza levantada |
| `sleep_b.png` | fila 3, columna 7 | tumbado, recostado completo (bloque espejado) |
| `front_a.png` | fila 2, columna 4 | caminando hacia cámara, cuadro 1 |
| `front_b.png` | fila 2, columna 5 | caminando hacia cámara, cuadro 2 |
| `front_c.png` | fila 2, columna 6 | caminando hacia cámara, cuadro 3 |
| `alert_a.png` | fila 4, columna 4 | pose erizada/defensiva, cuadro 1 |
| `alert_b.png` | fila 4, columna 5 | pose erizada/defensiva, cuadro 2 |
| `alert_c.png` | fila 4, columna 6 | pose erizada/defensiva, cuadro 3 |

`library/mascota/mascot.py` (`MascotSprites.load`) escala estos ocho cuadros a
96x96 con `Image.NEAREST` (nunca un filtro suavizante, para no difuminar el
pixel art) y a partir de ellos genera **en código, en tiempo de carga** las
seis animaciones de ánimo. No se commitea ningún cuadro ya teñido ni ya
escalado: solo estos 8 originales.

## Mapeo de ánimos (ver también el docstring de `mascot.py`)

| Ánimo (`MascotSprites.MOODS`) | Cuadros base usados | Tratamiento en código |
| --- | --- | --- |
| `durmiendo` | `sleep_a`, `sleep_b` | sin teñido, ciclo lento (respiración) |
| `calma` | `front_a`, `front_b` | sin teñido, ciclo lento |
| `atenta` | `front_a`, `front_b`, `front_c` | brillo/saturación +25%, ciclo más rápido (sin repetir cuadros) |
| `agobiada` | `alert_a`, `alert_b`, `alert_c` | teñido ámbar `#EAB308` (45% alpha), ciclo medio |
| `alarmada` | `alert_a`, `alert_b`, `alert_c` | teñido rojo `#EF4444` (55% alpha), ciclo rápido |
| `error` | `front_a`, `front_b` (generados, no commiteados) | escala de grises + ruido determinista + X roja + parpadeo invertido — un estado inconfundible que no existe en la hoja original |

El recurso original no incluye una pose de "dormido" en el sentido estricto
(ojos cerrados); se usa la pose de tumbado más cercana, que es la única del
set que transmite descanso. Ninguna pose de "ansiedad" existe tampoco: la
progresión atenta -> agobiada -> alarmada se logra reutilizando la pose
erizada/defensiva con teñido y velocidad crecientes, tal como permite la
tarea (T6).
