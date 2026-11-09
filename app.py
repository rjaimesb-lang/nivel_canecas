import math

import pandas as pd
import streamlit as st

# ----- Configuración -----
SHEET_ID = "PEGA_AQUI_EL_ID_DE_TU_HOJA"
PESTANA = "lecturas"
UMBRAL_ATENCION = 50       # % a partir del cual se muestra "atención"
UMBRAL_ALERTA = 80         # % a partir del cual se muestra "llena"
SEGUNDOS_SIN_SENAL = 120   # sin lecturas por más de esto = "sin señal"
DISTANCIA_VACIA = 26.5     # mismas cifras de la calibración del ESP32
DISTANCIA_LLENA = 4.9

# C1 es la real (viene de la hoja). Las demás son de ejemplo.
# "nivel" = % de llenado que se mostrará; "horas" = hace cuántas horas se vació.
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
    # Pequeña variación para que los números se vean "vivos"
    deriva = 1.5 * math.sin(ahora.timestamp() / 600 + cfg["fase"] * 6.28)
    pct = min(max(nivel + deriva, 0), 100)

    retraso = cfg.get("sin_senal_min", 0)
    fin = ahora - pd.Timedelta(minutes=retraso)
    tasa = nivel / cfg["horas"]  # % por hora
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

    # ----- Resumen general -----
    llenas = sum(1 for d in datos.values() if not d["sin_senal"] and d["pct"] >= UMBRAL_ALERTA)
    atencion = sum(1 for d in datos.values()
                   if not d["sin_senal"] and UMBRAL_ATENCION <= d["pct"] < UMBRAL_ALERTA)
    sin_senal = sum(1 for d in datos.values() if d["sin_senal"])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Canecas monitoreadas", len(datos))
    m2.metric("🔴 Para vaciar", llenas)
    m3.metric("🟠 En atención", atencion)
    m4.metric("⚪ Sin señal", sin_senal)

    urgentes = sorted(
        [(cid, d) for cid, d in datos.items() if not d["sin_senal"] and d["pct"] >= UMBRAL_ALERTA],
        key=lambda x: -x[1]["pct"],
    )
    if urgentes:
        st.error("🚨 Para vaciar ahora: " +
                 " → ".join(f"{cid} ({d['pct']:.0f} %)" for cid, d in urgentes))

    # ----- Tarjetas por caneca (las más llenas primero) -----
    orden = sorted(datos.items(), key=lambda x: (x[1]["sin_senal"], -x[1]["pct"]))
    columnas = st.columns(3)
    for i, (cid, d) in enumerate(orden):
        with columnas[i % 3]:
            with st.container(border=True):
                etiqueta = cid if d["real"] else f"{cid} 🧪"
                st.markdown(f"**{etiqueta}**")
                st.caption(f"📍 {CANECAS[cid]['ubicacion']}")
                st.metric("Llenado", f"{d['pct']:.0f} %")
                st.progress(int(min(max(d["pct"], 0), 100)))
                st.write(d["estado"])
                st.caption(f"Última lectura hace {hace(d['segundos'])}")

    # ----- Detalle de una caneca -----
    st.subheader("Detalle e historial")
    elegida = st.selectbox("Caneca", list(datos.keys()), key="caneca_detalle")
    d = datos[elegida]
    st.caption(f"📍 {CANECAS[elegida]['ubicacion']}  ·  Distancia al contenido: "
               f"{d['distancia']:.1f} cm  ·  Última lectura hace {hace(d['segundos'])}")
    st.line_chart(d["hist"])


st.title("🗑️ Monitor de canecas del campus")
mostrar_ejemplo = st.sidebar.checkbox("Mostrar canecas de ejemplo (simuladas)", value=True)
st.sidebar.caption("Las canecas marcadas con 🧪 son simuladas, para mostrar cómo se "
                   "vería el sistema con varios puntos. C1 es la real.")
panel(mostrar_ejemplo)
