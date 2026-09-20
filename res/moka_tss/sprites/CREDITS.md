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

Catorce recortes de 32x32 px de la variante de color "tan/dorado" de `cat.png`.
Ninguna otra parte de la hoja original se commitea: solo estos cuadros base.

| Archivo | Pose de origen en `cat.png` | Descripción |
| --- | --- | --- |
| `sleep_a.png`, `sleep_b.png` | pose de tumbado | acostado, dos cuadros |
| `calma_a/b/c.png` | caminata de perfil hacia la izquierda | perfil lateral, 3 cuadros |
| `atenta_a/b/c.png` | caminata alejándose de cámara | vista trasera, 3 cuadros |
| `alert_a/b/c.png` | pose erizada/defensiva de frente | frente erizado, 3 cuadros |
| `alarm_a/b/c.png` | caminata de perfil espejada (hacia la derecha) | perfil lateral invertido, 3 cuadros |

Las coordenadas exactas (fila, columna) de cada recorte en la hoja original no
se registraron al rehacer la dirección de arte y **no se reconstruyeron**: se
prefiere no documentar coordenadas sin verificarlas antes que dar cifras
inventadas. Todos los cuadros provienen del bloque de color tan de `cat.png`.

`library/mascota/mascot.py` (`MascotSprites.load`) escala estos cuadros a 96x96
con `Image.NEAREST` — nunca un filtro suavizante, que difuminaría el pixel art —
y a partir de ellos genera **en código, en tiempo de carga** las seis
animaciones. No se commitea ningún cuadro ya teñido ni ya escalado.

## Mapeo de ánimos (ver también el docstring de `mascot.py`)

La regla de diseño: **el ánimo se lee primero en la silueta y recién después en
el color.** La pantalla se mira de reojo desde lejos, donde el contorno es lo
que llega; por eso cada ánimo usa una pose distinta y el teñido solo refuerza.
Un test mide la diferencia de siluetas entre cada par de ánimos y falla por
debajo de un umbral, así que una regresión no puede volver a colapsar dos
ánimos en la misma forma sin que el suite lo note.

| Ánimo | Cuadros base | Tratamiento en código |
| --- | --- | --- |
| `durmiendo` | `sleep_a`, `sleep_b` | sin teñido, ciclo lento (respiración) |
| `calma` | `calma_a`, `calma_b`, `calma_c` | sin teñido, ciclo lento |
| `atenta` | `atenta_a`, `atenta_b`, `atenta_c` | sin teñido, ciclo medio |
| `agobiada` | `alert_a`, `alert_b`, `alert_c` | teñido ámbar `#EAB308` al 20% |
| `alarmada` | `alarm_a`, `alarm_b` | teñido rojo `#EF4444` al 25%, ciclo rápido |
| `error` | generado desde `calma_a`, `calma_b` | escala de grises + ruido determinista + X roja + parpadeo invertido |

Los teñidos son deliberadamente suaves (20-25%): un teñido debe **sombrear** la
pose, no repintarla. La primera versión usaba 45% y 55% y convertía al gato en
una mancha de color sin rasgos.

`alarm_c.png` está versionado pero la animación de `alarmada` solo usa
`alarm_a` y `alarm_b`. Se conserva por si se quisiera alargar el ciclo.

El recurso original no trae una pose de "dormido" con los ojos cerrados: se usa
la de tumbado, la única del set que transmite descanso. Tampoco existe una pose
de "ansiedad", así que la progresión atenta -> agobiada -> alarmada se construye
cambiando de pose (trasera -> frente erizado -> perfil espejado) y sumando
teñido y velocidad.
