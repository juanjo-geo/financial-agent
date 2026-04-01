"""
ml_predictor.py
---------------
Modelo ML que predice la DIRECCIÓN de BTC al día siguiente
usando el historial de precios de los 8 indicadores macro.

Modelo: RandomForestClassifier (scikit-learn)
  - No requiere GPU ni API externa
  - Entrena en segundos con los datos históricos disponibles
  - Se re-entrena cada vez que corre el pipeline (aprendizaje continuo)

Features por día t:
  - Variación % de cada indicador (btc, brent, gold, silver, dxy,
    sp500, usdcop, global_inflation_proxy)
  - Lags t-1 y t-2 de las mismas variaciones
  - Volatilidad rolling 5 días de BTC

Target:
  - btc_dir_next: +1 (BTC sube >0.5% al día siguiente)
                  -1 (BTC baja <-0.5%)
                   0 (lateral)

Salida:
  - data/signals/ml_model_meta.json   (métricas + importancias)
  - data/signals/ml_prediction_hoy.json  (predicción del día actual)
  - La predicción se agrega a daily_signals.json vía causal_interpreter

Uso: python -m intelligence.ml_predictor
"""

from __future__ import annotations

import json
import os
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT             = Path(__file__).parent.parent
MARKET_FILE      = ROOT / "data/historical/market_history.csv"
SNAPSHOT_FILE    = ROOT / "data/processed/latest_snapshot.csv"
MODEL_META_FILE  = ROOT / "data/signals/ml_model_meta.json"
PREDICTION_FILE  = ROOT / "data/signals/ml_prediction_hoy.json"
DAILY_SIGNALS    = ROOT / "data/signals/daily_signals.json"

INDICATORS = ["btc", "brent", "gold", "silver", "dxy", "sp500", "usdcop",
              "eurusd", "nasdaq", "wti"]
# NOTA: global_inflation_proxy excluido (sin ticker yfinance → datos desde nov-2025 solo)
# Los indicadores listados tienen 500+ días de historial desde backfill_extended.py

TARGET_THRESHOLD = 0.5   # % mínimo para clasificar como Alcista/Bajista
LAG_DAYS         = 2     # cuántos días de lags usar
MIN_TRAIN_ROWS   = 30    # mínimo de filas para entrenar


# ── Feature engineering ───────────────────────────────────────────────────────

def build_feature_matrix(df_history: pd.DataFrame) -> pd.DataFrame:
    """
    Pivotea market_history → DataFrame wide con features por día.
    Columnas: {ind}_chg, {ind}_chg_lag1, {ind}_chg_lag2, btc_vol5
    """
    df = df_history.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.normalize()
    df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce")

    # Pivot: filas=fecha, columnas=indicador
    pivot = df.pivot_table(
        index="date", columns="indicator", values="change_pct", aggfunc="last"
    )

    # Mantener solo indicadores conocidos presentes
    present = [c for c in INDICATORS if c in pivot.columns]
    pivot = pivot[present].copy()
    pivot.columns = [f"{c}_chg" for c in present]

    # Lags
    for lag in range(1, LAG_DAYS + 1):
        for col in list(pivot.columns):
            pivot[f"{col}_lag{lag}"] = pivot[col].shift(lag)

    # Volatilidad BTC rolling 5 días
    if "btc_chg" in pivot.columns:
        pivot["btc_vol5"] = pivot["btc_chg"].rolling(5).std()

    pivot = pivot.dropna()
    return pivot.reset_index()


def build_target(df_history: pd.DataFrame) -> pd.Series:
    """Retorna Serie con btc_dir_next: +1, -1, 0 para cada fecha."""
    df = df_history.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.normalize()
    btc = df[df["indicator"] == "btc"].copy()
    btc = btc.sort_values("date").drop_duplicates("date", keep="last")
    btc["change_pct"] = pd.to_numeric(btc["change_pct"], errors="coerce")

    def _dir(x):
        if pd.isna(x):   return np.nan
        if x >  TARGET_THRESHOLD: return 1
        if x < -TARGET_THRESHOLD: return -1
        return 0

    # Target es la dirección del DÍA SIGUIENTE
    btc["btc_dir_next"] = btc["change_pct"].shift(-1).apply(_dir)
    return btc.set_index("date")["btc_dir_next"]


# ── Entrenamiento ─────────────────────────────────────────────────────────────

def train_model(X: pd.DataFrame, y: pd.Series):
    """Entrena RandomForestClassifier. Retorna (modelo, cv_accuracy)."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import LabelEncoder

    # Alinear X e y
    common = X.index.intersection(y.index)
    X_al = X.loc[common].select_dtypes(include=[np.number])
    y_al = y.loc[common].dropna()
    X_al = X_al.loc[y_al.index]

    if len(X_al) < MIN_TRAIN_ROWS:
        raise ValueError(
            f"Solo {len(X_al)} filas de entrenamiento. Mínimo: {MIN_TRAIN_ROWS}."
        )

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=4,           # shallow para evitar overfitting con pocos datos
        min_samples_leaf=3,
        random_state=42,
        class_weight="balanced",
    )

    # Cross-validation con TimeSeriesSplit (preservar orden temporal)
    from sklearn.model_selection import TimeSeriesSplit
    tscv = TimeSeriesSplit(n_splits=5)
    cv_scores = cross_val_score(model, X_al, y_al, cv=tscv, scoring="accuracy")

    model.fit(X_al, y_al)
    return model, X_al, y_al, cv_scores


# ── Predicción del día actual ─────────────────────────────────────────────────

def predict_today(
    model,
    feature_matrix: pd.DataFrame,
    snapshot_file: Path,
) -> dict:
    """
    Genera features del día de hoy combinando snapshot actual + últimos lags
    del historial y produce la predicción.
    """
    # Features del día actual desde snapshot
    if not snapshot_file.exists():
        return {"error": "snapshot no encontrado"}

    snap = pd.read_csv(snapshot_file)
    today_changes: dict[str, float] = {}
    for _, row in snap.iterrows():
        ind = str(row.get("indicator", "")).lower()
        pct = pd.to_numeric(row.get("change_pct"), errors="coerce")
        if ind in INDICATORS and pd.notna(pct):
            today_changes[ind] = float(pct)

    # Tomar los últimos LAG_DAYS días del historial como lags
    last_rows = feature_matrix.tail(LAG_DAYS).copy()

    # Construir vector de features en el mismo orden que el entrenamiento
    feature_cols = [c for c in feature_matrix.columns if c != "date"]
    today_feat: dict[str, float] = {}

    for col in feature_cols:
        if col.endswith("_chg") and not "lag" in col:
            ind = col.replace("_chg", "")
            today_feat[col] = today_changes.get(ind, 0.0)
        elif "_lag1" in col:
            base = col.replace("_lag1", "")
            # lag1 = valor de ayer = última fila del historial
            if len(last_rows) >= 1 and base in last_rows.columns:
                today_feat[col] = float(last_rows[base].iloc[-1])
            else:
                today_feat[col] = 0.0
        elif "_lag2" in col:
            base = col.replace("_lag2", "")
            if len(last_rows) >= 2 and base in last_rows.columns:
                today_feat[col] = float(last_rows[base].iloc[-2])
            else:
                today_feat[col] = 0.0
        elif col == "btc_vol5":
            # Volatilidad rolling 5d: std de los últimos 5 retornos BTC
            btc_col = "btc_chg"
            recent_btc = list(feature_matrix[btc_col].tail(4)) + \
                         [today_changes.get("btc", 0.0)]
            today_feat[col] = float(np.std(recent_btc)) if recent_btc else 0.0
        else:
            today_feat[col] = 0.0

    X_today = pd.DataFrame([today_feat])[feature_cols]
    X_today = X_today.select_dtypes(include=[np.number])

    try:
        proba = model.predict_proba(X_today)[0]
        pred  = model.predict(X_today)[0]
        classes = list(model.classes_)
        proba_dict = {str(int(c)): round(float(p), 4) for c, p in zip(classes, proba)}
    except Exception as e:
        return {"error": str(e)}

    label_map = {1: "Alcista", -1: "Bajista", 0: "Lateral"}
    confianza = round(max(proba) * 10)  # escalar a 1-10

    return {
        "direccion":    label_map.get(int(pred), str(pred)),
        "valor_pred":   int(pred),
        "probabilidades": proba_dict,
        "confianza_ml": confianza,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        from sklearn.ensemble import RandomForestClassifier  # noqa: F401
    except ImportError:
        print("  scikit-learn no instalado. Ejecuta: pip install scikit-learn")
        return

    print("Cargando historial de mercado...")
    if not MARKET_FILE.exists():
        print(f"  No se encontró {MARKET_FILE}")
        return

    df_hist = pd.read_csv(MARKET_FILE)
    print(f"  {len(df_hist)} registros históricos ({df_hist['indicator'].nunique()} indicadores)")

    # Construir features y target
    feat_matrix = build_feature_matrix(df_hist)
    feat_matrix = feat_matrix.set_index("date")
    target      = build_target(df_hist)

    print(f"  Features: {feat_matrix.shape[1]} columnas, {len(feat_matrix)} filas")
    print(f"  Distribución target: {target.value_counts().to_dict()}")

    # Entrenar
    print("Entrenando RandomForest...")
    model, X_train, y_train, cv_scores = train_model(feat_matrix, target)

    cv_mean = round(float(cv_scores.mean()), 4)
    cv_std  = round(float(cv_scores.std()),  4)
    print(f"  CV Accuracy (TimeSeriesSplit-5): {cv_mean:.1%} ± {cv_std:.1%}")

    # Importancia de features
    feat_names = X_train.columns.tolist()
    importances = dict(sorted(
        zip(feat_names, model.feature_importances_),
        key=lambda x: x[1], reverse=True
    )[:10])

    print("  Top features:")
    for feat, imp in list(importances.items())[:5]:
        print(f"    {feat:<30} {imp:.3f}")

    # Predicción del día actual
    feat_for_pred = feat_matrix.reset_index()
    pred_hoy = predict_today(model, feat_for_pred, SNAPSHOT_FILE)
    print(f"\n  Predicción BTC mañana: {pred_hoy.get('direccion','?')} "
          f"(confianza ML: {pred_hoy.get('confianza_ml','?')}/10)")

    # Guardar metadatos del modelo
    meta = {
        "generado_en":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_train":        int(len(X_train)),
        "n_features":     int(len(feat_names)),
        "cv_accuracy":    cv_mean,
        "cv_std":         cv_std,
        "top_features":   {k: round(float(v), 4) for k, v in importances.items()},
        "target_threshold": TARGET_THRESHOLD,
        "distribucion_clases": {
            str(int(k)): int(v)
            for k, v in y_train.value_counts().items()
        },
        "prediccion_hoy": pred_hoy,
    }

    MODEL_META_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = MODEL_META_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, MODEL_META_FILE)
    print(f"  Metadatos guardados en: {MODEL_META_FILE}")

    # Guardar predicción del día
    pred_out = {
        "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fecha":       datetime.now().strftime("%Y-%m-%d"),
        **pred_hoy,
        "cv_accuracy": cv_mean,
    }
    tmp2 = PREDICTION_FILE.with_suffix(".tmp")
    tmp2.write_text(json.dumps(pred_out, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp2, PREDICTION_FILE)

    # Enriquecer daily_signals.json con la predicción ML (si existe)
    _inject_ml_into_daily_signals(pred_hoy, cv_mean)


def _inject_ml_into_daily_signals(pred: dict, cv_acc: float) -> None:
    """Agrega el bloque ml_prediccion a daily_signals.json sin sobrescribir el resto."""
    if not DAILY_SIGNALS.exists():
        return
    try:
        with open(DAILY_SIGNALS, "rb") as f:
            raw = f.read().rstrip(b"\x00")
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return

    data["ml_prediccion"] = {
        "direccion_btc_manana": pred.get("direccion", "N/A"),
        "confianza_ml":         pred.get("confianza_ml", 0),
        "probabilidades":       pred.get("probabilidades", {}),
        "cv_accuracy_modelo":   round(cv_acc * 100, 1),
        "nota": (
            "Predicción de RandomForest entrenado sobre historial macro. "
            f"CV accuracy: {cv_acc:.1%}. Usar como referencia, no como señal absoluta."
        ),
    }

    tmp = DAILY_SIGNALS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, DAILY_SIGNALS)
    print(f"  Predicción ML inyectada en: {DAILY_SIGNALS}")


if __name__ == "__main__":
    main()
