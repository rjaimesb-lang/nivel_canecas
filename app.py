"""Panel de alertas de canecas del campus (prototipo ESP32 + sensor ultrasónico).

Ejecutar:  streamlit run app.py

Formato de la hoja de Google (una fila por lectura del sensor):
    timestamp | caneca_id | distancia_cm
    13/10/2026 14:05:00 | C01 | 18.4
"""
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Canecas del campus de la Universidad Central", page_icon="🗑️", layout="wide")

ZONA_HORARIA = ZoneInfo("America/Bogota")
SIN_SENAL_MIN = 30  # minutos sin lecturas para considerar que el sensor perdió señal
PROFUNDIDAD_DEFECTO = 50  # cm, para canecas que no estén registradas abajo

# Una entrada por caneca: zona y profundidad útil en cm
# (distancia del sensor al fondo cuando la caneca está vacía). Ajústalo a tus canecas reales.
CANECAS = {
    "C01": {"zona": "Cafetería", "profundidad_cm": 50},
    "C02": {"zona": "Baño", "profundidad_cm": 50},
    "C03": {"zona": "Cafetería", "profundidad_cm": 50},
    "C04": {"zona": "Pasillo", "profundidad_cm": 50},
}


def secreto(nombre, defecto=""):
    """Lee un valor de .streamlit/secrets.toml sin fallar si el archivo no existe."""
    try:
        return st.secrets.get(nombre, defecto)
    except Exception:
        return defecto


def ahora():
    return datetime.now(ZONA_HORARIA).replace(tzinfo=None)


def info(caneca_id):
    return CANECAS.get(caneca_id, {"zona": "Sin registrar", "profundidad_cm": PROFUNDIDAD_DEFECTO})


def porcentaje_llenado(distancia_cm, profundidad_cm):
    """El sensor mide la distancia a los residuos: cerca de la tapa = caneca llena."""
    return max(0.0, min(100.0, (1 - distancia_cm / profundidad_cm) * 100))


def enviar_telegram(texto):
    token, chat = secreto("TELEGRAM_TOKEN"), secreto("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False, "Faltan TELEGRAM_TOKEN y TELEGRAM_CHAT_ID en .streamlit/secrets.toml"
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": texto},
            timeout=10,
        )
        return r.ok, r.text
    except requests.RequestException as e:
        return False, str(e)


# ---------- Barra lateral ----------
with st.sidebar:
    st.header("Configuración")
    fuente = st.radio("Fuente de datos", ["Demo (simulado)", "Google Sheets"])
    url = ""
    if fuente == "Google Sheets":
        url = st.text_input(
            "Enlace CSV de la hoja",
            value=secreto("SHEET_CSV_URL"),
            help="En Google Sheets: Archivo > Compartir > Publicar en la web > formato CSV.",
        )
    umbral = st.slider("Umbral de alerta (% de llenado)", 50, 95, 80, 5)
    refresco = st.select_slider("Actualizar cada (segundos)", options=[10, 30, 60, 120], value=30)
    auto_alerta = st.checkbox(
        "Enviar alerta por Telegram cuando una caneca se llene",
        value=False,
        disabled=(fuente == "Demo (simulado)"),
    )
    if st.button("Enviar alerta de prueba"):
        ok, msg = enviar_telegram("🗑️ Alerta de prueba del panel de canecas.")
        (st.success if ok else st.error)("Mensaje enviado" if ok else f"No se envió: {msg}")


# ---------- Datos ----------
def datos_demo(n=48):
    """12 h de lecturas simuladas (una cada 15 min) para probar el panel sin el sensor."""
    rng = random.Random(7)
    objetivo = {"C01": 92, "C02": 78, "C03": 45, "C04": 20}  # % de llenado al final
    t_fin = ahora()
    filas = []
    for cid in CANECAS:
        for i in range(n):
            t = t_fin - timedelta(minutes=15 * (n - 1 - i))
            pct = objetivo.get(cid, 30) * i / (n - 1) + rng.uniform(-2, 2)
            dist = info(cid)["profundidad_cm"] * (1 - max(0, min(100, pct)) / 100)
            filas.append({"timestamp": t, "caneca_id": cid, "distancia_cm": round(dist, 1)})
    return pd.DataFrame(filas)


@st.cache_data(ttl=20)
def leer_hoja(enlace):
    df = pd.read_csv(enlace)
    df.columns = [c.strip().lower() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"], dayfirst=True, errors="coerce")
    df["distancia_cm"] = pd.to_numeric(df["distancia_cm"], errors="coerce")
    return df.dropna(subset=["timestamp", "caneca_id", "distancia_cm"])


def cargar_datos():
    if fuente == "Demo (simulado)":
        return datos_demo()
    if not url:
        st.info("Pega el enlace CSV de la hoja en la barra lateral.")
        return None
    try:
        return leer_hoja(url)
    except Exception as e:  # hoja privada, columnas distintas, sin conexión...
        st.error(f"No pude leer la hoja: {e}")
        return None


def estado(pct, sin_senal):
    if sin_senal:
        return "⚪ Sin señal"
    if pct >= umbral:
        return "🔴 Llena"
    if pct >= umbral - 20:
        return "🟠 Atención"
    return "🟢 Normal"


def resumen(df):
    """Una fila por caneca con su nivel actual. Usa la mediana de las últimas 3 lecturas
    porque el ultrasónico da valores saltones."""
    filas = []
    for cid, g in df.sort_values("timestamp").groupby("caneca_id"):
        meta = info(cid)
        pct = porcentaje_llenado(g.tail(3)["distancia_cm"].median(), meta["profundidad_cm"])
        ultima = g["timestamp"].iloc[-1]
        sin_senal = ahora() - ultima > timedelta(minutes=SIN_SENAL_MIN)
        filas.append(
            {
                "id": cid,
                "zona": meta["zona"],
                "pct": pct,
                "estado": estado(pct, sin_senal),
                "ultima": ultima.strftime("%d/%m %H:%M"),
                "llena": (pct >= umbral) and not sin_senal,
            }
        )
    return pd.DataFrame(filas)


# ---------- Alertas ----------
def alertar_nuevas(tabla):
    """Avisa una vez por caneca cuando se llena; vuelve a armarse al vaciarse.
    El estado vive en la sesión del navegador: para uso real conviene correr esto
    en un proceso aparte o guardar lo ya avisado en la hoja."""
    alertadas = st.session_state.setdefault("alertadas", set())
    for r in tabla.itertuples():
        if r.pct < umbral - 10:
            alertadas.discard(r.id)
        elif r.llena and r.id not in alertadas:
            ok, _ = enviar_telegram(f"🗑️ {r.id} ({r.zona}) está al {r.pct:.0f}%: hay que recogerla.")
            if ok:
                alertadas.add(r.id)


# ---------- Panel ----------
st.title("🗑️ Canecas del campus")


@st.fragment(run_every=refresco)
def panel():
    df = cargar_datos()
    if df is None:
        return
    if df.empty:
        st.info("Todavía no hay lecturas.")
        return

    tabla = resumen(df)
    if auto_alerta and fuente != "Demo (simulado)":
        alertar_nuevas(tabla)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Canecas", len(tabla))
    c2.metric("Llenas", int(tabla["llena"].sum()))
    c3.metric("En atención", int(tabla["estado"].str.contains("Atención").sum()))
    c4.metric("Sin señal", int(tabla["estado"].str.contains("Sin señal").sum()))

    llenas = tabla[tabla["llena"]].sort_values("pct", ascending=False)
    if llenas.empty:
        st.success("No hay canecas para recoger por ahora.")
    else:
        st.warning(
            "Recoger ahora: "
            + ", ".join(f"{r.id} ({r.zona}, {r.pct:.0f}%)" for r in llenas.itertuples())
        )

    cols = st.columns(max(1, min(len(tabla), 4)))
    for i, r in enumerate(tabla.itertuples()):
        with cols[i % len(cols)]:
            with st.container(border=True):
                st.markdown(f"**{r.id}** · {r.zona}")
                st.markdown(f"### {r.pct:.0f}%")
                st.progress(int(round(r.pct)) / 100)
                st.caption(f"{r.estado} · última lectura {r.ultima}")

    st.subheader("Orden sugerido de recolección")
    vista = tabla.sort_values("pct", ascending=False)[["id", "zona", "pct", "estado", "ultima"]]
    vista.columns = ["Caneca", "Zona", "% llenado", "Estado", "Última lectura"]
    st.dataframe(
        vista,
        hide_index=True,
        column_config={
            "% llenado": st.column_config.ProgressColumn(
                "% llenado", min_value=0, max_value=100, format="%.0f%%"
            )
        },
    )

    st.subheader("Llenado en las últimas 24 horas")
    h = df[df["timestamp"] >= ahora() - timedelta(hours=24)].copy()
    h["pct"] = [
        porcentaje_llenado(d, info(c)["profundidad_cm"])
        for d, c in zip(h["distancia_cm"], h["caneca_id"])
    ]
    st.line_chart(h.pivot_table(index="timestamp", columns="caneca_id", values="pct"))
    st.caption(f"Actualizado {ahora():%H:%M:%S} · umbral de alerta {umbral}%")


panel()
