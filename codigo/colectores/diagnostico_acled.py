# -*- coding: utf-8 -*-
"""Diagnóstico: hasta qué fecha entrega datos la cuenta de ACLED de la Fundación.

La primera recolección trajo hechos hasta el 15/9/2025 y nada después, en los 33
Estados a la vez. Esto comprueba si es un límite de la cuenta, un tope de filas
por consulta o un problema de la consulta misma. No escribe nada."""
import urllib.parse

from acled import READ_URL, _token
from comun import pedir_json


def probar(token, etiqueta, params):
    url = READ_URL + "?" + urllib.parse.urlencode(params)
    try:
        d = pedir_json(url, segundos=120, cabeceras={"Authorization": "Bearer " + token})
    except Exception as e:  # noqa: BLE001
        print(f"{etiqueta:38s} FALLA {type(e).__name__}: {str(e)[:100]}")
        return
    for k in ("messages", "data_query_restrictions", "status", "total_count", "count"):
        if d.get(k) not in (None, [], ""):
            print(f"   {k}: {str(d[k])[:400]}")
    filas = d.get("data") or []
    fechas = sorted(f.get("event_date", "") for f in filas)
    print(f"{etiqueta:38s} filas={len(filas):6d}  claves={sorted(k for k in d if k != 'data')}  "
          f"primera={fechas[0] if fechas else '-'}  última={fechas[-1] if fechas else '-'}")


def main():
    token = _token()
    base = {"iso": 484, "fields": "event_date|event_type|fatalities"}
    probar(token, "México, 2026 completo", {**base, "event_date": "2026-01-01|2026-09-21",
                                            "event_date_where": "BETWEEN", "limit": 0})
    probar(token, "México, últimos 30 días", {**base, "event_date": "2026-08-21|2026-09-21",
                                              "event_date_where": "BETWEEN", "limit": 0})
    probar(token, "México, año 2026 (campo year)", {**base, "year": 2026, "limit": 0})
    probar(token, "México, año 2025 (campo year)", {**base, "year": 2025, "limit": 0})
    probar(token, "México, sin filtro, 5 filas", {**base, "limit": 5})
    probar(token, "México, 2026 ordenado al revés", {**base, "year": 2026, "limit": 5,
                                                     "order": "DESC"})
    probar(token, "Haití, 2026 completo", {"iso": 332, "fields": "event_date|event_type",
                                           "event_date": "2026-01-01|2026-09-21",
                                           "event_date_where": "BETWEEN", "limit": 0})


if __name__ == "__main__":
    main()
