# -*- coding: utf-8 -*-
"""Arma el tablero de FEMÓNOE: una sola página, sin servidor y sin tokens.

Lee lo que ya hay en el depósito —padrón, series, alertas, señales y calendario—
y escribe `tablero/index.html` con los datos adentro, para que abra con doble
clic y para que el robot la pueda regenerar todos los días.

Qué muestra, y por qué en ese orden:

1. **El mosaico de los 33 y el mapa al lado**, que son la entrada.
2. **Las alertas**, cada una con la chispa de 30 días de la serie que la disparó
   —con su umbral punteado— y la barra de plazo.
3. **El marcador por banda de Kent**: de las que la casa dijo «probable»,
   cuántas ocurrieron.
4. **El calendario institucional.**
5. **La ficha de cada Estado**, que se abre al tocar su celda o su país en el
   mapa.

Identidad: manual de la casa, sin un solo color de fuera. Fondo claro, franja
blanca con el logotipo enlazado y la línea violeta, y **el naranja reservado** a
la alerta vencida sin evidencia suficiente.

  python tablero.py          escribe tablero/index.html
"""
import csv
import json
import shutil
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from disarm import lectura as lectura_disarm  # noqa: E402
import zonas as _zonas  # noqa: E402

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "tablero"
SERIES = RAIZ / "datos" / "series"
GEO = SALIDA / "geo" / "paises-alc.geojson"
PADRON = json.loads((RAIZ / "padron.json").read_text(encoding="utf-8"))["estados"]
# El nombre de cada Estado por su ISO3. Lo usan el reparto de las alertas de
# zona y el horizonte; faltaba, y el reparto habría reventado al dibujar la
# primera alerta de zona.
NOMBRE = {p["iso3"]: p["nombre"] for p in PADRON}
CONF = json.loads((RAIZ / "umbrales.json").read_text(encoding="utf-8"))
# La pastilla de cada eje en el mosaico de los 33. Eran las iniciales sueltas
# —G, S, I— y la dirección las señaló el 2/10/2026: nadie decodifica una letra,
# y la del eje informativo era «I» de *informativo* cuando la palabra que el
# lector ve en todos lados es «entorno». Tres o cuatro letras entran igual en la
# celda y se adivinan; el nombre entero sigue en el `title`.
EJES = [("gobernabilidad", "Gob"), ("seguridad", "Seg"), ("entorno informativo", "Info")]
FUNDACION = ("https://fundacionkent.org/?utm_source=femonoe&amp;utm_medium=referral"
             "&amp;utm_campaign=tablero")
SIWA = "https://siwa.fundacionkent.org/sitio/pais/{slug}.html"
BANDAS = ["casi con certeza", "muy probable", "probable", "posibilidades parejas",
          "improbable", "muy improbable", "casi con certeza no"]
FALTA = "COMPLETAR"

# Paleta del manual. Ningún valor de fuera.
COLORES = {
    "azul": "#00121E",           # azul profundo · texto y titulares
    "fondo": "#F9F9F7",          # el fondo claro del sistema
    "superficie": "#FFFFFF",     # tarjetas y franja, como la web institucional
    "linea": "#DDE2E5",          # neutro de líneas
    "violeta": "#8C00E0",        # acento sobre claro (6,6:1)
    "violeta-claro": "#BA66EC",  # relleno y filetes, nunca texto chico
    "violeta-profundo": "#460070",
    "acero": "#667B89",          # filetes y texto grande
    "texto2": "#5A6E7B",         # texto chico sobre claro (5,3:1)
    "naranja": "#FB6500",        # RESERVADO: vencida sin evidencia suficiente
}


# --------------------------------------------------------------------------
# Lo que hay en el depósito
# --------------------------------------------------------------------------
ES_ALERTA = re.compile(r"^\d{4}-\d{2}-\d{2}-[A-Z]{3}-[GSI]$")


def _alertas():
    carpeta = RAIZ / "alertas"
    if not carpeta.exists():
        return []
    return sorted((json.loads(f.read_text(encoding="utf-8"))
                   for f in carpeta.glob("*.json") if ES_ALERTA.match(f.stem)),
                  key=lambda a: a["nace"], reverse=True)


def _calendario(tope=12):
    f = RAIZ / "calendario.json"
    if not f.exists():
        return []
    hoy = date.today()
    limite = hoy.replace(year=hoy.year + 1).isoformat()
    return [e for e in json.loads(f.read_text(encoding="utf-8"))
            if hoy.isoformat() <= e["fecha"] <= limite][:tope]


def _senales_recientes(dias=14):
    """Lo que el robot marcó en los últimos días, por país. Una señal no es una
    alerta: en la ficha se muestra como lo que es, materia prima."""
    salida = {}
    for archivo in sorted((RAIZ / "senales").glob("2*.json"))[-dias:]:
        registro = json.loads(archivo.read_text(encoding="utf-8"))
        for s in registro["senales"]:
            detalle = "; ".join(
                x.get("detalle") or f"valor {x.get('valor')} contra mediana {x.get('mediana')}"
                for x in s["senales"])
            salida.setdefault(s["iso3"], []).append(
                {"fecha": registro["fecha"], "eje": s["eje"], "detalle": detalle,
                 "familias": s["familias"]})
    for lista in salida.values():
        lista.sort(key=lambda x: x["fecha"], reverse=True)
    return salida


def _estado_fuentes():
    """Cuántas fuentes del padrón respondieron en la última verificación. Es la
    barra honesta: el lector tiene que poder ver si el tablero está mirando con
    todos los ojos o con la mitad."""
    f = RAIZ / "datos" / "verificacion.json"
    padron = json.loads((RAIZ / "redes.json").read_text(encoding="utf-8"))
    total = sum(len(padron.get(k, [])) for k in ("rss", "youtube", "telegram", "mastodon"))
    if not f.exists():
        return {"cifra": "—", "total": str(total), "fecha": "sin verificar todavía",
                "alerta": True}
    d = json.loads(f.read_text(encoding="utf-8"))
    return {"cifra": str(d["vivas"]), "total": str(d["revisadas"]),
            "fecha": d["fecha"],
            "alerta": d.get("con_problema", 0) > d.get("revisadas", 1) * 0.15}


def _ultima_corrida():
    senales = sorted((RAIZ / "senales").glob("2*.json"))
    return senales[-1].stem if senales else "sin corridas"


def _serie(senal, iso3, hasta, dias=30):
    """Los últimos 30 días de una serie, con los huecos en cero: la serie es
    diaria y un día sin dato es un día sin novedad."""
    archivo = SERIES / f"{senal}.csv"
    if not archivo.exists():
        return []
    desde = hasta - timedelta(days=dias)
    valores = {}
    with archivo.open(encoding="utf-8") as fh:
        for fila in csv.DictReader(fh):
            if fila.get("iso3") != iso3:
                continue
            try:
                d = date.fromisoformat(fila["fecha"])
            except (ValueError, KeyError):
                continue
            if desde <= d <= hasta:
                valores[d] = float(fila["valor"] or 0)
    return [valores.get(desde + timedelta(days=k), 0.0) for k in range(dias + 1)]


def _escapar(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _slug(nombre):
    base = unicodedata.normalize("NFD", nombre).encode("ascii", "ignore").decode()
    return base.lower().replace(" ", "-")


# --------------------------------------------------------------------------
# 1 · La chispa: la serie que disparó la alerta, con su umbral
# --------------------------------------------------------------------------
def _aviso_descarte(a):
    """Lo que se le dice al lector cuando una alerta fue descartada.

    **Por qué hizo falta.** El motivo del descarte se registraba entero en el
    expediente y **no se mostraba en ninguna parte**: la página de una alerta
    descartada se leía igual que la de una viva, con un «descartada» chico al
    lado del país. La dirección lo leyó así el 2/10/2026 y preguntó por qué
    Haití no figuraba activa en el tablero —y tenía razón en preguntar, porque
    la página no decía lo que había pasado—.

    Una alerta descartada **no es un error que se esconde**: es el método
    funcionando. Se muestra con su motivo, firmada y fechada.
    """
    d = a.get("descarte") or {}
    if a.get("estado") != "descartada":
        return ""
    quien = _escapar(d.get("por", "la dirección"))
    cuando = _escapar(d.get("fecha", ""))
    motivo = _negritas(d.get("motivo", ""))
    return ('<div class="descarte" role="note">'
            '<b>Esta alerta no se publicó: fue descartada antes de salir.</b> '
            f'La descartó <b>{quien}</b>{f" el {cuando}" if cuando else ""}. '
            'Queda en el registro porque el disenso que la frenó es parte del '
            'método, no un borrador que convenga borrar.'
            + (f'<p>{motivo}</p>' if motivo else "") + '</div>')


def _dia_mes(iso):
    """«2026-10-02» a «2 oct». Si no se entiende, se devuelve tal cual."""
    try:
        f = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return str(iso or "")
    return f"{f.day} {MESES_CORTOS[f.month - 1]}"


MESES_CORTOS = ("ene", "feb", "mar", "abr", "may", "jun",
                "jul", "ago", "sep", "oct", "nov", "dic")


def _figura(valores, mediana=None, desde=None, hasta=None, vivo=False,
            alto=48, unidad=""):
    """La serie con su escala, que es lo que la vuelve legible.

    **Por qué hizo falta.** Hasta el 2/10/2026 la figura era una línea sin un
    solo número: decía «la línea punteada marca la mediana de Haití» y no decía
    cuánto vale esa mediana, ni cuál es el máximo, ni qué días cubre. La
    dirección preguntó dónde estaban los ejes, y tenía razón: **una figura que
    no se puede leer es un adorno**, por más que los datos de atrás sean ciertos.

    **La escala va en HTML y no adentro del SVG.** El dibujo se estira con
    `preserveAspectRatio="none"` para ocupar su caja, y un `<text>` adentro se
    estiraría con él y saldría deformado. Afuera queda nítido y se adapta.
    """
    svg = _chispa(valores, mediana, alto=alto, vivo=vivo)
    if not svg:
        return ""
    tope = max(valores)
    med = ""
    if mediana is not None:
        # La mediana se rotula a la altura de su propia línea, para que el
        # número y la línea punteada se lean como una sola cosa.
        alto_rel = 1 - (min(float(mediana), tope) / tope if tope else 0)
        med = (f'<span class="rot-mediana" style="--y:{alto_rel * 100:.1f}%">'
               f'mediana {float(mediana):.0f}</span>')
    fechas = ""
    if desde or hasta:
        fechas = (f'<div class="eje-x"><span>{_escapar(_dia_mes(desde))}</span>'
                  f'<span>{_escapar(_dia_mes(hasta))}</span></div>')
    return (f'<div class="serie">'
            f'<div class="eje-y"><span>{tope:.0f}</span>'
            f'<span class="unidad">{_escapar(unidad)}</span><span>0</span></div>'
            f'<div class="trama">{svg}{med}</div>'
            f'{fechas}</div>')


def _negritas(texto):
    """Escapa y convierte las **negritas** de Markdown en <b>.

    La Oficina escribe los fundamentos y los dictámenes con `**` porque así se
    redactan en el expediente. Si sólo se escapa, los asteriscos salen crudos a
    la página: medido el 2/10/2026 había diez en la alerta de Haití, incluido un
    «**más de 628.755 electores inscriptos**» a la vista del lector. Y si se
    convierte sin escapar primero, cualquier `<` del texto entraría como
    etiqueta. Se hace en ese orden, y por eso está en una sola función.
    """
    partes = _escapar(texto).split("**")
    return "".join(x if i % 2 == 0 else f"<b>{x}</b>" for i, x in enumerate(partes))


def _chispa(valores, mediana=None, ancho=250, alto=48, vivo=False):
    """La serie dibujada. Si `vivo`, se traza sola al abrir la página.

    **Por qué se mueve, y qué puede moverse.** La dirección pidió el 2/10/2026
    que el tablero se vea «vivo, latiendo, que evoluciona». La regla que se
    impone la Oficina para cumplirlo sin faltar a la casa es una sola:

        **No se mueve nada que no sea un dato.**

    La línea se traza de izquierda a derecha porque eso **es** la serie: el
    tiempo pasando. El último punto late sólo mientras la alerta está vigente, y
    deja de latir cuando vence. La barra de plazo avanza hasta donde de verdad
    llegó. Nada de esto es adorno: cada movimiento representa algo medido, y si
    el dato no está, el movimiento no ocurre.

    Y se apaga entero con `prefers-reduced-motion`, donde la figura aparece ya
    dibujada. Una animación que no se puede desactivar es una animación que
    excluye gente.
    """
    if not valores or max(valores) <= 0:
        return ""
    margen, tope = 5, max(valores)
    paso = (ancho - 2 * margen) / max(len(valores) - 1, 1)
    alto_util = alto - 2 * margen

    def y(v):
        return margen + alto_util - (v / tope) * alto_util

    puntos = " ".join(f"{margen + i * paso:.1f},{y(v):.1f}" for i, v in enumerate(valores))
    # `preserveAspectRatio="none"` para que la figura ESTIRE hasta el ancho de su
    # caja en vez de quedar centrada y chiquita. En la ficha de un Estado la caja
    # es tres veces más ancha que el dibujo, y sin esto la línea aparecía flotando
    # en el medio. Estirar una serie no la deforma: el eje horizontal es tiempo,
    # y el tiempo no tiene escala propia que respetar.
    partes = [f'<svg class="chispa" viewBox="0 0 {ancho} {alto}" role="img" '
              f'preserveAspectRatio="none" '
              f'aria-label="Los últimos {len(valores)} días de la serie">']
    if mediana is not None and tope > 0:
        yu = y(min(float(mediana), tope))
        partes.append(f'<line x1="{margen}" y1="{yu:.1f}" x2="{ancho - margen}" y2="{yu:.1f}" '
                      f'stroke="var(--acero)" stroke-width="1" stroke-dasharray="3 3"/>')
    # El largo del trazo se calcula acá y se escribe en el atributo: así la
    # línea se dibuja sola sin una línea de JavaScript, y la página sigue siendo
    # un archivo estático que funciona sin red y se imprime bien.
    xs = [margen + i * paso for i in range(len(valores))]
    ys = [y(v) for v in valores]
    largo = sum(((xs[i + 1] - xs[i]) ** 2 + (ys[i + 1] - ys[i]) ** 2) ** 0.5
                for i in range(len(valores) - 1)) or 1
    partes.append(f'<polyline class="trazo" points="{puntos}" fill="none" '
                  f'stroke="var(--violeta)" stroke-width="1.8" stroke-linejoin="round" '
                  f'stroke-linecap="round" stroke-dasharray="{largo:.0f}" '
                  f'style="--largo:{largo:.0f}"/>')
    partes.append(f'<circle class="punta{" late" if vivo else ""}" '
                  f'cx="{margen + (len(valores) - 1) * paso:.1f}" '
                  f'cy="{y(valores[-1]):.1f}" r="3.2" fill="var(--violeta)"/>')
    partes.append("</svg>")
    return "".join(partes)


# --------------------------------------------------------------------------
# 2 · La barra de plazo: cuánto le queda a la alerta
# --------------------------------------------------------------------------
def _plazo(a):
    j = a["juicio"]
    if a["estado"] == "vencida":
        valor = a["resultado"]["valor"]
        clase = {"ocurrio": "ocurrio", "no_ocurrio": "no-ocurrio",
                 "sin_evidencia": "sin-evidencia"}[valor]
        return (f'<div class="plazo"><div class="riel"><span class="lleno {clase}" '
                f'style="width:100%"></span></div>'
                f'<small>{_escapar(a["resultado"]["leyenda"])} · '
                f'cerrada el {a["resultado"]["cerrada"]}</small></div>')
    if a["estado"] != "publicada" or str(j.get("vence", "")).startswith(FALTA):
        return ""
    nace = date.fromisoformat(a.get("publicada", a["nace"]))
    vence = date.fromisoformat(j["vence"])
    total = max((vence - nace).days, 1)
    corridos = min(max((date.today() - nace).days, 0), total)
    quedan = (vence - date.today()).days
    # «Cerca» no es una impresión: es el último quinto del plazo o tres días,
    # lo que llegue antes. Sólo entonces la barra late, y late por eso.
    cerca = quedan <= max(total // 5, 3)
    return (f'<div class="plazo{" cerca" if cerca else ""}"><div class="riel">'
            f'<span class="lleno avanza" style="--hasta:{corridos / total * 100:.0f}%">'
            f'</span></div>'
            f'<small>{corridos} de {total} días · '
            f'{"vence hoy" if quedan == 0 else f"quedan {quedan} días"}</small></div>')


# --------------------------------------------------------------------------
# 3 · El marcador por banda del léxico de Kent
# --------------------------------------------------------------------------
def _marcador(alertas):
    """El marcador, con la aritmética que exige un pronóstico y no una opinión.

    **Qué se mide.** Cada banda de Kent es un rango, y su punto medio es la
    probabilidad que la Oficina se compromete a sostener. Con eso se calcula el
    **Brier**: el promedio del cuadrado del error entre lo anunciado y lo que
    pasó. Cero es perfecto; **0,25 es el puntaje de quien dice siempre «mitad y
    mitad»**, y por eso es la vara con que se lo compara. Un marcador que sólo
    cuenta aciertos premia al que nunca se arriesga: anunciar «casi con certeza
    no» quince veces y acertar las quince no es mérito, es no haber dicho nada.

    **Qué NO se mide.** Las alertas que cerraron sin evidencia suficiente quedan
    **fuera del puntaje** y se cuentan aparte. Puntuarlas sería inventar un
    resultado que no hubo. Se muestran igual: un marcador que esconde sus
    indecidibles miente por omisión."""
    vencidas = [a for a in alertas if a["estado"] == "vencida"]
    puntuables = [a for a in vencidas
                  if a["resultado"]["valor"] in ("ocurrio", "no_ocurrio")
                  and a["juicio"]["probabilidad"] in PUNTO_MEDIO]
    sin_calificar = [a for a in vencidas if a["resultado"]["valor"] == "sin_evidencia"]
    if not puntuables:
        return {"de": 0, "ocurrieron": 0, "sin_calificar": len(sin_calificar),
                "brier": None, "leyenda": "", "bandas": []}
    pares = [(PUNTO_MEDIO[a["juicio"]["probabilidad"]],
              1.0 if a["resultado"]["valor"] == "ocurrio" else 0.0)
             for a in puntuables]
    brier = sum((p - o) ** 2 for p, o in pares) / len(pares)
    base = sum(o for _, o in pares) / len(pares)
    brier_base = sum((base - o) ** 2 for _, o in pares) / len(pares)
    bandas = []
    for banda in BANDAS:
        de_la_banda = [a for a in puntuables if a["juicio"]["probabilidad"] == banda]
        if not de_la_banda:
            continue
        ok = sum(1 for a in de_la_banda if a["resultado"]["valor"] == "ocurrio")
        bandas.append({"banda": banda, "de": len(de_la_banda), "ocurrieron": ok,
                       "anunciado": PUNTO_MEDIO[banda] * 100,
                       "observado": ok / len(de_la_banda) * 100})
    # **¿La comparación contra la frecuencia base significa algo todavía?**
    #
    # La frecuencia base se calcula **sobre la misma muestra que se puntúa**, y
    # con pocas alertas eso es degenerado. Apareció al resolver la primera, el
    # 9/10/2026: el hecho no había ocurrido, así que la frecuencia base era 0 y
    # acertaba perfecto —0,000—, y FEMÓNOE no podía empatarle **ni diciendo
    # «casi con certeza no»**. La página imprimía «peor que anunciar siempre la
    # frecuencia base»: aritméticamente cierto y **falso como afirmación**.
    #
    # La comparación recién dice algo cuando la muestra tiene de las dos cosas:
    # al menos un hecho que ocurrió y uno que no. Hasta entonces el número NO
    # se esconde —esconderlo sería mentir por omisión, que es justo lo que este
    # marcador no hace—: se publica el Brier y se declara que la comparación
    # todavía no es posible, y por qué.
    ocurrieron = sum(1 for _, o in pares if o)
    comparable = 0 < ocurrieron < len(pares)
    m = CONF.get("marcador", {})
    return {"de": len(puntuables),
            "ocurrieron": ocurrieron,
            "sin_calificar": len(sin_calificar),
            "comparable": comparable,
            "brier": brier, "brier_base": brier_base,
            "leyenda": m.get("leyenda", "en calibración") if len(puntuables) < 20 else "",
            "bandas": bandas}


def _bandas(alertas):
    """El marcador dibujado. Vacío también se muestra: arranca en cero y se
    llena en público, y eso es parte de lo que se promete."""
    m = _marcador(alertas)
    vence = _proxima_en_vencer(alertas)
    if not m["de"]:
        aviso = (f"La primera vence el <b>{vence}</b>." if vence
                 else "Todavía no hay ninguna alerta publicada.")
        return ('<div class="marcador vacio-honesto">'
                '<p class="arranca"><b>El marcador arranca en cero y se llena en '
                f'público.</b> {aviso} Cada alerta que vence se resuelve contra el '
                'criterio que se fijó al nacer, antes de saber el resultado, y el '
                'número que salga queda acá: acierte o no.</p>'
                '<p class="como">Se puntúa con el <b>Brier</b>, el promedio del '
                'cuadrado del error entre lo anunciado y lo ocurrido. Cero es '
                'perfecto y <b>0,25 es el puntaje de quien dice siempre «mitad y '
                'mitad»</b>. Contar aciertos sin más premiaría a quien nunca se '
                'arriesga.</p>'
                + _rieles_vacios() + '</div>')
    if m["comparable"]:
        comparacion = ("mejor que" if m["brier"] < m["brier_base"] else
                       "igual que" if abs(m["brier"] - m["brier_base"]) < 1e-9
                       else "peor que")
        contra = (f'{comparacion} anunciar siempre la frecuencia base '
                  f'({m["brier_base"]:.3f})')
    else:
        # Todas las alertas puntuadas cayeron del mismo lado. Ver el comentario
        # en `_marcador`: acá la frecuencia base no es un rival, es el mismo
        # dato mirándose al espejo.
        falta = "uno cuyo hecho ocurra" if not m["ocurrieron"] else "uno cuyo hecho no ocurra"
        contra = ('todavía sin comparar contra la frecuencia base: las alertas '
                  f'puntuadas cayeron todas del mismo lado y falta {falta}')
    filas = "".join(
        f'<li><span class="banda">{b["banda"]}</span>'
        f'<span class="riel">'
        f'<span class="lleno ocurrio" style="width:{b["observado"]:.0f}%"></span>'
        f'<span class="anuncio" style="left:{b["anunciado"]:.0f}%" '
        f'title="anunciado: {b["anunciado"]:.0f} %"></span></span>'
        f'<span class="cuenta">{b["ocurrieron"]} de {b["de"]} · '
        f'anunciado {b["anunciado"]:.0f} %, ocurrió {b["observado"]:.0f} %</span></li>'
        for b in m["bandas"])
    extra = (f'<p class="aparte">{m["sin_calificar"]} alerta'
             f'{"s" if m["sin_calificar"] != 1 else ""} cerró sin evidencia '
             'suficiente y queda <b>fuera del puntaje</b>: puntuarla sería '
             'inventar un resultado que no hubo.</p>') if m["sin_calificar"] else ""
    return ('<div class="marcador">'
            f'<div class="brier"><span class="rotulo">Brier</span>'
            f'<span class="cifra">{m["brier"]:.3f}</span>'
            f'<span class="nota">{contra} · {m["de"]} alerta'
            f'{"s" if m["de"] != 1 else ""} puntuada'
            f'{"s" if m["de"] != 1 else ""}'
            + (f' · <i>{m["leyenda"]}</i>' if m["leyenda"] else "") + '</span></div>'
            f'<ul class="bandas">{filas}</ul>'
            '<p class="como">La barra marca lo que ocurrió; el filete, lo que se '
            'había anunciado. Cuanto más cerca, mejor calibrado el juicio.</p>'
            + extra + '</div>')


def _rieles_vacios():
    """Las siete bandas dibujadas vacías. El lector ve la vara antes de que
    haya nada que medir, que es la única forma de que la vara no se acomode
    después a los resultados."""
    return '<ul class="bandas vacias">' + "".join(
        f'<li><span class="banda">{b}</span>'
        f'<span class="riel"><span class="anuncio" '
        f'style="left:{PUNTO_MEDIO[b] * 100:.0f}%"></span></span>'
        f'<span class="cuenta">anunciado {PUNTO_MEDIO[b] * 100:.0f} % · sin casos</span>'
        f'</li>' for b in BANDAS if b in PUNTO_MEDIO) + "</ul>"


# La casa escribe en castellano rioplatense: una fecha que lee una persona va
# en palabras. El formato AAAA-MM-DD queda para los registros, donde ordena.
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _en_palabras(iso):
    """«2026-10-09» a «9 de octubre». Si no se entiende, se devuelve tal cual:
    inventar una fecha legible a partir de una ilegible sería peor."""
    try:
        f = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return str(iso)
    return f"{f.day} de {MESES[f.month - 1]}"


def _proxima_en_vencer(alertas):
    fechas = sorted(a["juicio"].get("vence") for a in alertas
                    if a["estado"] == "publicada" and a["juicio"].get("vence"))
    return fechas[0] if fechas else ""


# --------------------------------------------------------------------------
# 4 · El mapa de la región
# --------------------------------------------------------------------------
def _proyectar(lon, lat, caja, ancho, alto):
    x0, y0, x1, y1 = caja
    return ((lon - x0) / (x1 - x0) * ancho, (y1 - lat) / (y1 - y0) * alto)


def _anillos(geometria):
    if geometria["type"] == "Polygon":
        return [geometria["coordinates"][0]]
    return [poligono[0] for poligono in geometria["coordinates"]]


def _mapa(con_alerta, zonas_vivas=None, con_senal=None):
    """Contornos de Natural Earth 1:50 m (dominio público), la misma copia que
    usa SIWA, traída al depósito de FEMÓNOE. Se dibuja acá, al generar la
    página: el navegador no descarga ni calcula nada.

    **Las Islas Malvinas van en la Argentina.** La Fundación tiene sede en la
    Argentina y sigue la posición argentina; el contorno no se dibuja a mano, sale
    de la misma fuente que los otros 33. Ningún mapa es neutral en un territorio
    en disputa —dibujarlo de un lado, del otro, u omitirlo son tres posiciones—,
    así que la que toma este queda escrita al pie de la página.

    A esta escala, un Estado del Caribe oriental mide dos píxeles. Cuando el
    contorno no llega a verse se le agrega una marca redonda en su centro: es un
    señalador, no una geometría inventada."""
    if not GEO.exists():
        return '<p class="vacio">Faltan los contornos del mapa.</p>'
    datos = json.loads(GEO.read_text(encoding="utf-8"))
    caja, ancho, alto = (-118.0, -56.0, -34.0, 33.0), 420, 560
    piezas, centros = [], {}
    for f in datos["features"]:
        iso = f["properties"].get("iso")
        nombre = f["properties"].get("pais", iso)
        trazos, xs, ys = [], [], []
        for anillo in _anillos(f["geometry"]):
            # Se redondea a dos decimales —un kilómetro— y se quitan los puntos
            # repetidos: el mapa es de lectura, no de medición.
            puntos, previo = [], None
            for lon, lat in anillo:
                punto = _proyectar(round(lon, 2), round(lat, 2), caja, ancho, alto)
                punto = (round(punto[0], 1), round(punto[1], 1))
                if punto != previo:
                    puntos.append(punto)
                    previo = punto
            if len(puntos) < 4:
                continue
            trazos.append("M" + "L".join(f"{x},{y}" for x, y in puntos) + "Z")
            xs += [x for x, _ in puntos]
            ys += [y for _, y in puntos]
        if not trazos:
            continue
        centros[iso] = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        clase = "pais viva" if iso in con_alerta else "pais"
        marca = ""
        if max(max(xs) - min(xs), max(ys) - min(ys)) < 7:
            marca = (f'<circle class="marca" cx="{(min(xs) + max(xs)) / 2:.1f}" '
                     f'cy="{(min(ys) + max(ys)) / 2:.1f}" r="3.4"/>')
        piezas.append(f'<a href="#pais-{iso}" class="{clase}" data-iso="{iso}">'
                      f'<title>{_escapar(nombre)}</title>'
                      f'<path d="{"".join(trazos)}"/>{marca}</a>')
    piezas.append(_zonas_en_mapa(centros, zonas_vivas or set()))

    # EL PULSO SOBRE EL MAPA. Una onda que se abre desde el centro de cada
    # Estado con alerta vigente, y sólo de ésos: es el mismo latido del mosaico
    # y del punto de la figura, dicho sobre la geografía. Las ondas salen
    # escalonadas —cada Estado entra un poco después que el anterior— porque
    # todas a la vez no se leen como varios focos sino como un parpadeo.
    #
    # Va al final, encima de los contornos, para que no lo tape ningún país.
    #
    # DOS NIVELES, porque «novedad» no es una sola cosa. El foco lleno marca al
    # Estado con **alerta vigente**: la casa anunció algo y se juega el
    # resultado. El foco tenue marca al Estado donde **una señal pasó el umbral
    # en los últimos catorce días y todavía no hay alerta**: la máquina vio algo
    # y nadie lo juzgó aún. Son estados distintos del mismo proceso y el mapa no
    # los puede decir con el mismo gesto, porque significan cosas distintas.
    ondas = []
    for n, iso in enumerate(sorted((con_senal or set()) - set(con_alerta))):
        if iso not in centros:
            continue
        cx, cy = centros[iso]
        ondas.append(
            f'<g class="foco tenue" style="--retraso:{n * 0.55:.2f}s" aria-hidden="true">'
            f'<circle class="onda" cx="{cx:.1f}" cy="{cy:.1f}" r="4"/>'
            f'<circle class="nucleo" cx="{cx:.1f}" cy="{cy:.1f}" r="1.8"/>'
            f'</g>')
    for n, iso in enumerate(sorted(con_alerta)):
        if iso not in centros:
            continue
        cx, cy = centros[iso]
        ondas.append(
            f'<g class="foco" style="--retraso:{n * 0.85:.2f}s" aria-hidden="true">'
            f'<circle class="onda" cx="{cx:.1f}" cy="{cy:.1f}" r="4"/>'
            f'<circle class="onda tarde" cx="{cx:.1f}" cy="{cy:.1f}" r="4"/>'
            f'<circle class="nucleo" cx="{cx:.1f}" cy="{cy:.1f}" r="2.6"/>'
            f'</g>')
    if ondas:
        piezas.append('<g class="focos">' + "".join(ondas) + "</g>")
    return (f'<svg id="mapa-alc" class="mapa" viewBox="0 0 {ancho} {alto}" role="img" '
            f'aria-label="Mapa de los 33 Estados y sus zonas transfronterizas">'
            f'{"".join(piezas)}</svg>')


def _zonas_en_mapa(centros, vivas):
    """Las zonas, dibujadas como lo que son: una relación entre Estados.

    **Por qué no se dibujan como polígonos.** No tenemos la geometría de una
    zona transfronteriza, y trazarla a mano sería inventar un límite donde la
    casa no tiene fuente. Lo que sí es verdadero es que la zona **une** a dos o
    tres Estados, así que se dibuja eso: un nodo en el punto medio de sus
    Estados y una línea a cada uno.

    El nodo no es «el lugar exacto de la zona»: es el centro de los Estados que
    la componen, calculado del mismo mapa. Queda declarado al pie."""
    piezas = []
    for z in _zonas.zonas():
        puntos = [centros[i] for i in z["estados"] if i in centros]
        if len(puntos) < 2:
            continue
        cx = sum(p[0] for p in puntos) / len(puntos)
        cy = sum(p[1] for p in puntos) / len(puntos)
        viva = z["codigo"] in vivas
        radios = "".join(f'<line x1="{cx:.1f}" y1="{cy:.1f}" '
                         f'x2="{px:.1f}" y2="{py:.1f}"/>' for px, py in puntos)
        piezas.append(
            f'<g class="zona{" viva" if viva else ""}" data-zona="{z["codigo"]}">'
            f'<title>{_escapar(z["nombre"])} · {" + ".join(z["estados"])}</title>'
            f'{radios}<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{4.6 if viva else 3.4}"/>'
            f'</g>')
    return f'<g class="zonas-capa">{"".join(piezas)}</g>' if piezas else ""


# --------------------------------------------------------------------------
# El mosaico y las alertas
# --------------------------------------------------------------------------
# El nombre humano de cada señal. Al pie de cada figura se mostraba el nombre
# del archivo —`eventos_violencia`, con guion bajo y todo—, que es el nombre de
# una variable y no significa nada fuera del código. La procedencia no se
# esconde: el nombre técnico queda en el `title`, que es donde sirve.
NOMBRE_SENAL = {
    "eventos_protesta": "hechos de protesta registrados",
    "eventos_violencia": "hechos de violencia registrados",
    "ooni_confirmados": "bloqueos de sitios confirmados",
    "ooni_tasa": "tasa de bloqueos confirmados",
    "ooni_panel": "bloqueos sobre el panel fijo de sitios",
    "ioda_alertas": "alertas de conectividad",
    "ioda_corte": "cortes de conectividad",
    "ooni_bloqueo": "bloqueos de sitios",
    "cloudflare_cortes": "cortes de tráfico",
    "cloudflare_deliberados": "cortes de tráfico deliberados",
    "redes_gobernabilidad": "menciones en redes sobre gobernabilidad",
    "redes_seguridad": "menciones en redes sobre seguridad",
    "redes_informativo": "menciones en redes sobre el entorno informativo",
    "redes_coordinado": "grupos de fuentes repitiendo el mismo texto",
    "acled_protesta": "protestas registradas por ACLED",
    "acled_violencia": "hechos de violencia registrados por ACLED",
    "acled_muertes": "muertes registradas por ACLED",
    "acled_hecho_grave": "hechos graves registrados por ACLED",
    "vigia_organismo": "publicaciones de la autoridad electoral",
}


def _nombre_senal(clave):
    """El nombre legible de una señal. Si no está en la tabla, se devuelve la
    clave con los guiones bajos cambiados por espacios: queda feo, pero nunca
    queda vacío ni inventado."""
    return NOMBRE_SENAL.get(clave, str(clave).replace("_", " "))


def _celda(p, suyas, orden=0):
    ejes = {a["eje"] for a in suyas if a["estado"] in ("publicada", "curada")}
    naranja = any(a["estado"] == "vencida" and a["resultado"]["valor"] == "sin_evidencia"
                  for a in suyas)
    luces = "".join(
        f'<span class="eje{" viva late" if nombre in ejes else ""}" title="{nombre}">{sigla}</span>'
        for nombre, sigla in EJES)
    aviso = ('<span class="naranja" title="alerta vencida sin evidencia suficiente '
             'para calificar"></span>') if naranja else ""
    return (f'<article class="celda entra{" viva" if ejes else ""}" '
            f'id="pais-{p["iso3"]}" style="--orden:{orden}" '
            f'data-iso="{p["iso3"]}" tabindex="0" role="button" '
            f'aria-label="Abrir la ficha de {_escapar(p["nombre"])}">'
            f'<img src="banderas/{p["iso3"]}.png" alt="" width="30" height="22" loading="lazy">'
            f'<div class="quien"><b>{_escapar(p["nombre"])}</b>'
            f'<small>{p["iso3"]} · {_escapar(p["bloque"])}</small></div>'
            f'<div class="luces">{luces}{aviso}</div></article>')


# El punto medio de cada rango de `doctrina/lexico.md` §1. Es la probabilidad
# que la Oficina se compromete a sostener cuando usa esa banda, y la que se
# puntúa. La doctrina prohíbe escribir 0 % y 100 %, así que ninguna llega ahí.
PUNTO_MEDIO = {
    "casi con certeza no": 0.03, "muy improbable": 0.125, "improbable": 0.30,
    "posibilidades parejas": 0.50, "probable": 0.70, "muy probable": 0.875,
    "casi con certeza": 0.97,
}

ESCALA = ["casi con certeza no", "muy improbable", "improbable", "posibilidades parejas",
          "probable", "muy probable", "casi con certeza"]
CORTOS = ["casi seguro que no", "muy improbable", "improbable", "parejas",
          "probable", "muy probable", "casi seguro"]


def _banda(elegida):
    """La escala de Kent entera, con el juicio marcado. Se ve la vara, no sólo el
    resultado: es lo contrario de un número que finge precisión."""
    if elegida not in ESCALA:
        return ""
    i = ESCALA.index(elegida)
    celdas = "".join(
        f'<span class="paso{" aqui" if n == i else ""}" title="{ESCALA[n]}">'
        f'{CORTOS[n] if n == i else ""}</span>' for n in range(len(ESCALA)))
    return (f'<div class="kent" role="img" aria-label="Probabilidad: {elegida}">'
            f'<small>menos probable</small>{celdas}<small>más probable</small></div>')



def _zona_celda(z, suyas, orden=0):
    """Una zona en la grilla. Lleva las banderas de sus Estados, porque lo
    primero que hay que entender de una zona es a quiénes cruza."""
    ejes = {a["eje"] for a in suyas if a["estado"] in ("publicada", "curada")}
    luces = "".join(
        f'<span class="eje{" viva late" if nombre in ejes else ""}" title="{nombre}">{sigla}</span>'
        for nombre, sigla in EJES)
    banderas = "".join(
        f'<img src="banderas/{iso}.png" alt="{iso}" width="22" height="16" loading="lazy">'
        for iso in z["estados"])
    # Era un <article> con tabindex y un `data-zona` que **ningún programa leía**:
    # se podía enfocar y tocar, y no pasaba nada. El mismo defecto del sello que
    # parecía botón, y que la dirección ya había señalado el 2/10/2026. Ahora es
    # un botón y abre su ficha, igual que un Estado.
    return (f'<button type="button" class="celda zona entra{" viva" if ejes else ""}" '
            f'data-zona="{z["codigo"]}" style="--orden:{orden}" '
            f'aria-label="Abrir la ficha de {_escapar(z["nombre"])}">'
            f'<div class="banderas">{banderas}</div>'
            f'<div class="quien"><b>{_escapar(z["nombre"])}</b>'
            f'<small>{" · ".join(z["estados"])}</small></div>'
            f'<div class="luces">{luces}</div></button>')


def _zonas_seccion(por_pais):
    celdas = "".join(
        _zona_celda(z, por_pais.get(z["codigo"], []), n)
        for n, z in enumerate(_zonas.zonas()))
    return ('<p class="referencia">Diez zonas que cruzan la frontera de dos o más '
            'Estados. Se miden <b>agregadas</b>: un hecho repartido entre tres países '
            'no pasa ningún umbral por separado y sí lo pasa junto, porque es un solo '
            'hecho. Para que cuente como zona, <b>ningún Estado puede aportar más de '
            'tres cuartos</b> del total: un hecho de frontera se ve de los dos lados. '
            'La frontera norte de México queda afuera porque su otro lado no está '
            'entre los 33: es un hueco declarado, no un olvido.</p>'
            f'<div class="mosaico zonas">{celdas}</div>')


def _tarjeta(a):
    j, d = a["juicio"], a.get("dictamen")
    hecho = (_escapar(j["hecho_anunciado"]) if not str(j["hecho_anunciado"]).startswith(FALTA)
             else '<i class="pendiente">Borrador: el juicio todavía no está escrito.</i>')
    if d:
        # La tesis suele venir con «El décimo hombre sostiene que» adentro: el
        # título de la columna ya lo dice, y repetirlo queda torpe.
        tesis = re.sub(r"^El décimo hombre sostiene que\s*", "",
                       (d.get("tesis") or "").strip())
        # La respuesta se muestra en prosa: se le sacan las marcas de formato y se
        # toman las dos primeras oraciones, que son las que cierran el asunto.
        prosa = re.sub(r"[*#]+", "", a.get("respuesta_de_la_oficina") or "")
        prosa = re.sub(r"\s+", " ", prosa).strip()
        oraciones = re.split(r"(?<=\.)\s", prosa)
        resumen = " ".join(oraciones[:2])[:340]
        disenso = ('<div class="dos-voces">'
                   '<div><h3>El décimo hombre</h3>'
                   f'<p>Sostiene que {_negritas(tesis)}</p>'
                   f'<p><b>{_escapar(d.get("veredicto", "").replace("_", " "))}</b></p></div>'
                   '<div><h3>La Oficina responde</h3>'
                   f'<p>{_escapar(resumen)}</p></div></div>')
    else:
        disenso = ('<p class="disenso falta">Sin dictamen del décimo hombre: '
                   'esta alerta no puede publicarse.</p>')
    prob = j["probabilidad"] if not str(j["probabilidad"]).startswith(FALTA) else "—"
    plazo = j["plazo_dias"] if not str(j["plazo_dias"]).startswith(FALTA) else "—"
    # Si los dos analistas del panel difirieron, se dice: la casa muestra su
    # discusión interna en vez de esconderla.
    divergencia = (a.get("panel") or {}).get("divergencia")
    panel = (f'<p class="panel">{_negritas(divergencia)}</p>'
             if divergencia and "difirieron" in divergencia else "")
    reserva = a.get("reserva") or {}
    aviso_reserva = (f'<p class="reserva"><b>Fuente reservada.</b> '
                     f'{_negritas(reserva.get("motivo", ""))} La Oficina conserva el registro '
                     f'completo.</p>') if reserva.get("aplicada") else ""
    primera = a["senal"]["detalle"][0] if a["senal"]["detalle"] else {}
    valores = _serie(primera.get("senal", ""), a["iso3"], date.fromisoformat(a["senal"]["fecha"]))
    _hasta = a["senal"]["fecha"]
    try:
        _desde = (date.fromisoformat(str(_hasta)[:10]) - timedelta(days=29)).isoformat()
    except (TypeError, ValueError):
        _desde = ""
    chispa = _figura(valores, primera.get("mediana"), _desde, _hasta,
                     vivo=a["estado"] == "publicada",
                     unidad=_nombre_senal(primera.get("senal", "")).split(" ")[0])
    pie = (f'<figcaption title="serie: {_escapar(primera.get("senal", ""))}">'
           f'{_escapar(_nombre_senal(primera.get("senal", "")))}, 30 días. '
           f'La línea punteada es la mediana de {_escapar(a["pais"])} en ese '
           f'tramo.</figcaption>') if chispa else ""
    return (f'<article class="alerta revela"><header><b>{_escapar(a["pais"])}</b>'
            f'<span>{_escapar(a["eje"])}</span></header>'
            f'<p class="hecho">{hecho}</p>'
            + _banda(prob)
            + (f'<p class="meta">plazo {_escapar(plazo)} días · confianza '
               f'{_escapar(j.get("confianza", ""))} · {_escapar(a["estado"])}</p>')
            + (f'<figure class="grafico">{chispa}{pie}</figure>' if chispa else "")
            + _aviso_descarte(a) + _plazo(a) + aviso_reserva + panel + disenso
            + f'<a class="leer" href="alerta/{a["id"]}.html">Leer el dictamen &rarr;</a>'
            + '</article>')


# --------------------------------------------------------------------------
# 5 · La ficha de cada Estado
# --------------------------------------------------------------------------
def _mediana_simple(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def _pulso_de_pais(iso3, vivos):
    """Las tres series del Estado, dibujadas para la ficha.

    **Por qué está acá.** La dirección pidió el 2/10/2026 que, al tocar un
    Estado, la figura siga viva como en la portada. Hasta ese día la ficha era
    sólo texto: se abría y lo que estaba latiendo se apagaba. Ahora lleva las
    mismas tres series del pulso de la apertura, con el mismo trazo que se
    dibuja solo y el mismo punto que late **si ese eje tiene alerta vigente en
    ese Estado**, y no si no la tiene.

    El SVG se arma en Python y viaja armado: la ficha la dibuja JavaScript, pero
    no calcula nada. Una figura calculada en dos lugares distintos son dos
    figuras que algún día se van a contradecir.
    """
    hoy = date.today()
    piezas = []
    for eje, serie, _sigla in PULSO:
        valores = _serie(serie, iso3, hoy, dias=90)
        if not valores or max(valores) <= 0:
            continue
        piezas.append({
            "eje": eje, "serie": serie, "vivo": eje in vivos,
            "nombre": _nombre_senal(serie),
            "svg": _figura(valores, _mediana_simple(valores),
                           (hoy - timedelta(days=90)).isoformat(), hoy.isoformat(),
                           vivo=eje in vivos, alto=40),
            "maximo": f"{max(valores):.0f}",
        })
    return piezas


def _corredores():
    """Los corredores comerciales por zona, si el colector ya corrió.

    Si el archivo no está, se devuelve vacío: la ficha muestra lo que hay y no
    inventa un corredor que nadie midió.
    """
    f = RAIZ / "datos" / "corredores.json"
    if not f.exists():
        return {}, None
    d = json.loads(f.read_text(encoding="utf-8"))
    return d.get("zonas", {}), d.get("fuente", {})


def _fichas_zona(por_zona):
    """La ficha de cada zona transfronteriza, con el mismo lenguaje que la de un
    Estado: el pulso primero, las alertas después.

    **El pulso de una zona es la suma de sus Estados**, que es exactamente como
    la mide el detector: un hecho repartido entre tres países no pasa ningún
    umbral por separado y sí lo pasa junto. Dibujar cada país por su lado acá
    sería mostrar una cosa distinta de la que se mide.
    """
    hoy = date.today()
    corredores, fuente_cor = _corredores()
    fichas = {}
    for z in _zonas.zonas():
        suyas = por_zona.get(z["codigo"], [])
        vivos = {a["eje"] for a in suyas if a["estado"] in ("publicada", "curada")}
        pulso = []
        for eje, serie, _sigla in PULSO:
            sumada = []
            for iso in z["estados"]:
                v = _serie(serie, iso, hoy, dias=90)
                if not v:
                    continue
                if not sumada:
                    sumada = list(v)
                else:
                    sumada = [a + b for a, b in zip(sumada, v)]
            if not sumada or max(sumada) <= 0:
                continue
            pulso.append({
                "eje": eje, "vivo": eje in vivos, "nombre": _nombre_senal(serie),
                "svg": _figura(sumada, _mediana_simple(sumada),
                               (hoy - timedelta(days=90)).isoformat(), hoy.isoformat(),
                               vivo=eje in vivos, alto=40),
                "maximo": f"{max(sumada):.0f}"})
        cor = (corredores.get(z["codigo"]) or {}).get("corredores", [])
        fichas[z["codigo"]] = {
            "nombre": z["nombre"], "bloque": " · ".join(z["estados"]),
            # Los corredores son contexto permanente, no una alerta: Comtrade se
            # actualiza por año. Van después del pulso y antes de las alertas,
            # porque explican el cruce y no anuncian nada.
            "corredores": [{
                "par": f'{c["origen"]}→{c["destino"]}',
                "de": c.get("pais_origen", ""), "a": c.get("pais_destino", ""),
                "brecha_pct": c.get("brecha_pct"),
                "sentido": c.get("sentido", ""),
                "marcado": bool(c.get("llama_la_atencion")),
            } for c in cor],
            "corredores_fuente": fuente_cor,
            "que_es": z.get("que_es", ""), "estados": z["estados"], "pulso": pulso,
            "alertas": [{"eje": a["eje"], "estado": a["estado"],
                         "hecho": a["juicio"]["hecho_anunciado"],
                         "probabilidad": a["juicio"].get("probabilidad", ""),
                         "vence": a["juicio"].get("vence", ""),
                         "resultado": (a["resultado"] or {}).get("leyenda", "")}
                        for a in suyas],
            "senales": [], "fechas": []}
    return fichas


def _fichas(por_pais, calendario, senales):
    fichas = {}
    for p in PADRON:
        suyas = por_pais.get(p["iso3"], [])
        vivos = {a["eje"] for a in suyas if a["estado"] in ("publicada", "curada")}
        fichas[p["iso3"]] = {
            "nombre": p["nombre"], "bloque": p["bloque"],
            "pulso": _pulso_de_pais(p["iso3"], vivos),
            "siwa": SIWA.format(slug=_slug(p["nombre"])),
            "alertas": [{
                "eje": a["eje"], "estado": a["estado"],
                "hecho": (a["juicio"]["hecho_anunciado"]
                          if not str(a["juicio"]["hecho_anunciado"]).startswith(FALTA)
                          else "Borrador: el juicio todavía no está escrito."),
                "probabilidad": (a["juicio"]["probabilidad"]
                                 if not str(a["juicio"]["probabilidad"]).startswith(FALTA) else ""),
                "vence": a["juicio"].get("vence", ""),
                "resultado": (a["resultado"] or {}).get("leyenda", ""),
            } for a in suyas],
            "senales": senales.get(p["iso3"], [])[:6],
            "fechas": [e for e in calendario if e["iso3"] == p["iso3"]][:3],
        }
    return fichas


# --------------------------------------------------------------------------
# El catálogo de la guía
# --------------------------------------------------------------------------
PREGUNTAS = [
    {"q": "que es femonoe que es esto para que sirve plataforma",
     "r": "FEMÓNOE es la plataforma de alerta temprana de la Fundación Sherman Kent para los "
          "33 Estados de América Latina y el Caribe, en tres ejes: gobernabilidad, seguridad y "
          "entorno informativo. Cada alerta dice qué podría pasar, con qué probabilidad y en "
          "qué plazo —y al vencer se publica si acertó."},
    {"q": "como nace se hace proceso capas quien escribe el juicio",
     "r": "En cuatro pasos. 1) El robot compara cada país con su propia línea de base y deja "
          "las señales que se salen de lo habitual. 2) Se exige corroboración: dos familias de "
          "fuentes independientes, o la credibilidad desciende y queda rotulado. 3) El equipo "
          "de análisis escribe el juicio, y el décimo hombre lo impugna. 4) Al vencer el plazo "
          "se marca el resultado. La máquina nunca alerta sola, y la Oficina nunca publica "
          "sola: la dirección cura cada alerta antes de que salga."},
    {"q": "decimo hombre disenso quien discute impugna",
     "r": "El décimo hombre es el disenso obligatorio de la casa: si la Oficina anuncia que "
          "algo va a pasar, él construye el mejor caso posible para que no pase, con su propia "
          "evidencia. No tiene que estar convencido: ese es el punto. Su dictamen se publica al "
          "lado de la alerta, con la respuesta de la Oficina. Sin dictamen, la alerta no sale."},
    {"q": "naranja color punto que significa",
     "r": "El naranja señala una sola cosa en toda la página: una alerta que venció sin "
          "evidencia suficiente para calificarla. Ni acertó ni falló: no se pudo saber, y se "
          "dice."},
    {"q": "aciertan marcador acierto calibracion tasa miden resultado",
     "r": "El criterio con que se va a dar por cumplida o fallada se fija cuando nace la "
          "alerta, antes de saber el resultado. Por eso el marcador no se puede acomodar "
          "después. El tablero lo muestra banda por banda del léxico de Kent, y hasta reunir "
          "20 alertas vencidas lleva la leyenda «en calibración»."},
    {"q": "de donde salen los datos fuentes fuente",
     "r": "De fuentes públicas y abiertas: mediciones de bloqueo y de cortes de conectividad, "
          "registros de hechos de protesta y violencia, prensa y canales públicos leídos por "
          "vías abiertas. Cada señal declara de qué familia de fuentes viene. Con una sola "
          "familia, el dato entra rotulado y no sostiene un juicio de confianza alta."},
    {"q": "umbral tope semanal cuantas emiten por que no aparece ninguna",
     "r": "El umbral es relativo a cada país: se compara contra lo que ese país tiene por "
          "costumbre, no contra un promedio de la región. Un Estado sin alertas es un Estado "
          "cuyas mediciones no se apartaron de su propia línea de base. Rige además un tope de "
          "5 alertas nuevas por semana."},
    {"q": "chispa grafico linea punteada que es ese dibujo",
     "r": "Es la serie de los últimos 30 días que originó la alerta. La línea punteada marca la "
          "mediana de ese Estado: el lector ve el dato y su línea de base juntos, y no depende "
          "de la palabra de la casa."},
    {"q": "cada cuanto se actualiza frecuencia robot",
     "r": "El robot corre todos los días y deja sus señales fechadas. El calendario "
          "institucional se actualiza una vez por semana."},
    {"q": "diferencia con siwa observatorio",
     "r": "SIWA dice cómo está cada país, con cifras calificadas. FEMÓNOE dice qué está por "
          "pasar, con probabilidad y plazo. Son dos registros distintos de la misma casa, y "
          "la ficha de cada Estado enlaza a su página en SIWA."},
    {"q": "quien firma responsable autor",
     "r": "Las firma el Equipo de Análisis de la Fundación Sherman Kent, sin nombres propios: "
          "las alertas hablan de indicadores y de hechos, nunca de personas."},
]

SECCIONES = [
    {"archivo": "mosaico", "rotulo": "El mosaico de los 33 y el mapa",
     "s": "mapa paises estados mosaico banderas ejes letras region"},
    {"archivo": "alertas", "rotulo": "Las alertas, con el disenso al lado",
     "s": "alerta vigente probabilidad plazo decimo hombre chispa"},
    {"archivo": "marcador", "rotulo": "El marcador de aciertos",
     "s": "marcador acierto calibracion kent banda"},
    {"archivo": "calendario", "rotulo": "El calendario institucional",
     "s": "elecciones calendario fechas comicios referendum"},
]


def _catalogo():
    # Los genéricos van primero: si la consulta no nombra un eje, la guía lleva a
    # la sección entera en vez de elegir un eje al azar.
    temas = [{"slug": "alertas", "eje": "General", "rotulo": "Las alertas vigentes"},
             {"slug": "mosaico", "eje": "General", "rotulo": "Los 33 Estados y el mapa"},
             {"slug": "marcador", "eje": "General", "rotulo": "El marcador de aciertos"},
             {"slug": "calendario", "eje": "General", "rotulo": "El calendario institucional"}]
    for nombre, _ in EJES:
        temas.append({"slug": "mosaico", "eje": nombre.capitalize(),
                      "rotulo": f"Los 33 Estados en {nombre}"})
        temas.append({"slug": "alertas", "eje": nombre.capitalize(),
                      "rotulo": f"Alertas de {nombre}"})
    return {
        "generado_nota": "Catálogo de la guía de FEMÓNOE. Lo escribe tablero.py con cada "
                         "corrida: los 33 Estados salen del padrón.",
        "ejes_orden": [n.capitalize() for n, _ in EJES],
        "temas": temas,
        "paises": [{"slug": p["iso3"], "rotulo": p["nombre"]} for p in PADRON],
        "herramientas": SECCIONES,
        "faq": PREGUNTAS,
    }


# --------------------------------------------------------------------------
def _tira(iso3, estados=None):
    """Los 33, con el de la alerta encendido. En una alerta de zona se encienden
    **todos los Estados que la zona cruza**: ese es justamente el punto."""
    vivos = set(estados or []) or {iso3}
    return "".join(
        f'<img src="../banderas/{x["iso3"]}.png" alt="{_escapar(x["nombre"])}"'
        + (' class="viva"' if x["iso3"] in vivos else "") + ">"
        for x in PADRON)


def _salvedades(a):
    """Las salvedades del décimo hombre, arriba y no en el anexo.

    Cuando la dirección publica una alerta que el disenso objetó, lo que la
    objeción dijo viaja **con** la alerta y a la vista. Una salvedad al pie es
    una salvedad que nadie lee, y acá son la mitad del producto: dicen qué es
    lo que el juicio no afirma."""
    ss = a.get("salvedades") or []
    if not ss:
        return ""
    filas = "".join(
        f'<li><b>{_escapar(s.get("titulo", ""))}.</b> '
        f'{_negritas(s.get("texto", ""))}</li>'
        for s in sorted(ss, key=lambda x: x.get("orden", 0)))
    ver = _escapar(str((a.get("dictamen") or {}).get("veredicto", "")).replace("_", " "))
    # Una corrección posterior a la publicación se muestra, con su fecha. Corregir
    # en silencio una alerta ya publicada es reescribir lo que se dijo.
    cs = a.get("correcciones_despues_de_publicar") or []
    aviso = ("".join(
        f'<p class="corregida"><b>Corregida el {_escapar(c.get("fecha", ""))}.</b> '
        f'{_escapar(c.get("por_que", ""))}</p>' for c in cs))
    return (f'<section class="salvedades"><h3>Lo que este juicio no afirma</h3>'
            f'<p class="porque">El décimo hombre dictaminó <b>{ver}</b>. La dirección '
            f'resolvió publicar igual, y estas son las salvedades con que se '
            f'publica.</p><ul>{filas}</ul>{aviso}</section>')


def _disarm(a):
    """La lectura DISARM de la señal, si la señal la habilita.

    Va con la advertencia pegada: la técnica se declara **compatible**, nunca
    afirmada, y debajo se dice qué haría falta para afirmarla. Sin eso, nombrar
    la técnica le presta al hallazgo una certeza que la medición no tiene."""
    try:
        lecturas = lectura_disarm(a["senal"].get("detalle", []))
    except SystemExit:
        return ""          # sin copia local del marco, la página sale igual
    if not lecturas:
        return ""
    bloques = []
    for lec in lecturas:
        chips = "".join(
            f'<span class="tecnica" title="{_escapar(t["tactica"])}">'
            f'{_escapar(t["id"])} · {_escapar(t["nombre"])}</span>'
            for t in lec["tecnicas"])
        bloques.append(
            f'<p class="observable">{_escapar(lec["observable"])} — '
            f'{_escapar(lec["se_mide_asi"])}.</p><div class="tecnicas">{chips}</div>'
            f'<p class="salvedad"><b>No lo afirma:</b> {_escapar(lec["no_prueba"])}. '
            f'<b>Haría falta</b> {_escapar(lec["haria_falta"])}.</p>')
    return ('<section class="disarm"><h3>Lectura con el marco DISARM</h3>'
            + "".join(bloques)
            + '<p class="credito">Taxonomía DISARM · DISARM Foundation · CC BY 4.0. '
              'FEMÓNOE la cita, no la modifica.</p></section>')



def _reparto(a):
    """De qué lado de la frontera pesa el hecho. Una alerta de zona que no
    muestra su reparto esconde justo lo que la hace distinta de una de país."""
    r = a.get("reparto")
    if not a.get("zona") or not r:
        return ""
    total = sum(r.values()) or 1
    filas = "".join(
        f'<li><span class="banda">{_escapar(NOMBRE.get(iso, iso))}</span>'
        f'<span class="riel"><span class="lleno ocurrio" '
        f'style="width:{100 * v / total:.0f}%"></span></span>'
        f'<span class="cuenta">{v:g} · {100 * v / total:.0f} %</span></li>'
        for iso, v in sorted(r.items(), key=lambda kv: -kv[1]))
    return ('<section class="disarm"><h4>De qué lado pesa</h4>'
            f'<ul class="bandas">{filas}</ul>'
            '<p class="credito">Para que una señal cuente como de zona, ningún '
            'Estado puede aportar más de tres cuartos del total. Un hecho de '
            'frontera se ve de los dos lados.</p></section>')


def _pagina_alerta(a):
    """La alerta con su propia página: ruta A, el dictamen. Se lee como un
    documento publicado y firmado, no como una tarjeta de panel."""
    j = a["juicio"]
    hecho = (_escapar(j["hecho_anunciado"])
             if not str(j["hecho_anunciado"]).startswith(FALTA)
             else "Borrador: el juicio todavía no está escrito.")
    prob = j["probabilidad"] if not str(j["probabilidad"]).startswith(FALTA) else ""
    plazo = j["plazo_dias"] if not str(j["plazo_dias"]).startswith(FALTA) else "—"
    vence = j.get("vence") or ""
    resumen = (f"Confianza {_escapar(j.get('confianza', ''))} · plazo {_escapar(plazo)} días"
               + (f" · vence el {vence}" if vence and not str(vence).startswith(FALTA) else "")
               + (" · <b>fuente única</b>" if a["senal"].get("fuente_unica") else ""))
    primera = a["senal"]["detalle"][0] if a["senal"]["detalle"] else {}
    valores = _serie(primera.get("senal", ""), a["iso3"], date.fromisoformat(a["senal"]["fecha"]))
    _hasta = a["senal"]["fecha"]
    try:
        _desde = (date.fromisoformat(str(_hasta)[:10]) - timedelta(days=29)).isoformat()
    except (TypeError, ValueError):
        _desde = ""
    chispa = _figura(valores, primera.get("mediana"), _desde, _hasta,
                     vivo=a["estado"] == "publicada",
                     unidad=_nombre_senal(primera.get("senal", "")).split(" ")[0])
    pie = (f'<figcaption title="serie: {_escapar(primera.get("senal", ""))}">'
           f'{_escapar(_nombre_senal(primera.get("senal", "")))}, 30 días. '
           f'La línea punteada es la mediana de {_escapar(a["pais"])} en ese '
           f'tramo.</figcaption>') if chispa else ""
    fundamento = "".join(f"<p>{_negritas(x.strip())}</p>"
                         for x in (j.get("fundamento") or "").split(chr(10)) if x.strip())
    d = a.get("dictamen")
    if d:
        tesis = re.sub(r"^El décimo hombre sostiene que\s*", "", (d.get("tesis") or "").strip())
        prosa = re.sub(r"[*#]+", "", a.get("respuesta_de_la_oficina") or "")
        prosa = re.sub(r"\s+", " ", prosa).strip()
        resumida = " ".join(re.split(r"(?<=\.)\s", prosa)[:3])[:520]
        disenso = ('<div class="dos-voces">'
                   '<div><h3>El décimo hombre</h3>'
                   f'<p>Sostiene que {_negritas(tesis)}</p>'
                   f'<p><b>{_escapar(str(d.get("veredicto", "")).replace("_", " "))}</b></p></div>'
                   '<div><h3>La Oficina responde</h3>'
                   f'<p>{_escapar(resumida)}</p></div></div>')
    else:
        disenso = ('<p class="disenso falta">Sin dictamen del décimo hombre: '
                   'esta alerta no puede publicarse.</p>')
    reserva = a.get("reserva") or {}
    if reserva.get("aplicada"):
        disenso = (f'<p class="reserva"><b>Fuente reservada.</b> '
                   f'{_negritas(reserva.get("motivo", ""))}</p>') + disenso
    html = PLANTILLA_ALERTA
    for clave, valor in {
        "pais": _escapar(a["pais"]), "eje": _escapar(a["eje"]), "id": a["id"],
        "estado": _escapar(a["estado"]), "nace": a["nace"], "hecho": hecho,
        "descarte": _aviso_descarte(a),
        "banda": _banda(prob), "resumen": resumen, "fundamento": fundamento,
        "chispa": chispa, "pie": pie, "plazo": _plazo(a),
        "criterio": _negritas(a.get("criterio_de_resolucion", "")),
        "disarm": _disarm(a) + _reparto(a),
        "salvedades": _salvedades(a),
        "disenso": disenso, "tira": _tira(a["iso3"], a.get("estados")),
        "estilos": "../estilos.css", "base": "../", "fundacion": FUNDACION,
        "hoy": date.today().isoformat(),
    }.items():
        html = html.replace("@@" + clave + "@@", valor)
    return html


def _estilos():
    """El sistema visual vive en `diseno.css`, no acá.

    Estaba incrustado en este archivo, que es como se degrada un diseño: cada
    función nueva agrega su CSS al lado y a los tres meses no hay sistema, hay
    sedimento. Ahora hay un solo archivo y lo lee todo lo que dibuja."""
    sistema = RAIZ / "diseno.css"
    hoja = sistema.read_text(encoding="utf-8") if sistema.exists() else ESTILOS
    for clave, valor in COLORES.items():
        hoja = hoja.replace("@@color-" + clave + "@@", valor)
    return hoja


def construir():
    alertas = _alertas()
    vigentes = [a for a in alertas if a["estado"] in ("publicada", "curada")]
    por_pais = {}
    for a in alertas:
        por_pais.setdefault(a["iso3"], []).append(a)
    calendario, senales = _calendario(), _senales_recientes()
    marcador = _marcador(alertas)
    estado_fuentes = _estado_fuentes()
    con_alerta = {a["iso3"] for a in vigentes if not a.get("zona")}
    zonas_vivas = {a["iso3"] for a in vigentes if a.get("zona")}

    celdas = "".join(_celda(p, por_pais.get(p["iso3"], []), n)
                      for n, p in enumerate(PADRON))
    tarjetas = "".join(_tarjeta(a) for a in alertas[:6]) or (
        '<p class="vacio">Sin alertas vigentes al cierre de esta edición.</p>')
    fechas = "".join(
        f'<li><b>{e["fecha"]}</b><span class="pais">{e["iso3"]}</span>'
        f'<span class="que">{_escapar(e["titulo"])[:78]}</span>'
        f'<span class="sello {"ok" if e.get("confirmado") else "porconf"}">'
        f'{"fecha cotejada" if e.get("confirmado") else "fecha sin cotejar"}</span></li>'
        for e in calendario) or '<li class="vacio">Calendario sin fechas cargadas.</li>'
    # La tarjeta de estado muestra el Brier, que es el número que importa. Sin
    # alertas puntuadas no se inventa un cero: se dice que arranca en cero.
    # «Arranca en cero» se leía como «acertamos cero de las alertas», que es lo
    # contrario de lo que dice: todavía NINGUNA alerta llegó a su fecha de
    # resolución, así que no hay nada puntuado. Lo dijo la dirección el
    # 2/10/2026 —«no comprendo lo de marcador de aciertos»— y si no se entiende
    # desde adentro, menos desde afuera.
    _vence = _proxima_en_vencer(alertas)
    marca_cifra = (f'{marcador["brier"]:.3f} <small>Brier · {marcador["de"]} '
                   f'puntuada{"s" if marcador["de"] != 1 else ""}</small>'
                   if marcador["de"] else
                   ('sin puntuar <small>ninguna alerta llegó a su fecha de '
                    + (f'resolución · la primera, el {_en_palabras(_vence)}</small>' if _vence
                       else 'resolución</small>')))
    marca = ((f'{marcador["ocurrieron"]} de {marcador["de"]} alertas puntuadas ocurrieron'
              + (f' · <i>{marcador["leyenda"]}</i>' if marcador["leyenda"] else ""))
             if marcador["de"] else "Todavía no venció ninguna alerta")

    html = PLANTILLA.replace("@@estilos@@", "estilos.css")
    for clave, valor in {
        "fundacion": FUNDACION, "celdas": celdas,
        "mapa": _mapa(con_alerta, zonas_vivas, set(senales)),
        "pulso": _pulso(), "mapa3": _REUSO,
        "tarjetas": tarjetas, "bandas": _bandas(alertas), "fechas": fechas,
        "zonas": _zonas_seccion(por_pais),
        "marca": marca, "vigentes": str(len(vigentes)), "corrida": _ultima_corrida(),
        "version": CONF["version"], "hoy": date.today().isoformat(),
        "fuentes_cifra": estado_fuentes["cifra"],
        "fuentes_total": estado_fuentes["total"],
        "fuentes_fecha": estado_fuentes["fecha"],
        "alerta_fuentes": "alerta" if estado_fuentes["alerta"] else "",
        "marca_cifra": marca_cifra,
        "tope": str(CONF.get("tope_semanal", 5)),
        # Un solo diccionario para Estados y zonas: el que abre la ficha no
        # tiene por qué saber cuál de las dos cosas le tocó. Las alertas de
        # zona viven en el mismo mapa, con el código de zona por clave.
        "fichas": json.dumps({**_fichas(por_pais, calendario, senales),
                              **_fichas_zona(por_pais)}, ensure_ascii=False),
    }.items():
        html = html.replace("@@" + clave + "@@", valor)

    global SALIDA
    if "--propuesta" in sys.argv:
        # Prototipo aparte. Regla de la casa: no se toca lo publicado para
        # mostrar una propuesta, y menos ahora que el sitio ya está en línea.
        SALIDA = RAIZ / "tablero" / "propuestas" / "v2"
        SALIDA.mkdir(parents=True, exist_ok=True)
        for sub in ("marca", "banderas", "geo"):
            origen, destino = RAIZ / "tablero" / sub, SALIDA / sub
            if origen.exists() and not destino.exists():
                shutil.copytree(origen, destino)
    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "estilos.css").write_text(_estilos(), encoding="utf-8")
    (SALIDA / "index.html").write_text(html, encoding="utf-8")
    carpeta = SALIDA / "alerta"
    carpeta.mkdir(exist_ok=True)
    for una in alertas:
        (carpeta / f"{una['id']}.html").write_text(_pagina_alerta(una), encoding="utf-8")
    import metodo
    import prospectiva
    metodo.construir(SALIDA, FUNDACION, PUNTO_MEDIO, BANDAS)
    # El horizonte necesita saber qué par (Estado, eje) tiene alerta vigente,
    # para que su figura lata igual que en la portada. No lo averigua solo: el
    # que lee los expedientes es este archivo.
    vivas = {(x["iso3"], x["eje"]) for x in alertas
             if x["estado"] in ("publicada", "curada")}
    prospectiva.construir(SALIDA, FUNDACION, NOMBRE, vivas)
    guia = SALIDA / "guia"
    guia.mkdir(exist_ok=True)
    (guia / "guia-femonoe.json").write_text(
        json.dumps(_catalogo(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Tablero escrito: {SALIDA / 'index.html'} · {len(PADRON)} Estados · "
          f"{len(vigentes)} alertas vigentes · mapa y fichas incluidos")


ESTILOS = """
  :root {
    --azul: @@color-azul@@; --fondo: @@color-fondo@@; --superficie: @@color-superficie@@;
    --linea: @@color-linea@@; --violeta: @@color-violeta@@;
    --violeta-claro: @@color-violeta-claro@@; --violeta-profundo: @@color-violeta-profundo@@;
    --acero: @@color-acero@@; --texto2: @@color-texto2@@; --naranja: @@color-naranja@@;
  }
  /* Fondo claro por defecto. El oscuro lo elige quien mira y se recuerda en su
     propio navegador: nunca se le impone. Misma paleta del manual, con el
     violeta claro, que es el que contrasta sobre oscuro. */
  :root[data-tema="oscuro"] {
    --azul: #DFE6EB; --fondo: #00121E; --superficie: #0A1620;
    --linea: rgba(198,198,197,.16); --violeta: #BA66EC; --violeta-claro: #8C00E0;
    --texto2: #9FB0BC;
    color-scheme: dark;
  }
  :root[data-tema="oscuro"] .eje.viva { color: #00121E; }
  :root[data-tema="oscuro"] svg.mapa .pais path,
  :root[data-tema="oscuro"] svg.mapa .pais .marca { fill: #13242F; }
  :root[data-tema="oscuro"] .celda img { border-color: var(--linea); }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--fondo); color: var(--azul);
    font-family: Inter, "Segoe UI", system-ui, sans-serif; font-weight: 500; line-height: 1.5;
  }

  /* Franja institucional, como la de SIWA, cerrada por la línea violeta. */
  .franja {
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 16px; padding: 12px 20px;
    background: var(--superficie); border-bottom: 3px solid var(--violeta);
  }
  .marca { display: flex; align-items: center; gap: 18px; }
  .marca a { display: block; line-height: 0; }
  .marca .logo { height: 54px; width: auto; }
  .marca .logo.oscuro { display: none; }
  :root[data-tema="oscuro"] .marca .logo.claro { display: none; }
  :root[data-tema="oscuro"] .marca .logo.oscuro { display: block; }
  .sep { width: 1px; height: 44px; background: rgba(0,18,30,.22); }
  .nombre { display: flex; align-items: center; gap: 10px; }
  .nombre .icono { width: 34px; height: 34px; }
  .franja h1 {
    font-size: 17px; margin: 0; font-weight: 700; letter-spacing: 2px; color: var(--violeta);
  }
  .franja small {
    display: block; color: var(--texto2); font-size: 10.5px; font-weight: 500;
    letter-spacing: .6px; text-transform: uppercase;
  }
  .franja-derecha {
    display: flex; align-items: center; gap: 18px; font-size: .8rem; color: var(--texto2);
  }
  .franja-derecha b { color: var(--azul); }
  .tema {
    border: 1px solid var(--linea); background: transparent; color: var(--texto2);
    font-family: inherit; font-size: .72rem; letter-spacing: .04em; padding: 5px 10px;
    cursor: pointer;
  }
  .tema:hover { border-color: var(--violeta); color: var(--azul); }
  .interno {
    border: 1px solid var(--linea); padding: 4px 10px; letter-spacing: .06em;
    text-transform: uppercase; font-size: .66rem;
  }

  main { max-width: 1180px; margin: 0 auto; padding: 0 16px 56px; }
  .bajada {
    font-size: 1.02rem; max-width: 62ch; margin: 26px 0 0;
    border-left: 3px solid var(--violeta); padding-left: 14px;
  }
  .estado {
    display: flex; flex-wrap: wrap; gap: 6px 26px; margin: 18px 0 0;
    color: var(--texto2); font-size: .84rem;
  }
  .estado b { color: var(--azul); }
  .estado .fuentes { border-left: 3px solid var(--violeta); padding-left: 8px; }
  .estado .fuentes.floja { border-left-color: var(--naranja); }
  h2 {
    font-weight: 700; font-size: .74rem; letter-spacing: .16em; text-transform: uppercase;
    color: var(--texto2); margin: 36px 0 14px; scroll-margin-top: 80px;
  }

  /* El mosaico entra primero; el mapa acompaña al costado. */
  .region { display: grid; gap: 18px; grid-template-columns: 1fr 340px; align-items: start; }
  .referencia {
    display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
    font-size: .82rem; color: var(--texto2); margin: -6px 0 14px;
  }
  .referencia .eje { display: inline-grid; width: 18px; height: 18px; }
  .referencia .naranja { display: inline-block; }
  .mosaico { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(222px, 1fr)); }
  .celda {
    display: flex; align-items: center; gap: 10px; min-height: 64px; cursor: pointer;
    background: var(--superficie); border: 1px solid var(--linea); padding: 10px 12px;
  }
  .celda:hover, .celda:focus-visible { border-color: var(--violeta-claro); outline: none; }
  .celda.viva { border-color: var(--violeta); }
  .celda:target { border-color: var(--violeta); box-shadow: 0 0 0 3px rgba(140,0,224,.18);
    scroll-margin-top: 90px; }
  .celda img { flex: none; border: 1px solid var(--linea); object-fit: cover; }
  .quien { min-width: 0; }
  .quien b { display: block; font-size: .9rem; line-height: 1.25; }
  .quien small {
    display: block; color: var(--texto2); font-size: .72rem;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .luces { margin-left: auto; display: flex; gap: 4px; align-items: center; }
  .eje {
    width: 20px; height: 20px; display: grid; place-items: center; font-size: .66rem;
    font-weight: 700; color: var(--texto2); border: 1px solid var(--linea);
  }
  .eje.viva { color: #fff; background: var(--violeta); border-color: var(--violeta); }
  .naranja { width: 9px; height: 9px; border-radius: 50%; background: var(--naranja); margin-left: 3px; }

  .caja-mapa {
    background: var(--superficie); border: 1px solid var(--linea); padding: 12px;
    position: sticky; top: 16px;
  }
  svg.mapa { width: 100%; height: auto; display: block; }
  svg.mapa .pais path { fill: #E6EBEE; stroke: var(--acero); stroke-width: .5;
    vector-effect: non-scaling-stroke; }
  svg.mapa .pais .marca { fill: #E6EBEE; stroke: var(--acero); stroke-width: .8; }
  svg.mapa .pais:hover path, svg.mapa .pais:hover .marca { fill: var(--violeta-claro); }
  svg.mapa .pais.viva path, svg.mapa .pais.viva .marca { fill: var(--violeta); }
  .caja-mapa figcaption { color: var(--texto2); font-size: .72rem; margin-top: 8px; }

  .alertas { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); }
  .alerta { background: var(--superficie); border: 1px solid var(--linea); padding: 14px 16px; }
  .alerta header { display: flex; justify-content: space-between; gap: 12px; font-size: .82rem; }
  .alerta header span { color: var(--texto2); }
  .hecho { margin: 10px 0 8px; font-size: 1.02rem; line-height: 1.45; }
  /* La escala de Kent, dibujada. Siete pasos; el juicio ocupa el suyo y se lee. */
  .kent {
    display: flex; align-items: center; gap: 4px; margin: 0 0 10px;
    font-size: .64rem; color: var(--texto2);
  }
  .kent small { white-space: nowrap; letter-spacing: .04em; }
  .kent .paso {
    flex: 1; height: 12px; background: var(--linea); display: grid; place-items: center;
  }
  .kent .paso.aqui {
    flex: 3.2; height: 20px; background: var(--violeta); color: #fff; font-weight: 700;
    font-size: .68rem; letter-spacing: .02em; white-space: nowrap; padding: 0 6px;
  }
  :root[data-tema="oscuro"] .kent .paso.aqui { color: #00121E; }
  .pendiente { color: var(--texto2); }
  .meta { color: var(--texto2); font-size: .82rem; margin: 0 0 10px; }
  .grafico { margin: 0 0 10px; }
  svg.chispa { width: 100%; height: auto; display: block; }
  .grafico figcaption { color: var(--texto2); font-size: .72rem; margin-top: 4px; }
  .plazo { margin: 0 0 10px; }
  .riel { display: block; height: 6px; background: var(--linea); overflow: hidden; }
  .riel .lleno { display: block; height: 100%; background: var(--violeta); }
  .lleno.ocurrio { background: var(--violeta); }
  .lleno.no-ocurrio { background: var(--acero); }
  .lleno.sin-evidencia { background: var(--naranja); }
  .plazo small { display: block; color: var(--texto2); font-size: .74rem; margin-top: 4px; }
  .dos-voces { display: grid; grid-template-columns: 1fr 1fr; gap: 0; margin-top: 12px;
    border-top: 1px solid var(--linea); }
  .dos-voces > * { padding: 10px 12px 0; font-size: .82rem; color: var(--texto2); }
  .dos-voces > *:first-child { border-right: 1px solid var(--linea); padding-left: 0; }
  .dos-voces h4 {
    margin: 0 0 4px; font-size: .62rem; letter-spacing: .14em; text-transform: uppercase;
    color: var(--azul);
  }
  @media (max-width: 620px) {
    .dos-voces { grid-template-columns: 1fr; }
    .dos-voces > *:first-child { border-right: 0; border-bottom: 1px solid var(--linea);
      padding-bottom: 10px; padding-left: 12px; }
  }
  .disenso {
    border-left: 3px solid var(--violeta-claro); padding-left: 10px; margin: 0;
    font-size: .82rem; color: var(--texto2);
  }
  .disenso.falta { border-left-color: var(--linea); }
  .panel { font-size: .78rem; color: var(--texto2); margin: 0 0 8px; }
  .reserva { font-size: .78rem; color: var(--azul); margin: 0 0 8px;
    border-left: 3px solid var(--acero); padding-left: 10px; }

  ul.bandas { list-style: none; margin: 0; padding: 0; }
  ul.bandas li {
    display: grid; grid-template-columns: 160px 1fr 140px; gap: 12px; align-items: center;
    padding: 7px 0; font-size: .84rem;
  }
  ul.bandas .banda { font-weight: 700; }
  ul.bandas .cuenta { color: var(--texto2); text-align: right; font-variant-numeric: tabular-nums; }

  ul.calendario { list-style: none; margin: 0; padding: 0; font-size: .86rem; }
  ul.calendario li {
    display: flex; gap: 12px; align-items: baseline; padding: 8px 0;
    border-bottom: 1px solid var(--linea);
  }
  ul.calendario .pais { color: var(--violeta); font-weight: 700; font-size: .78rem; }
  ul.calendario .que { color: var(--texto2); }
  .sello { margin-left: auto; font-size: .7rem; text-transform: uppercase; letter-spacing: .06em; }
  .sello.ok { color: var(--violeta); }
  .sello.porconf { color: var(--texto2); }
  .vacio { color: var(--texto2); }

  /* La ficha del Estado */
  #ficha {
    position: fixed; top: 0; right: 0; bottom: 0; width: 390px; max-width: 100%;
    background: var(--superficie); border-left: 3px solid var(--violeta); z-index: 8000;
    overflow-y: auto; padding: 18px 20px 40px; box-shadow: -18px 0 40px rgba(0,18,30,.14);
  }
  #ficha[hidden] { display: none; }
  #ficha h3 { margin: 0; font-size: 1.1rem; }
  #ficha .bloque { color: var(--texto2); font-size: .78rem; text-transform: uppercase;
    letter-spacing: .06em; }
  #ficha h4 { font-size: .7rem; letter-spacing: .14em; text-transform: uppercase;
    color: var(--texto2); margin: 22px 0 8px; }
  #ficha .item { border-left: 3px solid var(--linea); padding-left: 10px; margin-bottom: 10px;
    font-size: .86rem; }
  #ficha .item.viva { border-left-color: var(--violeta); }
  #ficha .item small { display: block; color: var(--texto2); font-size: .76rem; }
  #ficha .cerrar {
    position: absolute; top: 12px; right: 14px; background: transparent; border: 0;
    font-size: 24px; line-height: 1; color: var(--texto2); cursor: pointer; font-family: inherit;
  }
  #ficha .aSiwa { display: inline-block; margin-top: 16px; color: var(--violeta);
    font-size: .84rem; }

  footer {
    max-width: 1180px; margin: 0 auto; padding: 18px 16px 48px; font-size: .78rem;
    color: var(--texto2); border-top: 1px solid var(--linea);
  }
  footer a { color: var(--violeta); }

  @media (max-width: 900px) {
    .region { grid-template-columns: 1fr; }
    .caja-mapa { position: static; }
    svg.mapa { max-height: 420px; }
  }
  @media (max-width: 560px) {
    .marca .logo { height: 40px; }
    .sep { display: none; }
    .franja { padding: 10px 14px; gap: 10px; }
    ul.bandas li { grid-template-columns: 1fr; gap: 4px; }
    ul.bandas .cuenta { text-align: left; }
  }
  @media print { #ficha, .gf-lanzador, .gf-globo, .gf-pop { display: none !important; } }

  /* ---- Página de alerta · ruta A: el dictamen ---- */
  .dictamen { max-width: 860px; margin: 0 auto; padding: 34px 16px 60px; }
  .dictamen .sello {
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: .68rem;
    text-transform: uppercase; letter-spacing: .14em; color: var(--texto2);
  }
  .dictamen .sello b { color: var(--violeta); }
  .dictamen h2 {
    font-size: clamp(1.5rem, 4.2vw, 2.1rem); line-height: 1.2; margin: 14px 0 18px;
    font-weight: 700; max-width: 24ch; text-wrap: balance; color: var(--azul);
    letter-spacing: 0; text-transform: none;
  }
  .dictamen .kent { max-width: 580px; }
  .dictamen .resumen { color: var(--texto2); font-size: .84rem; margin: 10px 0 24px; }
  .dictamen .cuerpo {
    display: grid; grid-template-columns: 1.15fr .85fr; gap: 32px; align-items: start;
    border-top: 1px solid var(--linea); padding-top: 22px;
  }
  .dictamen .cuerpo p { margin: 0 0 12px; font-size: .94rem; }
  .dictamen .criterio {
    border-left: 3px solid var(--violeta-claro); padding-left: 12px; margin: 22px 0 0;
    font-size: .86rem; color: var(--texto2);
  }
  .salvedades { margin: 22px 0 26px; padding: 16px 18px; border-radius: 6px;
    background: color-mix(in srgb, var(--violeta) 6%, transparent);
    border-left: 4px solid var(--violeta); }
  .salvedades h4 { margin: 0 0 6px; font-size: .74rem; letter-spacing: .09em;
    text-transform: uppercase; color: var(--violeta); }
  .salvedades .porque { margin: 0 0 10px; font-size: .8rem; color: var(--texto2); }
  .salvedades ul { margin: 0; padding-left: 18px; }
  .salvedades .corregida { margin: 12px 0 0; font-size: .78rem; color: var(--texto2);
    border-top: 1px dashed var(--linea); padding-top: 10px; }
  .salvedades li { font-size: .84rem; margin-bottom: 8px; line-height: 1.5; }
  .disarm { margin: 26px 0 0; border-top: 1px solid var(--linea); padding-top: 18px; }
  .disarm h4 { margin: 0 0 10px; font-size: .74rem; letter-spacing: .09em;
    text-transform: uppercase; color: var(--texto2); }
  .disarm .observable { margin: 0 0 8px; font-size: .88rem; }
  .disarm .tecnicas { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
  .disarm .tecnica { font-size: .72rem; padding: 3px 8px; border-radius: 3px;
    border: 1px solid var(--violeta-claro); color: var(--violeta); }
  .disarm .salvedad { margin: 0 0 18px; font-size: .79rem; color: var(--texto2);
    border-left: 3px solid var(--linea); padding-left: 12px; }
  .disarm .credito { font-size: .7rem; color: var(--texto2); margin: 0; }
  .dictamen .volver { display: inline-block; margin-bottom: 18px; color: var(--violeta);
    font-size: .82rem; text-decoration: none; }
  .tira { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 26px;
    border-top: 1px solid var(--linea); padding-top: 18px; }
  .tira img { width: 22px; border: 1px solid var(--linea); opacity: .4; }
  .tira img.viva { opacity: 1; outline: 2px solid var(--violeta); }
  .leer { display: inline-block; margin-top: 4px; color: var(--violeta); font-size: .8rem;
    font-weight: 700; text-decoration: none; }
  @media (max-width: 720px) { .dictamen .cuerpo { grid-template-columns: 1fr; gap: 18px; } }

"""


PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FEMÓNOE · alerta temprana</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap">
<link rel="stylesheet" href="@@estilos@@">
</head>
<body>

<div class="franja">
  <div class="marca">
    <a href="@@fundacion@@" target="_blank" rel="noopener"
       title="Ir a la web de la Fundación Sherman Kent">
      <img class="logo claro" src="marca/fusk-lockup-color.svg" alt="Fundación Sherman Kent">
      <img class="logo oscuro" src="marca/fusk-lockup-blanco.svg" alt="Fundación Sherman Kent"></a>
    <div class="sep"></div>
    <a class="nombre" href="index.html" title="Volver a la portada de FEMÓNOE">
      <img class="icono" src="marca/femonoe-marca.svg" alt="">
      <div>
        <h1>FEMÓNOE</h1>
        <small>Alerta temprana · América Latina y el Caribe</small>
      </div>
    </a>
  </div>
  <div class="franja-derecha">
    <span><b>@@vigentes@@</b> alertas vigentes</span>
    <span title="El detector evalúa el día de AYER, porque el de hoy todavía está incompleto y daría desvíos falsos. El robot corre cada hora.">Último día evaluado <b>@@corrida@@</b></span>
    <button type="button" id="tema" class="tema" aria-pressed="false">Fondo oscuro</button>
  </div>
</div>
<div class="banda-uso" role="note"><b>Uso interno</b> · Este tablero no sale de la Fundación hasta la Beta del 20 de octubre de 2026</div>

<main>
  <section class="apertura">
    <div class="apertura-fondo" aria-hidden="true">@@mapa3@@</div>
    <div class="apertura-texto">
      <p class="sobre">Alerta temprana · América Latina y el Caribe</p>
      <h2>Los <em>33 Estados</em>, vigilados todos los días en
        <em>tres ejes</em>.</h2>
      <p class="bajada">Gobernabilidad, seguridad y entorno informativo. Cada
        alerta dice qué anuncia, con qué probabilidad y hasta cuándo. <b>El
        criterio con que se va a resolver se fija al nacer, antes de saber el
        resultado.</b></p>
      <div class="apertura-acciones">
        <a class="boton" href="metodo.html">Cómo se produce una alerta</a>
        <a class="boton hueco" href="horizonte.html">El horizonte</a>
      </div>
      <div class="pulso-caja">@@pulso@@</div>
    </div>
    <figure class="apertura-mapa">@@mapa@@
      <figcaption>En violeta, los Estados con alerta vigente, con un foco que late sobre cada uno. El foco gris y más lento marca al Estado donde <b>una señal pasó el umbral y todavía no hay alerta</b>: la máquina vio algo y nadie lo juzgó aún. Hoy son cuatro Estados en total, y es el dato: el detector es estricto y la plataforma es joven. Los nodos unidos
        por líneas son las <a href="#zonas">zonas transfronterizas</a>: el nodo
        está en el centro de los Estados que la zona cruza, calculado de este
        mismo mapa, y <b>no pretende ser el lugar exacto de la zona</b>.
        El círculo señala a los Estados que no alcanzan tamaño de dibujo a esta
        escala. Contornos de Natural Earth 1:50 m, de dominio público.
        <b>Las Islas Malvinas integran la Argentina</b>, conforme la posición
        argentina que sigue la Fundación; el detalle, al pie.</figcaption>
    </figure>
  </section>

  <ol class="recorrido">
    <li><b>La máquina señala</b> cuando una serie se sale de lo normal. No emite
      alertas: la alerta la escribe una persona.</li>
    <li><b>Dos analistas la leen sin verse.</b> Manda la banda más baja y el plazo
      más corto.</li>
    <li><b>El décimo hombre la impugna</b> con evidencia propia, y su dictamen se
      publica al lado del juicio.</li>
    <li><b>Al vencer se resuelve sola</b> contra el criterio fijado al nacer, y
      entra al marcador.</li>
  </ol>

  <!-- Tres tarjetas, y cada una contesta una pregunta de quien lee: con cuántos
       ojos está mirando, qué hay vigente ahora, y si le acierta. Había una
       cuarta —«Reglas de alerta · v1.0»— que contestaba una pregunta de la
       Oficina, y encima **duplicada**: la franja de arriba ya dice el último día
       evaluado y la página de método ya declara la versión de los umbrales. La
       dirección preguntó el 2/10/2026 para qué servía, y la respuesta honesta
       fue que para el lector no servía. -->
  <div class="estado">
    <div class="@@alerta_fuentes@@" title="El padrón de fuentes se revisa una vez por semana, los lunes. La fecha es la del último control, no la de hoy: si se atrasa, es que el control no corrió.">
      <span class="rotulo">Fuentes que respondieron</span>
      <span class="cifra">@@fuentes_cifra@@ <small>de @@fuentes_total@@ · control semanal del @@fuentes_fecha@@</small></span></div>
    <div title="El tope es de @@tope@@ alertas NUEVAS por semana (decisión de la dirección, 22/9/2026). No limita cuántas pueden estar vigentes al mismo tiempo: una alerta vigente es una que todavía no llegó a su fecha de resolución.">
      <span class="rotulo">Alertas vigentes</span>
      <span class="cifra">@@vigentes@@ <small>se abren hasta @@tope@@ nuevas por semana</small></span></div>
    <div title="Cada alerta se resuelve el día que vence, contra el criterio que se fijó al nacer. Mientras ninguna haya vencido no hay nada que puntuar.">
      <span class="rotulo">Marcador de aciertos</span>
      <span class="cifra">@@marca_cifra@@</span></div>

  </div>

  <h2 id="mosaico" class="revela">Los 33 Estados</h2>
  <p class="referencia">
    <span class="eje viva">Gob</span> gobernabilidad ·
    <span class="eje viva">Seg</span> seguridad ·
    <span class="eje viva">Info</span> entorno informativo.
    La sigla se enciende cuando el Estado tiene alerta vigente en ese eje;
    <span class="naranja"></span> señala una alerta vencida sin evidencia suficiente
    para calificar. Cada Estado abre su ficha.</p>
  <div class="mosaico">@@celdas@@</div>

  <h2 id="zonas">Zonas transfronterizas</h2>
  @@zonas@@

  <h2 id="alertas" class="revela">Alertas</h2>
  <div class="alertas">@@tarjetas@@</div>

  <h2 id="marcador" class="revela">Marcador de aciertos</h2>
  @@bandas@@

  <h2 id="calendario">Calendario institucional</h2>
  <ul class="calendario">@@fechas@@</ul>
</main>

<aside id="ficha" hidden aria-label="Ficha del Estado"></aside>

<script>
  /* La ficha de cada Estado. Los datos ya vienen en la página: no se pide nada
     a ningún servidor, y la ficha abre igual con el archivo en el escritorio. */
  window.FEMONOE = @@fichas@@;
  window.FEMONOE_FECHA = "@@hoy@@";
  (function () {
    var panel = document.getElementById("ficha");
    var esc = function (s) {
      return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    };
    function abrir(iso) {
      var f = window.FEMONOE[iso];
      if (!f) return;
      var h = '<button class="cerrar" aria-label="Cerrar la ficha">&times;</button>' +
        '<h3>' + esc(f.nombre) + '</h3><div class="bloque">' + esc(f.bloque) +
        ' · edición del ' + esc(window.FEMONOE_FECHA || '') + '</div>';
      // Una zona explica qué es; un Estado no hace falta que lo explique.
      if (f.que_es) { h += '<p class="que-es">' + esc(f.que_es) + '</p>'; }
      // El pulso del Estado, antes que nada: es lo que estaba latiendo en la
      // portada y tiene que seguir latiendo acá. El SVG viene armado de
      // Python; no se escapa porque lo genera la casa, no un tercero.
      if (f.pulso && f.pulso.length) {
        h += '<h4>Cómo viene</h4><div class="pulso-ficha">';
        f.pulso.forEach(function (x) {
          h += '<div class="fila' + (x.vivo ? ' viva' : '') + '">' +
            '<span class="rot">' + esc(x.eje) + (x.vivo ? ' <i>alerta vigente</i>' : '') +
            '</span>' + x.svg +
            '<small>' + esc(x.nombre) + ' · 90 días · máximo ' + esc(x.maximo) +
            ' · la línea punteada marca la mediana</small></div>';
        });
        h += '</div>';
      }
      // Los corredores comerciales de la zona. Van antes de las alertas porque
      // **no son una alerta**: Comtrade se actualiza por año, así que un cambio
      // entre corridas sería un artefacto del calendario de la fuente. Son
      // contexto permanente del cruce, y se dice.
      if (f.corredores && f.corredores.length) {
        h += '<h4>Corredores comerciales</h4>' +
          '<p class="de-donde">Diferencia entre lo que un Estado declara haber ' +
          'exportado al otro y lo que el otro declara haber importado de él, el ' +
          'mismo año. <b>No es una alerta</b>: la fuente se actualiza por año.</p>' +
          '<div class="corredores">';
        f.corredores.forEach(function (c) {
          var pct = (c.brecha_pct == null) ? '—' :
            (c.brecha_pct > 0 ? '+' : '') + Math.round(c.brecha_pct) + ' %';
          h += '<div class="corr' + (c.marcado ? ' marcado' : '') + '">' +
            '<b>' + esc(c.par) + '</b><span class="pct">' + esc(pct) + '</span>' +
            '<small>' + esc(c.de) + ' → ' + esc(c.a) +
            (c.sentido ? ' · ' + esc(c.sentido) : '') +
            (c.marcado ? ' · <i>lo señala SIWA</i>' : '') + '</small></div>';
        });
        h += '</div>';
        if (f.corredores_fuente && f.corredores_fuente.nombre) {
          h += '<p class="de-donde">Fuente: ' + esc(f.corredores_fuente.nombre) +
            ' · ' + esc(f.corredores_fuente.licencia || '') +
            (f.corredores_fuente.medido_en ?
              ' · medido el ' + esc(String(f.corredores_fuente.medido_en).slice(0, 10)) : '') +
            '</p>';
        }
      }
      h += '<h4>Alertas</h4>';
      if (!f.alertas.length) {
        h += '<p class="vacio">Sin alertas vigentes ni vencidas' +
          (f.que_es ? ' en esta zona' : '') + '.</p>';
      } else {
        f.alertas.forEach(function (a) {
          var viva = (a.estado === "publicada" || a.estado === "curada");
          h += '<div class="item' + (viva ? ' viva' : '') + '"><b>' + esc(a.eje) + '</b> — ' +
            esc(a.hecho) + '<small>' + esc(a.estado) +
            (a.probabilidad ? ' · ' + esc(a.probabilidad) : '') +
            (a.vence ? ' · vence ' + esc(a.vence) : '') +
            (a.resultado ? ' · ' + esc(a.resultado) : '') + '</small></div>';
        });
      }
      h += '<h4>Señales de los últimos días</h4>';
      if (!f.senales.length) {
        h += '<p class="vacio">Ninguna medición superó el umbral ' +
          (f.que_es ? 'de la zona' : 'del Estado') +
          ' en los últimos catorce días.</p>';
      } else {
        f.senales.forEach(function (s) {
          h += '<div class="item"><b>' + esc(s.fecha) + '</b> · ' + esc(s.eje) +
            '<small>' + esc(s.detalle) + ' — fuentes: ' + esc((s.familias || []).join(", ")) +
            '</small></div>';
        });
      }
      if (f.fechas.length) {
        h += '<h4>Calendario</h4>';
        f.fechas.forEach(function (e) {
          h += '<div class="item"><b>' + esc(e.fecha) + '</b> · ' + esc(e.titulo) +
            '<small>' + (e.confirmado ? 'confirmada' : 'sin confirmar') + '</small></div>';
        });
      }
      // Una zona no tiene página en SIWA: SIWA mide Estados. Omitir el enlace es
      // mejor que ofrecer uno que lleva a ninguna parte.
      if (f.siwa) {
        h += '<a class="aSiwa" href="' + esc(f.siwa) + '" target="_blank" rel="noopener">' +
          esc(f.nombre) + ' en SIWA: situación actual con cifras calificadas &nearr;</a>';
      }
      panel.innerHTML = h;
      panel.hidden = false;
      panel.querySelector(".cerrar").onclick = cerrar;
      panel.scrollTop = 0;
    }
    function cerrar() { panel.hidden = true; }
    document.addEventListener("click", function (ev) {
      // `data-iso` para un Estado, `data-zona` para una zona. Hasta el
      // 2/10/2026 sólo se leía la primera, así que las diez celdas de zona se
      // podían enfocar y tocar y no abrían nada.
      var celda = ev.target.closest(".celda");
      if (celda) { abrir(celda.dataset.iso || celda.dataset.zona); return; }
      var pais = ev.target.closest("svg.mapa .pais");
      if (pais) { abrir(pais.dataset.iso); return; }
      var zona = ev.target.closest("svg.mapa .zona");
      if (zona) { abrir(zona.dataset.zona); return; }
      if (!panel.hidden && !ev.target.closest("#ficha")) cerrar();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") cerrar();
      if ((ev.key === "Enter" || ev.key === " ") && document.activeElement &&
          document.activeElement.classList.contains("celda")) {
        ev.preventDefault();
        abrir(document.activeElement.dataset.iso ||
              document.activeElement.dataset.zona);
      }
    });
    /* La guía lleva a #pais-XXX: ahí también se abre la ficha. */
    function porAncla() {
      var m = /^#pais-([A-Z]{3})$/.exec(location.hash || "");
      if (m) abrir(m[1]);
    }
    window.addEventListener("hashchange", porAncla);
    porAncla();
  })();
</script>

<script>
  (function () {
    var raiz = document.documentElement, boton = document.getElementById("tema");
    function poner(modo) {
      raiz.setAttribute("data-tema", modo);
      boton.textContent = modo === "oscuro" ? "Fondo claro" : "Fondo oscuro";
      boton.setAttribute("aria-pressed", modo === "oscuro" ? "true" : "false");
    }
    var guardado = null;
    try { guardado = localStorage.getItem("femonoe-tema"); } catch (e) { guardado = null; }
    poner(guardado === "oscuro" ? "oscuro" : "claro");
    boton.onclick = function () {
      var nuevo = raiz.getAttribute("data-tema") === "oscuro" ? "claro" : "oscuro";
      poner(nuevo);
      try { localStorage.setItem("femonoe-tema", nuevo); } catch (e) { /* sin memoria */ }
    };
  })();
</script>

<script defer src="guia/guia-femonoe.js"></script>

<footer>
  <b>Equipo de Análisis · Fundación Sherman Kent.</b>
  Página generada el @@hoy@@. Uso interno hasta la Beta del 20 de octubre de 2026.
  Ninguna alerta se publica sin el dictamen del décimo hombre al lado ni sin la
  curaduría de la dirección. El naranja señala una sola cosa: alerta vencida sin
  evidencia suficiente para calificar.
  <p><b>Sobre el mapa.</b> Las Islas Malvinas se dibujan como parte de la Argentina:
  la Fundación tiene sede en la Argentina y sigue la posición argentina. Natural Earth
  —la fuente de todos estos contornos— clasifica al archipiélago como territorio en
  disputa administrado por el Reino Unido, y las Naciones Unidas lo tienen inscripto
  como territorio no autónomo con una disputa de soberanía pendiente de negociación
  entre ambos Estados. Ningún mapa es neutral en un territorio en disputa: dibujarlo de
  un lado, del otro u omitirlo son tres posiciones. Esta es la que toma este registro, y
  queda dicha.</p>
  <a href="@@fundacion@@" target="_blank" rel="noopener">fundacionkent.org</a>
  <p>Programa libre bajo <a href="https://www.gnu.org/licenses/agpl-3.0.html"
  target="_blank" rel="noopener">AGPL-3.0</a> · código en
  <a href="https://github.com/fundacion-sherman-kent/femonoe" target="_blank"
  rel="noopener">github.com/fundacion-sherman-kent/femonoe</a>.
  Banderas de flag-icons (MIT); contornos de Natural Earth (dominio público).</p>
</footer>
<script>
  // Lo que llega a la vista, entra.
  //
  // **Por qué no usa `IntersectionObserver`.** Es la herramienta correcta para
  // esto, pero el 2/10/2026 no entregó una sola llamada en el entorno donde la
  // Oficina verifica, ni siquiera creada a mano sobre un elemento a la vista.
  // Puede ser una limitación de ese entorno y no del navegador del lector —
  // pero **una función que no se puede comprobar no se publica**. Un recorrido
  // sobre la posición de cada pieza es más tosco, se puede medir, y con unas
  // decenas de piezas no cuesta nada.
  //
  // El estado por defecto del sitio es «todo a la vista»: si este programa no
  // corre, no se pierde nada. La animación se agrega; nunca se resta.
  (function () {
    var piezas = [].slice.call(document.querySelectorAll(".revela"));
    if (!piezas.length) { return; }
    var pedido = false;
    function mirar() {
      pedido = false;
      var alto = window.innerHeight || document.documentElement.clientHeight;
      for (var i = piezas.length - 1; i >= 0; i--) {
        var r = piezas[i].getBoundingClientRect();
        // Entra cuando su borde superior cruza el 92 % de la pantalla: un poco
        // antes de llegar abajo del todo, para que no aparezca de golpe.
        //
        // **Sin exigir que siga a la vista.** La primera versión pedía además
        // `r.bottom > 0`, y entonces una pieza que se pasaba de largo sin haber
        // sido mirada —por un salto de ancla, por una vuelta atrás, por rodar
        // rápido— quedaba invisible para siempre. Una animación de entrada que
        // puede dejar una sección en blanco no es una animación: es un defecto.
        if (r.top < alto * 0.92) {
          piezas[i].classList.add("visible");
          piezas.splice(i, 1);          // entra una vez y se deja de mirar
        }
      }
      if (!piezas.length) {
        window.removeEventListener("scroll", pedir);
        window.removeEventListener("resize", pedir);
      }
    }
    // Sin `requestAnimationFrame`: el 2/10/2026 no se entregó de forma fiable
    // en el entorno donde la Oficina verifica, y una entrada que a veces no
    // ocurre deja secciones en blanco. El freno por tiempo es más tosco y se
    // puede medir. Con unas decenas de piezas, el costo es imperceptible.
    var ultimo = 0;
    function pedir() {
      var ahora = Date.now();
      if (pedido || ahora - ultimo < 80) { return; }
      ultimo = ahora;
      pedido = true;
      setTimeout(mirar, 0);
    }
    window.addEventListener("scroll", pedir, { passive: true });
    window.addEventListener("resize", pedir);
    mirar();
  })();
</script>
</body>
</html>
"""




PLANTILLA_ALERTA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@pais@@ · @@eje@@ · FEMÓNOE</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap">
<link rel="stylesheet" href="@@estilos@@">
</head>
<body>

<div class="franja">
  <div class="marca">
    <a href="@@fundacion@@" target="_blank" rel="noopener"
       title="Ir a la web de la Fundación Sherman Kent">
      <img class="logo claro" src="@@base@@marca/fusk-lockup-color.svg" alt="Fundación Sherman Kent">
      <img class="logo oscuro" src="@@base@@marca/fusk-lockup-blanco.svg" alt="Fundación Sherman Kent"></a>
    <div class="sep"></div>
    <a class="nombre" href="@@base@@index.html" title="Volver a la portada de FEMÓNOE">
      <img class="icono" src="@@base@@marca/femonoe-marca.svg" alt="">
      <div><h1>FEMÓNOE</h1><small>Alerta temprana · América Latina y el Caribe</small></div>
    </a>
  </div>
  <div class="franja-derecha">
    <button type="button" id="tema" class="tema" aria-pressed="false">Fondo oscuro</button>
  </div>
</div>
<div class="banda-uso" role="note"><b>Uso interno</b> · Este tablero no sale de la Fundación hasta la Beta del 20 de octubre de 2026</div>

<main class="dictamen">
  <a class="volver" href="@@base@@index.html">&larr; Los 33 Estados</a>
  <div class="sello"><span>@@pais@@</span> · <span>@@eje@@</span> ·
    <b>@@estado@@</b> · <span>@@nace@@</span></div>
  @@descarte@@
  <h2>@@hecho@@</h2>
  @@banda@@
  <p class="resumen">@@resumen@@</p>

  @@salvedades@@

  <div class="cuerpo">
    <div>@@fundamento@@</div>
    <figure style="margin:0">@@chispa@@@@pie@@</figure>
  </div>

  @@plazo@@

  <p class="criterio"><b>Criterio de resolución, fijado al nacer la alerta.</b>
    @@criterio@@</p>

  @@disarm@@

  @@disenso@@

  <div class="tira" title="Los 33 Estados; en violeta, el de esta alerta">@@tira@@</div>
</main>

<script>
  (function () {
    var raiz = document.documentElement, boton = document.getElementById("tema");
    function poner(modo) {
      raiz.setAttribute("data-tema", modo);
      boton.textContent = modo === "oscuro" ? "Fondo claro" : "Fondo oscuro";
      boton.setAttribute("aria-pressed", modo === "oscuro" ? "true" : "false");
    }
    var guardado = null;
    try { guardado = localStorage.getItem("femonoe-tema"); } catch (e) { guardado = null; }
    poner(guardado === "oscuro" ? "oscuro" : "claro");
    boton.onclick = function () {
      var nuevo = raiz.getAttribute("data-tema") === "oscuro" ? "claro" : "oscuro";
      poner(nuevo);
      try { localStorage.setItem("femonoe-tema", nuevo); } catch (e) { /* sin memoria */ }
    };
  })();</script>

<footer>
  <b>Equipo de Análisis · Fundación Sherman Kent.</b> Alerta @@id@@, página generada el @@hoy@@.
  Uso interno hasta la Beta del 20 de octubre de 2026.
  <p>Programa libre bajo <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank"
  rel="noopener">AGPL-3.0</a> · código en
  <a href="https://github.com/fundacion-sherman-kent/femonoe" target="_blank"
  rel="noopener">github.com/fundacion-sherman-kent/femonoe</a>.</p>
</footer>
<script>
  // Lo que llega a la vista, entra.
  //
  // **Por qué no usa `IntersectionObserver`.** Es la herramienta correcta para
  // esto, pero el 2/10/2026 no entregó una sola llamada en el entorno donde la
  // Oficina verifica, ni siquiera creada a mano sobre un elemento a la vista.
  // Puede ser una limitación de ese entorno y no del navegador del lector —
  // pero **una función que no se puede comprobar no se publica**. Un recorrido
  // sobre la posición de cada pieza es más tosco, se puede medir, y con unas
  // decenas de piezas no cuesta nada.
  //
  // El estado por defecto del sitio es «todo a la vista»: si este programa no
  // corre, no se pierde nada. La animación se agrega; nunca se resta.
  (function () {
    var piezas = [].slice.call(document.querySelectorAll(".revela"));
    if (!piezas.length) { return; }
    var pedido = false;
    function mirar() {
      pedido = false;
      var alto = window.innerHeight || document.documentElement.clientHeight;
      for (var i = piezas.length - 1; i >= 0; i--) {
        var r = piezas[i].getBoundingClientRect();
        // Entra cuando su borde superior cruza el 92 % de la pantalla: un poco
        // antes de llegar abajo del todo, para que no aparezca de golpe.
        //
        // **Sin exigir que siga a la vista.** La primera versión pedía además
        // `r.bottom > 0`, y entonces una pieza que se pasaba de largo sin haber
        // sido mirada —por un salto de ancla, por una vuelta atrás, por rodar
        // rápido— quedaba invisible para siempre. Una animación de entrada que
        // puede dejar una sección en blanco no es una animación: es un defecto.
        if (r.top < alto * 0.92) {
          piezas[i].classList.add("visible");
          piezas.splice(i, 1);          // entra una vez y se deja de mirar
        }
      }
      if (!piezas.length) {
        window.removeEventListener("scroll", pedir);
        window.removeEventListener("resize", pedir);
      }
    }
    // Sin `requestAnimationFrame`: el 2/10/2026 no se entregó de forma fiable
    // en el entorno donde la Oficina verifica, y una entrada que a veces no
    // ocurre deja secciones en blanco. El freno por tiempo es más tosco y se
    // puede medir. Con unas decenas de piezas, el costo es imperceptible.
    var ultimo = 0;
    function pedir() {
      var ahora = Date.now();
      if (pedido || ahora - ultimo < 80) { return; }
      ultimo = ahora;
      pedido = true;
      setTimeout(mirar, 0);
    }
    window.addEventListener("scroll", pedir, { passive: true });
    window.addEventListener("resize", pedir);
    mirar();
  })();
</script>
</body>
</html>
"""



# --------------------------------------------------------------------------
# El pulso de la región
# --------------------------------------------------------------------------
# Las mismas siglas que el mosaico. Acá la letra iba al lado del nombre entero,
# así que no era ilegible —pero dos siglas distintas para el mismo eje en la
# misma página es peor que una sola mala.
PULSO = [("gobernabilidad", "eventos_protesta", "Gob"),
         ("seguridad", "eventos_violencia", "Seg"),
         ("entorno informativo", "ooni_panel", "Info")]


# El mapa se dibuja una sola vez, en la apertura, y las otras dos apariciones
# lo reusan. La geometria de los 33 pesa unos 150 KB: repetirla tres veces
# hacia una portada de 465 KB sin agregar una sola linea de informacion.
_REUSO = ('<svg class="mapa" viewBox="0 0 420 560" role="img" '
          'aria-label="Mapa de los 33 Estados"><use href="#mapa-alc"/></svg>')


def _pulso(dias=90):
    """Cuánto registra la región, día por día, en cada eje.

    **Por qué va arriba.** Un tablero de alerta temprana que sólo muestra las
    alertas parece vacío cuando no hay ninguna, y eso es falso: la plataforma
    mide todos los días aunque no anuncie nada. El pulso muestra el trabajo que
    se hace cuando no pasa nada, que es la mayor parte del tiempo.

    Es la suma de los 33 Estados, sin normalizar: lo que se lee es el volumen
    de la región, no una tasa. Cada eje lleva su propia escala porque medir
    protestas y bloqueos con la misma vara no compara nada."""
    hoy = date.today()
    rango = [(hoy - timedelta(days=k)).isoformat() for k in range(dias - 1, -1, -1)]
    bloques = []
    for nombre, serie, sigla in PULSO:
        s = _serie_regional(serie, rango)
        if not any(s):
            continue
        tope = max(s) or 1
        ancho, alto = 100.0, 26.0
        paso = ancho / max(len(s) - 1, 1)
        puntos = " ".join(f"{i * paso:.2f},{alto - (v / tope) * alto:.2f}"
                          for i, v in enumerate(s))
        bloques.append(
            f'<li><span class="eje viva">{sigla}</span>'
            f'<span class="que">{nombre}</span>'
            f'<svg class="pulso construye" viewBox="0 0 {ancho} {alto}" '
            f'preserveAspectRatio="none" '
            f'role="img" aria-label="{nombre}, {dias} días">'
            f'<polygon points="0,{alto} {puntos} {ancho},{alto}"/>'
            f'<polyline points="{puntos}"/></svg>'
            f'<span class="cuenta">{int(s[-1]):g} hoy · máx {int(tope):g}</span></li>')
    if not bloques:
        return ""
    return (f'<ul class="pulso-lista">{"".join(bloques)}</ul>'
            f'<p class="como">Suma de los 33 Estados, {dias} días. Cada eje con su '
            'propia escala: medir protestas y bloqueos con la misma vara no compara '
            'nada. <b>La plataforma mide todos los días, anuncie o no.</b></p>')


def _serie_regional(nombre, rango):
    """La serie sumada de los 33, en el orden de fechas que se pide."""
    try:
        serie = {}
        with (SERIES / f"{nombre}.csv").open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                serie[r["fecha"]] = serie.get(r["fecha"], 0) + float(r["valor"] or 0)
    except (OSError, ValueError):
        return []
    return [serie.get(d, 0) for d in rango]

# ---------------------------------------------------------------------------
# EL ARRANQUE VA SIEMPRE AL FINAL DEL ARCHIVO. Si queda en el medio, lo que
# se define después no existe todavía cuando corre, y el error aparece como
# un NameError lejos de la causa. Pasó tres veces: 26/9, 27/9 y 1/10.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    construir()
