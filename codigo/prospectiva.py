# -*- coding: utf-8 -*-
"""El horizonte: qué viene y qué hay que mirar, más allá del plazo de una alerta.

**Qué es, y qué no.** Una alerta anuncia un hecho con probabilidad y fecha, y se
resuelve sola contra un criterio mecánico. El horizonte no anuncia nada: dice
**qué está por venir**, **cómo viene cada eje** y **qué habría que mirar para
saber si cambia**. Son dos productos distintos y conviene que no se confundan,
porque se juzgan de maneras distintas: la alerta acierta o no, el horizonte
sirve o no sirve.

**La regla que lo gobierna.** Todo lo que dice sale de una serie o del
calendario institucional. **No hay escenarios escritos acá.** Un escenario es un
juicio, y los juicios de la casa salen del panel ciego con disenso: cuando los
haya, entran por ese camino y no por éste. Mientras tanto el horizonte hace lo
que sí puede hacer con honestidad: describir la trayectoria y nombrar el
indicador.

**Por qué la tendencia se declara y no se proyecta.** Decir «la violencia subió
un 40 % respecto del semestre anterior» es describir lo que pasó. Decir «va a
seguir subiendo» es pronosticar, y un pronóstico de la casa necesita banda,
plazo, criterio y disenso. Acá no hay ninguno de los cuatro, así que no hay
pronóstico.
"""
import csv
import json
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SERIES = RAIZ / "datos" / "series"

# Los tres ejes, con la serie que mejor los describe a lo largo del tiempo.
EJES = [("gobernabilidad", "eventos_protesta"),
        ("seguridad", "eventos_violencia"),
        ("entorno informativo", "ooni_tasa")]

# El nombre legible de la serie de cada eje. Debajo de cada eje decía
# «Serie: eventos_protesta», que es el nombre de un archivo y no significa nada
# fuera del código. El nombre técnico no se esconde: queda en el `title`.
_NOMBRE_SERIE = {"eventos_protesta": "hechos de protesta registrados",
                 "eventos_violencia": "hechos de violencia registrados",
                 "ooni_tasa": "tasa de bloqueos de sitios confirmados"}

VENTANA = 90          # días de cada mitad que se comparan

# Cuánta actividad hace falta para que una serie diga algo, **en la unidad de
# cada serie**. Era un número único, 5, aplicado por igual a un recuento de
# hechos y a una tasa por mil: para `ooni_tasa` eso no es un umbral, es un
# disparate de unidades. Medido el 2/10/2026, el máximo de esa serie en un día
# mediano es 1,00 por mil (Colombia), así que el 5 la excluía entera.
#
# **Pero el arreglo no es bajar el umbral.** Medido el mismo día: de 33 Estados,
# sólo 4 registran alguna protesta en un día mediano y sólo 1 tiene tasa de
# bloqueo por encima de cero. Con un umbral bajo, el horizonte informaría
# movimientos calculados sobre saltos de 0 a 1, que es exactamente lo que este
# mínimo existe para impedir. Lo que corresponde no es fabricar lecturas: es
# **decir por eje por qué no las hay**, que es lo que ahora hace la página.
MINIMO = {"eventos_protesta": (5, "protestas por día"),
          "eventos_violencia": (5, "hechos de violencia por día"),
          "ooni_tasa": (0.5, "bloqueos confirmados por mil mediciones")}
MINIMO_PARA_HABLAR = 5   # el que se usa si una serie no está en la tabla


def _serie(nombre):
    por_pais = {}
    f = SERIES / f"{nombre}.csv"
    if not f.exists():
        return por_pais
    with f.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                por_pais.setdefault(r["iso3"], {})[r["fecha"]] = float(r["valor"] or 0)
            except ValueError:
                continue
    return por_pais


def _mediana(xs):
    xs = sorted(xs)
    if not xs:
        return 0.0
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def tendencia(serie_pais, hoy=None, serie=None):
    """Compara los últimos 90 días con los 90 anteriores, por mediana.

    Mediana y no promedio: un solo día excepcional no debe mover la lectura de
    un semestre. Y se exige un mínimo de actividad en alguna de las dos mitades,
    porque el salto de 0 a 1 es del 100 % y no significa nada."""
    hoy = hoy or date.today()
    def tramo(desde, hasta):
        return [v for d, v in serie_pais.items() if desde <= d < hasta]
    reciente = tramo((hoy - timedelta(days=VENTANA)).isoformat(), hoy.isoformat())
    previo = tramo((hoy - timedelta(days=VENTANA * 2)).isoformat(),
                   (hoy - timedelta(days=VENTANA)).isoformat())
    if len(reciente) < VENTANA // 3 or len(previo) < VENTANA // 3:
        return {"lectura": "sin historia suficiente", "cambio": None}
    a, b = _mediana(previo), _mediana(reciente)
    minimo, unidad = MINIMO.get(serie, (MINIMO_PARA_HABLAR, "por día"))
    if max(a, b) < minimo:
        return {"lectura": "actividad baja en los dos períodos", "cambio": None,
                "antes": a, "ahora": b, "minimo": minimo, "unidad": unidad}
    if a == 0:
        return {"lectura": "aparece actividad donde no había", "cambio": None,
                "antes": a, "ahora": b}
    cambio = (b - a) / a
    # **Contra el largo plazo también**, y éste es el arreglo que importa.
    # Comparar sólo contra los 90 días previos deja que un tramo anormalmente
    # bajo infle la lectura. Pasó el 2/10/2026 con Haití: el tramo previo tenía
    # mediana 6 —el más bajo de toda la serie— y el horizonte informó +100 %.
    # Contra la mediana de todo lo medido, el alza es de +33 %. El dato que
    # abrió una alerta estaba inflado por su denominador.
    largo = _mediana(list(serie_pais.values()))
    cambio_largo = (b - largo) / largo if largo else None
    base_extrema = bool(largo) and (a <= largo * 0.75 or a >= largo * 1.33)
    if abs(cambio) < 0.15:
        lectura = "estable"
    elif cambio > 0:
        lectura = "en alza"
    else:
        lectura = "en baja"
    return {"lectura": lectura, "cambio": cambio, "antes": a, "ahora": b,
            "mediana_larga": largo, "cambio_contra_largo": cambio_largo,
            "base_extrema": base_extrema,
            "aviso": ("el período previo era atípico, así que el porcentaje contra "
                      "él exagera el movimiento: mirar el de largo plazo")
                     if base_extrema else ""}


def calendario_por_delante(meses=12, hoy=None):
    hoy = hoy or date.today()
    tope = (hoy + timedelta(days=int(meses * 30.4))).isoformat()
    f = RAIZ / "calendario.json"
    if not f.exists():
        return []
    salida = []
    for e in json.loads(f.read_text(encoding="utf-8")):
        cuando = str(e.get("fecha", ""))[:10]
        if hoy.isoformat() <= cuando <= tope:
            salida.append({"fecha": cuando, "iso3": e.get("iso3"),
                           "titulo": e.get("titulo", ""),
                           "confirmado": bool(e.get("confirmado")),
                           "confirmacion": e.get("confirmacion"),
                           "se_busco": e.get("se_busco")})
    return sorted(salida, key=lambda x: x["fecha"])


def horizonte(hoy=None):
    """Lo que el horizonte sabe decir, Estado por Estado."""
    hoy = hoy or date.today()
    series = {eje: _serie(nombre) for eje, nombre in EJES}
    fechas = calendario_por_delante(hoy=hoy)
    por_pais = {}
    for eje, nombre in EJES:
        for iso, s in series[eje].items():
            por_pais.setdefault(iso, {"ejes": {}, "fechas": []})
            por_pais[iso]["ejes"][eje] = dict(tendencia(s, hoy, nombre), serie=nombre)
    for e in fechas:
        if e["iso3"] in por_pais:
            por_pais[e["iso3"]]["fechas"].append(e)
    return {"generado": hoy.isoformat(), "ventana_dias": VENTANA,
            "calendario": fechas, "estados": por_pais}


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>El horizonte · FEMÓNOE</title>
<meta name="description" content="Qué viene en los próximos doce meses en América
  Latina y el Caribe, y cómo viene cada eje. No es un pronóstico: es qué mirar.">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap">
<link rel="stylesheet" href="estilos.css">
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
      <div><h1>FEMÓNOE</h1><small>Alerta temprana · América Latina y el Caribe</small></div>
    </a>
  </div>
  <div class="franja-derecha">
    <button type="button" id="tema" class="tema" aria-pressed="false">Fondo oscuro</button>
  </div>
</div>
<div class="banda-uso" role="note"><b>Uso interno</b> · Este tablero no sale de la Fundación hasta la Beta del 20 de octubre de 2026</div>

<main class="dictamen ancho">
  <a class="volver" href="index.html">&larr; Los 33 Estados</a>

  <div class="hero">
    <h2>El horizonte</h2>
    <p>Qué está por venir en los próximos doce meses, y cómo viene cada eje.
      <b>Esto no es un pronóstico.</b> Una alerta anuncia un hecho con
      probabilidad y fecha y se resuelve sola; el horizonte no anuncia nada:
      describe la trayectoria y nombra el indicador. Se juzgan de maneras
      distintas —la alerta acierta o no, el horizonte sirve o no sirve— y
      conviene que no se confundan.</p>
  </div>

  <h2>Lo que viene</h2>
  <p class="referencia">Fechas institucionales de los próximos doce meses. Las
    que figuran <b>sin confirmar</b> salen de fuentes públicas y todavía no se
    cotejaron contra la autoridad electoral del país: se muestran igual, porque
    omitir una fecha probable es peor que mostrarla rotulada.</p>
  <ul class="calendario">@@fechas@@</ul>

  <h2>Cómo viene cada eje</h2>
  <p class="referencia">Se compara contra <b>dos bases</b>, y conviene mirar la
    segunda: los @@ventana@@ días previos, y la mediana de todo lo medido. Si el
    período previo fue atípico, el porcentaje contra él exagera el movimiento.
    <b>Pasó el 2 de octubre de 2026 con Haití</b>, que marcaba +100 % contra un
    tramo que era el más bajo de toda su serie, y +33 % contra el largo plazo.
    Donde eso ocurre, se avisa. Mediana y no promedio: un solo día excepcional no
    debe mover la lectura de un semestre. Donde dice «actividad baja» es que la
    serie no da para hablar, y eso también se informa.</p>
  <p class="leyenda-color"><span class="llave sube"></span><b>Rojo</b>: la serie
    sube. <span class="llave baja"></span><b>Verde</b>: baja. Las tres series
    miden hechos adversos —protestas, violencia, bloqueo de sitios—, así que
    subir es deterioro. <b>El color juzga, y por eso se declara.</b> La figura
    de la izquierda es la serie de los últimos 180 días, dibujada a escala de
    cada país: sirve para ver la forma del movimiento, no para comparar un país
    con otro.</p>
  @@movimientos@@

  <h2>Lo que el horizonte no hace</h2>
  <ul class="no-hace">
    <li><b>No escribe escenarios</b><p>Un escenario es un juicio, y los juicios
      de la casa salen del panel ciego con disenso. Cuando los haya, entran por
      ese camino y no por éste.</p></li>
    <li><b>No proyecta la tendencia</b><p>Decir que la violencia subió un 40 %
      describe lo que pasó. Decir que va a seguir subiendo es pronosticar, y un
      pronóstico necesita banda, plazo, criterio y disenso. Acá no hay ninguno
      de los cuatro.</p></li>
    <li><b>No cubre lo que no mide</b><p>De @@total@@ lecturas posibles, sólo
      @@dicen@@ dicen algo. El resto son Estados con poca actividad registrada
      en las series, y se declara en vez de rellenarse.</p></li>
  </ul>
</main>

<footer>
  <b>Equipo de Análisis · Fundación Sherman Kent.</b> Horizonte generado el @@hoy@@.
  Uso interno hasta la Beta del 20 de octubre de 2026.
  <p>Programa libre bajo <a href="https://www.gnu.org/licenses/agpl-3.0.html"
  target="_blank" rel="noopener">AGPL-3.0</a>.</p>
</footer>

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


def _negritas(s):
    """Las notas del calendario se escriben con **negritas** de Markdown. Si no
    se convierten, salen crudas; y si además se cortan por la mitad —como pasó
    hasta el 2/10/2026, que el recorte a 220 caracteres partía «**El sitio no
    publica la fecha**» y dejaba un «**E» suelto en la página— salen crudas Y
    rotas. Se convierten, y no se cortan: estas notas son la declaración de un
    vacío, y un vacío declarado a medias no está declarado."""
    partes = _esc(s).split("**")
    return "".join(p if i % 2 == 0 else f"<b>{p}</b>" for i, p in enumerate(partes))


def _recortar(s, tope):
    """Corta en el espacio anterior, nunca en mitad de una palabra."""
    s = str(s)
    if len(s) <= tope:
        return s
    corte = s[:tope].rsplit(" ", 1)[0]
    return (corte or s[:tope]) + "…"


# Marcas de que un rótulo está en castellano. Sirven para elegir, cuando la
# fuente trae el mismo comicio con dos nombres unidos por un punto medio.
CASTELLANO = ("eleccion", "elecciones", "comicios", "presidencia", "legislativ",
              "municipal", "regional", "general", "asamblea", "referéndum")


def _titulo(e):
    """El rótulo del comicio, prefiriendo el castellano cuando la fuente da los dos.

    No se traduce lo que la fuente no tradujo: «Haitian Presidency» entra tal
    cual porque así lo publica ElectionGuide, y poner un nombre que la fuente no
    usa sería inventarlo. Pero cuando el propio calendario ya trae la versión en
    castellano unida con un punto medio —Brasil llega con las dos—, se muestra
    ésa."""
    t = str(e.get("titulo", ""))
    if " · " not in t:
        return t
    piezas = [p.strip() for p in t.split(" · ") if p.strip()]
    for p in piezas:
        bajo = p.lower()
        if any(m in bajo for m in CASTELLANO) and " de " in bajo:
            return p
    return piezas[0] if piezas else t


def _bandera(iso):
    return (f'<img class="bandera" src="banderas/{_esc(iso)}.png" alt="" '
            f'width="24" height="17" loading="lazy">') if iso else ""


def _chispa(valores, sube, antes=None, ahora=None, largo=None, titulo="",
            alerta=False):
    """La serie dibujada, en SVG a mano y sin biblioteca.

    SIWA dibuja sus tendencias con ECharts, que vendoriza. FEMÓNOE es una página
    estática sin dependencias —así se publica y así se imprime—, de modo que de
    SIWA se toma el **lenguaje visual** y no la herramienta: el mismo verde y el
    mismo rojo, la misma idea de que la figura va al lado del número y no en
    lugar del número. El mapa de la portada ya se dibuja así."""
    if len(valores) < 4:
        return ""
    alto, ancho = 40, 150
    tope = max(valores) or 1
    paso = ancho / (len(valores) - 1)

    def y(v):
        return alto - 4 - (v / tope) * (alto - 10)

    puntos = " ".join(f"{i * paso:.1f},{y(v):.1f}" for i, v in enumerate(valores))
    clase = "sube" if sube else "baja"
    # La mitad derecha es el período reciente y la izquierda el previo: son los
    # dos tramos que el número compara. Sin esa marca, la figura era un dibujo
    # —lo dijo la dirección el 2/10/2026— porque no se veía contra qué se mide.
    corte = ancho / 2
    piezas = [f'<rect class="tramo" x="{corte:.1f}" y="0" width="{corte:.1f}" height="{alto}"/>']
    if largo:
        piezas.append(f'<line class="mediana" x1="0" y1="{y(largo):.1f}" '
                      f'x2="{ancho}" y2="{y(largo):.1f}"/>')
    # El largo del trazo se calcula acá y viaja en el atributo: la línea se
    # dibuja sola sin una línea de JavaScript, igual que en el tablero.
    xs = [i * paso for i in range(len(valores))]
    ys = [y(v) for v in valores]
    recorrido = sum(((xs[i + 1] - xs[i]) ** 2 + (ys[i + 1] - ys[i]) ** 2) ** 0.5
                    for i in range(len(valores) - 1)) or 1
    piezas.append(f'<polyline class="linea trazo" points="{puntos}" '
                  f'stroke-dasharray="{recorrido:.0f}" style="--largo:{recorrido:.0f}"/>')
    for n, (x, v) in enumerate(((corte / 2, antes), (corte + corte / 2, ahora))):
        if v is None:
            continue
        # **El latido tiene UN solo significado en todo el sitio: hay alerta
        # vigente.** Si acá significara «la serie sube», el lector tendría que
        # aprender dos gestos iguales con sentidos distintos, y el de la portada
        # dejaría de querer decir lo que dice. El punto que late es el del
        # período reciente, que es el que la alerta está mirando.
        late = " late" if (alerta and n == 1) else ""
        piezas.append(f'<circle class="punto{late}" cx="{x:.1f}" cy="{y(v):.1f}" r="2.6"/>')
    return (f'<svg class="chispa {clase}" viewBox="0 0 {ancho} {alto}" '
            f'width="{ancho}" height="{alto}" role="img">'
            f'<title>{_esc(titulo)}</title>' + "".join(piezas) + '</svg>')


def _ultimos(serie_pais, hoy, dias=180):
    """Los últimos días de la serie de un país, con los huecos en cero."""
    desde = hoy - timedelta(days=dias)
    return [serie_pais.get((desde + timedelta(days=k)).isoformat(), 0.0)
            for k in range(dias + 1)]


def construir(salida, fundacion, nombres, vivas=None):
    h = horizonte()
    fechas = "".join(
        f'<li><time>{e["fecha"]}</time>'
        f'<span class="pais">{_bandera(e["iso3"])}'
        f'<span class="iso">{_esc(e["iso3"])}</span></span>'
        f'<span class="que">{_esc(_recortar(_titulo(e), 110))}</span>'
        f'<span class="sello {"ok" if e["confirmado"] else "porconf"}">'
        f'{"fecha cotejada" if e["confirmado"] else "fecha sin cotejar"}</span>'
        + (f'<span class="nota-fecha">{_esc((e.get("confirmacion") or {}).get("organismo", ""))} · '
           f'<a href="{_esc((e.get("confirmacion") or {}).get("donde", ""))}" target="_blank" '
           f'rel="noopener">verificado el '
           f'{(e.get("confirmacion") or {}).get("fecha", "")}</a></span>'
           if (e.get("confirmacion") or {}).get("organismo") else
           f'<span class="nota-fecha">{_negritas(e["se_busco"]["resultado"])}</span>'
           if e.get("se_busco") else "")
        + '</li>'
        for e in h["calendario"]) or '<li class="vacio">Sin fechas en los próximos doce meses.</li>'
    hoy = date.fromisoformat(h["generado"])
    series = {eje: _serie(nombre) for eje, nombre in EJES}
    movs = []
    for iso, e in h["estados"].items():
        for eje, v in e["ejes"].items():
            if v["cambio"] is None:
                continue
            pct = v["cambio"] * 100
            ancho = min(abs(pct), 100)
            movs.append((abs(pct), iso, eje, v, pct, ancho))
    movs.sort(reverse=True)

    # Los pares (Estado, eje) con alerta vigente. El horizonte no inventa el
    # dato: se lo pasa el tablero, que es quien lee los expedientes.
    con_alerta = set(vivas or ())

    def _fila(iso, eje, v, pct, ancho):
        serie = series[eje].get(iso, {})
        titulo = (f'{nombres.get(iso, iso)} · {eje}. Los 180 días de la serie. '
                  f'El tramo sombreado es el período reciente, que se compara con '
                  f'el anterior: mediana {v["antes"]:.0f} a {v["ahora"]:.0f}. '
                  f'La línea punteada es la mediana de todo lo medido.')
        largo = _mediana([x for x in serie.values()]) if serie else None
        return (f'<li class="{"sube" if pct > 0 else "baja"} revela">'
                f'<span class="banda">{_bandera(iso)}'
                f'<span>{_esc(nombres.get(iso, iso))}</span></span>'
                + _chispa(_ultimos(serie, hoy), pct > 0, v["antes"], v["ahora"],
                          largo, titulo, alerta=(iso, eje) in con_alerta)
                + f'<span class="riel"><span class="lleno avanza" '
                f'style="--hasta:{ancho:.0f}%"></span></span>'
                f'<span class="cuenta">{v["lectura"]} · {pct:+.0f} % contra el '
                f'período previo' + (f' · <b>{v["cambio_contra_largo"] * 100:+.0f} % '
                f'contra todo lo medido</b>' if v.get("cambio_contra_largo") is not None
                else "") + f' (mediana {v["antes"]:.0f} a {v["ahora"]:.0f})</span>'
                + (f'<span class="nota-fecha">{_esc(v["aviso"])}</span>'
                   if v.get("aviso") else "") + '</li>')

    # **Un eje por vez, y los tres.** La sección se llama «cómo viene cada eje»
    # y mostraba una sola lista: medido el 2/10/2026, diez de las once lecturas
    # eran de seguridad, así que de hecho mostraba un eje y prometía tres. Los
    # otros dos no tienen lecturas porque **no tienen actividad medida**, y eso
    # se dice por eje y con los números, en vez de dejar el hueco sin nombre.
    bloques = []
    for eje, nombre_serie in EJES:
        propias = [(iso, v, pct, an) for _, iso, ej, v, pct, an in movs if ej == eje]
        callados = sum(1 for e in h["estados"].values()
                       if e["ejes"].get(eje, {}).get("cambio") is None)
        minimo, unidad = MINIMO.get(nombre_serie, (MINIMO_PARA_HABLAR, "por día"))
        if propias:
            cuerpo = ('<ul class="bandas">'
                      + "".join(_fila(iso, eje, v, pct, an) for iso, v, pct, an in propias)
                      + '</ul>')
            resto = (f'<p class="callados">Los otros {callados} Estados no dan lectura '
                     f'en este eje: su serie no llega al mínimo de {minimo:g} {unidad} '
                     f'en ninguno de los dos períodos.</p>' if callados else "")
        else:
            cuerpo = ""
            resto = (f'<p class="callados"><b>Ningún Estado da lectura en este eje.</b> '
                     f'Hace falta una mediana de al menos {minimo:g} {unidad} en alguno '
                     f'de los dos períodos de 90 días, y los {callados} Estados medidos '
                     f'quedan por debajo. No es que no pase nada: es que <b>esta serie '
                     f'no alcanza para decirlo</b>, y antes de informar un movimiento '
                     f'calculado sobre un salto de cero a uno se prefiere declarar el '
                     f'vacío.</p>')
        bloques.append(f'<section class="bloque-eje"><h3>{eje}</h3>'
                       f'<p class="de-donde" title="serie: {nombre_serie}">{_NOMBRE_SERIE.get(nombre_serie, nombre_serie)} · '
                       f'{len(propias)} de {len(propias) + callados} Estados con '
                       f'lectura</p>{cuerpo}{resto}</section>')
    por_eje = "".join(bloques)

    filas = "".join(
        # El color dice la dirección: rojo sube, verde baja. Las tres series
        # miden hechos adversos —protestas, violencia, bloqueo de sitios—, así
        # que subir es deterioro. Se declara en la leyenda, porque un color que
        # juzga sin decir que juzga es peor que ninguno.
        f'<li class="{"sube" if pct > 0 else "baja"}">'
        f'<span class="banda">{_bandera(iso)}'
        f'<span>{_esc(nombres.get(iso, iso))} · {eje}</span></span>'
        + _chispa(_ultimos(series[eje].get(iso, {}), hoy), pct > 0)
        + f'<span class="riel"><span class="lleno" '
        f'style="width:{ancho:.0f}%"></span></span>'
        f'<span class="cuenta">{v["lectura"]} · {pct:+.0f} % contra el período '
        f'previo' + (f' · <b>{v["cambio_contra_largo"] * 100:+.0f} % contra todo lo '
        f'medido</b>' if v.get("cambio_contra_largo") is not None else "")
        + f' (mediana {v["antes"]:.0f} a {v["ahora"]:.0f})</span>'
        + (f'<span class="nota-fecha">{_esc(v["aviso"])}</span>'
           if v.get("aviso") else "") + '</li>'
        for _, iso, eje, v, pct, ancho in movs)
    total = sum(len(e["ejes"]) for e in h["estados"].values())
    html = PLANTILLA
    for clave, valor in {"fundacion": fundacion, "fechas": fechas,
                         "movimientos": por_eje,
                         "ventana": str(h["ventana_dias"]), "hoy": h["generado"],
                         "total": str(total), "dicen": str(len(movs))}.items():
        html = html.replace("@@" + clave + "@@", valor)
    (salida / "horizonte.html").write_text(html, encoding="utf-8")
    return {"fechas": len(h["calendario"]), "movimientos": len(movs), "total": total}
