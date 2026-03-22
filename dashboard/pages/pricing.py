"""
Página pública de planes y precios del Agente Financiero Autónomo.
Accesible sin autenticación.
"""

import streamlit as st

CONTACT_EMAIL = "jjgrillom98@gmail.com"

_PRICING_CSS = """
<style>
.pricing-page { max-width: 860px; margin: 0 auto; padding: 32px 16px; }
.pricing-hero { text-align: center; padding: 48px 0 40px; }
.pricing-hero h1 {
    font-size: 2.4rem; font-weight: 800; color: #1B2A4A;
    letter-spacing: -1px; margin-bottom: 12px;
}
.pricing-hero p { font-size: 1.05rem; color: #5A6A7E; max-width: 520px; margin: 0 auto; }

.pricing-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 24px;
    margin: 40px 0;
}
@media (max-width: 640px) { .pricing-grid { grid-template-columns: 1fr; } }

.plan-card {
    background: #FFFFFF; border-radius: 16px;
    padding: 36px 32px; border: 2px solid #E8EDF2;
    display: flex; flex-direction: column;
}
.plan-card.featured {
    border-color: #00C896;
    box-shadow: 0 8px 40px rgba(0,200,150,0.15);
}
.plan-badge {
    display: inline-block; background: #00C896; color: #fff;
    font-size: 0.65rem; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; padding: 3px 12px; border-radius: 20px;
    margin-bottom: 16px;
}
.plan-name { font-size: 1.4rem; font-weight: 800; color: #1B2A4A; margin-bottom: 6px; }
.plan-price {
    font-size: 2.4rem; font-weight: 800; color: #1B2A4A;
    margin-bottom: 4px; letter-spacing: -1px;
}
.plan-price span { font-size: 1rem; font-weight: 400; color: #8A9BB0; }
.plan-desc { font-size: 0.88rem; color: #5A6A7E; margin-bottom: 24px; min-height: 40px; }

.plan-features { list-style: none; padding: 0; margin: 0 0 32px; flex: 1; }
.plan-features li {
    font-size: 0.88rem; color: #3A4A5E; padding: 7px 0;
    border-bottom: 1px solid #F0F4F8; display: flex; align-items: flex-start; gap: 8px;
}
.plan-features li:last-child { border-bottom: none; }
.feat-check { color: #00C896; font-weight: 700; flex-shrink: 0; }
.feat-check.basic { color: #8A9BB0; }

.plan-cta {
    display: block; text-align: center;
    padding: 13px 24px; border-radius: 10px;
    font-size: 0.9rem; font-weight: 700; text-decoration: none;
    cursor: pointer; border: none; width: 100%;
}
.plan-cta.free {
    background: #F0F4F8; color: #1B2A4A;
}
.plan-cta.premium {
    background: linear-gradient(135deg, #00C896, #00875A);
    color: #fff; box-shadow: 0 4px 16px rgba(0,200,150,0.35);
}
.plan-cta.premium:hover { box-shadow: 0 6px 20px rgba(0,200,150,0.45); }

.pricing-faq { margin-top: 48px; }
.pricing-faq h2 {
    font-size: 1.3rem; font-weight: 800; color: #1B2A4A;
    margin-bottom: 24px; text-align: center;
}
.faq-item { margin-bottom: 20px; }
.faq-q { font-size: 0.95rem; font-weight: 700; color: #1B2A4A; margin-bottom: 6px; }
.faq-a { font-size: 0.88rem; color: #5A6A7E; line-height: 1.6; }

.pricing-footer {
    text-align: center; padding: 40px 0 20px;
    font-size: 0.82rem; color: #8A9BB0;
}
</style>
"""

_BASIC_FEATURES = [
    "Precios en tiempo real (5 activos)",
    "Variación histórica 7d / 30d",
    "Titulares recientes por indicador",
    "Gráficas históricas de precios",
    "Reporte diario análisis IA",
]

_PREMIUM_FEATURES = [
    "Todo lo incluido en el Plan Básico",
    "Señales del Agente (sesgo, riesgo, convicción)",
    "Detector de cambio de régimen (gauge 0-100)",
    "Señales compuestas entre activos (9 reglas)",
    "Correlaciones dinámicas + detección de ruptura",
    "Market Intelligence Score (0-100)",
    "Ranking de activos por convicción y régimen",
    "Proyecciones 24h determinísticas por activo",
    "Precisión histórica del agente (ex-post)",
    "Histórico de señales — últimos 30 días",
    "Alertas inteligentes en tiempo real",
]

_FAQS = [
    (
        "¿Qué activos cubre el agente?",
        "El agente monitorea Brent (petróleo), Bitcoin, DXY (dólar), USD/COP y Oro de forma predeterminada. "
        "El plan puede configurarse para incluir más activos según necesidad.",
    ),
    (
        "¿Cómo recibo las alertas?",
        "Las alertas del plan premium se envían por email y WhatsApp cuando algún activo supera "
        "el umbral configurado, junto con el análisis de señales del momento.",
    ),
    (
        "¿Cada cuánto se actualiza la información?",
        "El pipeline corre automáticamente cada mañana. Además puedes forzar una actualización "
        "manual desde el dashboard en cualquier momento.",
    ),
    (
        "¿Cómo accedo al contenido premium?",
        "Una vez que contratas el plan, recibes una contraseña de acceso que introduces directamente "
        "en el dashboard para desbloquear todas las secciones premium.",
    ),
]


def main():
    st.markdown(_PRICING_CSS, unsafe_allow_html=True)

    st.markdown("""
<div class="pricing-page">
  <div class="pricing-hero">
    <h1>Planes y Precios</h1>
    <p>Inteligencia financiera automatizada, desde gratis hasta análisis profesional.</p>
  </div>
""", unsafe_allow_html=True)

    # Plan cards
    basic_li = "".join(
        f'<li><span class="feat-check basic">✓</span>{f}</li>' for f in _BASIC_FEATURES
    )
    premium_li = "".join(
        f'<li><span class="feat-check">✓</span>{f}</li>' for f in _PREMIUM_FEATURES
    )

    st.markdown(f"""
<div class="pricing-grid">
  <!-- Plan Básico -->
  <div class="plan-card">
    <div class="plan-name">Plan Básico</div>
    <div class="plan-price">Gratis <span>/ siempre</span></div>
    <div class="plan-desc">Monitoreo esencial de mercados y reporte diario.</div>
    <ul class="plan-features">{basic_li}</ul>
    <a href="/" class="plan-cta free">Acceder al dashboard →</a>
  </div>
  <!-- Plan Premium -->
  <div class="plan-card featured">
    <span class="plan-badge">Recomendado</span>
    <div class="plan-name">Plan Premium</div>
    <div class="plan-price">$29 <span>USD / mes</span></div>
    <div class="plan-desc">Señales avanzadas, predicciones y alertas inteligentes.</div>
    <ul class="plan-features">{premium_li}</ul>
    <a href="mailto:{CONTACT_EMAIL}?subject=Acceso%20Premium%20-%20Agente%20Financiero&body=Hola%2C%20estoy%20interesado%20en%20el%20Plan%20Premium%20del%20Agente%20Financiero%20Aut%C3%B3nomo."
       class="plan-cta premium">Contactar para suscribirse →</a>
  </div>
</div>
""", unsafe_allow_html=True)

    # FAQ
    faq_html = ""
    for q, a in _FAQS:
        faq_html += f'<div class="faq-item"><div class="faq-q">{q}</div><div class="faq-a">{a}</div></div>'

    st.markdown(f"""
<div class="pricing-faq">
  <h2>Preguntas frecuentes</h2>
  {faq_html}
</div>
<div class="pricing-footer">
  Para consultas escríbenos a
  <a href="mailto:{CONTACT_EMAIL}" style="color:#00C896;text-decoration:none">{CONTACT_EMAIL}</a>
</div>
</div>
""", unsafe_allow_html=True)


main()
