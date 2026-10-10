# -*- coding: utf-8 -*-
"""ACLED · protestas, violencia y muertes por país y por semana (G-1, S-1, S-2, S-3).

Entra con la misma cuenta de la Fundación que usa SIWA, pero con su propia copia
de la clave en este depósito: FEMÓNOE no lee ni escribe nada de SIWA.
Licencia: uso con atribución y sin fines comerciales. No se republica el
listado de hechos: sólo recuentos semanales y el aviso de hechos graves.
ACLED publica con demora; la semana en curso llega incompleta y el detector la
ignora."""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

from comun import UA, dias_atras, guardar_eventos, guardar_serie, padron, pedir_json

TOKEN_URL = "https://acleddata.com/oauth/token"
READ_URL = "https://acleddata.com/api/acled/read"
PROTESTA = ("Protests", "Riots")
VIOLENCIA = ("Battles", "Explosions/Remote violence", "Violence against civilians")


def _token() -> str:
    usuario, clave = os.environ.get("ACLED_USUARIO"), os.environ.get("ACLED_CLAVE")
    if not usuario or not clave:
        raise SystemExit("ACLED: faltan los secretos ACLED_USUARIO y ACLED_CLAVE en este depósito")
    body = urllib.parse.urlencode({"username": usuario, "password": clave,
                                   "grant_type": "password", "client_id": "acled",
                                   "scope": "authenticated"}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["access_token"]


def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def main():
    token = _token()
    hasta = date.today()
    desde = hasta - timedelta(days=dias_atras())
    prot, viol, muertes, graves = [], [], [], []
    for p in padron():
        params = {"iso": p["iso_num"], "event_date": f"{desde}|{hasta}",
                  "event_date_where": "BETWEEN", "limit": 0,
                  "fields": "event_id_cnty|event_date|event_type|fatalities"}
        try:
            filas = pedir_json(READ_URL + "?" + urllib.parse.urlencode(params), segundos=180,
                               cabeceras={"Authorization": "Bearer " + token}).get("data") or []
        except Exception as e:  # noqa: BLE001
            print(f"ACLED {p['nombre']}: {type(e).__name__}")
            continue
        semanas = {}
        for f in filas:
            s = semanas.setdefault(_lunes(date.fromisoformat(f["event_date"])), [0, 0, 0])
            m = int(float(f.get("fatalities") or 0))
            s[0] += f.get("event_type") in PROTESTA
            s[1] += f.get("event_type") in VIOLENCIA
            s[2] += m
            if m >= 10:
                graves.append({"id": f"acled-{f['event_id_cnty']}", "fecha": f["event_date"],
                               "iso3": p["iso3"], "senal": "acled_hecho_grave",
                               "detalle": f"{f.get('event_type')}: {m} muertes",
                               "fuente": "ACLED", "url": "https://acleddata.com/"})
        lunes = _lunes(desde)  # todas las semanas, con cero donde no hubo hechos
        while lunes <= hasta:
            a, b, c = semanas.get(lunes, (0, 0, 0))
            k = lunes.isoformat()
            prot.append((k, p["iso3"], a))
            viol.append((k, p["iso3"], b))
            muertes.append((k, p["iso3"], c))
            lunes += timedelta(days=7)
        time.sleep(1)
    guardar_serie("acled_protesta", prot)
    guardar_serie("acled_violencia", viol)
    guardar_serie("acled_muertes", muertes)
    guardar_eventos("acled_hecho_grave", graves)
    print(f"ACLED: {len(prot)} semanas-país, {len(graves)} hechos con 10 muertes o más")


if __name__ == "__main__":
    main()
