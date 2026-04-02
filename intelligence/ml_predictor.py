"""
ml_predictor.py
---------------
Modelo ML que predice la DIRECCIÓN de BTC al día siguiente
usando el historial de precios de los indicadores macro + features técnicas de BTC.

Modelo: XGBoostClassifier (con fallback a RandomForestClassifier)
  - No requiere GPU ni API externa
  - Entrena en segundos con los datos históricos disponibles
  - Se re-entrena cada vez que corre el pipeline (aprendizaje continuo)

Features por día t:
  - Variación % de cada indicador macro (btc, brent, gold, silver, dxy,
    sp500, usdcop, eurusd, nasdaq, wti)
  - Lags t-1 … t-5 de las mismas variaciones
  - Volatilidad rolling 5 días de BTC (btc_vol5)
  - Indicadores técnicos de BTC: RSI(14), MACD histogram, BB %B, BB width

Target:
  - btc_dir_next: +1 (BTC sube >0.5% al día siguiente)
                  -1 (BTC baja <-0.5%)
                   0 (lateral)

Salida:
  - data/signals/ml_model_meta.json      (métricas + importancias)
  - data/signals/ml_prediction_hoy.json  (predicción del día actual)
  - La predicción se agrega a daily_signals.json vía causal_interpreter

Uso: python -m intelligence.ml_predictor
"""

from __future__ import annotations

import json
import os
import re
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT             = Path(__file__).parent.parent
MARKET_FILE      = ROOT / "data/historical/market_history.csv"
ONCHAIN_FILE     = ROOT / "data/historical/onchain_history.csv"
FG_FILE          = ROOT / "data/historical/feargreed_history.csv"
FUNDING_FILE     = ROOT / "data/historical/funding_history.csv"
SNAPSHOT_FILE    = ROOT / "data/processed/latest_snapshot.csv"
MODEL_META_FILE  = ROOT / "data/signals/ml_model_meta.json"
PREDICTION_FILE  = ROOT / "data/signals/ml_prediction_hoy.json"
DAILY_SIGNALS    = ROOT / "data/signals/daily_signals.json"

INDICATORS = ["btc", "brent", "gold", "silver", "dxy", "sp500", "usdcop",
              "eurusd", "nasdaq", "wti"]
# NOTA: global_inflation_proxy excluido (sin ticker yfinance → datos desde nov-2025 solo)

# Métricas on-chain disponibles (se agregan al modelo si onchain_history.csv existe)
ONCHAIN_INDICATORS = [
    "onchain_active_addr",
    "onchain_tx_count",
    "onchain_hashrate",
    "onchain_mempool_size",
    "onchain_tx_volume_usd",
]

TARGET_THRESHOLD = 0.5   # % mínimo para clasificar como Alcista/Bajista
FORWARD_DAYS     = 2     # horizonte de predicción: 1 = mañana, 2 = pasado mañana (óptimo)
LAG_DAYS         = 5     # días de lags (aumentado de 2 a 5 para capturar memoria semanal)
MIN_TRAIN_ROWS   = 30    # mínimo de filas para entrenar


# ── Indicadores técnicos de BTC ───────────────────────────────────────────────

def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI clásico con EWM (Wilder smoothing)."""
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _compute_macd_hist(series: pd.Series,
                       fast: int = 12, slow: int = 26, signal: int = 9
                       ) -> pd.Series:
    """Histograma MACD (MACD line - Signal line)."""
    ema_fast   = series.ewm(span=fast,   min_periods=fast).mean()
    ema_slow   = series.ewm(span=slow,   min_periods=slow).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, min_periods=signal).mean()
    return macd_line - signal_line


def _compute_bollinger(series: pd.Series, period: int = 20):
    """Retorna (bb_pct, bb_width) — posición y amplitud de las bandas."""
    sma    = series.rolling(period).mean()
    std    = series.rolling(period).std()
    upper  = sma + 2 * std
    lower  = sma - 2 * std
    denom  = (upper - lower).replace(0, np.nan)
    bb_pct   = (series - lower) / denom          # 0 = banda inferior, 1 = superior
    bb_width = denom / sma.replace(0, np.nan)    # amplitud relativa al precio
    return bb_pct, bb_width


def _compute_stoch_rsi(series: pd.Series,
                       rsi_period: int = 14, stoch_period: int = 14) -> pd.Series:
    """Stochastic RSI: posición del RSI dentro de su propio rango histórico (0-1)."""
    rsi     = _compute_rsi(series, rsi_period)
    min_rsi = rsi.rolling(stoch_period).min()
    max_rsi = rsi.rolling(stoch_period).max()
    return (rsi - min_rsi) / (max_rsi - min_rsi).replace(0, np.nan)


def build_technical_features(df_history: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula indicadores técnicos desde los precios de cierre de BTC.

    Retorna DataFrame con columnas:
      date, btc_rsi14, btc_stoch_rsi, btc_macd_hist,
      btc_bb_pct, btc_bb_width, btc_ema_cross, btc_above_ma50
    """
    btc = df_history[df_history["indicator"] == "btc"].copy()
    if btc.empty:
        return pd.DataFrame(columns=["date"])

    btc["date"]  = pd.to_datetime(btc["timestamp"]).dt.normalize()
    btc["close"] = pd.to_numeric(btc["value"], errors="coerce")
    btc = btc.sort_values("date").drop_duplicates("date", keep="last")
    btc = btc.set_index("date")["close"]

    tech = pd.DataFrame(index=btc.index)

    # Momentum
    tech["btc_rsi14"]     = _compute_rsi(btc, 14)
    tech["btc_stoch_rsi"] = _compute_stoch_rsi(btc, 14, 14)
    tech["btc_macd_hist"] = _compute_macd_hist(btc)

    # Bandas de Bollinger
    bb_pct, bb_width      = _compute_bollinger(btc, 20)
    tech["btc_bb_pct"]    = bb_pct
    tech["btc_bb_width"]  = bb_width

    # Tendencia: EMA 9 vs EMA 21 (+1 alcista, -1 bajista)
    ema9  = btc.ewm(span=9,  min_periods=9).mean()
    ema21 = btc.ewm(span=21, min_periods=21).mean()
    tech["btc_ema_cross"] = np.sign(ema9 - ema21)

    # Contexto de mercado: ¿BTC sobre su MA50?
    ma50 = btc.rolling(50).mean()
    tech["btc_above_ma50"] = (btc > ma50).astype(float)

    return tech.reset_index()   # columna "date" restaurada


# ── Feature engineering ───────────────────────────────────────────────────────

def build_feature_matrix(df_history: pd.DataFrame) -> pd.DataFrame:
    """
    Pivotea market_history → DataFrame wide con features por día.

    Columnas:
      {ind}_chg, {ind}_chg_lag1 … {ind}_chg_lag5,
      btc_vol5,
      btc_rsi14, btc_macd_hist, btc_bb_pct, btc_bb_width

    FIX calendarios: ffill(limit=3) para alinear BTC (7d) con futuros/forex (5d).
    FIX lags: se capturan base_cols antes del loop para evitar lags de lags.
    """
    df = df_history.copy()
    df["timestamp"]  = pd.to_datetime(df["timestamp"])
    df["date"]       = df["timestamp"].dt.normalize()
    df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce")

    # Pivot: filas=fecha, columnas=indicador
    pivot = df.pivot_table(
        index="date", columns="indicator", values="change_pct", aggfunc="last"
    )

    # Mantener solo indicadores conocidos presentes
    present = [c for c in INDICATORS if c in pivot.columns]
    pivot = pivot[present].copy()
    pivot.columns = [f"{c}_chg" for c in present]

    # Forward-fill gaps de fines de semana / festivos (máx 3 días)
    pivot = pivot.ffill(limit=3)

    # Capturar columnas BASE antes de añadir lags (evita lags de lags)
    base_cols = list(pivot.columns)

    # Lags t-1 … t-LAG_DAYS
    for lag in range(1, LAG_DAYS + 1):
        for col in base_cols:
            pivot[f"{col}_lag{lag}"] = pivot[col].shift(lag)

    # Volatilidad BTC rolling 5 y 10 días
    if "btc_chg" in pivot.columns:
        pivot["btc_vol5"]  = pivot["btc_chg"].rolling(5).std()
        pivot["btc_vol10"] = pivot["btc_chg"].rolling(10).std()

    # Correlaciones dinámicas de BTC con macro (ventana 20 días)
    if "btc_chg" in pivot.columns:
        if "sp500_chg" in pivot.columns:
            pivot["corr_btc_sp500_20d"] = (
                pivot["btc_chg"].rolling(20).corr(pivot["sp500_chg"])
            )
        if "dxy_chg" in pivot.columns:
            pivot["corr_btc_dxy_20d"] = (
                pivot["btc_chg"].rolling(20).corr(pivot["dxy_chg"])
            )
        if "gold_chg" in pivot.columns:
            pivot["corr_btc_gold_20d"] = (
                pivot["btc_chg"].rolling(20).corr(pivot["gold_chg"])
            )

    # Indicadores técnicos de BTC
    tech_df = build_technical_features(df_history)
    if not tech_df.empty:
        tech_df = tech_df.set_index("date")
        pivot   = pivot.join(tech_df, how="left")
        tech_cols = [c for c in tech_df.columns if c in pivot.columns]
        pivot[tech_cols] = pivot[tech_cols].ffill(limit=3)

    # Volumen de BTC (guardado como indicador separado en market_history)
    if "btc_volume" in df_history["indicator"].values:
        vol_df = _build_volume_features(df_history)
        if not vol_df.empty:
            pivot = pivot.join(vol_df.set_index("date"), how="left")
            vol_cols = [c for c in vol_df.columns if c != "date" and c in pivot.columns]
            pivot[vol_cols] = pivot[vol_cols].ffill(limit=3)

    # Features on-chain (si onchain_history.csv existe)
    onchain_df = _build_onchain_features()
    if not onchain_df.empty:
        pivot = pivot.join(onchain_df.set_index("date"), how="left")
        oc_cols = [c for c in onchain_df.columns if c != "date" and c in pivot.columns]
        pivot[oc_cols] = pivot[oc_cols].ffill(limit=5)  # on-chain llega con 1 día de retraso

    # Features Funding Rate (si funding_history.csv existe)
    funding_df = _build_funding_features()
    if not funding_df.empty:
        pivot = pivot.join(funding_df.set_index("date"), how="left")
        fr_cols = [c for c in funding_df.columns if c != "date" and c in pivot.columns]
        pivot[fr_cols] = pivot[fr_cols].ffill(limit=3)
        # Imputar pre-2019 (antes de que existieran futuros perpetuos en Binance)
        fr_neutral = {
            "fr_mean": 0.01, "fr_max": 0.01, "fr_min": 0.01,
            "fr_annualized": 10.95, "fr_7d_mean": 0.01,
            "fr_extreme_long": 0.0, "fr_extreme_short": 0.0, "fr_change": 0.0,
            "fr_lag1": 0.01, "fr_lag3": 0.01,
        }
        for col, fill_val in fr_neutral.items():
            if col in pivot.columns:
                pivot[col] = pivot[col].fillna(fill_val)

    # Features Fear & Greed Index (si feargreed_history.csv existe)
    fg_df = _build_feargreed_features()
    if not fg_df.empty:
        pivot = pivot.join(fg_df.set_index("date"), how="left")
        fg_cols = [c for c in fg_df.columns if c != "date" and c in pivot.columns]
        pivot[fg_cols] = pivot[fg_cols].ffill(limit=3)
        # Imputar filas pre-2018 (antes de que existiera F&G) con valores neutrales.
        # Esto recupera ~600 filas del ciclo 2013-2018 sin introducir sesgo fuerte.
        fg_neutral = {
            "fg_value_norm":  0.5,   # 50/100 = neutral
            "fg_change_pct":  0.0,
            "fg_value_lag1":  0.5,
            "fg_value_lag3":  0.5,
            "fg_value_lag7":  0.5,
            "fg_extreme_fear": 0.0,
            "fg_greed_zone":   0.0,
            "fg_momentum7":    0.0,
        }
        for col, fill_val in fg_neutral.items():
            if col in pivot.columns:
                pivot[col] = pivot[col].fillna(fill_val)

    # Eliminar filas de arranque donde lags/indicadores técnicos son NaN
    pivot = pivot.dropna(subset=["btc_chg"])
    pivot = pivot.dropna()
    return pivot.reset_index()


def _build_volume_features(df_history: pd.DataFrame) -> pd.DataFrame:
    """Construye features de volumen BTC desde market_history.csv."""
    vol = df_history[df_history["indicator"] == "btc_volume"].copy()
    if vol.empty:
        return pd.DataFrame()
    vol["date"]  = pd.to_datetime(vol["timestamp"]).dt.normalize()
    vol["value"] = pd.to_numeric(vol["value"], errors="coerce")
    vol = vol.sort_values("date").drop_duplicates("date", keep="last")
    vol = vol.set_index("date")["value"].rename("btc_volume_raw")
    result = pd.DataFrame(index=vol.index)
    # Volumen relativo: cuánto mayor es el volumen vs su MA20
    ma20 = vol.rolling(20).mean()
    result["btc_vol_rel20"] = vol / ma20.replace(0, float("nan"))
    # Cambio % de volumen día a día
    result["btc_vol_chg"]   = vol.pct_change() * 100
    return result.reset_index()


def _build_funding_features() -> pd.DataFrame:
    """Carga funding_history.csv y construye features de funding rate de BTC."""
    if not FUNDING_FILE.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(FUNDING_FILE)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    df["date"]    = pd.to_datetime(df["date"]).dt.normalize()
    df["fr_mean"] = pd.to_numeric(df["fr_mean"], errors="coerce")
    df = df.sort_values("date").drop_duplicates("date", keep="last").set_index("date")

    result = pd.DataFrame(index=df.index)
    result["fr_mean"]          = df["fr_mean"]
    result["fr_max"]           = pd.to_numeric(df.get("fr_max"), errors="coerce")
    result["fr_min"]           = pd.to_numeric(df.get("fr_min"), errors="coerce")
    result["fr_annualized"]    = pd.to_numeric(df.get("fr_annualized"), errors="coerce")
    result["fr_7d_mean"]       = pd.to_numeric(df.get("fr_7d_mean"), errors="coerce")
    result["fr_extreme_long"]  = pd.to_numeric(df.get("fr_extreme_long"), errors="coerce")
    result["fr_extreme_short"] = pd.to_numeric(df.get("fr_extreme_short"), errors="coerce")
    result["fr_change"]        = pd.to_numeric(df.get("fr_change"), errors="coerce")
    # Lags: funding de 1 y 3 días atrás (señal de acumulación de posiciones)
    result["fr_lag1"]          = result["fr_mean"].shift(1)
    result["fr_lag3"]          = result["fr_mean"].shift(3)

    return result.reset_index()


def _build_feargreed_features() -> pd.DataFrame:
    """Carga feargreed_history.csv y construye features de sentimiento."""
    if not FG_FILE.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(FG_FILE)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    df["date"]     = pd.to_datetime(df["date"]).dt.normalize()
    df["fg_value"] = pd.to_numeric(df["fg_value"], errors="coerce")
    df = df.sort_values("date").drop_duplicates("date", keep="last").set_index("date")

    result = pd.DataFrame(index=df.index)
    # Valor absoluto normalizado 0-100 → 0-1
    result["fg_value_norm"] = df["fg_value"] / 100.0
    # Cambio % diario del índice
    result["fg_change_pct"] = df["fg_change_pct"]
    # Lags: señales de sentimiento de 1, 3 y 7 días atrás
    result["fg_value_lag1"] = result["fg_value_norm"].shift(1)
    result["fg_value_lag3"] = result["fg_value_norm"].shift(3)
    result["fg_value_lag7"] = result["fg_value_norm"].shift(7)
    # Zona de sentimiento: extreme fear (<25), fear (25-45), neutral (45-55), greed (55-75), extreme greed (>75)
    result["fg_extreme_fear"]  = (df["fg_value"] < 25).astype(float)
    result["fg_greed_zone"]    = (df["fg_value"] > 65).astype(float)
    # Momentum de sentimiento: cambio en 7 días (reversión a la media)
    result["fg_momentum7"]     = result["fg_value_norm"] - result["fg_value_norm"].shift(7)

    return result.reset_index()


def _build_onchain_features() -> pd.DataFrame:
    """Carga onchain_history.csv y construye features normalizadas."""
    if not ONCHAIN_FILE.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(ONCHAIN_FILE)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    df["date"]       = pd.to_datetime(df["timestamp"]).dt.normalize()
    df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce")

    present = [c for c in ONCHAIN_INDICATORS if c in df["indicator"].values]
    if not present:
        return pd.DataFrame()

    pivot = df[df["indicator"].isin(present)].pivot_table(
        index="date", columns="indicator", values="change_pct", aggfunc="last"
    )
    pivot.columns = [f"{c}_chg" for c in pivot.columns]
    # Lag 1 de cada métrica on-chain (llegan con 1 día de retraso)
    for col in list(pivot.columns):
        pivot[f"{col}_lag1"] = pivot[col].shift(1)
    pivot = pivot.ffill(limit=3)
    return pivot.reset_index()


def build_target(df_history: pd.DataFrame) -> pd.Series:
    """
    Retorna Serie BINARIA con btc_dir_next: +1 (sube) vs -1 (baja).
    Los días laterales (|chg| <= TARGET_THRESHOLD) se eliminan del entrenamiento
    asignándoles NaN → el modelo solo aprende de movimientos claros.
    """
    df = df_history.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"]      = df["timestamp"].dt.normalize()
    btc = df[df["indicator"] == "btc"].copy()
    btc = btc.sort_values("date").drop_duplicates("date", keep="last")
    btc["change_pct"] = pd.to_numeric(btc["change_pct"], errors="coerce")

    def _dir_binary(x):
        if pd.isna(x):            return np.nan
        if x >  TARGET_THRESHOLD: return 1    # Alcista
        if x < -TARGET_THRESHOLD: return -1   # Bajista
        return np.nan                          # Lateral → excluido

    # Target: dirección N días hacia adelante (FORWARD_DAYS=1 → mañana, 2 → pasado mañana)
    # Con 2 días, el ruido de corto plazo se reduce y las señales tienen más tiempo para madurar.
    # Se usa la suma acumulada de los próximos FORWARD_DAYS para capturar el movimiento neto.
    if FORWARD_DAYS == 1:
        fwd_return = btc["change_pct"].shift(-1)
    else:
        # Retorno compuesto de los próximos FORWARD_DAYS días
        fwd_return = sum(btc["change_pct"].shift(-i) for i in range(1, FORWARD_DAYS + 1))

    btc["btc_dir_next"] = fwd_return.apply(_dir_binary)
    return btc.set_index("date")["btc_dir_next"]


# ── Entrenamiento ─────────────────────────────────────────────────────────────

def train_model(X: pd.DataFrame, y: pd.Series):
    """
    Entrena XGBoostClassifier (fallback a RandomForest si XGBoost no está instalado).
    Retorna (modelo, X_alineado, y_alineado, cv_scores, nombre_modelo).
    """
    from sklearn.model_selection import TimeSeriesSplit, cross_val_score

    # Alinear X e y
    common = X.index.intersection(y.index)
    X_al   = X.loc[common].select_dtypes(include=[np.number])
    y_al   = y.loc[common].dropna()
    X_al   = X_al.loc[y_al.index]

    if len(X_al) < MIN_TRAIN_ROWS:
        raise ValueError(
            f"Solo {len(X_al)} filas de entrenamiento. Mínimo: {MIN_TRAIN_ROWS}."
        )

    tscv = TimeSeriesSplit(n_splits=5)

    # 1) Intentar XGBoost — modo BINARIO (binary:logistic)
    try:
        import xgboost as _xgb
        from xgboost import XGBClassifier
        # Binario: -1 → 0, +1 → 1
        label_map = {-1: 0, 1: 1}
        inv_label = {0: -1, 1: 1}
        y_enc     = y_al.map(label_map).astype(int)

        # ── Paso 1: entrenar con todos los features para obtener importancias
        model_full = XGBClassifier(
            n_estimators      = 500,
            max_depth         = 3,
            learning_rate     = 0.02,
            subsample         = 0.7,
            colsample_bytree  = 0.7,
            min_child_weight  = 5,
            gamma             = 0.1,
            reg_alpha         = 0.1,
            reg_lambda        = 1.5,
            objective         = "binary:logistic",
            eval_metric       = "logloss",
            random_state      = 42,
            verbosity         = 0,
        )
        model_full.fit(X_al, y_enc)

        # ── Paso 2: poda de features — conservar solo los que superen
        #           el 70% de la importancia promedio (poda más agresiva = menos sobreajuste)
        imp       = model_full.feature_importances_
        threshold = imp.mean() * 0.7
        keep_mask = imp >= threshold
        X_pruned  = X_al.loc[:, keep_mask]
        n_dropped = (~keep_mask).sum()
        print(f"  [INFO] Poda: {n_dropped} features eliminados "
              f"({keep_mask.sum()} conservados de {len(imp)})")

        # ── Paso 3: pesos por recencia (exponential decay, half-life = 730 días = 2 años)
        # Datos recientes pesan más → el modelo prioriza el régimen actual
        # half-life = 730d: dato de hace 2 años pesa ~37%, hace 4 años ~14%
        n          = len(X_pruned)
        half_life  = 730
        decay      = np.exp(-np.arange(n - 1, -1, -1) / half_life)
        weights    = (decay / decay.sum() * n).astype(float)
        recency_pct = round(weights[-1] / weights[0], 1)
        print(f"  [INFO] Recency weighting (half-life=2y): "
              f"dato reciente pesa {recency_pct}x más que el más antiguo")

        # ── Paso 4: Búsqueda de hiperparámetros con RandomizedSearchCV
        #           (sin sample_weight en búsqueda → compatibilidad sklearn>=1.4)
        N_SEARCH = 150
        param_dist = {
            "n_estimators":     [200, 300, 500, 700, 1000],
            "max_depth":        [2, 3, 4, 5],
            "learning_rate":    [0.005, 0.01, 0.02, 0.05, 0.08],
            "subsample":        [0.5, 0.6, 0.7, 0.8, 0.9],
            "colsample_bytree": [0.5, 0.6, 0.7, 0.8],
            "min_child_weight": [3, 5, 7, 10, 15],
            "gamma":            [0.0, 0.05, 0.1, 0.2, 0.3, 0.5],
            "reg_alpha":        [0.0, 0.05, 0.1, 0.2, 0.5],
            "reg_lambda":       [0.5, 1.0, 1.5, 2.0, 3.0],
        }

        # ── Búsqueda manual con barra de progreso ──────────────────────────────
        rng = np.random.RandomState(42)
        # Generar todas las combinaciones de una vez
        param_list = [
            {k: rng.choice(v).item() for k, v in param_dist.items()}
            for _ in range(N_SEARCH)
        ]

        print(f"  [INFO] Buscando hiperparámetros óptimos ({N_SEARCH} combinaciones)...")
        best_p  = param_list[0]
        best_cv = 0.0
        REPORT_EVERY = 10   # mostrar progreso cada N iteraciones

        for i, params in enumerate(param_list):
            m_test = XGBClassifier(
                **params,
                objective    = "binary:logistic",
                eval_metric  = "logloss",
                random_state = 42,
                verbosity    = 0,
            )
            score = cross_val_score(
                m_test, X_pruned, y_enc, cv=tscv, scoring="accuracy"
            ).mean()

            if score > best_cv:
                best_cv = score
                best_p  = params

            # Progreso cada REPORT_EVERY iteraciones y en la última
            if (i + 1) % REPORT_EVERY == 0 or (i + 1) == N_SEARCH:
                pct     = (i + 1) / N_SEARCH * 100
                bar_len = 20
                filled  = int(bar_len * (i + 1) / N_SEARCH)
                bar     = "█" * filled + "░" * (bar_len - filled)
                print(f"  [{bar}] {pct:5.1f}%  iter {i+1:3d}/{N_SEARCH}"
                      f"  mejor: {best_cv:.1%}"
                      f"  (depth={best_p.get('max_depth')}"
                      f" lr={best_p.get('learning_rate')}"
                      f" n={best_p.get('n_estimators')})")

        print(f"  [INFO] Mejores params → depth={best_p.get('max_depth')} "
              f"lr={best_p.get('learning_rate')} n={best_p.get('n_estimators')} "
              f"sub={best_p.get('subsample')}")
        print(f"  [INFO] Mejor CV accuracy (búsqueda): {best_cv:.1%}")

        # ── Paso 5: Fit final con mejores params + recency weights
        model = XGBClassifier(
            **best_p,
            objective    = "binary:logistic",
            eval_metric  = "logloss",
            random_state = 42,
            verbosity    = 0,
        )
        model.fit(X_pruned, y_enc, sample_weight=weights)

        # CV final con best params (sin pesos → estimación conservadora)
        cv_scores = cross_val_score(model, X_pruned, y_enc, cv=tscv, scoring="accuracy")

        # ── Paso 6: Meta-labeling — segundo modelo que aprende CUÁNDO el primero acierta
        # El meta-modelo predice si la predicción primaria es CORRECTA (1) o no (0).
        # Esto permite filtrar operaciones de baja confianza y mejorar la precisión real.
        try:
            print("  [INFO] Entrenando meta-modelo (confianza adaptativa)...")
            # Predicciones in-sample del modelo primario
            proba_primary  = model.predict_proba(X_pruned)[:, 1]
            pred_primary   = (proba_primary >= 0.5).astype(int)
            # Target del meta-modelo: 1 si acertó, 0 si falló
            meta_target    = (pred_primary == y_enc.values).astype(int)
            # Features del meta-modelo: probabilidad primaria + features más importantes
            top_imp_cols   = pd.Series(model.feature_importances_,
                                       index=X_pruned.columns).nlargest(20).index.tolist()
            X_meta         = X_pruned[top_imp_cols].copy()
            X_meta["primary_proba"]  = proba_primary
            X_meta["primary_margin"] = np.abs(proba_primary - 0.5)

            meta_model = XGBClassifier(
                n_estimators  = 200,
                max_depth     = 2,
                learning_rate = 0.05,
                subsample     = 0.7,
                objective     = "binary:logistic",
                eval_metric   = "logloss",
                random_state  = 99,
                verbosity     = 0,
            )
            meta_model.fit(X_meta, meta_target, sample_weight=weights)
            meta_cv = cross_val_score(meta_model, X_meta, meta_target, cv=tscv, scoring="accuracy")
            print(f"  [INFO] Meta-modelo CV accuracy: {meta_cv.mean():.1%} ± {meta_cv.std():.1%}")
        except Exception as em:
            meta_model  = None
            top_imp_cols = []
            print(f"  [WARN] Meta-modelo falló: {em}")

        print("  [INFO] Usando XGBoost", _xgb.__version__,
              "— clasificación BINARIA + recency + tuning + meta-labeling")
        return model, X_pruned, y_al, cv_scores, "XGBoost-Binary-Tuned", inv_label, \
               meta_model, top_imp_cols
    except Exception as e1:
        print(f"  [INFO] XGBoost no disponible ({type(e1).__name__}) — intentando LightGBM...")

    # 2) Intentar LightGBM — binario
    try:
        import lightgbm as lgb
        from lightgbm import LGBMClassifier
        label_map2 = {-1: 0, 1: 1}
        inv_label2 = {0: -1, 1: 1}
        y_enc2     = y_al.map(label_map2).astype(int)
        model = LGBMClassifier(
            n_estimators     = 500,
            max_depth        = 3,
            learning_rate    = 0.02,
            subsample        = 0.7,
            colsample_bytree = 0.7,
            random_state     = 42,
            class_weight     = "balanced",
            verbose          = -1,
        )
        cv_scores = cross_val_score(model, X_al, y_enc2, cv=tscv, scoring="accuracy")
        model.fit(X_al, y_enc2)
        print("  [INFO] Usando LightGBM", lgb.__version__, "— clasificación BINARIA")
        return model, X_al, y_al, cv_scores, "LightGBM-Binary", inv_label2
    except Exception as e2:
        print(f"  [INFO] LightGBM no disponible ({type(e2).__name__}) — usando RandomForest.")

    # 3) Fallback: RandomForest — binario (eliminar laterales de y_al)
    from sklearn.ensemble import RandomForestClassifier
    model = RandomForestClassifier(
        n_estimators     = 300,
        max_depth        = 5,
        min_samples_leaf = 3,
        random_state     = 42,
        class_weight     = "balanced",
    )
    cv_scores = cross_val_score(model, X_al, y_al, cv=tscv, scoring="accuracy")
    model.fit(X_al, y_al)
    return model, X_al, y_al, cv_scores, "RandomForest-Binary", None


# ── Predicción del día actual ─────────────────────────────────────────────────

_TECH_COLS = [
    # Indicadores técnicos
    "btc_rsi14", "btc_stoch_rsi", "btc_macd_hist",
    "btc_bb_pct", "btc_bb_width", "btc_ema_cross", "btc_above_ma50",
    # Volatilidad
    "btc_vol10",
    # Correlaciones dinámicas
    "corr_btc_sp500_20d", "corr_btc_dxy_20d", "corr_btc_gold_20d",
    # Volumen
    "btc_vol_rel20", "btc_vol_chg",
    # Funding Rate BTC (apalancamiento del mercado)
    "fr_mean", "fr_max", "fr_min", "fr_annualized",
    "fr_7d_mean", "fr_extreme_long", "fr_extreme_short",
    "fr_change", "fr_lag1", "fr_lag3",
    # Fear & Greed Index (sentimiento de mercado)
    "fg_value_norm", "fg_change_pct",
    "fg_value_lag1", "fg_value_lag3", "fg_value_lag7",
    "fg_extreme_fear", "fg_greed_zone", "fg_momentum7",
    # On-chain (cambios % y sus lags)
    "onchain_active_addr_chg", "onchain_active_addr_chg_lag1",
    "onchain_tx_count_chg",    "onchain_tx_count_chg_lag1",
    "onchain_hashrate_chg",    "onchain_hashrate_chg_lag1",
    "onchain_mempool_size_chg","onchain_mempool_size_chg_lag1",
    "onchain_tx_volume_usd_chg","onchain_tx_volume_usd_chg_lag1",
]


def predict_today(
    model,
    feature_matrix: pd.DataFrame,
    snapshot_file: Path,
    inv_label: dict | None = None,
    meta_model=None,
    meta_cols: list | None = None,
) -> dict:
    """
    Genera features del día de hoy combinando snapshot actual + últimos lags
    del historial y produce la predicción.
    Si se provee meta_model, también calcula la confianza adaptativa.
    """
    if not snapshot_file.exists():
        return {"error": "snapshot no encontrado"}

    snap = pd.read_csv(snapshot_file)
    today_changes: dict[str, float] = {}
    for _, row in snap.iterrows():
        ind = str(row.get("indicator", "")).lower()
        pct = pd.to_numeric(row.get("change_pct"), errors="coerce")
        if ind in INDICATORS and pd.notna(pct):
            today_changes[ind] = float(pct)

    # Últimas LAG_DAYS filas del historial para construir lags
    last_rows = feature_matrix.tail(LAG_DAYS).copy()

    feature_cols = [c for c in feature_matrix.columns if c != "date"]
    today_feat: dict[str, float] = {}

    for col in feature_cols:
        # Indicadores técnicos: usar el último valor conocido
        if col in _TECH_COLS:
            if col in feature_matrix.columns and len(feature_matrix) > 0:
                today_feat[col] = float(feature_matrix[col].iloc[-1])
            else:
                today_feat[col] = 0.0

        # Volatilidad rolling
        elif col == "btc_vol5":
            recent_btc = list(feature_matrix["btc_chg"].tail(4)) + \
                         [today_changes.get("btc", 0.0)]
            today_feat[col] = float(np.std(recent_btc)) if recent_btc else 0.0

        # Cambio del día actual (sin lag)
        elif col.endswith("_chg") and "_lag" not in col:
            ind = col.replace("_chg", "")
            today_feat[col] = today_changes.get(ind, 0.0)

        # Lags: _lagN → valor de N días atrás en la columna base
        else:
            m = re.search(r"_lag(\d+)$", col)
            if m:
                lag_n = int(m.group(1))
                base  = col[:m.start()]          # ej. "btc_chg"
                if base in last_rows.columns and len(last_rows) >= lag_n:
                    today_feat[col] = float(last_rows[base].iloc[-lag_n])
                else:
                    today_feat[col] = 0.0
            else:
                today_feat[col] = 0.0

    X_today = pd.DataFrame([today_feat])[feature_cols]
    X_today = X_today.select_dtypes(include=[np.number])

    try:
        proba = model.predict_proba(X_today)[0]
        pred_raw = model.predict(X_today)[0]

        # Descodificar etiqueta XGBoost (0→-1, 1→0, 2→1) si aplica
        if inv_label is not None:
            pred     = inv_label.get(int(pred_raw), int(pred_raw))
            classes  = [inv_label.get(int(c), int(c)) for c in model.classes_]
        else:
            pred    = int(pred_raw)
            classes = [int(c) for c in model.classes_]

        proba_dict = {str(c): round(float(p), 4) for c, p in zip(classes, proba)}

    except Exception as e:
        return {"error": str(e)}

    label_map = {1: "Alcista", -1: "Bajista", 0: "Lateral"}
    # Confianza binaria: escalar 50%-100% → 1-10 (50% = azar = 1, 100% = certeza = 10)
    prob_max  = max(proba)
    confianza = max(1, round((prob_max - 0.5) / 0.5 * 10))

    result = {
        "direccion":      label_map.get(pred, str(pred)),
        "valor_pred":     pred,
        "probabilidades": proba_dict,
        "confianza_ml":   confianza,
    }

    # Meta-labeling: estimar probabilidad de que la predicción primaria sea correcta
    if meta_model is not None and meta_cols:
        try:
            X_meta_today = {}
            # Llenar los features normales del meta-modelo
            for col in meta_cols:
                if col in X_today.columns:
                    X_meta_today[col] = float(X_today[col].iloc[0])
                else:
                    X_meta_today[col] = 0.0
            # Agregar outputs del modelo primario (siempre explícito, fuera del loop)
            X_meta_today["primary_proba"]  = float(prob_max if pred == 1 else (1 - prob_max))
            X_meta_today["primary_margin"] = float(abs(prob_max - 0.5))
            all_meta_cols = meta_cols + ["primary_proba", "primary_margin"]
            X_meta_df    = pd.DataFrame([X_meta_today])[all_meta_cols]
            meta_proba   = meta_model.predict_proba(X_meta_df)[0][1]
            # Confianza combinada: promedio ponderado de modelo primario y meta-modelo
            combined     = 0.5 * prob_max + 0.5 * meta_proba
            meta_conf    = max(1, round((combined - 0.5) / 0.5 * 10))
            result["meta_confianza"]      = meta_conf
            result["meta_prob_correcta"]  = round(float(meta_proba), 4)
        except Exception:
            pass

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
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
    dist = target.dropna().value_counts().to_dict()
    print(f"  Distribución target (binaria): Alcista={int(dist.get(1,0))}  "
          f"Bajista={int(dist.get(-1,0))}  "
          f"Lateral excluido={int((target==0).sum())}")

    # Entrenar
    result     = train_model(feat_matrix, target)
    # Desempaquetar — puede venir con o sin meta-modelo
    if len(result) == 8:
        model, X_train, y_train, cv_scores, model_name, inv_label, meta_model, meta_cols = result
    else:
        model, X_train, y_train, cv_scores, model_name, inv_label = result
        meta_model, meta_cols = None, []

    cv_mean = round(float(cv_scores.mean()), 4)
    cv_std  = round(float(cv_scores.std()),  4)
    print(f"Entrenando {model_name}...")
    print(f"  CV Accuracy (TimeSeriesSplit-5): {cv_mean:.1%} ± {cv_std:.1%}")
    print(f"  (baseline aleatorio binario = 50.0%)")

    # Importancia de features
    feat_names  = X_train.columns.tolist()
    importances = dict(sorted(
        zip(feat_names, model.feature_importances_),
        key=lambda x: x[1], reverse=True
    )[:10])

    print("  Top features:")
    for feat, imp in list(importances.items())[:5]:
        print(f"    {feat:<35} {imp:.3f}")

    # Predicción del día actual — usar solo los features podados
    feat_for_pred = feat_matrix[X_train.columns].reset_index()
    pred_hoy = predict_today(model, feat_for_pred, SNAPSHOT_FILE, inv_label,
                             meta_model=meta_model, meta_cols=meta_cols)
    horizonte = "mañana" if FORWARD_DAYS == 1 else f"en {FORWARD_DAYS} días"
    print(f"\n  Predicción BTC {horizonte}: {pred_hoy.get('direccion','?')} "
          f"(confianza ML: {pred_hoy.get('confianza_ml','?')}/10)"
          + (f"  [meta: {pred_hoy.get('meta_confianza','?')}/10]"
             if pred_hoy.get('meta_confianza') else ""))

    # Guardar metadatos del modelo
    meta = {
        "generado_en":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "modelo":         model_name,
        "lag_days":       LAG_DAYS,
        "forward_days":   FORWARD_DAYS,
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
        "modelo":      model_name,
    }
    tmp2 = PREDICTION_FILE.with_suffix(".tmp")
    tmp2.write_text(json.dumps(pred_out, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp2, PREDICTION_FILE)

    # Enriquecer daily_signals.json con la predicción ML (si existe)
    _inject_ml_into_daily_signals(pred_hoy, cv_mean, model_name)


def _inject_ml_into_daily_signals(pred: dict, cv_acc: float,
                                   model_name: str = "ML") -> None:
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
        "modelo":               model_name,
        "nota": (
            f"Predicción BINARIA de {model_name} (Alcista vs Bajista). "
            f"Entrenado con macro + técnicos + on-chain + volumen BTC. "
            f"CV accuracy: {cv_acc:.1%} (baseline aleatorio = 50%). "
            f"Usar como referencia, no como señal absoluta."
        ),
    }

    tmp = DAILY_SIGNALS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, DAILY_SIGNALS)
    print(f"  Predicción ML inyectada en: {DAILY_SIGNALS}")


if __name__ == "__main__":
    main()
