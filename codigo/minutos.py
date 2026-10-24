# -*- coding: utf-8 -*-
"""Cuánto está gastando el robot, y aviso antes de quedarse sin nafta.

**Por qué existe.** La cuota gratuita de GitHub son **2.000 minutos por mes**, y
cuando se acaban no se degrada nada: **se para todo** —la edición diaria, el
buzón y la publicación del sitio—. Hasta el 22/10/2026 nadie los medía, así que
el modo de falla era el peor posible: la plataforma se congela, el sitio sigue
en línea mostrando lo último que alcanzó a publicar, y la casa se entera cuando
alguien mira.

**Por qué se calcula y no se consulta.** GitHub tiene un campo `billable` por
corrida y **para este depósito informa cero en todas**: sólo cuenta el excedente
sobre la cuota, no el consumo. Medido el 22/10/2026 sobre seis corridas
terminadas. Así que el consumo se calcula con la regla que GitHub documenta:
**se redondea hacia arriba al minuto entero cada TRABAJO**, no cada corrida.

Esa distinción no es un detalle. La corrida diaria tiene dos trabajos, `hechos`
de 24 segundos y `fuentes` de 379: factura **8 minutos** —1 + 7—, mientras que
su reloj de pared dice 3. Contar por corrida subestima, y subestimar el
presupuesto es la manera de quedarse sin él.

**Por qué lleva libro.** Pedirle a GitHub los trabajos de cada corrida del mes
son cientos de pedidos. El libro guarda lo ya contado, así que cada día se
preguntan sólo las corridas nuevas: unas veinticinco.

**Qué NO sabe.** El ciclo de facturación de GitHub puede no empezar el día 1.
Acá se cuenta por mes calendario y se declara, que es mejor que suponer.

Para correrlo:  python minutos.py
"""
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
LIBRO = RAIZ / "datos" / "minutos.json"
DEPOSITO = os.environ.get("GITHUB_REPOSITORY", "fundacion-sherman-kent/femonoe")
API = "https://api.github.com"

# La cuota del plan Free, en minutos por mes.
CUOTA = 2000
# Cuánto de la cuota hay que llevar consumido para que avise.
AVISA_CONSUMIDO = 0.70
# O cuánto tiene que proyectar el ritmo actual a fin de mes.
AVISA_PROYECCION = 0.90

# Cuántas corridas nuevas se cuentan como mucho en una pasada. Cada una es un
# pedido a la API, y la primera pasada de un mes tiene que contar el mes entero
# —cientos—, que no entra en el tope de tiempo del paso. Con este límite la
# primera pasada cuenta un pedazo, lo guarda en el libro, y las siguientes
# terminan el trabajo: el libro se pone al día solo en unos días y ninguna
# corrida se pasa de tiempo. El total que informa mientras tanto es **lo
# contado**, y se dice cuántas quedan, para que nadie lo lea como el total real.
TOPE_POR_PASADA = 150


def _pedir(ruta):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("minutos: falta GH_TOKEN o GITHUB_TOKEN para leer la API")
    req = urllib.request.Request(API + ruta, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "FEMONOE/1.0 (Fundacion Sherman Kent; medidor de minutos)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _minutos_de(run_id):
    """Los minutos que factura una corrida: cada TRABAJO redondeado hacia arriba."""
    d = _pedir(f"/repos/{DEPOSITO}/actions/runs/{run_id}/jobs?per_page=100")
    total = 0
    for j in d.get("jobs", []):
        a, b = j.get("started_at"), j.get("completed_at")
        if not (a and b):
            continue
        seg = (datetime.fromisoformat(b.replace("Z", "+00:00"))
               - datetime.fromisoformat(a.replace("Z", "+00:00"))).total_seconds()
        # Un trabajo salteado dura cero y no factura; uno que corrió, mínimo 1.
        if seg <= 0 and j.get("conclusion") == "skipped":
            continue
        total += max(1, math.ceil(seg / 60))
    return total


def _libro():
    if LIBRO.exists():
        try:
            return json.loads(LIBRO.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"corridas": {}}


def main():
    hoy = datetime.now(timezone.utc)
    mes = hoy.strftime("%Y-%m")
    libro = _libro()
    ya = libro.setdefault("corridas", {})

    nuevas, faltan, pagina = 0, 0, 1
    while pagina <= 10:                      # 1.000 corridas, de sobra para un mes
        d = _pedir(f"/repos/{DEPOSITO}/actions/runs"
                   f"?per_page=100&page={pagina}&created=>={mes}-01")
        corridas = d.get("workflow_runs") or []
        if not corridas:
            break
        for c in corridas:
            cid = str(c["id"])
            if cid in ya or c.get("status") != "completed":
                continue
            if nuevas >= TOPE_POR_PASADA:
                faltan += 1
                continue
            try:
                ya[cid] = {"mes": str(c.get("created_at"))[:7],
                           "dia": str(c.get("created_at"))[:10],
                           "flujo": c.get("name") or "?",
                           "minutos": _minutos_de(cid)}
                nuevas += 1
            except urllib.error.HTTPError as e:
                print(f"  no se pudo contar la corrida {cid}: HTTP {e.code}")
        if len(corridas) < 100:
            break
        pagina += 1

    del_mes = {k: v for k, v in ya.items() if v.get("mes") == mes}
    total = sum(v["minutos"] for v in del_mes.values())
    dia = hoy.day
    dias_del_mes = 31 if hoy.month in (1, 3, 5, 7, 8, 10, 12) else (
        30 if hoy.month != 2 else 28 + (hoy.year % 4 == 0))
    # **La proyección se hace con los últimos días y no con el promedio del
    # mes.** El promedio arrastra cadencias viejas: en octubre de 2026 mezcla el
    # período de una corrida por hora con el de cada dos, y proyecta un pasado
    # que ya no corre. Se usan los últimos siete días completos —sin el de hoy,
    # que está a medias y siempre parece barato—.
    por_dia = {}
    for v in del_mes.values():
        d = v.get("dia")
        if d:
            por_dia[d] = por_dia.get(d, 0) + v["minutos"]
    completos = sorted(d for d in por_dia if d != hoy.date().isoformat())
    recientes = completos[-7:]
    ritmo = (sum(por_dia[d] for d in recientes) / len(recientes)) if recientes else 0
    quedan = dias_del_mes - dia
    proyeccion = total + ritmo * quedan if ritmo else total / max(dia, 1) * dias_del_mes

    por_flujo = {}
    for v in del_mes.values():
        f = por_flujo.setdefault(v["flujo"], [0, 0])
        f[0] += 1
        f[1] += v["minutos"]

    print(f"Minutos de {mes} · {len(del_mes)} corridas contadas "
          f"({nuevas} nuevas en esta pasada)")
    if faltan:
        print(f"  OJO: quedan {faltan} corridas sin contar, por el tope de "
              f"{TOPE_POR_PASADA} por pasada. Lo de abajo es LO CONTADO, no el "
              f"total del mes; se completa en las próximas corridas.")
    for f, (c, m) in sorted(por_flujo.items(), key=lambda x: -x[1][1]):
        print(f"  {f[:38]:38s} {c:4d} corridas {m:5d} min")
    print(f"  {'TOTAL':38s} {len(del_mes):4d} corridas {total:5d} min "
          f"de {CUOTA} ({total / CUOTA * 100:.0f} %)")
    if recientes:
        print(f"  consumo por día, los últimos siete completos:")
        for d in recientes:
            print(f"    {d}  {por_dia[d]:4d} min")
    print(f"  ritmo reciente: {ritmo:.1f} min/día (promedio del mes: "
          f"{total / max(dia, 1):.1f})")
    print(f"  proyección a fin de mes: {proyeccion:.0f} min "
          f"({proyeccion / CUOTA * 100:.0f} %) — lo gastado más {quedan} días "
          f"al ritmo reciente")
    print("  (el ciclo de facturación de GitHub puede no empezar el día 1; "
          "acá se cuenta por mes calendario)")

    libro["medido"] = hoy.isoformat(timespec="seconds")
    libro["resumen"] = {"mes": mes, "minutos": total, "cuota": CUOTA,
                        "sin_contar": faltan,
                        "proyeccion": round(proyeccion)}
    LIBRO.parent.mkdir(parents=True, exist_ok=True)
    LIBRO.write_text(json.dumps(libro, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8")

    apremia = (not faltan
               and (total >= CUOTA * AVISA_CONSUMIDO
                    or proyeccion >= CUOTA * AVISA_PROYECCION))
    if apremia:
        texto = "\n".join([
            "FEMÓNOE · los minutos del robot aprietan", "",
            f"Van {total} de {CUOTA} minutos del mes ({total / CUOTA * 100:.0f} %).",
            f"Al ritmo de los últimos días —{ritmo:.1f} por día— el mes cierra en "
            f"{proyeccion:.0f}.", "",
            "Si se acaban no se degrada nada: se para todo, la edición diaria y el "
            "buzón incluidos.", "",
            "La proyección usa los últimos siete días completos. Si la cadencia se "
            "cambió hace poco, esos días traen la cadencia vieja y la proyección "
            "exagera: se acomoda sola en una semana.", "",
            "Lo que más pesa:",
            *[f"  · {f}: {m} min en {c} corridas"
              for f, (c, m) in sorted(por_flujo.items(), key=lambda x: -x[1][1])[:3]],
            "",
            "La perilla de la cadencia es `CADA_CUANTAS_HORAS` en vigia/worker.js.",
        ])
        try:
            sys.path.insert(0, str(RAIZ))
            from aviso import _mandar
            _mandar(texto)
        except Exception as e:  # noqa: BLE001 — un aviso que falla no tumba la corrida
            print(f"  no se pudo avisar: {type(e).__name__}")
        print("  AVISO ENVIADO: los minutos aprietan")
    else:
        print("  holgado: no se avisa")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
