# -*- coding: utf-8 -*-
"""Arma el expediente de una alerta y dice cuánto va a costar analizarla.

**El problema.** Si los analistas leen el depósito por su cuenta y salen a buscar
en la web, el gasto es imprevisible y grande. **La solución es la de siempre en
esta casa: el trabajo pesado lo hace el robot.**

Este programa reúne, sin gastar un token, todo lo que los dos analistas y el
décimo hombre necesitan para juzgar una señal:

1. **La señal**, con sus códigos, valores y medianas.
2. **La serie de 90 días** y sus estadísticos, para no tener que recalcularlos.
3. **La tasa base**: cuántas veces ese país cruzó ese umbral antes, y qué pasó
   después. Es la pregunta que casi nadie hace.
4. **El calendario** del país en la ventana.
5. **La prensa del propio país**, de las fuentes que ya recolectamos: titulares
   de los últimos días, filtrados por el eje. **Esto es lo que evita que el
   analista tenga que navegar**, que es donde el gasto se dispara.
6. **Los antecedentes**: alertas anteriores de ese Estado y cómo terminaron.

Y antes de gastar nada, **dice cuánto pesa**: caracteres, tokens estimados y el
costo del ciclo completo.

  python expediente.py <id>              arma el expediente
  python expediente.py <id> --presupuesto  sólo dice cuánto costaría
"""
import csv
import json
import re
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SERIES = RAIZ / "datos" / "series"
MENSAJES = RAIZ / "datos" / "mensajes"
ALERTAS = RAIZ / "alertas"
# En español, un token cubre algo menos de cuatro caracteres. Es una estimación
# declarada, no una medición: sirve para decidir antes de gastar.
CHARS_POR_TOKEN = 3.7
TITULARES = 40
DIAS_PRENSA = 5


ES_ALERTA = re.compile(r"^\d{4}-\d{2}-\d{2}-[A-Z]{3}-[GSI]$")


def _serie(senal, iso3, hasta, dias):
    archivo = SERIES / f"{senal}.csv"
    if not archivo.exists():
        return []
    desde = hasta - timedelta(days=dias)
    valores = {}
    with archivo.open(encoding="utf-8") as fh:
        for fila in csv.DictReader(fh):
            if fila.get("iso3") != iso3:
                continue
            try:
                d = date.fromisoformat(fila["fecha"])
            except (ValueError, KeyError):
                continue
            if desde <= d <= hasta:
                valores[d] = float(fila["valor"] or 0)
    return [(desde + timedelta(days=k), valores.get(desde + timedelta(days=k), 0.0))
            for k in range(dias + 1)]


def _tasa_base(senal, iso3, hasta, umbral):
    """De las veces que este país cruzó este valor, ¿cuántas volvieron a cruzarlo
    dentro de los 21 días siguientes? **No es la probabilidad del hecho
    anunciado** —eso no lo sabe nadie todavía— sino la persistencia de la señal,
    que es lo que sí se puede medir con lo que hay. Se declara así."""
    serie = _serie(senal, iso3, hasta, 400)
    if not serie:
        return None
    cruces = [f for f, v in serie if v >= umbral]
    if len(cruces) < 2:
        return {"cruces": len(cruces), "persistieron": 0, "nota": "muestra corta"}
    persistieron = sum(1 for f in cruces[:-1]
                       if any(0 < (g - f).days <= 21 for g in cruces if g > f))
    return {"cruces": len(cruces), "persistieron": persistieron,
            "proporcion": round(persistieron / max(len(cruces) - 1, 1), 2)}


def _prensa(iso3, eje, hasta):
    """Titulares del propio país, de las fuentes del padrón. Sin esto el analista
    tendría que navegar, y ahí es donde el gasto se vuelve imprevisible."""
    try:
        from colectores.redes import EJES
        patron = EJES.get(eje)
    except Exception:                                  # noqa: BLE001
        patron = None
    vistos, salida = set(), []
    for k in range(DIAS_PRENSA):
        archivo = MENSAJES / f"{hasta - timedelta(days=k)}.jsonl"
        if not archivo.exists():
            continue
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            try:
                m = json.loads(linea)
            except ValueError:
                continue
            if (m.get("iso3_fuente") or m.get("iso3")) != iso3:
                continue
            texto = re.sub(r"\s+", " ", (m.get("texto") or "")).strip()
            if patron and not patron.search(texto):
                continue
            clave = texto[:60].lower()
            if clave in vistos or len(texto) < 25:
                continue
            vistos.add(clave)
            salida.append({"fecha": (m.get("fecha") or "")[:10],
                           "titular": texto[:180],
                           "fuente": (m.get("cuenta") or m.get("fuente") or "")[:40]})
            if len(salida) >= TITULARES:
                return salida
    return salida


def armar(ident):
    a = json.loads((ALERTAS / f"{ident}.json").read_text(encoding="utf-8"))
    iso3, eje = a["iso3"], a["eje"]
    dia = date.fromisoformat(a["senal"]["fecha"])
    L = [f"# Expediente · {a['pais']} · {eje}", "",
         f"Señal del {dia}. Umbrales {a['senal']['umbrales_version']}. "
         f"Familias que la sostienen: {', '.join(a['senal']['familias'])}"
         + (" — **fuente única**" if a["senal"]["fuente_unica"] else "")
         + (" — **hecho duro**" if a["senal"]["hecho_duro"] else "") + ".", "",
         "## 1 · Lo que disparó la señal", ""]
    for x in a["senal"]["detalle"]:
        L.append(f"- `{x['senal']}` ({x['familia']}): valor {x.get('valor')}, "
                 f"mediana {x.get('mediana')}. {x.get('detalle') or ''}")

    L += ["", "## 2 · La serie, ya medida", ""]
    for x in a["senal"]["detalle"]:
        serie = _serie(x["senal"], iso3, dia, 90)
        if not serie:
            continue
        valores = [v for _, v in serie]
        ultimos = [f"{v:.0f}" for _, v in serie[-30:]]
        mediana = statistics.median(valores)
        mad = statistics.median([abs(v - mediana) for v in valores])
        L += [f"**{x['senal']}** · 90 días: mediana {mediana:.1f}, desviación mediana "
              f"{mad:.1f}, máximo {max(valores):.0f}.",
              f"Últimos 30 días: {' '.join(ultimos)}", ""]
        base = _tasa_base(x["senal"], iso3, dia, float(x.get("valor") or 0))
        if base:
            L.append(f"Tasa base de persistencia: la señal cruzó este valor "
                     f"{base['cruces']} veces en 400 días y volvió a cruzarlo dentro de "
                     f"los 21 días siguientes en {base['persistieron']} de ellas"
                     + (f" ({base['proporcion']:.0%})" if base.get("proporcion") else "")
                     + ". **Mide persistencia de la señal, no probabilidad del hecho.**")
        L.append("")

    calendario = RAIZ / "calendario.json"
    if calendario.exists():
        cerca = [e for e in json.loads(calendario.read_text(encoding="utf-8"))
                 if e["iso3"] == iso3 and abs((date.fromisoformat(e["fecha"]) - dia).days) <= 60]
        L += ["## 3 · Calendario institucional en la ventana", ""]
        L += ([f"- {e['fecha']} · {e['titulo']} "
               f"({'confirmada' if e.get('confirmado') else 'sin confirmar'})" for e in cerca]
              or ["- Sin fechas institucionales en ±60 días."])

    contexto = RAIZ / "datos" / "contexto.json"
    if contexto.exists():
        hechos = [e for e in json.loads(contexto.read_text(encoding="utf-8"))
                  if e.get("iso3") == iso3]
        if hechos:
            L += ["", "## 4 · Contexto de desastres", ""]
            L += [f"- {e['fecha']} · {e.get('nivel', '')} · {e.get('titulo', '')[:110]}"
                  for e in hechos[:5]]

    prensa = _prensa(iso3, eje, dia)
    L += ["", f"## 5 · Prensa del país, {DIAS_PRENSA} días, filtrada por el eje", ""]
    L += ([f"- {t['fecha']} · {t['titular']}" for t in prensa]
          or ["- Sin titulares del país que crucen el eje en la ventana. "
              "**La ausencia de cobertura también es un dato.**"])

    previas = []
    for f in ALERTAS.glob("*.json"):
        if not ES_ALERTA.match(f.stem):
            continue
        otra = json.loads(f.read_text(encoding="utf-8"))
        if otra["iso3"] == iso3 and otra["id"] != ident:
            previas.append(otra)
    L += ["", "## 6 · Antecedentes de este Estado", ""]
    L += ([f"- {o['nace']} · {o['eje']} · {o['estado']}"
           + (f" · {o['resultado']['leyenda']}" if o.get("resultado") else "")
           for o in previas] or ["- Sin alertas anteriores."])

    L += ["", "---", "",
          "Armado por el robot, sin gastar tokens. Los analistas trabajan sobre esto: "
          "no necesitan recalcular la serie ni salir a navegar para lo básico."]
    return "\n".join(L) + "\n"


def presupuesto(texto):
    expediente = len(texto) / CHARS_POR_TOKEN
    instruccion = 1500          # lo que pesa la ficha de cada agente
    salida = 700                # el juicio que cada uno escribe
    partes = {
        "analista de indicadores": expediente + instruccion + salida,
        "analista de contexto": expediente + instruccion + salida,
        "décimo hombre": expediente + instruccion + salida * 2,
        "consolidación y tarjeta": expediente / 2 + salida,
    }
    return partes


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ident = sys.argv[1]
    texto = armar(ident)
    partes = presupuesto(texto)
    total = sum(partes.values())
    print(f"Expediente de {ident}: {len(texto):,} caracteres · "
          f"{len(texto) / CHARS_POR_TOKEN:,.0f} tokens estimados")
    print("\nCosto estimado del ciclo completo, por agente:")
    for quien, t in partes.items():
        print(f"  {quien:26s} {t:8,.0f} tokens")
    print(f"  {'TOTAL':26s} {total:8,.0f} tokens estimados")
    if "--presupuesto" in sys.argv:
        return
    salida = ALERTAS / f"{ident}-expediente.md"
    salida.write_text(texto, encoding="utf-8")
    print(f"\nEscrito: {salida}")


if __name__ == "__main__":
    main()
