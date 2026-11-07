# -*- coding: utf-8 -*-
"""GDACS y USGS · desastres naturales como CONTEXTO, no como alerta.

FEMÓNOE no mide amenazas naturales. Un evento naranja o rojo de GDACS, o un
sismo de magnitud 6 o más, vuelve más sensibles los umbrales de gobernabilidad
y seguridad de ese país durante 21 días. Sin clave."""
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from comun import RAIZ, padron, pedir, pedir_json

GDACS = "https://www.gdacs.org/xml/rss.xml"
USGS = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_month.geojson"
NS = {"gdacs": "http://www.gdacs.org"}


def main():
    estados = padron()
    salida = []
    for it in ElementTree.fromstring(pedir(GDACS, segundos=90)).iter("item"):
        nivel = (it.findtext("gdacs:alertlevel", "", NS) or "").lower()
        pais = it.findtext("gdacs:country", "", NS) or ""
        if nivel not in ("orange", "red"):
            continue
        try:
            fecha = parsedate_to_datetime(it.findtext("pubDate", "")).date().isoformat()
        except (TypeError, ValueError):
            fecha = ""
        for p in estados:
            if p["nombre_en"].lower() in pais.lower():
                salida.append({"iso3": p["iso3"], "fuente": "GDACS", "nivel": nivel, "fecha": fecha,
                               "titulo": it.findtext("title", ""), "url": it.findtext("link", "")})
    for f in pedir_json(USGS, segundos=60)["features"]:
        pr = f["properties"]
        if (pr.get("mag") or 0) < 6:
            continue
        for p in estados:
            if re.search(re.escape(p["nombre_en"]), pr.get("place") or "", re.I):
                salida.append({"iso3": p["iso3"], "fuente": "USGS", "nivel": f"M{pr['mag']}",
                               "titulo": pr.get("place"), "url": pr.get("url"),
                               "fecha": datetime.fromtimestamp(pr["time"] / 1000, timezone.utc).date().isoformat()})
    (RAIZ / "datos" / "contexto.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    print(f"Contexto: {len(salida)} eventos naturales relevantes en los 33")


if __name__ == "__main__":
    main()
