# -*- coding: utf-8 -*-
"""ACLED · protestas, violencia y muertes por país y por semana (G-1b, S-1b, S-2, S-3).

Entra con la misma cuenta de la Fundación que usa SIWA, pero con su propia copia
de la clave en este depósito: FEMÓNOE no lee ni escribe nada de SIWA.
Licencia: uso con atribución y sin fines comerciales. No se republica el
listado de hechos: sólo recuentos semanales y el aviso de hechos graves.

**EL MURO DE DOCE MESES, Y POR QUÉ ESTA FUENTE NO SIRVE PARA ALERTAR.**
Medido contra la API el 22/10/2026: la licencia de la Fundación sólo deja ver
hechos de **doce meses de antigüedad**. La propia respuesta lo declara, en un
campo que este colector descartaba:

    "data_query_restrictions": {"date_recency": {"quantity": 12,
        "unit": "Months", "date": "2025-10-22"}}

El muro es móvil: cada día se libera un día más. Pedirle los últimos diez días
—lo que hacía este colector— es pedirle lo que la licencia no permite ver, y la
API no contesta con un error: contesta `count: 0, success: true`. El colector
escribía ese vacío como un cero por semana y por país, y **un cero es una
lectura, no una ausencia**: el detector lo compara contra una mediana de ceros,
nunca marca nada, y una ola de protesta real se lee como calma. Las tres series
estuvieron 402 días así sin que ningún control lo dijera.

**Qué hace entonces este colector.** Pide la ventana que está justo detrás del
muro, así que cada corrida incorpora la semana recién liberada y el archivo
avanza solo. ACLED queda siendo lo que con esta licencia puede ser: **la
historia con que se calcula lo normal de cada Estado —la tasa base—, nunca la
señal de esta semana.** Para la semana en curso están GDELT, IODA, OONI,
Cloudflare y la familia de redes.

**Y no inventa.** Sólo escribe semanas enteramente detrás del muro. Si la
ventana que pidió vuelve vacía estando del lado permitido, eso sí es una falla
y se dice en voz alta en vez de guardarse como cero.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from comun import UA, dias_atras, guardar_eventos, guardar_serie, padron, pedir_json

TOKEN_URL = "https://acleddata.com/oauth/token"
READ_URL = "https://acleddata.com/api/acled/read"
PROTESTA = ("Protests", "Riots")
VIOLENCIA = ("Battles", "Explosions/Remote violence", "Violence against civilians")

# Dónde queda anotado el muro, para que el resto de la casa lo lea en vez de
# suponerlo: el tablero, la ficha de la familia y el control de frescura.
MURO = Path(__file__).resolve().parent.parent / "datos" / "acled_muro.json"

# Cuántas semanas detrás del muro se vuelven a pedir en cada corrida. Tres, no
# una: ACLED corrige y completa hechos después de publicarlos, y la semana
# recién liberada es justo la que más se corrige.
SEMANAS_DETRAS = 3


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


POR_PAGINA = 5000      # el tope que la API aplica por consulta
PAGINAS_MAXIMAS = 40   # 200.000 hechos: si no alcanza, algo anda mal y se dice


def _consultar(token: str, iso_num, desde: date, hasta: date, pagina: int = 1) -> dict:
    """Una consulta, con la respuesta entera: los hechos Y lo que la API avisa."""
    params = {"iso": iso_num, "event_date": f"{desde}|{hasta}",
              "event_date_where": "BETWEEN", "limit": POR_PAGINA, "page": pagina,
              "with_total": "true",
              "fields": "event_id_cnty|event_date|event_type|fatalities"}
    return pedir_json(READ_URL + "?" + urllib.parse.urlencode(params), segundos=180,
                      cabeceras={"Authorization": "Bearer " + token}) or {}


def _todas_las_filas(token: str, iso_num, desde: date, hasta: date):
    """Todos los hechos de la ventana, paginando hasta llegar al total.

    **Por qué existe, y es un defecto que se pagó caro.** El 22/10/2026 una
    corrida de relleno de 400 días trajo Brasil completo las primeras 27 semanas
    y **cero las últimas 30**: la consulta excede el tope de 5.000 filas, la API
    devuelve sólo la primera página —que son los hechos más viejos— y el colector
    escribía cero para las semanas que esa página no alcanzaba. Pisó con ceros
    los datos buenos de agosto y septiembre que ya estaban en el archivo.

    Es la misma falla de siempre con otra cara: **tomar la ausencia de respuesta
    por una respuesta**. Acá se arregla donde está el conocimiento: la API
    declara `total_count`, así que el colector pagina hasta alcanzarlo y, si no
    lo alcanza, **devuelve None y no se escribe nada de ese Estado** — es mejor
    un Estado sin actualizar que un Estado en cero.

    Devuelve `(filas, aviso)`; si `filas` es None, el aviso dice por qué.
    """
    filas, total, pagina = [], None, 1
    while pagina <= PAGINAS_MAXIMAS:
        d = _consultar(token, iso_num, desde, hasta, pagina)
        lote = d.get("data") or []
        if total is None:
            total = d.get("total_count")
        filas += lote
        if not lote or (total is not None and len(filas) >= int(total)):
            break
        pagina += 1
    if total is None:
        return None, "la API no declaró `total_count`: no se puede saber si faltan hechos"
    if len(filas) < int(total):
        return None, (f"truncado: {len(filas)} hechos de {total} en "
                      f"{PAGINAS_MAXIMAS} páginas")
    return filas, f"{len(filas)} hechos en {pagina} página(s)"


def _leer_muro(respuesta: dict):
    """Hasta qué fecha deja ver la licencia, según la respuesta de la API.

    Se lee de la respuesta y no se escribe a mano porque el muro se mueve todos
    los días y porque una licencia puede cambiar sin avisar. Si la API dejara de
    declararlo se devuelve None y el colector no escribe nada: es preferible un
    archivo que no avanza a un archivo con ceros inventados.
    """
    r = (respuesta.get("data_query_restrictions") or {}).get("date_recency") or {}
    try:
        return date.fromisoformat(str(r["date"])[:10]), r
    except (KeyError, TypeError, ValueError):
        return None, r


def main():
    token = _token()
    hoy = date.today()

    # Primera consulta, al solo efecto de que la API declare su muro. Se le pide
    # un día viejo y uno solo para que cueste lo mínimo.
    muro, ficha = _leer_muro(_consultar(token, 76, hoy - timedelta(days=400),
                                        hoy - timedelta(days=399)))
    if muro is None:
        raise SystemExit(
            "ACLED: la API no declaró `data_query_restrictions.date_recency`, así que no "
            "se sabe hasta dónde deja ver la licencia. No se escribe nada: un cero "
            f"inventado es peor que un archivo que no avanza. Lo que vino: {ficha!r}")
    atraso = (hoy - muro).days
    MURO.parent.mkdir(parents=True, exist_ok=True)
    MURO.write_text(json.dumps({
        "medido": hoy.isoformat(), "muro": muro.isoformat(), "dias_de_atraso": atraso,
        "declarado_por_la_api": ficha,
        "que_significa": ("La licencia de la Fundación sólo deja ver hechos de esta "
                          "antigüedad. ACLED sirve para la tasa base histórica; no puede "
                          "corroborar una señal de la semana en curso."),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"ACLED · muro de la licencia: {muro} ({atraso} días de atraso, "
          f"{ficha.get('description')})")

    # La ventana va pegada al muro, no pegada a hoy.
    hasta = muro
    if dias_atras() <= 10:
        desde = _lunes(muro) - timedelta(weeks=SEMANAS_DETRAS)
    else:
        desde = muro - timedelta(days=dias_atras())
    print(f"ACLED · ventana pedida: {desde} a {hasta}")

    prot, viol, muertes, graves = [], [], [], []
    sin_hechos, con_hechos, truncados = [], 0, []
    for p in padron():
        try:
            filas, aviso = _todas_las_filas(token, p["iso_num"], desde, hasta)
        except Exception as e:  # noqa: BLE001
            print(f"ACLED {p['nombre']}: {type(e).__name__}")
            continue
        if filas is None:
            # **No se escribe nada de este Estado.** Es mejor un Estado sin
            # actualizar que un Estado en cero: el cero lo lee el detector como
            # calma y lo mete en la mediana.
            print(f"ACLED {p['nombre']}: NO SE ESCRIBE — {aviso}")
            truncados.append(p["iso3"])
            continue
        if filas:
            con_hechos += 1
        else:
            # Un Estado sin hechos en tres semanas es posible y normal en el
            # Caribe. Igual se escriben sus ceros: la ventana está detrás del
            # muro, así que acá el cero SÍ es una lectura.
            sin_hechos.append(p["iso3"])
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
        lunes = _lunes(desde)
        while lunes <= hasta:
            # **Sólo semanas enteras detrás del muro.** La que lo cruza viene
            # recortada: escribirla sería escribir un recuento bajo que no es
            # bajo, es incompleto.
            if lunes + timedelta(days=6) > muro:
                break
            a, b, c = semanas.get(lunes, (0, 0, 0))
            k = lunes.isoformat()
            prot.append((k, p["iso3"], a))
            viol.append((k, p["iso3"], b))
            muertes.append((k, p["iso3"], c))
            lunes += timedelta(days=7)
        time.sleep(1)

    if con_hechos == 0:
        raise SystemExit(
            f"ACLED: los Estados del padrón volvieron todos vacíos para {desde}–{hasta}, "
            f"que está detrás del muro ({muro}) y por lo tanto debería traer hechos. Eso "
            "es una falla de la fuente o de la cuenta, no calma en la región. No se "
            "escribe nada.")

    guardar_serie("acled_protesta", prot)
    guardar_serie("acled_violencia", viol)
    guardar_serie("acled_muertes", muertes)
    guardar_eventos("acled_hecho_grave", graves)
    print(f"ACLED: {len(prot)} semanas-país escritas ({con_hechos} Estados con hechos, "
          f"{len(sin_hechos)} sin hechos), {len(graves)} con 10 muertes o más")
    if truncados:
        print(f"ACLED: {len(truncados)} Estado(s) NO escritos por respuesta incompleta: "
              f"{', '.join(truncados)}. Conservan lo que ya tenían.")
    print(f"ACLED: la semana en curso NO se mide — el muro está en {muro}. "
          "Esta familia da la tasa base, no la señal.")


if __name__ == "__main__":
    main()
