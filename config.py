"""
config.py — Carga y validación de configuración desde .env
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Carga variables de entorno desde .env (si existe)
load_dotenv(override=True)


def _require(key: str) -> str:
    """Obtiene una variable de entorno requerida o lanza un error."""
    value = os.getenv(key, "").strip()
    if not value:
        raise ValueError(
            f"Variable de entorno requerida no configurada: '{key}'. "
            f"Edita el archivo .env antes de ejecutar el bot."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str

    @property
    def api_url(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/sendMessage"


@dataclass(frozen=True)
class CinemaConfig:
    name: str
    url: str
    enabled: bool = True


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    movie_name: str
    cinemas: list[CinemaConfig]
    check_interval: int        # segundos
    playwright_timeout: int    # milisegundos
    page_settle_ms: int        # milisegundos
    headless: bool
    state_file: Path
    log_level: str


def load_config() -> AppConfig:
    """Carga y valida toda la configuración de la aplicación."""

    telegram = TelegramConfig(
        bot_token=_require("TELEGRAM_BOT_TOKEN"),
        chat_id=_require("TELEGRAM_CHAT_ID"),
    )

    movie_name = _optional("MOVIE_NAME", "Película monitoreada")

    cinemas = [
        CinemaConfig(
            name="Cineplanet Chile",
            url=_optional(
                "CINEPLANET_MOVIE_URL",
                "https://www.cineplanet.cl/peliculas/",
            ),
            enabled=bool(_optional("CINEPLANET_MOVIE_URL")),
        ),
        CinemaConfig(
            name="Cinépolis Chile",
            url=_optional(
                "CINEPOLIS_MOVIE_URL",
                "https://cinepolis.com/cl/pelicula/",
            ),
            enabled=bool(_optional("CINEPOLIS_MOVIE_URL")),
        ),
        CinemaConfig(
            name="Cinemark Chile",
            url=_optional(
                "CINEMARK_MOVIE_URL",
                "https://www.cinemark.cl/pelicula/",
            ),
            enabled=bool(_optional("CINEMARK_MOVIE_URL")),
        ),
    ]

    state_file = Path(_optional("STATE_FILE", "./data/state.json"))
    state_file.parent.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        telegram=telegram,
        movie_name=movie_name,
        cinemas=cinemas,
        check_interval=int(_optional("CHECK_INTERVAL", "300")),
        playwright_timeout=int(_optional("PLAYWRIGHT_TIMEOUT", "30000")),
        page_settle_ms=int(_optional("PAGE_SETTLE_MS", "3000")),
        headless=_optional("HEADLESS", "true").lower() == "true",
        state_file=state_file,
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
    )
