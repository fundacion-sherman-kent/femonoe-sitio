# -*- coding: utf-8 -*-
"""Confirma las fechas del calendario contra la autoridad electoral de cada país.

El calendario se arma con Wikidata, que es gratis y amplia pero no es fuente
oficial: por eso cada fecha nace rotulada **«sin confirmar»**, sirve para bajar
el umbral —un uso conservador— y **no se publica** como confirmada.

Esto busca la segunda fuente, que es la que manda: **la autoridad electoral del
propio país**, ahora que están en el padrón. Va al sitio y al feed del organismo
y busca la fecha escrita como la escribe un organismo —«4 de octubre de 2026»,
«04/10/2026», «October 4, 2026»—. Si la encuentra, la fecha pasa a confirmada
**con el enlace donde se la encontró**; si no, queda como estaba y se anota que
se buscó.

No inventa ni deduce: o la fecha está publicada por el organismo, o no está.

  python confirmar.py            revisa las fechas por venir
  python confirmar.py --ver      muestra el estado del calendario
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
CALENDARIO = RAIZ / "calendario.json"
PADRON = RAIZ / "redes.json"
UA = "FEMONOE-robot/0.1 (Fundacion Sherman Kent; +https://fundacionkent.org)"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
MESES_EN = ["january", "february", "march", "april", "may", "june", "july", "august",
            "september", "october", "november", "december"]
# Un organismo electoral se reconoce por su nombre completo o por su sigla como
# palabra entera: «ine» suelto también está dentro de «Kaieteur» y de «Vorágine».
SIGLAS = r"\b(servel|ine|tse|cne|jce|cse|tsje|jne|onpe|iee|cnе)\b"
PALABRAS = ("electoral", "elecciones", "registraduria", "registraduría",
            "junta central electoral", "tribunal supremo de elecciones",
            "consejo nacional electoral", "corte electoral", "elections", "electoral office")


def _sin_tildes(s):
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()


def autoridades(iso3, padron):
    """Las autoridades electorales del país, de dos lugares.

    **El registro propio manda.** Probado el 2/10/2026: de veinticuatro
    organismos electorales de la región, **ninguno publica RSS**. Buscarlos
    sólo dentro del padrón de fuentes —que es un padrón de feeds— dejaba al
    cotejo revisando una sola fecha de seis. Por eso tienen registro aparte,
    `autoridades.json`, con el sitio y no con un feed que no existe."""
    salida = []
    propio = RAIZ / "autoridades.json"
    if propio.exists():
        for a in json.loads(propio.read_text(encoding="utf-8")).get("autoridades", []):
            if a.get("iso3") == iso3:
                salida.append({"nombre": a["nombre"], "url_rss": a["sitio"],
                               "iso3": iso3, "registro": "autoridades.json"})
    for e in padron.get("rss", []):
        if e.get("iso3") != iso3 or e.get("activo") is False:
            continue
        texto = _sin_tildes(f"{e.get('nombre', '')} {e.get('url_rss', '')}")
        if any(p in texto for p in map(_sin_tildes, PALABRAS)) or re.search(SIGLAS, texto):
            salida.append(e)
    return salida


def _formas(f):
    """La misma fecha como la escribe un organismo."""
    d = date.fromisoformat(f)
    mes, mes_en = MESES[d.month - 1], MESES_EN[d.month - 1]
    return [f"{d.day} de {mes} de {d.year}", f"{d.day} de {mes} del {d.year}",
            f"{d.day:02d}/{d.month:02d}/{d.year}", f"{d.day}/{d.month}/{d.year}",
            f"{d.year}-{d.month:02d}-{d.day:02d}",
            f"{mes_en} {d.day}, {d.year}", f"{d.day} {mes_en} {d.year}"]


def _bajar(url, limite=900_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read(limite).decode("utf-8", "replace")


def buscar(entrada, fuente):
    """Busca la fecha en el feed del organismo y en su portada."""
    urls = [fuente.get("url_rss")]
    raiz = re.match(r"https?://[^/]+", fuente.get("url_rss") or "")
    if raiz:
        urls.append(raiz.group(0))
    formas = [_sin_tildes(x) for x in _formas(entrada["fecha"])]
    for url in filter(None, urls):
        try:
            texto = _sin_tildes(re.sub(r"<[^>]+>", " ", _bajar(url)))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            continue
        texto = re.sub(r"\s+", " ", texto)
        for forma in formas:
            if forma in texto:
                return {"url": url, "forma": forma}
    return None


def main():
    if not CALENDARIO.exists():
        sys.exit("Todavía no hay calendario.")
    calendario = json.loads(CALENDARIO.read_text(encoding="utf-8"))
    if "--ver" in sys.argv:
        for e in calendario:
            if e["fecha"] >= date.today().isoformat():
                sello = "confirmada" if e.get("confirmado") else "sin confirmar"
                print(f"  {e['fecha']}  {e['iso3']}  {e['titulo'][:52]:54s} {sello}")
        return
    padron = json.loads(PADRON.read_text(encoding="utf-8"))
    hoy = date.today().isoformat()
    revisadas = confirmadas = 0
    for entrada in calendario:
        if entrada["fecha"] < hoy or entrada.get("confirmado"):
            continue
        fuentes = autoridades(entrada["iso3"], padron)
        if not fuentes:
            entrada["confirmacion"] = {"estado": "sin autoridad electoral en el padrón",
                                       "revisado": hoy}
            continue
        revisadas += 1
        hallazgo = None
        for f in fuentes:
            hallazgo = buscar(entrada, f)
            if hallazgo:
                entrada.update({
                    "confirmado": True, "fuente": f.get("nombre"),
                    "confirmacion": {"estado": "confirmada", "revisado": hoy,
                                     "url": hallazgo["url"], "texto": hallazgo["forma"],
                                     "organismo": f.get("nombre")}})
                confirmadas += 1
                print(f"  CONFIRMADA  {entrada['iso3']} {entrada['fecha']} · "
                      f"{f.get('nombre')} · {hallazgo['url'][:60]}")
                break
        if not hallazgo:
            entrada["confirmacion"] = {
                "estado": "buscada y no hallada", "revisado": hoy,
                "organismos": [f.get("nombre") for f in fuentes]}
            print(f"  sin hallar  {entrada['iso3']} {entrada['fecha']} · se buscó en "
                  f"{', '.join(f.get('nombre', '') for f in fuentes)}")
    CALENDARIO.write_text(json.dumps(calendario, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    print(f"\n{revisadas} fechas revisadas contra su autoridad electoral · "
          f"{confirmadas} confirmadas.")


if __name__ == "__main__":
    main()
