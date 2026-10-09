"""
scrapers.py — Lógica de scraping por cadena de cines

Cada función recibe una página de Playwright ya abierta y retorna:
    (available: bool, detail: str)

- available: True si las entradas están disponibles para compra
- detail:    Mensaje descriptivo del estado detectado
"""

import logging
import re

from playwright.async_api import Page, TimeoutError as PwTimeout

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Utilidades comunes
# ─────────────────────────────────────────────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

EXTRA_HEADERS = {
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


async def _safe_navigate(page: Page, url: str, timeout: int, settle_ms: int) -> None:
    """Navega a una URL y espera que la red esté estable."""
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    await page.wait_for_timeout(settle_ms)


# ─────────────────────────────────────────────────────────────────────────────
# 1. CINEPLANET
# ─────────────────────────────────────────────────────────────────────────────

async def check_cineplanet(
    page: Page,
    url: str,
    timeout: int,
    settle_ms: int,
) -> tuple[bool, str]:
    """
    Detecta si el botón "Comprar" en Cineplanet está habilitado.

    Estrategia:
    - Busca el botón primario de compra por clase o texto.
    - Verifica que no esté deshabilitado (disabled attr / clase disabled).
    - Verifica que no contenga texto de "próximamente" o "no disponible".
    """
    try:
        await _safe_navigate(page, url, timeout, settle_ms)

        # Selectores de mayor a menor especificidad
        selectors = [
            "button.call-to-action.movie-detail-header--purchase-button-large",
            "button.movie-detail-header--purchase-button-large",
            "button[class*='purchase-button']",
        ]

        buy_button = None
        for sel in selectors:
            locator = page.locator(sel).first
            if await locator.count() > 0:
                buy_button = locator
                logger.debug("Cineplanet: botón encontrado con selector '%s'", sel)
                break

        # Fallback: buscar por texto "Comprar"
        if buy_button is None:
            text_loc = page.get_by_role("button", name=re.compile(r"comprar", re.I))
            if await text_loc.count() > 0:
                buy_button = text_loc.first
                logger.debug("Cineplanet: botón encontrado por texto 'Comprar'")

        if buy_button is None:
            # Verificar si existe texto de "próximamente"
            page_text = (await page.content()).lower()
            if any(k in page_text for k in ["próximamente", "proximamente", "coming soon"]):
                return False, "Página muestra 'Próximamente' — sin botón de compra."
            return False, "Botón de compra no encontrado en el DOM."

        # ¿Está deshabilitado?
        is_disabled = await buy_button.is_disabled()
        if is_disabled:
            return False, "Botón 'Comprar' existe pero está deshabilitado (disabled)."

        # ¿Está visible?
        is_visible = await buy_button.is_visible()
        if not is_visible:
            return False, "Botón 'Comprar' existe pero no es visible."

        # Verificar texto del botón
        btn_text = (await buy_button.inner_text()).strip().lower()
        if any(k in btn_text for k in ["próximamente", "no disponible", "agotado"]):
            return False, f"Botón encontrado con texto de no-disponibilidad: '{btn_text}'"

        return True, f"✅ Botón de compra activo detectado: '{btn_text}'"

    except PwTimeout:
        raise TimeoutError(f"Timeout al cargar Cineplanet ({url})")
    except Exception as exc:
        raise RuntimeError(f"Error inesperado en Cineplanet: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# 2. CINÉPOLIS
# ─────────────────────────────────────────────────────────────────────────────

async def check_cinepolis(
    page: Page,
    url: str,
    timeout: int,
    settle_ms: int,
) -> tuple[bool, str]:
    """
    Detecta si el botón "Ver horarios" en Cinépolis Chile está habilitado.

    Estrategia:
    - Busca el botón por clase parcial 'mf-movie-detail'.
    - Verifica ausencia de clases de deshabilitado ('disabled', 'opacity-50').
    - Alternativa: busca por texto "Ver horarios".
    """
    try:
        await _safe_navigate(page, url, timeout, settle_ms)

        # Esperar a que el contenido dinámico cargue
        try:
            await page.wait_for_selector(
                "button[class*='mf-movie-detail'], button[class*='movie-detail']",
                timeout=10000,
            )
        except PwTimeout:
            logger.debug("Cinépolis: timeout esperando selector principal, continuando...")

        # Buscar botón por clase parcial
        selectors = [
            "button[class*='mf-movie-detail-flex']",
            "button[class*='mf-movie-detail']",
            "button[class*='movie-detail']",
        ]

        btn_locator = None
        for sel in selectors:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                btn_locator = loc
                break

        # Fallback: búsqueda por texto
        if btn_locator is None:
            for text in ["Ver horarios", "Comprar", "Compra"]:
                loc = page.get_by_role("button", name=re.compile(text, re.I))
                if await loc.count() > 0:
                    btn_locator = loc.first
                    break

        if btn_locator is None:
            page_text = (await page.content()).lower()
            if any(k in page_text for k in ["próximamente", "coming soon"]):
                return False, "Cinépolis muestra 'Próximamente' — sin botón de horarios."
            return False, "Botón 'Ver horarios' no encontrado en el DOM."

        # Verificar clases de deshabilitado
        class_attr = await btn_locator.get_attribute("class") or ""
        disabled_classes = ["mf-movie-detail-disabled", "opacity-50", "disabled", "btn-disabled"]
        for cls in disabled_classes:
            if cls in class_attr:
                return False, f"Botón encontrado pero con clase de deshabilitado: '{cls}'"

        # Verificar atributo disabled
        is_disabled = await btn_locator.is_disabled()
        if is_disabled:
            return False, "Botón 'Ver horarios' tiene atributo disabled."

        is_visible = await btn_locator.is_visible()
        if not is_visible:
            return False, "Botón 'Ver horarios' no es visible."

        btn_text = (await btn_locator.inner_text()).strip()
        return True, f"✅ Botón de horarios activo detectado: '{btn_text}'"

    except PwTimeout:
        raise TimeoutError(f"Timeout al cargar Cinépolis ({url})")
    except Exception as exc:
        raise RuntimeError(f"Error inesperado en Cinépolis: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# 3. CINEMARK
# ─────────────────────────────────────────────────────────────────────────────

HORARIO_PATTERN = re.compile(
    r"\b\d{1,2}:\d{2}\s*(hs|hrs|am|pm)?\b",
    re.IGNORECASE,
)


async def check_cinemark(
    page: Page,
    url: str,
    timeout: int,
    settle_ms: int,
) -> tuple[bool, str]:
    """
    Detecta si Cinemark Chile muestra horarios disponibles para la película.

    Estrategia multi-nivel:
    1. Busca botones de horario (ej. "18:20hs") en la sección de funciones.
    2. Busca botón "Comprar entradas" o "Seleccionar función".
    3. Busca texto de horarios en el DOM completo.
    4. Verifica ausencia de indicadores de "próximamente".
    """
    try:
        await _safe_navigate(page, url, timeout, settle_ms)

        # Esperar contenido dinámico
        try:
            await page.wait_for_selector(
                ".showtimes, .schedule, [class*='showtime'], [class*='horario'],"
                " [class*='schedule'], .movie-detail",
                timeout=10000,
            )
        except PwTimeout:
            logger.debug("Cinemark: timeout esperando sección de horarios, continuando...")

        # ── Nivel 1: Botones con texto de horario ──────────────────────────
        # Busca botones que contengan patrones de hora (ej. "18:20")
        page_content = await page.content()
        horario_matches = HORARIO_PATTERN.findall(page_content)
        if horario_matches:
            # Verificar que sean botones interactivos (no texto plano)
            time_buttons = page.locator(
                "button, a[role='button'], .showtime-button, "
                "[class*='showtime'], [class*='horario']"
            ).filter(has_text=re.compile(r"\d{1,2}:\d{2}"))

            count = await time_buttons.count()
            if count > 0:
                sample = (await time_buttons.first.inner_text()).strip()
                return True, f"✅ {count} horario(s) disponible(s). Primero detectado: '{sample}'"

        # ── Nivel 2: Botón de compra / selección de función ───────────────
        buy_selectors = [
            "button[class*='buy'], button[class*='purchase'], button[class*='ticket']",
            "a[class*='buy-ticket'], a[class*='purchase']",
            "button[class*='select-showtime'], button[class*='book']",
        ]
        for sel in buy_selectors:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                text = (await loc.inner_text()).strip()
                if not await loc.is_disabled():
                    return True, f"✅ Botón de compra activo detectado: '{text}'"

        # Fallback texto
        for text in ["Comprar entradas", "Seleccionar función", "Comprar", "Buy"]:
            loc = page.get_by_role("button", name=re.compile(text, re.I)).first
            if await loc.count() > 0 and not await loc.is_disabled():
                t = (await loc.inner_text()).strip()
                return True, f"✅ Botón de compra encontrado: '{t}'"

        # ── Nivel 3: Texto de horarios en el HTML ─────────────────────────
        lower_content = page_content.lower()
        horarios_raw = HORARIO_PATTERN.findall(page_content)
        if horarios_raw:
            return True, f"✅ Texto con {len(horarios_raw)} horario(s) detectado en la página."

        # ── Nivel 4: Indicadores negativos ────────────────────────────────
        negative_keywords = [
            "próximamente", "proximamente", "coming soon",
            "preventa próximamente", "no hay funciones",
        ]
        for kw in negative_keywords:
            if kw in lower_content:
                return False, f"Página muestra indicador negativo: '{kw}'"

        return False, "No se detectaron horarios ni botones de compra activos."

    except PwTimeout:
        raise TimeoutError(f"Timeout al cargar Cinemark ({url})")
    except Exception as exc:
        raise RuntimeError(f"Error inesperado en Cinemark: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Mapa de scrapers por nombre de cine
# ─────────────────────────────────────────────────────────────────────────────

SCRAPER_MAP = {
    "Cineplanet Chile": check_cineplanet,
    "Cinépolis Chile": check_cinepolis,
    "Cinemark Chile": check_cinemark,
}
