"""
Clasifica texto (titulares o reportes) por categoria tematica
y asigna un peso 1/2/3.

Categorias:
  geopolitica, petroleo, inflacion, tasas, recesion,
  dolar, cripto, apetito_riesgo, colombia

Pesos:
  1 = senal debil / mencion periferica
  2 = senal moderada / mencion directa
  3 = senal fuerte / shock o evento de alta relevancia

Como modulo del pipeline: lee los archivos de senales y reportes disponibles,
clasifica su contenido y guarda data/signals/news_weights.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── Reglas por categoria: (patron regex, peso) ────────────────────────────────
_RULES: dict[str, list[tuple[str, int]]] = {
    "geopolitica": [
        (r"\b(guerra|war|conflict|sancion|sanction|ataque|attack|invasion|nato|otan|misil|missile|bomba|bomb)\b", 3),
        (r"\b(tension|diplomatic|geopolit|embargo|coup|golpe|bloqueo)\b", 2),
        (r"\b(israel|iran|ukraine|ucrania|russia|rusia|china|taiwan|corea|korea)\b", 2),
        (r"\b(negociac|acuerdo.?paz|peace|ceasefire|tregua|tratado)\b", 1),
    ],
    "petroleo": [
        (r"\b(opec\+?|opep|brent|wti|crude|petróleo|barrel|barril|oil.?price|precio.?petróleo)\b", 3),
        (r"\b(produccion.?petróleo|oil.?production|energy.?crisis|crisis.?energe|shale)\b", 3),
        (r"\b(natural.?gas|lng|gasoducto|pipeline|refinería|refinery)\b", 2),
        (r"\b(oil|petróleo|energy|energía)\b", 1),
    ],
    "inflacion": [
        (r"\b(cpi|pce|ipc|inflation|inflación|deflación|deflation|core.?inflation|subyacente|hyperinflation)\b", 3),
        (r"\b(precios.?consumidor|consumer.?price|índice.?precio|price.?index)\b", 3),
        (r"\b(salario|wage|wage.?growth|cost.?push|demand.?pull|stagflation|estanflación)\b", 2),
        (r"\b(precio|price|cost|costo|alza|subida|sube)\b", 1),
    ],
    "tasas": [
        (r"\b(fed|federal.?reserve|reserva.?federal|banrep|banco.?central|ecb|bce|boj|rba)\b", 3),
        (r"\b(interest.?rate|tasa.?interes|rate.?hike|rate.?cut|recorte|alza.?tasa|pivot|pausa)\b", 3),
        (r"\b(treasury|bono|bond|yield|rendimiento|fomc|dot.?plot|hawkish|dovish)\b", 2),
        (r"\b(monetar|política.?monetaria|monetary.?policy|quantitative|qe|qt)\b", 2),
    ],
    "recesion": [
        (r"\b(recession|recesión|contraction|contracción|gdp.?fall|pib.?cae|double.?dip)\b", 3),
        (r"\b(desempleo|unemployment|layoff|despido|jobless|job.?loss)\b", 2),
        (r"\b(slowdown|desaceleración|weak.?growth|crecimiento.?débil|stagnation)\b", 2),
        (r"\b(pmi|ism|manufacturing|manufactura|industrial.?output)\b", 1),
    ],
    "dolar": [
        (r"\b(dxy|dollar.?index|índice.?dólar|dólar.?fuerte|strong.?dollar|dollar.?surge|dollar.?rally)\b", 3),
        (r"\b(dólar|dollar|usd|forex|fx|divisa|currency|reserve.?currency)\b", 2),
        (r"\b(devaluación|devaluation|revaluación|revaluation|parity|paridad|debase)\b", 2),
        (r"\b(exchange.?rate|tipo.?cambio|tasa.?cambio|moneda)\b", 1),
    ],
    "cripto": [
        (r"\b(bitcoin|btc|ethereum|eth|crypto|criptomoneda|blockchain|halving|etf.?bitcoin)\b", 3),
        (r"\b(altcoin|defi|nft|web3|stablecoin|tether|usdt|usdc|cbdc)\b", 2),
        (r"\b(binance|coinbase|exchange.?cripto|crypto.?regulation|regulación.?cripto)\b", 2),
        (r"\b(digital.?asset|activo.?digital|token)\b", 1),
    ],
    "apetito_riesgo": [
        (r"\b(risk.?off|risk.?on|flight.?to.?quality|safe.?haven|refugio.?valor|fuga.?calidad)\b", 3),
        (r"\b(volatility|volatilidad|vix|fear|pánico|panic|crash|desplome)\b", 3),
        (r"\b(selloff|sell.?off|rally|risk.?appetite|apetito.?riesgo|capitulación)\b", 2),
        (r"\b(equities|acciones|stocks|bolsa|equity|mercado.?accion)\b", 1),
    ],
    "colombia": [
        (r"\b(colombia|colombi|gustavo.?petro|banrep|banco.?república|minhacienda)\b", 3),
        (r"\b(cop|peso.?colombiano|usdcop|tasa.?rep|ocad|fedesarrollo|dane)\b", 3),
        (r"\b(bogotá|medellín|economía.?colombiana|colombia.?economy|petróleo.?colombia)\b", 2),
        (r"\b(ecopetrol|bancolombia|grupo.?sura|confis)\b", 2),
    ],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def classify(text: str) -> dict[str, int]:
    """
    Clasifica un texto y retorna {categoria: peso_maximo}.
    Solo incluye categorias detectadas (peso > 0).
    """
    t = text.lower()
    result: dict[str, int] = {}
    for category, rules in _RULES.items():
        best = 0
        for pattern, weight in rules:
            if re.search(pattern, t):
                best = max(best, weight)
        if best > 0:
            result[category] = best
    return result


def classify_many(texts: list[str]) -> dict[str, int]:
    """
    Agrega pesos de multiples textos: toma el maximo por categoria
    para no inflar scores por repeticion.
    """
    agg: dict[str, int] = {}
    for t in texts:
        for cat, w in classify(t).items():
            agg[cat] = max(agg.get(cat, 0), w)
    return agg


def _read_file_lines(path: Path) -> list[str]:
    if path.exists():
        try:
            return path.read_text(encoding="utf-8").splitlines()
        except Exception:
            pass
    return []


# ── Main ──────────────────────────────────────────────────────────────────────

def run_classification() -> dict[str, int]:
    """
    Lee archivos de senales y reportes disponibles, clasifica su contenido
    y retorna los pesos tematicos agregados.
    """
    sources: list[str] = []
    for rel_path in [
        "data/signals/latest_signals.txt",
        "data/signals/macro_report.txt",
        "data/signals/market_regime.txt",
        "reports/daily_report.txt",
    ]:
        lines = _read_file_lines(ROOT / rel_path)
        sources.extend(lines)

    if not sources:
        print("  [news_classifier] Sin texto disponible para clasificar.")
        return {}

    weights = classify_many(sources)
    print(f"  [news_classifier] Pesos tematicos detectados: {weights}")
    return weights


def main():
    print("Clasificando noticias y reportes por categoria tematica...")
    weights = run_classification()

    output = ROOT / "data/signals/news_weights.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(weights, f, indent=2, ensure_ascii=False)

    print(f"  Pesos guardados en {output}")


if __name__ == "__main__":
    main()
