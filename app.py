import json
import time
import unicodedata
import string

import streamlit as st
from PIL import Image
from bokeh.models.widgets import Button
from bokeh.models import CustomJS
from streamlit_bokeh_events import streamlit_bokeh_events
import paho.mqtt.client as paho

# ─────────────────────────── Configuración ───────────────────────────
BROKER = "broker.mqttdashboard.com"
PORT = 1883
TOPIC = "danieri"

# Comandos que entiende el ESP32 (deben coincidir EXACTAMENTE con el código de Wokwi)
COMANDOS = [
    {"texto": "Enciende las luces", "icono": "💡", "grupo": "Luces",  "desc": "Prende el LED del pin 2"},
    {"texto": "Apaga las luces",    "icono": "🌑", "grupo": "Luces",  "desc": "Apaga el LED del pin 2"},
    {"texto": "Abre la puerta",     "icono": "🚪", "grupo": "Puerta", "desc": "Mueve el servo a 180°"},
    {"texto": "Cierra la puerta",   "icono": "🔒", "grupo": "Puerta", "desc": "Mueve el servo a 90°"},
]

st.set_page_config(page_title="Control por Voz", page_icon="🎙️", layout="centered")

# ─────────────────────────── Estilos ───────────────────────────
st.markdown("""
<style>
.block-container { padding-top: 2rem; max-width: 760px; }
.hero {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 55%, #db2777 100%);
    border-radius: 20px; padding: 28px 30px; color: white; margin-bottom: 22px;
    box-shadow: 0 10px 30px rgba(79,70,229,.25);
}
.hero h1 { margin: 0; font-size: 2rem; color: white; }
.hero p  { margin: 6px 0 0; opacity: .9; font-size: 1.05rem; }
.badge {
    display:inline-block; background: rgba(255,255,255,.18); padding: 3px 12px;
    border-radius: 999px; font-size: .8rem; margin-bottom: 10px; letter-spacing: .05em;
}
.section-title { font-weight: 700; font-size: 1.15rem; margin: 18px 0 10px; }
.cmd-card {
    border: 1px solid rgba(128,128,128,.25); border-radius: 14px; padding: 14px 16px;
    margin-bottom: 10px; background: rgba(124,58,237,.05);
}
.cmd-card .icono { font-size: 1.6rem; }
.cmd-card .frase { font-weight: 700; font-size: 1.02rem; }
.cmd-card .desc  { opacity: .7; font-size: .85rem; }
.heard {
    border-left: 5px solid #7c3aed; background: rgba(124,58,237,.08);
    padding: 12px 16px; border-radius: 10px; font-size: 1.1rem; margin: 10px 0;
}
.ok   { color: #16a34a; font-weight: 700; }
.fail { color: #dc2626; font-weight: 700; }
.hist { font-size: .9rem; opacity: .85; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────── Utilidades ───────────────────────────
def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni puntuación."""
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.translate(str.maketrans("", "", string.punctuation)).strip()


def interpretar(texto: str):
    """Convierte lo que dijo el usuario en el comando exacto que espera el ESP32."""
    t = normalizar(texto)
    if "luz" in t or "luces" in t or "foco" in t:
        if any(p in t for p in ("apaga", "apagar", "apague")):
            return "Apaga las luces"
        if any(p in t for p in ("enciende", "encender", "prende", "prender", "encienda")):
            return "Enciende las luces"
    if "puerta" in t:
        if any(p in t for p in ("abre", "abrir", "abra")):
            return "Abre la puerta"
        if any(p in t for p in ("cierra", "cerrar", "cierre")):
            return "Cierra la puerta"
    return None


def crear_cliente():
    try:  # paho-mqtt 2.x
        return paho.Client(paho.CallbackAPIVersion.VERSION1, f"DLS-{int(time.time())}")
    except AttributeError:  # paho-mqtt 1.x
        return paho.Client(f"DLS-{int(time.time())}")


def enviar(comando: str) -> bool:
    try:
        cliente = crear_cliente()
        cliente.connect(BROKER, PORT)
        cliente.publish(TOPIC, json.dumps({"Act1": comando}))
        cliente.disconnect()
        return True
    except Exception as e:
        st.error(f"No se pudo publicar en MQTT: {e}")
        return False


def registrar(oido: str, comando, enviado: bool):
    st.session_state.historial.insert(0, {
        "hora": time.strftime("%H:%M:%S"),
        "oido": oido, "comando": comando, "ok": enviado,
    })
    st.session_state.historial = st.session_state.historial[:8]


if "historial" not in st.session_state:
    st.session_state.historial = []

# ─────────────────────────── Encabezado ───────────────────────────
st.markdown("""
<div class="hero">
  <span class="badge">INTERFACES MULTIMODALES</span>
  <h1>🎙️ Control por voz</h1>
  <p>Habla y controla las luces y la puerta de tu casa simulada en Wokwi.</p>
</div>
""", unsafe_allow_html=True)

col_img, col_txt = st.columns([1, 2])
with col_img:
    try:
        st.image(Image.open("voice_ctrl.jpg"), use_container_width=True)
    except FileNotFoundError:
        st.markdown("<div style='font-size:5rem;text-align:center'>🎤</div>", unsafe_allow_html=True)
with col_txt:
    st.markdown("**¿Cómo funciona?**")
    st.markdown(
        "1. Toca **Iniciar** y permite el micrófono.\n"
        "2. Di una de las frases sugeridas.\n"
        "3. La orden viaja por MQTT al ESP32 en Wokwi."
    )
    st.caption(f"Broker: `{BROKER}` · Tópico: `{TOPIC}`")

# ─────────────────────────── Micrófono ───────────────────────────
st.markdown('<div class="section-title">🎤 Habla aquí</div>', unsafe_allow_html=True)

stt_button = Button(label="🎙️  Iniciar", width=220, button_type="primary")
stt_button.js_on_event("button_click", CustomJS(code="""
    var recognition = new webkitSpeechRecognition();
    recognition.lang = 'es-ES';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = function (e) {
        var value = "";
        for (var i = e.resultIndex; i < e.results.length; ++i) {
            if (e.results[i].isFinal) { value += e.results[i][0].transcript; }
        }
        if (value != "") {
            document.dispatchEvent(new CustomEvent("GET_TEXT", {detail: value}));
        }
    }
    recognition.start();
"""))

result = streamlit_bokeh_events(
    stt_button, events="GET_TEXT", key="listen",
    refresh_on_update=False, override_height=60, debounce_time=0,
)

if result and "GET_TEXT" in result:
    oido = result.get("GET_TEXT").strip()
    st.markdown(f'<div class="heard">🗣️ “{oido}”</div>', unsafe_allow_html=True)
    comando = interpretar(oido)
    if comando:
        ok = enviar(comando)
        if ok:
            st.markdown(f'<span class="ok">✅ Enviado: {comando}</span>', unsafe_allow_html=True)
        registrar(oido, comando, ok)
    else:
        st.markdown('<span class="fail">⚠️ No reconocí un comando. Prueba con una de las sugerencias.</span>',
                    unsafe_allow_html=True)
        registrar(oido, None, False)

# ─────────────────────────── Sugerencias ───────────────────────────
st.markdown('<div class="section-title">💬 Puedes decir…</div>', unsafe_allow_html=True)
st.caption("También puedes tocar ▶ para enviar el comando sin hablar.")

for grupo in ("Luces", "Puerta"):
    st.markdown(f"**{'💡' if grupo == 'Luces' else '🚪'} {grupo}**")
    cols = st.columns(2)
    for col, cmd in zip(cols, [c for c in COMANDOS if c["grupo"] == grupo]):
        with col:
            st.markdown(f"""
            <div class="cmd-card">
              <span class="icono">{cmd['icono']}</span>
              <div class="frase">“{cmd['texto']}”</div>
              <div class="desc">{cmd['desc']}</div>
            </div>""", unsafe_allow_html=True)
            if st.button(f"▶ Enviar", key=f"btn_{cmd['texto']}", use_container_width=True):
                ok = enviar(cmd["texto"])
                registrar("(botón)", cmd["texto"], ok)
                if ok:
                    st.toast(f"Enviado: {cmd['texto']}", icon="✅")

# ─────────────────────────── Historial ───────────────────────────
if st.session_state.historial:
    st.markdown('<div class="section-title">🕘 Últimas órdenes</div>', unsafe_allow_html=True)
    for h in st.session_state.historial:
        estado = "✅" if h["ok"] else "❌"
        detalle = h["comando"] or "sin coincidencia"
        st.markdown(f'<div class="hist">{estado} <code>{h["hora"]}</code> · {h["oido"]} → <b>{detalle}</b></div>',
                    unsafe_allow_html=True)
