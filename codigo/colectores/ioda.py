# -*- coding: utf-8 -*-
"""IODA · cortes de conectividad por país (señal I-1).

IODA (Georgia Tech) compara el tráfico de cada país con su propio historial y
emite alertas con nivel —warning o critical— y la medición que la detectó. Un
corte no dice la causa: puede ser un apagón eléctrico, un huracán o un corte
deliberado. Eso lo decide una persona, no el robot. Sin clave."""
import time
from datetime import datetime, timedelta, timezone

from comun import dias_atras, guardar_eventos, guardar_serie, padron, pedir_json

URL = ("https://api.ioda.inetintel.cc.gatech.edu/v2/outages/alerts"
       "?from={desde}&until={hasta}&entityType=country&entityCode={cc}")


def main():
    hasta = int(time.time())
    desde = hasta - dias_atras() * 86400
    hoy = datetime.now(timezone.utc).date()
    todas, criticas, eventos, caidos = [], [], [], []
    for p in padron():
        try:
            d = pedir_json(URL.format(desde=desde, hasta=hasta, cc=p["iso2"]), segundos=60)
        except Exception as e:  # noqa: BLE001 — un país que falla no tumba la corrida
            caidos.append(f"{p['nombre']}: {type(e).__name__}")
            continue
        alertas = d.get("data") or []
        if isinstance(alertas, dict):
            alertas = alertas.get("alerts") or []
        por_dia = {}
        for a in alertas:
            dia = datetime.fromtimestamp(int(a.get("time", 0)), timezone.utc).date().isoformat()
            c = por_dia.setdefault(dia, [0, 0])
            c[0] += 1
            if a.get("level") == "critical":
                c[1] += 1
                eventos.append({
                    "id": f"ioda-{p['iso3']}-{a.get('time')}-{a.get('datasource')}",
                    "fecha": dia, "iso3": p["iso3"], "senal": "ioda_corte",
                    "detalle": f"alerta crítica de {a.get('datasource')}",
                    "fuente": "IODA, Georgia Tech", "url": "https://ioda.inetintel.cc.gatech.edu/"})
        # los días sin alerta también son dato: cero, no vacío
        for k in range(dias_atras()):
            dia = (hoy - timedelta(days=k)).isoformat()
            n, c = por_dia.get(dia, (0, 0))
            todas.append((dia, p["iso3"], n))
            criticas.append((dia, p["iso3"], c))
        time.sleep(1)
    guardar_serie("ioda_alertas", todas)
    guardar_serie("ioda_criticas", criticas)
    guardar_eventos("ioda_corte", eventos)
    print(f"IODA: {len(eventos)} alertas críticas; sin respuesta: {caidos or 'ninguno'}")


if __name__ == "__main__":
    main()
