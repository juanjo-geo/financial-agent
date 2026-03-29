import subprocess
import sys
from datetime import datetime

steps = [
    "intelligence.evaluator",           # evalúa predicciones de ayer vs actuals de hoy
    "scripts.backfill_history",         # rellena histórico de indicadores nuevos
    "scripts.market_collector",
    "scripts.processor",
    "scripts.market_signals",
    "scripts.macro_interpreter",
    "scripts.market_regime",
    "intelligence.backfill_signals_history",  # rellena historial de señales si < 7 filas
    "intelligence.news_classifier",     # clasifica noticias/reportes por categoría temática
    "intelligence.signals_engine",      # genera 5 señales compuestas (reglas determinísticas)
    "intelligence.causal_interpreter",        # genera interpretación narrativa → daily_signals.json
    "intelligence.regime_change_detector",    # detecta cambio de régimen → regime_change.json
    "intelligence.regime_classifier",         # clasifica régimen v2 (INFLACIONARIO/RISK-ON/CRISIS/LATERAL)
    "intelligence.correlation_tracker",       # correlaciones dinámicas + detección de ruptura
    "intelligence.composite_signals",         # señales compuestas entre pares de activos
    "intelligence.market_score",              # score de inteligencia de mercado (0-100)
    "intelligence.asset_ranker",              # rankea activos por conviccion + regimen
    "intelligence.confidence_calibrator",     # calibra factores por banda de confianza
    "intelligence.rules_optimizer",           # optimiza pesos trend/momentum/signals
    "intelligence.predictor_24h",             # predicción determinística 24h por indicador
    "scripts.market_report",                  # prepara report_context.json para Claude (Cowork)
    # scripts.email_report y scripts.whatsapp_report son ejecutados por Claude
    # via tarea programada en Cowork (claude-daily-report) — no requieren API key
]


def run_step(module):
    print("\n---------------------------------")
    print(f"Ejecutando {module}")
    print("---------------------------------")

    result = subprocess.run(
        [sys.executable, "-m", module],
        capture_output=True,
        text=True
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print("ERROR:")
        print(result.stderr)

    if result.returncode != 0:
        print(f"El módulo {module} terminó con código {result.returncode}")


def main():
    print("\n====================================")
    print("FINANCIAL AGENT DAILY PIPELINE")
    print("====================================")
    print("Python usado:", sys.executable)
    print("Inicio:", datetime.now())

    for step in steps:
        run_step(step)

    print("\n====================================")
    print("PIPELINE COMPLETADO")
    print("Fin:", datetime.now())
    print("====================================")


if __name__ == "__main__":
    main()