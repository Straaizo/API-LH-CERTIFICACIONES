from datetime import datetime
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("America/Santiago")


def ahora() -> datetime:
    """Fecha y hora de Chile, sin zona (así se guarda en la base y se muestra igual en la app)."""
    return datetime.now(ZONA).replace(tzinfo=None)
