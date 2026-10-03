# -*- coding: utf-8 -*-
"""Calendario electoral de los 33, desde ElectionGuide (IFES).

**Por qué hizo falta otra fuente.** El calendario se armaba sólo con Wikidata, y
medido el 2/10/2026 daba **siete fechas para 33 Estados en doce meses**. La
causa no era la consulta: se probó con precisión de día y de año, por país y por
jurisdicción, y el resultado no cambiaba. **Las elecciones de la región en
Wikidata no tienen fecha cargada** —Guatemala, Nicaragua, México y Chile
devuelven sus comicios sin `P585`—. El límite era la fuente, no el filtro.

**Qué aporta ésta.** ElectionGuide, del IFES, lleva las elecciones nacionales
del mundo desde 1998 y **declara si la fecha está confirmada o es tentativa**,
que es exactamente la distinción que la casa ya usa. Los 33 Estados están en su
padrón. No pide clave.

**Qué se conserva.** La regla no cambia: una fecha entra confirmada sólo si la
fuente la declara confirmada, y `confirmar.py` la sigue cotejando contra el
organismo electoral del propio país. ElectionGuide es la segunda fuente, no la
última palabra.

**Lo que esta fuente no cubre:** elecciones subnacionales. ElectionGuide sigue
comicios nacionales. Las estatales, regionales y municipales —las de Chihuahua,
las regionales peruanas— vienen de Wikidata o se cargan a mano, y eso queda
declarado en el origen de cada fecha.
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CALENDARIO = RAIZ / "calendario.json"
BASE = "https://www.electionguide.org/electionresults/"
UA = "FEMONOE-robot/0.1 (Fundacion Sherman Kent; +https://fundacionkent.org)"
DIAS_ADELANTE = 540

# El identificador de cada Estado en ElectionGuide, leído de su propio
# formulario de búsqueda el 2/10/2026. Los 33 están.
IDS = {"ARG": "11", "BOL": "27", "BRA": "31", "CHL": "44", "COL": "48",
       "CRI": "53", "CUB": "56", "DOM": "62", "ECU": "64", "SLV": "66",
       "GTM": "90", "HTI": "94", "HND": "97", "MEX": "140", "NIC": "156",
       "PAN": "167", "PRY": "169", "PER": "170", "URY": "228", "VEN": "231",
       "BLZ": "23", "GUY": "93", "SUR": "203", "JAM": "108", "TTO": "216",
       "BRB": "20", "BHS": "17", "DMA": "61", "GRD": "87", "LCA": "183",
       "ATG": "10", "KNA": "182", "VCT": "185"}
POR_ID = {v: k for k, v in IDS.items()}

MESES = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
         "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def _fecha(texto):
    """«Oct 4 2026» a fecha ISO. Si no se entiende, no se adivina."""
    m = re.match(r"([A-Za-z]{3})[a-z]*\s+(\d{1,2})\s+(\d{4})", texto.strip())
    if not m or m.group(1).lower() not in MESES:
        return None
    try:
        return date(int(m.group(3)), MESES[m.group(1).lower()], int(m.group(2))).isoformat()
    except ValueError:
        return None


def traer(anios):
    q = [("countries[]", v) for v in IDS.values()]
    q += [("years[]", str(a)) for a in anios]
    req = urllib.request.Request(BASE + "?" + urllib.parse.urlencode(q),
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        html = r.read(3_000_000).decode("utf-8", "replace")
    salida = []
    for fila in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        plano = re.sub(r"\s+", " ", fila)
        f = re.search(r"<strong>([^<]+)</strong>", plano)
        marca = re.search(r"<small>\((\w)\)</small>", plano)
        cuerpo = re.search(r'<a href="/elections/id/\d+/">([^<]+)</a>', plano)
        pais = re.search(r'<a href="/countries/id/(\d+)/">', plano)
        if not (f and cuerpo and pais):
            continue
        cuando = _fecha(f.group(1))
        iso = POR_ID.get(pais.group(1))
        if not cuando or not iso:
            continue
        salida.append({
            "fecha": cuando, "iso3": iso,
            "titulo": re.sub(r"\s+", " ", cuerpo.group(1)).strip(),
            # «d» es *declared*: la fecha está fijada. «t» es *tentative*.
            # Se traslada tal cual, sin mejorarla.
            "confirmado": (marca.group(1).lower() == "d") if marca else False,
            "tipo": "eleccion",
            "fuente": "ElectionGuide (IFES)",
            "url": "https://www.electionguide.org/elections/type/upcoming/",
            "origen": "nacional",
        })
    return salida


def main():
    hoy = date.today()
    tope = (hoy + timedelta(days=DIAS_ADELANTE)).isoformat()
    anios = sorted({hoy.year, hoy.year + 1, (hoy + timedelta(days=DIAS_ADELANTE)).year})
    try:
        traidas = traer(anios)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"ElectionGuide: no respondió ({type(e).__name__}). No se toca el calendario.")
        return
    nuevas = [e for e in traidas if hoy.isoformat() <= e["fecha"] <= tope]
    cal = json.loads(CALENDARIO.read_text(encoding="utf-8")) if CALENDARIO.exists() else []
    # Lo ya confirmado contra el organismo del país **no se pisa**: esa es una
    # verificación de primera fuente y ElectionGuide es la segunda.
    # Un mismo día en un mismo país es UNA fecha institucional, aunque se
    # elijan tres cuerpos. Brasil el 4 de octubre elige Presidencia, Cámara y
    # Senado: para el umbral y para el lector eso es una jornada electoral, no
    # tres. Se fusiona, y los cuerpos quedan listados dentro.
    por_clave = {}
    for e in cal:
        por_clave.setdefault((e.get("iso3"), str(e.get("fecha", ""))[:10]), e)
    agregadas = fusionadas = 0
    for e in nuevas:
        clave = (e["iso3"], e["fecha"])
        ya = por_clave.get(clave)
        if ya is None:
            cal.append(e)
            por_clave[clave] = e
            agregadas += 1
            continue
        cuerpos = ya.setdefault("cuerpos", [])
        if e["titulo"] not in cuerpos and e["titulo"] != ya.get("titulo"):
            cuerpos.append(e["titulo"])
        # Una segunda fuente que la declara confirmada la confirma; ninguna la
        # desconfirma, porque la confirmación de la primera no se pierde.
        if e["confirmado"] and not ya.get("confirmado"):
            ya["confirmado"] = True
            ya.setdefault("confirmacion", {})
            ya["confirmacion"] = {"organismo": "ElectionGuide (IFES)",
                                  "donde": e["url"], "fecha": hoy.isoformat(),
                                  "textual": ("La fuente la declara «(d)», fecha "
                                              "declarada, y no tentativa.")}
        fusionadas += 1
    cal.sort(key=lambda x: str(x.get("fecha", "")))
    CALENDARIO.write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
    porvenir = [e for e in cal if str(e.get("fecha", ""))[:10] >= hoy.isoformat()]
    print(f"ElectionGuide: {len(traidas)} elecciones leídas, {len(nuevas)} en ventana · "
          f"{agregadas} nuevas al calendario, {fusionadas} fusionadas con una ya cargada")
    print(f"  El calendario queda con {len(porvenir)} fechas por delante, "
          f"{sum(1 for e in porvenir if e.get('confirmado'))} confirmadas")


if __name__ == "__main__":
    main()
