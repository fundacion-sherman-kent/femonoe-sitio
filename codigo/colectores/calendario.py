# -*- coding: utf-8 -*-
"""Calendario institucional de FEMÓNOE · elecciones y fechas fijas de los 33.

Para qué sirve. Los umbrales bajan de 3 a 2 desvíos cuando el país tiene una
elección o un vencimiento institucional dentro de los 21 días: en esas ventanas
lo mismo vale más. El detector lee ese calendario desde que se escribieron los
umbrales, pero el archivo no existía: **hasta hoy el multiplicador nunca se
activó.**

De dónde sale. Dos fuentes, y se declara cuál sostiene cada fecha:

1. `calendario_base.json` —opcional, escrito a mano— para lo confirmado contra
   la autoridad electoral del país o el boletín oficial. Lleva `confirmado: true`.
2. **Wikidata**, consultada por SPARQL, gratis y sin clave. Cobertura despareja,
   sobre todo en el Caribe oriental: entra como `confirmado: false`.

Una fecha sin confirmar **sirve para bajar el umbral** —es un uso conservador:
mirar mejor nunca es el riesgo— pero **no se publica** en el calendario público
hasta que una segunda fuente la sostenga. Es la regla de la casa.

  python colectores/calendario.py          actualiza calendario.json
  python colectores/calendario.py --ver    muestra lo que hay, sin consultar
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from comun import RAIZ, UA, padron

SALIDA = RAIZ / "calendario.json"
BASE = RAIZ / "calendario_base.json"
SPARQL = "https://query.wikidata.org/sparql"
MINUTOS = 40          # presupuesto: si se agota, guarda lo que juntó
DIAS_ATRAS = 60       # una elección reciente también mueve el umbral
DIAS_ADELANTE = 540

# Clases de Wikidata que cuentan como fecha institucional. Verificadas en vivo el
# 23/9/2026: Q40231 es «elección» y Q43109, «referéndum». Las dos que se habían
# usado antes —Q4504495 y Q380782— resultaron ser «ceremonia de premiación» y
# «comandante en jefe», y metían ruido. Lo demás —juicios, plazos
# constitucionales, asunciones— entra por `calendario_base.json`, a mano.
CLASES = {"Q40231": "elección", "Q43109": "referéndum"}


def _consultar(consulta: str, segundos: int = 120) -> list:
    datos = urllib.parse.urlencode({"query": consulta, "format": "json"}).encode()
    req = urllib.request.Request(SPARQL, data=datos, headers={
        "User-Agent": UA, "Accept": "application/sparql-results+json",
        "Content-Type": "application/x-www-form-urlencoded"})
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=segundos) as r:
                return json.load(r)["results"]["bindings"]
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if intento == 2:
                print(f"  Wikidata no respondió: {e}")
                return []
            time.sleep(20 * (intento + 1))
    return []


def _qids(isos: list) -> dict:
    """ISO3 -> identificador de Wikidata. Una sola consulta, por P298."""
    valores = " ".join(f'"{i}"' for i in isos)
    filas = _consultar(f"""SELECT ?iso ?p WHERE {{
      VALUES ?iso {{ {valores} }}
      ?p wdt:P298 ?iso .
    }}""")
    return {f["iso"]["value"]: f["p"]["value"].rsplit("/", 1)[-1] for f in filas}


def _fechas_del_pais(qid: str, desde: date, hasta: date) -> list:
    """Sólo fechas con precisión de día. Wikidata guarda muchas elecciones con
    precisión de año, y las devuelve como «1 de enero»: tomarlas por buenas haría
    bajar el umbral un día cualquiera. Se descartan."""
    clases = " ".join(f"wd:{q}" for q in CLASES)
    filas = _consultar(f"""SELECT DISTINCT ?e ?eLabel ?fecha ?raizLabel WHERE {{
      VALUES ?raiz {{ {clases} }}
      ?e wdt:P17 wd:{qid} ; wdt:P31/wdt:P279* ?raiz ; p:P585 ?dec .
      ?dec psv:P585 ?nodo .
      ?nodo wikibase:timeValue ?fecha ; wikibase:timePrecision ?precision .
      FILTER(?precision >= 11)
      FILTER(?fecha >= "{desde}T00:00:00Z"^^xsd:dateTime
             && ?fecha <= "{hasta}T00:00:00Z"^^xsd:dateTime)
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
    }} ORDER BY ?fecha LIMIT 40""")
    salida, vistos = [], set()
    for f in filas:
        clave = (f["e"]["value"], f["fecha"]["value"][:10])
        if clave in vistos:
            continue
        vistos.add(clave)
        salida.append({
            "fecha": f["fecha"]["value"][:10],
            "tipo": f.get("raizLabel", {}).get("value", "fecha institucional"),
            "titulo": f.get("eLabel", {}).get("value", ""),
            "fuente": "Wikidata",
            "url": f["e"]["value"],
            "confirmado": False,
        })
    return salida


def _base() -> list:
    if not BASE.exists():
        return []
    entradas = json.loads(BASE.read_text(encoding="utf-8"))
    for e in entradas:
        e["confirmado"] = True
        e.setdefault("fuente", "autoridad nacional")
    return entradas



def _verificado() -> list:
    """Lo que ya se coteja contra el organismo del país **no se vuelve a pedir**.

    Esto existe por un accidente del 2/10/2026: este colector se regenera entero
    desde Wikidata, y al correr se llevó puestas tres fechas que se habían
    verificado a mano contra la ONPE y el TSE, con enlace y cita. La regla de
    la casa dice que todo dato se actualiza solo; **actualizar no puede ser
    borrar una verificación**. Una fecha confirmada contra su organismo es un
    hecho acreditado, y lo acreditado no vuelve a dudar porque pasó un robot.

    Entra primero en la fusión, así que manda sobre lo que traiga Wikidata."""
    if not SALIDA.exists():
        return []
    try:
        previas = json.loads(SALIDA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in previas
            if e.get("confirmado") and (e.get("confirmacion") or {}).get("organismo")]


def _fusionar(base: list, hallado: list) -> list:
    """Una entrada por país y día. Lo confirmado manda: si la base ya tiene esa
    fecha, la de Wikidata no la duplica ni la pisa. Dos actos el mismo día en el
    mismo país son la misma ventana: se juntan en una sola línea."""
    por_dia = {(e["iso3"], e["fecha"]): e for e in base}
    for e in hallado:
        clave = (e["iso3"], e["fecha"])
        previa = por_dia.get(clave)
        if previa is None:
            por_dia[clave] = e
        elif not previa.get("confirmado") and e["titulo"] not in previa["titulo"]:
            previa["titulo"] = f"{previa['titulo']} · {e['titulo']}"
    return sorted(por_dia.values(), key=lambda e: (e["fecha"], e["iso3"]))


def ver():
    if not SALIDA.exists():
        print("Todavía no hay calendario.")
        return
    d = json.loads(SALIDA.read_text(encoding="utf-8"))
    hoy = date.today()
    proximas = [e for e in d if e["fecha"] >= hoy.isoformat()]
    confirmadas = [e for e in proximas if e.get("confirmado")]
    print(f"{len(d)} fechas · {len(proximas)} por venir · "
          f"{len(confirmadas)} confirmadas por fuente oficial")
    for e in proximas[:25]:
        sello = "confirmada" if e.get("confirmado") else "sin confirmar"
        print(f"  {e['fecha']}  {e['iso3']}  {e['titulo'][:60]:60s} {sello}")


def main():
    if "--ver" in sys.argv:
        ver()
        return
    isos = [p["iso3"] for p in padron()]
    desde, hasta = date.today() - timedelta(days=DIAS_ATRAS), date.today() + timedelta(days=DIAS_ADELANTE)
    print(f"Calendario: {len(isos)} Estados, del {desde} al {hasta}")
    qids = _qids(isos)
    faltan = [i for i in isos if i not in qids]
    if faltan:
        print(f"  Sin identificador en Wikidata: {', '.join(faltan)}")
    hallado, limite = [], time.time() + MINUTOS * 60
    for n, iso in enumerate(isos, 1):
        if iso not in qids:
            continue
        if time.time() > limite:
            print(f"  Presupuesto agotado en {iso} ({n} de {len(isos)}): se guarda lo juntado")
            break
        for e in _fechas_del_pais(qids[iso], desde, hasta):
            hallado.append({"iso3": iso, **e})
    entradas = _fusionar(_verificado() + _base(), hallado)
    SALIDA.write_text(json.dumps(entradas, ensure_ascii=False, indent=1), encoding="utf-8")
    paises = len({e["iso3"] for e in entradas})
    print(f"Calendario: {len(entradas)} fechas en {paises} Estados "
          f"({sum(1 for e in entradas if e.get('confirmado'))} confirmadas)")


if __name__ == "__main__":
    main()
