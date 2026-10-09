# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile — CineAlert Chile Bot
#
# Usa la imagen oficial de Playwright con Python 3.11 y Chromium preinstalado.
# Esto evita tener que ejecutar "playwright install" durante el build.
# ─────────────────────────────────────────────────────────────────────────────

# Imagen base oficial de Microsoft con Playwright + Python 3.11 + Chromium
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Metadatos
LABEL maintainer="CineAlert Chile Bot"
LABEL description="Bot de monitoreo de disponibilidad de entradas de cine en Chile"
LABEL version="1.0.0"

# Variables de entorno del sistema
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    TZ=America/Santiago \
    LANG=es_CL.UTF-8

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# ── Instalar dependencias Python ───────────────────────────────────────────
# Copiar solo requirements primero para aprovechar cache de capas Docker
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Copiar código fuente ────────────────────────────────────────────────────
COPY main.py config.py scrapers.py notifier.py state.py ./

# ── Crear directorio de datos persistentes ────────────────────────────────
RUN mkdir -p /app/data

# ── Healthcheck ───────────────────────────────────────────────────────────
# Verifica que el proceso Python esté corriendo cada 2 minutos
HEALTHCHECK --interval=2m --timeout=30s --start-period=60s --retries=3 \
    CMD pgrep -f "python main.py" || exit 1

# ── Usuario no-root por seguridad ─────────────────────────────────────────
# La imagen oficial de Playwright ya incluye usuario 'pwuser'
USER pwuser

# ── Punto de entrada ───────────────────────────────────────────────────────
CMD ["python", "-u", "main.py"]
