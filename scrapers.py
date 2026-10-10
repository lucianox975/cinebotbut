"""
scrapers.py — Lógica de scraping por cadena de cines

Cada función recibe una página de Playwright ya abierta y retorna:
    (available: bool, detail: str)

- available: True si las entradas están disponibles para compra
- detail:    Mensaje descriptivo del estado detectado
"""

import logging
import re

from bs4 import BeautifulSoup
from curl_cffi import requests
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
# 3. CINEMARK (HTTP con curl_cffi para bypass WAF/Cloudflare)
# ─────────────────────────────────────────────────────────────────────────────

CINEMARK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "es-CL,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

HORARIO_PATTERN = re.compile(
    r"\b\d{1,2}:\d{2}\s*(hs|hrs|am|pm)?\b",
    re.IGNORECASE,
)


def check_cinemark_http(url: str, timeout: int = 15) -> tuple[bool, str]:
    """
    Scraper exclusivo para Cinemark Chile usando curl_cffi (impersonando Chrome).
    Evita la detección de automatización (Playwright/Puppeteer) y el bloqueo por Cloudflare/WAF.

    Retorna:
        (available: bool, detail: str)
    """
    logger.debug("Cinemark HTTP: solicitando %s con curl_cffi impersonate='chrome120'", url)

    try:
        response = requests.get(
            url,
            impersonate="chrome120",
            headers=CINEMARK_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
    except Exception as exc:
        logger.error("Cinemark HTTP error de conexión: %s", exc)
        return False, f"⚠️ Error de conexión HTTP hacia Cinemark: {exc}"

    # 1. Validación de código de estado (Anti-Bot / Cloudflare)
    if response.status_code in (403, 429):
        logger.warning("Cinemark HTTP bloqueado por WAF/Cloudflare (HTTP %d)", response.status_code)
        return False, f"⚠️ BLOQUEADO por WAF/Cloudflare (HTTP {response.status_code})"
    elif response.status_code == 404:
        return False, "❌ Página no encontrada (HTTP 404)"
    elif response.status_code != 200:
        return False, f"⚠️ Respuesta HTTP inusual ({response.status_code})"

    # 2. Parseo del HTML con BeautifulSoup
    soup = BeautifulSoup(response.text, "html.parser")

    # Contenedores de horarios típicos de Cinemark (Material-UI y clases semánticas)
    schedule_containers = soup.select(
        "[class*='pfbuym'], [class*='horario'], [class*='showtime'], "
        "[class*='schedule'], section:has([class*='Mui']), .movie-detail"
    )

    # Buscar horarios en elementos interactivos o contenedores
    horas_detectadas: list[str] = []

    # Extraer horas en botones o elementos interactivos
    for el in soup.find_all(["button", "a", "span", "div"]):
        txt = el.get_text(strip=True)
        if re.fullmatch(r"\d{1,2}:\d{2}(?:\s*hs)?", txt, re.IGNORECASE):
            horas_detectadas.append(txt)

    # Si no se hallaron en texto exacto, buscar en los contenedores de funciones
    if not horas_detectadas:
        for cont in schedule_containers:
            matches = HORARIO_PATTERN.findall(cont.get_text())
            if matches:
                horas_detectadas.extend(matches)

    horas_unicas = list(dict.fromkeys(horas_detectadas))
    if horas_unicas:
        return True, f"✅ Funciones disponibles detectadas ({len(horas_unicas)} horarios: {', '.join(horas_unicas[:5])})"

    # 3. Verificación de indicadores negativos
    body_text = soup.get_text(separator=" ", strip=True).lower()
    negative_keywords = [
        "próximamente", "proximamente", "coming soon",
        "no hay funciones", "sin funciones disponibles",
    ]
    for kw in negative_keywords:
        if kw in body_text:
            return False, f"Página indica película en '{kw}' — sin funciones activas."

    return False, "No se detectaron horarios ni funciones en el HTML de Cinemark."


# ─────────────────────────────────────────────────────────────────────────────
# Mapa de scrapers por nombre de cine
# ─────────────────────────────────────────────────────────────────────────────

SCRAPER_MAP = {
    "Cineplanet Chile": check_cineplanet,
    "Cinépolis Chile": check_cinepolis,
}

