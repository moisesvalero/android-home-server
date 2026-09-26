# 🖥️ Dashboard Web del Android Server

Panel de control visual del servidor multimedia. Vive entero en `index.html` y lo sirve
`dashboard_server.py` en el puerto **8090**.

> 👉 `http://<IP-DEL-MOVIL>:8090`

Es una app de una sola página, **sin build, sin dependencias y sin framework**: HTML + un
bloque de CSS + un bloque de JS, todo inline. Se diseñó así para que el móvil no tenga que
instalar nada (ni Node, ni npm, ni un bundler) y para que el panel cargue en un solo
round-trip.

---

## 📁 Estructura

```
media_server/
├── dashboard/
│   ├── index.html       # Todo el panel: marcado + CSS inline + JS inline
│   └── README.md        # Este documento
└── dashboard_server.py  # Sirve el panel y expone la API REST (puerto 8090)
```

En el dispositivo se copia a:

```
~/media/
├── dashboard/index.html       # Lo que sirve el servidor
├── dashboard_server.py
├── fetch_cover.py
├── peliculas/                 # Biblioteca de películas
└── series/                    # Biblioteca de series
```

Las carátulas se guardan junto al vídeo como `<nombre-del-video>.jpg`; también se acepta un
`cover.jpg` de carpeta como respaldo.

---

## 🧭 Qué hay en pantalla

### Cabecera
- Enlaces de navegación que hacen scroll a cada sección.
- **Subir** (`triggerFileInput`) — abre el selector de archivos.
- **Biblioteca** (`openLibraryModal`) — abre el explorador completo.
- **Selector de idioma (ES / EN)** (`toggleLanguage`) — conmuta al instante entre español e inglés toda la interfaz (navegación, telemetría, explorador modal, avisos y formatos de fecha), persistiendo la preferencia en `localStorage['dashboard_lang']` y respetando el idioma del navegador por defecto.
- **Tema claro / oscuro** (`toggleTheme`) — se guarda en `localStorage['theme']` y se aplica
  antes de pintar para que no haya parpadeo.

### Resumen superior
Saludo y fecha reales (`hero-greeting`, `hero-date`), y cuatro tarjetas con datos en vivo:
nº de vídeos, almacenamiento, batería y estado DLNA + uptime. Todas se refrescan solas cada
**10 s** con `GET /api/system`.

### «Añadir a tu biblioteca»
- **Selector segmentado Películas / Series** — decide el destino de la subida.
- **Zona de arrastre** (`dropzone`) — acepta arrastrar y soltar, o clic para elegir archivos.
- **Cola de subidas** (`upload-queue-container`) — una fila por archivo.

### «Estado del servidor»
Temperatura del dispositivo (número grande), ecualizador animado decorativo, batería y RAM
del móvil. Usa el mismo sistema visual `.hw-*` que el modal de hardware (ver más abajo).

### Barra inferior (dock)
Atajos a las mismas acciones que la cabecera.

---

## 🔄 Cómo se comporta la cola de subidas

La gestiona la clase `UploadQueueManager` del propio `index.html`.

| Comportamiento | Detalle |
|---|---|
| **Concurrencia** | 3 archivos a la vez; el resto espera en cola |
| **Reiniciar** | `restartUpload()` — reenvía ese archivo desde cero |
| **Cancelar** | `cancelUpload()` — aborta y descarta el parcial |
| **Progreso** | Porcentaje y bytes (`formatBytes`) en cada fila, con `role="progressbar"` |
| **Formatos** | `.mkv`, `.mp4`, `.avi`, `.mov`, `.webm`, `.m4v`, `.ts` (se valida en cliente y servidor) |
| **Detector de atasco** | Si en 60 s no llega ni un byte de progreso ni respuesta, la fila se marca en rojo con «Sin respuesta del servidor» en vez de quedarse muda |
| **Errores** | Se muestra el motivo que devuelve el servidor en la propia fila |
| **Al terminar** | Barra verde y la fila se retira a los 3 s (roja si falló) |

**Invariante que hay que respetar al tocar este código:** en `restartUpload()` y
`cancelUpload()` el estado (`item.status`) se asigna **antes** de `xhr.abort()`. `abort()`
dispara `onabort` de forma síncrona, y ese handler descuenta `activeCount` si el item sigue
en `'uploading'`. Si se invierte el orden, una sola subida descuenta dos veces, el contador
va por detrás de la realidad y se supera el límite de 3 subidas simultáneas. Hay un test que
lo blinda (`test_upload_queue_marks_status_before_abort`).

---

## 🌐 API REST

Todas las respuestas son JSON salvo las de fichero (`/api/cover`, `/api/stream`) y el propio
panel. El servidor habla **HTTP/1.0**, así que **no admite `Transfer-Encoding: chunked`**.

### `GET`

| Ruta | Devuelve |
|---|---|
| `/` · `/index.html` | El panel |
| `/favicon.ico` · `/favicon.svg` | Icono SVG embebido |
| `/api/media` | Lista de vídeos: `filename`, `clean_title`, `category`, `rel_path`, `size_bytes`, `size_formatted`, `mtime`, `has_cover`, `cover_path` |
| `/api/storage` | `total_gb`, `used_gb`, `free_gb`, `percent_used` |
| `/api/system` | `storage`, `battery`, `ram`, `dlna_online`, `uptime` |
| `/api/cover?path=` | Imagen de la carátula |
| `/api/stream?path=` | Vídeo con soporte de `Range` (HTTP 206) para poder saltar en la reproducción |

### `POST`

| Ruta | Cuerpo | Hace |
|---|---|---|
| `/api/upload?name=&category=` | **Bytes crudos** del vídeo | Guarda el archivo por bloques de 64 KB y lanza la búsqueda de carátula en segundo plano |
| `/api/media/rename` | `{path, new_name}` | Renombra el vídeo y su `.jpg` |
| `/api/media/move` | `{path, destination}` | Mueve entre `peliculas` y `series` |
| `/api/media/copy` | `{path, destination}` | Copia entre categorías (sufijo `_copia` si ya existe) |
| `/api/media/cover` | `{path}` | Relanza la búsqueda de carátula oficial |

### `DELETE`

| Ruta | Hace |
|---|---|
| `/api/media?path=` | Borra el vídeo y su carátula |

### Códigos de `/api/upload`

Es el endpoint más delicado. Requiere **`Content-Length` obligatorio y mayor que 0**:

| Código | Cuándo |
|---|---|
| `200` | Subida completa |
| `400` | Nombre inválido, extensión no permitida, `Content-Length` no numérico, o **cuerpo de 0 bytes** (el navegador no pudo leer el archivo) |
| `403` | La ruta destino se sale de `peliculas/` o `series/` |
| `411` | Falta `Content-Length`, o llega `Transfer-Encoding: chunked` |
| `499` | El cliente cortó a mitad; el parcial **se descarta** para no dejar un vídeo incompleto en la biblioteca |

Sin ese contrato, un cliente que anuncia bytes y no los envía dejaría un hilo del servidor
bloqueado para siempre y el navegador se quedaría en «Iniciando…». El servidor aplica un
timeout de inactividad de **180 s** durante la recepción, y sólo durante ella: si se aplicara
a todas las peticiones, un vídeo en pausa más de ese tiempo dejaría de drenar el socket y se
cortaría la reproducción a media película.

---

## 🪟 Modales

Cinco diálogos, todos con `role="dialog"`, `aria-modal="true"` y nombre accesible. Se cierran
con la ✕, con clic en el fondo y con `Escape` (`setupModalInteractions`).

| Modal | Qué muestra |
|---|---|
| **Biblioteca** | Explorador completo: pestañas Todos/Películas/Series, buscador, listado con carátula y acciones (ver, renombrar, mover, copiar, refrescar carátula, descargar, borrar) |
| **Reproductor** | Vídeo HTML5 con streaming por `Range` |
| **Confirmar borrado** | Nombre del archivo y aviso de acción irreversible |
| **DLNA** | Nombre en la red, puerto y cómo verlo en la Smart TV |
| **Hardware** | Ventana estilo macOS moderno (barra de título con semáforos, el rojo cierra) con grupos «Estado general» (batería, temperatura, estado de carga, voltaje, salud), «Recursos» (RAM y disco, con barra de uso) y «Servicios» (DLNA, tiempo activo, puerto) |

Los cinco modales son **ventanas macOS moderno**: `.mac-titlebar` con los semáforos
(el rojo cierra, así que no hay botón de ✕ suelto) y el título centrado, `.modal-body`
para el contenido y `.modal-foot` para las acciones. Los botones son `.mac-btn`
(rectángulo de 6px con degradado sutil), con las variantes `.mac-btn--primary` (azul) y
`.mac-btn--danger` (rojo). Los bloques de metadatos usan `.modal-chip`.

### Sistema visual de las superficies de hardware

El modal de hardware y la tarjeta «Estado del servidor» comparten las clases `.hw-*`
(paleta, azulejos de icono, tipografía, barras) y las `.mac-*` del lenguaje macOS
moderno (Sonoma / Tahoe): `.mac-titlebar` + `.mac-lights` (semáforos), `.mac-group-title`
(encabezado **encima** de cada caja, en minúscula y gris), `.hw-card` (caja de grupo con
esquinas de 11px), `.hw-row` (icono + etiqueta a la izquierda, valor a la derecha) y
`.mac-btn` (rectángulo de 6px con degradado sutil).

Los colores salen de variables en `:root` y `html.dark` (`--hw-label`, `--hw-mute`,
`--hw-window`, `--hw-group`, `--hw-hair`, `--hw-track`, `--hw-edge` y los colores de
sistema). El color de las barras lo fija el JS por variable CSS (`--hw-fill`) y no por
estilo inline, porque las reglas llevan `!important` y ganarían a `style.backgroundColor`.
Los umbrales están en `colorDeNivel()` (RAM y disco: mucho es malo) y `colorBateria()`
(batería: rojo por debajo del 20%, como en macOS).

**No añadas `backdrop-filter` aquí.** El efecto cristal se consigue con transparencia, un
borde luminoso (`--hw-edge`) y sombras suaves, a propósito: el modal se abre sobre un velo
de color plano, donde un desenfoque no se apreciaría, y en el Android Server sí cuesta — fue lo
que hacía que los modales fueran a tirones (ver la sección de rendimiento, más arriba).

### Toque macOS en el resto del panel

Debajo de ese bloque hay una capa que extiende el mismo lenguaje a todo el panel, sin
tocar el fondo degradado azul, las transparencias ni los hovers de las tarjetas:

- Etiquetas y textos secundarios en gris neutro (`--hw-mute`) e iconos en el azul de
  acento, en vez de los azulados originales.
- Esquinas de macOS: los `rounded-[22px]`/`rounded-[24px]` pasan a 12px, los azulejos a
  8px y las pastillas de botón a 8-12px.
- Azulejos del dock con color plano de sistema (los `from-*-400` dejan de ser degradado).
- Las filas del explorador de biblioteca usan `.lib-row` y compañía: **una línea de alto
  fijo por fila**. Antes el título, el nombre y los metadatos se partían en varias líneas
  según lo largos que fuesen, así que unas filas quedaban más altas que otras y la lista
  se veía irregular. Si tocas esa plantilla, mantén cada dato en una sola línea con
  elipsis (`.lib-title`, `.lib-filename`, `.lib-meta-path`).
- Los botones de la biblioteca llevan `data-tip` con su descripción y `aria-label` para
  lectores de pantalla, en vez de `title`: así sale el tooltip propio (`.mac-tip`,
  `setupMacTooltips()`) y no el nativo del navegador, que tarda y no se puede estilar.
  Se usa **un solo nodo compartido** que se recoloca, no uno por botón: con 50 archivos
  serían cientos. Si añades un botón con `data-tip`, el tooltip ya funciona solo.

---

## ⚠️ Trampa al tocar los estilos: el Tailwind está precompilado

`index.html` lleva un bloque de CSS de Tailwind **compilado de un build anterior a los
modales**. Consecuencia: **muchas clases de utilidad no existen y fallan en silencio**. La
clase se escribe en el marcado pero no produce ningún estilo, y no salta ningún error.

Comprobado que **no existen**: `bg-[#176fda]`, `bg-white/75`, `bg-white/90`, `bg-white/95`,
`bg-black/75`, `bg-slate-50`, `bg-emerald-500`, `bg-red-500`, `bg-emerald-400`,
`bg-amber-400`, `bg-red-400`, `animate-pulse`.
Comprobado que **sí existen**: `bg-white/45`, `bg-white/70`, `border-white/45`, `bg-red-600`,
`bg-blue-100`, `text-white`, `text-[#176fda]`, `size-2`, `rounded-full`.

Esto ya provocó dos bugs reales: las pestañas de la biblioteca quedaban con texto blanco
sobre fondo transparente (usaban `bg-[#176fda]`, que no existe), y la barra de subida no
cambiaba de color al terminar ni al fallar.

**Cómo se trabaja aquí:**

1. Para estilos nuevos, **añade CSS al bloque `<style>` propio**, no confíes en clases nuevas
   de Tailwind. Prefija con un id (`#library-modal .mi-clase`) porque hay reglas del tipo
   `#library-modal button { color: inherit !important }` que ganan a cualquier clase suelta.
2. Si el JS aplica una clase cambiando `className`, **verifica en el navegador** que esa clase
   existe de verdad antes de darla por buena.
3. **Los tests no detectan esto.** Son comparaciones de cadenas: no ven clases inertes ni
   `ReferenceError`. Un cambio de estilos no está validado hasta que se ve en el navegador.

Otro detalle del mismo estilo: `formatBytes()` se usaba en dos sitios y no estaba definida.
El fallo no lo detectaban los tests y dejaba el explorador de biblioteca **vacío** (lanzaba
excepción antes de pintar) y el progreso congelado en «Iniciando…». Si añades una llamada a
una función nueva, comprueba que existe.

---

## 🛠️ Trabajar en local

```bash
# Servir el panel (usa ~/media como biblioteca en macOS)
PORT=8090 python3 media_server/dashboard_server.py
```

Abre `http://localhost:8090`. Ojo: crea `~/media/peliculas` y `~/media/series` si no existen.
Para probar sin tocar tu `~/media`, arranca el servidor desde un script propio que sobrescriba
`MEDIA_ROOT`, `PELICULAS_DIR` y `SERIES_DIR` antes de llamar a `run_server()`.

Tests:

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

---

## 🔒 Seguridad

**El panel no tiene autenticación.** Está pensado para la red Wi-Fi de casa y nunca debe
exponerse a Internet: no abras ni redirijas el puerto 8090 en el router.

Lo que sí valida el servidor:

- **Contención de rutas:** toda operación resuelve la ruta y comprueba con `is_relative_to()`
  que el archivo esté dentro de `peliculas/` o `series/`. Un nombre como `../../etc/passwd`
  se neutraliza con `os.path.basename()` y acaba dentro de la categoría, nunca fuera.
- **Extensiones permitidas:** vídeo `.mkv .mp4 .avi .mov .webm .m4v .ts`; imagen
  `.jpg .jpeg .png .webp`. Nada más se lee ni se escribe.
- **Sin secretos en el cliente:** el `index.html` no contiene credenciales ni claves.
