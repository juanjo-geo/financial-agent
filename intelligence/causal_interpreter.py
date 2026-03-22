"""
Genera interpretacion narrativa de las senales del agente financiero.
Usa lenguaje prudente: "sugiere", "parece indicar", "podria estar reflejando".

Inputs:
  - data/signals/signals_engine_output.json

Output:
  - data/signals/daily_signals.json  (resultado final completo)

Campos generados:
  driver_principal  : indicador de mayor movimiento del dia y su implicacion
  driver_secundario : segundo factor de mayor peso
  lectura_cruzada   : sintesis de la interaccion entre senales
  cierre_ejecutivo  : resumen ejecutivo de 2-3 oraciones
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from intelligence.signals_engine import append_signals_history

ROOT          = Path(__file__).parent.parent
ENGINE_FILE   = ROOT / "data/signals/signals_engine_output.json"
DAILY_SIGNALS = ROOT / "data/signals/daily_signals.json"


# ── Plantillas de lenguaje prudente por indicador ────────────────────────────

_DRIVER_TEMPLATES: dict[str, dict[str, str]] = {
    "brent": {
        "up_strong":   "El petroleo Brent registro un avance pronunciado ({pct:+.1f}%), lo que parece indicar tensiones en la oferta energetica global o senales de mayor demanda.",
        "up_mild":     "El Brent subio moderadamente ({pct:+.1f}%), sugiriendo cierta presion al alza en precios energeticos.",
        "down_strong": "El petroleo Brent cedio con fuerza ({pct:+.1f}%), lo que podria estar reflejando menor demanda o aumento de oferta.",
        "down_mild":   "El Brent retrocedio levemente ({pct:+.1f}%), con impacto limitado sobre la dinamica inflacionaria.",
        "flat":        "El petroleo Brent cerro practicamente sin cambios, sin senal energetica dominante en la sesion.",
    },
    "wti": {
        "up_strong":   "El WTI avanzo {pct:+.1f}%, en linea con presiones en el mercado de crudo liviano.",
        "up_mild":     "El WTI subio moderadamente ({pct:+.1f}%).",
        "down_strong": "El WTI cayo {pct:+.1f}%, senalando debilidad en el crudo liviano.",
        "down_mild":   "El WTI retrocedio levemente ({pct:+.1f}%).",
        "flat":        "El WTI sin cambios relevantes.",
    },
    "gold": {
        "up_strong":   "El oro avanzo {pct:+.1f}%, una senal que podria estar reflejando busqueda de refugio seguro ante mayor percepcion de riesgo.",
        "up_mild":     "El oro subio moderadamente ({pct:+.1f}%), con cierta demanda como activo de cobertura.",
        "down_strong": "El oro retrocedio {pct:+.1f}%, lo que sugiere menor demanda de refugio y posiblemente mayor apetito por riesgo.",
        "down_mild":   "El oro cedio levemente ({pct:+.1f}%), sin senal de refugio dominante.",
        "flat":        "El oro permanecio estable, sin senal de aversion al riesgo marcada.",
    },
    "silver": {
        "up_strong":   "La plata avanzo {pct:+.1f}%, siguiendo dinamicas de metales preciosos e industriales.",
        "up_mild":     "La plata subio moderadamente ({pct:+.1f}%).",
        "down_strong": "La plata cedio con fuerza ({pct:+.1f}%), lo que podria reflejar presion sobre metales industriales y preciosos.",
        "down_mild":   "La plata bajo levemente ({pct:+.1f}%).",
        "flat":        "La plata sin cambios relevantes.",
    },
    "btc": {
        "up_strong":   "Bitcoin registro un avance significativo ({pct:+.1f}%), lo que parece indicar mayor apetito de riesgo en activos especulativos.",
        "up_mild":     "Bitcoin subio moderadamente ({pct:+.1f}%), con senal positiva en el segmento cripto.",
        "down_strong": "Bitcoin cayo {pct:+.1f}%, una senal que podria estar reflejando aversion al riesgo o presion de ventas en activos especulativos.",
        "down_mild":   "Bitcoin retrocedio levemente ({pct:+.1f}%), sin senal de alarma clara en el segmento cripto.",
        "flat":        "Bitcoin sin cambios relevantes en la sesion.",
    },
    "dxy": {
        "up_strong":   "El indice dolar (DXY) mostro fortaleza pronunciada ({pct:+.1f}%), lo que sugiere busqueda de refugio en la moneda reserva y presion sobre activos de riesgo emergentes.",
        "up_mild":     "El DXY avanzo moderadamente ({pct:+.1f}%), con cierta apreciacion del dolar a nivel global.",
        "down_strong": "El DXY cayo {pct:+.1f}%, lo que podria estar reflejando menor demanda de refugio en el dolar y condiciones mas favorables para monedas emergentes.",
        "down_mild":   "El DXY retrocedio levemente ({pct:+.1f}%), con presion moderada sobre el dolar.",
        "flat":        "El DXY sin cambios relevantes; el dolar global mantuvo niveles estables.",
    },
    "usdcop": {
        "up_strong":   "El USD/COP avanzo {pct:+.1f}%, presionando el peso colombiano y encareciendo importaciones.",
        "up_mild":     "El USD/COP subio moderadamente ({pct:+.1f}%), con leve depreciacion del peso.",
        "down_strong": "El USD/COP retrocedio {pct:+.1f}%, fortaleciendo el peso colombiano en la sesion.",
        "down_mild":   "El USD/COP bajo levemente ({pct:+.1f}%), con cierto alivio para el peso.",
        "flat":        "El USD/COP sin variacion relevante; el peso colombiano mantuvo su cotizacion.",
    },
    "sp500": {
        "up_strong":   "El S&P 500 avanzo {pct:+.1f}%, senal de apetito de riesgo y confianza en el ciclo economico.",
        "up_mild":     "El S&P 500 subio moderadamente ({pct:+.1f}%).",
        "down_strong": "El S&P 500 retrocedio {pct:+.1f}%, lo que podria estar reflejando ajuste de expectativas corporativas o aversion al riesgo.",
        "down_mild":   "El S&P 500 cedio levemente ({pct:+.1f}%), con presion moderada sobre renta variable.",
        "flat":        "El S&P 500 sin cambios relevantes.",
    },
    "nasdaq": {
        "up_strong":   "El Nasdaq avanzo {pct:+.1f}%, liderado posiblemente por tecnologia y activos de crecimiento.",
        "up_mild":     "El Nasdaq subio moderadamente ({pct:+.1f}%).",
        "down_strong": "El Nasdaq cayo {pct:+.1f}%, con presion especial sobre el segmento tecnologico.",
        "down_mild":   "El Nasdaq cedio levemente ({pct:+.1f}%).",
        "flat":        "El Nasdaq sin cambios relevantes.",
    },
    "eurusd": {
        "up_strong":   "El EUR/USD subio {pct:+.1f}%, reflejando debilitamiento del dolar frente al euro.",
        "up_mild":     "El EUR/USD avanzo levemente ({pct:+.1f}%).",
        "down_strong": "El EUR/USD cayo {pct:+.1f}%, con fortaleza del dolar frente al euro.",
        "down_mild":   "El EUR/USD retrocedio levemente ({pct:+.1f}%).",
        "flat":        "El EUR/USD sin variacion relevante.",
    },
    "default": {
        "up_strong":   "{indicator} registro un avance de {pct:+.1f}% en la sesion.",
        "up_mild":     "{indicator} subio moderadamente ({pct:+.1f}%).",
        "down_strong": "{indicator} retrocedio {pct:+.1f}% en la sesion.",
        "down_mild":   "{indicator} bajo levemente ({pct:+.1f}%).",
        "flat":        "{indicator} sin cambios relevantes.",
    },
}


def _direction_key(pct: float) -> str:
    if pct >= 2.5:    return "up_strong"
    elif pct >= 0.5:  return "up_mild"
    elif pct <= -2.5: return "down_strong"
    elif pct <= -0.5: return "down_mild"
    else:             return "flat"


def _driver_text(indicator: str, pct: float) -> str:
    templates = _DRIVER_TEMPLATES.get(indicator, _DRIVER_TEMPLATES["default"])
    key = _direction_key(pct)
    tpl = templates.get(key, "{indicator}: {pct:+.1f}%")
    return tpl.format(indicator=indicator.upper(), pct=pct)


# ── Lectura cruzada ───────────────────────────────────────────────────────────

def _lectura_cruzada(senales: dict, changes: dict[str, float]) -> str:
    """Sintesis narrativa de la interaccion entre senales."""
    sesgo     = senales.get("sesgo_mercado", "Mixto")
    riesgo    = senales.get("riesgo_macro", "Medio")
    inflacion = senales.get("presion_inflacionaria", "Neutral")
    cop       = senales.get("presion_cop", "Neutral")

    brent = changes.get("brent", 0.0)
    gold  = changes.get("gold",  0.0)
    btc   = changes.get("btc",   0.0)
    sp500 = changes.get("sp500", 0.0)
    dxy   = changes.get("dxy",   0.0)

    parts: list[str] = []

    # Introduccion segun sesgo
    if sesgo == "Risk-off":
        parts.append(
            "El entorno de la sesion parece inclinarse hacia aversion al riesgo, "
            "con senales de cautela en activos de mayor volatilidad."
        )
    elif sesgo == "Risk-on":
        parts.append(
            "La sesion sugiere apetito por activos de riesgo, "
            "con dinamicas positivas en los principales indicadores de confianza."
        )
    else:
        parts.append(
            "Las senales del dia presentan un cuadro mixto, "
            "sin un sesgo de riesgo claramente dominante."
        )

    # Tension petroleo vs renta variable
    if brent > 1.5 and sp500 < -0.5:
        parts.append(
            "La combinacion de petroleo al alza y renta variable bajo presion "
            "podria estar reflejando preocupacion por el impacto del costo energetico "
            "sobre los margenes corporativos."
        )
    elif brent < -1.5 and sp500 > 0.5:
        parts.append(
            "La caida del petroleo junto con el avance de las acciones "
            "sugiere alivio en costos de produccion que el mercado parece estar descontando positivamente."
        )

    # Oro vs BTC (narrativa de refugio)
    if gold > 0.5 and btc < -0.5:
        parts.append(
            "La preferencia por oro sobre Bitcoin podria estar indicando "
            "busqueda de refugio en activos mas tradicionales "
            "frente a mayor percepcion de incertidumbre."
        )
    elif gold < -0.5 and btc > 0.5:
        parts.append(
            "El repliegue del oro junto al avance de Bitcoin "
            "podria reflejar rotacion hacia activos especulativos "
            "en un ambiente de menor aversion al riesgo."
        )
    elif gold < -1.0 and sp500 < -1.0:
        parts.append(
            "La caida simultanea de oro y renta variable es inusual: "
            "podria estar reflejando presion de liquidez o ajuste tecnico "
            "mas que una tendencia fundamental sostenida."
        )

    # DXY y COP
    if dxy > 0.3 and cop == "Alcista USD/COP":
        parts.append(
            "La fortaleza del dolar a nivel global parece trasladarse al tipo de cambio colombiano, "
            "lo que podria presionar la inflacion importada en Colombia."
        )
    elif dxy < -0.3 and cop == "Favorable COP":
        parts.append(
            "El debilitamiento del dolar global parece traducirse en alivio "
            "para el peso colombiano, mejorando el panorama cambiario de corto plazo."
        )

    # Escenario estanflacionario
    if inflacion == "Alcista" and riesgo == "Alto":
        parts.append(
            "La confluencia de presion inflacionaria y riesgo macro elevado "
            "sugiere un entorno de estanflacion potencial que podria complicar "
            "las decisiones de politica monetaria."
        )

    return " ".join(parts)


# ── Cierre ejecutivo ──────────────────────────────────────────────────────────

def _cierre_ejecutivo(senales: dict, changes: dict[str, float]) -> str:
    """Resumen ejecutivo de 2-3 oraciones con lenguaje prudente."""
    riesgo    = senales.get("riesgo_macro", "Medio")
    inflacion = senales.get("presion_inflacionaria", "Neutral")
    cop       = senales.get("presion_cop", "Neutral")
    conv      = senales.get("conviccion", 5)

    # Primera oracion: resumen del nivel de riesgo
    if riesgo == "Alto":
        primera = (
            "La sesion registra un entorno de riesgo macro elevado, "
            "con senales que sugieren cautela en la exposicion a activos de mayor riesgo."
        )
    elif riesgo == "Bajo":
        primera = (
            "El entorno macro parece moderadamente estable en esta sesion, "
            "sin senales que apunten a una disrupcion significativa en los mercados."
        )
    else:
        primera = (
            "El entorno macro se presenta con un nivel de riesgo moderado, "
            "con senales mixtas que aconsejan seguimiento cercano."
        )

    # Segunda oracion: inflacion y COP
    if inflacion == "Alcista" and cop == "Alcista USD/COP":
        segunda = (
            "La presion inflacionaria al alza, combinada con depreciacion del peso, "
            "podria estar deteriorando el panorama de poder adquisitivo en Colombia."
        )
    elif inflacion == "Bajista" and cop == "Favorable COP":
        segunda = (
            "La desinflacion energetica y la relativa fortaleza del peso "
            "configuran un escenario moderadamente favorable para la economia colombiana."
        )
    elif inflacion == "Alcista":
        segunda = (
            "La presion inflacionaria sugiere que los bancos centrales "
            "podrian mantener una postura restrictiva por mas tiempo del esperado."
        )
    elif cop == "Alcista USD/COP":
        segunda = (
            "La apreciacion del dolar frente al peso "
            "podria generar presion adicional sobre importaciones y deuda externa colombiana."
        )
    elif inflacion == "Bajista":
        segunda = (
            "La desinflacion energetica ofrece cierto alivio para la politica monetaria, "
            "aunque no garantiza un ciclo de recortes inmediato."
        )
    else:
        segunda = (
            "Sin senales inflacionarias ni cambiarias dominantes, "
            "el escenario para Colombia se mantiene en un rango de incertidumbre manejable."
        )

    # Tercera oracion: conviccion
    if conv >= 7:
        tercera = (
            f"Las senales presentan una conviccion {conv}/10, "
            "por lo que la narrativa descrita parece robusta con la informacion disponible hoy."
        )
    elif conv >= 4:
        tercera = (
            f"La conviccion de las senales es moderada ({conv}/10); "
            "se recomienda confirmar en la proxima sesion antes de tomar decisiones "
            "basadas exclusivamente en este analisis."
        )
    else:
        tercera = (
            f"La conviccion es baja ({conv}/10), lo que indica que las senales son inconclusas "
            "y requieren confirmacion adicional antes de actuar sobre ellas."
        )

    return f"{primera} {segunda} {tercera}"


# ── Main ──────────────────────────────────────────────────────────────────────

def run_causal_interpreter() -> dict:
    if not ENGINE_FILE.exists():
        raise FileNotFoundError(
            f"No existe {ENGINE_FILE}. Ejecuta intelligence.signals_engine primero."
        )
    with open(ENGINE_FILE, encoding="utf-8") as f:
        engine_data = json.load(f)

    senales = engine_data.get("senales", {})
    changes = engine_data.get("variaciones_mercado", {})
    nw      = engine_data.get("pesos_noticias", {})

    # Determinar drivers por magnitud absoluta de variacion
    sorted_changes = sorted(changes.items(), key=lambda x: abs(x[1]), reverse=True)

    driver1_key = sorted_changes[0][0] if len(sorted_changes) > 0 else "brent"
    driver1_pct = sorted_changes[0][1] if len(sorted_changes) > 0 else 0.0
    driver2_key = sorted_changes[1][0] if len(sorted_changes) > 1 else "dxy"
    driver2_pct = sorted_changes[1][1] if len(sorted_changes) > 1 else 0.0

    driver_principal  = _driver_text(driver1_key, driver1_pct)
    driver_secundario = _driver_text(driver2_key, driver2_pct)
    lectura_cruzada   = _lectura_cruzada(senales, changes)
    cierre_ejecutivo  = _cierre_ejecutivo(senales, changes)

    result = {
        "fecha":       datetime.now().strftime("%Y-%m-%d"),
        "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "senales": senales,
        "interpretacion": {
            "driver_principal":  driver_principal,
            "driver_secundario": driver_secundario,
            "lectura_cruzada":   lectura_cruzada,
            "cierre_ejecutivo":  cierre_ejecutivo,
        },
        "scores_internos":     engine_data.get("scores_internos", {}),
        "factores":            engine_data.get("factores", {}),
        "pesos_noticias":      nw,
        "variaciones_mercado": changes,
    }
    return result


def main():
    print("Generando interpretacion causal...")
    result = run_causal_interpreter()

    DAILY_SIGNALS.parent.mkdir(parents=True, exist_ok=True)
    with open(DAILY_SIGNALS, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    interp = result["interpretacion"]
    print(f"\n  Driver principal  : {interp['driver_principal']}")
    print(f"  Driver secundario : {interp['driver_secundario']}")
    print(f"\n  Lectura cruzada:")
    print(f"    {interp['lectura_cruzada']}")
    print(f"\n  Cierre ejecutivo:")
    print(f"    {interp['cierre_ejecutivo']}")
    print(f"\n  Guardado en: {DAILY_SIGNALS}")

    # Actualiza historial con drivers completos
    append_signals_history(
        result["senales"],
        driver_principal=interp["driver_principal"],
        driver_secundario=interp["driver_secundario"],
    )


if __name__ == "__main__":
    main()
