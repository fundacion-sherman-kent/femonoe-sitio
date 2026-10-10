# -*- coding: utf-8 -*-
"""Ciclo de vida de una alerta de FEMÓNOE. Sin tokens: sólo ordena y controla.

La máquina detecta señales (detector.py). La alerta la escribe una persona, la
impugna el décimo hombre y la cura la dirección antes de publicarse.

  borrador  ->  panel ciego  ->  dictamen  ->  curada  ->  publicada  ->  vencida

Dos analistas leen la misma señal sin verse —analista-indicadores-femonoe y
analista-contexto-femonoe—, el décimo hombre impugna el resultado y la dirección
cura antes de publicar. Al consolidar el panel manda la banda más baja y el
plazo más corto.

  python alerta.py abrir 2026-09-20 1      abre el borrador de la señal n.º 1
  python alerta.py horizonte HTI seguridad abre desde el horizonte, sin señal
  python alerta.py tablero                 en qué anda cada alerta
  python alerta.py panel <id>              junta las dos lecturas en un juicio
  python alerta.py reservar <id> <motivo>  protege la identidad de la fuente
  python alerta.py revisar <id>            qué le falta para pasar de estado
  python alerta.py curar <id> [motivo]     la dirección la aprueba
  python alerta.py descartar <id> <motivo> la alerta no sale, y se anota por qué
  python alerta.py publicar <id>           sale al tablero
  python alerta.py vencer <id> ocurrio|no_ocurrio|sin_evidencia
  python alerta.py marcador                aciertos sobre alertas vencidas
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "colectores"))
from comun import RAIZ, padron  # noqa: E402

ALERTAS = RAIZ / "alertas"
CONF = json.loads((RAIZ / "umbrales.json").read_text(encoding="utf-8"))
NOMBRE = {p["iso3"]: p["nombre"] for p in padron()}
FIRMA = "Equipo de Análisis · Fundación Sherman Kent"
BANDAS = ["casi con certeza no", "muy improbable", "improbable", "posibilidades parejas",
          "probable", "muy probable", "casi con certeza"]
RESULTADOS = {"ocurrio": "ocurrió", "no_ocurrio": "no ocurrió",
              "sin_evidencia": "vencida sin evidencia suficiente"}
FALTA = "COMPLETAR"


ES_ALERTA = re.compile(r"^\d{4}-\d{2}-\d{2}-[A-Z]{3}-[GSI]$")


def _sigla(eje):
    return {"gobernabilidad": "G", "seguridad": "S", "entorno informativo": "I"}[eje]


def _cargar(ident):
    f = ALERTAS / f"{ident}.json"
    if not f.exists():
        sys.exit(f"No existe la alerta {ident}")
    return json.loads(f.read_text(encoding="utf-8"))


def _guardar(a):
    ALERTAS.mkdir(exist_ok=True)
    (ALERTAS / f"{a['id']}.json").write_text(
        json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    (ALERTAS / f"{a['id']}.md").write_text(tarjeta(a), encoding="utf-8")


def _todas():
    ALERTAS.mkdir(exist_ok=True)
    return sorted((json.loads(f.read_text(encoding="utf-8"))
                   for f in ALERTAS.glob("*.json") if ES_ALERTA.match(f.stem)),
                  key=lambda a: a["nace"])


def _nuevas_en_la_semana(hoy):
    """Tope de la dirección (22/9/2026): 5 alertas NUEVAS cada siete días.
    No limita cuántas pueden estar vigentes a la vez."""
    desde = hoy - timedelta(days=7)
    return [a for a in _todas() if desde < date.fromisoformat(a["nace"]) <= hoy]


def abrir(fecha, n):
    registro = json.loads((RAIZ / "senales" / f"{fecha}.json").read_text(encoding="utf-8"))
    senales = registro["senales"]
    if not 1 <= n <= len(senales):
        sys.exit(f"El {fecha} hubo {len(senales)} señales; pediste la {n}")
    s = senales[n - 1]
    hoy = date.today()
    previas = _nuevas_en_la_semana(hoy)
    tope = CONF.get("tope_semanal", 5)
    if len(previas) >= tope:
        sys.exit(f"Tope alcanzado: {len(previas)} alertas nuevas en los últimos siete días "
                 f"(el tope es {tope}). Para abrir otra, algo tiene que esperar.")
    ident = f"{fecha}-{s['iso3']}-{_sigla(s['eje'])}"
    if (ALERTAS / f"{ident}.json").exists():
        sys.exit(f"Ya existe {ident}")
    a = {
        "id": ident, "estado": "borrador", "nace": hoy.isoformat(),
        "firma": FIRMA,
        "iso3": s["iso3"], "pais": s.get("pais") or NOMBRE.get(s["iso3"], s["iso3"]),
        "eje": s["eje"],
        # Una alerta de zona nombra a la zona, y **no pierde de qué Estado salió
        # cada dato**: el reparto queda en el expediente. La zona es la unidad
        # de análisis, no una forma de borrar el origen.
        "zona": bool(s.get("zona")),
        "estados": s.get("estados"),
        "reparto": next((x.get("reparto") for x in s["senales"] if x.get("reparto")), None),
        "tambien_como_pais": s.get("tambien_como_pais"),
        "tambien_como_zona": s.get("tambien_como_zona"),
        # Capas 1 y 2: lo que trae la máquina. No se toca a mano.
        "senal": {"fecha": fecha, "orden": n, "hecho_duro": s["hecho_duro"],
                  "familias": s["familias"], "fuente_unica": s["fuente_unica"],
                  "umbrales_version": registro["umbrales_version"],
                  "umbrales_huella": registro["umbrales_huella"],
                  "detalle": [{"codigo": x.get("codigo"), "senal": x["senal"],
                               "familia": x["familia"], "valor": x.get("valor"),
                               "mediana": x.get("mediana"),
                               "detalle": x.get("detalle")} for x in s["senales"]]},
        # Capa 3: el juicio. Lo escribe el equipo de análisis.
        "juicio": {"hecho_anunciado": FALTA, "probabilidad": FALTA,
                   "confianza": FALTA, "plazo_dias": FALTA, "vence": FALTA,
                   "fundamento": FALTA},
        # Se fija al nacer, antes de saber el resultado. La capa 4 se calcula sola.
        "criterio_de_resolucion": FALTA,
        # Panel ciego: dos analistas leen la misma señal sin verse entre ellos.
        "panel": {"indicadores": None, "contexto": None, "divergencia": None},
        "dictamen": None,          # lo carga el décimo hombre
        "respuesta_de_la_oficina": FALTA,
        # Protección de fuente (dirección, 23/9/2026). La traza interna nunca se
        # borra: lo que se reserva es lo que sale publicado.
        "reserva": None,
        "curaduria": None,         # la dirección, antes de publicar
        "resultado": None,
    }
    if s["fuente_unica"]:
        a["rotulo"] = ("Fuente única: una sola familia de fuentes sostiene esta señal. "
                       "La credibilidad desciende y no sostiene confianza alta.")
    _guardar(a)
    otra = s.get("tambien_como_pais") or s.get("tambien_como_zona")
    if otra:
        print(f"  AVISO: esta señal también aparece como {', '.join(otra)} el mismo "
              "día y eje. Casi siempre es un solo hecho visto de dos maneras: "
              "**abrí una sola alerta**, la que mejor lo describa.")
    print(f"Abierta {ident} (borrador). Quedan {tope - len(previas) - 1} alertas nuevas "
          f"disponibles en la semana.")
    print(f"  {ALERTAS / (ident + '.md')}")



def abrir_horizonte(iso3, eje):
    """Abre una alerta desde el **horizonte** y no desde una señal del detector.

    **Por qué hace falta.** El detector atrapa desvíos: algo que se salió de lo
    normal. Pero un hecho anticipable no necesita salirse de nada. Haití tiene
    elección confirmada el 13 de diciembre y su eje de seguridad duplicó la
    mediana en noventa días, y **no produjo una sola señal en treinta días**,
    porque nada se disparó: el deterioro es la normalidad.

    Una plataforma de alerta temprana que sólo puede hablar cuando algo salta
    llega tarde a todo lo que estaba en el calendario. Esta vía existe para eso,
    y **se declara**: la alerta lleva `origen: horizonte` y nadie la confunde
    con una disparada por el detector.

    Lo que no cambia: el panel ciego, el disenso y la curaduría. La vía de
    entrada es distinta; el estándar del juicio es el mismo."""
    import prospectiva
    h = prospectiva.horizonte()
    estado = h["estados"].get(iso3)
    if not estado:
        sys.exit(f"{iso3} no tiene lectura en el horizonte.")
    tendencia = estado["ejes"].get(eje)
    if not tendencia:
        sys.exit(f"{iso3} no tiene lectura del eje «{eje}».")
    fechas = [e for e in h["calendario"] if e["iso3"] == iso3]
    hoy = date.today()
    previas = _nuevas_en_la_semana(hoy)
    tope = CONF.get("tope_semanal", 5)
    if len(previas) >= tope:
        sys.exit(f"Tope alcanzado: {len(previas)} alertas nuevas en siete días.")
    ident = f"{hoy.isoformat()}-{iso3}-{_sigla(eje)}"
    if (ALERTAS / f"{ident}.json").exists():
        sys.exit(f"Ya existe {ident}")
    a = {
        "id": ident, "estado": "borrador", "nace": hoy.isoformat(), "firma": FIRMA,
        "iso3": iso3, "pais": NOMBRE.get(iso3, iso3), "eje": eje,
        "origen": "horizonte",
        "senal": {
            "fecha": hoy.isoformat(), "orden": None, "hecho_duro": False,
            "familias": [tendencia.get("serie", "")], "fuente_unica": True,
            "umbrales_version": CONF["version"],
            "umbrales_huella": "no aplica · no la disparó el detector",
            "detalle": [{"codigo": "H-1", "senal": tendencia.get("serie"),
                         "familia": "hechos_gdelt",
                         "valor": tendencia.get("ahora"),
                         "mediana": tendencia.get("antes"),
                         "detalle": (f"Horizonte: {tendencia['lectura']}"
                                     + (f", {tendencia['cambio'] * 100:+.0f} %"
                                        if tendencia.get("cambio") is not None else "")
                                     + " entre los últimos 90 días y los 90 previos")}],
            "por_que_no_hubo_senal": (
                "El detector no produjo señal: no hay desvío que marcar porque "
                "el deterioro es sostenido, no repentino. Esta alerta no nace de "
                "un salto sino de una trayectoria más una fecha del calendario."),
        },
        "calendario": fechas,
        "juicio": {"hecho_anunciado": FALTA, "probabilidad": FALTA,
                   "confianza": FALTA, "plazo_dias": FALTA, "vence": FALTA,
                   "fundamento": FALTA},
        "criterio_de_resolucion": FALTA,
        "panel": {"indicadores": None, "contexto": None, "divergencia": None},
        "dictamen": None, "respuesta_de_la_oficina": FALTA,
        "reserva": None, "curaduria": None, "resultado": None,
        "rotulo": ("Nace del horizonte y no de una señal del detector: la "
                   "sostiene una trayectoria y una fecha del calendario, no un "
                   "desvío. Fuente única mientras lo sostenga una sola familia."),
    }
    _guardar(a)
    print(f"Abierta {ident} (borrador) · origen: horizonte")
    print(f"  {eje}: {tendencia['lectura']}"
          + (f" ({tendencia['cambio'] * 100:+.0f} %)"
             if tendencia.get("cambio") is not None else ""))
    for e in fechas:
        print(f"  calendario: {e['fecha']} · {e['titulo'][:56]} · "
              + ("confirmada" if e["confirmado"] else "sin confirmar"))
    print(f"  {ALERTAS / (ident + '.md')}")


def _pendientes(a):
    falta = []
    j = a["juicio"]
    for campo in ("hecho_anunciado", "probabilidad", "confianza", "plazo_dias", "fundamento"):
        if str(j.get(campo)).startswith(FALTA):
            falta.append(f"juicio.{campo}")
    if j.get("probabilidad") not in BANDAS and not str(j.get("probabilidad")).startswith(FALTA):
        falta.append("juicio.probabilidad no es una banda de Kent: " + " · ".join(BANDAS))
    if str(a["criterio_de_resolucion"]).startswith(FALTA):
        falta.append("criterio_de_resolucion (se fija al nacer, no al vencer)")
    panel = a.get("panel") or {}
    for quien in ("indicadores", "contexto"):
        if not panel.get(quien):
            falta.append(f"lectura del analista de {quien} (panel ciego)")
    if not a.get("dictamen"):
        falta.append("dictamen del décimo hombre")
    elif str(a["respuesta_de_la_oficina"]).startswith(FALTA):
        falta.append("respuesta_de_la_oficina al dictamen, objeción por objeción")
    return falta


def consolidar(ident):
    """Junta las dos lecturas del panel en un solo juicio, con una regla fija y
    escrita: **manda la banda más baja y el plazo más corto.** La más baja porque
    la casa no infla lo que anuncia; el más corto porque es el más exigente para
    ella misma. La diferencia no se esconde: queda anotada y se publica."""
    a = _cargar(ident)
    panel = a.get("panel") or {}
    # Cada analista escribe su lectura en su propio archivo, sin ver la del otro.
    # Acá se levantan las dos por primera y única vez: antes de este momento
    # nadie las tuvo juntas, que es lo que hace ciego al panel.
    for quien in ("indicadores", "contexto"):
        f = ALERTAS / f"{ident}-{quien}.json"
        if not panel.get(quien) and f.exists():
            panel[quien] = json.loads(f.read_text(encoding="utf-8"))
    a["panel"] = panel
    uno, dos = panel.get("indicadores"), panel.get("contexto")
    if not uno or not dos:
        falta = [q for q in ("indicadores", "contexto") if not panel.get(q)]
        sys.exit(f"Faltan lecturas del panel: {', '.join(falta)}. "
                 f"Se esperan en {ALERTAS}\\{ident}-<analista>.json, "
                 "escritas a ciegas.")
    # **«No hay alerta» es un resultado del panel, no un error de carga.**
    # La casa le pide a cada analista que, si la evidencia no sostiene un hecho
    # publicable, lo diga —es preferible a forzar uno—. Hasta el 5/10/2026 la
    # herramienta no sabía recibir esa respuesta: el analista de contexto de la
    # alerta de Haití escribió que no proponía anunciar nada y la consolidación
    # se cortó con «no es una banda de Kent». El panel no tenía cómo decir que
    # no, que es justamente lo que existe para poder decir.
    #
    # Un analista dice que no de dos maneras, las dos válidas: dejando la banda
    # vacía, o escribiendo `no_publicable: true`.
    def _dice_que_no(lectura):
        if lectura.get("no_publicable") is True:
            return True
        banda = str(lectura.get("probabilidad") or "").strip().lower()
        return banda not in BANDAS

    negativos = [q for q, lec in (("indicadores", uno), ("contexto", dos))
                 if _dice_que_no(lec)]
    for q, lectura in (("indicadores", uno), ("contexto", dos)):
        if q in negativos:
            continue
        # La banda se compara sin mirar mayúsculas ni espacios de borde, y se
        # normaliza a como la escribe la casa. «Muy probable» al principio de
        # una oración es la misma banda que «muy probable», y rechazar el
        # juicio de un analista por una mayúscula es rigor mal puesto.
        lectura["probabilidad"] = str(lectura.get("probabilidad", "")).strip().lower()

    if negativos:
        # **Manda la lectura más conservadora**, que es la regla de la casa
        # llevada hasta el final: si la banda más baja gobierna, «ninguna» es
        # más baja que «casi con certeza no». Un analista ciego que no encuentra
        # hecho publicable frena la alerta; no la promedia.
        a["estado"] = "borrador"
        a["panel_sin_hecho"] = {
            "quienes": negativos,
            "por_que": [str((uno if q == "indicadores" else dos).get("probabilidad") or
                            "declaró no publicable")[:400] for q in negativos],
            "regla": ("Manda la lectura más conservadora. Si un analista ciego no "
                      "encuentra hecho publicable, el panel no emite: la alerta va a "
                      "la dirección para descartarse o para que se le encargue otra "
                      "pregunta, no al décimo hombre, que impugna alertas y no la "
                      "ausencia de una."),
            "fecha": date.today().isoformat(),
        }
        a["juicio"]["probabilidad"] = ""
        _guardar(a)
        print(f"{ident} · el panel NO emite.")
        print(f"  {', '.join(negativos)} no encontró hecho publicable.")
        otro = "contexto" if negativos == ["indicadores"] else "indicadores"
        if len(negativos) == 1:
            lec = uno if otro == "indicadores" else dos
            print(f"  {otro} sí propuso uno: «{str(lec.get('hecho_anunciado'))[:110]}…» "
                  f"({lec.get('probabilidad')}, confianza {lec.get('confianza')}).")
            print("  Los dos quedan en el expediente. **Decide la dirección**: descartar, "
                  "o encargar otra pregunta sobre la misma señal.")
        return

    menor = min(uno, dos, key=lambda x: BANDAS.index(x["probabilidad"]))
    confianzas = ["baja", "media", "alta"]
    j = a["juicio"]
    j["probabilidad"] = menor["probabilidad"]
    j["plazo_dias"] = min(int(uno["plazo_dias"]), int(dos["plazo_dias"]))
    j["confianza"] = min([uno.get("confianza", "baja"), dos.get("confianza", "baja")],
                         key=lambda c: confianzas.index(c) if c in confianzas else 0)
    for campo, clave in (("hecho_anunciado", "hecho_anunciado"),
                         ("fundamento", "fundamento")):
        if uno.get(clave) == dos.get(clave):
            j[campo] = uno.get(clave)
    if uno.get("criterio_de_resolucion") == dos.get("criterio_de_resolucion"):
        a["criterio_de_resolucion"] = uno.get("criterio_de_resolucion")
    # La divergencia se mide en dos planos, y el segundo es el que importa.
    # Coincidir en la banda no es coincidir: el 27/9/2026 los dos analistas de
    # la alerta de Cuba dijeron «muy probable» sobre **hechos distintos** —uno,
    # que la tasa de bloqueo se sostiene; el otro, que la mensajería sigue sin
    # bloquearse—, y el tablero lo mostró como acuerdo. Dos respuestas seguras
    # a dos preguntas distintas no son un acuerdo: son un panel sin pregunta.
    partes = []
    if uno["probabilidad"] != dos["probabilidad"]:
        partes.append(f"difirieron en la banda: indicadores dijo "
                      f"«{uno['probabilidad']}» y contexto, «{dos['probabilidad']}». "
                      "Rige la más baja")
    else:
        partes.append(f"coincidieron en la banda «{uno['probabilidad']}»")
    if uno.get("hecho_anunciado") != dos.get("hecho_anunciado"):
        partes.append("**anunciaron hechos distintos**, así que la coincidencia de "
                      "banda no es acuerdo. Indicadores anuncia: "
                      f"«{str(uno.get('hecho_anunciado'))[:180]}». Contexto anuncia: "
                      f"«{str(dos.get('hecho_anunciado'))[:180]}». La Oficina elige "
                      "cuál se publica y por qué, y el décimo hombre impugna esa "
                      "elección")
    a["panel"]["divergencia"] = "Los dos analistas " + "; ".join(partes) + "."
    a["panel"]["mismo_hecho"] = uno.get("hecho_anunciado") == dos.get("hecho_anunciado")
    # Foto de lo que propuso el panel, antes de que la dirección toque nada. Es
    # contra esta foto que se mide después qué corrige la curaduría.
    a["juicio_propuesto"] = {"probabilidad": j["probabilidad"], "plazo_dias": j["plazo_dias"],
                             "confianza": j["confianza"],
                             "hecho_anunciado": j.get("hecho_anunciado"),
                             "criterio_de_resolucion": a.get("criterio_de_resolucion")}
    a["reglas_aplicadas"] = _aplicar_reglas(a)
    _guardar(a)
    print(f"{ident}: panel consolidado · {j['probabilidad']} · confianza {j['confianza']} "
          f"· {j['plazo_dias']} días")
    for r in a["reglas_aplicadas"]:
        print(f"  regla de curaduría aplicada: {r}")
    print("  " + a["panel"]["divergencia"])
    falta = _pendientes(a)
    for f in falta:
        print(f"  falta: {f}")


def _aplicar_reglas(a):
    """Aplica las correcciones que la dirección viene haciendo siempre y que ya
    autorizó a automatizar. Ninguna regla se aplica sola: entra en juego cuando
    la dirección la aprueba en el aprendiz. Lo aplicado queda a la vista."""
    archivo = RAIZ / "curaduria" / "reglas.json"
    if not archivo.exists():
        return []
    aplicadas = []
    j = a["juicio"]
    for regla in json.loads(archivo.read_text(encoding="utf-8")):
        if regla.get("estado") != "aprobada":
            continue
        if regla["tipo"] == "banda" and j["probabilidad"] in BANDAS:
            i = BANDAS.index(j["probabilidad"]) + int(regla["ajuste"])
            i = max(0, min(len(BANDAS) - 1, i))
            if BANDAS[i] != j["probabilidad"]:
                aplicadas.append(f"{regla['id']}: {j['probabilidad']} a {BANDAS[i]}")
                j["probabilidad"] = BANDAS[i]
        elif regla["tipo"] == "plazo":
            nuevo = max(7, min(21, int(j["plazo_dias"]) + int(regla["ajuste"])))
            if nuevo != int(j["plazo_dias"]):
                aplicadas.append(f"{regla['id']}: {j['plazo_dias']} a {nuevo} días")
                j["plazo_dias"] = nuevo
        elif regla["tipo"] == "fuente_unica" and a["senal"].get("fuente_unica"):
            aplicadas.append(f"{regla['id']}: fuente única, no se eleva a curaduría")
            a["estado"] = "detenida"
    return aplicadas


def _registrar(a, accion, motivo):
    """Todo lo que la dirección corrige o rechaza queda anotado. De acá aprende
    el aprendiz: sin registro no hay nada que aprender."""
    carpeta = RAIZ / "curaduria"
    carpeta.mkdir(exist_ok=True)
    prop = a.get("juicio_propuesto") or {}
    j = a["juicio"]
    final = {"probabilidad": j.get("probabilidad"), "plazo_dias": j.get("plazo_dias"),
             "confianza": j.get("confianza"), "hecho_anunciado": j.get("hecho_anunciado"),
             "criterio_de_resolucion": a.get("criterio_de_resolucion")}
    cambios = [k for k, v in final.items() if prop.get(k) is not None and prop.get(k) != v]
    registro = {"fecha": date.today().isoformat(), "id": a["id"], "iso3": a["iso3"],
                "eje": a["eje"], "accion": accion, "motivo": motivo,
                "propuesto": prop, "final": final, "cambios": cambios,
                "fuente_unica": a["senal"].get("fuente_unica"),
                "familias": a["senal"].get("familias"),
                "hecho_duro": a["senal"].get("hecho_duro"),
                "reglas_aplicadas": a.get("reglas_aplicadas", [])}
    with (carpeta / "registro.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + chr(10))
    return cambios


def reservar(ident, motivo):
    """Reserva la identidad de la fuente en lo publicado. **No borra la traza**:
    el expediente sigue nombrándola y por eso la alerta sigue siendo auditable
    puertas adentro. Lo que cambia es la tarjeta pública, que dice «fuente
    reservada» y el motivo, con su calificación a la vista.

    No afecta la regla de las dos fuentes: una fuente reservada sigue necesitando
    corroboración, y si es la única, la alerta se rotula igual."""
    a = _cargar(ident)
    a["reserva"] = {"aplicada": True, "motivo": motivo,
                    "autorizada_por": "dirección", "fecha": date.today().isoformat()}
    _guardar(a)
    print(f"{ident}: fuente reservada en lo publicado. Motivo: {motivo}")
    print("  La traza interna queda intacta; la corroboración sigue exigiéndose igual.")


def revisar(ident):
    a = _cargar(ident)
    falta = _pendientes(a)
    print(f"{ident} · {a['estado']}")
    if not falta:
        if not a.get("entregada"):
            j = a["juicio"]
            a["entregada"] = date.today().isoformat()
            a["juicio_propuesto"] = {
                "probabilidad": j["probabilidad"], "plazo_dias": j["plazo_dias"],
                "confianza": j["confianza"], "hecho_anunciado": j.get("hecho_anunciado"),
                "criterio_de_resolucion": a.get("criterio_de_resolucion")}
            _guardar(a)
        print("  Completa. Lista para la curaduría de la dirección.")
    for f in falta:
        print(f"  falta: {f}")
    return falta


def curar(ident, motivo=None):
    a = _cargar(ident)
    if _pendientes(a):
        sys.exit("No esta lista para curar:" + chr(10) + "  " +
                 (chr(10) + "  ").join(_pendientes(a)))
    cambios = _registrar(a, "curada", motivo)
    a["curaduria"] = {"por": "direccion", "fecha": date.today().isoformat(),
                      "motivo": motivo, "cambios": cambios}
    a["estado"] = "curada"
    _guardar(a)
    print(f"{ident}: curada por la direccion. Ya puede publicarse.")
    print("  sin correcciones" if not cambios else f"  corregido: {', '.join(cambios)}")

def descartar(ident, motivo):
    """La alerta no sale, y **se anota por qué**.

    Es un final legítimo del ciclo y no un fracaso: el disenso existe para
    frenar una alerta antes de que se publique, y cuando lo consigue tiene que
    quedar escrito. Descartar no borra nada —el expediente, las lecturas del
    panel y el dictamen quedan donde estaban— y entra al registro de curaduría
    como cualquier otra decisión, porque el aprendiz también aprende de lo que
    la dirección decide no publicar."""
    if not motivo or not motivo.strip():
        sys.exit("Una alerta no se descarta sin motivo escrito.")
    a = _cargar(ident)
    if a["estado"] in ("publicada", "vencida"):
        sys.exit(f"{ident} está en «{a['estado']}»: lo publicado no se descarta, "
                 "se vence con su resultado.")
    cambios = _registrar(a, "descartada", motivo)
    a["descarte"] = {"por": "dirección", "fecha": date.today().isoformat(),
                     "motivo": motivo,
                     "veredicto_del_decimo_hombre": (a.get("dictamen") or {}).get("veredicto")}
    a["estado"] = "descartada"
    _guardar(a)
    print(f"{ident}: descartada. No se publica.")
    print(f"  motivo: {motivo[:160]}")
    if cambios:
        print(f"  la dirección había corregido: {', '.join(cambios)}")


def publicar(ident):
    a = _cargar(ident)
    if a["estado"] != "curada":
        sys.exit(f"{ident} está en «{a['estado']}». Sin curaduría de la dirección no se publica.")
    vence = date.today() + timedelta(days=int(a["juicio"]["plazo_dias"]))
    a["juicio"]["vence"] = vence.isoformat()
    a["estado"] = "publicada"
    a["publicada"] = date.today().isoformat()
    _guardar(a)
    print(f"{ident}: publicada. Vence el {vence}.")


def vencer(ident, resultado):
    if resultado not in RESULTADOS:
        sys.exit("El resultado es ocurrio, no_ocurrio o sin_evidencia")
    a = _cargar(ident)
    if a["estado"] != "publicada":
        sys.exit(f"{ident} está en «{a['estado']}»")
    a["resultado"] = {"valor": resultado, "leyenda": RESULTADOS[resultado],
                      "cerrada": date.today().isoformat(),
                      "criterio": a["criterio_de_resolucion"]}
    a["estado"] = "vencida"
    _guardar(a)
    print(f"{ident}: {RESULTADOS[resultado]}.")


def marcador():
    vencidas = [a for a in _todas() if a["estado"] == "vencida"]
    m = CONF.get("marcador", {})
    if not vencidas:
        print("Todavía no venció ninguna alerta.")
        return
    acertadas = [a for a in vencidas if a["resultado"]["valor"] == "ocurrio"]
    naranjas = [a for a in vencidas if a["resultado"]["valor"] == "sin_evidencia"]
    leyenda = f" · {m.get('leyenda')}" if len(vencidas) < 20 else ""
    print(f"Marcador: {len(acertadas)} de {len(vencidas)} alertas vencidas ocurrieron{leyenda}")
    print(f"  sin evidencia suficiente para calificar (naranja): {len(naranjas)}")
    for banda in BANDAS:
        de_la_banda = [a for a in vencidas if a["juicio"]["probabilidad"] == banda]
        if de_la_banda:
            ok = sum(1 for a in de_la_banda if a["resultado"]["valor"] == "ocurrio")
            print(f"  {banda:20s} {ok}/{len(de_la_banda)}")


def tablero():
    todas = _todas()
    if not todas:
        print("Sin alertas todavía.")
        return
    hoy = date.today()
    nuevas = len(_nuevas_en_la_semana(hoy))
    print(f"FEMÓNOE · {len(todas)} {'alerta' if len(todas) == 1 else 'alertas'} · "
          f"{nuevas} {'nueva' if nuevas == 1 else 'nuevas'} en los últimos siete días "
          f"(tope {CONF.get('tope_semanal', 5)})")
    print("")
    for a in todas:
        cola = ""
        if a["estado"] == "publicada":
            dias = (date.fromisoformat(a["juicio"]["vence"]) - hoy).days
            cola = f" · vence en {dias} días" if dias >= 0 else f" · VENCIDA hace {-dias} días"
        elif a["estado"] == "vencida":
            cola = " · " + a["resultado"]["leyenda"]
        elif a["estado"] == "borrador":
            cola = " · falta: " + ", ".join(_pendientes(a)[:2])
        print(f"  {a['id']:22s} {a['pais']:22s} {a['estado']:12s}{cola}")


def tarjeta(a):
    j, d = a["juicio"], a.get("dictamen")
    L = [f"# {a['pais']} · {a['eje']}", "",
         f"**{j['hecho_anunciado']}**", "",
         f"- Probabilidad: **{j['probabilidad']}** · confianza {j['confianza']}",
         f"- Plazo: {j['plazo_dias']} días · vence {j.get('vence')}",
         f"- Nace: {a['nace']} · estado: **{a['estado']}**", ""]
    if a.get("rotulo"):
        L += [f"> {a['rotulo']}", ""]
    L += ["## El dato que la disparó", ""]
    for x in a["senal"]["detalle"]:
        det = x["detalle"] or f"valor {x['valor']} contra mediana {x['mediana']}"
        L.append(f"- `{x['senal']}` ({x['familia']}): {det}")
    L += ["", f"Familias de fuentes: {', '.join(a['senal']['familias'])}. "
              f"Umbrales {a['senal']['umbrales_version']} "
              f"(huella {a['senal']['umbrales_huella']}).",
          "", "## Fundamento", "", j["fundamento"], "",
          "## Criterio de resolución", "",
          f"Fijado al nacer la alerta: {a['criterio_de_resolucion']}", ""]
    panel = a.get("panel") or {}
    if panel.get("indicadores") and panel.get("contexto"):
        L += ["## El panel", "",
              f"Dos analistas leyeron la señal sin verse. {panel.get('divergencia', '')}",
              f"- Indicadores: {panel['indicadores'].get('probabilidad')} · "
              f"{panel['indicadores'].get('fundamento', '')}",
              f"- Contexto: {panel['contexto'].get('probabilidad')} · "
              f"{panel['contexto'].get('fundamento', '')}", ""]
    L += ["## El décimo hombre", ""]
    if not d:
        L.append("*Pendiente. Sin dictamen, esta alerta no pasa a la dirección.*")
    else:
        L += [f"El décimo hombre sostiene que {d['tesis']}", ""]
        for r in d.get("razones", []):
            L.append(f"- {r}")
        alternativa = f" ({d['probabilidad_alternativa']})" if d.get("probabilidad_alternativa") else ""
        L += ["", f"Tasa base: {d.get('tasa_base')}",
              f"Veredicto: **{d.get('veredicto')}**" + alternativa,
              f"Lo que lo daría por refutado: {d.get('que_me_haria_cambiar')}", "",
              "### Respuesta de la Oficina", "", a["respuesta_de_la_oficina"], ""]
    if a.get("resultado"):
        L += ["## Resultado", "",
              f"{a['resultado']['leyenda']} · cerrada el {a['resultado']['cerrada']}", ""]
    L += ["---", "", a["firma"]]
    if a.get("curaduria"):
        L.append(f"Curada por la dirección el {a['curaduria']['fecha']}.")
    return "\n".join(L) + "\n"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    orden, resto = sys.argv[1], sys.argv[2:]
    if orden == "abrir":
        abrir(resto[0], int(resto[1]))
    elif orden == "horizonte":
        abrir_horizonte(resto[0], " ".join(resto[1:]))
    elif orden == "tablero":
        tablero()
    elif orden == "panel":
        consolidar(resto[0])
    elif orden == "revisar":
        revisar(resto[0])
    elif orden == "reservar":
        if len(resto) < 2:
            sys.exit("Hace falta el motivo: python alerta.py reservar <id> <motivo>")
        reservar(resto[0], " ".join(resto[1:]))
    elif orden == "curar":
        curar(resto[0], " ".join(resto[1:]) or None)
    elif orden == "descartar":
        if len(resto) < 2:
            sys.exit("Hace falta el motivo: python alerta.py descartar <id> <motivo>")
        descartar(resto[0], " ".join(resto[1:]))
    elif orden == "publicar":
        publicar(resto[0])
    elif orden == "vencer":
        vencer(resto[0], resto[1])
    elif orden == "marcador":
        marcador()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
