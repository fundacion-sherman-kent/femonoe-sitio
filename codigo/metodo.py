# -*- coding: utf-8 -*-
"""La página de método de FEMÓNOE.

**Por qué existe.** La Beta del 20 de octubre se presenta por el método y no
por el marcador, porque el marcador va a estar casi vacío y decir otra cosa
sería vender un historial que no hay. Lo que FEMÓNOE sí puede mostrar desde el
primer día es **cómo** produce un juicio: dos analistas que no se ven, un
disenso que se publica al lado, y un criterio de resolución fijado antes de
saber el resultado. Eso no lo publica nadie más en la región.

**Cómo se mantiene sola.** Las cifras de esta página —las bandas, la versión de
umbrales, cuántas fuentes hay en el padrón— se leen del sistema en cada
corrida. Una página de método con números escritos a mano envejece en una
semana y empieza a mentir sin que nadie lo note.
"""
import json
from datetime import date
from pathlib import Path

from tablero import direccion_de_la_tarjeta

RAIZ = Path(__file__).resolve().parent

# Los pasos del ciclo. Cada uno dice qué hace, quién lo hace y qué no.
CICLO = [
    ("La máquina señala", "detector",
     "Un robot aplica umbrales declarados a las series y marca cuándo un país "
     "se sale de lo normal en alguno de los tres ejes. **No emite alertas.** "
     "Una señal es materia prima: dice que algo se movió, no qué va a pasar."),
    ("Dos analistas la leen sin verse", "panel ciego",
     "El panel es ciego de verdad: ninguno de los dos ve el trabajo del otro "
     "hasta que los dos terminaron. Al juntarlos **manda la banda más baja y "
     "el plazo más corto** —la casa no infla lo que anuncia y se pone el plazo "
     "más exigente para sí misma—. Si anunciaron hechos distintos, eso no es "
     "acuerdo y queda consignado como divergencia."),
    ("El décimo hombre la impugna", "disenso obligatorio",
     "Un tercer analista sostiene que el hecho anunciado **no** va a ocurrir, "
     "con evidencia propia. No critica el razonamiento: defiende la tesis "
     "contraria. Su dictamen se publica al lado del juicio, no en un anexo. "
     "Ninguna alerta sale sin él, y puede dictaminar que no se publique."),
    ("La dirección cura", "curaduría",
     "La dirección aprueba, corrige o descarta. Cuando publica una alerta que "
     "el disenso objetó, las salvedades van **arriba**, antes del cuerpo, bajo "
     "el título «Lo que este juicio no afirma»."),
    ("Se publica con su fecha de vencimiento", "publicada",
     "La alerta queda a la vista con su probabilidad, su confianza y el día en "
     "que se resuelve. Una corrección posterior a la publicación se muestra "
     "con su fecha: corregir en silencio algo publicado es reescribir lo que "
     "se dijo."),
    ("Al vencer se resuelve sola", "marcador",
     "Contra el criterio que se fijó **al nacer la alerta**, antes de saber el "
     "resultado. El criterio es mecánico: dice qué archivo se abre, qué filas "
     "se toman y qué valor decide. El número que salga entra al marcador, "
     "acierte o no."),
]

NO_HACE = [
    ("No pronostica lo que no puede medir",
     "Si no hay serie que lo resuelva, no hay alerta. Un juicio sin criterio "
     "mecánico de resolución es una opinión con fecha."),
    ("No cuenta aciertos sin más",
     "Se puntúa con el Brier. Anunciar «casi con certeza no» quince veces y "
     "acertar las quince no es mérito: es no haber dicho nada."),
    ("No puntúa lo que quedó sin resolver",
     "Las alertas que cierran sin evidencia suficiente quedan fuera del "
     "puntaje y se muestran aparte. Puntuarlas sería inventar un resultado."),
    ("No republica lo que lee",
     "Los canales y cuentas públicas se usan como fuente —se cita el canal y "
     "la fecha— y el corpus no se publica. Tampoco se compilan perfiles."),
    ("No tiene zonas transfronterizas, todavía",
     "El análisis es por Estado. Un hecho repartido entre tres países produce "
     "tres señales separadas y más débiles. Está declarado porque es un hueco "
     "real, no porque esté resuelto."),
    ("No afirma una operación cuando sólo ve una huella",
     "Las señales del entorno informativo se nombran con el marco DISARM y se "
     "declaran **compatibles con** una técnica, nunca confirmadas. Observar "
     "amplificación no prueba una operación."),
]


def datos_del_sistema():
    """Las cifras salen del sistema, no de la memoria de quien escribe."""
    conf = json.loads((RAIZ / "umbrales.json").read_text(encoding="utf-8"))
    padron = json.loads((RAIZ / "redes.json").read_text(encoding="utf-8"))
    fuentes = sum(len(padron.get(k, []))
                  for k in ("rss", "youtube", "telegram", "mastodon", "bluesky"))
    calificadas = sum(1 for k in ("rss", "youtube", "telegram", "mastodon", "bluesky")
                      for x in padron.get(k, [])
                      if x.get("calidad") not in (None, "sin calificar"))
    return {"version": conf["version"], "fuentes": fuentes,
            "calificadas": calificadas,
            "tope": conf.get("tope_semanal", 5),
            "series": len(conf.get("diarias", {})) + len(conf.get("semanales", {})),
            "hoy": date.today().isoformat()}


PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- Medicion. Es la MISMA etiqueta de la Fundacion que ya usa SIWA: una sola
     propiedad y un solo flujo para las tres plataformas, que se separan despues
     por nombre de host. Si la propiedad cambia, se cambia SOLO esta linea.
     * anonymize_ip: la IP del visitante se recorta antes de guardarse.
     * linker.domains nombra los CUATRO dominios de la casa. Sin eso, un salto
       entre plataformas crea un usuario nuevo y una sesion nueva, y el dato de
       que las plataformas se alimentan entre si no se podria demostrar.
     * El evento de entrada NO se dispara aca. La casa lo crea del lado de
       Analytics, como `siwa_entrada`, a partir de page_view y la direccion.
     * PENDIENTE DE LA DIRECCION: esto instala cookies de medicion; corresponde
       el aviso de privacidad y el consentimiento (Ley 25.326). -->
<script>
  window.FEMONOE_GA = "G-L9ZDDH81GB";
</script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-L9ZDDH81GB"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', window.FEMONOE_GA, {
    anonymize_ip: true,
    linker: { domains: ['fundacionkent.org', 'siwa.fundacionkent.org',
                        'femonoe.fundacionkent.org', 'ysyry.fundacionkent.org'] }
  });
</script>
<title>Cómo trabaja FEMÓNOE · método</title>
<meta name="description" content="La máquina señala, dos analistas la leen sin verse, el décimo hombre la impugna y al vencer se resuelve sola contra el criterio fijado al nacer.">
<!-- Cómo se ve el enlace al compartirse. La tarjeta la genera
     `herramientas/tarjeta_redes.py` con la paleta del manual: no es un PNG
     suelto que alguien dibujó una vez. -->
<meta property="og:type" content="website">
<meta property="og:site_name" content="FEMÓNOE · Fundación Sherman Kent">
<meta property="og:locale" content="es_AR">
<meta property="og:title" content="Cómo trabaja FEMÓNOE · el método">
<meta property="og:description" content="La máquina señala, dos analistas la leen sin verse, el décimo hombre la impugna y al vencer se resuelve sola contra el criterio fijado al nacer.">
<link rel="canonical" href="https://femonoe.fundacionkent.org/metodo.html">
<meta property="og:url" content="https://femonoe.fundacionkent.org/metodo.html">
<meta property="og:image" content="@@tarjeta@@">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="FEMÓNOE · alerta temprana para América Latina y el Caribe">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Cómo trabaja FEMÓNOE · el método">
<meta name="twitter:description" content="La máquina señala, dos analistas la leen sin verse, el décimo hombre la impugna y al vencer se resuelve sola contra el criterio fijado al nacer.">
<meta name="twitter:image" content="@@tarjeta@@">
<meta name="description" content="El ciclo de una alerta de FEMÓNOE: panel ciego,
  disenso publicado y criterio de resolución fijado antes de saber el resultado.">
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
<div class="banda-uso" role="note"><b>Versión beta</b> · en desarrollo</div>

<main class="dictamen">
  <a class="volver" href="index.html">&larr; Los 33 Estados</a>

  <div class="hero">
    <h2>Cómo se produce <em>una alerta</em></h2>
    <p>FEMÓNOE no publica una opinión con fecha. Publica un juicio con
      probabilidad declarada, el disenso al lado, y un criterio de resolución
      que se fijó antes de saber el resultado. Esta página dice cómo, y también
      qué no hace.</p>
  </div>

  <h2 class="revela">El ciclo</h2>
  <ol class="ciclo">@@ciclo@@</ol>

  <h2 class="revela">El léxico de probabilidad</h2>
  <p class="referencia">Las siete bandas de Sherman Kent, que la Fundación usa
    textualmente. <b>Nunca se escribe 100 % ni 0 %</b>, y nunca se mezclan dos
    términos en un mismo juicio. El punto medio de cada rango es la probabilidad
    con que se puntúa en el marcador.</p>
  <ul class="bandas">@@bandas@@</ul>

  <h2 class="revela">Las fuentes</h2>
  <p>Cada fuente lleva una letra de fiabilidad del sistema Almirantazgo, de la
    <b>A</b> —registro oficial, documento primario— a la <b>F</b>, que es
    «no evaluable». Hoy el padrón tiene <b>@@fuentes@@ fuentes</b>, de las que
    <b>@@calificadas@@</b> están calificadas.</p>
  <p><b>Dos fuentes, o desciende la calificación.</b> Un dato de fuente única no
    puede alcanzar el grado máximo de credibilidad —la escala lo reserva para lo
    confirmado por otras fuentes— y <b>no sostiene un juicio de confianza
    alta</b>. Cuando una alerta descansa en una familia sola, lo dice en la
    tarjeta.</p>

  <h3>De dónde sale cada dato</h3>
  <p class="referencia">Quién lo publica, qué entrega y bajo qué condición se usa.
    La plataforma no recolecta datos propios de conflicto: los lee de estos
    proyectos, y lo dice.</p>
  <ul class="creditos">@@creditos@@</ul>

  <h2 class="revela">Lo que FEMÓNOE no hace</h2>
  <p class="referencia">Un producto sin vacíos declarados se rechaza. Éstos son
    los de la plataforma, no los de un informe.</p>
  <ul class="no-hace">@@no_hace@@</ul>

  <h2 class="revela">Las cifras de esta página</h2>
  <p class="referencia">Umbrales <b>v@@version@@</b> · @@series@@ series medidas ·
    tope de <b>@@tope@@</b> alertas nuevas por semana · generada el @@hoy@@.
    Salen del sistema en cada corrida: una página de método con números
    escritos a mano envejece en una semana y miente sin que nadie lo note.</p>
  <p class="referencia"><b>Los umbrales quedan congelados durante la prueba.</b>
    Son las reglas que deciden cuándo una señal pasa a ser alerta —cuántas veces
    por encima de lo habitual, con cuántas familias de fuentes, durante cuántas
    corridas—. Si cambiaran mientras se mide, el marcador de aciertos no
    significaría nada: no se sabría si mejoró el método o si se corrió la vara.
    Una corrección durante la prueba se declara, con su fecha y su motivo.</p>
</main>

<footer>
  <b>Equipo de Análisis · Fundación Sherman Kent.</b> Página generada el @@hoy@@.
  Versión beta en desarrollo.
  <p>Programa libre bajo <a href="https://www.gnu.org/licenses/agpl-3.0.html"
  target="_blank" rel="noopener">AGPL-3.0</a> · código en
  <a href="https://github.com/fundacion-sherman-kent/femonoe-sitio" target="_blank"
  rel="noopener">github.com/fundacion-sherman-kent/femonoe-sitio</a>.</p>
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


def _negrita(t):
    """Las dobles estrellas del texto fuente pasan a negrita de verdad."""
    partes = t.split("**")
    return "".join(p if i % 2 == 0 else "<b>" + p + "</b>"
                   for i, p in enumerate(partes))


# ═══ LOS CRÉDITOS DE LAS FUENTES ════════════════════════════════════════════
#
# **Por qué existen y por qué se generan.** Hasta el 22/10/2026 el sitio no
# nombraba a ninguna de las fuentes de las que vive: GDELT, OONI e IODA
# aparecían sólo por casualidad, dentro del texto de un juicio, y ACLED y
# Cloudflare Radar no aparecían en ninguna parte. Eso falla a dos cosas a la
# vez: la **atribución** que la licencia de ACLED exige a quien usa sus datos, y
# la **regla 2 de la casa** —toda afirmación es trazable—, que no admite un
# producto cuyo lector no puede saber de dónde salió el número.
#
# Se generan y no se escriben a mano por lo mismo que todo lo demás: el estado
# de cada familia —si ya puede corroborar o está en puesta en marcha— sale de
# `umbrales.json`, y el muro de ACLED, de lo que la propia API declaró en la
# última corrida. Un crédito escrito a mano dice el año pasado.
FUENTES_DE_LA_CASA = [
    ("acled", "ACLED", "https://acleddata.com/",
     "Armed Conflict Location &amp; Event Data Project",
     "Recuentos semanales de protesta, violencia y muertes por Estado. "
     "No se republica el listado de hechos: sólo los recuentos.",
     "Licencia de investigación: uso con atribución y sin fines comerciales. "
     "Entrega con doce meses de demora, así que da la <b>tasa base histórica</b> "
     "y nunca la señal de la semana en curso."),
    ("hechos_gdelt", "GDELT", "https://www.gdeltproject.org/",
     "The GDELT Project",
     "Hechos de protesta y de violencia codificados de prensa, del archivo "
     "diario.",
     "Cuenta <b>notas de prensa codificadas</b>, no personas en la calle, y "
     "fecha por el archivo de ingesta y no por el día del hecho."),
    ("ooni", "OONI", "https://ooni.org/",
     "Open Observatory of Network Interference",
     "Mediciones de bloqueo de sitios y aplicaciones, y su tasa.",
     "Datos abiertos."),
    ("ioda", "IODA", "https://ioda.inetintel.cc.gatech.edu/",
     "Internet Outage Detection and Analysis",
     "Alertas de corte de conectividad, y cuáles se sostienen.",
     "Datos abiertos."),
    ("cloudflare", "Cloudflare Radar", "https://radar.cloudflare.com/",
     "Cloudflare, Inc.",
     "Cortes de internet con la causa que Cloudflare les atribuye.",
     "La atribución de la causa es de Cloudflare, <b>no de la Fundación</b>, y "
     "así se cita."),
    ("oficial", "Organismos del Estado", None,
     "Autoridades electorales, policías, gobiernos y asambleas",
     "Lo que publica el propio organismo en su canal propio.",
     "Documento primario, leído en la fuente y citado textual."),
    ("redes", "Redes y mensajería", None,
     "Recolección propia de la Fundación",
     "Canales públicos de Telegram, Mastodon, Bluesky y YouTube de medios, organismos y organizaciones de los 33 Estados.",
     "Es la única familia que la casa recolecta por su cuenta. Mide <b>circulación</b>, no hechos: que algo se diga mucho no es que haya pasado."),
    (None, "Wikidata", "https://www.wikidata.org/",
     "Wikidata",
     "Fechas del calendario institucional, que después se cotejan contra la "
     "autoridad electoral de cada Estado.",
     "El título de Wikidata <b>no manda</b>: manda el textual del organismo."),
]



MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _en_castellano(iso):
    """Una fecha como la lee una persona, no como la escribe una máquina."""
    from datetime import date
    try:
        d = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return str(iso)
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _creditos():
    """La lista de fuentes, con el estado de cada familia sacado de la casa."""
    import json
    from datetime import date
    conf = json.loads((RAIZ / "umbrales.json").read_text(encoding="utf-8"))
    familias = conf.get("familias", {})
    dias = familias.get("dias_para_corroborar", 60)
    muro = None
    f = RAIZ / "datos" / "acled_muro.json"
    if f.exists():
        try:
            muro = json.loads(f.read_text(encoding="utf-8")).get("muro")
        except ValueError:
            muro = None

    salida = []
    for clave, nombre, url, quien, que, condicion in FUENTES_DE_LA_CASA:
        estado = ""
        ficha = familias.get(clave) or {}
        desde = ficha.get("desde")
        if desde:
            try:
                edad = (date.today() - date.fromisoformat(desde)).days
            except ValueError:
                edad = None
            if edad is not None and edad < dias:
                estado = ('<span class="puesta">en puesta en marcha: todavía no '
                          'corrobora</span>')
        if clave == "acled" and muro:
            condicion += (f' Muro medido en la última corrida: no deja ver nada '
                          f'posterior al <b>{_en_castellano(muro)}</b>.')
        titulo = (f'<a href="{url}" rel="noopener">{nombre}</a>' if url
                  else f'<b>{nombre}</b>')
        salida.append(f'<li><h4>{titulo}{estado}</h4>'
                      f'<p class="quien">{quien}</p>'
                      f'<p>{que}</p>'
                      f'<p class="condicion">{condicion}</p></li>')
    return "".join(salida)


def construir(salida, fundacion, punto_medio, bandas_orden):
    d = datos_del_sistema()
    ciclo = "".join(
        f'<li><b>{titulo}</b> <span class="etapa">{etapa}</span>'
        f'<p>{_negrita(texto)}</p></li>' for titulo, etapa, texto in CICLO)
    bandas = "".join(
        f'<li><span class="banda">{b}</span>'
        f'<span class="riel"><span class="anuncio" '
        f'style="left:{punto_medio[b] * 100:.0f}%"></span></span>'
        f'<span class="cuenta">punto medio {punto_medio[b] * 100:.0f} %</span></li>'
        for b in bandas_orden if b in punto_medio)
    no_hace = "".join(f'<li><b>{t}</b><p>{_negrita(x)}</p></li>' for t, x in NO_HACE)
    html = PLANTILLA
    for clave, valor in {"fundacion": fundacion, "ciclo": ciclo, "bandas": bandas,
                         "no_hace": no_hace, "creditos": _creditos(),
                         "version": d["version"],
                         "fuentes": str(d["fuentes"]),
                         "calificadas": str(d["calificadas"]),
                         "series": str(d["series"]), "tope": str(d["tope"]),
                         "hoy": d["hoy"],
                         "tarjeta": direccion_de_la_tarjeta()}.items():
        html = html.replace("@@" + clave + "@@", valor)
    (salida / "metodo.html").write_text(html, encoding="utf-8")
    return d
