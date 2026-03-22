"""
Generador de senales compuestas entre activos.

Evalua combinaciones de movimientos del dia para detectar patrones
que tienen significado macro especifico para Colombia y mercados emergentes.

Reglas implementadas:
  Brent +2% & DXY +0.5%  -> "Alerta macro fuerte"
  BTC   +2% & DXY -0.3%  -> "Risk-on fuerte"
  Oro   +1% & SP500 -0.5% -> "Aversion al riesgo"
  Brent +2% & USDCOP +0.5% -> "Presion importadora Colombia"
  3+ activos cayendo >1%  -> "Sesion de aversion generalizada"
  BTC  +3% & Oro +1%      -> "Apetito por activos alternativos"
  Brent -2% & Oro -1%     -> "Desinflacion de activos reales"
  DXY  +0.5% & Gold -0.5% -> "Fortaleza del dolar presiona metales"

Salida: data/signals/composite_signals.json
  activas    : lista de senales disparadas hoy
  fecha
  variaciones: cambios del dia por indicador
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT         = Path(__file__).parent.parent
HISTORY_FILE = ROOT / "data/historical/market_history.csv"
CONFIG_FILE  = ROOT / "config.json"
OUTPUT_FILE  = ROOT / "data/signals/composite_signals.json"

# Severidad: HIGH=rojo, MED=naranja, LOW=amarillo
_RULES: list[dict] = [
    {
        "id":          "macro_fuerte",
        "nombre":      "Alerta macro fuerte",
        "descripcion": "Petroleo y dolar suben juntos: señal de tension macro global.",
        "condiciones": [("brent", ">=", 2.0), ("dxy", ">=", 0.5)],
        "severidad":   "HIGH",
        "icono":       "!",
    },
    {
        "id":          "risk_on_fuerte",
        "nombre":      "Risk-on fuerte",
        "descripcion": "Cripto al alza y dolar debil: apetito por riesgo dominante.",
        "condiciones": [("btc", ">=", 2.0), ("dxy", "<=", -0.3)],
        "severidad":   "MED",
        "icono":       "+",
    },
    {
        "id":          "aversion_riesgo",
        "nombre":      "Aversion al riesgo",
        "descripcion": "Oro sube mientras las acciones caen: refugio ante incertidumbre.",
        "condiciones": [("gold", ">=", 1.0), ("sp500", "<=", -0.5)],
        "severidad":   "MED",
        "icono":       "~",
    },
    {
        "id":          "presion_colombia",
        "nombre":      "Presion importadora Colombia",
        "descripcion": "Petroleo y USDCOP suben: costo de importaciones en Colombia aumenta.",
        "condiciones": [("brent", ">=", 2.0), ("usdcop", ">=", 0.5)],
        "severidad":   "HIGH",
        "icono":       "!",
    },
    {
        "id":          "aversion_generalizada",
        "nombre":      "Sesion de aversion generalizada",
        "descripcion": "Multiples activos en rojo simultaneamente: posible desapalancamiento.",
        "condiciones": "custom_multi_down",
        "severidad":   "HIGH",
        "icono":       "!",
    },
    {
        "id":          "activos_alternativos",
        "nombre":      "Apetito por activos alternativos",
        "descripcion": "BTC y Oro suben juntos: busqueda de reservas de valor.",
        "condiciones": [("btc", ">=", 3.0), ("gold", ">=", 1.0)],
        "severidad":   "MED",
        "icono":       "+",
    },
    {
        "id":          "desinflacion_real",
        "nombre":      "Desinflacion de activos reales",
        "descripcion": "Petroleo y Oro bajan juntos: presiones deflacionarias en commodities.",
        "condiciones": [("brent", "<=", -2.0), ("gold", "<=", -1.0)],
        "severidad":   "MED",
        "icono":       "v",
    },
    {
        "id":          "dxy_presion_metales",
        "nombre":      "Fortaleza del dolar presiona metales",
        "descripcion": "DXY al alza y Oro a la baja: correlacion inversa activa.",
        "condiciones": [("dxy", ">=", 0.5), ("gold", "<=", -0.5)],
        "severidad":   "LOW",
        "icono":       "~",
    },
    {
        "id":          "cop_debilidad",
        "nombre":      "Debilidad del COP",
        "descripcion": "USDCOP sube junto al DXY: presion cambiaria desde contexto global.",
        "condiciones": [("usdcop", ">=", 0.8), ("dxy", ">=", 0.3)],
        "severidad":   "MED",
        "icono":       "!",
    },
]


# ── Loader ────────────────────────────────────────────────────────────────────

def _load_today_changes() -> dict[str, float]:
    """
    Carga el cambio_pct del ultimo dia disponible para cada indicador.
    Usa la fila mas reciente de market_history.csv.
    """
    if not HISTORY_FILE.exists():
        return {}
    try:
        df = pd.read_csv(HISTORY_FILE)
        df["timestamp"]  = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
        df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce")
        df = df.dropna(subset=["timestamp", "change_pct"])
        df["date_str"] = df["timestamp"].dt.strftime("%Y-%m-%d")

        last_date = df["date_str"].max()
        today_df  = df[df["date_str"] == last_date]

        return {
            str(row["indicator"]).lower(): float(row["change_pct"])
            for _, row in today_df.iterrows()
            if pd.notna(row["change_pct"])
        }
    except Exception:
        return {}


def _eval_condition(chg: dict[str, float], cond: tuple) -> bool:
    ind, op, val = cond
    pct = chg.get(ind)
    if pct is None:
        return False
    if op == ">=":
        return pct >= val
    if op == "<=":
        return pct <= val
    return False


def _multi_down(chg: dict[str, float], n: int = 3, threshold: float = -1.0) -> bool:
    """Retorna True si al menos n activos caen mas de threshold%."""
    falling = sum(1 for v in chg.values() if v <= threshold)
    return falling >= n


# ── Motor ─────────────────────────────────────────────────────────────────────

def run_composite_signals() -> dict:
    chg = _load_today_changes()

    activas: list[dict] = []
    for rule in _RULES:
        condiciones = rule["condiciones"]
        if condiciones == "custom_multi_down":
            fired = _multi_down(chg, n=3, threshold=-1.0)
        else:
            fired = all(_eval_condition(chg, c) for c in condiciones)

        if fired:
            activas.append({
                "id":          rule["id"],
                "nombre":      rule["nombre"],
                "descripcion": rule["descripcion"],
                "severidad":   rule["severidad"],
                "icono":       rule["icono"],
            })

    # Resumen de variaciones del dia
    variaciones = {k: round(v, 4) for k, v in chg.items()}

    return {
        "fecha":       datetime.now().strftime("%Y-%m-%d"),
        "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_activas":   len(activas),
        "activas":     activas,
        "variaciones": variaciones,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Generando senales compuestas entre activos...")
    result = run_composite_signals()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    n = result["n_activas"]
    print(f"  Senales activas hoy: {n}")
    if result["activas"]:
        for s in result["activas"]:
            print(f"  [{s['severidad']:<4}] {s['nombre']}")
            print(f"         {s['descripcion']}")
    else:
        print("  Ninguna senal compuesta disparada hoy.")

    print(f"\n  Variaciones del dia:")
    for ind, pct in sorted(result["variaciones"].items()):
        sign = "+" if pct >= 0 else ""
        print(f"    {ind:<14} {sign}{pct:.2f}%")

    print(f"\n  Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
