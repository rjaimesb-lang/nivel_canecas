import pandas as pd
import streamlit as st

# ----- Cambia estos datos -----
SHEET_ID = "PEGA_AQUI_EL_ID_DE_TU_HOJA"
PESTANA = "lecturas"
UBICACION = "Bloque B, piso 2, junto a la cafetería"
UMBRAL_ATENCION = 50   # % a partir del cual se muestra "atención"
UMBRAL_ALERTA = 80     # % a partir del cual se muestra "llena"

URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={PESTANA}"

st.set_page_config(page_title="Monitor de caneca", page_icon="🗑️", layout="centered")
st.title("🗑️ Monitor de caneca")
st.caption(f"📍 {UBICACION}")


def cargar():
    df = pd.read_csv(URL)
    df["fecha"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce")
    for col in ["distancia_cm", "porcentaje"]:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce"
        )
    return df.dropna(subset=["fecha", "porcentaje"]).sort_values("fecha")


@st.fragment(run_every=10)
def panel():
    try:
        df = cargar()
    except Exception:
        st.error("No se pudo leer la hoja. Revisa el ID y que esté compartida "
                 "con 'Cualquier persona con el enlace'.")
        return

    if df.empty:
        st.info("Aún no hay lecturas.")
        return

    ultima = df.iloc[-1]
    pct = float(ultima["porcentaje"])
    ahora = pd.Timestamp.now(tz="America/Bogota").tz_localize(None)
    segundos = (ahora - ultima["fecha"]).total_seconds()

    col1, col2 = st.columns(2)
    col1.metric("Nivel de llenado", f"{pct:.0f} %")
    col2.metric("Distancia al contenido", f"{ultima['distancia_cm']:.1f} cm")
    st.progress(int(min(max(pct, 0), 100)))

    if pct >= UMBRAL_ALERTA:
        st.error("🔴 Caneca llena: requiere vaciado")
    elif pct >= UMBRAL_ATENCION:
        st.warning("🟠 Atención: nivel medio-alto")
    else:
        st.success("🟢 Nivel normal")

    if segundos > 120:
        st.warning(f"⚠️ Sin lecturas nuevas hace {int(segundos // 60)} min. "
                   "Revisa la alimentación o el WiFi.")
    else:
        st.caption(f"Última lectura hace {int(segundos)} s")

    st.subheader("Historial de llenado")
    st.line_chart(df.set_index("fecha")["porcentaje"].tail(200))


panel()
