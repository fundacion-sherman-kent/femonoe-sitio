# -*- coding: utf-8 -*-
"""Piezas comunes de los colectores de FEMÓNOE.

Cada señal se guarda como una serie por país en datos/series/<señal>.csv, con
tres columnas: fecha, iso3, valor. Volver a correr un colector reemplaza los
valores de las mismas fechas: nunca duplica.
"""
import contextlib
import csv
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SERIES = RAIZ / "datos" / "series"
EVENTOS = RAIZ / "datos" / "eventos"
UA = "FEMONOE-robot/0.1 (Fundacion Sherman Kent; +https://fundacionkent.org)"


def padron() -> list:
    return json.loads((RAIZ / "padron.json").read_text(encoding="utf-8"))["estados"]


def pedir(url: str, segundos: int = 60, cabeceras: dict | None = None,
          intentos: int = 3, espera: int = 20) -> bytes:
    """GET con reintento. Ante un 429 espera cada vez más, y se identifica con su
    nombre real: la casa no se disfraza de navegador."""
    ultimo = None
    for n in range(intentos):
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(cabeceras or {})})
        try:
            with urllib.request.urlopen(req, timeout=segundos) as r:
                return r.read(20_000_000)
        except urllib.error.HTTPError as e:
            ultimo = e
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError) as e:
            ultimo = e
        time.sleep(espera * (n + 1))
    raise ultimo


def pedir_json(url: str, **kw):
    return json.loads(pedir(url, **kw).decode("utf-8", "replace"))


def guardar_serie(senal: str, filas: list) -> int:
    """filas: [(fecha 'AAAA-MM-DD', iso3, valor)]. Reemplaza las fechas repetidas."""
    SERIES.mkdir(parents=True, exist_ok=True)
    archivo = SERIES / f"{senal}.csv"
    datos = {}
    if archivo.exists():
        with archivo.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                datos[(r["fecha"], r["iso3"])] = r["valor"]
    for fecha, iso3, valor in filas:
        datos[(fecha, iso3)] = valor
    with archivo.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fecha", "iso3", "valor"])
        for (fecha, iso3), valor in sorted(datos.items()):
            w.writerow([fecha, iso3, valor])
    return len(filas)


def leer_serie(senal: str) -> dict:
    """{iso3: {fecha: valor}}"""
    archivo = SERIES / f"{senal}.csv"
    salida = {}
    if not archivo.exists():
        return salida
    with archivo.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            salida.setdefault(r["iso3"], {})[r["fecha"]] = float(r["valor"])
    return salida


def guardar_eventos(nombre: str, eventos: list) -> None:
    """Hechos discretos (cortes, bloqueos, hechos graves), deduplicados por 'id'."""
    EVENTOS.mkdir(parents=True, exist_ok=True)
    archivo = EVENTOS / f"{nombre}.json"
    previos = json.loads(archivo.read_text(encoding="utf-8")) if archivo.exists() else []
    por_id = {e["id"]: e for e in previos}
    for e in eventos:
        por_id[e["id"]] = e
    archivo.write_text(json.dumps(sorted(por_id.values(), key=lambda e: e["fecha"]),
                                  ensure_ascii=False, indent=1), encoding="utf-8")


def dias_atras() -> int:
    """Una corrida normal mira pocos días; con RELLENO=1 trae la historia larga."""
    return 400 if os.environ.get("RELLENO") == "1" else 10


# ═════════════════════════════════════════════════════════════════════════════
# PEDIR MUCHAS COSAS A LA VEZ SIN DEJAR DE SER UN BUEN VECINO.
#
# POR QUÉ EXISTE. Los colectores pedían una fuente, dormían un segundo, pedían
# la siguiente. Medido el 9/10/2026 sobre corridas reales: las 436 fuentes de
# redes tardaban así **16 minutos**, de los cuales 436 segundos eran sueño
# puro; los 33 países de IODA, 40 segundos, de los cuales 33 de sueño. Entre
# los dos se comían el 80 % de la corrida diaria y casi un cuarto de los 2.000
# minutos mensuales que la cuenta de la Fundación reparte entre FEMÓNOE, la
# vigilancia y Ysyry.
#
# QUÉ SE CUIDA DE VERDAD. Una pausa global no cuida a nadie: la fuente
# siguiente casi siempre es otro sitio. Lo que hay que cuidar es **el ritmo
# contra cada sitio**, y eso cambia todo, porque hay grupos enteros que pegan
# al mismo lugar: 100 canales de YouTube, 80 de Telegram, y los 33 países de
# IODA contra un único servicio académico de Georgia Tech. Paralelizar sin este
# freno sería golpearlos.
#
# LA REGLA. A cada sitio, como máximo tres pedidos a la vez y nunca dos
# seguidos a menos de 0,4 segundos. Es más suave que una persona leyendo con
# varias pestañas abiertas, y se aplica sola: el que pide no tiene que
# acordarse.
A_LA_VEZ = 12               # pedidos en vuelo, contando todos los sitios
A_LA_VEZ_POR_SITIO = 3      # pedidos en vuelo contra un mismo sitio
PAUSA_POR_SITIO = 0.4       # segundos mínimos entre dos pedidos al mismo sitio

_sitios = {}
_cerrojo_sitios = threading.Lock()


def _estado_de(sitio: str):
    with _cerrojo_sitios:
        if sitio not in _sitios:
            _sitios[sitio] = [threading.Semaphore(A_LA_VEZ_POR_SITIO),
                              threading.Lock(), 0.0]
        return _sitios[sitio]


@contextlib.contextmanager
def turno(sitio: str):
    """Espera a que a este sitio le toque, y lo libera al salir.

    El cerrojo de ritmo se toma sólo para mirar el reloj y esperar, **no
    durante el pedido**: si se tomara durante el pedido, cada sitio quedaría en
    fila de uno y no habría paralelo ninguno.
    """
    semaforo, ritmo, _ = _estado_de(sitio)
    semaforo.acquire()
    try:
        with ritmo:
            estado = _estado_de(sitio)
            falta = PAUSA_POR_SITIO - (time.monotonic() - estado[2])
            if falta > 0:
                time.sleep(falta)
            estado[2] = time.monotonic()
        yield
    finally:
        semaforo.release()


def sitio_de(url: str) -> str:
    """El dominio contra el que se va a pedir: la unidad que se cuida."""
    u = url if "//" in url else "https://" + url
    return urllib.parse.urlparse(u).netloc.lower() or url
