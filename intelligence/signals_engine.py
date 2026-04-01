"""
Genera 5 senales compuestas usando reglas deterministicas basadas en
variaciones de mercado (latest_snapshot.csv) + pesos tematicos de noticias
(news_weights.json, opcional).

Senales generadas:
  riesgo_macro         : Bajo / Medio / Alto
  sesgo_mercado        : Risk-on / Risk-off / Mixto
  presion_inflacionaria: Bajista / Neutral / Alcista
  presion_cop          : Favorable COP / Neutral / Alcista USD/COP
  conviccion           : 1-10

Salida: data/signals/signals_engine_output.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT                 = Path(__file__).parent.parent
SNAPSHOT_FILE        = ROOT / "data/processed/latest_snapshot.csv"
WEIGHTS_FILE         = ROOT / "data/signals/news_weights.json"
OUTPUT_FILE          = ROOT / "data/signals/signals_engine_output.json"
SIGNALS_HISTORY_FILE = ROOT / "data/signals/signals_history.csv"
ADAPTIVE_FILE        = ROOT / "data/signals/adaptive_weights.json"

HISTORY_COLS = [
    "fecha", "riesgo_macro", "sesgo_mercado", "presion_inflacionaria",
    "presion_cop", "conviccion", "driver_principal", "driver_secundario",
]


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_changes() -> dict[str, float]:
    """Retorna {indicator: change_pct} desde el snapshot."""
    if not SNAPSHOT_FILE.exists():
        return {}
    df = pd.read_csv(SNAPSHOT_FILE)
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        pct = pd.to_numeric(row.get("change_pct"), errors="coerce")
        if pd.notna(pct):
            out[str(row["indicator"]).lower()] = float(pct)
    return out


def _load_snapshot_full() -> dict[str, dict]:
    """Retorna {indicator: {value, change_pct, unit}}."""
    if not SNAPSHOT_FILE.exists():
        return {}
    df = pd.read_csv(SNAPSHOT_FILE)
    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        key = str(row["indicator"]).lower()
        out[key] = {
            "value":      pd.to_numeric(row.get("value"),      errors="coerce"),
            "change_pct": pd.to_numeric(row.get("change_pct"), errors="coerce"),
            "unit":       str(row.get("unit", "")),
        }
    return out


def _load_news_weights() -> dict[str, int]:
    if WEIGHTS_FILE.exists():
        try:
            with open(WEIGHTS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _pct(c: dict[str, float], key: str) -> float:
    return c.get(key, 0.0)


# ── Regla 1: riesgo_macro ─────────────────────────────────────────────────────

def compute_riesgo_macro(
    c: dict[str, float], nw: dict[str, int]
) -> tuple[str, float, dict]:
    """
    Nivel de riesgo macro basado en indicadores de estres financiero.
    Score > 4 = Alto | 1.5-4 = Medio | < 1.5 = Bajo
    """
    score = 0.0
    factors: dict[str, float] = {}

    brent = _pct(c, "brent")
    gold  = _pct(c, "gold")
    btc   = _pct(c, "btc")
    sp500 = _pct(c, "sp500")
    dxy   = _pct(c, "dxy")

    # Petroleo: subida fuerte = presion inflacionaria = riesgo macro
    if brent >= 4.0:
        score += 2.0;  factors["brent_surge"]   = 2.0
    elif brent >= 2.0:
        score += 1.0;  factors["brent_up"]       = 1.0
    elif brent <= -4.0:
        score -= 0.5;  factors["brent_fall"]     = -0.5

    # Oro: demanda de refugio = riesgo off
    if gold >= 1.5:
        score += 1.5;  factors["gold_safe_haven"] = 1.5
    elif gold >= 0.5:
        score += 0.5;  factors["gold_up"]         = 0.5
    elif gold <= -1.5:
        score -= 0.5;  factors["gold_down"]       = -0.5

    # BTC: proxy de apetito de riesgo (cae = risk off)
    if btc <= -4.0:
        score += 2.0;  factors["btc_crash"]       = 2.0
    elif btc <= -2.0:
        score += 1.0;  factors["btc_drop"]        = 1.0
    elif btc <= -0.5:
        score += 0.3;  factors["btc_weak"]        = 0.3
    elif btc >= 3.0:
        score -= 1.0;  factors["btc_rally"]       = -1.0
    elif btc >= 1.0:
        score -= 0.3;  factors["btc_up"]          = -0.3

    # S&P 500: barometro de confianza corporativa
    if sp500 <= -2.0:
        score += 2.5;  factors["sp500_selloff"]   = 2.5
    elif sp500 <= -1.0:
        score += 1.5;  factors["sp500_down"]      = 1.5
    elif sp500 <= -0.5:
        score += 0.5;  factors["sp500_weak"]      = 0.5
    elif sp500 >= 1.0:
        score -= 1.0;  factors["sp500_rally"]     = -1.0
    elif sp500 >= 0.5:
        score -= 0.3;  factors["sp500_up"]        = -0.3

    # DXY: dolar fuerte = presion sobre emergentes
    if dxy >= 1.0:
        score += 1.0;  factors["dxy_strong"]      = 1.0
    elif dxy >= 0.4:
        score += 0.4;  factors["dxy_up"]          = 0.4
    elif dxy <= -0.8:
        score -= 0.5;  factors["dxy_weak"]        = -0.5

    # Modificadores por noticias
    rec_w = nw.get("recesion", 0)
    if rec_w >= 3:
        score += 2.0;  factors["news_recesion_alta"]    = 2.0
    elif rec_w >= 2:
        score += 1.0;  factors["news_recesion_media"]   = 1.0
    elif rec_w >= 1:
        score += 0.3;  factors["news_recesion_baja"]    = 0.3

    geo_w = nw.get("geopolitica", 0)
    if geo_w >= 3:
        score += 1.5;  factors["news_geopolitica_alta"] = 1.5
    elif geo_w >= 2:
        score += 0.7;  factors["news_geopolitica_med"]  = 0.7

    # Clasificacion
    if score >= 4.0:
        nivel = "Alto"
    elif score >= 1.5:
        nivel = "Medio"
    else:
        nivel = "Bajo"

    return nivel, round(score, 2), factors


# ── Regla 2: sesgo_mercado ────────────────────────────────────────────────────

def compute_sesgo_mercado(
    c: dict[str, float], nw: dict[str, int]
) -> tuple[str, dict]:
    """
    Sesgo Risk-on / Risk-off / Mixto.
    Gana el lado que supere al otro por al menos 1.5 puntos.
    """
    risk_on  = 0.0
    risk_off = 0.0
    details: dict[str, str] = {}

    btc   = _pct(c, "btc")
    sp500 = _pct(c, "sp500")
    gold  = _pct(c, "gold")
    dxy   = _pct(c, "dxy")

    # BTC
    if btc >= 3.0:
        risk_on  += 2.0; details["btc"] = f"Risk-on +2 (BTC {btc:+.1f}%)"
    elif btc >= 1.0:
        risk_on  += 1.0; details["btc"] = f"Risk-on +1 (BTC {btc:+.1f}%)"
    elif btc <= -3.0:
        risk_off += 2.0; details["btc"] = f"Risk-off +2 (BTC {btc:+.1f}%)"
    elif btc <= -1.0:
        risk_off += 1.0; details["btc"] = f"Risk-off +1 (BTC {btc:+.1f}%)"

    # S&P 500
    if sp500 >= 1.0:
        risk_on  += 2.0; details["sp500"] = f"Risk-on +2 (SP500 {sp500:+.1f}%)"
    elif sp500 >= 0.4:
        risk_on  += 1.0; details["sp500"] = f"Risk-on +1 (SP500 {sp500:+.1f}%)"
    elif sp500 <= -1.5:
        risk_off += 2.5; details["sp500"] = f"Risk-off +2.5 (SP500 {sp500:+.1f}%)"
    elif sp500 <= -0.5:
        risk_off += 1.5; details["sp500"] = f"Risk-off +1.5 (SP500 {sp500:+.1f}%)"

    # Oro (refugio)
    if gold >= 1.0:
        risk_off += 1.5; details["gold"] = f"Risk-off +1.5 (Oro {gold:+.1f}%)"
    elif gold >= 0.3:
        risk_off += 0.5; details["gold"] = f"Risk-off +0.5 (Oro {gold:+.1f}%)"
    elif gold <= -1.0:
        risk_on  += 0.5; details["gold"] = f"Risk-on +0.5 (Oro {gold:+.1f}%)"

    # DXY
    if dxy >= 0.6:
        risk_off += 1.0; details["dxy"] = f"Risk-off +1 (DXY {dxy:+.1f}%)"
    elif dxy <= -0.6:
        risk_on  += 1.0; details["dxy"] = f"Risk-on +1 (DXY {dxy:+.1f}%)"

    # Noticias apetito de riesgo
    if nw.get("apetito_riesgo", 0) >= 2:
        risk_off += 0.5; details["news"] = "Risk-off +0.5 (noticias apetito_riesgo)"

    gap = risk_on - risk_off
    if gap >= 1.5:
        sesgo = "Risk-on"
    elif gap <= -1.5:
        sesgo = "Risk-off"
    else:
        sesgo = "Mixto"

    return sesgo, {"risk_on": round(risk_on, 2), "risk_off": round(risk_off, 2), "details": details}


# ── Regla 3: presion_inflacionaria ───────────────────────────────────────────

def compute_presion_inflacionaria(
    c: dict[str, float], nw: dict[str, int]
) -> tuple[str, float, dict]:
    """
    Presion inflacionaria Bajista / Neutral / Alcista.
    Brent domina; oro y plata como modificadores; DXY como contrapeso.
    Score > 1.5 = Alcista | < -1.5 = Bajista | resto = Neutral
    """
    score = 0.0
    factors: dict[str, float] = {}

    brent  = _pct(c, "brent")
    gold   = _pct(c, "gold")
    silver = _pct(c, "silver")
    dxy    = _pct(c, "dxy")

    # Brent (principal driver energetico)
    if brent >= 4.0:
        score += 4.0;  factors["brent_surge"]   = 4.0
    elif brent >= 2.0:
        score += 3.0;  factors["brent_up"]       = 3.0
    elif brent >= 0.8:
        score += 1.5;  factors["brent_mild"]     = 1.5
    elif brent <= -4.0:
        score -= 4.0;  factors["brent_crash"]    = -4.0
    elif brent <= -2.0:
        score -= 3.0;  factors["brent_fall"]     = -3.0
    elif brent <= -0.8:
        score -= 1.5;  factors["brent_weak"]     = -1.5

    # Oro (cobertura inflacionaria)
    if gold >= 1.5:
        score += 0.8;  factors["gold_hedge"]     = 0.8
    elif gold >= 0.5:
        score += 0.3;  factors["gold_up"]        = 0.3
    elif gold <= -1.5:
        score -= 0.5;  factors["gold_down"]      = -0.5
    elif gold <= -0.5:
        score -= 0.2;  factors["gold_weak"]      = -0.2

    # Plata (proxy industrial + inflacion)
    if silver >= 2.0:
        score += 0.3;  factors["silver_up"]      = 0.3
    elif silver <= -2.0:
        score -= 0.3;  factors["silver_down"]    = -0.3

    # DXY: dolar fuerte = desinflacion importada
    if dxy >= 0.8:
        score -= 0.5;  factors["dxy_deflationary"] = -0.5
    elif dxy <= -0.8:
        score += 0.5;  factors["dxy_inflationary"] = 0.5

    # Modificadores por noticias
    infl_w = nw.get("inflacion", 0)
    if infl_w >= 3:
        score += 1.0;  factors["news_inflacion_alta"]  = 1.0
    elif infl_w >= 2:
        score += 0.5;  factors["news_inflacion_media"] = 0.5
    if nw.get("petroleo", 0) >= 3:
        score += 0.5;  factors["news_petroleo_alta"]   = 0.5

    # Clasificacion
    if score >= 1.5:
        nivel = "Alcista"
    elif score <= -1.5:
        nivel = "Bajista"
    else:
        nivel = "Neutral"

    return nivel, round(score, 2), factors


# ── Regla 4: presion_cop ─────────────────────────────────────────────────────

def compute_presion_cop(
    c: dict[str, float], nw: dict[str, int]
) -> tuple[str, float, dict]:
    """
    Presion sobre el peso colombiano.
    Score > 2 = Alcista USD/COP | < -2 = Favorable COP | resto = Neutral.
    Nota: brent arriba es POSITIVO para Colombia (pais exportador).
    """
    score = 0.0
    factors: dict[str, float] = {}

    dxy    = _pct(c, "dxy")
    brent  = _pct(c, "brent")
    usdcop = _pct(c, "usdcop")
    sp500  = _pct(c, "sp500")

    # DXY: mayor determinante del COP
    if dxy >= 1.0:
        score += 2.5;  factors["dxy_strong"]          = 2.5
    elif dxy >= 0.5:
        score += 1.5;  factors["dxy_up"]              = 1.5
    elif dxy >= 0.2:
        score += 0.5;  factors["dxy_mild"]            = 0.5
    elif dxy <= -1.0:
        score -= 2.5;  factors["dxy_weak"]            = -2.5
    elif dxy <= -0.5:
        score -= 1.5;  factors["dxy_down"]            = -1.5
    elif dxy <= -0.2:
        score -= 0.5;  factors["dxy_mild_down"]       = -0.5

    # Brent: Colombia es exportador -> brent arriba = COP se fortalece
    if brent >= 3.0:
        score -= 1.5;  factors["brent_cop_positive"]  = -1.5
    elif brent >= 1.5:
        score -= 0.8;  factors["brent_mild_cop"]      = -0.8
    elif brent <= -3.0:
        score += 1.5;  factors["brent_cop_negative"]  = 1.5
    elif brent <= -1.5:
        score += 0.8;  factors["brent_weak_cop"]      = 0.8

    # USD/COP directo
    if usdcop >= 2.0:
        score += 2.0;  factors["usdcop_direct_up"]    = 2.0
    elif usdcop >= 1.0:
        score += 1.0;  factors["usdcop_up"]           = 1.0
    elif usdcop <= -2.0:
        score -= 2.0;  factors["usdcop_direct_down"]  = -2.0
    elif usdcop <= -1.0:
        score -= 1.0;  factors["usdcop_down"]         = -1.0

    # S&P 500: correlacion con emergentes
    if sp500 <= -1.5:
        score += 1.0;  factors["sp500_em_pressure"]   = 1.0
    elif sp500 <= -0.8:
        score += 0.5;  factors["sp500_weak"]          = 0.5
    elif sp500 >= 1.0:
        score -= 0.5;  factors["sp500_em_relief"]     = -0.5

    # Noticias Colombia
    col_w = nw.get("colombia", 0)
    if col_w >= 3:
        score += 1.0;  factors["news_colombia_alta"]  = 1.0
    elif col_w >= 2:
        score += 0.5;  factors["news_colombia_media"] = 0.5

    # Clasificacion
    if score >= 2.0:
        nivel = "Alcista USD/COP"
    elif score <= -2.0:
        nivel = "Favorable COP"
    else:
        nivel = "Neutral"

    return nivel, round(score, 2), factors


# ── Regla 5: conviccion ───────────────────────────────────────────────────────

def compute_conviccion(
    riesgo: str,
    sesgo: str,
    inflacion: str,
    cop: str,
    c: dict[str, float],
    nw: dict[str, int],
    scores: dict[str, float],
) -> tuple[int, str]:
    """
    Conviccion 1-10 basada en:
    - Numero de indicadores con movimientos significativos
    - Consistencia interna (ausencia de contradicciones)
    - Refuerzo de senales por noticias
    - Magnitud de los scores internos
    """
    base = 3.0

    # Indicadores con movimiento significativo (>= 1.5%)
    sig_count = sum(1 for v in c.values() if abs(v) >= 1.5)
    base += min(sig_count * 0.5, 3.0)

    # Penalizar contradicciones internas
    contradictions = 0
    if riesgo == "Alto" and sesgo == "Risk-on":
        contradictions += 1
    if inflacion == "Alcista" and sesgo == "Risk-off" and _pct(c, "brent") < 0:
        contradictions += 1
    base -= contradictions * 0.7

    # Noticias refuerzan conviccion
    news_total = sum(nw.values())
    base += min(news_total * 0.1, 2.0)

    # Senales extremas aumentan conviccion
    if abs(scores.get("riesgo_score", 0)) >= 5:
        base += 1.0
    if abs(scores.get("inflacion_score", 0)) >= 3:
        base += 0.5
    if abs(scores.get("cop_score", 0)) >= 3:
        base += 0.5

    conv = max(1, min(10, round(base)))
    razon = (
        f"{sig_count} indicador(es) con movimiento significativo"
        + (f", {contradictions} contradiccion(es) detectada(s)" if contradictions else "")
    )
    return conv, razon


# ── History persistence ───────────────────────────────────────────────────────

def append_signals_history(
    signals: dict,
    driver_principal: str = "",
    driver_secundario: str = "",
) -> None:
    """Agrega (o actualiza) la fila del dia en signals_history.csv."""
    fecha = datetime.now().strftime("%Y-%m-%d")
    new_row = {
        "fecha":                 fecha,
        "riesgo_macro":          signals.get("riesgo_macro",           ""),
        "sesgo_mercado":         signals.get("sesgo_mercado",          ""),
        "presion_inflacionaria": signals.get("presion_inflacionaria",  ""),
        "presion_cop":           signals.get("presion_cop",            ""),
        "conviccion":            signals.get("conviccion",             0),
        "driver_principal":      driver_principal,
        "driver_secundario":     driver_secundario,
    }
    SIGNALS_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SIGNALS_HISTORY_FILE.exists():
        df = pd.read_csv(SIGNALS_HISTORY_FILE)
        df = df[df["fecha"] != fecha]
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    else:
        df = pd.DataFrame([new_row], columns=HISTORY_COLS)
    df.to_csv(SIGNALS_HISTORY_FILE, index=False)
    print(f"  Historial actualizado: {SIGNALS_HISTORY_FILE} ({len(df)} filas)")


# ── Main ──────────────────────────────────────────────────────────────────────

def _load_adaptive_weights() -> dict[str, float]:
    """Retorna {indicator: multiplicador} desde adaptive_weights.json."""
    if not ADAPTIVE_FILE.exists():
        return {}
    try:
        with open(ADAPTIVE_FILE, "rb") as f:
            raw = f.read().rstrip(b"\x00")
        data = json.loads(raw.decode("utf-8"))
        return {k: v["multiplicador"] for k, v in data.get("pesos", {}).items()}
    except Exception:
        return {}


def _apply_adaptive_weights(
    changes: dict[str, float],
    multipliers: dict[str, float],
) -> dict[str, float]:
    """Escala las variaciones de precio según los multiplicadores adaptativos."""
    if not multipliers:
        return changes
    return {k: v * multipliers.get(k, 1.0) for k, v in changes.items()}


def run_signals_engine() -> dict:
    changes_raw  = _load_changes()
    nw           = _load_news_weights()
    multipliers  = _load_adaptive_weights()
    changes      = _apply_adaptive_weights(changes_raw, multipliers)

    riesgo,    riesgo_score,    riesgo_factors    = compute_riesgo_macro(changes, nw)
    sesgo,     sesgo_detail                       = compute_sesgo_mercado(changes, nw)
    inflacion, inflacion_score, inflacion_factors = compute_presion_inflacionaria(changes, nw)
    cop,       cop_score,       cop_factors       = compute_presion_cop(changes, nw)

    scores = {
        "riesgo_score":    riesgo_score,
        "inflacion_score": inflacion_score,
        "cop_score":       cop_score,
    }
    conviccion, conv_razon = compute_conviccion(
        riesgo, sesgo, inflacion, cop, changes, nw, scores
    )

    return {
        "senales": {
            "riesgo_macro":            riesgo,
            "sesgo_mercado":           sesgo,
            "presion_inflacionaria":   inflacion,
            "presion_cop":             cop,
            "conviccion":              conviccion,
        },
        "scores_internos": {
            "riesgo_score":     riesgo_score,
            "sesgo_risk_on":    sesgo_detail["risk_on"],
            "sesgo_risk_off":   sesgo_detail["risk_off"],
            "inflacion_score":  inflacion_score,
            "cop_score":        cop_score,
            "conviccion_razon": conv_razon,
        },
        "factores": {
            "riesgo":    riesgo_factors,
            "inflacion": inflacion_factors,
            "cop":       cop_factors,
            "sesgo":     sesgo_detail["details"],
        },
        "pesos_noticias":        nw,
        "variaciones_mercado":   changes_raw,
        "variaciones_ajustadas": changes,
        "multiplicadores_activos": multipliers,
    }


def main():
    print("Generando senales compuestas del mercado...")
    result = run_signals_engine()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    s = result["senales"]
    print(f"  riesgo_macro           : {s['riesgo_macro']}")
    print(f"  sesgo_mercado          : {s['sesgo_mercado']}")
    print(f"  presion_inflacionaria  : {s['presion_inflacionaria']}")
    print(f"  presion_cop            : {s['presion_cop']}")
    print(f"  conviccion             : {s['conviccion']}/10")
    print(f"\n  Guardado en: {OUTPUT_FILE}")
    # Historial: los drivers se llenaran cuando causal_interpreter lo llame
    append_signals_history(s)


if __name__ == "__main__":
    main()
