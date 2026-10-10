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
import re
import time
import unicodedata
import zipfile
from datetime import date, timedelta

from comun import dias_atras, guardar_serie, padron, pedir

URL = "http://data.gdeltproject.org/events/{fecha}.export.CSV.zip"
PROTESTA = ("14",)
VIOLENCIA = ("18", "19", "20")
MINUTOS = 70  # presupuesto de tiempo del colector


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
    crudo = pedir(URL.format(fecha=dia.strftime("%Y%m%d")), segundos=120, intentos=2, espera=15)
    z = zipfile.ZipFile(io.BytesIO(crudo))
    texto = io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8", errors="replace")
    prot, viol = {}, {}
    for f in csv.reader(texto, delimiter="\t"):
        if len(f) < 56:
            continue
        iso = nombres.get(_clave((f[50] or "").split(", ")[-1]))
        if not iso:
            continue
        raiz = (f[28] or "")[:2]
        if raiz in PROTESTA:
            prot[iso] = prot.get(iso, 0) + 1
        elif raiz in VIOLENCIA:
            viol[iso] = viol.get(iso, 0) + 1
    return prot, viol


def main():
    estados = padron()
    nombres = {_clave(p["nombre_en"]): p["iso3"] for p in estados}
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
    guardar_serie("eventos_protesta", prot)
    guardar_serie("eventos_violencia", viol)
    print(f"Hechos GDELT: {len(dias) - fallados - sin_tiempo} días leídos, "
          f"{fallados} sin archivo, {sin_tiempo} sin tiempo")


if __name__ == "__main__":
    main()
