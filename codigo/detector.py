# -*- coding: utf-8 -*-
"""Detector de FEMÓNOE: aplica umbrales.json a las series y decide qué señales
le llegan a una persona. **No emite alertas**: la alerta la escribe una persona.

Salida:
  senales/AAAA-MM-DD.json   todo lo que pasó el umbral, con su motivo (registro)
  senales/ultimo.md         el resumen para leer
Uso: python detector.py [AAAA-MM-DD]   (sin fecha, evalúa ayer)
     python detector.py --ensayo 90    (corre el detector sobre los últimos 90 días)
"""
import hashlib
import json
import math
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "colectores"))
from comun import EVENTOS, RAIZ, leer_serie, padron  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import zonas  # noqa: E402

CONF_TXT = (RAIZ / "umbrales.json").read_text(encoding="utf-8")
CONF = json.loads(CONF_TXT)
HUELLA = hashlib.sha256(CONF_TXT.encode()).hexdigest()[:12]
C = CONF["comun"]
NOMBRE = {p["iso3"]: p["nombre"] for p in padron()}


def _mediana_mad(valores):
    med = statistics.median(valores)
    mad = statistics.median([abs(v - med) for v in valores])
    return med, mad


def _poisson_cola(k, lam):
    """P(X >= k) con media lam."""
    lam = max(lam, 0.1)
    termino, acumulado = math.exp(-lam), 0.0
    for i in range(int(k)):
        acumulado += termino
        termino *= lam / (i + 1)
        if acumulado >= 1:
            break
    return max(0.0, 1 - acumulado)


def _sensibles(dia: date) -> set:
    """Países con calendario institucional o desastre natural grave en la ventana."""
    salida = set()
    for archivo in ("calendario.json", "datos/contexto.json"):
        f = RAIZ / archivo
        if not f.exists():
            continue
        for e in json.loads(f.read_text(encoding="utf-8")):
            try:
                d = date.fromisoformat(str(e.get("fecha"))[:10])
            except ValueError:
                continue
            if abs((d - dia).days) <= C["multiplicador_calendario_dias"]:
                salida.add(e["iso3"])
    return salida


def _desvio_diario(senal, reglas, dia, sensibles):
    serie = leer_serie(senal)
    salida = []
    for iso, s in serie.items():
        def cruza(d):
            v = s.get(d.isoformat())
            base = [s[(d - timedelta(days=k)).isoformat()] for k in range(1, C["dias_base"] + 1)
                    if (d - timedelta(days=k)).isoformat() in s]
            if v is None or len(base) < C["dias_base"] // 2 or v < reglas["piso"]:
                return None
            med, mad = _mediana_mad(base)
            veces, zmin = reglas["veces_mediana"], reglas.get("z_robusto", 3)
            if iso in sensibles:
                veces, zmin = CONF["calendario"]["veces_mediana"], CONF["calendario"]["z_robusto"]
            if med == 0:
                p = _poisson_cola(v, statistics.mean(base))
                return {"valor": v, "mediana": med, "p_poisson": round(p, 6)} if p < C["poisson_p"] else None
            z = (v - med) / (1.4826 * mad) if mad else float("inf")
            if v >= veces * med and z >= zmin:
                return {"valor": v, "mediana": med, "veces": round(v / med, 1)}
            return None
        hoy, ayer = cruza(dia), cruza(dia - timedelta(days=1))
        if hoy and ayer:  # persistencia: dos corridas seguidas
            salida.append({"iso3": iso, "senal": senal, "clase": "desvio", **reglas, **hoy,
                           "sensible": iso in sensibles})
    return salida


def _desvio_zona(senal, reglas, dia):
    """El mismo desvío, pero sobre la zona y no sobre el país.

    **Por qué suma antes de medir.** Tres Estados con un alza del treinta por
    ciento cada uno no pasan ningún umbral por separado, y juntos sí: es un
    solo hecho repartido. Medir primero y agregar después habría perdido
    exactamente el caso que las zonas vienen a recuperar.

    El piso se exige sobre el total de la zona, no sobre cada Estado. La línea
    de base es la de la zona, calculada sobre su propia serie sumada."""
    serie = leer_serie(senal)
    salida = []
    for z in zonas.zonas():
        s = zonas.serie_de_zona(serie, z)
        if not s:
            continue

        def cruza(d, s=s, z=z):
            v = s.get(d.isoformat())
            base = [s[(d - timedelta(days=k)).isoformat()]
                    for k in range(1, C["dias_base"] + 1)
                    if (d - timedelta(days=k)).isoformat() in s]
            if v is None or len(base) < C["dias_base"] // 2 or v < reglas["piso"]:
                return None
            med, mad = _mediana_mad(base)
            if med == 0:
                p = _poisson_cola(v, statistics.mean(base))
                return ({"valor": v, "mediana": med, "p_poisson": round(p, 6)}
                        if p < C["poisson_p"] else None)
            zr = (v - med) / (1.4826 * mad) if mad else float("inf")
            if v >= reglas["veces_mediana"] * med and zr >= reglas.get("z_robusto", 3):
                return {"valor": v, "mediana": med, "veces": round(v / med, 1)}
            return None

        hoy, ayer = cruza(dia), cruza(dia - timedelta(days=1))
        if not (hoy and ayer):
            continue
        # De qué Estados salió. El expediente nunca pierde el origen: la zona
        # es la unidad de análisis, no una forma de borrar el dato.
        reparto = {iso: serie.get(iso, {}).get(dia.isoformat(), 0)
                   for iso in z["estados"]}
        # **Prueba de reparto, y es la que hace honesta a la zona.** Sumar
        # antes de medir deja que un solo país se disfrace de zona: medido el
        # 1/10/2026, de siete señales de zona cinco eran un país solo —Haití
        # con el 93 % de la frontera con Dominicana, Argentina con el 100 % de
        # la Triple Frontera—. Un hecho de frontera se ve de los dos lados; si
        # no se ve, es un hecho nacional con nombre prestado.
        total = sum(reparto.values()) or 1
        mayor = max(reparto.values()) / total
        if mayor > CONF.get("zonas", {}).get("concentracion_maxima", 0.75):
            continue
        salida.append({"iso3": z["codigo"], "zona": True,
                       "concentracion": round(mayor, 2),
                       "nombre_zona": z["nombre"], "estados": z["estados"],
                       "senal": senal, "clase": "desvio", **reglas, **hoy,
                       "reparto": reparto, "sensible": False})
    return salida


def _desvio_semanal(senal, reglas, dia):
    serie = leer_serie(senal)
    lunes = dia - timedelta(days=dia.weekday()) - timedelta(days=7)  # última semana completa
    salida = []
    n_base = reglas.get("semanas_base", C["semanas_base"])
    for iso, s in serie.items():
        v = s.get(lunes.isoformat())
        base = [s[(lunes - timedelta(weeks=k)).isoformat()] for k in range(1, n_base + 1)
                if (lunes - timedelta(weeks=k)).isoformat() in s]
        if v is None or len(base) < n_base // 2 or v < reglas["piso"]:
            continue
        med = statistics.median(base)
        ok = v >= reglas["veces_mediana"] * max(med, 1)
        if "percentil" in reglas:
            ok = ok and v >= sorted(base)[int(len(base) * reglas["percentil"] / 100) - 1]
        if ok:
            salida.append({"iso3": iso, "senal": senal, "clase": "desvio", **reglas,
                           "semana": lunes.isoformat(), "valor": v, "mediana": med,
                           "veces": round(v / max(med, 1), 1)})
    return salida


def _hechos_duros(dia):
    salida = []
    reglas = CONF["hechos_duros"]
    desde = dia - timedelta(days=7)
    f = EVENTOS / "acled_hecho_grave.json"
    if f.exists():
        for e in json.loads(f.read_text(encoding="utf-8")):
            if desde < date.fromisoformat(e["fecha"]) <= dia:
                salida.append({**reglas["acled_hecho_grave"], **e, "clase": "hecho_duro"})
    # corte de internet: una sola alerta crítica es ruido —el 6 % de los días-país
    # tiene alguna—; un corte real lo ven varias mediciones el mismo día
    r = reglas["ioda_corte"]
    for iso, s in leer_serie("ioda_criticas").items():
        v = s.get(dia.isoformat(), 0)
        if v >= r["criticas_minimas"]:
            salida.append({**r, "iso3": iso, "senal": "ioda_corte", "clase": "hecho_duro",
                           "fecha": dia.isoformat(), "valor": v,
                           "detalle": f"{int(v)} alertas críticas de corte en el día"})
    # bloqueo nuevo: confirmado hoy en un país sin bloqueos en los 28 días previos
    r = reglas["ooni_bloqueo"]
    for iso, s in leer_serie("ooni_confirmados").items():
        v = s.get(dia.isoformat(), 0)
        previos = [s.get((dia - timedelta(days=k)).isoformat(), 0) for k in range(1, r["dias_sin_previo"] + 1)]
        if v >= r["confirmados_minimos"] and not any(previos):
            salida.append({**r, "iso3": iso, "senal": "ooni_bloqueo", "clase": "hecho_duro",
                           "fecha": dia.isoformat(), "valor": v,
                           "detalle": f"{int(v)} bloqueos confirmados, ninguno en los 28 días previos"})
    return salida


DIAS_PARA_CORROBORAR = 60


def _madura(familia: str, dia: date) -> bool:
    """¿Esta familia lleva midiendo lo suficiente como para corroborar?

    Por qué existe. El 22/9/2026 la primera alerta de la casa figuraba sostenida
    por dos familias y en sustancia la sostenía una: la familia de redes había
    arrancado el 20/9 y saltó de casi nada a cientos de mensajes diarios **en los
    33 Estados a la vez**. Eso no es un hecho de un país: es la puesta en marcha
    del recolector, y una familia sin línea de base no puede decir si algo se
    salió de lo normal.

    No se deduce de la serie —un feed leído hoy trae notas de hace meses y simula
    una historia que el recolector no tuvo—: se declara en `umbrales.json`,
    familia por familia, con la fecha en que empezó a medir."""
    conf = CONF.get("familias", {})
    ficha = conf.get(familia)
    if not isinstance(ficha, dict) or not ficha.get("desde"):
        return True          # familia sin declaración: se asume con historia
    try:
        desde = date.fromisoformat(ficha["desde"])
    except ValueError:
        return True
    return (dia - desde).days >= conf.get("dias_para_corroborar", 60)


def evaluar(dia: date) -> list:
    sensibles = _sensibles(dia)
    crudas = _hechos_duros(dia)
    for senal, reglas in CONF["diarias"].items():
        crudas += _desvio_diario(senal, reglas, dia, sensibles)
        if CONF.get("zonas_activas", True):
            crudas += _desvio_zona(senal, reglas, dia)
    for senal, reglas in CONF["semanales"].items():
        crudas += _desvio_semanal(senal, reglas, dia)

    # corroboración: familias distintas por país y eje
    por_pais = {}
    for s in crudas:
        por_pais.setdefault(s["iso3"], []).append(s)
    salida = []
    for iso, lista in por_pais.items():
        ejes = {s["eje"] for s in lista}
        for eje in ejes:
            del_eje = [s for s in lista if s["eje"] == eje]
            familias = sorted({s["familia"] for s in del_eje})
            maduras = sorted({s["familia"] for s in del_eje if _madura(s["familia"], dia)})
            nuevas = [f for f in familias if f not in maduras]
            abre = [s for s in del_eje if s.get("abre", True)]
            if not abre:  # sólo GDELT: corrobora pero no abre
                continue
            salida.append({
                "iso3": iso, "eje": eje,
                "pais": (next((s.get("nombre_zona") for s in del_eje
                               if s.get("nombre_zona")), None)
                         or NOMBRE.get(iso, iso)),
                "zona": any(s.get("zona") for s in del_eje),
                "estados": next((s.get("estados") for s in del_eje
                                 if s.get("estados")), None),
                "hecho_duro": any(s["clase"] == "hecho_duro" for s in del_eje),
                "dos_ejes": len(ejes) > 1,
                "familias": familias,
                "familias_que_corroboran": maduras,
                "familias_en_puesta_en_marcha": nuevas,
                "fuente_unica": len(maduras) < 2,
                "tamano": max((s.get("veces") or 0) for s in del_eje),
                "senales": del_eje,
            })
    _corroborar_por_presencia(salida, dia)
    _vincular_zona_y_pais(salida)
    salida.sort(key=lambda x: (not x["hecho_duro"], not x["dos_ejes"], -len(x["familias"]), -x["tamano"]))
    return salida


SERIE_REDES = {"gobernabilidad": "redes_gobernabilidad", "seguridad": "redes_seguridad",
               "entorno informativo": "redes_informativo"}


def _corroborar_por_presencia(salida, dia):
    """Las redes todavía no tienen historia para medir desvíos. Mientras tanto
    confirman por presencia: mensajes del mismo país y eje, en las 72 horas previas,
    por encima del piso. Queda marcado así en la señal."""
    ventana = C["horas_corroboracion"] // 24
    for s in salida:
        if "redes" in s["familias"]:
            continue
        reglas = CONF["diarias"].get(SERIE_REDES[s["eje"]])
        serie = leer_serie(SERIE_REDES[s["eje"]]).get(s["iso3"], {})
        total = sum(serie.get((dia - timedelta(days=k)).isoformat(), 0) for k in range(ventana))
        if reglas and total >= reglas["piso"]:
            s["familias"] = sorted(s["familias"] + ["redes"])
            s["redes_por_presencia"] = int(total)
            # Sólo suma como segunda fuente si la serie de redes de ese país ya
            # tiene historia. Mientras arranca, es evidencia, no corroboración.
            if _madura("redes", dia):
                s["familias_que_corroboran"] = sorted(
                    s.get("familias_que_corroboran", []) + ["redes"])
            else:
                s["familias_en_puesta_en_marcha"] = sorted(
                    s.get("familias_en_puesta_en_marcha", []) + ["redes"])
            s["fuente_unica"] = len(s.get("familias_que_corroboran", [])) < 2



def _vincular_zona_y_pais(salida):
    """Cuando una zona y uno de sus Estados se mueven el mismo día y en el
    mismo eje, casi siempre es **un solo hecho visto de dos maneras**. Medido
    el 1/10/2026: cinco de ocho señales de zona coincidían con una de país.

    No se suprime ninguna de las dos. Suprimir la de zona perdería que el hecho
    cruza la frontera; suprimir la de país perdería de qué lado pesa. Lo que se
    hace es **vincularlas**, para que quien abra la alerta sepa que la otra
    existe y abra una sola."""
    zonas_hoy = [s for s in salida if s.get("zona")]
    paises_hoy = [s for s in salida if not s.get("zona")]
    for z in zonas_hoy:
        miembros = [p for p in paises_hoy
                    if p["iso3"] in (z.get("estados") or []) and p["eje"] == z["eje"]]
        if not miembros:
            continue
        z["tambien_como_pais"] = [p["iso3"] for p in miembros]
        for p in miembros:
            p.setdefault("tambien_como_zona", []).append(z["iso3"])

def escribir(dia: date, senales: list):
    carpeta = RAIZ / "senales"
    carpeta.mkdir(exist_ok=True)
    registro = {"fecha": dia.isoformat(), "umbrales_version": CONF["version"],
                "umbrales_huella": HUELLA, "cantidad": len(senales), "senales": senales}
    (carpeta / f"{dia}.json").write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
    lineas = [f"# FEMÓNOE · señales del {dia}", "",
              f"Umbrales versión {CONF['version']} (huella {HUELLA}). "
              f"**{len(senales)} {'señal' if len(senales) == 1 else 'señales'}** "
              f"{'pasó' if len(senales) == 1 else 'pasaron'} el umbral. Ninguna es una alerta todavía: "
              "la alerta la escribe una persona.", ""]
    if not senales:
        lineas.append("Sin señales. Ningún país de los 33 se salió de lo habitual.")
    for i, s in enumerate(senales, 1):
        marca = "HECHO DURO · " if s["hecho_duro"] else ""
        unica = " · **fuente única**" if s["fuente_unica"] else ""
        lineas.append(f"{i}. **{s['pais']}** · {s['eje']} · {marca}familias: {', '.join(s['familias'])}{unica}")
        for x in s["senales"]:
            det = x.get("detalle") or f"valor {x.get('valor')} contra mediana {x.get('mediana')}"
            lineas.append(f"   - {x.get('codigo')} `{x['senal']}`: {det}")
    (carpeta / "ultimo.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--ensayo":
        dias = int(sys.argv[2])
        cuenta = {}
        for k in range(dias, 0, -1):
            d = date.today() - timedelta(days=k)
            for s in evaluar(d):
                clave = (s["eje"], "duro" if s["hecho_duro"] else "desvío")
                cuenta[clave] = cuenta.get(clave, 0) + 1
        total = sum(cuenta.values())
        print(f"Ensayo de {dias} días: {total} señales, {total / dias * 7:.1f} por semana")
        for (eje, clase), n in sorted(cuenta.items()):
            print(f"  {eje:22s} {clase:7s} {n:5d}  ({n / dias * 7:.1f}/semana)")
        return
    dia = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today() - timedelta(days=1)
    senales = evaluar(dia)
    escribir(dia, senales)
    print(f"{dia}: {len(senales)} señales")


if __name__ == "__main__":
    main()
