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
CUENTA = DEPOSITO.split("/")[0]
API = "https://api.github.com"

# La cuota del plan Free, en minutos por mes.
CUOTA = 2000
# Cuánto de la cuota hay que llevar consumido para que avise.
AVISA_CONSUMIDO = 0.70
# O cuánto tiene que proyectar el ritmo actual a fin de mes.
AVISA_PROYECCION = 0.90

# **Lo que gastan los OTROS depósitos de la casa, que comparten esta cuota.**
#
# La cuota de 2.000 minutos es **de la cuenta**, no del depósito, y la casa
# tiene otros dos depósitos privados con robots propios: `vigilancia-fusk` y
# `ysyry-registro`. El token con que corre este medidor sólo puede leer su
# propio depósito, así que no los puede contar: se declara lo medido.
#
# Medido el 3/11/2026 sobre octubre, trabajo por trabajo, que es como GitHub
# factura: `vigilancia-fusk` 66 corridas y 212 minutos; `ysyry-registro` 287
# corridas y 337. **549 minutos entre los dos.**
#
# Con eso, octubre cerró en **1.989 de 2.000 minutos: el 99,4 %**. No es una
# estimación que se acerca: es el techo tocado casi exactamente, y confirma
# que la caida fue la cuota y no otra cosa.
#
# **Por qué esto importa y no es un detalle.** Del 28 al 31 de octubre de 2026
# la plataforma estuvo caída entera: los trabajos fallaban en dos segundos y sin
# un solo paso, que es GitHub negándose a correrlos, y se recuperó sola el 1 de
# noviembre cuando el mes se reinició. Este medidor marcaba 1.440 de 2.000 —el
# 72 %— mientras la cuenta iba por 2.040. **Contaba bien el número equivocado.**
#
# Se vuelve a medir cada vez que cambie el ritmo de esos robots.
# CUÁNTO SE LE PERDONA A UN DÍA PARA SEGUIR SIENDO DE LA MISMA CADENCIA.
#
# Una corrida que falla o que GitHub saltea deja el día con una menos. Un día
# en que la cadencia cambió al mediodía queda con un número intermedio, y ése
# SÍ tiene que quedar afuera porque no corre ninguna de las dos.
TOLERANCIA_CORRIDAS = 1
RESERVA_OTROS_DEPOSITOS = 549
MEDIDA_EL = "2026-11-03"

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


def _minutos_de(run_id, deposito=None):
    """Los minutos que factura una corrida: cada TRABAJO redondeado hacia arriba."""
    d = _pedir(f"/repos/{deposito or DEPOSITO}/actions/runs/{run_id}/jobs?per_page=100")
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


def _ventana_de_la_cadencia(del_mes, dias_del_mes, hoy_iso):
    """Los días que corren la cadencia de hoy, incluido hoy si ya la cumplió.

    **Por qué se deduce y no se declara.** El 4/11/2026 el medidor proyectó
    2.411 minutos —el 121 %— porque promedió los tres únicos días completos del
    mes, que eran los tres de la cadencia vieja; la de cuatro horas había
    empezado el día anterior. Sobre ese número la Oficina le dijo a la
    dirección que una mejora no cabía en noviembre. **Cabía: 1.683, el 84 %.**

    El primer arreglo fue una fecha escrita a mano. La dirección lo corrigió el
    mismo día: *«siempre actualizá y publicá; recordá que debe ser automático
    para no quedar atrasado»*. Una fecha a mano es justamente lo que se queda
    atrasado: la próxima vez que cambie la cadencia, si nadie la toca, el
    medidor vuelve a proyectar el período equivocado y en silencio.

    **La cadencia está en la hora de las corridas.** El espacio entre dos
    corridas horarias consecutivas dice cada cuántas horas corre el robot, y
    eso se lee **hoy mismo**, sin esperar a que el día cierre. Con la cadencia
    en la mano, un día está terminado cuando **ya juntó las corridas que le
    tocaban** —24 dividido la cadencia—, y no cuando cambia la fecha: esperar
    el cambio de fecha es lo que dejaba al medidor un día atrás justo el día en
    que más importaba.

    Se perdona una corrida de diferencia, por las que fallan. El día en que la
    cadencia cambió al mediodía queda afuera solo, porque su cuenta no es ni
    una ni la otra.
    """
    horas, cuenta = {}, {}
    for v in del_mes.values():
        if "horaria" not in v["flujo"] or not v.get("dia"):
            continue
        cuenta[v["dia"]] = cuenta.get(v["dia"], 0) + 1
        if v.get("hora"):
            horas.setdefault(v["dia"], []).append(v["hora"])

    # El espacio típico entre las ÚLTIMAS corridas, no entre las de los
    # últimos días. Promediar días enteros hace que el día viejo gane por
    # cantidad: el 4/11 tenía cinco espacios de cuatro horas y el 3/11 once de
    # dos, y la mediana de los dieciséis daba dos horas — justo la cadencia que
    # se acababa de cambiar. Se miran las últimas CORRIDAS, que es donde está
    # la cadencia de ahora.
    ULTIMAS = 7
    marcas = sorted((d, h) for d in horas for h in horas[d])[-ULTIMAS:]
    minutos_de = [int(h[:2]) * 60 + int(h[3:]) for _, h in marcas]
    espacios = [(b - a) % 1440 for (da, a), (db, b) in zip(
        zip([d for d, _ in marcas], minutos_de),
        zip([d for d, _ in marcas][1:], minutos_de[1:]))]
    espacios = [e for e in espacios if e > 0]
    if not espacios:
        return [], "sin hora anotada todavía"
    espacios.sort()
    cadencia = max(1, round(espacios[len(espacios) // 2] / 60))
    esperadas = max(1, round(24 / cadencia))

    # Terminados: los que juntaron sus corridas. Hoy entra si ya las juntó.
    terminados = [d for d in sorted(cuenta)
                  if cuenta[d] >= esperadas - TOLERANCIA_CORRIDAS
                  and cuenta[d] <= esperadas + TOLERANCIA_CORRIDAS
                  and (d != hoy_iso or cuenta[d] >= esperadas)]
    ventana = []
    for d in reversed(terminados):
        if d in dias_del_mes:
            ventana.append(d)
    return sorted(ventana), f"cada {cadencia} h, {esperadas} corridas por día"


def _depositos():
    """Todos los depósitos privados de la cuenta, porque la cuota es de la cuenta.

    **Por qué existe, y costó cuatro días de caída.** Este medidor contaba sólo
    FEMÓNOE. Del 28 al 31 de octubre de 2026 la plataforma estuvo **caída
    entera** —los trabajos fallaban en dos segundos y sin un solo paso, que es
    GitHub negándose a correrlos— y se recuperó sola el 1 de noviembre, cuando
    el mes se reinició. Medido después: FEMÓNOE gastó 1.440 minutos y los otros
    dos depósitos privados de la casa —`vigilancia-fusk` y `ysyry-registro`—
    al menos 600 más. **Total 2.040 contra una cuota de 2.000.**

    El medidor marcaba 72 % y la cuenta estaba en el 102 %. Contaba bien el
    número equivocado.

    Los depósitos **públicos** no se cuentan: GitHub no los factura.
    """
    # La cuenta puede ser una persona o una organización, y cada una tiene su
    # camino en la API. Se prueban los dos antes de darse por vencido: dar por
    # vencido acá significa volver a contar un solo depósito, que es el error
    # que costó la caída.
    for ruta in (f"/orgs/{CUENTA}/repos?per_page=100&type=private",
                 f"/users/{CUENTA}/repos?per_page=100&type=owner"):
        try:
            d = _pedir(ruta)
        except urllib.error.HTTPError:
            continue
        privados = [r["full_name"] for r in d if r.get("private")]
        if privados:
            return privados
    print("  OJO: no se pudo listar los depósitos de la cuenta; se cuenta sólo "
          f"{DEPOSITO}, y la cuota es de la CUENTA. El total de abajo es un piso.")
    return [DEPOSITO]


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

    nuevas, faltan = 0, 0
    for deposito in _depositos():
      pagina = 1
      while pagina <= 10:                    # 1.000 corridas, de sobra para un mes
        d = _pedir(f"/repos/{deposito}/actions/runs"
                   f"?per_page=100&page={pagina}&created=>={mes}-01")
        corridas = d.get("workflow_runs") or []
        if not corridas:
            break
        for c in corridas:
            cid = str(c["id"])
            if cid in ya:
                # Se cura solo: las corridas anotadas antes del 5/11/2026 no
                # tienen hora, y sin hora no se puede leer la cadencia. El
                # listado ya está en la mano, así que se completa de paso en
                # vez de pedir que alguien rellene nada.
                if not ya[cid].get("hora") and c.get("created_at"):
                    ya[cid]["hora"] = str(c["created_at"])[11:16]
                continue
            if c.get("status") != "completed":
                continue
            if nuevas >= TOPE_POR_PASADA:
                faltan += 1
                continue
            try:
                # La HORA se guarda porque de ahí sale la cadencia: el
                # espacio entre dos corridas consecutivas dice cada cuántas
                # horas corre el robot, y eso se puede leer sin esperar a que
                # el día termine. Las corridas anotadas antes del 5/11/2026 no
                # la tienen, y la deducción las saltea sin fallar.
                ya[cid] = {"mes": str(c.get("created_at"))[:7],
                           "dia": str(c.get("created_at"))[:10],
                           "hora": str(c.get("created_at"))[11:16],
                           "flujo": c.get("name") or "?",
                           "deposito": deposito.split("/")[-1],
                           "minutos": _minutos_de(cid, deposito)}
                nuevas += 1
            except urllib.error.HTTPError as e:
                print(f"  no se pudo contar la corrida {cid}: HTTP {e.code}")
        if len(corridas) < 100:
            break
        pagina += 1

    del_mes = {k: v for k, v in ya.items() if v.get("mes") == mes}
    propio = sum(v["minutos"] for v in del_mes.values())
    # El total que se compara con la cuota es el de la CUENTA, no el propio.
    total = propio + RESERVA_OTROS_DEPOSITOS
    dia = hoy.day
    dias_del_mes = 31 if hoy.month in (1, 3, 5, 7, 8, 10, 12) else (
        30 if hoy.month != 2 else 28 + (hoy.year % 4 == 0))
    # **La proyección se hace con los días que corren la cadencia de hoy.**
    #
    # El promedio del mes arrastra cadencias viejas: en octubre de 2026 mezcla
    # el período de una corrida por hora con el de cada dos, y proyecta un
    # pasado que ya no corre. Por eso se usaban los últimos siete días
    # completos, sin el de hoy, que está a medias y siempre parece barato.
    #
    # **Siete no alcanzaba, y la casa pagó el error el 4/11/2026.** La cadencia
    # bajó a cuatro horas el 3/11. Al día siguiente los siete días completos
    # eran tres, los tres de la cadencia vieja, y el medidor proyectó **2.411
    # minutos, el 121 %**. Con eso la Oficina le dijo a la dirección que una
    # mejora de 180 minutos al mes «no cabe en noviembre». El primer día
    # completo con la cadencia nueva dio **35 minutos contra 63**, y la
    # proyección real es **1.683, el 84 %**. El medidor no se equivocó en la
    # cuenta: midió el período equivocado, que es el mismo modo de falla que
    # le costó a la casa cuatro días de caída en octubre.
    #
    # El aviso ya advertía por escrito que «si la cadencia se cambió hace poco
    # la proyección sobra». **No alcanza con advertirlo al pie: hay que
    # medirlo bien.** La ventana son los días completos que corren la MISMA
    # cadencia que el último de ellos, **deducida de los datos** —ver
    # `_ventana_de_la_cadencia`—, y sólo si no hay ningún día completo se cae a
    # los siete, y lo dice en la línea del listado, no en una nota al pie.
    por_dia = {}
    for v in del_mes.values():
        d = v.get("dia")
        if d:
            por_dia[d] = por_dia.get(d, 0) + v["minutos"]
    completos = sorted(d for d in por_dia if d != hoy.date().isoformat())
    de_la_cadencia, cadencia = _ventana_de_la_cadencia(
        del_mes, set(por_dia), hoy.date().isoformat())
    recientes = de_la_cadencia or completos[-7:]
    ventana = (f"los días que corren la cadencia de hoy, {cadencia}"
               if de_la_cadencia
               else "los últimos siete completos · OJO: ningún día completo "
                    "todavía, la proyección puede traer una cadencia vieja")
    ritmo = (sum(por_dia[d] for d in recientes) / len(recientes)) if recientes else 0
    quedan = dias_del_mes - dia
    proyeccion = total + ritmo * quedan if ritmo else total / max(dia, 1) * dias_del_mes

    por_flujo = {}
    for v in del_mes.values():
        etiq = (v.get("deposito") or "femonoe") + " · " + v["flujo"]
        f = por_flujo.setdefault(etiq, [0, 0])
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
    print(f"  {'este depósito':38s} {len(del_mes):4d} corridas {propio:5d} min")
    print(f"  {'los otros de la casa (declarado ' + MEDIDA_EL + ')':38s} "
          f"{'':4s}          {RESERVA_OTROS_DEPOSITOS:5d} min")
    print(f"  {'TOTAL DE LA CUENTA':38s} {'':4s}          {total:5d} min "
          f"de {CUOTA} ({total / CUOTA * 100:.0f} %)")
    if recientes:
        print(f"  consumo por día, {ventana}:")
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
            f"La proyección usa {ventana}: "
            f"{len(recientes)} día(s) completo(s).", "",
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
