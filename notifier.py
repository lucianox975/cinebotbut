"""
notifier.py — Envío de notificaciones vía Telegram Bot API
"""

import logging
from datetime import datetime

import httpx

from config import TelegramConfig

logger = logging.getLogger(__name__)


AVAILABLE_TEMPLATE = """
🎬 <b>¡ENTRADAS DISPONIBLES!</b>

🏟️ <b>Cine:</b> {cinema_name}
🎞️ <b>Película:</b> {movie_name}
📅 <b>Detectado:</b> {timestamp}

✅ <b>Estado:</b> <i>DISPONIBLE PARA COMPRA</i>

🔗 <a href="{url}">👉 Comprar entradas aquí</a>

<i>⚡ Bot CineAlert Chile — Monitoreo automático</i>
""".strip()

UNAVAILABLE_TEMPLATE = """
⏳ <b>Sin disponibilidad aún</b>

🏟️ <b>Cine:</b> {cinema_name}
🎞️ <b>Película:</b> {movie_name}
📅 <b>Verificado:</b> {timestamp}

❌ <b>Estado:</b> <i>No disponible</i>

<i>⚡ Bot CineAlert Chile — Monitoreo automático</i>
""".strip()

ERROR_TEMPLATE = """
⚠️ <b>Error de scraping</b>

🏟️ <b>Cine:</b> {cinema_name}
🎞️ <b>Película:</b> {movie_name}
📅 <b>Momento:</b> {timestamp}

🐛 <b>Error:</b> <code>{error}</code>

<i>⚡ Bot CineAlert Chile</i>
""".strip()

STARTUP_TEMPLATE = """
🤖 <b>Bot CineAlert Chile iniciado</b>

🎞️ <b>Monitoreando:</b> {movie_name}
🔍 <b>Cines activos:</b> {cinema_list}
⏱️ <b>Intervalo:</b> cada {interval} minutos

<i>Recibirás una notificación cuando las entradas estén disponibles.</i>
""".strip()


async def send_telegram_message(
    cfg: TelegramConfig,
    text: str,
    disable_notification: bool = False,
) -> bool:
    """
    Envía un mensaje al chat de Telegram configurado.

    Returns:
        True si el mensaje fue enviado correctamente, False en caso contrario.
    """
    payload = {
        "chat_id": cfg.chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
        "disable_notification": disable_notification,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(cfg.api_url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("ok"):
                logger.info("✅ Mensaje Telegram enviado correctamente.")
                return True
            else:
                logger.error(
                    "❌ Telegram API respondió con error: %s", data.get("description")
                )
                return False

    except httpx.HTTPStatusError as exc:
        logger.error("❌ HTTP error al enviar Telegram: %s", exc)
    except httpx.RequestError as exc:
        logger.error("❌ Error de red al enviar Telegram: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ Error inesperado al enviar Telegram: %s", exc)

    return False


def _ts() -> str:
    """Timestamp legible en hora local."""
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


async def notify_available(
    cfg: TelegramConfig,
    cinema_name: str,
    movie_name: str,
    url: str,
) -> bool:
    text = AVAILABLE_TEMPLATE.format(
        cinema_name=cinema_name,
        movie_name=movie_name,
        timestamp=_ts(),
        url=url,
    )
    return await send_telegram_message(cfg, text)


async def notify_unavailable(
    cfg: TelegramConfig,
    cinema_name: str,
    movie_name: str,
) -> bool:
    text = UNAVAILABLE_TEMPLATE.format(
        cinema_name=cinema_name,
        movie_name=movie_name,
        timestamp=_ts(),
    )
    return await send_telegram_message(cfg, text, disable_notification=True)


async def notify_error(
    cfg: TelegramConfig,
    cinema_name: str,
    movie_name: str,
    error: str,
) -> bool:
    text = ERROR_TEMPLATE.format(
        cinema_name=cinema_name,
        movie_name=movie_name,
        timestamp=_ts(),
        error=str(error)[:300],
    )
    return await send_telegram_message(cfg, text, disable_notification=True)


async def notify_startup(
    cfg: TelegramConfig,
    movie_name: str,
    cinema_names: list[str],
    interval_seconds: int,
) -> bool:
    text = STARTUP_TEMPLATE.format(
        movie_name=movie_name,
        cinema_list=", ".join(cinema_names),
        interval=interval_seconds // 60,
    )
    return await send_telegram_message(cfg, text, disable_notification=True)
