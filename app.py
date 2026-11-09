import base64
import math
import os

import pandas as pd
import streamlit as st

# ----- Configuración -----
SHEET_ID = "1tWx9sWxbX7QzVMrPspHNbhCEZLFyItKxSFOwTxq9u0o"
PESTANA = "lecturas"
LOGO = "logo_universidad.png"   # súbelo junto a este archivo (si no existe, no se muestra)
UMBRAL_ATENCION = 50       # % a partir del cual se muestra "atención"
UMBRAL_ALERTA = 80         # % a partir del cual se muestra "llena"
SEGUNDOS_SIN_SENAL = 120   # sin lecturas por más de esto = "sin señal"
DISTANCIA_VACIA = 26.5     # mismas cifras de la calibración del ESP32
DISTANCIA_LLENA = 4.9

# C1 es la real (viene de la hoja). Las demás son de ejemplo.
CANECAS = {
    "C1": {"ubicacion": "Bloque B, piso 2, junto a la cafetería", "real": True},
    "C2": {"ubicacion": "Biblioteca, entrada principal", "nivel": 92, "horas": 9, "fase": 0.2},
    "C3": {"ubicacion": "Cafetería central", "nivel": 67, "horas": 5, "fase": 0.5},
    "C4": {"ubicacion": "Bloque A, hall de ingreso", "nivel": 18, "horas": 3, "fase": 0.8},
    "C5": {"ubicacion": "Zona deportiva", "nivel": 41, "horas": 7, "fase": 0.1},
    "C6": {"ubicacion": "Parqueadero norte", "nivel": 55, "horas": 8, "fase": 0.4,
           "sin_senal_min": 47},
}

# Si pegaste el enlace completo, esto saca solo el ID
SHEET_ID = SHEET_ID.strip()
if "/d/" in SHEET_ID:
    SHEET_ID = SHEET_ID.split("/d/")[1].split("/")[0]

URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={PESTANA}"

st.set_page_config(page_title="Monitor de canecas", page_icon="🗑️", layout="wide")

ESTILO = """
<style>
.cabecera{display:flex;align-items:center;gap:18px;margin-bottom:10px}
.titulo{font-size:2.1rem;font-weight:700}
@keyframes pulso{
  0%{box-shadow:0 0 0 0 rgba(229,57,53,.75)}
  70%{box-shadow:0 0 0 18px rgba(229,57,53,0)}
  100%{box-shadow:0 0 0 0 rgba(229,57,53,0)}
}
.alerta{background:linear-gradient(90deg,#b71c1c,#e53935);color:#fff;padding:18px 22px;
  border-radius:14px;margin:8px 0 16px 0;animation:pulso 1.6s infinite}
.alerta h2{margin:0 0 6px 0;font-size:1.6rem;color:#fff}
.ruta{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}
.chip{background:rgba(255,255,255,.2);border-radius:10px;padding:8px 14px;font-weight:600}
.ok{background:#1b5e20;color:#fff;padding:14px 20px;border-radius:12px;
  margin:8px 0 16px 0;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px;margin:12px 0}
.card{border-radius:14px;padding:14px 16px;background:#1b1f27;color:#fff;
  border-left:8px solid var(--c)}
.card.roja{animation:pulso 1.6s infinite}
.nombre{font-weight:700;font-size:1.1rem}
.ubic{opacity:.75;font-size:.85rem;margin-bottom:6px}
.nivel{font-size:2.4rem;font-weight:800;line-height:1.1}
.barra{height:10px;background:#3a3f4b;border-radius:6px;overflow:hidden;margin:8px 0}
.barra>div{height:100%;background:var(--c)}
.est{font-weight:600}
.ult{opacity:.6;font-size:.8rem;margin-top:4px}
</style>
"""
st.markdown(ESTILO, unsafe_allow_html=True)


def logo_html(ruta, alto=56):
    ext = ruta.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "jpeg", "svg": "svg+xml"}.get(ext, ext)
    with open(ruta, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return (f'<div style="background:#fff;border-radius:12px;padding:8px 14px;">'
            f'<img src="data:image/{mime};base64,{b64}" style="height:{alto}px"></div>')


def cargar():
    df = pd.read_csv(URL)
    df.columns = [c.strip() for c in df.columns]
    df["fecha"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce")
    for col in ["distancia_cm", "porcentaje"]:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce"
        )
    df["caneca"] = df["caneca"].astype(str).str.strip()
    return df.dropna(subset=["fecha", "porcentaje"]).sort_values("fecha")


def estado(pct, sin_senal):
    if sin_senal:
        return "⚪ Sin señal"
    if pct >= UMBRAL_ALERTA:
        return "🔴 Llena: vaciar"
    if pct >= UMBRAL_ATENCION:
        return "🟠 Atención"
    return "🟢 Normal"


def datos_reales(cid, df, ahora):
    d = df[df["caneca"] == cid]
    if d.empty:
        return None
    ultima = d.iloc[-1]
    return {
        "pct": float(ultima["porcentaje"]),
        "distancia": float(ultima["distancia_cm"]),
        "segundos": (ahora - ultima["fecha"]).total_seconds(),
        "hist": d.set_index("fecha")["porcentaje"].tail(200),
        "real": True,
    }


def datos_simulados(cfg, ahora):
    nivel = cfg["nivel"]
    deriva = 1.5 * math.sin(ahora.timestamp() / 600 + cfg["fase"] * 6.28)
    pct = min(max(nivel + deriva, 0), 100)

    retraso = cfg.get("sin_senal_min", 0)
    fin = ahora - pd.Timedelta(minutes=retraso)
    tasa = nivel / cfg["horas"]
    t_vaciado = fin - pd.Timedelta(hours=cfg["horas"])
    indice = pd.date_range(end=fin, periods=144, freq="10min")
    horas_desde = (indice - t_vaciado).total_seconds() / 3600
    hist = pd.Series([(tasa * h) % 100 for h in horas_desde], index=indice)

    return {
        "pct": pct,
        "distancia": DISTANCIA_VACIA - pct / 100 * (DISTANCIA_VACIA - DISTANCIA_LLENA),
        "segundos": retraso * 60 if retraso else 8,
        "hist": hist,
        "real": False,
    }


def hace(segundos):
    if segundos < 120:
        return f"{int(segundos)} s"
    if segundos < 7200:
        return f"{int(segundos // 60)} min"
    return f"{int(segundos // 3600)} h"


def tarjeta(cid, d):
    if d["sin_senal"]:
        color, clase = "#9e9e9e", ""
    elif d["pct"] >= UMBRAL_ALERTA:
        color, clase = "#e53935", "roja"
    elif d["pct"] >= UMBRAL_ATENCION:
        color, clase = "#fb8c00", ""
    else:
        color, clase = "#43a047", ""
    etiqueta = cid if d["real"] else f"{cid} 🧪"
    ancho = int(min(max(d["pct"], 0), 100))
    return (f'<div class="card {clase}" style="--c:{color}">'
            f'<div class="nombre">{etiqueta}</div>'
            f'<div class="ubic">📍 {CANECAS[cid]["ubicacion"]}</div>'
            f'<div class="nivel">{d["pct"]:.0f} %</div>'
            f'<div class="barra"><div style="width:{ancho}%"></div></div>'
            f'<div class="est">{d["estado"]}</div>'
            f'<div class="ult">Última lectura hace {hace(d["segundos"])}</div>'
            f'</div>')


@st.fragment(run_every=10)
def panel(mostrar_ejemplo):
    ahora = pd.Timestamp.now(tz="America/Bogota").tz_localize(None)

    df = None
    try:
        df = cargar()
    except Exception as e:
        st.error("No se pudo leer la hoja (la caneca real no se mostrará). Error:")
        st.code(f"{type(e).__name__}: {e}")

    datos = {}
    for cid, cfg in CANECAS.items():
        if cfg.get("real"):
            if df is not None:
                d = datos_reales(cid, df, ahora)
                if d:
                    datos[cid] = d
        elif mostrar_ejemplo:
            datos[cid] = datos_simulados(cfg, ahora)

    if not datos:
        st.info("No hay canecas para mostrar.")
        return

    for d in datos.values():
        d["sin_senal"] = d["segundos"] > SEGUNDOS_SIN_SENAL
        d["estado"] = estado(d["pct"], d["sin_senal"])

    # ----- Alerta de vaciado -----
    urgentes = sorted(
        [(cid, d) for cid, d in datos.items() if not d["sin_senal"] and d["pct"] >= UMBRAL_ALERTA],
        key=lambda x: -x[1]["pct"],
    )
    if urgentes:
        chips = "".join(
            f'<div class="chip">{i}. {cid} · {CANECAS[cid]["ubicacion"]} · {d["pct"]:.0f} %</div>'
            for i, (cid, d) in enumerate(urgentes, 1)
        )
        texto = ("1 caneca requiere vaciado" if len(urgentes) == 1
                 else f"{len(urgentes)} canecas requieren vaciado")
        st.markdown(
            f'<div class="alerta"><h2>🚨 ALERTA DE VACIADO</h2>'
            f'<div>{texto}. Ruta sugerida (la más llena primero):</div>'
            f'<div class="ruta">{chips}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="ok">✅ Todo en orden: ninguna caneca requiere vaciado</div>',
                    unsafe_allow_html=True)

    # ----- Resumen general -----
    atencion = sum(1 for d in datos.values()
                   if not d["sin_senal"] and UMBRAL_ATENCION <= d["pct"] < UMBRAL_ALERTA)
    sin_senal = sum(1 for d in datos.values() if d["sin_senal"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Canecas monitoreadas", len(datos))
    m2.metric("🔴 Para vaciar", len(urgentes))
    m3.metric("🟠 En atención", atencion)
    m4.metric("⚪ Sin señal", sin_senal)

    # ----- Tarjetas (las más llenas primero) -----
    orden = sorted(datos.items(), key=lambda x: (x[1]["sin_senal"], -x[1]["pct"]))
    st.markdown('<div class="grid">' + "".join(tarjeta(cid, d) for cid, d in orden) + "</div>",
                unsafe_allow_html=True)

    # ----- Detalle de una caneca -----
    st.subheader("Detalle e historial")
    elegida = st.selectbox("Caneca", list(datos.keys()), key="caneca_detalle")
    d = datos[elegida]
    st.caption(f"📍 {CANECAS[elegida]['ubicacion']}  ·  Distancia al contenido: "
               f"{d['distancia']:.1f} cm  ·  Última lectura hace {hace(d['segundos'])}")
    serie = d["hist"]
    if d["real"]:
        serie = serie.rolling(5, min_periods=1).median()  # suaviza el ruido
    st.line_chart(serie)
    st.caption(f"Actualizado: {ahora:%H:%M:%S}")


logo = logo_html(LOGO) if os.path.exists(LOGO) else ""
st.markdown(
    f'<div class="cabecera">{logo}<div class="titulo">🗑️ Monitor de canecas del campus</div></div>',
    unsafe_allow_html=True,
)
mostrar_ejemplo = st.sidebar.checkbox("Mostrar canecas de ejemplo (simuladas)", value=True)
st.sidebar.caption("Las canecas marcadas con 🧪 son simuladas, para mostrar cómo se "
                   "vería el sistema con varios puntos. C1 es la real.")
panel(mostrar_ejemplo)
