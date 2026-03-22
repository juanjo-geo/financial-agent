"""
Detector de cambio de regimen macro.

Analiza signals_history.csv de los ultimos 14 dias para cuantificar
si el mercado esta transitando entre regimenes (Risk-on <-> Risk-off,
Bajo <-> Alto riesgo, etc.).

Salida: data/signals/regime_change.json
Campos:
  score          : 0-100 (0=estable, 100=cambio total de regimen)
  nivel          : Estable / Transicion / Significativo / Critico
  tipo_cambio    : Gradual / Abrupto
  alerta         : bool (score >= ALERT_THRESHOLD)
  direccion      : Deterioro / Mejora / Mixto
  transiciones   : lista de dims con cambios detectados
  descripcion    : narrativa en espanol
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT                 = Path(__file__).parent.parent
SIGNALS_HISTORY_FILE = ROOT / "data/signals/signals_history.csv"
OUTPUT_FILE          = ROOT / "data/signals/regime_change.json"

WINDOW_DAYS      = 14
RECENT_DAYS      = 3       # "ahora" = ultimos N dias
MIN_ROWS         = 4       # minimo para calculo significativo
ALERT_THRESHOLD  = 70


# ── Codificadores ordinales ───────────────────────────────────────────────────

_ENCODERS: dict[str, dict[str, float]] = {
    "sesgo_mercado":         {"Risk-on": -1.0, "Mixto": 0.0, "Risk-off":  1.0},
    "riesgo_macro":          {"Bajo":     0.0, "Medio": 1.0, "Alto":      2.0},
    "presion_inflacionaria": {"Bajista": -1.0, "Neutral": 0.0, "Alcista": 1.0},
    "presion_cop":           {"Favorable COP": -1.0, "Neutral": 0.0, "Alcista USD/COP": 1.0},
}

# Maximo delta posible por dimension (para normalizar a 0-peso)
_MAX_DELTA: dict[str, float] = {
    "sesgo_mercado":         2.0,
    "riesgo_macro":          2.0,
    "presion_inflacionaria": 2.0,
    "presion_cop":           2.0,
}

# Peso de cada dimension en el score total (suma = 100)
_WEIGHTS: dict[str, int] = {
    "sesgo_mercado":         30,
    "riesgo_macro":          30,
    "presion_inflacionaria": 20,
    "presion_cop":           20,
}

_DIM_LABELS: dict[str, str] = {
    "sesgo_mercado":         "Sesgo de Mercado",
    "riesgo_macro":          "Riesgo Macro",
    "presion_inflacionaria": "Presion Inflacionaria",
    "presion_cop":           "Presion COP",
}

# Representacion de riesgo creciente (>0 = mas riesgo, <0 = menos riesgo)
_RISK_DIRECTION: dict[str, dict[str, float]] = {
    "sesgo_mercado":         {"Risk-on": -1.0, "Mixto": 0.0, "Risk-off":  1.0},
    "riesgo_macro":          {"Bajo": -1.0, "Medio": 0.0, "Alto":         1.0},
    "presion_inflacionaria": {"Bajista": -0.5, "Neutral": 0.0, "Alcista": 0.5},
    "presion_cop":           {"Favorable COP": -0.5, "Neutral": 0.0, "Alcista USD/COP": 0.5},
}


# ── Loader ───────────────────────────────────────────────────────────────────

def _load_history() -> pd.DataFrame:
    if not SIGNALS_HISTORY_FILE.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(SIGNALS_HISTORY_FILE)
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df = df.dropna(subset=["fecha"]).sort_values("fecha")
        return df.tail(WINDOW_DAYS).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


# ── Analisis por dimension ────────────────────────────────────────────────────

def _encode_col(df: pd.DataFrame, col: str) -> list[float]:
    enc = _ENCODERS.get(col, {})
    return df[col].map(enc).fillna(0.0).tolist()


def _dim_score(all_vals: list[float], col: str) -> tuple[float, float, float]:
    """
    Retorna (dim_score, recent_mean, baseline_mean).
    dim_score es la contribucion normalizada al score total (0..weight).
    """
    if len(all_vals) < 2:
        return 0.0, 0.0, 0.0
    recent   = all_vals[-RECENT_DAYS:]
    baseline = all_vals[:-RECENT_DAYS] if len(all_vals) > RECENT_DAYS else all_vals

    recent_mean   = sum(recent) / len(recent)
    baseline_mean = sum(baseline) / len(baseline)
    delta         = abs(recent_mean - baseline_mean)

    weight    = _WEIGHTS[col]
    max_delta = _MAX_DELTA[col]
    score     = min(float(weight), delta / max_delta * weight)
    return round(score, 2), round(recent_mean, 3), round(baseline_mean, 3)


def _is_abrupt(all_vals_by_dim: dict[str, list[float]], score: float) -> bool:
    """
    Cambio abrupto si alguna dimension cambia >= 1.0 en un solo dia
    dentro de los ultimos 5 dias Y el score global >= 30.
    """
    if score < 30:
        return False
    for vals in all_vals_by_dim.values():
        recent = vals[-5:]
        for i in range(1, len(recent)):
            if abs(recent[i] - recent[i - 1]) >= 1.0:
                return True
    return False


def _current_values(df: pd.DataFrame) -> dict[str, str]:
    """Valores de la ultima fila del historico."""
    if df.empty:
        return {}
    last = df.iloc[-1]
    return {col: str(last.get(col, "")) for col in _ENCODERS}


def _baseline_mode(df: pd.DataFrame, col: str) -> str:
    """Valor mas frecuente en el periodo baseline (excl. ultimos RECENT_DAYS)."""
    baseline_df = df.iloc[:-RECENT_DAYS] if len(df) > RECENT_DAYS else df
    if baseline_df.empty:
        return ""
    return str(baseline_df[col].mode().iloc[0]) if not baseline_df[col].mode().empty else ""


# ── Narrativa ────────────────────────────────────────────────────────────────

def _build_narrative(
    score: float,
    nivel: str,
    tipo: str,
    direccion: str,
    transiciones: list[dict],
    n_days: int,
) -> str:
    if score < 15:
        return (
            "El mercado se encuentra en un regimen estable. "
            "Las senales macro no muestran cambios significativos "
            f"en los ultimos {n_days} dias."
        )

    # Intro segun tipo
    if tipo == "Abrupto":
        intro = "Se detecta un cambio abrupto en el regimen macro"
    else:
        intro = "Se observa una transicion gradual en el regimen macro"

    # Top transicion
    top = transiciones[0] if transiciones else None
    top_str = ""
    if top:
        de_val = top.get("de", "")
        a_val  = top.get("a",  "")
        dim    = top.get("dimension_label", "")
        if de_val and a_val and de_val != a_val:
            top_str = f": {dim} transita de {de_val} hacia {a_val}"
        elif de_val:
            top_str = f": {dim} muestra cambio desde {de_val}"

    # Nivel de alerta
    if score >= 80:
        alerta_str = "Las condiciones sugieren un cambio de fase inminente que requiere atencion inmediata."
    elif score >= 70:
        alerta_str = "El nivel de cambio supera el umbral de alerta. Se recomienda revisar posicionamiento."
    elif score >= 50:
        alerta_str = "El cambio es relevante pero aun no alcanza nivel de alerta critica."
    else:
        alerta_str = "El movimiento es moderado; seguimiento recomendado en proximas sesiones."

    # Direccion
    if direccion == "Deterioro":
        dir_str = "El entorno de riesgo parece estar deteriorandose."
    elif direccion == "Mejora":
        dir_str = "El entorno de riesgo muestra senales de mejora."
    else:
        dir_str = "Las senales presentan direcciones contradictorias."

    return f"{intro}{top_str}. {dir_str} {alerta_str}"


# ── Motor principal ───────────────────────────────────────────────────────────

def run_regime_change_detector() -> dict:
    df = _load_history()

    if df.empty or len(df) < MIN_ROWS:
        n = len(df)
        return {
            "fecha":        datetime.now().strftime("%Y-%m-%d"),
            "generado_en":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "score":        0,
            "nivel":        "Estable",
            "tipo_cambio":  "Gradual",
            "alerta":       False,
            "direccion":    "Mixto",
            "transiciones": [],
            "descripcion":  (
                f"Historial insuficiente ({n} dias). "
                f"Se necesitan al menos {MIN_ROWS} dias para calcular el score."
            ),
            "n_dias_analizados": n,
        }

    n_days = len(df)
    all_vals:   dict[str, list[float]] = {}
    dim_scores: dict[str, float]       = {}
    recent_means:   dict[str, float]   = {}
    baseline_means: dict[str, float]   = {}

    for col in _ENCODERS:
        if col not in df.columns:
            all_vals[col]       = [0.0] * n_days
            dim_scores[col]     = 0.0
            recent_means[col]   = 0.0
            baseline_means[col] = 0.0
            continue
        vals = _encode_col(df, col)
        all_vals[col] = vals
        ds, rm, bm = _dim_score(vals, col)
        dim_scores[col]     = ds
        recent_means[col]   = rm
        baseline_means[col] = bm

    total_score = round(sum(dim_scores.values()), 1)

    # Nivel
    if total_score >= 80:
        nivel = "Critico"
    elif total_score >= 60:
        nivel = "Significativo"
    elif total_score >= 30:
        nivel = "Transicion"
    else:
        nivel = "Estable"

    # Tipo
    abrupt     = _is_abrupt(all_vals, total_score)
    tipo_cambio = "Abrupto" if abrupt else "Gradual"
    alerta      = total_score >= ALERT_THRESHOLD

    # Direccion de riesgo: compara reciente vs baseline en terminos de riesgo
    risk_recent   = 0.0
    risk_baseline = 0.0
    for col, rd_map in _RISK_DIRECTION.items():
        enc = _ENCODERS.get(col, {})
        rev = {v: k for k, v in enc.items()}  # num -> label

        r_val  = recent_means.get(col, 0.0)
        b_val  = baseline_means.get(col, 0.0)

        # Map mean numeric value to nearest risk direction
        # Simple: use the sign of (recent - baseline) * risk_sign
        # Risk sign: positive if higher encoded = higher risk
        risk_sign = 1.0 if col in ("sesgo_mercado", "riesgo_macro") else 0.5
        risk_recent   += (r_val - b_val) * risk_sign

    if risk_recent > 0.3:
        direccion = "Deterioro"
    elif risk_recent < -0.3:
        direccion = "Mejora"
    else:
        direccion = "Mixto"

    # Transiciones: dimensiones con cambio > umbral (score parcial > 3)
    current = _current_values(df)
    transiciones: list[dict] = []
    for col in sorted(_ENCODERS, key=lambda c: -dim_scores[c]):
        ds = dim_scores[col]
        if ds < 3.0:
            continue
        de_val = _baseline_mode(df, col)
        a_val  = current.get(col, "")
        transiciones.append({
            "dimension":       col,
            "dimension_label": _DIM_LABELS[col],
            "de":              de_val,
            "a":               a_val,
            "score_parcial":   ds,
            "peso_dimension":  _WEIGHTS[col],
        })

    descripcion = _build_narrative(
        total_score, nivel, tipo_cambio, direccion, transiciones, n_days
    )

    # Series para el dashboard (ultimos 14 dias de cada senal)
    series: dict[str, list] = {}
    for col in _ENCODERS:
        if col in df.columns:
            series[col] = df[col].tolist()
        else:
            series[col] = []

    return {
        "fecha":              datetime.now().strftime("%Y-%m-%d"),
        "generado_en":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "score":              total_score,
        "nivel":              nivel,
        "tipo_cambio":        tipo_cambio,
        "alerta":             alerta,
        "direccion":          direccion,
        "transiciones":       transiciones,
        "descripcion":        descripcion,
        "scores_por_dim":     {c: dim_scores[c]     for c in _ENCODERS},
        "recientes":          {c: recent_means[c]   for c in _ENCODERS},
        "baselines":          {c: baseline_means[c] for c in _ENCODERS},
        "n_dias_analizados":  n_days,
        "series":             series,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Detectando cambio de regimen macro...")
    result = run_regime_change_detector()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    score  = result["score"]
    nivel  = result["nivel"]
    tipo   = result["tipo_cambio"]
    alerta = result["alerta"]
    direc  = result["direccion"]

    print(f"  Regime Change Score : {score}/100  [{nivel}]")
    print(f"  Tipo de cambio      : {tipo}")
    print(f"  Direccion           : {direc}")
    print(f"  Alerta              : {'SI - Score >= 70' if alerta else 'No'}")

    if result["transiciones"]:
        print("  Transiciones detectadas:")
        for t in result["transiciones"]:
            de = t.get("de", "?")
            a  = t.get("a",  "?")
            arrow = "->" if de != a else "="
            print(f"    {t['dimension_label']:<25} {de} {arrow} {a}  "
                  f"(+{t['score_parcial']:.1f}pts)")
    else:
        print("  Sin transiciones significativas detectadas.")

    print(f"\n  {result['descripcion']}")
    print(f"\n  Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
