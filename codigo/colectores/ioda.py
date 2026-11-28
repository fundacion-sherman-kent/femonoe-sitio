# -*- coding: utf-8 -*-
"""IODA · cortes de conectividad por país (señal I-1).

IODA (Georgia Tech) compara el tráfico de cada país con su propio historial y
emite alertas con nivel —warning o critical— y la medición que la detectó. Un
corte no dice la causa: puede ser un apagón eléctrico, un huracán o un corte
deliberado. Eso lo decide una persona, no el robot. Sin clave."""
import time
from datetime import datetime, timedelta, timezone

from concurrent.futures import ThreadPoolExecutor

from comun import (A_LA_VEZ, dias_atras, guardar_eventos, guardar_serie, padron,
                   pedir_json, sitio_de, turno)

HORAS_PARA_SOSTENIDA = 6

URL = ("https://api.ioda.inetintel.cc.gatech.edu/v2/outages/alerts"
       "?from={desde}&until={hasta}&entityType=country&entityCode={cc}")


def main():
    hasta = int(time.time())
    desde = hasta - dias_atras() * 86400
    hoy = datetime.now(timezone.utc).date()
    todas, criticas_dia, sostenidas, eventos, caidos = [], [], [], [], []
    # **Los 33 países se consultan a la vez, no en fila.**
    #
    # Los 33 pedidos van al MISMO servicio académico de Georgia Tech, así que
    # acá el freno por sitio no es un detalle: es la condición para poder
    # paralelizar sin golpearlo. Le llegan tres pedidos a la vez y nunca dos
    # seguidos a menos de 0,4 segundos. El regulador está en `comun.py`.
    SITIO = sitio_de(URL)

    def _un_pais(p):
        """Lee un país y devuelve lo que encontró.

        Corre en su propio hilo y **no toca ninguna lista compartida**: junta
        lo suyo y lo entrega. Quien lo llamó lo suma, en el orden del padrón,
        para que dos corridas iguales den el mismo archivo.
        """
        mis_todas, mis_criticas, mis_sostenidas, mis_eventos = [], [], [], []
        try:
            with turno(SITIO):
                d = pedir_json(URL.format(desde=desde, hasta=hasta, cc=p["iso2"]), segundos=60)
        except Exception as e:  # noqa: BLE001 — un país que falla no tumba la corrida
            return None, f"{p['nombre']}: {type(e).__name__}"
        alertas = d.get("data") or []
        if isinstance(alertas, dict):
            alertas = alertas.get("alerts") or []

        # **Cuánto duró cada corte.** IODA emite una alerta cuando algo cae y
        # otra cuando se recupera, de la misma medición. Emparejarlas da la
        # duración, y la duración es lo que separa un corte de un parpadeo.
        #
        # Hizo falta el 5/10/2026. En Haití la medición `gtr` repite una crítica
        # que se recupera en pocas horas **31 veces en doce meses**, con mediana
        # de 3,5 h. Con el umbral viejo —tres críticas en el día, sin mirar nada
        # más— tres parpadeos bastaban para declarar un hecho duro. Medido sobre
        # los 33 Estados y 366 días: el umbral viejo dispara 75 veces, 1,43 por
        # semana. Exigiendo además que al menos una no se recupere en seis horas,
        # dispara 12, una cada mes en toda la región.
        #
        # Una crítica sin alerta de recuperación cuenta como sostenida: el corte
        # sigue abierto, que es lo más grave, no lo menos.
        criticas = sorted((x for x in alertas if x.get("level") == "critical"),
                          key=lambda x: x.get("time", 0))
        recuperaciones = sorted((x for x in alertas if x.get("level") != "critical"),
                                key=lambda x: x.get("time", 0))

        def _sostenida(c):
            for n in recuperaciones:
                if (n.get("datasource") == c.get("datasource")
                        and n.get("time", 0) > c.get("time", 0)):
                    return (n["time"] - c["time"]) / 3600 > HORAS_PARA_SOSTENIDA
            return True

        por_dia = {}
        for a in alertas:
            dia = datetime.fromtimestamp(int(a.get("time", 0)), timezone.utc).date().isoformat()
            c = por_dia.setdefault(dia, [0, 0, 0])
            c[0] += 1
            if a.get("level") == "critical":
                c[1] += 1
                if _sostenida(a):
                    c[2] += 1
                mis_eventos.append({
                    "id": f"ioda-{p['iso3']}-{a.get('time')}-{a.get('datasource')}",
                    "fecha": dia, "iso3": p["iso3"], "senal": "ioda_corte",
                    "detalle": f"alerta crítica de {a.get('datasource')}",
                    "fuente": "IODA, Georgia Tech", "url": "https://ioda.inetintel.cc.gatech.edu/"})
        # los días sin alerta también son dato: cero, no vacío
        for k in range(dias_atras()):
            dia = (hoy - timedelta(days=k)).isoformat()
            n, c, sost = por_dia.get(dia, (0, 0, 0))
            mis_todas.append((dia, p["iso3"], n))
            mis_criticas.append((dia, p["iso3"], c))
            mis_sostenidas.append((dia, p["iso3"], sost))
        return (mis_todas, mis_criticas, mis_sostenidas, mis_eventos), None

    # `map` devuelve en el orden del padrón, no en el orden en que contestaron:
    # la misma entrada da la misma salida.
    with ThreadPoolExecutor(max_workers=A_LA_VEZ) as grupo:
        for resultado, caida in grupo.map(_un_pais, list(padron())):
            if caida:
                caidos.append(caida)
                continue
            a, b, c, ev = resultado
            todas += a
            criticas_dia += b
            sostenidas += c
            eventos += ev

    guardar_serie("ioda_alertas", todas)
    guardar_serie("ioda_criticas", criticas_dia)
    guardar_serie("ioda_sostenidas", sostenidas)
    guardar_eventos("ioda_corte", eventos)
    print(f"IODA: {len(eventos)} alertas críticas; sin respuesta: {caidos or 'ninguno'}")


if __name__ == "__main__":
    main()
