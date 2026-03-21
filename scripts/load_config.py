"""Carga config.json con valores por defecto si el archivo no existe."""
import json
import os
from pathlib import Path

ROOT        = Path(__file__).parent.parent
CONFIG_FILE = ROOT / "config.json"

DEFAULTS = {
    "send_hour_utc":       12,
    "email_enabled":       True,
    "email_to":            "",
    "whatsapp_enabled":    True,
    "whatsapp_to":         "",
    "alerts_enabled":      True,
    "alert_threshold":     4.0,
    "active_indicators":   ["brent", "btc", "dxy", "usdcop", "gold"],
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULTS, **data}
    return DEFAULTS.copy()


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
