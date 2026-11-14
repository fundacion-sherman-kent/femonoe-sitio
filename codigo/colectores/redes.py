# -*- coding: utf-8 -*-
"""Redes y mensajería pública · Telegram (versión web), Mastodon, Bluesky y YouTube.

Qué hace, en tres pasos:
 1. Lee las fuentes del padrón (redes.json). Todas públicas y sin cuenta: la casa
    se identifica con su nombre de robot y no se disfraza de navegador.
 2. Reconoce de qué país habla cada mensaje (nombres, gentilicios y capitales en
    castellano, portugués, inglés y francés) y de qué eje (listas de términos). Si
    no nombra ningún país y la fuente es nacional, se le asigna el país de la fuente.
 3. Arma tres series diarias por país —una por eje— y una cuarta de **difusión
    coordinada**: el mismo texto publicado el mismo día por tres cuentas distintas
    o más. Ojo: una misma noticia replicada por varios medios también da eso. Lo
    distingue una persona, no el robot.

En el detector esta familia **confirma, no dispara** (umbrales.json, "abre": false).
Los mensajes se guardan en este depósito privado como fuente, con fecha y enlace, y
nunca se republican (doctrina/limites.md, «Mensajería pública»)."""
import hashlib
import html
import json
import re
import threading
import time
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from comun import (A_LA_VEZ, RAIZ, guardar_serie, padron, pedir, pedir_json,
                   sitio_de, turno)

# Por debajo de esto no hay mensaje que compartir, sólo un enlace.
TEXTO_MINIMO_COORDINACION = 40

MENSAJES = RAIZ / "datos" / "mensajes"
CONF = json.loads((RAIZ / "redes.json").read_text(encoding="utf-8"))


def _plano(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# ── Cómo se nombra cada país (sin acentos; se compara con el texto sin acentos) ──
TERMINOS = {
    "ARG": ["argentina", "argentino", "argentinos", "argentinas", "buenos aires", "argentine",
            "puerto iguazu"],
    "BRA": ["brasil", "brazil", "brasileno", "brasilenos", "brasileiro", "brasileira", "brazilian", "brasilia",
            "foz do iguacu", "foz de iguazu"],
    "CHL": ["chileno", "chilena", "chilenos", "chilean", "santiago de chile", r"chile(?! con)"],
    "PRY": ["paraguay", "paraguayo", "paraguaya", "paraguayos", "asuncion"],  # «ciudad del este»: ver AMBIGUOS
    "URY": ["uruguay", "uruguayo", "uruguaya", "uruguayos", "montevideo"],
    "BOL": ["bolivia", "boliviano", "boliviana", "bolivianos", "la paz bolivia", "sucre"],
    "COL": ["colombia", "colombiano", "colombiana", "colombianos", "bogota"],
    "ECU": ["ecuador", "ecuatoriano", "ecuatoriana", "ecuatorianos", "quito", "guayaquil"],
    "PER": ["peru", "peruano", "peruana", "peruanos", "peruvian", "lima peru"],
    "VEN": ["venezuela", "venezolano", "venezolana", "venezolanos", "venezuelan", "caracas"],
    "GUY": ["guyana", "guyanes", "guyanese", "georgetown"],
    "SUR": ["surinam", "suriname", "surinamese", "paramaribo"],
    "MEX": ["mexico", "mexicano", "mexicana", "mexicanos", "mexican"],
    "BLZ": ["belice", "belize", "beliceno", "belizean"],
    "CRI": ["costa rica", "costarricense", "costa rican"],
    "SLV": ["el salvador", "salvadoreno", "salvadorena", "salvadorenos", "salvadoran"],
    "GTM": ["guatemala", "guatemalteco", "guatemalteca", "guatemaltecos", "guatemalan"],
    "HND": ["honduras", "hondureno", "hondurena", "hondurenos", "honduran", "tegucigalpa"],
    "NIC": ["nicaragua", "nicaraguense", "nicaraguan", "managua"],
    "PAN": ["panama", "panameno", "panamena", "panamenos", "panamanian"],
    "CUB": ["cuba", "cubano", "cubana", "cubanos", "cuban", "la habana", "havana"],
    "DOM": ["republica dominicana", "dominicano", "dominicana", "dominican republic", "santo domingo"],
    "HTI": ["haiti", "haitiano", "haitiana", "haitianos", "haitian", "haitien", "haitienne", "puerto principe", "port-au-prince"],
    "JAM": ["jamaica", "jamaicano", "jamaican", "kingston jamaica"],
    "TTO": ["trinidad y tobago", "trinidad and tobago", "trinitense", "trinidadian", "port of spain"],
    "BHS": ["bahamas", "bahamian", "nassau"],
    "BRB": ["barbados", "barbadian", "bridgetown"],
    "ATG": ["antigua y barbuda", "antigua and barbuda", "antiguan"],
    "DMA": [r"dominica(?!n)", "dominican island", "roseau"],
    "GRD": ["grenada", "grenadian", r"granada \(caribe\)"],
    "KNA": ["san cristobal y nieves", "saint kitts", "st kitts", "st. kitts", "kittitian"],
    "LCA": ["santa lucia", "saint lucia", "st lucia", "st. lucia", "castries"],
    "VCT": ["san vicente y las granadinas", "saint vincent", "st vincent", "st. vincent", "vincentian"],
}
PATRON_PAIS = {iso: re.compile(r"\b(" + "|".join(t) + r")\b") for iso, t in TERMINOS.items()}

# ── Topónimos que no son de un solo país ──────────────────────────────────────
# «Ciudad del Este» es la ciudad paraguaya de la Triple Frontera **y** un centro
# comercial de Curridabat, Costa Rica, que se incendió en septiembre de 2026 y
# dejó doce notas en el corpus. Asignarla a Paraguay sin mirar habría metido un
# incendio costarricense en la serie paraguaya.
#
# Dos filtros, y el segundo es el que importa. El primero mira el texto: si
# nombra Curridabat o el centro comercial, no es Paraguay. Pero las notas de
# seguimiento —«Pizzería en Ciudad del Este hace gentil gesto para Bomberos»—
# no nombran nada de eso, y medido contra el corpus cinco se escapaban igual.
# El segundo mira **quién publica**: un diario costarricense que dice «Ciudad
# del Este» sin ninguna seña paraguaya está hablando del shopping de su barrio.
#
# El principio es el de la casa aplicado a los topónimos: **un nombre ambiguo
# no asigna país por sí solo.** Necesita que algo lo corrobore, y si lo único
# que hay lo contradice, no cuenta.
AMBIGUOS = {
    "ciudad del este": {
        "pais": "PRY",
        "descarta_si": re.compile(
            r"\b(curridabat|costa rica|costarricense|san jose|centro comercial|"
            r"nova cinemas|grupo zeta|mall|shopping)\b"),
        "compite_con": ("CRI",),
    },
}


def _ambiguos(texto, paises, iso3_fuente=""):
    """Suma los topónimos ambiguos que ni el texto ni la fuente desmienten."""
    for termino, regla in AMBIGUOS.items():
        if termino not in texto:
            continue
        if regla["descarta_si"].search(texto):
            continue
        if iso3_fuente in regla.get("compite_con", ()):
            continue          # la fuente es del otro lugar: no alcanza el nombre
        if regla["pais"] not in paises:
            paises.append(regla["pais"])
    return paises


# ── De qué eje habla (raíces en castellano, portugués, inglés y francés) ──
EJES = {
    "gobernabilidad": r"\b(protest|manifestac|marcha|paro nacional|huelga|greve|strike|cacerol|toque de queda|curfew|couvre-feu"
                      r"|estado de (excepcion|sitio|emergencia)|state of emergency|juicio politico|impeachment|destitu|renuncia"
                      r"|golpe de estado|coup|eleccion|elecao|election|fraude|congreso|parlamento|asamblea|gabinete|crisis politica)",
    "seguridad": r"\b(asesin|homicid|masacre|massacre|balacera|tiroteo|shooting|ataque armado|emboscada|secuestr|kidnap|narco"
                 r"|carte|pandill|gang|crimen organizado|violencia|violence|muertos|mortos|dead|killed|motin|riot|carcel|prision"
                 r"|militar|ejercito|policia|police|frontera|border|explosi|bomba)",
    "informativo": r"\b(desinformac|desinforma|disinformation|misinformation|fake news|noticia falsa|bulo|censura|censorship"
                   r"|bloqueo de (internet|redes)|apagon digital|internet shutdown|corte de internet|periodista|journalist"
                   r"|jornalista|libertad de prensa|press freedom|bot|trolls?|campana de influencia|influence operation|hackeo|ciberataque|cyberattack)",
}
PATRON_EJE = {e: re.compile(p) for e, p in EJES.items()}



def _lineas(archivo) -> list:
    """Renglones de un archivo diario de mensajes. Se corta sólo en el salto de
    línea real: splitlines() también corta en separadores Unicode (U+2028) que
    algunos mensajes traen dentro del texto, y rompía la lectura."""
    return [l for l in archivo.read_text(encoding="utf-8").split(chr(10)) if l.strip()]


def _sin_etiquetas(t: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


# ── Lectores ──
def telegram(canal: str) -> list:
    pagina = pedir(f"https://t.me/s/{canal}", segundos=40, intentos=2, espera=5).decode("utf-8", "replace")
    salida = []
    for bloque in pagina.split('class="tgme_widget_message_wrap')[1:]:
        texto = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', bloque, re.S)
        fecha = re.search(r'datetime="([^"]+)"', bloque)
        enlace = re.search(r'class="tgme_widget_message_date" href="([^"]+)"', bloque)
        if texto and fecha:
            salida.append({"fecha": fecha.group(1), "texto": _sin_etiquetas(texto.group(1)),
                           "enlace": enlace.group(1) if enlace else f"https://t.me/{canal}", "cuenta": canal})
    return salida


def mastodon(instancia: str) -> list:
    datos = pedir_json(f"https://{instancia}/api/v1/timelines/public?local=true&limit=40", segundos=40, intentos=2, espera=5)
    return [{"fecha": d.get("created_at"), "texto": _sin_etiquetas(d.get("content")), "enlace": d.get("url"),
             "cuenta": (d.get("account") or {}).get("acct", "") + "@" + instancia} for d in datos or []]


def bluesky(cuenta: str) -> list:
    """Publicaciones de una cuenta. La búsqueda abierta de Bluesky responde 403 sin
    cuenta (comprobado el 21/9/2026); leer el perfil de una cuenta sigue abierto."""
    url = ("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?limit=50&filter=posts_no_replies&actor="
           + urllib.parse.quote(cuenta))
    datos = pedir_json(url, segundos=40, intentos=2, espera=10)
    salida = []
    for item in datos.get("feed") or []:
        p = item.get("post") or {}
        autor = (p.get("author") or {}).get("handle", "")
        clave = (p.get("uri") or "").rsplit("/", 1)[-1]
        salida.append({"fecha": (p.get("record") or {}).get("createdAt"), "texto": (p.get("record") or {}).get("text", ""),
                       "enlace": f"https://bsky.app/profile/{autor}/post/{clave}", "cuenta": autor})
    return salida


def youtube(canal_id: str) -> list:
    raiz = ElementTree.fromstring(pedir(f"https://www.youtube.com/feeds/videos.xml?channel_id={canal_id}", segundos=40, intentos=2, espera=5))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    return [{"fecha": e.findtext("a:published", "", ns), "texto": e.findtext("a:title", "", ns),
             "enlace": (e.find("a:link", ns).get("href") if e.find("a:link", ns) is not None else ""),
             "cuenta": canal_id} for e in raiz.findall("a:entry", ns)]


def rss(url: str) -> list:
    """Canal RSS o Atom de un medio o de un organismo. Lee la fecha de donde venga:
    pubDate, updated, published, dc:date o valueDate (Diario Oficial de México)."""
    from email.utils import parsedate_to_datetime
    raiz = ElementTree.fromstring(pedir(url, segundos=40, intentos=2, espera=5))
    salida = []
    for e in raiz.iter():
        etiqueta = e.tag.rsplit("}", 1)[-1]
        if etiqueta not in ("item", "entry"):
            continue
        campos = {c.tag.rsplit("}", 1)[-1]: c for c in e}
        titulo = (campos.get("title").text if campos.get("title") is not None else "") or ""
        resumen = ""
        for k in ("description", "summary"):
            if campos.get(k) is not None and campos[k].text:
                resumen = _sin_etiquetas(campos[k].text)[:300]
                break
        enlace = campos.get("link")
        enlace = (enlace.get("href") or enlace.text or "") if enlace is not None else ""
        fecha = ""
        for k in ("pubDate", "updated", "published", "date", "valueDate"):
            if campos.get(k) is not None and campos[k].text:
                fecha = _fecha_iso(campos[k].text.strip())
                if fecha:
                    break
        salida.append({"fecha": fecha, "texto": f"{titulo}. {resumen}".strip(), "enlace": enlace.strip(), "cuenta": url})
    return salida


def _fecha_iso(crudo: str) -> str:
    """Toda fecha se guarda en el mismo formato, y la que no se entiende no se
    guarda.

    Por qué existe esto. Hasta el 24/9/2026 la fecha del feed se guardaba como
    venía cuando no era del formato de correo: un diario que publica
    «23/09/2026» quedaba en la serie con esa clave, que el detector nunca lee
    —espera año, mes y día—. Resultado: **parte de los mensajes de un día se
    contaban en una fecha inexistente y el valor del día quedaba corto**. Eran
    198 filas por serie."""
    for intento in (
        lambda s: parsedate_to_datetime(s).date().isoformat(),
        lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat(),
        lambda s: datetime.strptime(s[:10], "%d/%m/%Y").date().isoformat(),
        lambda s: datetime.strptime(s[:10], "%m/%d/%Y").date().isoformat(),
        lambda s: datetime.strptime(s[:10], "%Y/%m/%d").date().isoformat(),
    ):
        try:
            return intento(crudo)
        except (TypeError, ValueError, IndexError):
            continue
    return ""


def _fecha_razonable(iso):
    """Una fecha fuera de rango no es una fecha: es un error de la fuente.

    El 2/10/2026 un diario hondureño publicó una nota fechada **2050-10-01** y
    esa fecha entró a cuatro series, con 33 filas cada una. No rompió nada
    visible —por eso estuvo días sin que nadie lo notara— pero una serie con
    una fila en 2050 tiene un máximo falso y una línea de base falsa.

    Se acepta desde 2015 hasta mañana. Mañana y no hoy, porque un feed puede
    venir con la hora adelantada; el año que viene, no."""
    if not iso:
        return ""
    manana = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    return iso if "2015-01-01" <= iso <= manana else ""

def _clasificar(m: dict) -> None:
    t = _plano(m["texto"])
    paises = [iso for iso, pat in PATRON_PAIS.items() if pat.search(t)]
    paises = _ambiguos(t, paises, m.get("iso3_fuente") or "")
    if not paises and m.get("iso3_fuente") and m["iso3_fuente"] not in ("REG", "GLO"):
        paises = [m["iso3_fuente"]]
    m["paises"] = paises
    m["ejes"] = [e for e, pat in PATRON_EJE.items() if pat.search(t)]


def main():
    ahora = datetime.now(timezone.utc)
    crudos, caidas = [], []

    cerrojo_datos = threading.Lock()

    def juntar(fuente, iso3, sitio, lector, *args):
        """Lee UNA fuente. Corre en su propio hilo, uno por fuente.

        El regulador de ritmo decide cuándo le toca, para no golpear al sitio.
        Una fuente que falla **no tumba la corrida y queda anotada**: la lista
        de caídas es la que después baja la calificación de esa fuente.
        """
        try:
            with turno(sitio):
                leidos = lector(*args)
        except Exception as e:  # noqa: BLE001 — una fuente que falla no tumba la corrida
            with cerrojo_datos:
                caidas.append(f"{fuente} {args[0]}: {type(e).__name__}")
            return
        with cerrojo_datos:
            for m in leidos:
                m.update({"fuente": fuente, "iso3_fuente": iso3})
                crudos.append(m)

    # La lista de lo que hay que pedir, **con el sitio de cada fuente
    # declarado**: lo que el regulador cuida es el sitio, no la fuente. Los 100
    # canales de YouTube son 100 fuentes y UN solo sitio; los 228 canales RSS
    # son 228 fuentes y casi 228 sitios distintos.
    tareas = []
    for c in CONF.get("telegram", []):
        if c.get("activo", True):
            tareas.append(("telegram", c.get("iso3", "REG"), "t.me",
                           telegram, c["canal"]))
    for m in CONF.get("mastodon", []):
        if m.get("activo", True):
            tareas.append(("mastodon", m.get("iso3", "REG"), sitio_de(m["instancia"]),
                           mastodon, m["instancia"]))
    for r in CONF.get("rss", []):
        if r.get("activo", True):
            tareas.append(("rss", r["iso3"], sitio_de(r["url_rss"]),
                           rss, r["url_rss"]))
    for y in CONF.get("youtube", []):
        if y.get("activo", True):
            tareas.append(("youtube", y["iso3"], "www.youtube.com",
                           youtube, y["canal_id"]))
    for b in CONF.get("bluesky", []):
        if b.get("activo", True):
            tareas.append(("bluesky", b.get("iso3", "REG"), "public.api.bsky.app",
                           bluesky, b["cuenta"]))

    with ThreadPoolExecutor(max_workers=A_LA_VEZ) as grupo:
        list(grupo.map(lambda tarea: juntar(*tarea), tareas))

    # **Se ordena a propósito.** Leyendo a la vez, los mensajes llegan en el
    # orden en que contestó cada sitio, que cambia en cada corrida. Ordenarlos
    # acá devuelve lo que una casa de inteligencia necesita: **la misma entrada
    # da la misma salida**, y una diferencia entre dos corridas significa que
    # algo cambió afuera, no que los hilos terminaron en otro orden.
    crudos.sort(key=lambda m: ((m.get("enlace") or ""), (m.get("fuente") or "")))

    # deduplicar contra lo ya guardado en los últimos días
    MENSAJES.mkdir(parents=True, exist_ok=True)
    vistos = set()
    for k in range(0, 8):
        f = MENSAJES / f"{(ahora - timedelta(days=k)).date()}.jsonl"
        if f.exists():
            vistos |= {json.loads(l)["enlace"] for l in _lineas(f)}
    nuevos = []
    for m in crudos:
        if not m.get("enlace") or m["enlace"] in vistos or not m.get("fecha"):
            continue
        vistos.add(m["enlace"])
        m["texto"] = (m["texto"] or "")[:600]
        _clasificar(m)
        nuevos.append(m)
    with (MENSAJES / f"{ahora.date()}.jsonl").open("a", encoding="utf-8") as f:
        for m in nuevos:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    # series por país y eje, contando por el día en que se publicó el mensaje
    todos = []
    for k in range(0, 8):
        f = MENSAJES / f"{(ahora - timedelta(days=k)).date()}.jsonl"
        if f.exists():
            todos += [json.loads(l) for l in _lineas(f)]
    cuenta = {}
    grupos = {}
    for m in todos:
        dia = _fecha_razonable(_fecha_iso(str(m.get("fecha") or "")))
        if not dia:
            continue
        for iso in m.get("paises", []):
            for eje in m.get("ejes", []):
                cuenta[(eje, dia, iso)] = cuenta.get((eje, dia, iso), 0) + 1
        # La huella se calcula sobre el texto SIN las direcciones. Un mensaje
        # que es sólo un enlace queda en nada, y todos los que son sólo un
        # enlace quedan en la misma nada: medido el 27/9/2026, **39 de las 43
        # marcas de coordinación eran eso** —una de ellas, diez cuentas de
        # once países que ese día habían publicado un link y nada más—.
        # Compartir un enlace no es compartir un mensaje.
        desnudo = re.sub(r"https?://\S+|[^a-z0-9 ]", "", _plano(m["texto"]))[:140]
        if len(desnudo.strip()) < TEXTO_MINIMO_COORDINACION:
            continue
        huella = hashlib.sha1(desnudo.encode()).hexdigest()
        g = grupos.setdefault((huella, dia), {"cuentas": set(), "paises": set()})
        g["cuentas"].add(m.get("cuenta"))
        g["paises"] |= set(m.get("paises", []))
    dias = sorted({k[1] for k in cuenta} | {k[1] for k in grupos})
    for eje in EJES:
        filas = [(d, p["iso3"], cuenta.get((eje, d, p["iso3"]), 0)) for d in dias for p in padron()]
        guardar_serie(f"redes_{eje}", filas)
    # Difusión coordinada: tres FUENTES INDEPENDIENTES, no tres cuentas.
    # `doctrina/fuentes.md` §2: tres medios que citan el mismo cable son una
    # fuente. Las que repiten texto de forma rutinaria vienen agrupadas en
    # sindicacion.json; sin ese archivo se cuenta como antes.
    familia = {}
    f_sind = RAIZ / "sindicacion.json"
    if f_sind.exists():
        for i, g in enumerate(json.loads(f_sind.read_text(encoding="utf-8"))["grupos"]):
            for c in g:
                familia[c] = f"g{i}"
    coord = {}
    for (huella, dia), g in grupos.items():
        independientes = {familia.get(c, c) for c in g["cuentas"]}
        if len(independientes) >= 3:
            for iso in g["paises"]:
                coord[(dia, iso)] = coord.get((dia, iso), 0) + 1
    guardar_serie("redes_coordinado", [(d, p["iso3"], coord.get((d, p["iso3"]), 0)) for d in dias for p in padron()])

    con_pais = sum(1 for m in nuevos if m["paises"])
    print(f"Redes: {len(nuevos)} mensajes nuevos, {con_pais} con país reconocido; "
          f"{sum(coord.values())} grupos de difusión coordinada; fuentes caídas: {len(caidas)}")
    for c in caidas[:15]:
        print("   ", c)


if __name__ == "__main__":
    main()
