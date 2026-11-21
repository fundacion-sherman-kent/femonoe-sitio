# -*- coding: utf-8 -*-
"""Control de frescura: ninguna serie escribe filas sobre lo que no ve.

**Por qué existe.** El 22/10/2026 se descubrió que las tres series de ACLED no
tenían un solo valor distinto de cero desde el 15 de septiembre de 2025 —402
días— mientras el colector informaba «66 semanas-país» como éxito y el archivo
seguía creciendo. La licencia de la Fundación sólo deja ver hechos de doce meses
de antigüedad; la API contestaba `count: 0, success: true` y el colector
escribía ese vacío como un cero por semana y por Estado.

**La falla de fondo no es de ACLED, es de la casa.** Un cero es una lectura, no
una ausencia: el detector lo compara contra una mediana de ceros, nunca marca
nada, y una ola real se lee como calma. No había ningún control capaz de
distinguir «no pasó nada» de «no pregunté». Este control es ése, y vale para las
veinte series, no para la que ya falló.

**Qué mira.** Dos cosas distintas que se confunden fácil:

  *rezago*      cuántos días hace del último valor distinto de cero.
  *escribe y
   no ve*       que haya filas MÁS NUEVAS que ese último valor. Eso es lo
                grave: la serie afirma sobre días que la fuente no contestó.

**Por qué no tumba la corrida.** Un control que frena la publicación por una
condición ya conocida y declarada deja a la plataforma sin salir todos los días,
y a los quince días nadie lo mira. Así que falla en rojo —sale con error— sólo
cuando una serie **empeora respecto de la última medición**: ahí hay novedad y
alguien tiene que verla. Lo ya sabido se publica en el estado de fuentes, a la
vista, sin frenar nada. Es la regla de la casa: lo que no falla solo en rojo no
se sostiene, pero el rojo tiene que querer decir algo.

**Por qué sólo «escribe y no ve» es rojo, y las otras dos candidatas no.**
Probadas las tres el 22/10/2026 contra las veinte series:

  *todo en cero*      No sirve de rojo. `cloudflare_deliberados` y
                      `redes_coordinado` están enteras en cero y las dos son
                      correctas: cuentan hechos raros que no ocurrieron —un
                      apagón dispuesto por un gobierno, una difusión coordinada
                      con la definición estricta del 27/9—. Un cero ahí es la
                      respuesta, no la falta de respuesta. Queda en amarillo y
                      exige motivo escrito.
  *última fila vieja* Tampoco. Las dos series de Cloudflare terminan el 13/10 y
                      el colector corrió hoy: dicen la fecha del último corte,
                      porque un corte es un hecho esparcido y no una medición
                      diaria. Habría acusado a un colector sano.
  *escribe y no ve*   Ésta sí. Rellenar con ceros fechas posteriores a lo último
                      que la fuente contestó es la firma exacta de ACLED, y
                      ninguna serie sana la tiene: las sanas o traen dato, o no
                      traen fila.

Para correrlo:  python control_frescura.py
"""
import csv
import io
import json
import os
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SERIES = RAIZ / "datos" / "series"
REGISTRO = RAIZ / "datos" / "frescura.json"

# Cuántos días de rezago se toleran antes de nombrar a una serie. Generoso a
# propósito: ACLED estuvo 402 días y las series sanas andan en 0 a 9.
DIAS_DE_TOLERANCIA = 45

# Series a las que un rezago largo no les es defecto, con el motivo. Una
# excepción sin motivo escrito es una excepción que nadie puede impugnar.
DECLARADAS = {
    "acled_protesta": "licencia con muro de 12 meses — da la tasa base, no la señal",
    "acled_violencia": "licencia con muro de 12 meses — da la tasa base, no la señal",
    "acled_muertes": "licencia con muro de 12 meses — da la tasa base, no la señal",
    "cloudflare_deliberados": "cuenta apagones dispuestos por un gobierno: en cero "
                              "porque no hubo, y uno solo abre alerta",
    "redes_coordinado": "definición estricta del 27/9 (texto propio de 40 caracteres y "
                        "fuentes independientes): pasó de 52 marcas a 1",
}


def _mirar(archivo: Path) -> dict | None:
    try:
        filas = list(csv.DictReader(io.open(archivo, encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return None
    if not filas or "fecha" not in (filas[0] or {}):
        return None
    ultima = max(r["fecha"] for r in filas)
    no_nulas = []
    for r in filas:
        try:
            if float((r.get("valor") or "").strip()) != 0.0:
                no_nulas.append(r["fecha"])
        except ValueError:
            pass
    ultimo_dato = max(no_nulas) if no_nulas else None
    rezago = None
    if ultimo_dato:
        try:
            rezago = (date.today() - date.fromisoformat(ultimo_dato[:10])).days
        except ValueError:
            pass
    return {"filas": len(filas), "ultima_fila": ultima, "ultimo_dato": ultimo_dato,
            "rezago": rezago, "no_nulas": len(no_nulas),
            # Lo grave: afirma sobre días posteriores a lo último que vio.
            "escribe_y_no_ve": bool(ultimo_dato and ultima > ultimo_dato
                                    and (rezago or 0) > DIAS_DE_TOLERANCIA),
            "todo_en_cero": ultimo_dato is None}


def main() -> int:
    if not SERIES.exists():
        print("Control de frescura: todavía no hay series.")
        return 0
    previo = {}
    if REGISTRO.exists():
        try:
            previo = json.loads(REGISTRO.read_text(encoding="utf-8")).get("series", {})
        except ValueError:
            previo = {}

    ahora, amarillas, empeoraron = {}, [], []
    for n in sorted(os.listdir(SERIES)):
        if not n.endswith(".csv"):
            continue
        d = _mirar(SERIES / n)
        if d is None:
            continue
        serie = n[:-4]
        ahora[serie] = d
        if d["todo_en_cero"] or d["escribe_y_no_ve"]:
            amarillas.append(serie)
        # Rojo sólo la firma de ACLED, sólo si no está declarada, y sólo si es
        # novedad: la primera corrida fija la línea de base y nunca falla, que
        # si no el control nace en rojo y nace desacreditado.
        if not previo or serie in DECLARADAS or not d["escribe_y_no_ve"]:
            continue
        antes = previo.get(serie) or {}
        if (not antes.get("escribe_y_no_ve")
                or (d["rezago"] or 0) > (antes.get("rezago") or 0) + 7):
            empeoraron.append(serie)

    print(f"  {'serie':30s} {'filas':>6s} {'últ. fila':>11s} {'últ. dato':>11s} {'rezago':>8s}")
    print("  " + "-" * 74)
    for serie, d in sorted(ahora.items(), key=lambda x: -(x[1]["rezago"] or 10 ** 6)):
        marca = ""
        if d["todo_en_cero"]:
            marca = "  <- TODO EN CERO"
        elif d["escribe_y_no_ve"]:
            marca = "  <- escribe y no ve"
        if serie in DECLARADAS and marca:
            marca += f" (declarado: {DECLARADAS[serie]})"
        print(f"  {serie:30s} {d['filas']:6d} {d['ultima_fila']:>11s} "
              f"{str(d['ultimo_dato']):>11s} "
              f"{((str(d['rezago']) + ' d') if d['rezago'] is not None else '-'):>8s}{marca}")

    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text(json.dumps(
        {"medido": date.today().isoformat(), "tolerancia_dias": DIAS_DE_TOLERANCIA,
         "declaradas": DECLARADAS, "series": ahora},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    sin_motivo = [s for s in amarillas if s not in DECLARADAS]
    print(f"\n  {len(ahora)} series · {len(amarillas)} en amarillo"
          f" · {len(amarillas) - len(sin_motivo)} con motivo declarado")
    if sin_motivo:
        print("  en amarillo SIN motivo escrito, y una excepción sin motivo no se "
              f"puede impugnar: {', '.join(sin_motivo)}")
    if empeoraron:
        print("\n  EMPEORÓ desde la última medición, y eso es novedad:")
        for s in empeoraron:
            d = ahora[s]
            print(f"    · {s}: {d['filas']} filas escritas, último dato "
                  f"{d['ultimo_dato']}, rezago {d['rezago']} días")
        print("\n  Una serie que escribe sobre días que la fuente no contestó no mide: "
              "\n  afirma. Revisar el colector antes de que el detector lo lea como calma.")
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
