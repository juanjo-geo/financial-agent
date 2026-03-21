import json
import os
import re
from pathlib import Path
import streamlit as st

# ── Rutas ─────────────────────────────────────────────────────────────────────
ROOT          = Path(__file__).parent.parent.parent
CONFIG_FILE   = ROOT / "config.json"
WORKFLOW_FILE = ROOT / ".github" / "workflows" / "daily_pipeline.yml"

DEFAULTS = {
    "send_hour_utc":     12,
    "email_enabled":     True,
    "email_to":          "",
    "whatsapp_enabled":  True,
    "whatsapp_to":       "",
    "alerts_enabled":    True,
    "alert_threshold":   4.0,
    "active_indicators": ["brent", "btc", "dxy", "usdcop", "gold"],
}

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULTS, **data}
        except Exception:
            pass
    return dict(DEFAULTS)

def save_config(cfg: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def update_workflow_cron(hora_utc: int, hora_colombia: int) -> bool:
    """Reemplaza el horario cron en daily_pipeline.yml con la nueva hora UTC."""
    if not WORKFLOW_FILE.exists():
        return False
    try:
        content = WORKFLOW_FILE.read_text(encoding="utf-8")
        new_line = (
            f'    - cron: "0 {hora_utc} * * *"'
            f"   # {hora_utc:02d}:00 UTC = {hora_colombia:02d}:00 Colombia"
        )
        content = re.sub(r'    - cron: ".*".*', new_line, content)
        WORKFLOW_FILE.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False

# ── Catálogo de indicadores ───────────────────────────────────────────────────
MAX_ACTIVE = 5

CATALOG_GROUPS = {
    "Commodities": [
        ("brent",  "Brent",           "BZ=F"),
        ("gold",   "Oro (XAU/USD)",   "GC=F"),
        ("wti",    "WTI",             "CL=F"),
        ("silver", "Plata (XAG/USD)", "SI=F"),
        ("copper", "Cobre",           "HG=F"),
        ("natgas", "Gas Natural",     "NG=F"),
    ],
    "Crypto": [
        ("btc",    "Bitcoin (BTC)",   "BTC-USD"),
    ],
    "Divisas": [
        ("dxy",    "DXY (Dólar Index)", "DX-Y.NYB"),
        ("usdcop", "USD/COP",           "COP=X"),
        ("eurusd", "EUR/USD",           "EURUSD=X"),
    ],
    "Índices": [
        ("sp500",  "S&P 500",  "^GSPC"),
        ("nasdaq", "Nasdaq",   "^IXIC"),
    ],
    "Las 7 Magníficas": [
        ("aapl",  "Apple (AAPL)",     "AAPL"),
        ("msft",  "Microsoft (MSFT)", "MSFT"),
        ("nvda",  "Nvidia (NVDA)",    "NVDA"),
        ("amzn",  "Amazon (AMZN)",    "AMZN"),
        ("googl", "Alphabet (GOOGL)", "GOOGL"),
        ("meta",  "Meta (META)",      "META"),
        ("tsla",  "Tesla (TSLA)",     "TSLA"),
    ],
    "Macro": [
        ("global_inflation_proxy", "Inflación Global (proxy)", "manual"),
    ],
}

GROUP_ORDER = ["Commodities", "Crypto", "Divisas", "Índices", "Las 7 Magníficas", "Macro"]

ADMIN_CSS = """
<style>
/* ── Page base ───────────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"] { background: #F8F9FA; }
[data-testid="stAppViewBlockContainer"],
[data-testid="stMainBlockContainer"],
.block-container { padding-top: 2rem !important; }

/* ── Section cards ───────────────────────────────────────────────────────── */
.adm-card {
    background: #FFFFFF;
    border: 1px solid #EAF0F6;
    border-radius: 16px;
    padding: 24px 28px;
    margin-bottom: 20px;
    box-shadow: 0 1px 4px rgba(27,42,74,.05);
}
.adm-card-title {
    font-size: 0.95rem; font-weight: 700; color: #1B2A4A;
    margin-bottom: 4px; display: flex; align-items: center; gap: 8px;
}
.adm-card-subtitle {
    font-size: 0.78rem; color: #8A9BB0; margin-bottom: 20px;
}
.adm-divider {
    border: none; border-top: 1px solid #F0F4F8; margin: 16px 0;
}

/* ── Indicator chips ─────────────────────────────────────────────────────── */
div[data-testid="stCheckbox"] {
    padding: 0 !important; margin-bottom: 0 !important;
}
div[data-testid="stCheckbox"] label {
    background: #F4F6F8 !important;
    border: 1.5px solid #DDE4EC !important;
    border-radius: 30px !important;
    padding: 5px 14px 5px 10px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    color: #7B8FA4 !important;
    cursor: pointer !important;
    transition: all 0.15s ease !important;
    width: 100% !important;
    display: flex !important;
    align-items: center !important;
}
div[data-testid="stCheckbox"]:has(input:checked) label {
    background: #E6FBF4 !important;
    border-color: #00C896 !important;
    color: #007A5C !important;
}
div[data-testid="stCheckbox"] label:hover {
    border-color: #00C896 !important;
    background: #F0FDF9 !important;
}

/* ── Counter badge ───────────────────────────────────────────────────────── */
.counter-row {
    display: flex; align-items: center; gap: 12px;
    margin-top: 16px; padding-top: 16px;
    border-top: 1px solid #F0F4F8;
}
.counter-badge {
    font-size: 0.85rem; font-weight: 700;
    padding: 4px 14px; border-radius: 20px;
}
.counter-ok  { background: #E6FBF4; color: #007A5C; }
.counter-max { background: #FFF0F0; color: #C0392B; }
.counter-label { font-size: 0.78rem; color: #8A9BB0; }

/* ── Group headers ───────────────────────────────────────────────────────── */
.group-header {
    font-size: 0.7rem; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: #8A9BB0;
    margin-bottom: 10px; margin-top: 14px;
    display: flex; align-items: center; gap: 8px;
}
.group-header::after {
    content:""; flex:1; height:1px; background:#EAF0F6;
}
.group-header:first-child { margin-top: 0; }

/* ── Info notice ─────────────────────────────────────────────────────────── */
.adm-notice {
    background: #EFF6FF; border: 1px solid #BFDBFE;
    border-radius: 10px; padding: 12px 16px;
    font-size: 0.8rem; color: #1E40AF; line-height: 1.5;
    margin-top: 12px;
}
</style>
"""

# ── Autenticación ─────────────────────────────────────────────────────────────
def get_admin_password():
    try:
        return st.secrets["ADMIN_PASSWORD"]
    except Exception:
        return os.getenv("ADMIN_PASSWORD", "admin1234")

def login_form():
    st.markdown(ADMIN_CSS, unsafe_allow_html=True)
    st.markdown('<div style="max-width:400px;margin:80px auto 0">', unsafe_allow_html=True)
    st.markdown("""
<div style="text-align:center;margin-bottom:32px">
  <div style="font-size:2.5rem">⚙️</div>
  <div style="font-size:1.5rem;font-weight:800;color:#1B2A4A;margin-top:8px">Panel de Control</div>
  <div style="font-size:0.85rem;color:#8A9BB0;margin-top:4px">Agente Financiero Autónomo</div>
</div>""", unsafe_allow_html=True)
    pwd = st.text_input("Contraseña", type="password", placeholder="Ingresa la contraseña de administrador")
    if st.button("Ingresar", use_container_width=True, type="primary"):
        if pwd == get_admin_password():
            st.session_state["admin_logged_in"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    st.markdown('</div>', unsafe_allow_html=True)

if not st.session_state.get("admin_logged_in"):
    login_form()
    st.stop()

# ── Panel ─────────────────────────────────────────────────────────────────────
st.markdown(ADMIN_CSS, unsafe_allow_html=True)
cfg = load_config()

# Header
col_title, col_logout = st.columns([5, 1])
with col_title:
    st.markdown("""
<div style="padding:12px 0 20px">
  <div style="font-size:1.5rem;font-weight:800;color:#1B2A4A">⚙️ Panel de Control</div>
  <div style="font-size:0.82rem;color:#8A9BB0;margin-top:2px">Configuración del Agente Financiero Autónomo</div>
</div>""", unsafe_allow_html=True)
with col_logout:
    st.markdown("<div style='padding-top:18px'>", unsafe_allow_html=True)
    if st.button("Cerrar sesión", type="secondary"):
        st.session_state["admin_logged_in"] = False
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# ── Sección: Indicadores ──────────────────────────────────────────────────────
active_now = cfg.get("active_indicators", DEFAULTS["active_indicators"])
if "ind_selection" not in st.session_state:
    st.session_state["ind_selection"] = set(active_now)
selected = st.session_state["ind_selection"]

st.markdown("""
<div class="adm-card">
  <div class="adm-card-title">📊 Indicadores activos</div>
  <div class="adm-card-subtitle">Selecciona hasta 5 indicadores para el dashboard y el pipeline</div>
""", unsafe_allow_html=True)

for group in GROUP_ORDER:
    items = CATALOG_GROUPS.get(group, [])
    if not items:
        continue
    st.markdown(f'<div class="group-header">{group}</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    for i, (key, label, symbol) in enumerate(items):
        col = cols[i % 3]
        is_checked = key in selected
        ticker_tag = f" ({symbol})" if symbol != "manual" else " (proxy)"
        new_val = col.checkbox(
            f"{label}{ticker_tag}",
            value=is_checked,
            key=f"ind_{key}",
        )
        if new_val and not is_checked:
            if len(selected) >= MAX_ACTIVE:
                st.error(f"Maximo {MAX_ACTIVE} indicadores. Desactiva uno antes de agregar otro.")
                st.session_state[f"ind_{key}"] = False
            else:
                selected.add(key)
        elif not new_val and is_checked:
            selected.discard(key)

st.session_state["ind_selection"] = selected
n = len(selected)
badge_cls = "counter-ok" if n <= MAX_ACTIVE else "counter-max"
st.markdown(f"""
  <div class="counter-row">
    <span class="counter-badge {badge_cls}">{n} / {MAX_ACTIVE}</span>
    <span class="counter-label">indicadores activos seleccionados</span>
  </div>
</div>""", unsafe_allow_html=True)
if n == 0:
    st.warning("Debes tener al menos 1 indicador activo.")

# ── Sección: Horario ──────────────────────────────────────────────────────────
st.markdown("""
<div class="adm-card">
  <div class="adm-card-title">⏰ Horario de envío</div>
  <div class="adm-card-subtitle">Hora en que se envía el reporte diario</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns([2, 1])
with col1:
    hora_colombia = st.selectbox(
        "Hora de envío (Colombia, UTC-5)",
        options=list(range(0, 24)),
        index=cfg.get("send_hour_utc", 12),
        format_func=lambda h: f"{h:02d}:00",
    )
with col2:
    hora_utc = (hora_colombia + 5) % 24
    st.metric("Equivalente UTC", f"{hora_utc:02d}:00")

st.markdown(f"""
  <div class="adm-notice">
    Al guardar, se actualizará automáticamente el cron de
    <code>.github/workflows/daily_pipeline.yml</code>
    a <code>0 {hora_utc} * * *</code>.
    Recuerda hacer <strong>commit y push</strong> del archivo para que el cambio
    se aplique en GitHub Actions.
  </div>
</div>""", unsafe_allow_html=True)

# ── Sección: Notificaciones ───────────────────────────────────────────────────
st.markdown("""
<div class="adm-card">
  <div class="adm-card-title">📧 Notificaciones</div>
  <div class="adm-card-subtitle">Canales por los cuales se envía el reporte diario</div>
""", unsafe_allow_html=True)

col_email, col_wa = st.columns(2)
with col_email:
    st.markdown("**Email**")
    email_enabled = st.toggle("Activar email", value=cfg.get("email_enabled", True), key="tog_email")
    email_to = st.text_input(
        "Destinatario",
        value=cfg.get("email_to", ""),
        disabled=not email_enabled,
        placeholder="correo@ejemplo.com",
        key="email_to_input",
    )

with col_wa:
    st.markdown("**WhatsApp**")
    whatsapp_enabled = st.toggle("Activar WhatsApp", value=cfg.get("whatsapp_enabled", True), key="tog_wa")
    whatsapp_to = st.text_input(
        "Número (sin +)",
        value=cfg.get("whatsapp_to", ""),
        disabled=not whatsapp_enabled,
        placeholder="573174286451",
        key="wa_to_input",
    )

st.markdown("</div>", unsafe_allow_html=True)

# ── Sección: Alertas ──────────────────────────────────────────────────────────
st.markdown("""
<div class="adm-card">
  <div class="adm-card-title">🔔 Monitor de alertas</div>
  <div class="adm-card-subtitle">Notificación cuando un indicador supera el umbral de variación</div>
""", unsafe_allow_html=True)

alerts_enabled = st.toggle("Activar monitor de alertas", value=cfg.get("alerts_enabled", True))
threshold = st.slider(
    "Umbral de alerta (variación % vs apertura)",
    min_value=1.0, max_value=10.0,
    value=float(cfg.get("alert_threshold", 4.0)),
    step=0.5,
    disabled=not alerts_enabled,
    help="Se dispara la alerta si la variación supera este porcentaje respecto al precio de apertura.",
)
if alerts_enabled:
    st.caption(f"Alerta si cualquier indicador activo varía mas de ±{threshold:.1f}% desde la apertura del dia.")

st.markdown("</div>", unsafe_allow_html=True)

# ── Guardar ───────────────────────────────────────────────────────────────────
st.markdown("<div style='margin-top:8px'>", unsafe_allow_html=True)
can_save = 1 <= n <= MAX_ACTIVE
if st.button("💾 Guardar configuración", type="primary", use_container_width=True, disabled=not can_save):
    new_cfg = {
        "send_hour_utc":     hora_utc,
        "email_enabled":     email_enabled,
        "email_to":          email_to.strip(),
        "whatsapp_enabled":  whatsapp_enabled,
        "whatsapp_to":       whatsapp_to.strip(),
        "alerts_enabled":    alerts_enabled,
        "alert_threshold":   threshold,
        "active_indicators": sorted(selected),
    }
    save_config(new_cfg)
    cron_updated = update_workflow_cron(hora_utc, hora_colombia)
    st.success("Configuracion guardada correctamente en config.json")
    if cron_updated:
        st.success(
            f"Workflow actualizado: cron `0 {hora_utc} * * *` "
            f"({hora_utc:02d}:00 UTC = {hora_colombia:02d}:00 Colombia). "
            "Haz commit y push de `.github/workflows/daily_pipeline.yml` para aplicarlo."
        )
    st.info(
        "Para que los cambios se reflejen en el dashboard, ve al Dashboard y haz clic en Actualizar datos.",
        icon="ℹ️",
    )
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        json_str = f.read()
    st.download_button(
        label="Descargar config.json",
        data=json_str,
        file_name="config.json",
        mime="application/json",
    )
st.markdown("</div>", unsafe_allow_html=True)

# ── Config actual ─────────────────────────────────────────────────────────────
with st.expander("Ver configuracion actual (config.json)"):
    st.json(cfg)
