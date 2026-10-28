# -*- coding: utf-8 -*-
"""OONI sobre panel fijo de dominios · la señal I-2d, que compara lo comparable.

**Por qué existe, y son dos cegueras que se pagaron el mismo día.**

El 27/9/2026 la Oficina cambió la señal de OONI del **recuento** de bloqueos a
la **tasa** sobre mediciones, para no confundir «más bloqueo» con «más gente
midiendo». Esa misma tarde el disenso mostró que la tasa tiene la ceguera
opuesta: en Cuba los confirmados cayeron 86 % entre el 20 y el 26 de septiembre
y la tasa quedó plana, porque cayó también el denominador.

Y ninguna de las dos resuelve la trampa de fondo: **si cambia la lista de sitios
que la sonda pone a prueba, las dos se mueven sin que el Estado haya hecho
nada.** Cinco de los ocho dominios que encabezaron el episodio cubano no se
habían medido ni una vez en agosto.

**Qué mide esta señal.** La tasa de bloqueo **restringida a los dominios que ya
se venían midiendo antes**. Un sitio que aparece por primera vez en la lista de
prueba no puede mover la señal, por bloqueado que esté: lo que muestra es que
alguien empezó a mirarlo, y eso es una noticia sobre el medidor.

**Lo que se aprendió al probarla contra el caso cubano**, y por eso se adopta:
sobre los veinticuatro dominios que hoy dan bloqueo y que **ya se medían** del 1
al 14 de septiembre, la tasa pasó de 9,6 % —intervalo de 5,3 a 16,8 %— a 25,6 %.
Dos conclusiones que ninguna de las otras dos señales podía separar: el padrón
**ya estaba censurado** antes del 18, de modo que el salto de 0 % a 18 % del
indicador de país exagera enormemente el cambio; y **aun así hubo un aumento
real**, que queda fuera del ruido de muestreo. Las dos cosas a la vez.

**Costo.** Dos consultas por Estado y por corrida, unos tres segundos cada una:
alrededor de cuatro minutos para los 33. Sin clave.
"""
from collections import defaultdict
from datetime import date, timedelta

from comun import guardar_serie, padron, pedir_json

# El panel se arma con lo medido entre estos dos hitos, contados hacia atrás
# desde el día que se evalúa. El hueco de quince días existe para que un
# episodio que arranca hoy no contamine su propia referencia.
REFERENCIA_DESDE = 60
REFERENCIA_HASTA = 15
MEDICIONES_PARA_ENTRAR = 3     # por debajo, el dominio no tiene historia propia
MINIMO_DIARIO = 30             # mediciones de panel en el día; si no, no se emite

URL = ("https://api.ooni.io/api/v1/aggregation?probe_cc={cc}"
       "&test_name=web_connectivity&since={desde}&until={hasta}{ejes}")


def _pedir(cc, desde, hasta, ejes=""):
    d = pedir_json(URL.format(cc=cc, desde=desde, hasta=hasta, ejes=ejes), segundos=180)
    r = (d or {}).get("result")
    return r if isinstance(r, list) else ([r] if isinstance(r, dict) else [])


def panel_de(cc, hoy):
    """Los dominios que ese Estado ya venía midiendo antes de la ventana actual."""
    filas = _pedir(cc, hoy - timedelta(days=REFERENCIA_DESDE),
                   hoy - timedelta(days=REFERENCIA_HASTA), "&axis_x=domain")
    return {x["domain"] for x in filas
            if x.get("domain") and x.get("measurement_count", 0) >= MEDICIONES_PARA_ENTRAR}


def main():
    hoy = date.today()
    desde = hoy - timedelta(days=REFERENCIA_HASTA)
    filas, sin_panel = [], []
    for p in padron():
        cc, i3 = p["iso2"], p["iso3"]
        try:
            panel = panel_de(cc, hoy)
            if len(panel) < 20:
                # Sin panel no se inventa una tasa: se declara y se sigue.
                sin_panel.append(f"{i3} ({len(panel)} dominios)")
                continue
            dia = defaultdict(lambda: [0, 0])
            for x in _pedir(cc, desde, hoy + timedelta(days=1),
                            "&axis_x=measurement_start_day&axis_y=domain"):
                if x.get("domain") not in panel:
                    continue
                d = str(x.get("measurement_start_day"))[:10]
                dia[d][0] += x.get("measurement_count", 0)
                dia[d][1] += x.get("confirmed_count", 0)
            for d, (m, c) in dia.items():
                filas.append((d, i3, round(1000 * c / m) if m >= MINIMO_DIARIO else 0))
        except Exception as e:                                   # noqa: BLE001
            sin_panel.append(f"{i3} (falló: {type(e).__name__})")
    guardar_serie("ooni_panel", filas)
    print(f"OONI panel fijo: {len(filas)} filas país-día sobre dominios con historia "
          f"propia. Sin panel suficiente: {len(sin_panel)}")
    for s in sin_panel[:12]:
        print("   ", s)


if __name__ == "__main__":
    main()
