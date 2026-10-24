# -*- coding: utf-8 -*-
"""OONI · bloqueos y anomalías de sitios web, por país y por día (señal I-2).

OONI son mediciones de voluntarios que prueban si un sitio responde. Distingue
*anomalía* (algo raro, puede ser falla técnica) de *bloqueo confirmado*. Una
sola consulta trae todos los países agrupados por día. Sin clave."""
from datetime import date, timedelta

from comun import dias_atras, guardar_serie, padron, pedir_json

MEDICIONES_MINIMAS = 100   # por debajo, la tasa es ruido

URL = ("https://api.ooni.io/api/v1/aggregation?since={desde}&until={hasta}"
       "&test_name=web_connectivity&axis_x=measurement_start_day&axis_y=probe_cc")


def main():
    iso = {p["iso2"]: p["iso3"] for p in padron()}
    hasta = date.today()
    desde = hasta - timedelta(days=dias_atras())
    filas = pedir_json(URL.format(desde=desde, hasta=hasta), segundos=180).get("result") or []
    conf, anom, med, tasa = [], [], [], []
    for f in filas:
        i3 = iso.get(f.get("probe_cc"))
        if not i3:
            continue
        dia = str(f.get("measurement_start_day"))[:10]
        c, m = f.get("confirmed_count", 0), f.get("measurement_count", 0)
        conf.append((dia, i3, c))
        anom.append((dia, i3, f.get("anomaly_count", 0)))
        med.append((dia, i3, m))
        # La tasa, en partes por mil. El conteo crudo sube cuando hay más
        # bloqueo Y cuando hay más voluntarios midiendo, y desde afuera las dos
        # cosas se ven igual. Cuba pasó de 135 mediciones a 1.273 entre el 14 y
        # el 18/9/2026: el conteo se multiplicó por cien, pero la tasa también
        # —de 1,5 % a 17,8 %—, y eso es lo que dice que el bloqueo creció.
        # Por debajo de MEDICIONES_MINIMAS no se calcula: con veinte sondas, un
        # solo bloqueo da 5 % y no significa nada.
        tasa.append((dia, i3, round(1000 * c / m) if m >= MEDICIONES_MINIMAS else 0))
    guardar_serie("ooni_confirmados", conf)
    guardar_serie("ooni_anomalias", anom)
    guardar_serie("ooni_mediciones", med)
    guardar_serie("ooni_tasa", tasa)
    print(f"OONI: {len(conf)} filas país-día, {len({x[1] for x in conf})} Estados con medición")


if __name__ == "__main__":
    main()
