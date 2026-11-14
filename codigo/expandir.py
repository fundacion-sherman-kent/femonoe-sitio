# -*- coding: utf-8 -*-
"""Expansión del padrón de fuentes · propone, verifica e incorpora sola.

La dirección pidió el 23/9/2026 sumar todo lo que publique lo necesario: diarios,
blogs, canales oficiales, analistas, YouTube y redes. Esto lo hace en cadena, sin
gastar tokens:

1. **Propone.** Un modelo gratuito de Groq nombra medios, organismos, centros de
   estudio y canales de cada Estado, con su dominio.
2. **Descubre.** Para cada dominio busca el feed que el sitio declara en su
   portada, y si no declara ninguno prueba las direcciones habituales.
3. **Verifica.** Descarga el feed, comprueba que traiga notas con fecha reciente
   y descarta lo que no responde. **Lo que no se puede comprobar, no entra.**
4. **Incorpora** —sólo con `--incorporar`— lo verificado, marcado
   `calidad: "sin calificar"`.

**Qué significa «sin calificar».** La fuente entra y se lee, pero **no cuenta
como familia independiente** para corroborar una alerta hasta que una persona la
califique. Así el padrón crece rápido sin que la credibilidad se afloje: es la
regla 10 de la casa —dos fuentes o desciende la calificación— aplicada al
crecimiento.

**Límite de recolección.** Sólo material público y abierto, sin forzar accesos ni
usar cuentas de la Fundación: `doctrina/limites.md`.

  python expandir.py ATG GRD KNA        propone para esos Estados
  python expandir.py --todos            los 33, por tandas
  python expandir.py ATG --incorporar   además suma al padrón lo verificado
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
from mejoras import _llama  # noqa: E402  — el modelo gratuito, ya resuelto ahí
from verificar import UA, verificar  # noqa: E402

PADRON = RAIZ / "redes.json"
PROPUESTAS = RAIZ / "propuestas"
_PADRON = json.loads((RAIZ / "padron.json").read_text(encoding="utf-8"))["estados"]
ESTADOS = {p["iso3"]: p["nombre"] for p in _PADRON}
INGLES = {p["iso3"]: p.get("nombre_en", p["nombre"]) for p in _PADRON}
CCTLD = {p["iso3"]: "." + p["iso2"].lower() for p in _PADRON}
# Nombres que se confunden con ciudades o países ajenos. Verificado el 23/9/2026:
# el modelo propuso Granada Hoy y la Universidad de Granada —España— para Granada
# del Caribe, y los tres feeds funcionaban.
AMBIGUOS = {
    "GRD": "Grenada, el Estado insular del Caribe oriental, NO la ciudad española de Granada",
    "DMA": "Dominica, el Estado insular, NO la República Dominicana",
    "DOM": "la República Dominicana, NO la isla de Dominica",
    "LCA": "Saint Lucia, el Estado insular del Caribe, NO una ciudad homónima",
    "KNA": "Saint Kitts and Nevis, el Estado insular del Caribe",
    "VCT": "Saint Vincent and the Grenadines, el Estado insular del Caribe",
    "ATG": "Antigua and Barbuda, el Estado insular del Caribe, NO Antigua Guatemala",
}
CAMINOS = ("/feed/", "/rss", "/rss.xml", "/feed", "/feeds/posts/default?alt=rss",
           "/index.xml", "/atom.xml", "/?feed=rss2")
TIPOS = ("prensa", "oficial", "analisis", "sociedad civil")


def _dominio(url):
    m = re.match(r"https?://([^/]+)", url or "")
    return (m.group(1) if m else (url or "")).lower().replace("www.", "")


def _padron():
    return json.loads(PADRON.read_text(encoding="utf-8"))


def _ya_estan():
    d = _padron()
    vistos = {_dominio(e.get("url_rss", "")) for e in d.get("rss", [])}
    vistos |= {e.get("canal_id") for e in d.get("youtube", [])}
    return vistos


INSTITUCIONES = (
    "la autoridad electoral nacional (tribunal, consejo, junta o instituto electoral)",
    "el boletín o diario oficial del Estado",
    "la presidencia o jefatura de gobierno",
    "el ministerio del interior o de gobierno",
    "la policía nacional",
    "la defensoría del pueblo o procuraduría de derechos humanos",
    "el poder judicial o corte suprema",
    "el parlamento o asamblea nacional",
    "el organismo de protección civil o gestión de desastres",
)


def proponer(iso3, cuantas=10, foco=""):
    """El modelo nombra; nada de lo que diga entra sin verificarse."""
    pais = ESTADOS.get(iso3, iso3)
    ingles = INGLES.get(iso3, pais)
    aclaracion = AMBIGUOS.get(iso3, "")
    sistema = ("Sos documentalista de una fundación de análisis. Devolvés SOLO un arreglo "
               "JSON, sin texto alrededor, con objetos {\"nombre\", \"dominio\", \"tipo\"}. "
               "El dominio va sin https:// ni barra final. El tipo es uno de: prensa, "
               "oficial, analisis, sociedad civil. No inventes dominios: si no estás "
               "seguro de uno, no lo incluyas.")
    if foco == "instituciones":
        listado = "; ".join(INSTITUCIONES)
        pregunta = (f"País: {pais} ({ingles}), código {iso3}"
                    + (f". ATENCIÓN: se trata de {aclaracion}. " if aclaracion else ". ")
                    + f"Necesito el sitio web oficial de cada uno de estos organismos de ese "
                    f"país: {listado}. Devolvé el dominio oficial de cada uno, con tipo "
                    f"\"oficial\". Si no sabés el dominio de alguno con certeza, omitilo.")
        r = _llama(pregunta, sistema)
        return _leer_propuestas(r, iso3)
    pregunta = (f"País: {pais} ({ingles}), código {iso3}"
                + (f". ATENCIÓN: se trata de {aclaracion}. " if aclaracion else ". ")
                + f"Fuentes de ese país que publiquen seguido sobre gobernabilidad, seguridad o "
                f"entorno informativo: diarios nacionales y regionales, radios y canales con "
                f"sitio web, boletines y organismos oficiales —presidencia, interior, policía, "
                f"autoridad electoral, defensoría—, centros de estudio, universidades y "
                f"organizaciones de la sociedad civil que publiquen informes, y blogs de "
                f"analistas. Hasta {cuantas}.")
    return _leer_propuestas(_llama(pregunta, sistema), iso3)


def _leer_propuestas(r, iso3):
    if not r or r["modelo"] in ("sin clave", "sin modelo", "error"):
        print(f"  {iso3}: el modelo no respondió ({r['modelo'] if r else 'sin clave'})")
        return []
    m = re.search(r"\[.*\]", r["texto"], re.S)
    if not m:
        return []
    try:
        crudas = json.loads(m.group(0))
    except ValueError:
        return []
    salida = []
    for c in crudas:
        dominio = _dominio(str(c.get("dominio", "")))
        if not dominio or "." not in dominio:
            continue
        salida.append({"nombre": str(c.get("nombre", ""))[:80], "dominio": dominio,
                       "tipo": c.get("tipo") if c.get("tipo") in TIPOS else "prensa",
                       "iso3": iso3, "propuesta_por": r["modelo"]})
    return salida


def _pedir(url, limite=400_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=35) as r:
        return r.read(limite).decode("utf-8", "replace")


def _pertenece(candidata, html):
    """Que un feed funcione no prueba que sea del país. Se exige una de dos: el
    dominio nacional, o que el sitio se nombre a sí mismo en ese país. Sin una de
    las dos, la candidata no entra: es preferible un padrón chico a uno con
    fuentes atribuidas a un país que no les corresponde."""
    iso = candidata["iso3"]
    if candidata["dominio"].endswith(CCTLD.get(iso, "@")):
        return "dominio nacional"
    texto = re.sub(r"<[^>]+>", " ", html[:400_000]).lower()
    for nombre in {ESTADOS.get(iso, ""), INGLES.get(iso, "")}:
        if nombre and nombre.lower() in texto:
            return f"el sitio se nombra en {nombre}"
    return ""


def buscar_feed(candidata):
    try:
        return _buscar_feed(candidata)
    except Exception as e:                      # noqa: BLE001 — un sitio roto no
        return {**candidata, "estado": f"error al revisar ({type(e).__name__}: {e})"}


def _buscar_feed(candidata):
    """Primero se le pregunta al sitio —los feeds se declaran en la portada—; sólo
    después se prueban las direcciones habituales."""
    base = f"https://{candidata['dominio']}"
    try:
        html = _pedir(base, 900_000)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        return {**candidata, "estado": f"el sitio no responde ({type(e).__name__})"}
    atribucion = _pertenece(candidata, html)
    if not atribucion:
        return {**candidata, "estado": f"no se pudo atribuir a {ESTADOS.get(candidata['iso3'])}"}
    declarados = []
    for etiqueta in re.findall(r"<link[^>]+>", html, re.I):
        baja = etiqueta.lower()
        if "alternate" in baja and ("rss" in baja or "atom" in baja):
            m = re.search(r"href=[\"']([^\"']+)[\"']", etiqueta, re.I)
            if m:
                declarados.append(urllib.parse.urljoin(base + "/", m.group(1)))
    for url in declarados + [base + c for c in CAMINOS]:
        r = verificar({**candidata, "url_rss": url})
        if r["estado"] == "viva":
            return {**candidata, "url_rss": url, "estado": "viva", "atribucion": atribucion,
                    "ultima": r.get("ultima"), "declarado": url in declarados}
    return {**candidata, "estado": "sin feed verificable"}


def main():
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    incorporar = "--incorporar" in sys.argv
    isos = list(ESTADOS) if "--todos" in sys.argv else argumentos
    if not isos:
        sys.exit(__doc__)
    ya = _ya_estan()
    todas, nuevas = [], []
    for iso in isos:
        foco = "instituciones" if "--instituciones" in sys.argv else ""
        candidatas = [c for c in proponer(iso, foco=foco) if c["dominio"] not in ya]
        if not candidatas:
            print(f"  {iso}: sin candidatas nuevas")
            continue
        with ThreadPoolExecutor(max_workers=6) as pool:
            resultados = list(pool.map(buscar_feed, candidatas))
        vivas = [r for r in resultados if r["estado"] == "viva"]
        todas += resultados
        nuevas += vivas
        print(f"  {iso} · {len(candidatas)} propuestas · {len(vivas)} con feed verificado")
        PROPUESTAS.mkdir(exist_ok=True)
        (PROPUESTAS / f"{date.today()}.json").write_text(
            json.dumps(todas, ensure_ascii=False, indent=1), encoding="utf-8")
        for v in vivas:
            print(f"      {v['nombre'][:34]:36s} {v['url_rss'][:46]:48s} "
                  f"{v.get('atribucion', '')}")

    PROPUESTAS.mkdir(exist_ok=True)
    (PROPUESTAS / f"{date.today()}.json").write_text(
        json.dumps(todas, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(nuevas)} fuentes nuevas verificadas de {len(todas)} propuestas.")

    if incorporar and nuevas:
        d = _padron()
        for v in nuevas:
            d["rss"].append({"nombre": v["nombre"], "iso3": v["iso3"], "tipo": v["tipo"],
                             "url_rss": v["url_rss"], "activo": True,
                             "calidad": "sin calificar",
                             "nota": f"Propuesta por {v['propuesta_por']}, atribuida por "
                                     f"{v.get('atribucion')} y verificada el "
                                     f"{date.today()}. Corrobora, pero no cuenta como familia "
                                     f"independiente hasta que se la califique."})
        PADRON.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Padrón: {len(nuevas)} fuentes incorporadas como «sin calificar».")


if __name__ == "__main__":
    main()
