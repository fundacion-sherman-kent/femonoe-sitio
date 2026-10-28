# -*- coding: utf-8 -*-
"""Corredores comerciales de SIWA, traídos a las zonas de FEMÓNOE.

**Qué es un corredor.** SIWA le pregunta a Comtrade de Naciones Unidas dos cosas
sobre el mismo par de Estados y el mismo año: cuánto declara **A** que exportó a
**B**, y cuánto declara **B** que importó de **A**. Las dos cifras deberían
parecerse. Cuando no se parecen, la diferencia es el corredor: Honduras declara
haber exportado 422 millones a Nicaragua y Nicaragua declara haber importado
1.003 millones de Honduras —medido el 5/10/2026—, y ahí hay 580 millones que una
de las dos aduanas no vio.

**Por qué entra a FEMÓNOE, y por dónde.** Las diez zonas transfronterizas se
medían **sumando series nacionales**: protestas de un lado más protestas del
otro. Eso describe a los dos Estados, no al cruce. Un corredor es lo contrario:
es una medición **bilateral por construcción**, que no existe para un país solo.
Es la primera evidencia propiamente transfronteriza que tiene la plataforma.

**Lo que NO hace, y es lo más importante.** Un corredor **no abre una alerta**.
Comtrade se actualiza por año, no por día: un «cambio» entre dos corridas sería
un artefacto del calendario de la fuente, no un hecho del mundo. Esto es
**contexto permanente de la zona**, del mismo rango que saber que ahí hay una
zona franca. Usarlo como disparador sería anunciar un hecho que no ocurrió.

**De dónde sale y con qué licencia.** De los datos públicos de SIWA
(`siwa.fundacionkent.org/datos/publico/comercio.json`), **CC BY 4.0**, leídos por
HTTP como cualquier otra fuente. No se toca el depósito de SIWA ni se escribe
nada en él: el cruce va en un solo sentido, que es lo que fijó el acta el
21/9/2026. La calificación de la fuente viaja tal como la escribió SIWA —no se
recalifica lo que otro ya calificó— y la atribución queda en cada registro.

**El vacío que deja, declarado.** Cuatro de las diez zonas no tienen ningún
corredor medido: Colombia–Venezuela, Esequibo, Haití–República Dominicana y
Venezuela–Brasil. No es que el comercio no exista: es que **esos Estados no
declaran a Comtrade**, y justamente son las zonas sobre las que más se querría
mirar. El silencio de la fuente no es ausencia del fenómeno, y así se publica.
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# La consola de Windows viene en cp1252 y se cae con una flecha. Los flujos del
# robot fijan PYTHONIOENCODING, pero un programa que sólo funciona dentro de su
# flujo no se puede probar a mano, y lo que no se prueba a mano no se arregla.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import zonas as _zonas  # noqa: E402

FUENTE = "https://siwa.fundacionkent.org/datos/publico/comercio.json"
SALIDA = RAIZ / "datos" / "corredores.json"
UA = "FEMONOE-robot/0.1 (Fundacion Sherman Kent; +https://fundacionkent.org)"


def traer(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def main():
    try:
        d = traer(FUENTE)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"SIWA no respondió ({type(e).__name__}). No se toca nada.")
        return
    corredores = d.get("corredores") or []
    proc = d.get("procedencia") or {}
    if not corredores:
        print("SIWA respondió sin corredores. No se inventa ninguno.")
        return

    zs = _zonas.zonas()
    por_zona, usados = {}, set()
    for z in zs:
        miembros = set(z["estados"])
        suyos = [c for c in corredores
                 if c.get("origen") in miembros and c.get("destino") in miembros]
        for c in suyos:
            usados.add((c["origen"], c["destino"]))
        por_zona[z["codigo"]] = {
            "nombre": z["nombre"], "estados": z["estados"],
            "corredores": sorted(suyos, key=lambda c: -abs(c.get("brecha_pct") or 0)),
            # Un corredor «marcado» es uno que la propia SIWA señaló. No se
            # inventa un umbral acá: el que mide, califica.
            "marcados": sum(1 for c in suyos if c.get("llama_la_atencion")),
        }

    # Los que no caen en ninguna zona también se guardan: son pares fronterizos
    # medidos sobre los que FEMÓNOE **todavía no abrió zona**, y saber cuáles son
    # es lo que permite discutir el padrón de zonas con un número encima.
    fuera = [c for c in corredores if (c.get("origen"), c.get("destino")) not in usados]
    sin_dato = [z["codigo"] for z in zs if not por_zona[z["codigo"]]["corredores"]]

    registro = {
        "que_es": ("Diferencia entre lo que un Estado declara haber exportado a otro y "
                   "lo que ese otro declara haber importado de él, en el mismo año y "
                   "sobre el total de mercaderías."),
        "no_abre_alertas": ("Comtrade se actualiza por año. Un cambio entre dos corridas "
                            "sería un artefacto del calendario de la fuente, no un hecho "
                            "del mundo. Esto es contexto permanente de la zona."),
        "traido_el": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": {
            "nombre": "SIWA · Fundación Sherman Kent, sobre Comtrade de Naciones Unidas",
            "url": FUENTE, "licencia": "CC BY 4.0",
            "medido_en": proc.get("obtenido_en"),
            "calificacion": proc.get("calificacion"),
            "metodo_de_la_fuente": d.get("metodo"),
        },
        "zonas": por_zona,
        "fuera_de_zona": sorted(fuera, key=lambda c: -abs(c.get("brecha_pct") or 0)),
        "vacios_declarados": [
            {"que": "zonas sin ningún corredor medido", "cuales": sin_dato,
             "por_que": ("Esos Estados no declaran a Comtrade. El silencio de la fuente "
                         "no es ausencia del fenómeno.")},
            {"que": "pares fronterizos medidos sin zona abierta en FEMÓNOE",
             "cuantos": len(fuera),
             "por_que": ("El padrón de zonas se armó por criterio territorial, no por "
                         "lo que hubiera medido. Estos pares son candidatos a discutir.")},
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")

    con = sum(1 for z in zs if por_zona[z["codigo"]]["corredores"])
    marcados = sum(por_zona[z["codigo"]]["marcados"] for z in zs)
    print(f"Corredores de SIWA: {len(corredores)} medidos el "
          f"{str(proc.get('obtenido_en', ''))[:10]}")
    print(f"  {con} de {len(zs)} zonas con al menos un corredor · {marcados} marcados por SIWA")
    for z in zs:
        v = por_zona[z["codigo"]]
        if not v["corredores"]:
            continue
        detalle = ", ".join(f"{c['origen']}→{c['destino']} {c['brecha_pct']:+.0f} %"
                            for c in v["corredores"] if c.get("llama_la_atencion"))
        print(f"    {z['codigo']}: {len(v['corredores'])} corredor(es)"
              + (f" · marcados: {detalle}" if detalle else ""))
    print(f"  sin ningún corredor medido: {', '.join(sin_dato) or 'ninguna'}")
    print(f"  {len(fuera)} pares medidos fuera de toda zona "
          f"({sum(1 for c in fuera if c.get('llama_la_atencion'))} marcados)")


if __name__ == "__main__":
    main()
