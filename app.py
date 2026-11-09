import base64
import html
import math
import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

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
# piso, x, y = dónde se dibuja el punto en el esquema (cuadrícula de 830 x 700).
CANECAS = {
    "C1": {"ubicacion": "Hall de ingreso (planta 1)", "piso": 1, "x": 525, "y": 297,
           "real": True},
    "C2": {"ubicacion": "Exhibición (planta 1)", "piso": 1, "x": 525, "y": 168,
           "nivel": 92, "horas": 9, "fase": 0.2},
    "C3": {"ubicacion": "Plaza (planta 1)", "piso": 1, "x": 420, "y": 440,
           "nivel": 67, "horas": 5, "fase": 0.5},
    "C7": {"ubicacion": "Hall de distribución (planta 1)", "piso": 1, "x": 200, "y": 255,
           "nivel": 30, "horas": 4, "fase": 0.7},
    "C4": {"ubicacion": "Información (planta 4)", "piso": 4, "x": 470, "y": 290,
           "nivel": 18, "horas": 3, "fase": 0.8},
    "C5": {"ubicacion": "Aula de eventos, ingreso (planta 4)", "piso": 4, "x": 590, "y": 285,
           "nivel": 41, "horas": 7, "fase": 0.1},
    "C6": {"ubicacion": "Salones de reuniones (planta 4)", "piso": 4, "x": 646, "y": 64,
           "nivel": 55, "horas": 8, "fase": 0.4, "sin_senal_min": 47},
    "C8": {"ubicacion": "Corredor de aulas (planta 4)", "piso": 4, "x": 165, "y": 500,
           "nivel": 74, "horas": 6, "fase": 0.3},
}

# ----- Esquemas de las plantas (dibujo propio, simplificado) -----
ESTILOS_FORMAS = {
    "edificio": ("#1f2430", "#3a4154"),
    "aula": ("#262c3a", "#4a5268"),
    "local": ("#222836", "#4a5268"),
    "hall": ("#2c3548", "#5a6682"),
    "plaza": ("#1d2b27", "#35564b"),
    "jardin": ("#1b2a1f", "#2f5a3a"),
    "nucleo": ("#303746", "#59627a"),
    "paso": ("#1a1e28", "#2c3344"),
}

PLANTAS = {
    1: {
        "titulo": "Planta 1",
        "formas": [
            ("266,45 540,28 540,144 266,206", "jardin"),
            ("265,392 540,318 540,468 734,468 734,554 265,562", "plaza"),
            ("176,227 540,144 540,310 266,387 176,389", "hall"),
            ("71,229 176,229 176,558 71,569", "local"),
            ("176,389 266,387 266,418 176,418", "nucleo"),
            ("176,418 265,418 265,558 176,558", "local"),
            ("540,27 702,4 702,76 540,76", "local"),
            ("543,79 702,79 702,144 543,144", "paso"),
            ("540,144 630,145 630,310 540,310", "nucleo"),
            ("630,145 702,145 702,310 630,310", "local"),
            ("540,310 702,310 702,389 540,389", "local"),
        ],
        "etiquetas": [
            (123, 400, "Locales"), (221, 492, "Locales"),
            (621, 44, "Locales"), (666, 232, "Locales"), (621, 354, "Locales"),
            (585, 232, "Núcleo"), (400, 100, "Jardín"), (440, 520, "Plaza"),
            (300, 305, "Hall de distribución"), (385, 335, "Hall de ingreso"),
            (470, 238, "Exhibición"),
        ],
    },
    4: {
        "titulo": "Planta 4",
        "formas": [
            ("71,240 266,240 266,608 71,608", "edificio"),
            ("71,245 151,245 151,304 71,304", "aula"),
            ("71,304 151,304 151,363 71,363", "aula"),
            ("71,363 151,363 151,421 71,421", "aula"),
            ("71,475 151,475 151,544 71,544", "aula"),
            ("179,428 266,428 266,481 179,481", "aula"),
            ("179,481 266,481 266,534 179,534", "aula"),
            ("179,534 266,534 266,587 179,587", "aula"),
            ("187,247 259,247 259,274 187,274", "nucleo"),
            ("179,320 266,320 266,382 179,382", "nucleo"),
            ("266,240 547,162 547,320 266,400", "hall"),
            ("543,38 738,9 738,240 543,240", "edificio"),
            ("543,38 630,38 630,86 543,86", "aula"),
            ("662,20 738,9 738,86 662,86", "aula"),
            ("543,86 634,86 634,162 543,162", "nucleo"),
            ("662,86 738,86 738,238 662,238", "aula"),
            ("541,240 756,240 756,506 541,506", "edificio"),
            ("630,284 734,284 734,479 630,479", "aula"),
            ("543,324 630,324 630,464 543,464", "nucleo"),
        ],
        "etiquetas": [
            (111, 278, "Aulas"), (111, 515, "Aulas"), (222, 508, "Aulas"),
            (223, 355, "Baños"), (223, 262, "Núcleo"),
            (400, 345, "Hall · Información"),
            (586, 62, "Salón"), (700, 52, "Salón"), (588, 128, "Baños"),
            (700, 165, "Eventos"), (682, 385, "Aula de eventos"), (587, 398, "Escaleras"),
        ],
    },
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


def color_de(d):
    if d["sin_senal"]:
        return "#9e9e9e"
    if d["pct"] >= UMBRAL_ALERTA:
        return "#e53935"
    if d["pct"] >= UMBRAL_ATENCION:
        return "#fb8c00"
    return "#43a047"


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
    color = color_de(d)
    clase = "roja" if (not d["sin_senal"] and d["pct"] >= UMBRAL_ALERTA) else ""
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


def svg_planta(piso, datos, ruta):
    pl = PLANTAS[piso]
    p = ['<rect width="830" height="700" rx="16" fill="#14171f"/>',
         f'<text x="24" y="38" fill="#e6e9f2" font-size="22" font-weight="700">{pl["titulo"]}</text>']

    for puntos, clase in pl["formas"]:
        relleno, borde = ESTILOS_FORMAS[clase]
        p.append(f'<polygon points="{puntos}" fill="{relleno}" stroke="{borde}" stroke-width="1.5"/>')
    for x, y, texto in pl["etiquetas"]:
        p.append(f'<text x="{x}" y="{y}" fill="#8b93a7" font-size="12" '
                 f'text-anchor="middle">{texto}</text>')

    # Ruta de vaciado (solo las urgentes de esta planta)
    pts = [(CANECAS[c]["x"], CANECAS[c]["y"]) for c in ruta if CANECAS[c]["piso"] == piso]
    if len(pts) > 1:
        linea = " ".join(f"{x},{y}" for x, y in pts)
        p.append(f'<polyline points="{linea}" fill="none" stroke="#ff8a80" '
                 f'stroke-width="3" stroke-dasharray="8 6"/>')

    # Canecas
    for cid, d in datos.items():
        cfg = CANECAS[cid]
        if cfg["piso"] != piso:
            continue
        x, y = cfg["x"], cfg["y"]
        color = color_de(d)
        tip = html.escape(f"{cid} · {cfg['ubicacion']} · {d['pct']:.0f} % · "
                          f"última lectura hace {hace(d['segundos'])}")
        g = [f"<g><title>{tip}</title>"]
        if not d["sin_senal"] and d["pct"] >= UMBRAL_ALERTA:
            g.append(f'<circle cx="{x}" cy="{y}" r="11" fill="none" stroke="{color}" '
                     f'stroke-width="3"><animate attributeName="r" from="11" to="32" '
                     f'dur="1.6s" repeatCount="indefinite"/><animate attributeName="opacity" '
                     f'from="0.9" to="0" dur="1.6s" repeatCount="indefinite"/></circle>')
        dash = ' stroke-dasharray="3 3"' if d["sin_senal"] else ""
        g.append(f'<circle cx="{x}" cy="{y}" r="11" fill="{color}" stroke="#ffffff" '
                 f'stroke-width="2"{dash}/>')
        if cid in ruta:
            n = ruta.index(cid) + 1
            g.append(f'<circle cx="{x - 14}" cy="{y - 14}" r="9" fill="#e53935" '
                     f'stroke="#ffffff" stroke-width="1.5"/>'
                     f'<text x="{x - 14}" y="{y - 10}" fill="#ffffff" font-size="11" '
                     f'font-weight="700" text-anchor="middle">{n}</text>')
        marca = "" if d["real"] else " 🧪"
        valor = "sin señal" if d["sin_senal"] else f"{d['pct']:.0f} %"
        g.append(f'<text x="{x + 17}" y="{y + 5}" fill="#ffffff" font-size="14" '
                 f'font-weight="700" stroke="#14171f" stroke-width="4" '
                 f'paint-order="stroke">{cid}{marca} · {valor}</text>')
        g.append("</g>")
        p.append("".join(g))

    # Leyenda
    items = [("#43a047", "Normal"), ("#fb8c00", "Atención"),
             ("#e53935", "Llena"), ("#9e9e9e", "Sin señal")]
    for i, (c, t) in enumerate(items):
        lx = 24 + i * 130
        p.append(f'<circle cx="{lx}" cy="675" r="7" fill="{c}"/>'
                 f'<text x="{lx + 14}" y="680" fill="#8b93a7" font-size="13">{t}</text>')
    return "".join(p)


def vista_planta(piso, datos, ruta):
    svg = svg_planta(piso, datos, ruta)
    doc = ('<html><body style="margin:0;background:transparent;font-family:sans-serif">'
           '<svg viewBox="0 0 830 700" xmlns="http://www.w3.org/2000/svg" '
           'font-family="sans-serif" '
           'style="width:100%;max-width:860px;display:block;margin:0 auto">'
           f'{svg}</svg></body></html>')
    components.html(doc, height=730)


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
    ruta_ids = [cid for cid, _ in urgentes]
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

    # ----- Ubicación en el edificio -----
    st.subheader("🗺️ Ubicación en el edificio")
    rojas = {p: sum(1 for c in ruta_ids if CANECAS[c]["piso"] == p) for p in PLANTAS}
    piso = st.radio(
        "Planta", list(PLANTAS.keys()), horizontal=True, key="piso_vista",
        format_func=lambda p: f"Planta {p}" + (f"  ·  🔴 {rojas[p]}" if rojas[p] else ""),
    )
    vista_planta(piso, datos, ruta_ids)

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
