# -*- coding: utf-8 -*-
"""GDELT · archivos diarios de hechos: protestas y violencia por país (G-1, S-1).

Por qué esta vía y no el buscador de GDELT. El buscador (la API de documentos)
limita la tasa y devuelve series distintas entre corridas: SIWA lo dejó afuera
por eso, y a FEMÓNOE le falló dos veces. Los archivos diarios, en cambio, son
fijos: el de un día ya cerrado da siempre lo mismo. Cada archivo pesa unos 7 MB
y trae los hechos del mundo ya clasificados con el código CAMEO.

Qué se cuenta, y qué NO es:
  - protestas      = código raíz 14
  - violencia      = códigos raíz 18, 19 y 20 (agresión, combate, violencia masiva)
Un «hecho» acá es **una nota de prensa codificada**, no un hecho verificado en el
terreno: dos medios que cubren lo mismo pueden dar dos registros. Sirve para
medir si un país se sale de lo habitual, nunca como recuento de lo ocurrido.
El país sale del nombre del lugar de la acción, que GDELT escribe en inglés."""
import csv
import io
import json
import os
import re
import time
import unicodedata
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from comun import dias_atras, guardar_serie, padron, pedir

URL = "http://data.gdeltproject.org/events/{fecha}.export.CSV.zip"
PROTESTA = ("14",)
VIOLENCIA = ("18", "19", "20")
MINUTOS = 70  # presupuesto de tiempo del colector
MANIFIESTO = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
PORCION = "http://data.gdeltproject.org/gdeltv2/{sello}.export.CSV.zip"

# DONDE ESTA CADA COSA, SEGUN EL ANCHO DE LA FILA.
#
# El archivo diario trae 58 columnas; el de 15 minutos, 61, porque en el de 61
# cada bloque geografico lleva un campo mas (el codigo ADM2). El codigo raiz
# cae en la 28 en los dos. El nombre del lugar de la accion, en la 50 y en la
# 52, y ahi esta la trampa: leer el archivo de 15 minutos con el indice del
# diario NO falla — toma el codigo «AR» de una provincia como nombre de pais,
# no empareja con ninguno y **descarta todos los hechos en silencio**. Es el
# mismo modo de falla que se pago con Trinidad y Tobago, explicado arriba.
#
# Medido el 4/11/2026 contra los dos archivos reales, con
# `herramientas/mirar_gdelt_15min.py`.
COLUMNAS = {58: {"raiz": 28, "lugar": 50}, 61: {"raiz": 28, "lugar": 52}}


def _clave(nombre):
    """El nombre de un país, reducido a algo que se pueda comparar.

    **Por qué hizo falta.** El país salía del nombre del lugar que escribe
    GDELT, emparejado **letra por letra** contra el padrón. GDELT escribe en
    mayúsculas de título: «Trinidad And Tobago», con A mayúscula. El padrón dice
    «Trinidad and Tobago». No emparejaban, y **todos los hechos de ese país se
    tiraban en silencio**.

    Medido el 7/10/2026 sobre el archivo de un solo día: se perdían 62 hechos de
    Trinidad y Tobago, 13 de San Vicente y las Granadinas, 8 de Antigua y
    Barbuda y 4 de San Cristóbal y Nieves. Sobre el total de la región es el
    2 %; sobre esos cuatro Estados es **el 100 %**, y por eso figuraban con una
    sola familia de fuentes y no podían sostener una alerta.

    Granada y Barbados nunca fallaron, y ése fue el indicio: son los nombres de
    la región que **no llevan «and»**.

    Se normaliza a minúsculas, sin tildes, sin puntuación y sin el artículo
    inicial —GDELT escribe «The Bahamas» donde el padrón dice «Bahamas»—.
    """
    t = unicodedata.normalize("NFD", nombre or "").lower()
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[4:] if t.startswith("the ") else t


def _un_dia(dia: date, nombres: dict):
    """El archivo diario de un dia ya cerrado."""
    return _un_dia_url(URL.format(fecha=dia.strftime("%Y%m%d")), nombres)


def _un_dia_url(url: str, nombres: dict):
    """Cuenta protestas y violencias de UN archivo, diario o de 15 minutos."""
    crudo = pedir(url, segundos=120, intentos=2, espera=15)
    z = zipfile.ZipFile(io.BytesIO(crudo))
    texto = io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8", errors="replace")
    prot, viol = {}, {}
    for f in csv.reader(texto, delimiter="\t"):
        col = COLUMNAS.get(len(f))
        if not col:
            continue
        iso = nombres.get(_clave((f[col["lugar"]] or "").split(", ")[-1]))
        if not iso:
            continue
        raiz = (f[col["raiz"]] or "")[:2]
        if raiz in PROTESTA:
            prot[iso] = prot.get(iso, 0) + 1
        elif raiz in VIOLENCIA:
            viol[iso] = viol.get(iso, 0) + 1
    return prot, viol


# ═════════════════════════════════════════════════════════════════════════════
# EL DIA EN CURSO, CON LAS PORCIONES DE 15 MINUTOS.
#
# POR QUE EXISTE. El archivo diario de un dia solo aparece cuando el dia
# cerro, asi que este colector arrancaba por ayer y los ejes de gobernabilidad
# y seguridad —los que abren casi todas las alertas— tenian un piso de un dia
# de atraso en los 33 Estados. La direccion fijo el 4/11/2026 que FEMONOE debe
# llegar a tiempo real en cada uno de los Estados.
#
# POR QUE SE PUEDE, Y COMO SE COMPROBO. GDELT publica una porcion cada 15
# minutos. El 4/11/2026 se sumaron **las 96 porciones** del 2/11 y se
# compararon contra el archivo diario de ese mismo dia, con la regla exacta del
# colector: 3.333 hechos de la region contra 3.333, protesta 14 contra 14,
# violencia 219 contra 219, y ninguna porcion faltante. El archivo diario ES la
# union de sus porciones, asi que el dia en curso armado con porciones queda en
# **la misma escala** que el historico y el detector puede compararlos. Ese era
# el criterio de aceptacion, fijado antes de medir en
# `herramientas/mirar_gdelt_15min.py`.
#
# POR QUE SUMA EN VEZ DE RECONTAR. Recontar el dia entero en cada corrida es
# mas simple y no necesita memoria, pero la corrida de la noche bajaria 81
# porciones y el dia completo costaria dos veces y media lo que cuesta sumando.
# Los minutos del plan gratuito son el recurso escaso de la casa —octubre
# cerro en 1.989 de 2.000—, asi que se lleva la cuenta de la ultima porcion
# contada y se suman solo las nuevas.
#
# POR QUE NO SE PISA CON EL ARCHIVO DIARIO. `guardar_serie` reemplaza la fecha
# repetida, no la acumula. Cuando el dia cierra, la corrida siguiente lee su
# archivo diario y **sobreescribe** lo que habian armado las porciones. Como
# los dos dan el mismo numero, el reemplazo no mueve la serie: es el cierre
# autoritativo del dia, no una correccion.
#
# QUE NO HACE. No juzga. El detector evalua AYER, asi que el dia parcial nunca
# entra en un juicio ni en la ventana de 28 dias que le sirve de base: entra en
# la serie y en el tablero, que es donde «tiempo real» significa algo.
MEMORIA = Path(__file__).resolve().parent.parent / "datos" / "gdelt_porciones.json"
PORCIONES_POR_CORRIDA = 40   # tope: una laguna larga no se come la corrida


def _sellos_del_dia(dia: date):
    """Los 96 sellos de un dia, en orden."""
    return [f"{dia.strftime('%Y%m%d')}{h:02d}{m:02d}00"
            for h in range(24) for m in (0, 15, 30, 45)]


def _memoria():
    try:
        return json.loads(MEMORIA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _dia_en_curso(nombres):
    """Suma las porciones nuevas de hoy y devuelve el recuento acumulado."""
    try:
        manifiesto = pedir(MANIFIESTO, segundos=60).decode("utf-8", "replace")
        ultima = next(l.split()[-1].rsplit("/", 1)[-1][:14]
                      for l in manifiesto.splitlines() if ".export.CSV.zip" in l)
    except Exception as e:  # noqa: BLE001
        print(f"Hechos: no se pudo leer el manifiesto de 15 minutos ({type(e).__name__}). "
              f"El dia en curso queda sin armar; los dias cerrados no se tocan.")
        return None

    hoy = ultima[:8]
    m = _memoria()
    if m.get("dia") != hoy:            # dia nuevo: la cuenta arranca de cero
        m = {"dia": hoy, "ultimo_sello": "", "protesta": {}, "violencia": {}}
    nuevos = [s for s in _sellos_del_dia(date(int(hoy[:4]), int(hoy[4:6]), int(hoy[6:8])))
              if m["ultimo_sello"] < s <= ultima][:PORCIONES_POR_CORRIDA]

    leidas = 0
    for sello in nuevos:
        try:
            p, v = _un_dia_url(PORCION.format(sello=sello), nombres)
        except Exception:  # noqa: BLE001 — una porcion que falta no tumba la corrida
            continue
        for iso, n in p.items():
            m["protesta"][iso] = m["protesta"].get(iso, 0) + n
        for iso, n in v.items():
            m["violencia"][iso] = m["violencia"].get(iso, 0) + n
        m["ultimo_sello"] = sello
        leidas += 1

    sellos = _sellos_del_dia(date(int(hoy[:4]), int(hoy[4:6]), int(hoy[6:8])))
    m["porciones_contadas"] = sellos.index(m["ultimo_sello"]) + 1 if m["ultimo_sello"] else 0
    m["medido"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    MEMORIA.parent.mkdir(parents=True, exist_ok=True)
    MEMORIA.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Hechos: dia en curso {hoy} — {leidas} porciones nuevas, "
          f"{m['porciones_contadas']} de 96 contadas (hasta {m['ultimo_sello']})")
    return m


def main():
    estados = padron()
    nombres = {_clave(p["nombre_en"]): p["iso3"] for p in estados}

    # MODO LIVIANO, PARA LA CORRIDA HORARIA.
    #
    # Con `SOLO_EN_CURSO=1` se saltean los dias cerrados y se arma unicamente
    # el dia de hoy con sus porciones de 15 minutos. Es lo que necesita la
    # capa horaria —que juzga y publica cada cuatro horas— y cuesta unos
    # segundos en vez de bajar diez archivos de 7 MB.
    #
    # Los dias cerrados los sigue trayendo la corrida diaria, que es la unica
    # que puede escribir el cierre autoritativo de un dia: el archivo diario de
    # un dia recien existe cuando ese dia termino.
    if os.environ.get("SOLO_EN_CURSO") == "1":
        curso = _dia_en_curso(nombres)
        if not curso:
            return
        hoy_iso = f"{curso['dia'][:4]}-{curso['dia'][4:6]}-{curso['dia'][6:8]}"
        prot = [(hoy_iso, e["iso3"], curso["protesta"].get(e["iso3"], 0)) for e in estados]
        viol = [(hoy_iso, e["iso3"], curso["violencia"].get(e["iso3"], 0)) for e in estados]
        guardar_serie("eventos_protesta", prot)
        guardar_serie("eventos_violencia", viol)
        print(f"Hechos GDELT: modo liviano, solo el dia en curso ({hoy_iso})")
        return

    arranque = time.time()
    hoy = date.today()
    # el archivo del día en curso todavía no está cerrado: se empieza por ayer
    dias = [hoy - timedelta(days=k) for k in range(1, dias_atras() + 1)]
    prot, viol, fallados, sin_tiempo = [], [], 0, 0
    for dia in dias:
        if time.time() - arranque > MINUTOS * 60:
            sin_tiempo += 1
            continue
        try:
            p, v = _un_dia(dia, nombres)
        except Exception:  # noqa: BLE001 — un día que falta no tumba la corrida
            fallados += 1
            continue
        for e in estados:  # los ceros también son dato
            prot.append((dia.isoformat(), e["iso3"], p.get(e["iso3"], 0)))
            viol.append((dia.isoformat(), e["iso3"], v.get(e["iso3"], 0)))
        if len(prot) > 3000:  # se guarda de a poco
            guardar_serie("eventos_protesta", prot)
            guardar_serie("eventos_violencia", viol)
            prot, viol = [], []
    # El dia en curso, armado con sus porciones de 15 minutos. Va DESPUES de
    # los dias cerrados: si el archivo diario de hoy ya existiera —no existe,
    # pero el orden lo garantiza igual—, el parcial no lo pisaria.
    curso = _dia_en_curso(nombres)
    if curso:
        hoy_iso = f"{curso['dia'][:4]}-{curso['dia'][4:6]}-{curso['dia'][6:8]}"
        for e in estados:   # los ceros tambien son dato
            prot.append((hoy_iso, e["iso3"], curso["protesta"].get(e["iso3"], 0)))
            viol.append((hoy_iso, e["iso3"], curso["violencia"].get(e["iso3"], 0)))

    guardar_serie("eventos_protesta", prot)
    guardar_serie("eventos_violencia", viol)
    print(f"Hechos GDELT: {len(dias) - fallados - sin_tiempo} días cerrados leídos, "
          f"{fallados} sin archivo, {sin_tiempo} sin tiempo")


if __name__ == "__main__":
    main()
