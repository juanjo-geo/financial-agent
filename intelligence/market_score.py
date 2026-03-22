"""
Score de inteligencia de mercado (0-100).

Combina multiples fuentes para resumir la claridad, coherencia y
conviccion de las senales del sistema en un numero unico.

Componentes (suma = 100 pts):
  Claridad del regimen    25 pts  : confianza del clasificador v2
  Conviccion de senales   20 pts  : conviccion de daily_signals.json
  Coherencia predictiva   25 pts  : confianza calibrada media (no-Lateral)
  Senales compuestas      15 pts  : n_activas de composite_signals.json
  Estabilidad macro       15 pts  : 15 - (regime_change_score / 100 * 15)

Niveles:
  86-100 : Confluencia maxima
  71-85  : Alta conviccion
  51-70  : Senales claras
  31-50  : Visibilidad moderada
  0-30   : Senales mixtas

Salida: data/signals/market_score.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT              = Path(__file__).parent.parent
REGIME_V2_FILE    = ROOT / "data/signals/market_regime_v2.json"
SIGNALS_FILE      = ROOT / "data/signals/daily_signals.json"
PREDICTIONS_FILE  = ROOT / "data/signals/predictions_24h.json"
COMPOSITE_FILE    = ROOT / "data/signals/composite_signals.json"
REGIME_CHG_FILE   = ROOT / "data/signals/regime_change.json"
OUTPUT_FILE       = ROOT / "data/signals/market_score.json"

_LEVELS = [
    (86, "Confluencia maxima",   "#00875A"),
    (71, "Alta conviccion",      "#00C896"),
    (51, "Senales claras",       "#2563EB"),
    (31, "Visibilidad moderada", "#E65100"),
    (0,  "Senales mixtas",       "#8A9BB0"),
]


def _level(score: int) -> tuple[str, str]:
    for threshold, label, color in _LEVELS:
        if score >= threshold:
            return label, color
    return "Senales mixtas", "#8A9BB0"


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── Componentes ───────────────────────────────────────────────────────────────

def _comp_regime_clarity(rv2: dict) -> tuple[float, str]:
    """25 pts proporcionales a la confianza del clasificador de regimen."""
    confianza = float(rv2.get("confianza", 0))
    # confianza va de 0 a ~100 (diferencia entre 1er y 2do score)
    pts = min(25.0, confianza / 100.0 * 25.0)
    return round(pts, 1), f"Regimen {rv2.get('regime','?')} (confianza +{int(confianza)}pts)"


def _comp_signal_conviction(signals: dict) -> tuple[float, str]:
    """20 pts proporcionales a la conviccion de daily_signals (1-10)."""
    conv = float(signals.get("senales", {}).get("conviccion", 5))
    pts  = (conv / 10.0) * 20.0
    return round(pts, 1), f"Conviccion {conv:.0f}/10"


def _comp_predictive_coherence(preds: dict) -> tuple[float, str]:
    """
    25 pts basados en la confianza calibrada media de predicciones
    con direccion no-Lateral.
    """
    predicciones = preds.get("predicciones", {})
    if not predicciones:
        return 0.0, "Sin predicciones"

    confidences = []
    for p in predicciones.values():
        if p.get("direccion_24h") != "Lateral":
            cal = p.get("confianza_calibrada", p.get("confianza", 5))
            confidences.append(float(cal))

    if not confidences:
        return 5.0, "Solo predicciones laterales"

    avg_conf = sum(confidences) / len(confidences)
    pts      = (avg_conf / 10.0) * 25.0
    return round(pts, 1), f"Conf. calibrada media {avg_conf:.1f}/10 ({len(confidences)} activos)"


def _comp_composite_signals(composite: dict) -> tuple[float, str]:
    """15 pts: 5 pts por cada senal compuesta activa (max 3 senales = 15 pts)."""
    n   = int(composite.get("n_activas", 0))
    pts = min(15.0, n * 5.0)
    return pts, f"{n} senal(es) compuesta(s) activa(s)"


def _comp_macro_stability(rc: dict) -> tuple[float, str]:
    """
    15 pts: maximos cuando el mercado es estable (rc_score bajo),
    0 cuando hay cambio de regimen critico (rc_score >= 100).
    """
    rc_score = float(rc.get("score", 0))
    pts      = max(0.0, 15.0 - (rc_score / 100.0) * 15.0)
    nivel    = rc.get("nivel", "Estable")
    return round(pts, 1), f"Regime change {rc_score:.0f}/100 ({nivel})"


# ── Motor principal ───────────────────────────────────────────────────────────

def run_market_score() -> dict:
    rv2      = _load(REGIME_V2_FILE)
    signals  = _load(SIGNALS_FILE)
    preds    = _load(PREDICTIONS_FILE)
    composite= _load(COMPOSITE_FILE)
    rc       = _load(REGIME_CHG_FILE)

    comp_regime,    desc_regime    = _comp_regime_clarity(rv2)
    comp_signals,   desc_signals   = _comp_signal_conviction(signals)
    comp_predict,   desc_predict   = _comp_predictive_coherence(preds)
    comp_composite, desc_composite = _comp_composite_signals(composite)
    comp_stability, desc_stability = _comp_macro_stability(rc)

    total = round(comp_regime + comp_signals + comp_predict + comp_composite + comp_stability)
    total = max(0, min(100, total))

    label, color = _level(total)

    # Narrativa
    regime   = rv2.get("regime", "LATERAL")
    sesgo    = signals.get("senales", {}).get("sesgo_mercado", "Mixto")
    riesgo   = signals.get("senales", {}).get("riesgo_macro", "Medio")

    if total >= 71:
        narrative = (
            f"El sistema cuenta hoy con alta conviccion: regimen {regime}, "
            f"sesgo {sesgo}, riesgo macro {riesgo}. "
            f"Las senales apuntan en direccion coherente."
        )
    elif total >= 51:
        narrative = (
            f"Las senales son legibles: regimen {regime} con sesgo {sesgo}. "
            f"Existen algunas contradicciones entre componentes que moderan la conviccion."
        )
    elif total >= 31:
        narrative = (
            f"Visibilidad parcial. Regimen {regime} pero con senales mixtas "
            f"(sesgo {sesgo}, riesgo {riesgo}). Se recomienda cautela."
        )
    else:
        narrative = (
            f"Senales mixtas o insuficientes. El mercado no muestra "
            f"una direccion consensuada hoy."
        )

    return {
        "fecha":       datetime.now().strftime("%Y-%m-%d"),
        "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "score":       total,
        "label":       label,
        "color":       color,
        "narrative":   narrative,
        "componentes": {
            "claridad_regimen":   {"pts": comp_regime,    "desc": desc_regime,    "max": 25},
            "conviccion_senales": {"pts": comp_signals,   "desc": desc_signals,   "max": 20},
            "coherencia_pred":    {"pts": comp_predict,   "desc": desc_predict,   "max": 25},
            "senales_compuestas": {"pts": comp_composite, "desc": desc_composite, "max": 15},
            "estabilidad_macro":  {"pts": comp_stability, "desc": desc_stability, "max": 15},
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Calculando market score...")
    result = run_market_score()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    score = result["score"]
    label = result["label"]
    bar   = "#" * (score // 5) + "." * (20 - score // 5)
    print(f"  Score   : {score}/100  [{label}]")
    print(f"  [{bar}]")
    print(f"  Narrative: {result['narrative'][:80]}...")
    print()
    print(f"  {'Componente':<24} {'Pts':>5} / {'Max':>4}")
    print("  " + "-" * 36)
    for k, v in result["componentes"].items():
        print(f"  {k:<24} {v['pts']:>5.1f} / {v['max']:>4}  {v['desc']}")
    print(f"\n  Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
