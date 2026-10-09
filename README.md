# CineAlert Chile Bot 🎬

Bot de monitoreo automático de disponibilidad de entradas de cine en Chile. Notifica vía Telegram cuando detecta que las entradas o preventas están disponibles en **Cineplanet**, **Cinépolis** y **Cinemark Chile**.

---

## Estructura del proyecto

```
cinebutbot/
├── main.py              # Orquestador principal (loop, Playwright)
├── config.py            # Carga y validación de configuración
├── scrapers.py          # Lógica de scraping por cadena de cines
├── notifier.py          # Envío de mensajes a Telegram
├── state.py             # Estado persistente anti-spam (JSON)
├── requirements.txt     # Dependencias Python
├── Dockerfile           # Imagen basada en Playwright oficial
├── docker-compose.yml   # Despliegue con reinicio automático
├── .env                 # ⚠️ Configuración (NO subir a Git)
└── data/
    └── state.json       # Estado generado en runtime
```

---

## Configuración inicial (`.env`)

Abre el archivo `.env` y completa los valores obligatorios:

```env
# OBLIGATORIO: ID del chat/grupo/canal donde recibirás las notificaciones
TELEGRAM_CHAT_ID=123456789

# OBLIGATORIO: URLs de las páginas de detalle de la película a monitorear
CINEPLANET_MOVIE_URL=https://www.cineplanet.cl/peliculas/nombre-de-la-pelicula
CINEPOLIS_MOVIE_URL=https://cinepolis.com/cl/pelicula/nombre-de-la-pelicula
CINEMARK_MOVIE_URL=https://www.cinemark.cl/pelicula/nombre-de-la-pelicula

# Nombre legible de la película
MOVIE_NAME=Nombre de la Película
```

> **¿Cómo obtener tu `TELEGRAM_CHAT_ID`?**
> Envía un mensaje a `@userinfobot` en Telegram. Te responderá con tu Chat ID.

---

## Ejecución con Docker (recomendado)

```bash
# 1. Construir la imagen
docker compose build

# 2. Iniciar el bot en segundo plano
docker compose up -d

# 3. Ver logs en tiempo real
docker compose logs -f

# 4. Detener el bot
docker compose down
```

El contenedor se reinicia automáticamente si falla o si reinicias el servidor (`restart: unless-stopped`).

---

## Ejecución local (sin Docker)

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Instalar navegador Chromium de Playwright
playwright install chromium

# 3. Ejecutar el bot
python main.py
```

---

## Lógica anti-spam

El bot mantiene un archivo `data/state.json` con el último estado de cada cine:

- **Primera ejecución**: solo notifica si las entradas ya están disponibles.
- **Cambio de estado** `No disponible → Disponible`: envía notificación inmediata.
- **Sin cambio**: no envía mensaje (evita spam).
- **Errores**: notifica solo cada 5 errores consecutivos.

---

## Formato de notificación Telegram

```
🎬 ¡ENTRADAS DISPONIBLES!

🏟️ Cine: Cineplanet Chile
🎞️ Película: Avatar 3
📅 Detectado: 09/10/2025 18:35:22

✅ Estado: DISPONIBLE PARA COMPRA

👉 Comprar entradas aquí
```

---

## Scrapers por cine

| Cine | Estrategia | Criterio de éxito |
|---|---|---|
| **Cineplanet** | Botón `button.call-to-action.movie-detail-header--purchase-button-large` | Existe, visible y no `disabled` |
| **Cinépolis** | Botón `button[class*='mf-movie-detail']` | Sin clases `disabled` ni `opacity-50` |
| **Cinemark** | Detecta botones con texto de horario (`\d{1,2}:\d{2}`) | Al menos 1 horario o botón de compra activo |

---

## Variables de entorno completas

| Variable | Requerida | Default | Descripción |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Token del bot de Telegram |
| `TELEGRAM_CHAT_ID` | ✅ | — | Chat ID de destino |
| `MOVIE_NAME` | ❌ | `Película monitoreada` | Nombre para notificaciones |
| `CINEPLANET_MOVIE_URL` | ❌ | — | URL de la película en Cineplanet |
| `CINEPOLIS_MOVIE_URL` | ❌ | — | URL de la película en Cinépolis |
| `CINEMARK_MOVIE_URL` | ❌ | — | URL de la película en Cinemark |
| `CHECK_INTERVAL` | ❌ | `300` | Intervalo en segundos |
| `PLAYWRIGHT_TIMEOUT` | ❌ | `30000` | Timeout de página en ms |
| `PAGE_SETTLE_MS` | ❌ | `3000` | Espera post-carga en ms |
| `HEADLESS` | ❌ | `true` | Modo headless |
| `STATE_FILE` | ❌ | `./data/state.json` | Ruta del estado persistente |
| `LOG_LEVEL` | ❌ | `INFO` | Nivel de logging |

---

## Seguridad — manejo de secretos

El proyecto separa la **configuración general** de los **secretos**:

| Archivo | ¿Contiene secretos? | ¿Se sube a Git? |
|---|---|---|
| `.env` | ❌ No | ✅ Sí (es seguro) |
| `.env.secrets` | ✅ Sí (token Telegram) | ❌ No (`.gitignore`) |
| `.env.secrets.example` | ❌ Plantilla vacía | ✅ Sí |

### Setup inicial de secretos

```bash
# 1. Copia la plantilla
cp .env.secrets.example .env.secrets

# 2. Edita .env.secrets y pega tu token real
TELEGRAM_BOT_TOKEN=8916685897:AAH5drK4Lh6jCaY2MWd2ur6c4zn0MfHJdXY
```

`config.py` carga `.env.secrets` primero (prioridad alta) y luego `.env`, de forma automática.

