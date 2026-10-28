# -*- coding: utf-8 -*-
"""Cloudflare Radar · cortes de internet anotados, con su causa declarada.

**Qué resuelve, y es el hueco más grande que tiene FEMÓNOE.** IODA detecta que
el tráfico de un país cayó, pero no sabe por qué: un cable cortado, un temporal
y un apagón deliberado se ven igual desde afuera. Así quedó escrito en la
lectura DISARM de la casa —«no prueba que sea deliberada»— y así se publicó.

Cloudflare anota sus cortes **con la causa**: distingue un apagón dispuesto por
un gobierno de una falla técnica o de un corte de energía. Eso es exactamente lo
que al eje del entorno informativo le faltaba para pasar de «hubo una caída» a
«hubo una caída y esto es lo que la originó».

**Y es una segunda familia.** Hoy casi toda señal de FEMÓNOE sale de fuente
única, porque la familia `redes` no corrobora hasta el 19/11/2026. Cloudflare
mide con infraestructura propia, distinta de la de IODA —que es académica— y de
la de OONI —que son voluntarios—, así que corrobora de verdad y no por
parentesco.

**La llave.** Es de sólo lectura sobre Radar, gratuita, y vive en el robot. La
misma que ya usa SIWA. Sin ella este colector **se detiene declarándolo** en
vez de escribir un archivo vacío que después alguien lea como «no pasó nada».

**Escrito sin poder probarlo**, porque la llave no está en esta máquina. Por eso
no da por sentada la forma de la respuesta: busca cada campo entre varios
nombres posibles, y **lo que no entiende lo anota en vez de inventarlo**. La
primera corrida del robot es su verdadera prueba.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import RAIZ, guardar_serie, padron  # noqa: E402

BASE = "https://api.cloudflare.com/client/v4/radar/annotations/outages"
SECRETO = ("CLOUDFLARE_RADAR", "CF_RADAR_TOKEN", "CLOUDFLARE_TOKEN")
DIAS = 400          # la historia que se pide, para que la familia nazca madura
UA = ("FEMONOE-robot/0.1 (Fundacion Sherman Kent; +https://fundacionkent.org)")

# Causas que Cloudflare declara. Sólo las dos primeras hablan de una decisión;
# las demás son el mundo físico, y confundirlas sería el error que esta fuente
# vino a evitar.
DELIBERADO = ("GOVERNMENT_DIRECTED", "SHUTDOWN", "GOVERNMENT")


def _llave():
    for nombre in SECRETO:
        v = os.environ.get(nombre)
        if v:
            return v
    return ""


def _pedir(token, desde, hasta):
    q = urllib.parse.urlencode({"dateStart": desde.isoformat() + "T00:00:00Z",
                                "dateEnd": hasta.isoformat() + "T00:00:00Z",
                                "limit": 1000, "format": "json"})
    req = urllib.request.Request(f"{BASE}?{q}", headers={
        "User-Agent": UA, "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _campo(d, *nombres):
    """El primer campo que exista, probando varios nombres. La respuesta de un
    servicio ajeno cambia de forma sin avisar; buscar por un solo nombre es
    cómo un colector empieza a devolver ceros en silencio."""
    for n in nombres:
        if isinstance(d, dict) and d.get(n) not in (None, ""):
            return d[n]
    return None


def main():
    token = _llave()
    if not token:
        print("Cloudflare Radar: falta la llave de sólo lectura. No se escribe "
              "nada: un archivo vacío se lee después como «no hubo cortes», y "
              "eso sería mentir. Cargar el secreto CLOUDFLARE_RADAR.")
        return
    # La fuente rechaza cualquier fecha futura: «Must be before now (utc)».
    # Se pide hasta ayer, que ademas evita el dia parcial en curso.
    hasta = date.today() - timedelta(days=1)
    desde = hasta - timedelta(days=DIAS)
    try:
        d = _pedir(token, desde, hasta)
    except urllib.error.HTTPError as e:
        print(f"Cloudflare Radar: respondió {e.code}. "
              f"{e.read(300).decode('utf-8', 'replace')[:200]}")
        return
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"Cloudflare Radar: no respondió ({type(e).__name__}). No se escribe nada.")
        return

    crudas = (d.get("result") or {}).get("annotations") or []
    iso2 = {p["iso2"]: p["iso3"] for p in padron()}
    por_dia, expediente, sin_entender, fuera = defaultdict(int), [], 0, 0
    for a in crudas:
        lugares = _campo(a, "locations", "locationsDetails", "location") or []
        if isinstance(lugares, (str, dict)):
            lugares = [lugares]
        codigos = []
        for l in lugares:
            c = l if isinstance(l, str) else _campo(l, "code", "alpha2", "locationCode")
            if c and str(c).upper() in iso2:
                codigos.append(iso2[str(c).upper()])
        inicio = str(_campo(a, "startDate", "startTime", "start") or "")[:10]
        if not inicio:
            sin_entender += 1       # sin fecha no se puede usar: se declara
            continue
        if not codigos:
            fuera += 1              # corte real, pero de otro Estado del mundo
            continue
        # La causa viene ANIDADA en `outage.outageCause`. `eventType` dice
        # «OUTAGE» en todas, y leerlo como causa daba cero cortes deliberados
        # en una serie donde los hay. Verificado el 1/10/2026 contra la
        # respuesta real de la fuente, que hasta entonces no se habia podido
        # ver porque la llave vive en el robot.
        corte = a.get("outage") if isinstance(a.get("outage"), dict) else {}
        causa = str(_campo(corte, "outageCause", "cause")
                    or _campo(a, "cause", "outageCause") or "").upper()
        alcance = _campo(a, "scope", "asnsDetails", "asns")
        for iso3 in codigos:
            por_dia[(inicio, iso3)] += 1
            expediente.append({
                "fecha": inicio, "iso3": iso3, "causa": causa or "sin declarar",
                "deliberado": any(x in causa for x in DELIBERADO),
                "alcance": alcance if isinstance(alcance, (str, int)) else None,
                "descripcion": str(_campo(a, "description", "title") or "")[:300],
            })

    dias = sorted({k[0] for k in por_dia})
    if not dias:
        print(f"Cloudflare Radar: la fuente respondió pero no trajo ningún corte "
              f"de los 33 Estados en {DIAS} días. {sin_entender} anotaciones no "
              "se pudieron leer. No se escribe serie.")
        return
    filas = [(f, p["iso3"], por_dia.get((f, p["iso3"]), 0))
             for f in dias for p in padron()]
    guardar_serie("cloudflare_cortes", filas)
    deliberados = [e for e in expediente if e["deliberado"]]
    guardar_serie("cloudflare_deliberados",
                  [(f, p["iso3"],
                    sum(1 for e in deliberados if e["fecha"] == f and e["iso3"] == p["iso3"]))
                   for f in dias for p in padron()])
    salida = RAIZ / "datos" / "cortes_anotados.json"
    salida.write_text(json.dumps({
        "generado": date.today().isoformat(),
        "nota": ("Cortes de internet anotados por Cloudflare, con la causa que "
                 "la fuente declara. «deliberado» es lo que Cloudflare atribuye "
                 "a una decisión de gobierno: es su juicio, no el de la casa, y "
                 "así se cita."),
        "anotaciones_sin_leer": sin_entender,
        "cortes": sorted(expediente, key=lambda e: e["fecha"], reverse=True)[:400],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter as _C
    causas = _C(e["causa"] for e in expediente)
    print(f"Cloudflare Radar: {len(expediente)} cortes en los 33 Estados sobre "
          f"{len(dias)} días · {len(deliberados)} atribuidos a decisión de gobierno")
    print(f"   causas: {dict(causas.most_common(8))}")
    print(f"   {fuera} cortes de otros Estados del mundo, descartados por padrón"
          + (f" · {sin_entender} anotaciones sin fecha legible, declaradas"
             if sin_entender else ""))


if __name__ == "__main__":
    main()
