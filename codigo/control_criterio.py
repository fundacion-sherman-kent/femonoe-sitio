# -*- coding: utf-8 -*-
"""Revisa el criterio de resolución ANTES de convocar al panel. No juzga.

**De dónde sale este programa.** El 17/11/2026 la casa corrió el ciclo completo
sobre dos alertas: cuatro analistas del panel ciego y dos dictámenes del décimo
hombre. **Las dos murieron, y ninguna por el juicio: las dos por el criterio.**

  `2026-11-10-HTI-G` — el hecho admitía actos de **dos Estados** y el criterio
  sólo enumeraba fuentes de uno. Un decreto salvadoreño del 30/9 ya enunciaba
  dos de los cuatro términos pedidos: un resolutor competente fallaba el juicio
  en diciembre **con un documento de septiembre**. La alerta nacía falsa.

  `2026-11-11-BLZ-S` — la fuente designada para el acto más vivo **no podía ver
  el acto dentro del plazo**: el listado del caso ante la Corte Internacional no
  registra nada posterior a junio de 2022. Un escrito presentado en la ventana
  se habría resuelto «ocurrió» **por rezago de la fuente, no por acierto**. Y
  contadas las siete aplicaciones del criterio, no había una sola falsificación.

Las dos fallas son **mecánicamente detectables antes de gastar un solo token de
panel**. Eso es lo que hace este programa.

**Lo que NO hace.** No juzga el hecho, no toca la banda, no decide si la alerta
sale. Dice si el criterio tiene uno de los defectos que la casa ya pagó. Un
criterio que pasa estos controles puede ser igual un mal criterio; uno que no
los pasa **ya se sabe** que va a romperse, y sale más barato saberlo antes.

Uso:
    python control_criterio.py                 revisa todos los borradores
    python control_criterio.py <ident>         revisa uno
    python control_criterio.py --con-red       además prueba las fuentes citadas
"""
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ALERTAS = RAIZ / "alertas"
SALIDA = RAIZ / "datos" / "control-criterio.json"
UA = "FEMONOE-robot/0.1 (Fundacion Sherman Kent; +https://fundacionkent.org)"

PADRON = json.loads((RAIZ / "padron.json").read_text(encoding="utf-8"))["estados"]
SERIES = [f.stem for f in (RAIZ / "datos" / "series").glob("*.csv")]


def _plano(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _estados_nombrados(texto):
    """Qué Estados del padrón aparecen nombrados en un texto.

    Se busca por nombre y por gentilicio corto, no por ISO3: un hecho se escribe
    en castellano —«ni el Ejecutivo haitiano ni el Gobierno de El Salvador»— y
    buscar «HTI» ahí no encuentra nada.
    """
    plano = _plano(texto)
    hallados = set()
    for p in PADRON:
        nombres = [p["nombre"], p.get("nombre_en", "")]
        for n in nombres:
            if n and _plano(n) in plano:
                hallados.add(p["iso3"])
    return hallados


def _dominios(texto):
    return set(re.findall(r"\b([a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)+)\b",
                          _plano(texto)))


def _responde(dominio, segundos=12):
    for esquema in ("https://", "http://"):
        try:
            req = urllib.request.Request(esquema + dominio, method="HEAD",
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=segundos) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:  # noqa: BLE001
            continue
    return None


# ── LOS CONTROLES ────────────────────────────────────────────────────────────

GACETA = ("diario oficial", "gaceta", "boletin oficial", "journal officiel",
          "moniteur", "official gazette", "registro oficial")
LEGISLATURA = ("asamblea", "congreso", "parlamento", "camara de diputados",
               "senado", "assemblee", "parliament", "house of representatives")


def c1_actor_sin_gaceta(a):
    """L-08 · Si el hecho admite actos de varios Estados, el criterio tiene que
    nombrar, PARA CADA UNO, su gaceta oficial o su órgano legislativo.

    **Por qué no alcanza con nombrar al Estado.** Pagada en `2026-11-10-HTI-G`:
    el criterio **sí** nombraba canales salvadoreños —la Presidencia y un
    ministerio— y aun así se rompió, porque el acto que lo resolvía era un
    **decreto legislativo publicado en el Diario Oficial**. Nombrar al Ejecutivo
    de un Estado y creer que se cubrió ese Estado es el error exacto: las leyes y
    los decretos no salen por la oficina de prensa.

    Se mira por cláusula: a qué Estado pertenece cada tramo del criterio y si
    ese tramo nombra su gaceta o su legislatura.
    """
    hecho = (a.get("juicio") or {}).get("hecho_anunciado") or ""
    criterio = a.get("criterio_de_resolucion") or ""
    actores = _estados_nombrados(hecho)
    if len(actores) < 2:
        return None
    nombre = {p["iso3"]: p["nombre"] for p in PADRON}
    sin_gaceta = []
    for iso in sorted(actores):
        # las cláusulas que hablan de este Estado
        tramos = [c for c in re.split(r"[;.]\s+", criterio)
                  if iso in _estados_nombrados(c)]
        texto = _plano(" ".join(tramos))
        if not any(g in texto for g in GACETA + LEGISLATURA):
            sin_gaceta.append(nombre.get(iso, iso))
    if not sin_gaceta:
        return None
    return ("El hecho admite actos de {} Estados y **no se pudo atribuir una "
            "gaceta oficial ni un órgano legislativo** a: {}. Nombrar al "
            "Ejecutivo no cubre a un Estado — las leyes y los decretos no salen "
            "por la oficina de prensa, y eso rompió la alerta de Haití del "
            "10/11/2026 (lección L-08). **Ojo con el falso positivo:** la "
            "atribución es por cláusula, así que una gaceta nombrada sin su país "
            "—«Le Moniteur, journal officiel de la République»— no se empareja. "
            "Verificar a mano y, si está, escribir el país al lado."
            .format(len(actores), ", ".join(sin_gaceta)))


def c6_sin_direccion_exacta(a):
    """El criterio tiene que nombrar **la página**, no sólo el organismo.

    Hallado el 17/11/2026 al construir este control: **ninguno** de los dos
    criterios del día traía una sola dirección completa. Decían «los comunicados
    de la Primature» o «el listado del expediente del caso», y eso obliga a quien
    resuelve a buscar y elegir, que es precisamente lo que el criterio existe
    para evitar — «tiene que poder aplicarlo alguien que no participó».

    Sin dirección exacta tampoco se puede comprobar nada de lo demás: no se sabe
    si la fuente responde, ni si está al día, ni si muestra el acto dentro del
    plazo.
    """
    criterio = a.get("criterio_de_resolucion") or ""
    if re.search(r"https?://", criterio):
        return None
    if not criterio:
        return None
    return ("El criterio nombra fuentes pero **ninguna dirección exacta**. Quien "
            "resuelve tiene que buscar y elegir, que es lo que el criterio vino a "
            "evitar; y sin dirección no se puede comprobar si la fuente responde "
            "ni si está al día.")


def c2_sin_ventana(a):
    """El criterio tiene que acotar el acto A LA VENTANA, o lo resuelve algo
    anterior.

    Pagada en `2026-11-10-HTI-G`: el criterio no exigía que el acto fuera nuevo
    ni bilateral, así que un decreto de septiembre lo satisfacía en diciembre.
    """
    criterio = _plano(a.get("criterio_de_resolucion") or "")
    if not criterio:
        return "No hay criterio de resolución escrito."
    anios = set(re.findall(r"\b(20\d\d)\b", criterio))
    tiene_fechas = len(re.findall(r"\b\d{1,2} de [a-z]+ de 20\d\d\b", criterio)) >= 2 \
        or len(re.findall(r"\b20\d\d-\d\d-\d\d\b", criterio)) >= 2
    acota = any(x in criterio for x in (
        "dentro de la ventana", "en la ventana", "entre el", "a partir del",
        "posterior al", "dictados o publicados"))
    if tiene_fechas or (anios and acota):
        return None
    return ("El criterio no acota el acto a la ventana: no trae dos fechas ni una "
            "fórmula que excluya lo anterior. Un acto previo al nacimiento de la "
            "alerta puede resolverla, y entonces nace falsa.")


def c3_no_puede_fallar(a):
    """Un criterio que no tiene con qué fallar no acredita nada.

    Pagada en `2026-11-11-BLZ-S`: siete aplicaciones del criterio entre tasa base
    y prueba retroactiva, **cero falsificaciones**, y el décimo hombre señaló que
    la banda correcta era un escalón más arriba — en la que la alerta no advierte
    nada. Es la misma lección que dio el criterio de Cloudflare, que «pasó» sobre
    cero casos.
    """
    pruebas = []
    for quien in ("indicadores", "contexto"):
        f = ALERTAS / f"{a['_ident']}-{quien}.json"
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("prueba_del_criterio"):
                pruebas.append(_plano(d["prueba_del_criterio"]))
    if not pruebas:
        return ("Ningún analista escribió la prueba del criterio corrida hacia "
                "atrás. Sin eso no se sabe si el criterio discrimina o se cumple "
                "siempre.")
    texto = " ".join(pruebas)
    # «0 de N», «ninguna», «cero» aplicadas al resultado: el criterio no falsifica
    sospechoso = re.search(r"\b0 de (\d+)\b", texto) or \
        re.search(r"\bcero (falsificacion|veces)", texto) or \
        re.search(r"\bninguna (fallo|falsifica)", texto)
    if sospechoso:
        return ("La prueba del criterio corrida hacia atrás **no lo falsifica "
                "nunca** ({}). Un criterio que se cumple siempre no mide: "
                "conviene estrechar el hecho o subir la banda, y si la banda "
                "correcta es «casi con certeza», la alerta no advierte nada."
                .format(sospechoso.group(0)))
    return None


def c4_sobre_la_propia_serie(a):
    """La dirección rechazó el molde el 13/10/2026 al descartar
    `2026-10-10-MEX-S`: «FEMÓNOE prediciendo su propia serie». Una plataforma de
    alerta temprana anuncia hechos del mundo, no el futuro de su propio contador.
    """
    hecho = _plano((a.get("juicio") or {}).get("hecho_anunciado") or "")
    if not hecho:
        return None
    if "datos/series" in hecho or any(_plano(s) in hecho for s in SERIES):
        return ("El hecho anunciado es sobre una serie propia de la plataforma. "
                "La dirección rechazó ese molde el 13/10/2026: un lector al que "
                "se le anuncia que un contador va a subir no recibió ninguna "
                "advertencia sobre la región.")
    return None


def c5_fuente_ciega(a, con_red):
    """La fuente designada tiene que poder MOSTRAR el acto dentro del plazo.

    Pagada en `2026-11-11-BLZ-S`: el listado del caso ante la Corte no registra
    nada posterior a junio de 2022, así que un escrito presentado en la ventana
    no se habría visto al vencer. La alerta se habría resuelto por rezago de la
    fuente y no por acierto.

    Sin red se limita a decir cuántas fuentes cita. Con `--con-red` las pide y
    marca la que no responde: **una fuente que no contesta hoy tampoco va a
    contestar el día de resolver**.
    """
    criterio = a.get("criterio_de_resolucion") or ""
    doms = {d for d in _dominios(criterio)
            if not d.endswith((".json", ".csv", ".md", ".py", ".html"))}
    if not doms:
        return ("El criterio no nombra ninguna fuente consultable. Sin fuente "
                "nombrada, resolver la alerta es una opinión.")
    if not con_red:
        return None
    mudas = []
    for d in sorted(doms):
        estado = _responde(d)
        if estado is None or estado >= 500:
            mudas.append(f"{d} ({estado or 'no respondió'})")
    if mudas:
        return ("Fuentes del criterio que no responden hoy: {}. Una fuente que "
                "no contesta ahora tampoco va a contestar el día de resolver, y "
                "la alerta se cerraría «sin evidencia» por un defecto que se "
                "podía ver al nacer.".format(", ".join(mudas)))
    return None


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "setiembre", "octubre", "noviembre", "diciembre")


def _fechas_citadas(texto, anio_por_defecto=None):
    """Toda fecha que el texto nombre.

    **Con y sin año.** El fundamento de la alerta de Haití decía «15 de
    diciembre» a secas, sin el año, y la primera versión de esto lo perdía: el
    control no se disparaba sobre el caso que lo motivó. Una fecha sin año se
    resuelve al año que la vuelve posterior a la referencia, que es como la
    escribe cualquiera que habla del futuro inmediato.
    """
    plano = _plano(texto)
    salida = set()
    for m in re.finditer(r"(\d{1,2}) de ([a-z]+) de (20\d\d)", plano):
        dia, mes, anio = m.groups()
        if mes in MESES:
            n = MESES.index(mes) + 1
            if n >= 12:
                n = 12
            try:
                salida.add(date(int(anio), min(n, 12), int(dia)))
            except ValueError:
                pass
    for m in re.finditer(r"(20\d\d)-(\d\d)-(\d\d)", plano):
        try:
            salida.add(date(*map(int, m.groups())))
        except ValueError:
            pass
    if anio_por_defecto:
        for m in re.finditer(r"\b(\d{1,2}) de ([a-z]+)\b(?! de 20)", plano):
            dia, mes = m.groups()
            if mes not in MESES:
                continue
            n = MESES.index(mes) + 1
            n = 12 if n >= 12 else n
            for anio in (anio_por_defecto, anio_por_defecto + 1):
                try:
                    salida.add(date(anio, min(n, 12), int(dia)))
                except ValueError:
                    pass
    return salida


def c7_plazo_mas_corto_que_el_proceso(a):
    """El plazo tiene que abrazar el proceso que se mide, o lo resuelve el
    calendario y no el análisis.

    **Pagada en `2026-10-15-COL-G`, resuelta el 17/11/2026 como NO OCURRIÓ.** El
    hecho era un paro nacional convocado por la CUT o Fecode dentro de una
    ventana de 21 días. **La central lo convocó para siete días después del
    cierre.** Y lo peor: el fundamento **ya advertía** que la fecha más probable
    caía fuera del plazo. No se leyó mal a los actores — se los leyó bien y se
    fijó un plazo más corto que el proceso. Un paro nacional se convoca con
    semanas de anticipación; la ventana cerraba antes de que el calendario
    sindical pudiera expresarse.

    El mismo defecto en `2026-11-10-HTI-G`: el analista señaló que el nodo
    institucional más cargado del trimestre —la lista provisional de
    candidaturas— caía **28 días después del nacimiento** y el plazo máximo era
    21, y recomendó una alerta sucesora que lo abrazara.

    **Dos maneras de detectarlo, las dos mecánicas.** Una: el propio expediente
    nombra una fecha posterior al vencimiento. Otra: el calendario institucional
    tiene un nodo de ese Estado poco después de vencer.
    """
    j = a.get("juicio") or {}
    vence = j.get("vence")
    if not vence:
        return None
    try:
        vence = date.fromisoformat(vence)
    except ValueError:
        return None
    texto = " ".join(str(j.get(k) or "") for k in
                     ("hecho_anunciado", "fundamento")) + " " +         str(a.get("criterio_de_resolucion") or "")
    AVISA = ("fuera del plazo", "fuera de la ventana", "despues del cierre",
             "mas alla del plazo", "posterior al vencimiento", "excede el plazo",
             "fuera del periodo", "despues de que venza")
    dicho = [x for x in AVISA if x in _plano(texto)]
    posteriores = sorted(f for f in _fechas_citadas(texto, vence.year)
                         if vence < f <= vence.replace(year=vence.year + 1))
    avisos = []
    if dicho:
        avisos.append("**el propio expediente lo dice con todas las letras** "
                      "(«{}»): un analista ya advirtió que el hecho cae fuera "
                      "del plazo, y el plazo se fijó igual".format(dicho[0]))
    if posteriores:
        avisos.append("el expediente nombra {} fecha(s) POSTERIORES al "
                      "vencimiento ({}): {}".format(
                          len(posteriores), vence,
                          ", ".join(str(f) for f in posteriores[:4])))
    # el calendario institucional, que desde el 17/11 ya tiene fechas cargadas
    try:
        cal = json.loads((RAIZ / "calendario.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cal = []
    cerca = [e for e in cal if e.get("iso3") == a.get("iso3")
             and e.get("fecha") and vence < date.fromisoformat(e["fecha"])
             <= vence + __import__("datetime").timedelta(days=45)]
    if cerca:
        avisos.append("el calendario institucional trae {} nodo(s) de este "
                      "Estado dentro de los 45 días POSTERIORES al vencimiento: "
                      "{}".format(len(cerca),
                                  "; ".join(f'{e["fecha"]} {e["titulo"][:60]}'
                                            for e in cerca[:3])))
    if not avisos:
        return None
    return ("**El plazo puede ser más corto que el proceso que se mide.** "
            + " Y ".join(avisos) + ". Si el hecho depende de un proceso con su "
            "propio tiempo de maduración, el plazo tiene que abrazarlo: si no, "
            "el juicio se resuelve por el calendario y no por el análisis. Es lo "
            "que pasó con la alerta de Colombia del 15/10/2026, cuyo fundamento "
            "ya advertía que la fecha caería fuera del plazo.")


CONTROLES = [
    ("actor sin gaceta", c1_actor_sin_gaceta),
    ("sin dirección exacta", c6_sin_direccion_exacta),
    ("sin ventana", c2_sin_ventana),
    ("no puede fallar", c3_no_puede_fallar),
    ("sobre la propia serie", c4_sobre_la_propia_serie),
    ("plazo más corto que el proceso", c7_plazo_mas_corto_que_el_proceso),
]


def revisar(ident, con_red=False):
    f = ALERTAS / f"{ident}.json"
    a = json.loads(f.read_text(encoding="utf-8"))
    a["_ident"] = ident
    hallazgos = []
    for nombre, control in CONTROLES:
        try:
            r = control(a)
        except Exception as e:  # noqa: BLE001
            r = f"el control no pudo correr ({type(e).__name__})"
        if r:
            hallazgos.append({"control": nombre, "que_dice": r})
    r = c5_fuente_ciega(a, con_red)
    if r:
        hallazgos.append({"control": "fuente ciega", "que_dice": r})
    return hallazgos


def main():
    con_red = "--con-red" in sys.argv
    pedidos = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not pedidos:
        pedidos = [f.stem for f in ALERTAS.glob("????-??-??-???-?.json")
                   if json.loads(f.read_text(encoding="utf-8")).get("estado")
                   in ("borrador", "curada")]
    if not pedidos:
        print("Control de criterio: no hay borradores que revisar.")
        return 0

    todo, con_hallazgo = {}, 0
    for ident in sorted(pedidos):
        h = revisar(ident, con_red)
        todo[ident] = h
        if h:
            con_hallazgo += 1
        print(f"  {ident}: {'LIMPIO' if not h else str(len(h)) + ' hallazgo(s)'}")
        for x in h:
            print(f"     · {x['control']}: {x['que_dice'][:150]}")

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps({
        "medido": date.today().isoformat(),
        "con_red": con_red,
        "_nota": ("Controles mecánicos del criterio de resolución, corridos ANTES "
                  "del panel. No juzgan el hecho: dicen si el criterio tiene uno "
                  "de los defectos que la casa ya pagó el 17/11/2026, cuando dos "
                  "alertas murieron en el disenso y ninguna por el juicio."),
        "revisadas": todo,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Control de criterio: {len(pedidos)} revisada(s) · {con_hallazgo} con hallazgos")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
