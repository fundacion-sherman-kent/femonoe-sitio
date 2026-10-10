# -*- coding: utf-8 -*-
"""Expansión del padrón en canales: YouTube, Telegram público y Mastodon.

Lo que `expandir.py` hace con sitios web, esto lo hace con canales. Misma cadena
y mismo rigor: **el modelo propone, el robot resuelve, verifica y atribuye al
país; lo que no se puede comprobar no entra**, y lo que entra queda marcado
«sin calificar» hasta que una persona lo califique.

Cómo se verifica cada uno:

- **YouTube.** Un canal se lee por su identificador, no por su nombre. Se abre la
  página del canal, se extrae el identificador que declara y se arma su feed
  oficial de novedades. Si el feed no trae videos con fecha, no entra.
- **Telegram.** Sólo canales **públicos**, por su versión web abierta
  —`t.me/s/<canal>`—, que es la vía sin cuenta ni sesión. Se comprueba que haya
  mensajes y cuándo fue el último.
- **Mastodon.** Se pide la línea pública de la instancia por su interfaz abierta
  y se mira la fecha de la última publicación.

**Límite de recolección.** Sólo material público, sin cuentas de la Fundación ni
accesos forzados: `doctrina/limites.md`.

  python canales.py ARG BRA            propone canales para esos Estados
  python canales.py --todos            los 33
  python canales.py ARG --incorporar   suma al padrón lo verificado
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
from expandir import ESTADOS, INGLES, AMBIGUOS, PADRON, PROPUESTAS, _padron, _pedir  # noqa: E402
from mejoras import _llama  # noqa: E402
from verificar import verificar  # noqa: E402

DIAS_QUIETO = 45      # un canal que no publica hace mes y medio no sirve para alertar


def _normalizar(s):
    s = re.sub(r"[^a-z0-9]+", "", (s or "").lower())
    return s


def _medios_del_pais(iso3):
    """Los medios que ya están en el padrón atribuidos a ese Estado. Si un canal
    se llama como uno de ellos, la atribución está hecha: el país ya fue
    verificado cuando entró el sitio."""
    d = _padron()
    salida = {}
    for clave in ("rss", "youtube", "telegram"):
        for e in d.get(clave, []):
            if e.get("iso3") != iso3:
                continue
            nombre = e.get("nombre") or e.get("canal")
            if nombre:
                salida[_normalizar(nombre)] = nombre
    return salida


def _atribuye(iso3, texto, nombre_canal=""):
    bajo = texto.lower()
    for nombre in {ESTADOS.get(iso3, ""), INGLES.get(iso3, "")}:
        if nombre and nombre.lower() in bajo:
            return f"se nombra en {nombre}"
    # Segundo camino: coincide con un medio ya atribuido a ese Estado.
    canal = _normalizar(nombre_canal)
    if len(canal) >= 4:
        for clave, propio in _medios_del_pais(iso3).items():
            if len(clave) >= 4 and (clave in canal or canal in clave):
                return f"coincide con {propio}, ya atribuido en el padrón"
    return ""


# --------------------------------------------------------------------------
def resolver_youtube(identificador, iso3, nombre=""):
    """El feed de un canal se arma con su identificador, no con su nombre. La
    página del canal lo declara; se lo toma de ahí y no se adivina."""
    limpio = identificador.strip().lstrip("@")
    for url in (f"https://www.youtube.com/@{limpio}",
                f"https://www.youtube.com/c/{limpio}",
                f"https://www.youtube.com/user/{limpio}"):
        try:
            # La página de un canal pesa unos 2,5 MB y el identificador aparece
            # al final: leer de menos era la razón por la que no se encontraba.
            html = _pedir(url, 2_600_000)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            continue
        # El enlace canónico primero: es el que el propio canal declara. Nunca se
        # toma un «UC…» suelto del texto, que puede ser el de un video ajeno.
        m = (re.search(r'rel="canonical"\s+href="[^"]*channel/(UC[\w-]{20,})', html)
             or re.search(r'"browseId"\s*:\s*"(UC[\w-]{20,})"', html)
             or re.search(r'"channelId"\s*:\s*"(UC[\w-]{20,})"', html))
        if not m:
            continue
        canal = m.group(1)
        atribucion = _atribuye(iso3, re.sub(r"<[^>]+>", " ", html[:200_000]),
                               nombre or identificador)
        feed = f"https://www.youtube.com/feeds/videos.xml?channel_id={canal}"
        r = verificar({"url_rss": feed})
        if r["estado"] != "viva":
            return {"estado": f"el canal existe pero su feed {r['estado']}"}
        return {"estado": "viva" if atribucion else "viva, sin atribuir",
                "canal_id": canal, "url": url, "ultima": r.get("ultima"),
                "atribucion": atribucion or "sin comprobar"}
    return {"estado": "no se encontró el canal"}


def verificar_telegram(canal, iso3, nombre_propuesto=""):
    """Sólo la vista pública, que es la que se puede leer sin cuenta."""
    nombre = canal.strip().lstrip("@").replace("https://t.me/", "").replace("s/", "")
    try:
        html = _pedir(f"https://t.me/s/{nombre}", 700_000)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        return {"estado": f"no responde ({type(e).__name__})"}
    if "tgme_widget_message" not in html:
        return {"estado": "no es un canal público legible"}
    fechas = re.findall(r'datetime="([0-9T:+\-]+)"', html)
    ultima = None
    if fechas:
        try:
            ultima = max(datetime.fromisoformat(f) for f in fechas)
        except ValueError:
            ultima = None
    if ultima and (datetime.now(timezone.utc) - ultima).days > DIAS_QUIETO:
        return {"estado": f"quieto hace {(datetime.now(timezone.utc) - ultima).days} días"}
    atribucion = _atribuye(iso3, re.sub(r"<[^>]+>", " ", html[:200_000]),
                           nombre_propuesto or canal)
    return {"estado": "viva" if atribucion else "viva, sin atribuir", "canal": nombre,
            "atribucion": atribucion or "sin comprobar",
            "ultima": ultima.date().isoformat() if ultima else None}


def verificar_mastodon(instancia, iso3):
    dominio = instancia.strip().replace("https://", "").rstrip("/")
    try:
        crudo = _pedir(f"https://{dominio}/api/v1/timelines/public?limit=5", 400_000)
        datos = json.loads(crudo)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError,
            ValueError) as e:
        return {"estado": f"no responde ({type(e).__name__})"}
    if not isinstance(datos, list) or not datos:
        return {"estado": "la instancia no publica línea pública"}
    try:
        ultima = max(datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))
                     for d in datos if d.get("created_at"))
    except (ValueError, KeyError):
        return {"estado": "sin fechas legibles"}
    if (datetime.now(timezone.utc) - ultima).days > DIAS_QUIETO:
        return {"estado": f"quieta hace {(datetime.now(timezone.utc) - ultima).days} días"}
    return {"estado": "viva", "instancia": dominio, "ultima": ultima.date().isoformat()}


# --------------------------------------------------------------------------
def proponer(iso3, cuantas=12):
    pais, ingles = ESTADOS.get(iso3, iso3), INGLES.get(iso3, iso3)
    aclaracion = AMBIGUOS.get(iso3, "")
    sistema = ("Sos documentalista de una fundación de análisis. Devolvés SOLO un arreglo "
               "JSON, sin texto alrededor, con objetos "
               "{\"plataforma\", \"identificador\", \"nombre\", \"tipo\"}. "
               "plataforma: youtube, telegram o mastodon. identificador: para youtube el "
               "arroba del canal; para telegram el nombre del canal público; para mastodon "
               "el dominio de la instancia. tipo: prensa, oficial, analisis o sociedad civil. "
               "No inventes: si no estás seguro de que el canal existe, no lo incluyas.")
    pregunta = (f"País: {pais} ({ingles})"
                + (f". ATENCIÓN: se trata de {aclaracion}. " if aclaracion else ". ")
                + f"Canales que publiquen seguido sobre política, seguridad, protesta o "
                f"libertad de prensa: canales de YouTube de medios y de organismos públicos, "
                f"canales públicos de Telegram de medios o de gobierno, e instancias de "
                f"Mastodon del país. Hasta {cuantas}.")
    r = _llama(pregunta, sistema)
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
        plataforma = str(c.get("plataforma", "")).lower().strip()
        identificador = str(c.get("identificador", "")).strip()
        if plataforma in ("youtube", "telegram", "mastodon") and identificador:
            salida.append({"plataforma": plataforma, "identificador": identificador,
                           "nombre": str(c.get("nombre", ""))[:80], "iso3": iso3,
                           "tipo": c.get("tipo", "prensa"), "propuesto_por": r["modelo"]})
    return salida


def revisar(c):
    try:
        if c["plataforma"] == "youtube":
            r = resolver_youtube(c["identificador"], c["iso3"], c.get("nombre", ""))
        elif c["plataforma"] == "telegram":
            r = verificar_telegram(c["identificador"], c["iso3"], c.get("nombre", ""))
        else:
            r = verificar_mastodon(c["identificador"], c["iso3"])
        return {**c, **r}
    except Exception as e:                        # noqa: BLE001
        return {**c, "estado": f"error al revisar ({type(e).__name__}: {e})"}


def _ya_estan(d):
    return ({e.get("canal_id") for e in d.get("youtube", [])}
            | {str(e.get("canal", "")).lower() for e in d.get("telegram", [])}
            | {str(e.get("instancia", "")).lower() for e in d.get("mastodon", [])})


def main():
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    incorporar = "--incorporar" in sys.argv
    isos = list(ESTADOS) if "--todos" in sys.argv else argumentos
    if not isos:
        sys.exit(__doc__)
    d = _padron()
    ya = _ya_estan(d)
    todas, nuevas = [], []
    for iso in isos:
        candidatas = proponer(iso)
        if not candidatas:
            print(f"  {iso}: sin candidatas")
            continue
        with ThreadPoolExecutor(max_workers=5) as pool:
            resultados = list(pool.map(revisar, candidatas))
        vivas = [r for r in resultados
                 if r["estado"] == "viva"
                 and r.get("canal_id", r.get("canal", r.get("instancia", ""))) not in ya]
        todas += resultados
        nuevas += vivas
        sin_atribuir = [r for r in resultados if r["estado"] == "viva, sin atribuir"]
        print(f"  {iso} · {len(candidatas)} propuestas · {len(vivas)} verificadas"
              + (f" · {len(sin_atribuir)} vivas sin atribuir, para revisar a mano"
                 if sin_atribuir else ""))
        for v in vivas:
            print(f"      {v['plataforma']:9s} {v['nombre'][:30]:32s} "
                  f"{v.get('canal_id') or v.get('canal') or v.get('instancia')}")
        PROPUESTAS.mkdir(exist_ok=True)
        (PROPUESTAS / f"canales-{date.today()}.json").write_text(
            json.dumps(todas, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{len(nuevas)} canales nuevos verificados de {len(todas)} propuestas.")
    if incorporar and nuevas:
        nota = (f"Propuesto por el modelo gratuito y verificado el {date.today()}. "
                f"Corrobora, pero no cuenta como familia independiente hasta calificarlo.")
        for v in nuevas:
            if v["plataforma"] == "youtube":
                d["youtube"].append({"iso3": v["iso3"], "canal_id": v["canal_id"],
                                     "nombre": v["nombre"], "tipo": v["tipo"],
                                     "activo": True, "calidad": "sin calificar", "nota": nota})
            elif v["plataforma"] == "telegram":
                d["telegram"].append({"canal": v["canal"], "iso3": v["iso3"],
                                      "tipo": v["tipo"], "idioma": "es",
                                      "calidad": "sin calificar", "nota": nota})
            else:
                d["mastodon"].append({"instancia": v["instancia"], "iso3": v["iso3"],
                                      "activo": True, "calidad": "sin calificar", "nota": nota})
        PADRON.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Padrón: {len(nuevas)} canales incorporados como «sin calificar».")


if __name__ == "__main__":
    main()
