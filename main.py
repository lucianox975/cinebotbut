"""
main.py — CineAlert Chile Bot
Monitorea disponibilidad de entradas de cine en Chile y notifica vía Telegram.

Arquitectura:
- Playwright async (Chromium headless) para scraping dinámico
- Ciclo de 5 minutos con asyncio
- Estado persistente en JSON para control anti-spam
- Try-except independiente por cada cine (fallo aislado)
"""

import asyncio
import logging
import sys
from datetime import datetime

from playwright.async_api import async_playwright, Browser, BrowserContext

from config import AppConfig, CinemaConfig, load_config
from notifier import notify_available, notify_error, notify_startup
from scrapers import SCRAPER_MAP, USER_AGENT, EXTRA_HEADERS
from state import StateManager

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(level: str) -> None:
    log_level = getattr(logging, level, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Silenciar logs verbosos de librerías externas
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Scraping de un cine individual
# ─────────────────────────────────────────────────────────────────────────────

async def check_cinema(
    cinema: CinemaConfig,
    context: BrowserContext,
    cfg: AppConfig,
    state: StateManager,
) -> None:
    """
    Ejecuta el scraper para un cine y gestiona notificaciones.
    Los errores quedan contenidos aquí para no afectar a otros cines.
    """
    cinema_name = cinema.name
    scraper_fn = SCRAPER_MAP.get(cinema_name)

    if scraper_fn is None:
        logger.warning("No hay scraper registrado para '%s'. Omitiendo.", cinema_name)
        return

    page = await context.new_page()
    try:
        logger.info("🔍 Revisando %s → %s", cinema_name, cinema.url)
        available, detail = await scraper_fn(
            page=page,
            url=cinema.url,
            timeout=cfg.playwright_timeout,
            settle_ms=cfg.page_settle_ms,
        )

        status_icon = "✅" if available else "❌"
        logger.info("%s [%s] %s", status_icon, cinema_name, detail)

        # Control anti-spam: ¿debemos notificar?
        if state.should_notify(cinema_name, available):
            if available:
                sent = await notify_available(
                    cfg=cfg.telegram,
                    cinema_name=cinema_name,
                    movie_name=cfg.movie_name,
                    url=cinema.url,
                )
                state.update(cinema_name, available=True, notified=sent)
                logger.info("📨 Notificación de DISPONIBILIDAD enviada para '%s'.", cinema_name)
            else:
                # Solo loguear — no spamear con mensajes de "no disponible"
                state.update(cinema_name, available=False, notified=False)
        else:
            state.update(cinema_name, available=available, notified=False)
            logger.debug("Sin cambio de estado para '%s'. No se notifica.", cinema_name)

    except Exception as exc:  # noqa: BLE001
        error_count = state.record_error(cinema_name)
        logger.error("💥 Error en '%s' (intento #%d): %s", cinema_name, error_count, exc)

        # Enviar alerta de error solo cada 5 errores consecutivos para no spamear
        if error_count % 5 == 1:
            await notify_error(
                cfg=cfg.telegram,
                cinema_name=cinema_name,
                movie_name=cfg.movie_name,
                error=str(exc),
            )
    finally:
        await page.close()


# ─────────────────────────────────────────────────────────────────────────────
# Ciclo principal de scraping
# ─────────────────────────────────────────────────────────────────────────────

async def run_cycle(
    browser: Browser,
    cfg: AppConfig,
    state: StateManager,
) -> None:
    """Ejecuta un ciclo completo de revisión de todos los cines activos."""
    enabled_cinemas = [c for c in cfg.cinemas if c.enabled and c.url]
    if not enabled_cinemas:
        logger.warning("⚠️  No hay cines configurados con URL válida.")
        return

    # Crear contexto con User-Agent y headers personalizados
    context = await browser.new_context(
        user_agent=USER_AGENT,
        extra_http_headers=EXTRA_HEADERS,
        viewport={"width": 1280, "height": 900},
        locale="es-CL",
        timezone_id="America/Santiago",
        ignore_https_errors=True,
    )

    try:
        # Ejecutar scrapers en paralelo (uno por cine)
        tasks = [
            check_cinema(cinema, context, cfg, state)
            for cinema in enabled_cinemas
        ]
        await asyncio.gather(*tasks, return_exceptions=False)
    finally:
        await context.close()

    logger.info(
        "📊 Estado: %s",
        " | ".join(
            f"{name}={'✅' if info.get('available') else '❌'}"
            for name, info in state.summary().items()
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    """Punto de entrada principal del bot."""
    # Cargar configuración
    cfg = load_config()
    setup_logging(cfg.log_level)

    logger.info("=" * 60)
    logger.info("🎬 CineAlert Chile Bot — iniciando")
    logger.info("   Película : %s", cfg.movie_name)
    logger.info("   Intervalo: cada %d segundos (%d min)", cfg.check_interval, cfg.check_interval // 60)
    logger.info("   Headless : %s", cfg.headless)
    logger.info("   Estado   : %s", cfg.state_file)
    logger.info("=" * 60)

    # Inicializar gestor de estado
    state = StateManager(cfg.state_file)

    # Notificación de inicio al canal Telegram
    active_cinema_names = [c.name for c in cfg.cinemas if c.enabled and c.url]
    await notify_startup(
        cfg=cfg.telegram,
        movie_name=cfg.movie_name,
        cinema_names=active_cinema_names,
        interval_seconds=cfg.check_interval,
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=cfg.headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,900",
            ],
        )

        try:
            cycle_count = 0
            while True:
                cycle_count += 1
                start = datetime.now()
                logger.info("🔄 Ciclo #%d — %s", cycle_count, start.strftime("%H:%M:%S"))

                try:
                    await run_cycle(browser, cfg, state)
                except Exception as exc:  # noqa: BLE001
                    logger.error("💥 Error en ciclo principal: %s", exc)

                elapsed = (datetime.now() - start).total_seconds()
                sleep_secs = max(0, cfg.check_interval - elapsed)
                logger.info(
                    "⏱️  Ciclo #%d completado en %.1fs. Próxima revisión en %.0fs.",
                    cycle_count,
                    elapsed,
                    sleep_secs,
                )
                await asyncio.sleep(sleep_secs)

        except asyncio.CancelledError:
            logger.info("🛑 Bot detenido por señal de cancelación.")
        except KeyboardInterrupt:
            logger.info("🛑 Bot detenido por el usuario (Ctrl+C).")
        finally:
            await browser.close()
            logger.info("✅ Recursos liberados. Hasta luego.")


if __name__ == "__main__":
    asyncio.run(main())
