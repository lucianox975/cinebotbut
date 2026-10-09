"""
state.py — Gestión de estado persistente (JSON) para control anti-spam

El estado se guarda en disco para sobrevivir reinicios del contenedor.
Estructura del JSON:
{
  "Cineplanet Chile": {
    "available": false,
    "last_check": "2025-01-01T00:00:00",
    "last_notified": null,
    "consecutive_errors": 0
  },
  ...
}
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class StateManager:
    """Gestiona el estado de disponibilidad de cada cine en disco."""

    def __init__(self, state_file: Path) -> None:
        self._file = state_file
        self._state: dict[str, dict] = {}
        self._load()

    # ── I/O ───────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Carga el estado desde disco si existe."""
        if self._file.exists():
            try:
                with self._file.open("r", encoding="utf-8") as f:
                    self._state = json.load(f)
                logger.info("Estado cargado desde '%s'.", self._file)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("No se pudo cargar el estado: %s. Iniciando vacío.", exc)
                self._state = {}
        else:
            logger.info("Archivo de estado no encontrado. Iniciando vacío.")

    def _save(self) -> None:
        """Persiste el estado actual en disco."""
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            with self._file.open("w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False, default=str)
        except OSError as exc:
            logger.error("Error al guardar el estado: %s", exc)

    # ── Acceso al estado ──────────────────────────────────────────────────

    def _get_cinema(self, cinema_name: str) -> dict:
        """Retorna (o inicializa) el registro de un cine."""
        if cinema_name not in self._state:
            self._state[cinema_name] = {
                "available": None,       # None = desconocido (primer ciclo)
                "last_check": None,
                "last_notified": None,
                "consecutive_errors": 0,
            }
        return self._state[cinema_name]

    def get_available(self, cinema_name: str) -> bool | None:
        """
        Retorna el último estado conocido de disponibilidad.
        None si es la primera vez que se consulta.
        """
        return self._get_cinema(cinema_name).get("available")

    def should_notify(self, cinema_name: str, new_available: bool) -> bool:
        """
        Determina si se debe enviar una notificación.

        Reglas:
        - Siempre notificar si es el primer ciclo (last_notified is None).
        - Notificar si el estado cambia de False → True (¡disponible!).
        - No notificar si el estado no cambió (anti-spam).
        """
        record = self._get_cinema(cinema_name)
        prev = record.get("available")
        last_notified = record.get("last_notified")

        # Primer ciclo: solo notificar si ya está disponible al iniciar
        if last_notified is None:
            return new_available

        # Notificar solo en transición a disponible
        return (prev is False or prev is None) and new_available

    def update(
        self,
        cinema_name: str,
        available: bool,
        notified: bool = False,
    ) -> None:
        """Actualiza el estado de un cine y persiste en disco."""
        record = self._get_cinema(cinema_name)
        record["available"] = available
        record["last_check"] = datetime.now().isoformat()
        record["consecutive_errors"] = 0
        if notified:
            record["last_notified"] = datetime.now().isoformat()
        self._save()

    def record_error(self, cinema_name: str) -> int:
        """Incrementa el contador de errores consecutivos. Retorna el total."""
        record = self._get_cinema(cinema_name)
        record["consecutive_errors"] = record.get("consecutive_errors", 0) + 1
        record["last_check"] = datetime.now().isoformat()
        self._save()
        return record["consecutive_errors"]

    def get_error_count(self, cinema_name: str) -> int:
        return self._get_cinema(cinema_name).get("consecutive_errors", 0)

    def summary(self) -> dict:
        """Retorna una copia del estado completo."""
        return dict(self._state)
