"""
Rankeador de activos por conviccion y alineacion con el regimen actual.

Para cada indicador activo calcula:
  rank_score     : |total_score| * (confianza_calibrada/10) * multiplicador_regimen
  alineacion     : si la prediccion coincide con lo esperado en el regimen actual
  outlook        : etiqueta de oportunidad/precaucion
  momentum_label : Fuerte / Moderado / Debil segun magnitud

Ordena de mayor a menor rank_score. Los activos Laterales de baja
conviccion quedan al final.

Salida: data/signals/asset_ranking.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT             = Path(__file__).parent.parent
PREDICTIONS_FILE = ROOT / "data/signals/predictions_24h.json"
REGIME_V2_FILE   = ROOT / "data/signals/market_regime_v2.json"
CONFIG_FILE      = ROOT / "config.json"
OUTPUT_FILE      = ROOT / "data/signals/asset_ranking.json"

# ── Alineacion por regimen ────────────────────────────────────────────────────
# (indicador, direccion_predicha) -> "Alineado" | "Contrario" | "Neutral"
_ALIGNMENT: dict[str, dict[tuple[str, str], str]] = {
    "INFLACIONARIO": {
        ("brent",  "Alcista"): "Alineado",
        ("brent",  "Bajista"): "Contrario",
        ("gold",   "Alcista"): "Alineado",
        ("gold",   "Bajista"): "Contrario",
        ("dxy",    "Alcista"): "Alineado",
        ("dxy",    "Bajista"): "Contrario",
        ("usdcop", "Alcista"): "Alineado",
        ("usdcop", "Bajista"): "Contrario",
        ("btc",    "Bajista"): "Neutral",
        ("btc",    "Alcista"): "Neutral",
        ("sp500",  "Bajista"): "Alineado",
    },
    "RISK-ON": {
        ("btc",    "Alcista"): "Alineado",
        ("btc",    "Bajista"): "Contrario",
        ("sp500",  "Alcista"): "Alineado",
        ("sp500",  "Bajista"): "Contrario",
        ("dxy",    "Bajista"): "Alineado",
        ("dxy",    "Alcista"): "Contrario",
        ("brent",  "Alcista"): "Alineado",
        ("gold",   "Bajista"): "Alineado",
        ("gold",   "Alcista"): "Contrario",
        ("usdcop", "Bajista"): "Alineado",
    },
    "CRISIS": {
        ("gold",   "Alcista"): "Alineado",
        ("gold",   "Bajista"): "Contrario",
        ("dxy",    "Alcista"): "Alineado",
        ("dxy",    "Bajista"): "Contrario",
        ("btc",    "Bajista"): "Alineado",
        ("btc",    "Alcista"): "Contrario",
        ("sp500",  "Bajista"): "Alineado",
        ("brent",  "Bajista"): "Alineado",
        ("usdcop", "Alcista"): "Alineado",
    },
    "LATERAL": {},   # sin alineacion esperada en mercado lateral
}

_ALIGN_MULTIPLIER = {"Alineado": 1.25, "Neutral": 1.0, "Contrario": 0.75}

_CATALOG_LABELS = {
    "brent":  "Brent (Petroleo)",
    "btc":    "Bitcoin",
    "dxy":    "DXY (Dolar)",
    "usdcop": "USD/COP",
    "gold":   "Oro",
    "silver": "Plata",
    "sp500":  "S&P 500",
    "nasdaq": "Nasdaq",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _active_indicators() -> list[str]:
    cfg = _load(CONFIG_FILE)
    return cfg.get("active_indicators", ["brent", "btc", "dxy", "usdcop", "gold"])


def _momentum_label(momentum_pct: float) -> str:
    abs_m = abs(momentum_pct)
    if abs_m >= 2.0:
        return "Fuerte"
    if abs_m >= 0.5:
        return "Moderado"
    return "Debil"


def _outlook(direction: str, alineacion: str, rank_score: float) -> str:
    if direction == "Lateral":
        return "Sin tendencia"
    if direction == "Alcista":
        if alineacion == "Alineado":
            return "Oportunidad alcista"
        if alineacion == "Contrario":
            return "Alcista dudoso"
        return "Alcista moderado"
    # Bajista
    if alineacion == "Alineado":
        return "Precaucion bajista"
    if alineacion == "Contrario":
        return "Bajista dudoso"
    return "Bajista moderado"


# ── Motor principal ───────────────────────────────────────────────────────────

def run_asset_ranker() -> dict:
    preds  = _load(PREDICTIONS_FILE)
    rv2    = _load(REGIME_V2_FILE)
    active = _active_indicators()

    regime       = rv2.get("regime", "LATERAL")
    align_rules  = _ALIGNMENT.get(regime, {})
    predicciones = preds.get("predicciones", {})

    assets: list[dict] = []

    for ind in active:
        p = predicciones.get(ind)
        if not p:
            continue

        direction   = p.get("direccion_24h", "Lateral")
        magnitude   = p.get("magnitud_esperada", "Leve")
        confianza   = int(p.get("confianza", 5))
        conf_cal    = int(p.get("confianza_calibrada", confianza))
        total_score = float(p.get("_total_score", 0.0))
        momentum    = float(p.get("_momentum_pct", 0.0))
        slope       = float(p.get("_slope_pct_dia", 0.0))
        razon       = p.get("razon", "")

        alineacion  = align_rules.get((ind, direction), "Neutral")
        multiplier  = _ALIGN_MULTIPLIER[alineacion]

        # rank_score: fuerza de la senal ajustada por confianza calibrada y alineacion
        rank_score = abs(total_score) * (conf_cal / 10.0) * multiplier

        # Lateral de baja conviccion → penalizacion extra
        if direction == "Lateral" and conf_cal <= 4:
            rank_score *= 0.5

        outlook_lbl = _outlook(direction, alineacion, rank_score)
        mom_lbl     = _momentum_label(momentum)

        assets.append({
            "indicador":   ind,
            "label":       _CATALOG_LABELS.get(ind, ind.upper()),
            "direccion":   direction,
            "magnitud":    magnitude,
            "confianza":   confianza,
            "confianza_calibrada": conf_cal,
            "total_score": round(total_score, 3),
            "rank_score":  round(rank_score, 3),
            "alineacion":  alineacion,
            "outlook":     outlook_lbl,
            "momentum_pct": round(momentum, 3),
            "momentum_label": mom_lbl,
            "slope_pct_dia": round(slope, 3),
            "razon":       razon,
        })

    # Ordenar: activos con direccion clara primero, luego por rank_score desc
    assets.sort(key=lambda x: (
        0 if x["direccion"] != "Lateral" else 1,
        -x["rank_score"]
    ))

    for i, a in enumerate(assets, 1):
        a["rank"] = i

    # Insights de alto nivel
    alcistas  = [a for a in assets if a["direccion"] == "Alcista"]
    bajistas  = [a for a in assets if a["direccion"] == "Bajista"]
    alineados = [a for a in assets if a["alineacion"] == "Alineado"]
    contrarios= [a for a in assets if a["alineacion"] == "Contrario"]

    top     = assets[0] if assets else None
    bottom  = assets[-1] if assets else None

    return {
        "fecha":        datetime.now().strftime("%Y-%m-%d"),
        "generado_en":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "regime":       regime,
        "n_alcistas":   len(alcistas),
        "n_bajistas":   len(bajistas),
        "n_laterales":  len(assets) - len(alcistas) - len(bajistas),
        "n_alineados":  len(alineados),
        "n_contrarios": len(contrarios),
        "top_asset":    top["indicador"]   if top    else None,
        "bottom_asset": bottom["indicador"] if bottom else None,
        "assets":       assets,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Rankeando activos por conviccion y alineacion de regimen...")
    result = run_asset_ranker()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    regime = result["regime"]
    print(f"  Regimen actual : {regime}")
    print(f"  Alcistas:{result['n_alcistas']}  "
          f"Bajistas:{result['n_bajistas']}  "
          f"Laterales:{result['n_laterales']}  "
          f"Alineados:{result['n_alineados']}  "
          f"Contrarios:{result['n_contrarios']}")
    print()
    print(f"  {'#':<3} {'Activo':<20} {'Dir':^9} {'Conf':>5} {'Cal':>5} "
          f"{'Score':>7} {'Alin.':<11} Outlook")
    print("  " + "-" * 80)
    for a in result["assets"]:
        arrow = {"Alcista": "^", "Bajista": "v", "Lateral": "-"}.get(a["direccion"], "?")
        print(
            f"  {a['rank']:<3} {a['label']:<20} {arrow} {a['direccion']:<7} "
            f"{a['confianza']:>5} {a['confianza_calibrada']:>5} "
            f"{a['rank_score']:>7.3f} {a['alineacion']:<11} {a['outlook']}"
        )
    print(f"\n  Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
