# 🎬 Servidor Multimedia DLNA Ultraligero para Android & Smart TVs

Servidor de streaming multimedia sin transcodificación para cualquier smartphone **Android** con Termux, diseñado para enviar películas y series a Smart TVs (Samsung Tizen, LG webOS, Google TV/Android TV) con carátulas oficiales, con un consumo medido de **~17 MB de RAM** (MiniDLNA) y **~24 MB** (panel web), garantizando aislamiento total de otros procesos y de Hermes Agent.

---

## 📁 Estructura del Módulo

```text
media_server/
├── dashboard/
│   ├── index.html            # Interfaz Web moderna (Drag & Drop, galería, modal de incompatibilidad)
│   └── README.md             # Documentación del panel: UI, API REST, cola de subidas
├── dashboard_server.py       # Servidor HTTP ligero con streaming a disco (puerto 8090)
├── mac_helper.py             # Micro-asistente local para conversión rápida con 1 clic (puerto 8095)
├── iniciar_mac_helper.sh     # Script para arrancar el asistente manualmente
├── instalar_servicio_mac.sh  # Instala el asistente como servicio permanente (LaunchAgent macOS)
├── desinstalar_servicio_mac.sh # Desinstala el servicio de macOS
├── minidlna.conf             # Configuración de MiniDLNA optimizada para Smart TVs
├── fetch_cover.py            # Descargador automático de carátulas (IMDb & TVMaze en HD)
├── setup_media_server.sh     # Script de instalación para Termux en Android
└── enviar_al_servidor.sh     # Utilidad CLI con auto-conversión de AVI y envío en 1 comando
```

---

## 🌐 Panel de Control Web Visual

Una vez desplegado en el móvil, abre en tu navegador favorito (Safari, Chrome, Firefox):

👉 **`http://<IP-DE-TU-MOVIL>:8090`**

### ¿Qué puedes hacer desde la web?
- **Arrastrar y soltar (Drag & Drop):** Suelta cualquier archivo `.mkv`, `.mp4` o `.avi` para subirlo al móvil con barra de progreso en tiempo real.
- **Cola de subidas masiva:** Acepta varios archivos a la vez, sube hasta 3 en paralelo y escribe directamente en bloques de 64 KB con limpieza de parciales si se interrumpe la red.
- **Carátulas automáticas en HD:** Al terminar la subida, busca y asocia el póster oficial en alta definición desde IMDb y TVMaze.
- **Reproductor HTML5 Integrado:** Previsualiza el contenido directamente en el navegador con streaming por rangos (HTTP 206 `Range`).
- **Gestión rápida:** Renombrar, mover o eliminar con un clic para liberar espacio en disco.

---

## 📺 Cómo verlo en tu Smart TV

1. Enciende tu Smart TV conectada a la misma red Wi-Fi.
2. En el mando a distancia, pulsa **Fuentes** (o **Dispositivos Conectados**).
3. Selecciona **Android Media Server**.
4. Navega a **Películas** o **Series**: verás todos los títulos con sus pósters en alta definición listos para reproducir.

---

## 🪄 Detección de Incompatibilidad y Botón Mágico

Algunas Smart TVs (como Samsung Tizen) rechazan archivos `.avi` antiguos de DivX/Xvid por hardware. Para no fundir la CPU ni calentar la batería del móvil forzándolo a transcodificar:
1. El panel web detecta si intentas subir un `.avi`.
2. Ofrece el botón **[ 🪄 Convertir y Subir ]**.
3. El asistente local (`mac_helper.py` o script CLI `enviar_al_servidor.sh`) usa `ffmpeg` nativo en tu PC/Mac para convertirlo a MP4 H.264/AAC a máxima velocidad y enviarlo listo al móvil.
