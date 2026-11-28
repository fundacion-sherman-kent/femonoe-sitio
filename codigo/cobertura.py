# -*- coding: utf-8 -*-
"""Cuánto de los 33 Estados cubre cada familia, calculado por el robot.

**Por qué existe.** La dirección fijó el 16/11/2026 que FEMÓNOE debe llegar a
cubrir **el 100 % de los 33 Estados**, y en la misma orden que **el trabajo lo
hagan los robots o las IA libres, no los tokens de la casa**. Hasta ese día la
cobertura se medía a mano cada vez que alguien preguntaba: tres veces en doce
días, con el mismo programa escrito de nuevo cada vez. Eso es exactamente lo
que la regla vino a prohibir.

**Qué deja escrito.** `datos/cobertura.json`, con el atraso de cada familia, los
Estados con lectura, los Estados que nunca registraron un valor, y la lista
nominal de los que faltan — para que el tablero, el aviso y cualquiera que
pregunte **lean** en vez de medir.

**Lo que NO hace.** No juzga, no publica y no decide. Tampoco deduce por qué un
Estado falta: un Estado sin sondas de OONI y un Estado al que el colector no
llega se ven igual desde acá, y confundirlos sería inventar. Dice qué falta; el
por qué va en el acta, escrito por quien lo midió.
"""
import csv
import io
import json
import math
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CONF = json.loads((RAIZ / "umbrales.json").read_text(encoding="utf-8"))
PADRON = json.loads((RAIZ / "padron.json").read_text(encoding="utf-8"))["estados"]
ISO = [p["iso3"] for p in PADRON]
NOMBRE = {p["iso3"]: p["nombre"] for p in PADRON}


def _serie(nombre):
    d = {}
    f = RAIZ / "datos" / "series" / f"{nombre}.csv"
    if not f.exists():
        return d
    for r in csv.DictReader(io.open(f, encoding="utf-8")):
        d.setdefault(r["iso3"], {})[r["fecha"]] = float(r["valor"])
    return d


def _poisson(k, lam):
    lam = max(lam, 0.1)
    termino, acum = math.exp(-lam), 0.0
    for i in range(int(k)):
        acum += termino
        termino *= lam / (i + 1)
        if acum >= 1:
            break
    return max(0.0, 1 - acum)


def _cruza(s, dia, u, maduro):
    C = CONF["comun"]
    v = s.get(dia.isoformat())
    base = [s[(dia - timedelta(days=k)).isoformat()]
            for k in range(1, C["dias_base"] + 1)
            if (dia - timedelta(days=k)).isoformat() in s]
    if v is None or len(base) < C["dias_base"] // 2 or v < u["piso"]:
        return False
    med = statistics.median(base)
    mad = statistics.median([abs(x - med) for x in base])
    if med == 0:
        return maduro and _poisson(v, statistics.mean(base)) < C["poisson_p"]
    z = (v - med) / (1.4826 * mad) if mad else float("inf")
    return v >= u["veces_mediana"] * med and z >= u.get("z_robusto", 3)


def medir(hoy=None):
    hoy = hoy or date.today()
    por_familia = {}
    series_de = {}
    for n, u in (CONF.get("diarias") or {}).items():
        series_de.setdefault(u["familia"], []).append((n, u))

    for familia, lista in series_de.items():
        cargadas = {n: _serie(n) for n, _ in lista}
        fechas = sorted({f for s in cargadas.values() for v in s.values() for f in v})
        if not fechas:
            por_familia[familia] = {"vacia": True}
            continue
        ultima = fechas[-1]
        con_fila = [i for i in ISO
                    if any(ultima in (s.get(i) or {}) for s in cargadas.values())]
        con_valor = [i for i in ISO
                     if any(v > 0 for s in cargadas.values() for v in (s.get(i) or {}).values())]
        por_familia[familia] = {
            "ultima_fila": ultima,
            "atraso_dias": (hoy - date.fromisoformat(ultima)).days,
            "estados_con_lectura": len(con_fila),
            "estados_sin_lectura": sorted(set(ISO) - set(con_fila)),
            "estados_con_algun_valor": len(con_valor),
            "estados_sin_ningun_valor": sorted(set(ISO) - set(con_valor)),
            "eje": sorted({u["eje"] for _, u in lista}),
            "series": sorted(n for n, _ in lista),
        }

    # UNA FAMILIA CUENTA SI ADEMÁS ESTÁ AL DÍA.
    #
    # Contar la última fila sin mirar su fecha infla la cobertura: el 16/11/2026
    # `cloudflare` leía los 33 Estados **en una fila de diez días antes**, y así
    # contada daba cobertura plena para un eje que en los últimos diez días no
    # dijo nada. Una familia cuenta cuando su última fila es de hoy o de ayer;
    # la otra cuenta también se deja escrita, rotulada, porque la diferencia
    # entre «nunca lo leyó» y «lo leyó y está atrasada» es la que decide si hace
    # falta una fuente nueva o arreglar un colector.
    AL_DIA = 2

    def _lee(d, i):
        return not d.get("vacia") and i not in d.get("estados_sin_lectura", ISO)

    frescas = [d for d in por_familia.values()
               if not d.get("vacia") and d["atraso_dias"] <= AL_DIA]
    cubiertos = [i for i in ISO if any(_lee(d, i) for d in frescas)]

    def cuantas(i):
        return sum(1 for d in frescas if _lee(d, i))

    # MUDOS POR CONSTRUCCIÓN: leídos, pero sin con qué cruzar.
    #
    # La distinción que importa para el mandato del 100 %. Un Estado puede estar
    # leído todos los días por cuatro familias y **no poder producir una señal
    # nunca**, porque su máximo histórico no llega al piso de ninguna serie. El
    # 26/10/2026 se midieron cinco así —GUY, BHS, ATG, KNA, LCA—: el máximo
    # histórico de violencia de Bahamas es **0** contra un piso de 8. No es que
    # no cruce: no tiene con qué.
    #
    # Se escribe acá para que el motor de automejora apunte ahí cuando busca
    # fuentes nuevas, en vez de buscar para «los peor cubiertos», que mide otra
    # cosa. Lo que les falta no es que alguien los mire: es **volumen**.
    # **Y se mide DOS VECES, porque las dos cosas son distintas y confundirlas
    # ya dio dos respuestas opuestas a la misma pregunta.** El 26/10 se midieron
    # cinco mudos excluyendo `redes`; contando `redes` no hay ninguno, porque esa
    # familia tiene volumen en los 33. Las dos cuentas son ciertas y responden
    # preguntas distintas:
    #
    #   mudos_por_construccion       ¿puede producir una señal, con lo que haya?
    #   mudos_para_corroborar        ¿puede producirla desde una familia MADURA,
    #                                que es la única que sostiene un juicio de
    #                                confianza alta? (regla 10 de la casa)
    #
    # La segunda es la que importa para el mandato del 100 %, y es la que el
    # motor de automejora tiene que usar para buscar fuentes.
    def _madura(familia):
        f = (CONF.get("familias") or {}).get(familia)
        if not isinstance(f, dict) or not f.get("desde"):
            return True
        try:
            desde = date.fromisoformat(f["desde"])
        except ValueError:
            return True
        return (hoy - desde).days >= (CONF.get("familias") or {}).get(
            "dias_para_corroborar", 60)

    alcanzable = {i: [] for i in ISO}
    alcanzable_maduro = {i: [] for i in ISO}
    for n, u in (CONF.get("diarias") or {}).items():
        s = _serie(n)
        maduro = _madura(u.get("familia", ""))
        for i in ISO:
            if max((s.get(i) or {}).values(), default=0) >= u["piso"]:
                alcanzable[i].append(n)
                if maduro:
                    alcanzable_maduro[i].append(n)
    mudos = sorted(i for i in ISO if not alcanzable[i])
    mudos_corrob = sorted(i for i in ISO if not alcanzable_maduro[i])

    # LA REGLA COMPLETA, QUE ES LA QUE CONTESTA «¿PUEDE SEÑALAR?».
    #
    # Llegar al piso es necesario y no alcanza: después vienen el múltiplo y el
    # z robusto —o la cola de Poisson si la mediana es cero— y **la persistencia
    # de dos días seguidos**, que es la que más descarta. El 26/10/2026 Guyana
    # cruzó 22 días y **nunca dos seguidos**, así que la persistencia se la comía
    # entera aunque llegara al piso. Medir sólo el piso y llamarlo «puede
    # señalar» es el error que este bloque evita.
    #
    # Se corre hacia atrás sobre toda la serie, Estado por Estado, y queda
    # escrito. Es lo que antes había que pedirle a una herramienta aparte y
    # medir a mano cada vez que alguien preguntaba.
    # Y SE CUENTAN SÓLO LAS SERIES QUE PUEDEN **ABRIR** UNA ALERTA.
    #
    # Hasta el 20/11/2026 este bloque recorría TODAS las diarias, incluidas las
    # que llevan `abre: false` —`ooni_confirmados`, `ooni_tasa`, `ioda_alertas`,
    # las de `redes`, las de ACLED—. Esas series corroboran una alerta ajena;
    # ninguna puede abrir una propia. Contarlas acá le acreditaba a un Estado
    # una capacidad de señalar que no tiene.
    #
    # LO QUE OCULTABA, medido el mismo día: **Nicaragua figuraba con 2,5 señales
    # al año y no puede producir ninguna.** Pasa la regla 16 veces en las dos
    # series que abren y **nunca dos días seguidos** —el caso de Guyana exacto—.
    # El registro publicado decía cinco Estados mudos. Son seis.
    #
    # Lo halló el red-cell al impugnar otra cosa, y es la misma familia de
    # defecto que `no_pueden_senalar` vino a evitar: medir una parte de la regla
    # y llamarla la regla.
    senales = {}
    for n, u in (CONF.get("diarias") or {}).items():
        if not u.get("abre", True):
            continue
        s = _serie(n)
        maduro = _madura(u.get("familia", ""))
        dias = sorted({f for v in s.values() for f in v})
        if not dias:
            continue
        tramo = (date.fromisoformat(dias[-1]) - date.fromisoformat(dias[0])).days or 1
        for i in ISO:
            s_i = s.get(i) or {}
            veces = 0
            for f in sorted(s_i):
                d = date.fromisoformat(f)
                if _cruza(s_i, d, u, maduro) and _cruza(s_i, d - timedelta(days=1), u, maduro):
                    veces += 1
            if veces:
                senales[i] = round(senales.get(i, 0.0) + veces / tramo * 365, 1)
    nunca = sorted(i for i in ISO if i not in senales)

    return {
        "medido": hoy.isoformat(),
        "senales_por_ano_por_estado": dict(sorted(senales.items(), key=lambda x: -x[1])),
        "no_pueden_senalar": [[i, NOMBRE[i]] for i in nunca],
        "sin_llegar_al_piso": [[i, NOMBRE[i]] for i in mudos],
        "sin_llegar_al_piso_maduro": [[i, NOMBRE[i]] for i in mudos_corrob],
        "series_al_alcance_por_estado": {i: sorted(v) for i, v in alcanzable.items()},
        "series_maduras_al_alcance_por_estado": {i: sorted(v)
                                                 for i, v in alcanzable_maduro.items()},
        "estados_del_padron": len(ISO),
        "familias_al_dia": len(frescas),
        "estados_con_alguna_lectura_al_dia": len(cubiertos),
        "estados_sin_ninguna_lectura": sorted(
            {i: NOMBRE[i] for i in ISO if i not in cubiertos}.items()),
        "estados_con_una_sola_familia_al_dia": sorted(
            (i, NOMBRE[i]) for i in ISO if cuantas(i) == 1),
        "familias_por_estado_al_dia": {i: cuantas(i) for i in ISO},
        "familias": por_familia,
        "que_cuenta": {
            "atraso_dias": "días entre hoy y la última fila que escribió la familia.",
            "estados_con_lectura": "Estados que tienen fila en esa última fecha.",
            "estados_con_algun_valor": "Estados que alguna vez registraron un "
                                       "valor mayor que cero. Un Estado con "
                                       "filas siempre en cero está medido, no "
                                       "ciego: la diferencia importa.",
            "no_pueden_senalar": "Corrida la regla COMPLETA hacia atrás sobre "
                                 "toda la serie —piso, múltiplo, z robusto o "
                                 "Poisson, y persistencia de dos días—, no "
                                 "producirían ninguna señal. Es la cuenta que "
                                 "importa para el mandato del 100 %: llegar al "
                                 "piso es necesario y no alcanza.",
            "sin_llegar_al_piso_maduro": "No alcanzan el piso de ninguna serie de "
                                     "familia MADURA, así que no pueden sostener "
                                     "un juicio de confianza alta. Es la cuenta "
                                     "que importa para el mandato del 100 %.",
            "mudos_por_construccion": "Leídos, pero su máximo histórico no llega "
                                       "al piso de ninguna serie: no pueden "
                                       "producir una señal nunca. Lo que les "
                                       "falta es volumen, no que alguien los mire.",
            "estados_con_una_sola_familia_al_dia": "No pueden sostener un juicio de "
                                            "confianza alta: la regla 10 de la "
                                            "casa pide dos fuentes.",
        },
    }


def main():
    d = medir()
    salida = RAIZ / "datos" / "cobertura.json"
    salida.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Cobertura: {d['estados_con_alguna_lectura_al_dia']} de "
          f"{d['estados_del_padron']} Estados leídos por alguna familia AL DÍA "
          f"({d['familias_al_dia']} de {len(d['familias'])} familias al día) · "
          f"{len(d['estados_con_una_sola_familia_al_dia'])} con una sola")
    for f, x in sorted(d["familias"].items()):
        if x.get("vacia"):
            print(f"   {f:14s} VACÍA")
            continue
        print(f"   {f:14s} atraso {x['atraso_dias']:3d} d · "
              f"{x['estados_con_lectura']:2d}/33 con lectura · "
              f"{x['estados_con_algun_valor']:2d}/33 con algún valor")
    m = d["sin_llegar_al_piso"]
    mc = d["sin_llegar_al_piso_maduro"]
    print(f"   sin llegar al piso de ninguna serie ({len(m)}): "
          f"{', '.join(i for i, _ in m) if m else 'ninguno'}")
    print(f"   sin llegar al piso de ninguna serie madura ({len(mc)}): "
          f"{', '.join(i for i, _ in mc) if mc else 'ninguno'}")
    nn = d["no_pueden_senalar"]
    print(f"   NO PUEDEN SEÑALAR, regla completa ({len(nn)}): "
          f"{', '.join(i for i, _ in nn) if nn else 'ninguno'}")
    faltan = d["estados_sin_ninguna_lectura"]
    print(f"   sin ninguna lectura: {', '.join(i for i, _ in faltan) if faltan else 'ninguno'}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
