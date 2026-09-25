# 📱 Android Home Server — Hermes AI Agent, DLNA Streaming & Cron Automation

Infraestructura completa de servidor doméstico 24/7 de bajo consumo montada sobre cualquier smartphone **Android en desuso** (arquitectura ARM64 `aarch64` o ARMv7), combinando un agente de inteligencia artificial autónomo (**Hermes Agent**), automatización programada (**Crons de empleo, chollos y telemetría**), sistema de megafonía física por altavoz y un **servidor multimedia DLNA con panel web visual**.

Sustituye por completo una VPS en la nube multiplicando los recursos de memoria RAM y potencia de procesamiento, con **cero euros de coste mensual** y un consumo eléctrico casi imperceptible de 1 a 3 vatios.

---

## 🏛️ 1. Arquitectura del Sistema

```text
                         ┌────────────────────────────────────────────────────────┐
                         │                    ANDROID SMARTPHONE                  │
                         │               (Android 8.0+ / Termux aarch64)          │
                         │                                                        │
                         │   ┌────────────────────────────────────────────────┐   │
                         │   │                      PM2                       │   │
                         │   │              (Process Daemon 24/7)             │   │
                         │   └───┬────────────────────┬───────────────────┬───┘   │
                         │       │                    │                   │       │
                         │       ▼                    ▼                   ▼       │
                         │ ┌───────────┐      ┌─────────────┐     ┌─────────────┐ │
                         │ │  Hermes   │      │ DLNA Server │     │    Media    │ │
                         │ │   Agent   │      │  (MiniDLNA) │     │  Dashboard  │ │
                         │ │ (Outbound)│      │ (Port 8200) │     │ (Port 8090) │ │
                         │ └─────┬─────┘      └──────┬──────┘     └──────▲──────┘ │
                         │       │                   │                   │        │
                         └───────┼───────────────────┼───────────────────┼────────┘
                                 │                   │                   │
             ┌───────────────────┴─────────┐         │                   │ HTTP / API
             ▼                             ▼         ▼                   │ (Red Local)
    ┌─────────────────┐           ┌──────────────┐ ┌───────────────┐     │
    │ Telegram Bot    │           │ LLM APIs     │ │ Smart TV      │     │
    │ (Alertas & DMs) │           │ (DeepSeek,   │ │ (Samsung, LG, │     │
    └─────────────────┘           │  OpenAI, etc)│ │  Android TV)  │     │
                                  └──────────────┘ └───────────────┘     │
                                                                         │
                         ┌───────────────────────────────────────────────┴────────┐
                         │              PC / Mac Mini / Portátil (Cliente)        │
                         │                                                        │
                         │   ┌────────────────────────────────────────────────┐   │
                         │   │     Navegador Web: http://<IP-DEL-MOVIL>:8090   │   │
                         │   └──────────────────────┬─────────────────────────┘   │
                         │                          │ (Localhost API / CORS)      │
                         │                          ▼                             │
                         │   ┌────────────────────────────────────────────────┐   │
                         │   │       Conversion Helper (Opcional en PC/Mac)   │   │
                         │   │    (Port 8095 · ffmpeg nativo · 0% CPU en reposo)  │
                         │   └────────────────────────────────────────────────┘   │
                         └────────────────────────────────────────────────────────┘
```

---

## ⚡ 2. Comparativa: Móvil Viejo vs VPS Gratuita en la Nube

| Métrica | Instancia Cloud Gratuita / Barata | Smartphone Android (ej. 6 GB RAM) | Ventaja del Móvil |
| :--- | :--- | :--- | :--- |
| **Memoria RAM** | 1 GB *(Cuelgues por falta de memoria OOM)* | **4 GB – 8 GB LPDDR4X** (~2.5+ GB libres) | **+400% a +700% de memoria** |
| **CPU** | 0.25 vCPU compartida (con throttling) | **8 núcleos físicos ARM64** | Procesamiento paralelo real |
| **Almacenamiento** | Disco virtual en red / HDD lento | **Memoria flash UFS** ultrarrápida | Lecturas y escrituras SQLite instantáneas |
| **SAI / UPS** | Ninguno (se apaga ante cortes de luz) | **Batería integrada** | Sigue funcionando horas sin apagarse |
| **Coste** | Facturación por tráfico o cuota mensual | **0 € para siempre** | Sin sorpresas |
| **Consumo Eléctrico**| N/A | **~1 a 3 vatios** | Despreciable en la factura de la luz |

---

## 🔋 3. Cuidado y Seguridad de la Batería (Estrategia 50%)

Tener una batería de iones de litio conectada a corriente continua al 100% las 24 horas del día degrada la celda e incrementa el riesgo de hinchazón. Para garantizar **cero degradación y máxima seguridad**:

1. **Voltaje de Reposo Químico (45% - 70%):**  
   El litio se mantiene en su estado más estable en torno a ~3.8V por celda (entre el 40% y el 60%).
2. **Temporizador Físico de Enchufe:**  
   Utiliza un enchufe con temporizador analógico/mecánico programado para activarse **30 a 45 minutos dos veces al día** (por ejemplo: 08:00–08:45 y 20:00–20:45).
   * El resto del día el cargador permanece sin corriente.
   * La batería actúa como un **SAI / UPS integrado**: si se corta la luz en tu casa, el servidor no se apaga ni corrompe datos.
3. **Watchdog de Batería y Temperatura (`cron_battery_guard.py`):**  
   Un proceso programado cada 30 minutos vigila el estado de la batería mediante `termux-battery-status`:
   * **Batería Baja (< 25%):** Si el nivel cae del 25% (ej. falló el temporizador o se desconectó el cable), envía una **alerta urgente por Telegram**.
   * **Temperatura Crítica (≥ 45°C / ≥ 48°C):** Si la batería supera los 45°C, emite un aviso inmediato para prevenir sobrecalentamiento.

---

## 🌐 4. Conectividad: Por qué NO necesitas IP estática ni abrir puertos

* **Comunicación por Polling Saliente (*Outbound Long-Polling*):**  
  El bot de Telegram y las llamadas a los modelos de lenguaje (LLM) se ejecutan mediante conexiones salientes hacia internet.
* **Independencia de Red:**  
  No necesitas abrir ni redirigir ningún puerto en el router. Si tu proveedor de internet cambia tu IP pública o trasladas el teléfono a otra red Wi-Fi, **el servidor sigue funcionando sin interrupción**.
* **Acceso local SSH:**  
  Para administración interna desde tu ordenador dentro de la misma red Wi-Fi:  
  `ssh -p 8022 u0_a256@<IP-DE-TU-MOVIL>`
* **Acceso al Dashboard Multimedia:**  
  Abriendo `http://<IP-DE-TU-MOVIL>:8090` desde cualquier navegador de tu red local.

---

## 🤖 5. Soporte Multi-LLM y Hermes Agent

El servidor está preparado para trabajar con **cualquier modelo de lenguaje compatible con la API de OpenAI**. Puedes elegir tu proveedor favorito en el archivo `.env`:

* **DeepSeek:** `deepseek-flash`, `deepseek-chat`, `deepseek-reasoner` (económico, ultrarrápido y excelente en español).
* **OpenAI:** `gpt-4o-mini`, `gpt-4o`.
* **Groq:** `llama-3.3-70b-versatile` (inferencia en milisegundos).
* **OpenRouter:** Acceso unificado a modelos comerciales y open-source.
* **Ollama / Local:** Modelos ejecutándose en otra máquina de tu red local.

### Motor de Búsqueda Resiliente con Triple Redundancia (`scripts/web_search_helper.py`)
1. **Rotación Multi-Clave de Tavily:** Soporta múltiples claves en `.env` (`TAVILY_KEYS="key1,key2"`). Si una alcanza el límite de cuota mensual, conmuta automáticamente a la siguiente sin interrumpir las tareas.
2. **Extracción Estructurada con Firecrawl:** Convierte páginas web complejas a Markdown limpio.
3. **Fallback Nativo DuckDuckGo (`ddgs`):** Si las APIs externas no están disponibles, utiliza búsquedas gratuitas directas sin coste de saldo.

---

## ⏰ 6. Batería de Crons Automatizados

El sistema incluye una serie de tareas programadas independientes y configurables:

| Tarea | Script | Frecuencia | Destino | Funcionalidad |
| :--- | :--- | :--- | :--- | :--- |
| **Monitor de Batería** | `cron_battery_guard.py` | Cada 30 min | Telegram | Vigilancia térmica (≥45°C) y nivel de batería (<25%). |
| **Radar de Empleo** | `cron_job_radar.py` | Lunes-Viernes 08:00 | Telegram | Rastreo en portales clave (InfoJobs, Indeed, Tecnoempleo, remotos) con memoria contra duplicados (`seen_jobs.json`) y curación por IA. |
| **Radar de Chollos** | `cron_deals_radar.py` | Diario 12:00 | Telegram | Detección de ofertas reales en tecnología, hardware, consolas y errores de precio. |
| **Noticias Tech** | `cron_news_digest.py` | Diario 14:00 | Telegram | Resumen matutino de las noticias de tecnología e IA más relevantes del día. |

---

## 📢 7. Megáfono TTS Físico (`/di` y `/habla`)

Aprovecha los altavoces físicos del teléfono como un sistema de megafonía remota controlable desde Telegram en cualquier momento:

* **Comandos directos:** `/di <mensaje>` o `/habla <mensaje>`
* **Cero coste y latencia ultra baja:** Implementado como plugin nativo de Hermes (`plugins/megaphone`). Intercepta el comando antes del bucle del LLM, respondiendo en menos de 300 ms con **0 tokens consumidos**.
* **Volumen Máximo Garantizado:** Eleva automáticamente el volumen multimedia de Android al tope (`15/15`) y sintetiza la voz en español (`termux-tts-speak -s MUSIC -l es-ES`).

---

## 🎬 8. Servidor Multimedia & Dashboard Web (`:8090`)

El móvil funciona como servidor de streaming local para Smart TVs (Samsung Tizen, LG webOS, Android TV) y como panel de control interactivo:

* **Streaming DLNA (MiniDLNA en puerto 8200):** Lectura directa de disco sin transcodificación en el móvil. Consumo medido: **~17 MB de RAM y 0% de CPU**.
* **Dashboard Web Moderno (puerto 8090):**
  * Bento card con telemetría en tiempo real: temperatura, ecualizador de pulso, batería, memoria RAM y gigas libres de flash UFS.
  * Subidas masivas Drag & Drop con streaming directo a disco en bloques de 64 KB y limpieza de parciales si se interrumpe la red.
  * Carátulas HD automáticas descargadas desde IMDb y TVMaze (`fetch_cover.py`).
  * Reproductor HTML5 con soporte de rangos HTTP (206) para saltar a cualquier minuto.
* **El "Botón Mágico" para vídeos incompatibles:**
  * Si una Smart TV rechaza archivos antiguos `.avi` (DivX/Xvid), el asistente local en tu ordenador (`mac_helper.py` o `enviar_al_servidor.sh`) convierte el archivo con `ffmpeg` nativo a MP4 H.264/AAC por hardware y lo sube directamente al servidor listo para la TV sin sobrecalentar el móvil.

---

## 🚀 9. Instalación Paso a Paso desde Cero

### 1. Requisitos previos en el móvil
1. Descarga e instala **Termux** y **Termux:API** desde [F-Droid](https://f-droid.org) (evita Google Play).
2. En los ajustes de Android del móvil, desactiva la optimización de batería para Termux (*Ajustes → Apps → Termux → Batería → "Sin restricciones"*).

### 2. Clonar y configurar
Abre Termux en el móvil y clona el repositorio:

```bash
pkg install -y git
git clone https://github.com/moisesvalero/android-home-server.git ~/.hermes-server
cd ~/.hermes-server

# Copiar plantilla de variables y editar con tus claves
cp .env.example .env
nano .env
```

### 3. Ejecutar el instalador automático
```bash
chmod +x install.sh
./install.sh
```

El script configurará los paquetes nativos, el entorno de Python, MiniDLNA y registrará los procesos en PM2.

---

## 🔒 10. Hardening SSH en Termux

Para garantizar que el acceso remoto a través del puerto `8022` sea seguro:

1. Añade tu clave pública SSH a `~/.ssh/authorized_keys`.
2. Edita `$PREFIX/etc/ssh/sshd_config`:
   ```text
   PasswordAuthentication no
   PubkeyAuthentication yes
   PermitEmptyPasswords no
   MaxAuthTries 3
   ```
3. Reinicia el servicio SSH:
   ```bash
   pkill sshd && sshd
   ```
4. **Seguridad de red:** Nunca abras el puerto 8022 en tu router. El servidor solo debe ser accesible dentro de tu Wi-Fi local o mediante una VPN como WireGuard o Tailscale.

---

## 🛠️ 11. Gestión y Mantenimiento

```bash
# Ver estado y consumo en vivo de todos los servicios
pm2 status

# Inspeccionar logs en tiempo real
pm2 logs hermes           # Logs del agente de IA
pm2 logs media-dashboard  # Logs de peticiones HTTP y subidas
pm2 logs dlna-server      # Logs del servidor DLNA

# Reiniciar servicios
pm2 restart all

# Guardar lista de servicios activos para auto-arranque
pm2 save
```

---

## 📄 Licencia

Distribuido bajo la licencia [MIT](LICENSE). Siéntete libre de utilizarlo, modificarlo y compartirlo para darle una segunda vida a tu hardware en desuso.
