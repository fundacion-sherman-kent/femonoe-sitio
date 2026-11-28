# -*- coding: utf-8 -*-
"""FEMÓNOE · calificación de fuentes. Las tres capas que no gastan tokens.

**El problema.** El padrón tiene 42 fuentes marcadas «sin calificar»: las
propuso un modelo gratuito el 23/9, el robot les verificó el feed y entraron
así, a propósito —corroboran, pero **no cuentan como familia independiente**
hasta que alguien las califique—. Mientras sigan sin letra, están trabajando a
media máquina.

**Qué hace este archivo y qué no.** Califica con el sistema Almirantazgo de
`doctrina/fuentes.md`: letra de fiabilidad de la fuente, A a F. El número de
credibilidad **no** se toca acá, porque es del dato y no de la fuente.

Tres capas, ninguna de ellas gasta tokens de conversación:

1. `--independencia`  Quién repite a quién. Es la más importante y la que
   nadie mira: `doctrina/fuentes.md` §2 avisa que **tres medios que citan el
   mismo cable son UNA fuente, no tres**. Una repetidora sin detectar infla la
   corroboración y sube en cadena hasta el juicio. Se resuelve comparando los
   mensajes ya recolectados: cómputo puro, nada que consultar afuera.

2. `--legajo`  El expediente de cada fuente: dominio, quién responde por ella,
   desde cuándo publica, con qué cadencia, y si enlaza a su propio dominio o
   al de otros. Se baja del sitio, se mide, se guarda. Es **el insumo del
   juicio, no el juicio**.

3. `--tabla`  Las que la tabla de fiabilidad ya resuelve sin que nadie opine:
   una fuente en dominio de Estado es registro oficial, y la tabla dice `A`.
   No hay nada que sopesar, así que no se simula una deliberación.

**Lo que este archivo deliberadamente no hace:** poner la letra a las fuentes
que exigen distinguir `B` de `C` —medio de referencia con estándares
editoriales contra fuente con sesgo conocido pero verificable—. Eso es juicio,
y el juicio no se automatiza. Salen listadas al final de `--legajo`, con su
expediente armado, para que las mire una persona.

  python calificar.py --independencia
  python calificar.py --legajo [--aplicar]
  python calificar.py --tabla [--aplicar]

Sin `--aplicar` no escribe nada en el padrón: muestra qué haría.
"""
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PADRON = RAIZ / "redes.json"
MENSAJES = RAIZ / "datos" / "mensajes"
LEGAJOS = RAIZ / "legajos"
ESPERA = 8          # segundos entre pedidos al modelo gratuito
UA = ("Mozilla/5.0 (compatible; FEMONOE/0.1; Fundacion Sherman Kent; "
      "+https://fundacionkent.org)")

# Dominio de Estado: la tabla de `doctrina/fuentes.md` lo resuelve sola.
ESTADO = re.compile(r"\.(gob|gov|gub|gouv|presidencia|mil)\.[a-z]{2,3}$|\.(gob|gov)$")
# Señas de que alguien firma por lo que se publica.
RESPONSABLE = ("quienes-somos", "quiénes somos", "quem somos", "about-us", "nosotros",
               "staff", "director", "redaccion", "redacción", "editor responsable",
               "aviso legal", "mesa de redaccion", "expediente", "impressum")


def _padron():
    return json.loads(PADRON.read_text(encoding="utf-8"))


def sin_calificar(d=None):
    """Las entradas marcadas «sin calificar», con su plataforma."""
    d = d or _padron()
    return [(k, x) for k, v in d.items() if isinstance(v, list)
            for x in v if x.get("calidad") == "sin calificar"]


def nombre(x):
    return x.get("nombre") or x.get("canal") or x.get("canal_id") or x.get("url_rss") or "?"


def clave(plataforma, x):
    """Con qué nombre aparece esta fuente en los mensajes recolectados."""
    if plataforma == "rss":
        return x.get("url_rss")
    if plataforma == "youtube":
        return x.get("canal_id")
    if plataforma == "mastodon":
        return x.get("instancia")
    return x.get("canal")


def identidad(plataforma, x, laxa=False):
    """Cómo se compara una entrada con otra para ver si son la misma fuente.

    `laxa` borra la puntuación: `el-nacional.com` y `elnacional.com` quedan
    iguales. **No alcanza para declarar duplicado** —dos dominios parecidos
    pueden ser dos sitios—, por eso la forma laxa sólo se usa para proponer, y
    la prueba de independencia es la que confirma."""
    u = (clave(plataforma, x) or "").lower()
    u = re.sub(r"^https?://", "", u).removeprefix("www.").rstrip("/")
    return re.sub(r"[^a-z0-9]", "", u) if laxa else u


def dominio(x):
    m = re.search(r"https?://([^/]+)", x.get("url_rss") or x.get("url") or "")
    return m.group(1).lower().removeprefix("www.") if m else ""


# ---------------------------------------------------------------- capa 2

def _plano(t):
    t = unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+|[^a-z0-9 ]", "", t)).strip()


def _mensajes():
    todos = []
    for f in sorted(MENSAJES.glob("*.jsonl")):
        for linea in f.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                try:
                    todos.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue
    return todos


def independencia(silencio=False):
    """Quién repite a quién, sobre el material ya recolectado.

    La huella es la misma que usa el detector para difusión coordinada: los
    primeros 140 caracteres del texto, normalizados. Dos fuentes que comparten
    huella publicaron lo mismo, y la que publicó después **no corrobora**: es
    reproducción, y así lo manda marcar `doctrina/fuentes.md` §2."""
    msgs = _mensajes()
    if not msgs:
        sys.exit("No hay mensajes recolectados. La prueba necesita material.")
    # Todo el padrón, no sólo las sin calificar: tener letra `A` no vuelve
    # independiente a nadie. Dos organismos del mismo Estado que se
    # reproducen entre sí son **una** familia, y hoy cuentan como dos.
    d = _padron()
    interesan = {clave(k, x): (k, x) for k, v in d.items() if isinstance(v, list)
                 for x in v if clave(k, x)}
    huellas = defaultdict(list)
    for m in msgs:
        t = _plano(m.get("texto", ""))
        if len(t) < 60:          # un título corto se repite por azar
            continue
        h = hashlib.sha1(t[:140].encode()).hexdigest()
        huellas[h].append((m.get("fecha", ""), m.get("cuenta"), m.get("fuente")))

    calco = defaultdict(Counter)
    primeros = defaultdict(Counter)
    for grupo in huellas.values():
        cuentas = {c for _, c, _ in grupo}
        if len(cuentas) < 2:
            continue
        orden = sorted(grupo, key=lambda g: g[0] or "")
        primera = orden[0][1]
        for _, c, _ in orden[1:]:
            if c == primera:
                continue
            if c in interesan:
                calco[c][primera] += 1
            primeros[primera][c] += 1

    dias = sorted({f.stem for f in MENSAJES.glob("*.jsonl")})
    if silencio:
        return calco
    print("FEMÓNOE · prueba de independencia sobre las fuentes sin calificar")
    print(f"Material: {len(msgs)} mensajes, {len(dias)} días ({dias[0]} a {dias[-1]}).")
    print("La huella son los primeros 140 caracteres normalizados, la misma que")
    print("usa el detector. Coincidir no prueba copia: prueba texto idéntico.\n")
    if not calco:
        print("Ninguna de las 42 reprodujo texto de otra fuente del padrón en esta")
        print("ventana. **No se omite: se dice.** Con cinco días de material, esto")
        print("no las declara independientes; dice que todavía no se las vio copiar.")
    for c, quienes in sorted(calco.items(), key=lambda kv: -sum(kv[1].values())):
        k, x = interesan[c]
        total = sum(quienes.values())
        marca = "  ·sin calificar" if x.get("calidad") == "sin calificar" else ""
        print(f"· {nombre(x)} ({x.get('iso3')}, {k}){marca} — {total} textos repetidos")
        for otra, n in quienes.most_common(4):
            print(f"    {n:3d} después de {otra}")
        print("    → si se confirma, entra al padrón como DERIVADA y no corrobora\n")
    ventana = len(dias)
    print(f"\nAdvertencia de método: la ventana es de {ventana} días. Una repetidora "
          "que\ncopia poco necesita más material para aparecer. Se vuelve a correr.")
    return calco


def duplicados(aplicar=False, confirmadas=None):
    """La misma fuente cargada dos veces. Es peor que una derivada: una fuente
    que se corrobora a sí misma es corroboración falsa, y sube hasta el juicio.

    Se borra sola cuando **el identificador es idéntico** —misma dirección de
    feed, mismo canal—, porque ahí no hay nada que decidir. La variante de
    puntuación se propone y **sólo se borra si la prueba de independencia la
    confirmó** con textos repetidos."""
    d = _padron()
    confirmadas = confirmadas or {}
    exactos, laxos = defaultdict(list), defaultdict(list)
    for k, v in d.items():
        if not isinstance(v, list):
            continue
        for x in v:
            if not clave(k, x):
                continue
            exactos[(k, identidad(k, x))].append(x)
            laxos[(k, identidad(k, x, laxa=True))].append(x)

    def preferida(xs):
        """Se conserva la ya calificada; si ninguna lo está, la primera."""
        return next((x for x in xs if x.get("calidad") not in (None, "sin calificar")),
                    next((x for x in xs if "calidad" not in x), xs[0]))

    borrar, motivo = [], {}
    for (k, _), xs in exactos.items():
        if len(xs) > 1:
            queda = preferida(xs)
            for x in xs:
                if x is not queda:
                    borrar.append((k, x)); motivo[id(x)] = "identificador idéntico"
    for (k, _), xs in laxos.items():
        if len(xs) < 2 or any(x in [b for _, b in borrar] for x in xs):
            continue
        if len({identidad(k, x) for x in xs}) < 2:
            continue                       # ya lo tomó la pasada exacta
        cs = {clave(k, x) for x in xs}
        prueba = [c for c in cs if c in confirmadas]
        queda = preferida(xs)
        for x in xs:
            if x is queda:
                continue
            if prueba:
                borrar.append((k, x))
                motivo[id(x)] = ("variante de puntuación, confirmada por "
                                 f"{sum(confirmadas.get(clave(k, x), {}).values())} "
                                 "textos repetidos")
            else:
                motivo[id(x)] = "variante de puntuación SIN confirmar — no se toca"
                print(f"  ? {k} · {nombre(x)} ({x.get('iso3')}) se parece a "
                      f"{nombre(queda)}, pero ningún texto repetido lo confirma. "
                      "Queda como está.")

    print("FEMÓNOE · la misma fuente cargada dos veces\n")
    for k, x in borrar:
        print(f"  sale  {k:9s} {nombre(x)[:40]:40s} {x.get('iso3')}  "
              f"({motivo[id(x)]})")
    print(f"\n{len(borrar)} entradas duplicadas sobre "
          f"{sum(len(v) for v in d.values() if isinstance(v, list))}.")
    if aplicar and borrar:
        # Por identidad y no por igualdad: dos entradas duplicadas son dos dicts
        # IGUALES, y `x not in fuera` las borraría a las dos. Costó una fuente.
        fuera = {id(x) for _, x in borrar}
        for k, v in d.items():
            if isinstance(v, list):
                d[k] = [x for x in v if id(x) not in fuera]
        d.setdefault("nota_duplicados", []).append({
            "fecha": date.today().isoformat(),
            "quitadas": [{"plataforma": k, "nombre": nombre(x), "iso3": x.get("iso3"),
                          "identificador": clave(k, x), "motivo": motivo[id(x)]}
                         for k, x in borrar]})
        PADRON.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print("Padrón escrito. Lo quitado queda anotado en «nota_duplicados»: "
              "se saca del padrón, no del registro.")
    elif borrar:
        print("Nada escrito todavía. Con --aplicar se quitan.")
    return borrar


# ---------------------------------------------------------------- capa 1

def _bajar(url, limite=600_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(limite).decode("utf-8", "replace")


def _legajo_de(plataforma, x, msgs_por_cuenta):
    """El expediente de una fuente. Mide; no opina."""
    leg = {"nombre": nombre(x), "iso3": x.get("iso3"), "plataforma": plataforma,
           "tipo_declarado": x.get("tipo"), "dominio": dominio(x),
           "dominio_de_estado": bool(ESTADO.search(dominio(x))),
           "medido": date.today().isoformat()}
    propios = msgs_por_cuenta.get(clave(plataforma, x), [])
    leg["mensajes_recolectados"] = len(propios)
    fechas = sorted(m.get("fecha", "")[:10] for m in propios if m.get("fecha"))
    if fechas:
        leg["primer_mensaje"], leg["ultimo_mensaje"] = fechas[0], fechas[-1]
        leg["dias_con_publicacion"] = len(set(fechas))
    # ¿Los enlaces apuntan a su propio dominio, o reenvía a otros? Un agregador
    # no es una fuente: es un índice de fuentes ajenas.
    enlaces = [m.get("enlace", "") for m in propios if m.get("enlace")]
    if enlaces and leg["dominio"]:
        propios_n = sum(1 for e in enlaces if leg["dominio"] in e)
        leg["enlaces_a_dominio_propio"] = f"{propios_n}/{len(enlaces)}"
        leg["parece_agregador"] = propios_n < len(enlaces) * 0.5
    # ¿Alguien firma por lo que publica?
    url = x.get("url_rss") or (f"https://{leg['dominio']}" if leg["dominio"] else "")
    if url:
        raiz = re.match(r"https?://[^/]+", url)
        try:
            html = _bajar(raiz.group(0) if raiz else url).lower()
            leg["responsable_a_la_vista"] = sorted(
                {s for s in RESPONSABLE if s in html})[:4]
            t = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
            leg["titulo_del_sitio"] = re.sub(r"\s+", " ", t.group(1)).strip()[:80] if t else ""
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, UnicodeError) as e:
            leg["sitio"] = f"no se pudo leer: {type(e).__name__}"
    return leg


def legajos(aplicar=False):
    msgs_por_cuenta = defaultdict(list)
    for m in _mensajes():
        msgs_por_cuenta[m.get("cuenta")].append(m)
    salida = []
    pendientes = sin_calificar()
    print(f"FEMÓNOE · legajo de las {len(pendientes)} fuentes sin calificar\n")
    for i, (k, x) in enumerate(pendientes, 1):
        leg = _legajo_de(k, x, msgs_por_cuenta)
        salida.append(leg)
        marca = "A por tabla" if leg["dominio_de_estado"] else "requiere juicio"
        print(f"{i:3d}. {leg['nombre'][:38]:38s} {leg['iso3']} {k:8s} "
              f"{leg['mensajes_recolectados']:4d} msj  {marca}")
    LEGAJOS.mkdir(exist_ok=True)
    f = LEGAJOS / f"sin-calificar-{date.today()}.json"
    f.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    juicio = [l for l in salida if not l["dominio_de_estado"]]
    print(f"\nLegajos escritos en {f.relative_to(RAIZ)}")
    print(f"{len(salida) - len(juicio)} las resuelve la tabla · "
          f"**{len(juicio)} requieren juicio de una persona**")
    sin_sitio = [l for l in juicio if "sitio" in l]
    if sin_sitio:
        print(f"{len(sin_sitio)} no dejaron leer su sitio; el legajo lo dice en vez "
              "de suponerlo.")
    return salida


# ---------------------------------------------------------------- capa 3

def por_tabla(aplicar=False):
    """Fuente en dominio de Estado = registro oficial = `A`. Sin deliberación.

    La letra califica **la fiabilidad de la fuente**, no el interés del emisor:
    que un ministerio sea fiable en cuanto a lo que declara no vuelve cierto el
    número que le conviene. Eso lo resuelve la credibilidad del dato, que es el
    número y se pone en cada uso."""
    d = _padron()
    tocadas = []
    for k, v in d.items():
        if not isinstance(v, list):
            continue
        for x in v:
            if x.get("calidad") == "sin calificar" and ESTADO.search(dominio(x)):
                tocadas.append((k, x))
                if aplicar:
                    x["calidad"] = "A"
                    x["calificada"] = {
                        "fecha": date.today().isoformat(),
                        "por": "tabla de fiabilidad · dominio de Estado",
                        "fundamento": (
                            "Registro oficial en dominio de Estado. "
                            "`doctrina/fuentes.md` §1: A = documento primario. "
                            "La letra es de la fuente; el interés del organismo "
                            "en un dato concreto se resuelve en la credibilidad "
                            "del dato, no acá."),
                        "reversible": "poner calidad en «sin calificar» y borrar este bloque",
                    }
                    x["nota"] = re.sub(
                        r"Corrobora, pero no cuenta como familia independiente.*?\.",
                        "Calificada A el " + date.today().isoformat()
                        + " por dominio de Estado; cuenta como familia independiente.",
                        x.get("nota", ""))
    print("FEMÓNOE · las que la tabla resuelve sin juicio\n")
    for k, x in tocadas:
        print(f"  A   {dominio(x):38s} {x.get('iso3')}  {nombre(x)[:34]}")
    print(f"\n{len(tocadas)} fuentes en dominio de Estado.")
    if aplicar:
        PADRON.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print("Padrón escrito. Cada una lleva su fundamento y cómo se revierte.")
    else:
        print("Nada escrito todavía. Con --aplicar se guarda en el padrón.")
    return tocadas


def main():
    aplicar = "--aplicar" in sys.argv
    if "--independencia" in sys.argv:
        independencia()
    elif "--duplicados" in sys.argv:
        # La prueba de independencia corre primero y en silencio: es la que
        # confirma si dos direcciones parecidas son de veras la misma fuente.
        duplicados(aplicar, confirmadas=independencia(silencio=True))
    elif "--legajo" in sys.argv:
        legajos(aplicar)
    elif "--tabla" in sys.argv:
        por_tabla(aplicar)
    elif "--proponer" in sys.argv:
        proponer()
    else:
        sys.exit(__doc__)



# ---------------------------------------------------------------- capa 4

TABLA = """A = Completamente fiable. Historial extenso sin fallos. Registro oficial,
    filing regulatorio, documento primario.
B = Habitualmente fiable. Medio de referencia con estándares editoriales,
    informe de consultora seria.
C = Bastante fiable. Fuente con historial mixto o sesgo conocido pero verificable.
D = Habitualmente no fiable. Historial de errores o agenda evidente.
E = No fiable. Desinformación documentada.
F = Fiabilidad no evaluable. Fuente nueva o anónima."""

SISTEMA = (
    "Sos oficial de procesamiento de una fundación de análisis de inteligencia. "
    "Calificás la FIABILIDAD DE LA FUENTE con el sistema Almirantazgo/OTAN, una "
    "letra de la A a la F. No calificás la credibilidad del dato, que es otra "
    "escala y no se te pide.\n\n" + TABLA + "\n\n"
    "Reglas que no podés violar:\n"
    "- Si el legajo no alcanza para decidir, respondé letra «?» y decí qué falta. "
    "«No lo sé» es mejor respuesta que una conjetura presentada como hecho.\n"
    "- No inventes historia, premios, antigüedad ni propietarios que el legajo no "
    "diga. Fundamentá SOLO con lo que está en el legajo o con lo que sepas con "
    "certeza sobre ese medio, y distinguí una cosa de la otra.\n"
    "- Un medio con línea editorial marcada no es por eso poco fiable: si el sesgo "
    "es conocido y verificable, es C.\n"
    "- Respondé SOLO un objeto JSON: "
    '{"letra":"A|B|C|D|E|F|?","fundamento":"una oración","seguro":true|false}')


def proponer():
    """El modelo gratuito propone la letra; la decide una persona.

    Se le da el legajo medido y la tabla, y se le exige que conteste «?» cuando
    no le alcance. Lo que vuelve **no se aplica**: se escribe al lado de cada
    fuente para que la Oficina lo revise. La máquina propone, el juicio queda
    donde estaba."""
    sys.path.insert(0, str(RAIZ))
    from mejoras import _llama  # noqa: PLC0415  — el mismo modelo gratuito de la casa

    ultimo = sorted(LEGAJOS.glob("sin-calificar-*.json"))[-1]
    legs = json.loads(ultimo.read_text(encoding="utf-8"))
    print(f"FEMÓNOE · propuesta de letra para {len(legs)} fuentes\n"
          f"Legajos: {ultimo.name}. Propone un modelo gratuito; decide una persona.\n")
    salida = []
    for i, leg in enumerate(legs, 1):
        ficha = json.dumps(leg, ensure_ascii=False, indent=1)
        # El cupo gratuito se agota: el 27/9 la primera corrida contestó doce
        # fuentes y las trece restantes volvieron con «error», que el informe
        # mostraba como si el modelo hubiera dudado. Duda y cupo agotado no son
        # lo mismo, y confundirlos deja trece fuentes sin evaluar creyendo que
        # se evaluaron. Se espera entre pedidos y se reintenta con paciencia.
        for intento in range(4):
            r = _llama("Legajo de la fuente:" + chr(10) + ficha, SISTEMA)
            if r.get("modelo") != "error":
                break
            espera = ESPERA * (2 ** intento)
            print(f"     (sin cupo o error: {r.get('texto', '')[:70]} — "
                  f"espero {espera}s)")
            time.sleep(espera)
        time.sleep(ESPERA)
        try:
            p = json.loads(re.search(r"\{.*\}", r.get("texto", ""), re.S).group(0))
            if not isinstance(p, dict):
                raise ValueError
        except (AttributeError, json.JSONDecodeError, ValueError):
            p = {"fundamento": (f"NO EVALUADA — {r.get('texto', '')[:120]}"
                                if r.get("modelo") == "error"
                                else f"el modelo no devolvió JSON ({r.get('modelo')})")}
        # Lo que vuelve de un modelo se valida antes de usarlo: el 27/9 devolvió
        # un objeto sin la clave «letra» y volteó la corrida entera. Todo lo que
        # no sea una letra de la tabla se trata como «no sé», que es lo que es.
        letra = str(p.get("letra", "?")).strip().upper()[:1]
        p["letra"] = letra if letra in "ABCDEF" else "?"
        p["fundamento"] = str(p.get("fundamento", "")).strip() or "sin fundamento"
        p["seguro"] = bool(p.get("seguro")) and p["letra"] != "?"
        p["fuente"] = leg["nombre"]; p["iso3"] = leg["iso3"]
        p["modelo"] = r.get("modelo"); p["legajo"] = ultimo.name
        salida.append(p)
        marca = " " if p.get("seguro") and p["letra"] != "?" else "REVISAR"
        print(f"{i:3d}. {p['letra']:2s} {marca:7s} {leg['nombre'][:34]:34s} "
              f"{leg['iso3']}  {p.get('fundamento','')[:64]}")
    f = LEGAJOS / f"propuesta-{date.today()}.json"
    f.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    dudosas = [p for p in salida if not p.get("seguro") or p["letra"] == "?"]
    print(f"\nPropuesta escrita en {f.relative_to(RAIZ)}")
    print(f"{len(salida) - len(dudosas)} el modelo las dio por seguras · "
          f"**{len(dudosas)} pidió revisión**")
    print("Nada se aplicó al padrón: esto es una propuesta, no una calificación.")
    return salida


if __name__ == "__main__":
    main()
