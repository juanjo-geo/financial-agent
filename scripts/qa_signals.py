"""
QA completo del sistema de senales — 4 escenarios de prueba.

Llama directamente a las funciones de signals_engine con datos simulados
y verifica las senales esperadas sin tocar archivos de produccion.
"""

from __future__ import annotations

from intelligence.signals_engine import (
    compute_conviccion,
    compute_presion_cop,
    compute_presion_inflacionaria,
    compute_riesgo_macro,
    compute_sesgo_mercado,
)

# ── Utilidades de reporte ─────────────────────────────────────────────────────

PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "[INFO]"

results: list[dict] = []


def check(label: str, actual, expected_in, scenario: str) -> bool:
    """
    Verifica que `actual` este en `expected_in` (lista de valores validos).
    Imprime resultado y acumula para el resumen final.
    """
    if isinstance(expected_in, str):
        expected_in = [expected_in]
    ok = actual in expected_in
    icon = PASS if ok else FAIL
    exp  = " o ".join(expected_in) if len(expected_in) > 1 else expected_in[0]
    print(f"  {icon}  {label:<40}  esperado={exp:<20}  obtenido={actual}")
    results.append({"scenario": scenario, "label": label, "ok": ok,
                    "expected": exp, "actual": str(actual)})
    return ok


def run_scenario(
    name: str,
    changes: dict[str, float],
    nw: dict[str, int],
    assertions: list[tuple],   # (label, field, expected)
) -> None:
    SEP = "-" * 70
    print(f"\n{'=' * 70}")
    print(f"ESCENARIO: {name}")
    print(f"Datos: {', '.join(f'{k.upper()} {v:+.1f}%' for k, v in changes.items())}")
    print(SEP)

    # Calcular todas las senales
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

    senales = {
        "riesgo_macro":           riesgo,
        "sesgo_mercado":          sesgo,
        "presion_inflacionaria":  inflacion,
        "presion_cop":            cop,
        "conviccion":             conviccion,
    }

    print(f"  {INFO}  Senales generadas:")
    print(f"         riesgo_macro           = {riesgo:<20}  (score={riesgo_score:+.2f})")
    print(f"         sesgo_mercado          = {sesgo:<20}  "
          f"(risk_on={sesgo_detail['risk_on']:.1f} / risk_off={sesgo_detail['risk_off']:.1f})")
    print(f"         presion_inflacionaria  = {inflacion:<20}  (score={inflacion_score:+.2f})")
    print(f"         presion_cop            = {cop:<20}  (score={cop_score:+.2f})")
    print(f"         conviccion             = {conviccion}/10  ({conv_razon})")
    print(SEP)

    all_ok = True
    for label, field, expected in assertions:
        actual = senales.get(field)
        ok = check(label, actual, expected, name)
        all_ok = all_ok and ok

    status = "TODOS LOS CHECKS PASARON" if all_ok else "ALGUNOS CHECKS FALLARON"
    print(f"\n  >>> {status}")


# ── ESCENARIO 1: RISK-OFF ─────────────────────────────────────────────────────

run_scenario(
    name="RISK-OFF  (BTC -5%, SP500 -3%, DXY +2%, Brent -2%)",
    changes={"btc": -5.0, "sp500": -3.0, "dxy": 2.0, "brent": -2.0},
    nw={},
    assertions=[
        ("sesgo_mercado = Risk-off",        "sesgo_mercado",  "Risk-off"),
        ("riesgo_macro  = Alto o Medio",    "riesgo_macro",   ["Alto", "Medio"]),
        ("presion_cop   = Alcista USD/COP", "presion_cop",    "Alcista USD/COP"),
    ],
)

# ── ESCENARIO 2: RISK-ON ──────────────────────────────────────────────────────

run_scenario(
    name="RISK-ON   (BTC +5%, SP500 +2%, DXY -1%, Brent +1%)",
    changes={"btc": 5.0, "sp500": 2.0, "dxy": -1.0, "brent": 1.0},
    nw={},
    assertions=[
        ("sesgo_mercado = Risk-on",      "sesgo_mercado", "Risk-on"),
        ("riesgo_macro  = Bajo",         "riesgo_macro",  "Bajo"),
    ],
)

# ── ESCENARIO 3: MIXTO ────────────────────────────────────────────────────────

run_scenario(
    name="MIXTO     (BTC +3%, Brent +4%, DXY +1%, SP500 -1%)",
    changes={"btc": 3.0, "brent": 4.0, "dxy": 1.0, "sp500": -1.0},
    nw={},
    assertions=[
        ("sesgo_mercado = Mixto",  "sesgo_mercado", "Mixto"),
    ],
)

# ── ESCENARIO 4: DATOS FALTANTES ──────────────────────────────────────────────

print(f"\n{'=' * 70}")
print("ESCENARIO: DATOS FALTANTES  (falta USDCOP y SP500)")
print("-" * 70)

changes_partial = {"btc": -1.5, "brent": 1.0, "dxy": 0.5, "gold": 0.8}
nw_empty: dict[str, int] = {}

try:
    riesgo,    riesgo_score,    _ = compute_riesgo_macro(changes_partial, nw_empty)
    sesgo,     sesgo_detail       = compute_sesgo_mercado(changes_partial, nw_empty)
    inflacion, inflacion_score, _ = compute_presion_inflacionaria(changes_partial, nw_empty)
    cop,       cop_score,       _ = compute_presion_cop(changes_partial, nw_empty)
    scores = {"riesgo_score": riesgo_score, "inflacion_score": inflacion_score, "cop_score": cop_score}
    conviccion, conv_razon = compute_conviccion(riesgo, sesgo, inflacion, cop, changes_partial, nw_empty, scores)

    senales_partial = {
        "riesgo_macro":          riesgo,
        "sesgo_mercado":         sesgo,
        "presion_inflacionaria": inflacion,
        "presion_cop":           cop,
        "conviccion":            conviccion,
    }

    print(f"  {INFO}  Sistema no fallo con datos parciales")
    print(f"  {INFO}  Senales generadas:")
    print(f"         riesgo_macro           = {riesgo}")
    print(f"         sesgo_mercado          = {sesgo}")
    print(f"         presion_inflacionaria  = {inflacion}")
    print(f"         presion_cop            = {cop}  (sin USDCOP ni SP500 -> score basado en DXY)")
    print(f"         conviccion             = {conviccion}/10  ({conv_razon})")
    print("-" * 70)

    # Referencia: conviccion con dataset completo (mismo escenario + sp500 -2%)
    full_changes = dict(changes_partial)
    full_changes.update({"sp500": -2.0, "usdcop": 1.5})
    r2, rs2, _ = compute_riesgo_macro(full_changes, nw_empty)
    s2, sd2    = compute_sesgo_mercado(full_changes, nw_empty)
    i2, is2, _ = compute_presion_inflacionaria(full_changes, nw_empty)
    c2, cs2, _ = compute_presion_cop(full_changes, nw_empty)
    sc2        = {"riesgo_score": rs2, "inflacion_score": is2, "cop_score": cs2}
    conv2, _   = compute_conviccion(r2, s2, i2, c2, full_changes, nw_empty, sc2)

    print(f"  {INFO}  Referencia con dataset completo (+ SP500 -2%, USDCOP +1.5%):")
    print(f"         conviccion completo    = {conv2}/10")
    print("-" * 70)

    ok_no_crash = True
    ok_partial  = all(v is not None for v in senales_partial.values())
    ok_conv_le  = conviccion <= conv2   # conviccion parcial <= conviccion completa

    label1 = "Sistema no falla con datos faltantes"
    label2 = "Todas las senales tienen valor"
    label3 = f"Conviccion parcial ({conviccion}) <= completo ({conv2})"

    for lbl, ok, exp, act in [
        (label1, ok_no_crash, "True", "True"),
        (label2, ok_partial,  "True", str(ok_partial)),
        (label3, ok_conv_le,  "True", str(ok_conv_le)),
    ]:
        icon = PASS if ok else FAIL
        print(f"  {icon}  {lbl:<60}  {act}")
        results.append({"scenario": "DATOS FALTANTES", "label": lbl, "ok": ok,
                        "expected": exp, "actual": act})

    all_ok = ok_no_crash and ok_partial and ok_conv_le
    print(f"\n  >>> {'TODOS LOS CHECKS PASARON' if all_ok else 'ALGUNOS CHECKS FALLARON'}")

except Exception as exc:
    print(f"  {FAIL}  EXCEPCION NO ESPERADA: {exc}")
    results.append({"scenario": "DATOS FALTANTES", "label": "Sin excepcion",
                    "ok": False, "expected": "no crash", "actual": str(exc)})

# ── RESUMEN FINAL ─────────────────────────────────────────────────────────────

print(f"\n{'=' * 70}")
print("RESUMEN QA")
print("=" * 70)

total   = len(results)
passed  = sum(1 for r in results if r["ok"])
failed  = total - passed

for r in results:
    icon = PASS if r["ok"] else FAIL
    print(f"  {icon}  [{r['scenario'][:30]:<30}]  {r['label']}")

print("-" * 70)
print(f"  Total: {total}  |  Pasaron: {passed}  |  Fallaron: {failed}")
if failed == 0:
    print("  RESULTADO FINAL: QA COMPLETO — TODOS LOS CHECKS PASARON")
else:
    print(f"  RESULTADO FINAL: QA CON {failed} FALLO(S)")
print("=" * 70)
