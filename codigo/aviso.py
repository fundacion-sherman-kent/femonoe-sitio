# -*- coding: utf-8 -*-
"""El aviso: que una señal repetida llegue a una persona el mismo día.

**Por qué existe.** El 21/10/2026 la dirección pidió poner las alertas en
tiempo real. Al mirarlo, el problema no era la velocidad: el robot ya mide cada
dos horas y la edición diaria llega a las 09:11. **El problema era lo que pasa
después.** Una señal cruza el umbral, se guarda en un archivo, el tablero la
muestra con un foco gris, y **espera a que alguien mire**. Brasil estuvo tres
días marcado —18, 19 y 20 de octubre, con elecciones generales el 25— y nadie
se enteró, porque nada avisaba. Entre el 13 y el 21 de octubre no se abrió una
sola alerta mientras el detector marcaba señales seis de nueve días.

**Lo que este programa NO hace, y es lo que lo vuelve admisible.** No abre
alertas, no emite juicios, no decide nada. Dice «mirá esto». El acta es
explícita: **se automatiza el proceso, nunca el juicio.** Una alerta que se
abriera sola dejaría de ser lo que la casa vende.

**No repite.** Una vez avisado un par (Estado, eje), se calla hasta que ese par
deje de aparecer tres días o hasta que se le abra una alerta. Un aviso que
insiste se vuelve ruido, y el ruido no se lee.

**No cuesta nada.** Un pedido HTTP dentro de una corrida que ya se está
pagando, por el mismo bot que la casa ya usa para el buzón.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SENALES = RAIZ / "senales"
ALERTAS = RAIZ / "alertas"
ESTADO = RAIZ / "datos" / "avisos.json"

# Cuántos días seguidos tiene que repetirse una señal para que valga el aviso.
# Uno solo es ruido: el detector marca desvíos y muchos se desinflan al día
# siguiente. Dos es la señal que insiste.
DIAS_PARA_AVISAR = 2
# Cuántos días de silencio hacen falta para volver a avisar del mismo par.
DIAS_PARA_OLVIDAR = 3
# Una fecha institucional dentro de esta ventana sube el aviso de tono.
DIAS_DE_CALENDARIO = 30


def _senales_recientes(hoy, dias=7):
    """Qué pares (Estado, eje) marcó el detector, día por día."""
    por_dia = {}
    for k in range(dias):
        d = (hoy - timedelta(days=k)).isoformat()
        f = SENALES / f"{d}.json"
        if not f.exists():
            continue
        registro = json.loads(f.read_text(encoding="utf-8"))
        por_dia[d] = {(s["iso3"], s["eje"]): s for s in registro.get("senales", [])}
    return por_dia


def _seguidos(por_dia, hoy, par):
    """Cuántos días CORRIDOS viene apareciendo este par, contando hacia atrás.

    Se cuenta desde el último día que haya archivo, no desde hoy: si la corrida
    de hoy todavía no escribió sus señales, contar desde hoy daría cero y el
    aviso se perdería.
    """
    dias = sorted(por_dia, reverse=True)
    n = 0
    for d in dias:
        if par in por_dia[d]:
            n += 1
        elif n:
            break
    return n


def _con_alerta_abierta():
    """Los pares que ya tienen alerta viva: de ésos no hace falta avisar."""
    vivos = set()
    if not ALERTAS.exists():
        return vivos
    for f in ALERTAS.glob("*.json"):
        if any(x in f.name for x in ("-contexto", "-indicadores", "-dictamen")):
            continue
        try:
            a = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if a.get("estado") in ("borrador", "curada", "publicada"):
            vivos.add((a.get("iso3"), a.get("eje")))
    return vivos


def _fecha_cercana(iso3, hoy):
    """La próxima fecha institucional de ese Estado, si cae dentro de la ventana."""
    f = RAIZ / "calendario.json"
    if not f.exists():
        return None
    try:
        datos = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return None
    eventos = datos if isinstance(datos, list) else datos.get("eventos", [])
    cerca = []
    for e in eventos:
        if e.get("iso3") != iso3:
            continue
        try:
            d = date.fromisoformat(str(e.get("fecha"))[:10])
        except (TypeError, ValueError):
            continue
        faltan = (d - hoy).days
        if 0 <= faltan <= DIAS_DE_CALENDARIO:
            cerca.append((faltan, d, str(e.get("titulo") or "")))
    return min(cerca) if cerca else None


def _texto(iso3, eje, senal, seguidos, cercana):
    """El mensaje. Dice qué se vio y qué falta decidir, y nada más."""
    lineas = [f"FEMÓNOE · señal repetida", ""]
    lineas.append(f"{senal.get('pais') or iso3} · {eje}")
    lineas.append(f"{seguidos} días seguidos sobre el umbral.")
    for d in (senal.get("senales") or [])[:3]:
        # La familia `redes` está en puesta en marcha hasta el 19/11 y sus
        # números no son evidencia: se muestran marcados para que nadie los
        # confunda con un hecho.
        marca = "  (familia en puesta en marcha, no es evidencia)" if d.get("familia") == "redes" else ""
        lineas.append(f"  · {d.get('senal')}: {d.get('valor')} "
                      f"contra mediana {d.get('mediana')}{marca}")
    if cercana:
        faltan, cuando, titulo = cercana
        lineas.append("")
        lineas.append(f"Calendario: {titulo[:60]} el {cuando} — faltan {faltan} días.")
    lineas.append("")
    lineas.append("Esto NO es una alerta: es una señal que nadie juzgó todavía. "
                  "La alerta la escribe una persona.")
    return "\n".join(lineas)


def _mandar(texto):
    """Lo manda por el bot que la casa ya usa para el buzón."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("  (sin TELEGRAM_BOT_TOKEN: no se puede avisar, y no es una falla)")
        return False
    crudo = os.environ.get("BUZON_REMITENTES")
    destinos = []
    if crudo:
        try:
            destinos = json.loads(crudo).get("remitentes", [])
        except ValueError:
            pass
    if not destinos:
        print("  (sin destinatarios en BUZON_REMITENTES)")
        return False
    enviados = 0
    for quien in destinos:
        datos = urllib.parse.urlencode({"chat_id": quien, "text": texto}).encode()
        pedido = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=datos)
        try:
            with urllib.request.urlopen(pedido, timeout=30) as r:
                if r.status == 200:
                    enviados += 1
        except Exception as e:  # noqa: BLE001 — un aviso que falla no tumba la corrida
            print(f"  no se pudo avisar a {quien}: {type(e).__name__}")
    return enviados > 0


def _vencidas_sin_resolver(hoy):
    """Alertas publicadas que pasaron su fecha y nadie resolvió todavía.

    **Por qué existe, y por qué insiste.** Desde el 22/10/2026 FEMÓNOE es
    pública. Una alerta que pasó su plazo y sigue en el sitio sin resultado no
    es una alerta: es información vieja a la vista de cualquiera, y la
    plataforma vende exactamente lo contrario. Hasta hoy **nada vigilaba los
    vencimientos**: `vencer` se corre a mano y nadie avisaba que había llegado
    el día.

    A diferencia del aviso de señal repetida, **éste repite todos los días**. La
    señal que insiste se vuelve ruido; la alerta vencida sin resolver se vuelve
    peor cada día que pasa, porque el sitio sigue mostrándola.

    **No resuelve nada.** Leer el criterio contra el mundo y decir si ocurrió es
    juicio, y el juicio no se automatiza. Esto dice «llegó el día».
    """
    salida = []
    if not ALERTAS.exists():
        return salida
    for f in sorted(ALERTAS.glob("*.json")):
        if any(x in f.name for x in ("-contexto", "-indicadores", "-dictamen")):
            continue
        try:
            a = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if a.get("estado") != "publicada" or a.get("resultado"):
            continue
        try:
            vence = date.fromisoformat(str((a.get("juicio") or {}).get("vence"))[:10])
        except (TypeError, ValueError):
            continue
        if vence < hoy:
            salida.append((a, (hoy - vence).days))
    return sorted(salida, key=lambda x: -x[1])


def _texto_de_vencidas(vencidas):
    lineas = ["FEMÓNOE · alerta vencida sin resolver", ""]
    for a, dias in vencidas:
        j = a.get("juicio") or {}
        lineas.append(f"{a.get('pais') or a.get('iso3')} · {a.get('eje')} · {a['id']}")
        lineas.append(f"  venció el {j.get('vence')} — hace {dias} "
                      f"{'día' if dias == 1 else 'días'}")
        lineas.append(f"  dijo: {j.get('probabilidad')}")
        lineas.append(f"  {str(j.get('hecho_anunciado') or '')[:220]}")
        lineas.append("")
    lineas.append("El sitio la muestra como «pendiente de resolución», que es la "
                  "verdad pero no es un resultado.")
    lineas.append("")
    lineas.append("Se resuelve leyendo su criterio contra el mundo, y eso no lo hace "
                  "el robot:")
    lineas.append(f"  python alerta.py vencer {vencidas[0][0]['id']} "
                  "ocurrio|no_ocurrio|sin_evidencia")
    return "\n".join(lineas)


# Cuántos días de atraso se toleran antes de avisar. El detector evalúa el día
# de ayer, así que lo normal es 1. Dos quiere decir que una corrida no salió;
# tres, que hay algo roto.
DIAS_DE_ATRASO_QUE_AVISAN = 2


def _atraso_del_robot(hoy):
    """Hace cuántos días que el detector no evalúa un día nuevo.

    **Por qué está acá y no en la portada.** Estuvo un rato en la franja de
    arriba del sitio, y la dirección resolvió el 22/10/2026 sacarlo: el atraso
    es una falla de la casa, no un dato del mundo, y el lector no tiene por qué
    enterarse antes que la Oficina. Pero el dato no se tira — cambia de canal.
    Si el robot se detiene, la fecha del sitio se congela y **la plataforma
    sigue pareciendo al día mientras no mira nada**; eso tiene que llegarle a
    una persona, y por acá llega.
    """
    dias = sorted(p.stem for p in SENALES.glob("2*.json")) if SENALES.exists() else []
    if not dias:
        return None, "no hay ninguna corrida registrada"
    try:
        atraso = (hoy - date.fromisoformat(dias[-1])).days
    except ValueError:
        return None, f"la última corrida tiene una fecha ilegible: {dias[-1]!r}"
    if atraso < DIAS_DE_ATRASO_QUE_AVISAN:
        return atraso, None
    return atraso, (f"El último día evaluado es el {dias[-1]}: {atraso} días de atraso. "
                    "Lo normal es uno, porque el detector evalúa el día de ayer. "
                    "El sitio sigue mostrando esa fecha sin decir que es vieja.")



HECHOS_OFICIALES = RAIZ / "datos" / "eventos" / "vigia_organismo.json"


def _hechos_oficiales_nuevos(estado):
    """Los hechos que publican los propios organismos del Estado, avisados uno a uno.

    POR QUE EXISTE. La puerta G-8/S-9 declara una alerta cuando un organismo del
    propio Estado publica una medida de excepcion, y alcanza con UNA publicacion:
    no espera persistencia ni segunda jornada. Es la unica puerta que le sirve a
    un Estado chico, cuyos hechos son picos de un solo dia.

    Esa puerta dio CERO desde que existe, y el 27/11/2026 se midio por que: el
    padron eran 16 autoridades electorales de 21, con vocabulario electoral, en
    un ano sin elecciones; y el vigia corria en un servidor desplegado el 3/11,
    tres semanas antes de que se sumaran 38 fuentes nuevas, asi que ni siquiera
    las abria. Arreglado lo uno y lo otro, el primer hecho que entre por aca es
    la prueba de que la cadena funciona de punta a punta.

    LA DIRECCION PIDIO QUE SE LE AVISE. Se avisa por el mismo canal que ya usa
    la casa, dentro de una corrida que ya se paga: no cuesta un token ni depende
    de que nadie se acuerde de mirar.

    NO SE REPITE. Cada hecho se avisa una sola vez, por su identificador. El
    primero se anuncia como lo que es; los siguientes van en seco.
    """
    try:
        hechos = json.loads(HECHOS_OFICIALES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    ya = set(estado.get("hechos_oficiales_avisados", []))
    nuevos = [h for h in hechos if h.get("id") and h["id"] not in ya]
    return nuevos


def _texto_de_hechos_oficiales(nuevos, primera_vez):
    L = []
    if primera_vez:
        L += ["FEMONOE - PRIMER HECHO POR FUENTE OFICIAL", "",
              "Un organismo del Estado publico una medida de su propia materia. "
              "Es la primera vez que esta puerta produce algo: hasta hoy llevaba "
              "cero. Alcanza con una publicacion y no espera segunda jornada.", ""]
    else:
        L += ["FEMONOE - hecho por fuente oficial", ""]
    for h in nuevos[:5]:
        L += [f"{h.get('fecha','')} - {h.get('iso3','')} - {h.get('eje','')}",
              f"  {str(h.get('detalle',''))[:320]}",
              f"  Fuente: {h.get('fuente','')}", ""]
    if len(nuevos) > 5:
        L.append(f"(y {len(nuevos) - 5} mas)")
    L.append("Abre borrador y pasa al panel ciego. Nadie publica nada todavia.")
    return "\n".join(L)


def main():
    hoy = datetime.now(timezone.utc).date()

    # Antes que nada, si el robot mismo se detuvo: todo lo que sigue se calcula
    # sobre archivos que podrían tener días.
    atraso, aviso_atraso = _atraso_del_robot(hoy)
    if aviso_atraso:
        print(f"ATRASO: {aviso_atraso}")
        _mandar("FEMÓNOE · el robot se atrasó\n\n" + aviso_atraso)
    else:
        print(f"Atraso del robot: {atraso} día(s), que es lo normal.")

    # Después lo que tiene fecha cumplida, que es lo que ya está a la vista del
    # público. Va antes que las señales porque es deuda y no novedad.
    vencidas = _vencidas_sin_resolver(hoy)
    if vencidas:
        print(f"VENCIDAS SIN RESOLVER: {len(vencidas)}")
        for a, dias in vencidas:
            print(f"  {a['id']} · venció hace {dias} día(s)")
        _mandar(_texto_de_vencidas(vencidas))

    estado = {}
    if ESTADO.exists():
        try:
            estado = json.loads(ESTADO.read_text(encoding="utf-8"))
        except ValueError:
            estado = {}

    # LA PUERTA OFICIAL. Va antes que las señales porque es un hecho publicado
    # por el propio Estado, no un desvío estadístico, y porque la dirección
    # pidió expresamente que el primero le llegue.
    nuevos_of = _hechos_oficiales_nuevos(estado)
    if nuevos_of:
        primera = not estado.get("hechos_oficiales_avisados")
        print(f"HECHOS OFICIALES NUEVOS: {len(nuevos_of)}"
              + (" - ES EL PRIMERO DE LA PLATAFORMA" if primera else ""))
        _mandar(_texto_de_hechos_oficiales(nuevos_of, primera))
        estado["hechos_oficiales_avisados"] = sorted(
            set(estado.get("hechos_oficiales_avisados", []))
            | {h["id"] for h in nuevos_of})
        ESTADO.parent.mkdir(parents=True, exist_ok=True)
        ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")

    por_dia = _senales_recientes(hoy)
    if not por_dia:
        print("Aviso: todavía no hay señales guardadas.")
        return
    con_alerta = _con_alerta_abierta()
    pares = {p for dia in por_dia.values() for p in dia}
    avisados = 0
    for par in sorted(pares):
        iso3, eje = par
        clave = f"{iso3}|{eje}"
        seguidos = _seguidos(por_dia, hoy, par)
        if seguidos < DIAS_PARA_AVISAR:
            continue
        if par in con_alerta:
            # Ya tiene alerta viva: avisar sería repetirle a alguien algo que
            # ya está sobre su escritorio.
            estado.pop(clave, None)
            continue
        ya = estado.get(clave)
        if ya and (hoy - date.fromisoformat(ya["cuando"])).days < DIAS_PARA_OLVIDAR:
            continue
        ultimo = sorted(por_dia)[-1]
        senal = next((por_dia[d][par] for d in sorted(por_dia, reverse=True)
                      if par in por_dia[d]), {})
        texto = _texto(iso3, eje, senal, seguidos, _fecha_cercana(iso3, hoy))
        print(f"AVISO · {iso3} · {eje} · {seguidos} días seguidos")
        if _mandar(texto):
            estado[clave] = {"cuando": hoy.isoformat(), "dias": seguidos}
            avisados += 1
    # Lo que dejó de aparecer se olvida, para que vuelva a avisar si reaparece.
    for clave in list(estado):
        iso3, eje = clave.split("|", 1)
        if (iso3, eje) not in pares:
            estado.pop(clave)
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
    print(f"Aviso: {avisados} enviado(s); {len(pares)} par(es) mirado(s) en la ventana.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
