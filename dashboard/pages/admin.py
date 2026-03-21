import json
import os
from pathlib import Path
import streamlit as st

# ── Rutas ────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent.parent
CONFIG_FILE = ROOT / "config.json"

DEFAULTS = {
    "send_hour_utc":    12,
    "email_enabled":    True,
    "email_to":         "",
    "whatsapp_enabled": True,
    "whatsapp_to":      "",
    "alerts_enabled":   True,
    "alert_threshold":  4.0,
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

st.set_page_config(page_title="Panel de Control", page_icon="⚙️", layout="centered")

# ── Autenticación ─────────────────────────────────────────────────────────────
def get_admin_password():
    try:
        return st.secrets["ADMIN_PASSWORD"]
    except Exception:
        return os.getenv("ADMIN_PASSWORD", "admin1234")


def login_form():
    st.title("⚙️ Panel de Control")
    st.markdown("---")
    pwd = st.text_input("Contraseña", type="password", placeholder="Ingresa la contraseña de administrador")
    if st.button("Ingresar", use_container_width=True):
        if pwd == get_admin_password():
            st.session_state["admin_logged_in"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")


if not st.session_state.get("admin_logged_in"):
    login_form()
    st.stop()

# ── Panel (solo si autenticado) ───────────────────────────────────────────────
cfg = load_config()

st.title("⚙️ Panel de Control")
st.caption("Configuración del Agente Financiero Autónomo")

if st.button("Cerrar sesión", type="secondary"):
    st.session_state["admin_logged_in"] = False
    st.rerun()

st.markdown("---")

# ── Sección: Horario ──────────────────────────────────────────────────────────
st.subheader("Horario de envío")

col1, col2 = st.columns(2)
with col1:
    hora_colombia = st.selectbox(
        "Hora de envío (Colombia, UTC-5)",
        options=list(range(0, 24)),
        index=7,                              # 7am por defecto
        format_func=lambda h: f"{h:02d}:00",
    )
with col2:
    hora_utc = (hora_colombia + 5) % 24
    st.metric("Equivalente en UTC", f"{hora_utc:02d}:00")
    st.caption("GitHub Actions usa UTC")

st.info(
    f"El cron del workflow está fijo en `0 12 * * *` (12:00 UTC = 7:00 AM Colombia). "
    f"Si cambias la hora aquí, actualiza también el archivo `.github/workflows/daily_pipeline.yml`.",
    icon="ℹ️",
)

st.markdown("---")

# ── Sección: Email ────────────────────────────────────────────────────────────
st.subheader("Email")

email_enabled = st.toggle("Activar envío por email", value=cfg.get("email_enabled", True))
email_to = st.text_input(
    "Destinatario de email",
    value=cfg.get("email_to", ""),
    disabled=not email_enabled,
    placeholder="correo@ejemplo.com",
)

st.markdown("---")

# ── Sección: WhatsApp ─────────────────────────────────────────────────────────
st.subheader("WhatsApp")

whatsapp_enabled = st.toggle("Activar envío por WhatsApp", value=cfg.get("whatsapp_enabled", True))
whatsapp_to = st.text_input(
    "Número de WhatsApp (sin +)",
    value=cfg.get("whatsapp_to", ""),
    disabled=not whatsapp_enabled,
    placeholder="573174286451",
)

st.markdown("---")

# ── Sección: Alertas ──────────────────────────────────────────────────────────
st.subheader("Monitor de alertas")

alerts_enabled = st.toggle("Activar monitor de alertas", value=cfg.get("alerts_enabled", True))

threshold = st.slider(
    "Umbral de alerta (variación % vs apertura)",
    min_value=1.0,
    max_value=10.0,
    value=float(cfg.get("alert_threshold", 4.0)),
    step=0.5,
    disabled=not alerts_enabled,
    help="Si un indicador supera este % de variación respecto al precio de apertura, se dispara la alerta.",
)

if alerts_enabled:
    st.caption(f"Alerta si Brent, BTC o USD/COP varía más de ±{threshold}% respecto a la apertura del día.")

st.markdown("---")

# ── Guardar ───────────────────────────────────────────────────────────────────
if st.button("Guardar configuración", type="primary", use_container_width=True):
    new_cfg = {
        "send_hour_utc":    hora_utc,
        "email_enabled":    email_enabled,
        "email_to":         email_to.strip(),
        "whatsapp_enabled": whatsapp_enabled,
        "whatsapp_to":      whatsapp_to.strip(),
        "alerts_enabled":   alerts_enabled,
        "alert_threshold":  threshold,
    }
    save_config(new_cfg)
    st.success("Configuración guardada en config.json")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        json_str = f.read()

    st.download_button(
        label="Descargar config.json para subir a GitHub",
        data=json_str,
        file_name="config.json",
        mime="application/json",
        help="En Streamlit Cloud el archivo se resetea al reiniciar. Descárgalo y haz commit al repo.",
    )

# ── Config actual ─────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("Ver configuración actual (config.json)"):
    st.json(cfg)
