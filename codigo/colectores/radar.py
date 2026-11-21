# -*- coding: utf-8 -*-
"""Cloudflare Radar · cortes de internet anotados, con su causa declarada.

**Qué resuelve, y es el hueco más grande que tiene FEMÓNOE.** IODA detecta que
el tráfico de un país cayó, pero no sabe por qué: un cable cortado, un temporal
y un apagón deliberado se ven igual desde afuera. Así quedó escrito en la
lectura DISARM de la casa —«no prueba que sea deliberada»— y así se publicó.

Cloudflare anota sus cortes **con la causa**: distingue un apagón dispuesto por
un gobierno de una falla técnica o de un corte de energía. Eso es exactamente lo
que al eje del entorno informativo le faltaba para pasar de «hubo una caída» a
«hubo una caída y esto es lo que la originó».

**Y es una segunda familia.** Hoy casi toda señal de FEMÓNOE sale de fuente
única, porque la familia `redes` no corrobora hasta el 19/11/2026. Cloudflare
mide con infraestructura propia, distinta de la de IODA —que es académica— y de
la de OONI —que son voluntarios—, así que corrobora de verdad y no por
parentesco.

**La llave.** Es de sólo lectura sobre Radar, gratuita, y vive en el robot. La
misma que ya usa SIWA. Sin ella este colector **se detiene declarándolo** en
vez de escribir un archivo vacío que después alguien lea como «no pasó nada».

**Escrito sin poder probarlo**, porque la llave no está en esta máquina. Por eso
no da por sentada la forma de la respuesta: busca cada campo entre varios
nombres posibles, y **lo que no entiende lo anota en vez de inventarlo**. La
primera corrida del robot es su verdadera prueba.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import RAIZ, guardar_serie, padron  # noqa: E402

BASE = "https://api.cloudflare.com/client/v4/radar/annotations/outages"
SECRETO = ("CLOUDFLARE_RADAR", "CF_RADAR_TOKEN", "CLOUDFLARE_TOKEN")
DIAS = 400          # la historia que se pide, para que la familia nazca madura
TOPE_ANOTACIONES = 1000   # el `limit` que se le pide a la fuente, en un solo lugar
UA = ("FEMONOE-robot/0.1 (Fundacion Sherman Kent; +https://fundacionkent.org)")

# Causas que Cloudflare declara. Sólo las dos primeras hablan de una decisión;
# las demás son el mundo físico, y confundirlas sería el error que esta fuente
# vino a evitar.
# QUÉ CUENTA COMO APAGÓN DISPUESTO, Y QUÉ SE HACE CON LO QUE NO SE CONOCE.
#
# Antes esto era una tupla y se emparejaba POR SUBCADENA: `any(x in causa)`.
# El décimo hombre dictaminó el 16/11/2026 —y se verificó— que sobre un campo
# que la API documenta como texto libre, sin enumeración publicada, eso tiene
# dos modos de falla y los dos son silenciosos: un valor nuevo que contenga
# «GOVERNMENT» abre solo, y un cambio de nombre hace que no abra nunca.
#
# **Cerrar la lista sin más cambiaría una falla silenciosa por otra**, porque un
# valor nuevo quedaría afuera y se leería como «no deliberado». Así que la lista
# dice qué cuenta y el colector **declara en su salida todo valor que no
# conozca**, en vez de descartarlo callado. Las dos listas viven en
# `umbrales.json`, bajo `cloudflare_definicion`, con su motivo escrito.
_DEF = json.loads((RAIZ / "umbrales.json").read_text(encoding="utf-8")).get(
    "cloudflare_definicion", {})
DELIBERADO = tuple(_DEF.get("deliberadas") or ["GOVERNMENT_DIRECTED"])
CONOCIDAS = set(DELIBERADO) | set(_DEF.get("conocidas_no_deliberadas") or [])


def _llave():
    for nombre in SECRETO:
        v = os.environ.get(nombre)
        if v:
            return v
    return ""


def _pedir(token, desde, hasta):
    """`hasta` es un instante, no un dia: el corte de hoy tiene que entrar."""
    q = urllib.parse.urlencode({"dateStart": desde.isoformat() + "T00:00:00Z",
                                "dateEnd": hasta.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "limit": TOPE_ANOTACIONES, "format": "json"})
    req = urllib.request.Request(f"{BASE}?{q}", headers={
        "User-Agent": UA, "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _llave_corte(e):
    """Identifica una anotación entre corridas. La fuente no da identificador,
    así que se arma con lo que no cambia: fecha de inicio, Estado, causa y el
    principio de la descripción."""
    return "|".join([str(e.get("fecha")), str(e.get("iso3")), str(e.get("causa")),
                     str(e.get("descripcion"))[:120]])


def _campo(d, *nombres):
    """El primer campo que exista, probando varios nombres. La respuesta de un
    servicio ajeno cambia de forma sin avisar; buscar por un solo nombre es
    cómo un colector empieza a devolver ceros en silencio."""
    for n in nombres:
        if isinstance(d, dict) and d.get(n) not in (None, ""):
            return d[n]
    return None


def main():
    token = _llave()
    if not token:
        print("Cloudflare Radar: falta la llave de sólo lectura. No se escribe "
              "nada: un archivo vacío se lee después como «no hubo cortes», y "
              "eso sería mentir. Cargar el secreto CLOUDFLARE_RADAR.")
        return
    # LA FUENTE SOLO RECHAZA EL FUTURO: «Must be before now (utc)».
    #
    # Pedir «hasta ayer a las 00:00» era pedir el dia ANTERIOR a ayer: la
    # ventana cerraba al empezar ayer, asi que el ultimo dia entero que
    # entraba era el anteanterior. Medido el 4/11/2026: la serie llegaba al
    # 1/11 con el robot corriendo el 4. **Dos de esos tres dias de atraso eran
    # nuestros, no de Cloudflare.**
    #
    # Ahora se pide hasta hace un minuto. El dia en curso entra parcial, y eso
    # es correcto por dos motivos: un corte es un hecho con su fecha, no un
    # total diario que haya que esperar a que cierre; y `guardar_serie`
    # reemplaza la fecha repetida, de modo que cada corrida deja el dia mas
    # completo que la anterior. El detector evalua AYER, asi que el parcial de
    # hoy no entra en ningun juicio ni en la ventana que le sirve de base.
    hasta = datetime.now(timezone.utc) - timedelta(minutes=1)
    desde = hasta.date() - timedelta(days=DIAS)
    try:
        d = _pedir(token, desde, hasta)
    except urllib.error.HTTPError as e:
        print(f"Cloudflare Radar: respondió {e.code}. "
              f"{e.read(300).decode('utf-8', 'replace')[:200]}")
        return
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"Cloudflare Radar: no respondió ({type(e).__name__}). No se escribe nada.")
        return

    crudas = (d.get("result") or {}).get("annotations") or []
    iso2 = {p["iso2"]: p["iso3"] for p in padron()}
    por_dia, expediente, sin_entender, fuera = defaultdict(int), [], 0, 0
    for a in crudas:
        lugares = _campo(a, "locations", "locationsDetails", "location") or []
        if isinstance(lugares, (str, dict)):
            lugares = [lugares]
        codigos = []
        for l in lugares:
            c = l if isinstance(l, str) else _campo(l, "code", "alpha2", "locationCode")
            if c and str(c).upper() in iso2:
                codigos.append(iso2[str(c).upper()])
        inicio = str(_campo(a, "startDate", "startTime", "start") or "")[:10]
        if not inicio:
            sin_entender += 1       # sin fecha no se puede usar: se declara
            continue
        if not codigos:
            fuera += 1              # corte real, pero de otro Estado del mundo
            continue
        # La causa viene ANIDADA en `outage.outageCause`. `eventType` dice
        # «OUTAGE» en todas, y leerlo como causa daba cero cortes deliberados
        # en una serie donde los hay. Verificado el 1/10/2026 contra la
        # respuesta real de la fuente, que hasta entonces no se habia podido
        # ver porque la llave vive en el robot.
        corte = a.get("outage") if isinstance(a.get("outage"), dict) else {}
        causa = str(_campo(corte, "outageCause", "cause")
                    or _campo(a, "cause", "outageCause") or "").upper()
        alcance = _campo(a, "scope", "asnsDetails", "asns")
        for iso3 in codigos:
            por_dia[(inicio, iso3)] += 1
            # QUÉ SE GUARDA, Y POR QUÉ ESTOS CAMPOS.
            #
            # El décimo hombre dictaminó el 16/11/2026, y se verificó, que el
            # colector **tiraba el enlace a la nota en que la fuente basa su
            # atribución de causa**: un hecho sin enlace a su origen no es
            # trazable, y la regla 2 de la casa pide que toda afirmación lo sea.
            # También tiraba la escala —`alcance` llega **nulo en 29 de 29**
            # anotaciones—, mientras las descripciones de la propia fuente
            # nombran alcance parcial en al menos nueve casos. Sin escala, una
            # anotación provincial se lee igual que una nacional.
            #
            # Es puro agregado: ningún programa los lee todavía, así que esto no
            # cambia qué dispara. Se guardan para que lo que se construya mañana
            # sobre este campo pueda ser trazable y declarar su escala.
            expediente.append({
                "fecha": inicio, "iso3": iso3, "causa": causa or "sin declarar",
                "deliberado": causa in DELIBERADO,   # exacto, no por subcadena
                "alcance": alcance if isinstance(alcance, (str, int)) else None,
                "tipo": _campo(corte, "outageType", "type"),
                "escala": _campo(corte, "scope") or _campo(a, "scope"),
                "redes": _campo(a, "asns", "asnsDetails"),
                "enlace": _campo(a, "linkedUrl", "url", "link"),
                "descripcion": str(_campo(a, "description", "title") or "")[:300],
            })

    # LOS DÍAS SIN CORTE TAMBIÉN SON DATO, Y SIN ELLOS LA FAMILIA NO SERVÍA.
    #
    # **El defecto.** Esto escribía fila **sólo los días en que empezó un
    # corte**: un día sin cortes no quedaba en cero, no quedaba. Medido el
    # 5/11/2026: **30 fechas en 433 días de calendario**, contra 445 de 445 de
    # IODA. Corrida la regla exacta del detector, que pide al menos 14 de los
    # 28 días previos presentes, la familia tenía **0 de 990 días-Estado con
    # base usable — el 0 %**, contra el 97 % de IODA y de los hechos de GDELT.
    # La familia que se adoptó el 1/10/2026 para ser la **segunda fuente** del
    # eje informativo **no podía producir una señal, y nadie lo había medido**.
    #
    # **Qué cambia y qué no.** Ahora escribe fila para todos los días de la
    # ventana pedida. Corrido el criterio de aceptación de la casa —hacia atrás,
    # conservando Cuba 19–25/9 y Colombia 14–15/10— **pasa y agrega CERO
    # señales**: en 432 días Cloudflare anotó 30 cortes, todos de uno solo, y la
    # cola de Poisson pide tres el mismo día y dos días seguidos. Así que esto
    # **corrige la forma del archivo, no la cobertura**, y así se declaró a la
    # dirección antes de autorizarlo.
    #
    # **EL REPARO QUE ENSEÑÓ ACLED.** Una ausencia sólo es un cero si la
    # respuesta estaba completa. Si la fuente llegó al tope de anotaciones, lo
    # que falta puede estar truncado, y entonces **no se escriben ceros**: se
    # escriben nada más los días con corte y se declara. Es la misma lección que
    # costó 400 días de ceros falsos en ACLED.
    completa = len(crudas) < TOPE_ANOTACIONES
    if completa:
        dias = [(desde + timedelta(days=k)).isoformat()
                for k in range((hasta.date() - desde).days + 1)]
    else:
        dias = sorted({k[0] for k in por_dia})
        print(f"Cloudflare Radar: la fuente devolvió {len(crudas)} anotaciones, "
              f"el tope es {TOPE_ANOTACIONES}: la respuesta puede estar truncada, "
              "así que **no se escriben los días en cero** — una ausencia que "
              "quizá esté truncada no es un cero. Se escriben sólo los días con "
              "corte, como antes, y queda declarado acá.")
    if not dias:
        print(f"Cloudflare Radar: la fuente respondió pero no trajo ningún corte "
              f"de los 33 Estados en {DIAS} días. {sin_entender} anotaciones no "
              "se pudieron leer. No se escribe serie.")
        return
    filas = [(f, p["iso3"], por_dia.get((f, p["iso3"]), 0))
             for f in dias for p in padron()]
    guardar_serie("cloudflare_cortes", filas)
    deliberados = [e for e in expediente if e["deliberado"]]
    guardar_serie("cloudflare_deliberados",
                  [(f, p["iso3"],
                    sum(1 for e in deliberados if e["fecha"] == f and e["iso3"] == p["iso3"]))
                   for f in dias for p in padron()])
    # EL ATRASO DE APARICIÓN, QUE ES LA MEDICIÓN QUE FALTABA.
    #
    # El décimo hombre señaló el 16/11/2026 que sin saber **cuánto tarda una
    # anotación en aparecer** no se puede elegir la ventana de ninguna regla que
    # dispare con ella: si aparece con dos días de atraso, una regla que lee el
    # día nunca dispara; con una ventana de siete, el mismo corte vuelve a
    # señalar una semana. La medición **no existía en el depósito** y la Oficina
    # tampoco la tenía.
    #
    # No se puede deducir de la respuesta: la fuente da la fecha de INICIO del
    # corte, no la de su publicación. Así que se mide por presencia, que es la
    # única manera honesta: la primera vez que el colector ve una anotación
    # anota **cuándo la vio**, y eso se conserva en las corridas siguientes. La
    # serie arranca vacía y se llena sola; a las pocas semanas da la
    # distribución. Es la misma lógica con que la casa resolvió la corroboración
    # por presencia el 26/10.
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    previos = {}
    salida = RAIZ / "datos" / "cortes_anotados.json"
    try:
        for e in json.loads(salida.read_text(encoding="utf-8")).get("cortes") or []:
            if e.get("visto_primero"):
                previos[_llave_corte(e)] = e["visto_primero"]
    except (OSError, ValueError):
        pass
    # LA PRIMERA CORRIDA NO MIDE NADA, Y HAY QUE DECIRLO EN VEZ DE DAR UN NÚMERO.
    #
    # En la primera corrida **todas** las anotaciones se ven «por primera vez»,
    # así que su atraso calculado es simplemente su edad dentro de la ventana de
    # 400 días. La corrida del 17/11/2026 informó «mediana 146 d, de 11 a 397»:
    # eso no es el atraso de aparición, es la antigüedad del archivo histórico.
    # **La primera carga engaña**, que es una lección que la casa ya tenía
    # escrita, y el aviso de frescura ya resuelve igual: la primera pasada fija
    # la línea de base y no juzga.
    #
    # Así que la primera corrida **sólo deja la marca** y no mide. El atraso real
    # lo dan las anotaciones que aparezcan DESPUÉS, y recién ésas se cuentan.
    linea_de_base = not previos
    nuevas_vistas = 0
    for e in expediente:
        k = _llave_corte(e)
        if k in previos:
            e["visto_primero"] = previos[k]
        else:
            e["visto_primero"] = ahora
            nuevas_vistas += 1
        e["atraso_de_aparicion_dias"] = None
        if k in previos or linea_de_base:
            continue            # heredada, o línea de base: no mide
        try:
            e["atraso_de_aparicion_dias"] = (date.fromisoformat(ahora[:10])
                                             - date.fromisoformat(e["fecha"])).days
        except ValueError:
            pass
    medidos = [e["atraso_de_aparicion_dias"] for e in expediente
               if e.get("atraso_de_aparicion_dias") is not None]

    salida.write_text(json.dumps({
        "generado": date.today().isoformat(),
        "atraso_de_aparicion": {
            "_nota": ("Días entre el inicio del corte y la primera corrida que vio "
                      "la anotación. Se mide POR PRESENCIA porque la fuente no "
                      "publica cuándo anotó: sólo las anotaciones vistas por "
                      "primera vez cuentan, las heredadas quedan en nulo para no "
                      "contarse dos veces. Arranca vacío y se llena solo."),
            "linea_de_base": linea_de_base,
            "medidos_en_esta_corrida": len(medidos),
            "muestra": sorted(medidos),
        },
        "nota": ("Cortes de internet anotados por Cloudflare, con la causa que "
                 "la fuente declara. «deliberado» es lo que Cloudflare atribuye "
                 "a una decisión de gobierno: es su juicio, no el de la casa, y "
                 "así se cita."),
        "anotaciones_sin_leer": sin_entender,
        "cortes": sorted(expediente, key=lambda e: e["fecha"], reverse=True)[:400],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter as _C
    causas = _C(e["causa"] for e in expediente)
    desconocidas = sorted(c for c in causas if c not in CONOCIDAS and c != "sin declarar")
    if desconocidas:
        print("   ATENCIÓN · valores de causa que la casa NO conoce, declarados "
              "en vez de descartados en silencio: " + ", ".join(desconocidas)
              + ". Si alguno designa un apagón dispuesto por un gobierno, va a "
                "`umbrales.json` → `cloudflare_definicion.deliberadas`; si no, a "
                "`conocidas_no_deliberadas`. Mientras no se decida, **no abre**.")
    print(f"Cloudflare Radar: {len(expediente)} cortes en los 33 Estados sobre "
          f"{len(dias)} días {'de ventana entera, con sus ceros' if completa else 'con corte'}"
          f" · {len(deliberados)} atribuidos a decisión de gobierno")
    print(f"   causas: {dict(causas.most_common(8))}")
    if medidos:
        medidos.sort()
        print(f"   atraso de aparición: {len(medidos)} anotación(es) vista(s) por "
              f"primera vez · mediana {medidos[len(medidos) // 2]} d · "
              f"de {medidos[0]} a {medidos[-1]} d")
    elif linea_de_base:
        print(f"   atraso de aparición: línea de base, {nuevas_vistas} anotaciones "
              "marcadas y NINGUNA medida. En la primera corrida todas se ven por "
              "primera vez, así que su atraso sería la antigüedad del histórico y "
              "no el atraso real. Mide desde la corrida siguiente.")
    elif nuevas_vistas == 0:
        print("   atraso de aparición: ninguna anotación nueva en esta corrida; "
              "la medición se llena sola a medida que aparezcan.")
    print(f"   {fuera} cortes de otros Estados del mundo, descartados por padrón"
          + (f" · {sin_entender} anotaciones sin fecha legible, declaradas"
             if sin_entender else ""))


if __name__ == "__main__":
    main()
