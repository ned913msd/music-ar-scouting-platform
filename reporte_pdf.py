#!/usr/bin/env python3
# ============================================================================
# reporte_pdf.py
# A&R Scouting Command Center | Informe Ejecutivo PDF (fpdf2 + matplotlib)
#
# Qué hace:
#   Genera el entregable ejecutivo de un artista (para juntas de sello,
#   comités A&R o inversores) como PDF profesional: foto, KPIs, veredicto,
#   analytics multi-plataforma (gráfico estático), insights estratégicos y
#   recomendación de gira (motor touring_engine).
#
# Render-safe:
#   TODO se produce EN MEMORIA (io.BytesIO). El PDF nunca toca el disco del
#   servidor: Render usa un filesystem efímero que se destruye en cada deploy.
#
# Gráfico estático (por qué matplotlib y no plotly+kaleido):
#   kaleido lanza un Chromium embebido por subproceso para exportar
#   fig.write_image(): ~80MB extra en la imagen de Render y cuelgues
#   documentados del handshake Electron/chromium en hosts headless (verificado
#   en Windows: el proceso hija nunca devuelve el JSON de arranque). El mismo
#   gráfico, mismos datos y misma paleta se renderizan con matplotlib en el
#   proceso principal: determinista en Windows y Linux, sin subprocesos.
#   Plotly sigue siendo el motor interactivo de la web; este módulo es el
#   render "print" del entregable.
#
# Fuentes:
#   fpdf2 con fuentes core (latin-1) rompe con acentos/emojis del español.
#   Se usa DejaVuSans (licencia libre Bitstream Vera, embebida en
#   assets/fonts/, copiada del paquete matplotlib) + saneamiento de emojis
#   (ningún TTF estático los cubre). Si los TTF no están disponibles,
#   degrada con elegancia a fuentes core transliterando acentos.
# ============================================================================

import os
import re
import sys
import unicodedata
from datetime import date
from io import BytesIO

import requests
from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos
from fpdf.fonts import FontFace
from PIL import Image

_DIR_RAIZ = os.path.dirname(os.path.abspath(__file__))
if _DIR_RAIZ not in sys.path:
    sys.path.insert(0, _DIR_RAIZ)
_scripts_dir = os.path.join(_DIR_RAIZ, "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from touring_engine import calcular_ruta_touring, resumen_gira  # noqa: E402

FUENTE_REGULAR = os.path.join(_DIR_RAIZ, "assets", "fonts", "DejaVuSans.ttf")
FUENTE_BOLD = os.path.join(_DIR_RAIZ, "assets", "fonts", "DejaVuSans-Bold.ttf")

# ---------------------------------------------------------------------------
# Paleta coherente con el tema Cyberpunk de la web, versión "print" (página
# blanca: legible impresa y en cualquier visor de PDF corporativo)
# ---------------------------------------------------------------------------
NAVY = (10, 14, 39)        # #0a0e27 — banda de cabecera
AZUL = (0, 102, 255)       # #0066FF — acento primario
CIAN = (0, 206, 209)       # #00CED1 — acento secundario
TEXTO = (30, 41, 59)       # slate-800
GRIS = (100, 116, 139)     # slate-500
GRIS_LINEA = (203, 213, 225)  # slate-300
FONDO_SUAVE = (241, 245, 249)  # slate-100
ROJO = (220, 38, 38)       # veredicto FIRMAR
AMBAR = (217, 119, 6)      # veredicto OBSERVAR
GRIS_MEDIO = (107, 114, 128)   # veredicto DESCARTAR

_RE_EMOJIS = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # emojis y símbolos suplementarios (🔥👀🎧…)
    "\U00002700-\U000027BF"   # dingbats (✨✅…)
    "\U00002600-\U000026FF"   # símbolos misceláneos (⚠…)
    "\U00002B00-\U00002BFF"   # flechas/símbolos (⭐…)
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U0000200D"              # zero-width joiner (emojis compuestos)
    "\U00002190-\U00002199"   # flechas simples (←)
    "]+"
)

_FUENTES_TTF_DISPONIBLES = os.path.exists(FUENTE_REGULAR) and os.path.exists(
    FUENTE_BOLD
)


def _limpiar(texto):
    """Sanea texto para el PDF: fuera emojis (ningún TTF los cubre) y, si se
    degradó a fuentes core latin-1, translitera acentos (á→a, ñ→n…)."""
    if texto is None:
        return ""
    t = str(texto).replace("\u2192", "->").replace("\u2190", "<-")
    t = _RE_EMOJIS.sub("", t)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    if not _FUENTES_TTF_DISPONIBLES:
        t = (
            unicodedata.normalize("NFKD", t)
            .encode("latin-1", "ignore")
            .decode("latin-1")
        )
    return t


def _set_fuente(pdf, estilo="", tam=10):
    """Wrapper de set_font que respeta la degradación de fuentes."""
    familia = "DejaVu" if _FUENTES_TTF_DISPONIBLES else "helvetica"
    pdf.set_font(familia, estilo, tam)


def _num(valor):
    """Formatea enteros con separador de miles estilo ejecutivo (1,234,567)."""
    try:
        return f"{int(float(valor)):,}"
    except (TypeError, ValueError):
        return "—"


# ---------------------------------------------------------------------------
# PIE DE PÁGINA
# ---------------------------------------------------------------------------
class _InformePDF(FPDF):
    def footer(self):
        self.set_y(-13)
        _set_fuente(self, "", 7.5)
        self.set_text_color(*GRIS)
        self.cell(
            self.epw * 0.72,
            5,
            _limpiar("A&R Scouting Command Center — Informe confidencial generado automáticamente"),
            align=Align.L,
        )
        self.cell(
            self.epw * 0.28,
            5,
            f"{_limpiar('Página')} {self.page_no()}",
            align=Align.R,
        )


# ---------------------------------------------------------------------------
# PIEZAS DE LAYOUT
# ---------------------------------------------------------------------------
def _garantizar_espacio(pdf, mm_necesarios):
    """Salto de página manual si el bloque siguiente no cabe (fpdf2 no parte
    rects/badges: los partiría en dos páginas visiblemente rotos)."""
    if pdf.get_y() > pdf.h - pdf.b_margin - mm_necesarios:
        pdf.add_page()


def _seccion(pdf, titulo):
    """Título de sección: barra azul redondeada + titular navy."""
    _garantizar_espacio(pdf, 34)
    pdf.ln(1)
    y = pdf.get_y()
    pdf.set_fill_color(*AZUL)
    pdf.rect(pdf.l_margin, y + 0.6, 1.6, 6.4, style="F", round_corners=True, corner_radius=0.8)
    pdf.set_xy(pdf.l_margin + 4, y)
    _set_fuente(pdf, "B", 13)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7.6, _limpiar(titulo), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1.5)


def _badge(pdf, x, y, texto, color, tam=11):
    """Pill de veredicto con fondo de color y texto blanco centrado."""
    texto = _limpiar(texto)
    _set_fuente(pdf, "B", tam)
    ancho = pdf.get_string_width(texto) + 8
    pdf.set_fill_color(*color)
    pdf.rect(x, y, ancho, 8.4, style="F", round_corners=True, corner_radius=4.2)
    pdf.set_xy(x, y + 1.1)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(ancho, 6.2, texto, align=Align.C)
    return ancho


def _caja_kpi(pdf, x, y, w, h, etiqueta, valor):
    """Mini-card de KPI (fondo slate claro, borde slate, cifra navy)."""
    pdf.set_fill_color(*FONDO_SUAVE)
    pdf.set_draw_color(*GRIS_LINEA)
    pdf.set_line_width(0.2)
    pdf.rect(x, y, w, h, style="DF", round_corners=True, corner_radius=2.5)
    pdf.set_xy(x, y + 3.2)
    _set_fuente(pdf, "", 7)
    pdf.set_text_color(*GRIS)
    pdf.cell(w, 3.5, _limpiar(etiqueta).upper(), align=Align.C)
    pdf.set_xy(x, y + 7.4)
    _set_fuente(pdf, "B", 12)
    pdf.set_text_color(*NAVY)
    pdf.cell(w, 5.5, _limpiar(str(valor)), align=Align.C)


def _bullets(pdf, items, w=None):
    """Lista con viñeta clásica (DejaVu cubre '•'; en core se translitera)."""
    if w is None:
        w = pdf.epw
    viñeta = "•" if _FUENTES_TTF_DISPONIBLES else "-"
    for item in items:
        item = _limpiar(item)
        if not item:
            continue
        _garantizar_espacio(pdf, 16)
        pdf.set_text_color(*TEXTO)
        _set_fuente(pdf, "", 9.5)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            w,
            5.4,
            f"{viñeta}  {item}",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.ln(1.2)


# ---------------------------------------------------------------------------
# DATOS: FOTO + GRÁFICO PLOTLY
# ---------------------------------------------------------------------------
def _foto_cuadrada(url):
    """Descarga la foto de la CDN de Deezer y la recorta al centro en un
    cuadrado (fpdf estira si el aspect ratio no coincide). Devuelve BytesIO
    JPEG o None si la CDN falla (el layout dibuja un placeholder)."""
    try:
        resp = requests.get(url, timeout=6)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        lado = min(img.size)
        x0 = (img.width - lado) // 2
        y0 = (img.height - lado) // 2
        img = img.crop((x0, y0, x0 + lado, y0 + lado)).resize((520, 520), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=90)
        buf.seek(0)
        return buf
    except Exception:
        return None


def _figura_plataformas(artista):
    """Gráfico estático de alcance por plataforma en TEMA CLARO (el tema
    oscuro de la web deja texto gris claro invisible sobre la página blanca
    del PDF). Mismos factores de industria declarados en el perfil de la app.
    Matplotlib in-process: ver justificación en el docstring del módulo."""
    import matplotlib

    matplotlib.use("Agg")  # backend sin pantalla: seguro en Render
    import matplotlib.pyplot as plt

    fans = float(artista["deezer_fans"])
    rank = float(artista["deezer_rank"])
    datos = [
        ("Spotify", fans * 1.5, "#1DB954"),
        ("YouTube", rank * 2.5, "#FF0000"),
        ("Apple Music", fans * 0.8, "#FA243C"),
        ("TikTok", rank * 5, "#111111"),
        ("Deezer (real)", fans, "#00CED1"),
    ]

    fig, ax = plt.subplots(figsize=(8.6, 3.5), dpi=150)
    nombres = [d[0] for d in datos]
    valores = [d[1] for d in datos]
    colores = [d[2] for d in datos]
    barras = ax.bar(nombres, valores, color=colores, width=0.62)

    ax.set_yscale("log")
    ax.set_title(
        "Alcance estimado por plataforma (escala log)",
        fontsize=11,
        color="#0f172a",
        loc="left",
        pad=12,
        fontweight="bold",
    )
    ax.set_ylabel("Alcance estimado (log)", fontsize=8.5, color="#475569")
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(colors="#334155", labelsize=9)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#CBD5E1")

    # Cifras sobre cada barra (mismo dato que la tabla: trazabilidad)
    for barra, v in zip(barras, valores):
        ax.annotate(
            _num(v),
            (barra.get_x() + barra.get_width() / 2, v),
            ha="center",
            va="bottom",
            fontsize=7.5,
            color="#0f172a",
            xytext=(0, 2),
            textcoords="offset points",
        )

    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# SECCIONES DEL INFORME
# ---------------------------------------------------------------------------
def _encabezado(pdf, fecha_larga):
    """Banda navy a sangre con la identidad del producto."""
    pdf.set_fill_color(*NAVY)
    pdf.rect(-1, -1, pdf.w + 2, 27, style="F")
    pdf.set_y(4.5)
    _set_fuente(pdf, "", 8)
    pdf.set_text_color(*CIAN)
    pdf.cell(
        pdf.epw,
        4,
        "A&R SCOUTING COMMAND CENTER  ·  PLATAFORMA SaaS DE SCOUTING MUSICAL",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_y(9.5)
    _set_fuente(pdf, "B", 16.5)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(pdf.epw, 8, "INFORME EJECUTIVO DE SCOUTING ARTISTA", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(18.5)
    _set_fuente(pdf, "", 8)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(
        pdf.epw,
        4,
        _limpiar(f"Generado: {fecha_larga}  ·  Fuente: Deezer API (mart artist_scouting_deezer)  ·  Documento confidencial"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )


def _bloque_artista(pdf, artista):
    """Foto cuadrada a la derecha; nombre, veredicto y metadatos a la izquierda."""
    y0 = 31.5
    alto_foto = 46
    ancho_foto = 46
    x_foto = pdf.l_margin + pdf.epw - ancho_foto

    foto = _foto_cuadrada(artista.get("picture_url", ""))
    if foto is not None:
        pdf.image(foto, x=x_foto, y=y0, w=ancho_foto, h=alto_foto)
    else:
        # Placeholder: caja slate con las iniciales del artista
        pdf.set_fill_color(*FONDO_SUAVE)
        pdf.set_draw_color(*GRIS_LINEA)
        pdf.rect(x_foto, y0, ancho_foto, alto_foto, style="DF", round_corners=True, corner_radius=3)
        iniciales = "".join(p[0] for p in str(artista["artist_name"]).split()[:2]).upper() or "??"
        pdf.set_xy(x_foto, y0 + alto_foto / 2 - 6)
        _set_fuente(pdf, "B", 18)
        pdf.set_text_color(*GRIS)
        pdf.cell(ancho_foto, 10, iniciales, align=Align.C)

    ancho_texto = pdf.epw - ancho_foto - 6
    pdf.set_xy(pdf.l_margin, y0)
    _set_fuente(pdf, "B", 23)
    pdf.set_text_color(*NAVY)
    pdf.multi_cell(ancho_texto, 10.5, _limpiar(artista["artist_name"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    y = pdf.get_y() + 1.5

    veredicto, color = _veredicto(str(artista.get("ar_recommendation", "")))
    _set_fuente(pdf, "B", 11)
    y = y
    _badge(pdf, pdf.l_margin, y, veredicto, color)
    y += 11.5

    pdf.set_xy(pdf.l_margin, y)
    _set_fuente(pdf, "", 9.5)
    pdf.set_text_color(*TEXTO)
    lineas = [
        f"Género: {artista.get('genero', 'N/A')}   ·   Top Track: {artista.get('top_track_name', 'N/A')}",
        f"Fans Deezer: {_num(artista['deezer_fans'])}   ·   Rank Deezer: {_num(artista['deezer_rank'])}",
        _limpiar(f"Perfil en Deezer: {artista.get('deezer_link', '')}"),
    ]
    pdf.multi_cell(ancho_texto, 5.6, "\n".join(lineas), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    y_foto_fin = y0 + alto_foto + 4
    pdf.set_y(max(pdf.get_y(), y_foto_fin) + 2)


def _veredicto(recomendacion):
    """(texto_impreso, color) según la recomendación A&R del mart."""
    if "FIRMAR" in recomendacion:
        return "VEREDICTO: FIRMAR AHORA", ROJO
    if "OBSERVAR" in recomendacion:
        return "VEREDICTO: OBSERVACIÓN ACTIVA", AMBAR
    return "VEREDICTO: SIN PRIORIDAD", GRIS_MEDIO


def _kpis_ejecutivos(pdf, artista):
    prob = float(artista.get("probabilidad_viral", 0) or 0)
    kpis = [
        ("Scouting Score", f"{float(artista['scouting_score']):.0f}/100"),
        ("Prob. Viralidad 6M (ML)", f"{prob:.1f}%"),
        ("Fans Deezer", _num(artista["deezer_fans"])),
        ("Rank Deezer", _num(artista["deezer_rank"])),
    ]
    y = pdf.get_y()
    gap = 4
    w = (pdf.epw - gap * 3) / 4
    for i, (etiqueta, valor) in enumerate(kpis):
        _caja_kpi(pdf, pdf.l_margin + i * (w + gap), y, w, 17.5, etiqueta, valor)
    pdf.set_y(y + 17.5 + 3)


def _veredicto_detallado(pdf, artista):
    insight_mart = _limpiar(artista.get("strategic_insight", "")) or "Sin insight del mart."
    _garantizar_espacio(pdf, 26)
    pdf.set_fill_color(*FONDO_SUAVE)
    pdf.set_draw_color(*GRIS_LINEA)
    pdf.set_line_width(0.2)
    y0 = pdf.get_y()
    # Alto estimado: 3 líneas de texto + padding (insights del mart son cortos)
    alto = 20
    pdf.rect(pdf.l_margin, y0, pdf.epw, alto, style="DF", round_corners=True, corner_radius=2.5)
    pdf.set_xy(pdf.l_margin + 4, y0 + 3)
    _set_fuente(pdf, "B", 9.5)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 5, _limpiar("Lectura del comité A&R"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(pdf.l_margin + 4)
    pdf.set_text_color(*TEXTO)
    _set_fuente(pdf, "", 9.5)
    pdf.multi_cell(pdf.epw - 8, 5.4, insight_mart, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(max(pdf.get_y(), y0 + alto) + 4)


def _tabla_plataformas(pdf, artista):
    fans = float(artista["deezer_fans"])
    rank = float(artista["deezer_rank"])
    filas = [
        ("Spotify", "Monthly Listeners", fans * 1.5, "fans x 1.5 (líder de mercado)"),
        ("YouTube", "Subscribers", rank * 2.5, "rank x 2.5 (alcance audio+video)"),
        ("Apple Music", "Followers", fans * 0.8, "fans x 0.8 (base menor, engagement alto)"),
        ("TikTok", "Followers", rank * 5, "rank x 5 (viralidad exponencial)"),
        ("Deezer", "Fans (dato REAL)", fans, "dato real de la API"),
    ]
    # Fuente del cuerpo EXPLÍCITA: la tabla hereda la fuente vigente y un
    # bold grande previo envolvía las cifras en dos líneas
    _set_fuente(pdf, "", 9)
    encabezado_estilo = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=NAVY)
    pdf.set_draw_color(*GRIS_LINEA)
    pdf.set_line_width(0.2)
    with pdf.table(
        col_widths=(38, 46, 38, 60),
        text_align=("LEFT", "LEFT", "RIGHT", "LEFT"),
        line_height=5.6,
        padding=1.4,
        headings_style=encabezado_estilo,
        cell_fill_color=FONDO_SUAVE,
        cell_fill_mode="ROWS",
    ) as tabla:
        fila = tabla.row()
        for c in ("Plataforma", "Métrica", "Alcance est.", "Base del cálculo"):
            fila.cell(c)
        for nombre, metrica, valor, base in filas:
            fila = tabla.row()
            fila.cell(_limpiar(nombre))
            fila.cell(_limpiar(metrica))
            fila.cell(_num(valor))
            fila.cell(_limpiar(base))
    pdf.ln(1.5)
    _set_fuente(pdf, "", 7.5)
    pdf.set_text_color(*GRIS)
    pdf.multi_cell(
        pdf.epw,
        4.4,
        _limpiar(
            "Estimaciones con factores de industria 2026 aplicados a métricas REALES de Deezer: su API "
            "pública no expone datos de la competencia. En producción: conectores de YouTube Data API, "
            "TikTok Research API y Apple Music API."
        ),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )


def _grafico_plataformas(pdf, artista):
    """Inserta el gráfico estático (PNG matplotlib en memoria). Si el render
    fallara en algún entorno, el PDF sigue con el resto de secciones."""
    try:
        pdf.image(_figura_plataformas(artista), x=pdf.l_margin, w=pdf.epw)
    except Exception as e:
        _set_fuente(pdf, "", 8.5)
        pdf.set_text_color(*GRIS)
        pdf.multi_cell(
            pdf.epw,
            5,
            _limpiar(f"(Visualización no disponible en este entorno: {e})"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    pdf.ln(2)


def _insights(pdf, artista):
    fans = float(artista["deezer_fans"])
    rank = float(artista["deezer_rank"])
    prob = float(artista.get("probabilidad_viral", 0) or 0)

    items = []

    insight_mart = _limpiar(artista.get("strategic_insight", ""))
    if insight_mart:
        items.append(f"Señal del pipeline: {insight_mart}.")

    # Dominancia de plataforma (misma lógica que el perfil de la app)
    alcance = {
        "Spotify": fans * 1.5,
        "YouTube": rank * 2.5,
        "Apple Music": fans * 0.8,
        "TikTok": rank * 5,
        "Deezer": fans,
    }
    dominante = max(alcance, key=alcance.get)
    ratio_yt = (rank * 2.5) / max(fans, 1)
    enfoque = (
        "la apuesta es contenido en video (YouTube/TikTok)"
        if ratio_yt > 3
        else "la apuesta es streaming de audio (Spotify/Apple Music)"
    )
    items.append(
        f"Plataforma dominante: {dominante}. Ratio YouTube/Deezer de {ratio_yt:.1f}x "
        f"({ 'por encima' if ratio_yt > 3 else 'por debajo' } del umbral 3x): {enfoque}."
    )

    lectura_ml = (
        "señal fuerte: acelerar due diligence y contacto"
        if prob >= 50
        else "señal moderada: monitorear evolución semanal antes de mover recursos"
    )
    items.append(
        f"Machine Learning (RandomForest, ROC-AUC 0.9242): {prob:.1f}% de probabilidad de "
        f"viralidad a 6 meses — {lectura_ml}."
    )

    if "est_alcance_max" in getattr(artista, "index", []):
        items.append(
            f"Alcance máximo estimado multi-plataforma: {_num(artista['est_alcance_max'])} "
            "personas — dimensiona el techo del artista para pricing de la firma."
        )

    _bullets(pdf, items)


def _recomendacion_gira(pdf, artista):
    """KPIs de gira + tabla top-5 mercados con el motor real de Touring."""
    df_touring = calcular_ruta_touring(
        str(artista["artist_name"]),
        int(artista["deezer_fans"]),
        int(artista["deezer_rank"]),
    )
    resumen = resumen_gira(df_touring)

    y = pdf.get_y()
    gap = 4
    w = (pdf.epw - gap * 3) / 4
    kpis = [
        ("ROI bruto proyectado", f"${_num(resumen['roi_total_usd'])}"),
        ("Asistentes totales", _num(resumen["total_asistentes"])),
        ("Mercado ancla", _limpiar(resumen["mercado_top"].split(",")[0])),
        ("Venues viables", f"{resumen['venues_viables']}/8"),
    ]
    for i, (etiqueta, valor) in enumerate(kpis):
        _caja_kpi(pdf, pdf.l_margin + i * (w + gap), y, w, 17.5, etiqueta, valor)
    pdf.set_y(y + 17.5 + 4)

    # Fuente del cuerpo EXPLÍCITA (ver nota en _tabla_plataformas)
    _set_fuente(pdf, "", 9)
    encabezado_estilo = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=NAVY)
    pdf.set_draw_color(*GRIS_LINEA)
    pdf.set_line_width(0.2)
    with pdf.table(
        col_widths=(50, 50, 28, 22, 32),
        text_align=("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"),
        line_height=5.6,
        padding=1.4,
        headings_style=encabezado_estilo,
        cell_fill_color=FONDO_SUAVE,
        cell_fill_mode="ROWS",
    ) as tabla:
        fila = tabla.row()
        for c in ("Ciudad", "Venue recomendado", "Asistentes", "Ticket", "ROI bruto"):
            fila.cell(c)
        for _, mrow in df_touring.head(5).iterrows():
            fila = tabla.row()
            fila.cell(_limpiar(mrow["ciudad"]))
            fila.cell(_limpiar(mrow["venue_recomendado"]))
            fila.cell(_num(mrow["asistentes_estimados"]))
            fila.cell(f"${int(mrow['ticket_price_usd'])}")
            fila.cell(f"${_num(mrow['roi_estimado_usd'])}")

    pdf.ln(2)
    _set_fuente(pdf, "", 8)
    pdf.set_text_color(*GRIS)
    pdf.multi_cell(
        pdf.epw,
        4.4,
        _limpiar(
            f"Plan de ruta: abrir por {resumen['mercado_top']} ({_num(resumen['asistentes_top'])} asistentes "
            f"estimados) y escalar por tamaño de mercado. Metodología: reparto proporcional conservativo de los "
            f"{_num(artista['deezer_fans'])} fans reales de Deezer entre 8 mercados clave, conversión fan→ticket del 2% "
            "(-20% fuera del top 400k de rank) y ticket por tier de venue. Simulación determinista: mismo artista -> misma gira."
        ),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )


# ---------------------------------------------------------------------------
# API PÚBLICA DEL MÓDULO
# ---------------------------------------------------------------------------
def generar_reporte_pdf(artista) -> bytes:
    """Genera el Informe Ejecutivo PDF de un artista, 100% en memoria.

    Args:
        artista: fila (pandas Series o dict) del mart `artist_scouting_deezer`
            con las columnas que produce la app (incl. probabilidad_viral y
            est_alcance_max calculadas en tiempo real).

    Returns:
        bytes del PDF (para st.download_button). NUNCA se escribe a disco:
        Render tiene un filesystem efímero y el PDF viaja directo al browser.
    """
    meses = (
        "enero febrero marzo abril mayo junio julio agosto septiembre "
        "octubre noviembre diciembre"
    ).split()
    hoy = date.today()
    fecha_larga = f"{hoy.day} de {meses[hoy.month - 1]} de {hoy.year}"

    pdf = _InformePDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(left=14, top=14, right=14)
    pdf.set_auto_page_break(auto=True, margin=18)
    if _FUENTES_TTF_DISPONIBLES:
        pdf.add_font("DejaVu", "", FUENTE_REGULAR)
        pdf.add_font("DejaVu", "B", FUENTE_BOLD)
    pdf.set_title(f"Informe Ejecutivo — {artista['artist_name']}")
    pdf.set_author("A&R Scouting Command Center")
    pdf.set_creator("A&R Scouting Command Center (fpdf2 + matplotlib)")

    pdf.add_page()
    _encabezado(pdf, fecha_larga)
    _bloque_artista(pdf, artista)
    _kpis_ejecutivos(pdf, artista)

    _seccion(pdf, "Veredicto A&R")
    _veredicto_detallado(pdf, artista)

    _seccion(pdf, "Analytics Multi-Plataforma (estimado)")
    _tabla_plataformas(pdf, artista)
    _garantizar_espacio(pdf, 85)
    _grafico_plataformas(pdf, artista)

    _seccion(pdf, "Insights Estratégicos")
    _insights(pdf, artista)

    _seccion(pdf, "Recomendación de Gira")
    _recomendacion_gira(pdf, artista)

    return bytes(pdf.output())
