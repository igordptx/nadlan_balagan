"""Load human-edited TOML files from inside the project root."""

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIR = ROOT / "searches"
DATA_DIR = ROOT / "data"
PERIOD_LABELS = {
    "last_3_months": "ב-3 החודשים האחרונים",
    "last_6_months": "ב-6 החודשים האחרונים",
    "last_12_months": "ב-12 החודשים האחרונים",
    "last_36_months": "ב-36 החודשים האחרונים",
}


@dataclass(frozen=True)
class SearchConfig:
    id: str
    title: str
    enabled: bool
    gush_from: int
    gush_to: int
    property_type: str
    transaction_type: str
    period: str


@dataclass(frozen=True)
class Settings:
    port: int = 9999
    delay_seconds: float = 3.0
    headless: bool = True
    max_captcha_attempts: int = 8
    max_pages: int = 100


def _integer(value: object, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")
    return value.strip()


def parse_search(data: dict) -> SearchConfig:
    search_id = _text(data.get("id"), "id")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", search_id):
        raise ValueError("id must use lowercase letters, digits, hyphens, or underscores")
    title = _text(data.get("title"), "title")
    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be true or false")
    location = data.get("location")
    filters = data.get("filters")
    if not isinstance(location, dict) or location.get("kind") != "gush_range":
        raise ValueError("location.kind must be 'gush_range'")
    if not isinstance(filters, dict):
        raise ValueError("[filters] is required")
    gush_from = _integer(location.get("from"), "location.from", 1, 999999)
    gush_to = _integer(location.get("to"), "location.to", 1, 999999)
    if gush_to < gush_from:
        raise ValueError("location.to must be at least location.from")
    period = _text(filters.get("period"), "filters.period")
    if period not in PERIOD_LABELS:
        raise ValueError(f"filters.period must be one of: {', '.join(PERIOD_LABELS)}")
    return SearchConfig(
        id=search_id,
        title=title,
        enabled=enabled,
        gush_from=gush_from,
        gush_to=gush_to,
        property_type=_text(filters.get("property_type"), "filters.property_type"),
        transaction_type=_text(filters.get("transaction_type"), "filters.transaction_type"),
        period=period,
    )


def load_searches(directory: Path = SEARCH_DIR) -> tuple[dict[str, SearchConfig], list[str]]:
    searches: dict[str, SearchConfig] = {}
    errors: list[str] = []
    for path in sorted(directory.glob("*.toml")):
        try:
            with path.open("rb") as file:
                search = parse_search(tomllib.load(file))
            if search.id in searches:
                raise ValueError(f"duplicate id {search.id!r}")
            searches[search.id] = search
        except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
    return searches, errors


def load_settings(path: Path = ROOT / "settings.toml") -> Settings:
    if not path.exists():
        return Settings()
    with path.open("rb") as file:
        data = tomllib.load(file)
    port = _integer(data.get("port", 9999), "port", 1, 65535)
    delay = data.get("delay_seconds", 3)
    if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not 0 <= delay <= 300:
        raise ValueError("delay_seconds must be a number from 0 to 300")
    headless = data.get("headless", True)
    if not isinstance(headless, bool):
        raise ValueError("headless must be true or false")
    return Settings(
        port=port,
        delay_seconds=float(delay),
        headless=headless,
        max_captcha_attempts=_integer(data.get("max_captcha_attempts", 8), "max_captcha_attempts", 1, 30),
        max_pages=_integer(data.get("max_pages", 100), "max_pages", 1, 1000),
    )
