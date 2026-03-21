import subprocess
import sys
from datetime import datetime

steps = [
    "scripts.backfill_history",         # rellena histórico de indicadores nuevos
    "scripts.market_collector",
    "scripts.processor",
    "scripts.market_signals",
    "scripts.macro_interpreter",
    "scripts.market_regime",
    "intelligence.news_classifier",     # clasifica noticias/reportes por categoría temática
    "intelligence.signals_engine",      # genera 5 señales compuestas (reglas determinísticas)
    "intelligence.causal_interpreter",  # genera interpretación narrativa → daily_signals.json
    "scripts.market_report",
    "scripts.email_report",
    "scripts.whatsapp_report",
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