import json
import os
from pathlib import Path
import streamlit as st

# ── Rutas ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent.parent
CONFIG_FILE = ROOT / "config.json"

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

# ── Autenticación ─────────────────────────────────────────────────────────────
def get_admin_password():
    try:
        return st.secrets["ADMIN_PASSWORD"]
    except Exception:
        return os.getenv("ADMIN_PASSWORD", "admin1234")

def login_form():
    st.title("⚙️ Panel de Control")
    st.markdown("---")
    pwd = st.text_input("Contraseña", type="password",
                        placeholder="Ingresa la contraseña de administrador")
    if st.button("Ingresar", use_container_width=True):
        if pwd == get_admin_password():
            st.session_state["admin_logged_in"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")

if not st.session_state.get("admin_logged_in"):
    login_form()
    st.stop()

# ── Panel ─────────────────────────────────────────────────────────────────────
cfg = load_config()

st.title("⚙️ Panel de Control")
st.caption("Configuración del Agente Financiero Autónomo")

if st.button("Cerrar sesión", type="secondary"):
    st.session_state["admin_logged_in"] = False
    st.rerun()

st.markdown("---")

# ── Sección: Gestión de Indicadores ──────────────────────────────────────────
st.subheader("📊 Gestión de Indicadores")
st.caption(f"Selecciona hasta **{MAX_ACTIVE} indicadores** activos para el dashboard y el pipeline.")

active_now = cfg.get("active_indicators", DEFAULTS["active_indicators"])

# Inicializar selección en session_state para poder validar en tiempo real
if "ind_selection" not in st.session_state:
    st.session_state["ind_selection"] = set(active_now)

selected = st.session_state["ind_selection"]

# Mostrar grupos con checkboxes
for group in GROUP_ORDER:
    items = CATALOG_GROUPS.get(group, [])
    if not items:
        continue
    st.markdown(f"**{group}**")
    cols = st.columns(3)
    for i, (key, label, symbol) in enumerate(items):
        col = cols[i % 3]
        is_checked = key in selected
        ticker_tag = f"`{symbol}`" if symbol != "manual" else "`proxy`"

        new_val = col.checkbox(
            f"{label} {ticker_tag}",
            value=is_checked,
            key=f"ind_{key}",
        )

        if new_val and not is_checked:
            if len(selected) >= MAX_ACTIVE:
                st.error(f"⚠️ Máximo {MAX_ACTIVE} indicadores permitidos. Desactiva uno antes de agregar otro.")
                st.session_state[f"ind_{key}"] = False   # revertir visualmente en próximo rerun
            else:
                selected.add(key)
        elif not new_val and is_checked:
            selected.discard(key)

st.session_state["ind_selection"] = selected

# Resumen de selección
n = len(selected)
color = "green" if n <= MAX_ACTIVE else "red"
st.markdown(
    f"**Activos seleccionados:** "
    f"<span style='color:{color};font-weight:700'>{n} / {MAX_ACTIVE}</span>",
    unsafe_allow_html=True,
)
if n == 0:
    st.warning("Debes tener al menos 1 indicador activo.")

st.markdown("---")

# ── Sección: Horario ──────────────────────────────────────────────────────────
st.subheader("🕐 Horario de envío")

col1, col2 = st.columns(2)
with col1:
    hora_colombia = st.selectbox(
        "Hora de envío (Colombia, UTC-5)",
        options=list(range(0, 24)),
        index=cfg.get("send_hour_utc", 12),
        format_func=lambda h: f"{h:02d}:00",
    )
with col2:
    hora_utc = (hora_colombia + 5) % 24
    st.metric("Equivalente en UTC", f"{hora_utc:02d}:00")
    st.caption("GitHub Actions usa UTC")

st.info(
    "El cron del workflow está fijo en `0 12 * * *` (12:00 UTC = 7:00 AM Colombia). "
    "Si cambias la hora aquí, actualiza también `.github/workflows/daily_pipeline.yml`.",
    icon="ℹ️",
)

st.markdown("---")

# ── Sección: Email ────────────────────────────────────────────────────────────
st.subheader("📧 Email")

email_enabled = st.toggle("Activar envío por email", value=cfg.get("email_enabled", True))
email_to = st.text_input(
    "Destinatario de email",
    value=cfg.get("email_to", ""),
    disabled=not email_enabled,
    placeholder="correo@ejemplo.com",
)

st.markdown("---")

# ── Sección: WhatsApp ─────────────────────────────────────────────────────────
st.subheader("💬 WhatsApp")

whatsapp_enabled = st.toggle("Activar envío por WhatsApp", value=cfg.get("whatsapp_enabled", True))
whatsapp_to = st.text_input(
    "Número de WhatsApp (sin +)",
    value=cfg.get("whatsapp_to", ""),
    disabled=not whatsapp_enabled,
    placeholder="573174286451",
)

st.markdown("---")

# ── Sección: Alertas ──────────────────────────────────────────────────────────
st.subheader("🔔 Monitor de alertas")

alerts_enabled = st.toggle("Activar monitor de alertas", value=cfg.get("alerts_enabled", True))

threshold = st.slider(
    "Umbral de alerta (variación % vs apertura)",
    min_value=1.0, max_value=10.0,
    value=float(cfg.get("alert_threshold", 4.0)),
    step=0.5,
    disabled=not alerts_enabled,
    help="Si un indicador supera este % de variación respecto al precio de apertura, se dispara la alerta.",
)

if alerts_enabled:
    active_labels = [k for k in selected]
    st.caption(f"Alerta si algún indicador activo varía más de ±{threshold}% respecto a la apertura del día.")

st.markdown("---")

# ── Guardar ───────────────────────────────────────────────────────────────────
can_save = 1 <= n <= MAX_ACTIVE
if st.button("💾 Guardar configuración", type="primary", use_container_width=True,
             disabled=not can_save):
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
    st.success("✅ Configuración guardada en config.json")
    st.info(
        "⚠️ Para que los cambios de indicadores se reflejen en el dashboard, "
        "haz clic en **🔄 Actualizar datos** en el Dashboard. "
        "Para que el pipeline recolecte los nuevos indicadores, haz commit del config.json actualizado.",
        icon="ℹ️",
    )

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        json_str = f.read()

    st.download_button(
        label="⬇️ Descargar config.json para subir a GitHub",
        data=json_str,
        file_name="config.json",
        mime="application/json",
        help="Descarga y haz commit al repo para que GitHub Actions use los indicadores seleccionados.",
    )

# ── Config actual ─────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("Ver configuración actual (config.json)"):
    st.json(cfg)
