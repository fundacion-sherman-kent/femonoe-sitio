# -*- coding: utf-8 -*-
"""Vigía de organismos · el juez del alambre de trampa (señal G-7).

**El reparto.** El Worker de Cloudflare (`vigia/worker.js`) mira las autoridades
electorales cada dos minutos y dice únicamente «algo se movió». No puede decir
más: el plan gratuito le da 10 ms de procesador por corrida. Este programa es el
que lee, compara y decide si lo que se movió importa. La división no es
prolijidad: es la regla de la casa. **Se automatiza el proceso, nunca el
juicio.**

**Qué hace, en orden.**
  1. Retira del vigía las novedades pendientes. No las borra todavía.
  2. De cada organismo que se movió, trae la portada y saca sus titulares.
  3. Los compara con la instantánea guardada y queda con **los titulares
     nuevos**, textuales.
  4. Un titular nuevo que menciona vocabulario de calendario electoral
     —convocatoria, cronograma, postergación, segunda vuelta— sale como hecho
     con fuente y hora. Los demás quedan registrados como movimiento sin señal,
     que también es dato: un organismo que publica y no publica fechas es un
     organismo que no publicó la fecha.
  5. Recién entonces confirma al vigía que lo guardó, y el vigía lo borra.

**Lo que este colector NO hace.** No interpreta. Un titular que dice
«Resolución 1234/2026» entra como lo que es: un titular publicado por el
organismo tal día. Qué significa lo decide la Oficina, y si decide algo, lo
decide con una técnica declarada.

**Lo que todavía no está medido.** La *sensibilidad*: que el vigía dispare ante
una publicación real. Lo que se midió el 2/10/2026 es lo contrario —que no
dispara sin motivo, 13 de 15 organismos quietos en tres pasadas—. Hasta que
pase la primera publicación verificada, la sensibilidad es un vacío declarado.

**Si el vigía no está desplegado**, este programa no falla: avisa y se va. La
corrida diaria no se pone en rojo por una capa que la dirección todavía no
autorizó.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import vocabulario as _voc
from comun import UA, guardar_eventos, guardar_serie, pedir

RAIZ = Path(__file__).resolve().parent.parent
VIGIA = RAIZ / "vigia"
INSTANTANEAS = VIGIA / "instantaneas"
TOPE_CUERPO = 300 * 1024
TOPE_PIEZA = 400
MINIMO_TITULAR = 8

ETIQUETA = re.compile(r"<[^>]+>")
ESPACIOS = re.compile(r"\s+")
TITULO = re.compile(r"<h[1-4][^>]*>(.{1,%d}?)</h[1-4]>" % TOPE_PIEZA, re.I | re.S)
ENLACE = re.compile(r"<a\b[^>]*>(.{1,%d}?)</a>" % TOPE_PIEZA, re.I | re.S)
SIN_TILDE = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")


def titulares(html: str) -> list:
    """Los titulares de una portada, textuales y sin repetir.

    No tiene que coincidir con la huella del Worker, y a propósito: el Worker
    compara su huella sólo contra sí misma. Dos huellas que se creen iguales y
    no lo son ya costaron una medición falsa en la señal de coordinación el
    27/9/2026, y ese defecto no se repite por no necesitarlo.
    """
    vistos, salida = set(), []
    for patron in (TITULO, ENLACE):
        for cruda in patron.findall(html):
            t = ESPACIOS.sub(" ", ETIQUETA.sub(" ", cruda)).strip()
            if len(t) > MINIMO_TITULAR and t.lower() not in vistos:
                vistos.add(t.lower())
                salida.append(t)
    return salida


def _llamar(url: str, ruta: str, clave: str, cuerpo: dict | None = None):
    datos = json.dumps(cuerpo or {}).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + ruta, data=datos, method="POST",
                                 headers={"Authorization": f"Bearer {clave}",
                                          "Content-Type": "application/json",
                                          "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def instantanea(clave: str) -> dict:
    a = INSTANTANEAS / f"{clave}.json"
    return json.loads(a.read_text(encoding="utf-8")) if a.exists() else {}


def guardar_instantanea(clave: str, titulares_: list, cuando: str) -> None:
    INSTANTANEAS.mkdir(parents=True, exist_ok=True)
    (INSTANTANEAS / f"{clave}.json").write_text(json.dumps(
        {"clave": clave, "visto": cuando, "titulares": titulares_},
        ensure_ascii=False, indent=1), encoding="utf-8")


def configuracion():
    archivo = VIGIA / "url.txt"
    clave = os.environ.get("WA_ROBOT_CLAVE", "")
    if not archivo.exists():
        print("Vigía: no está desplegado (falta vigia/url.txt). "
              "Se despliega con el flujo «desplegar el vigía de organismos».")
        return None, None
    if not clave:
        print("Vigía: falta la clave WA_ROBOT_CLAVE en el entorno. No se retira nada.")
        return None, None
    return archivo.read_text(encoding="utf-8").strip(), clave


def estado():
    url, clave = configuracion()
    if not url:
        return
    d = _llamar(url, "/estado", clave)
    ub = d.get("ultimo_barrido") or {}
    print(f"Último sello de barrido: {ub.get('cuando') or 'ninguno'} · "
          f"pendientes de retirar: {d.get('pendientes')}")
    # El sello se escribe una corrida de cada cinco, pero lleva el resultado de
    # las que miró. Se imprime, porque es la única prueba directa de que el
    # disparador corrió y de qué le contestó cada organismo.
    for m in ub.get("mirados", []):
        detalle = f" · {m.get('detalle')}" if m.get("detalle") else ""
        print(f"  en ese barrido · {m.get('clave')}: {m.get('estado')}{detalle}")
    padron = d.get("padron", [])
    print(f"\n{'organismo':<10}{'último visto':<26}{'qué contestó':<36}nombre")
    for p in padron:
        # 26 de ancho porque una marca de tiempo ISO mide 24: con 22 la columna
        # se comía la siguiente y el informe salía ilegible.
        res = p.get("resultado") or "—"
        if p.get("ruidosa"):
            res += " · RUIDOSA"
        print(f"{(p.get('clave') or p['iso3']):<10}{(p.get('visto') or '—'):<26}"
              f"{res:<36}{p.get('organismo', '')}")

    def _clave(p):
        return p.get("clave") or p["iso3"]

    nunca = [_clave(p) for p in padron if not p.get("visto")]
    fallan = [_clave(p) for p in padron if p.get("visto")
              and str(p.get("resultado") or "").startswith(("HTTP", "no respondió",
                                                            "vino sin titulares", "ruidosa"))]
    vigilados = [_clave(p) for p in padron if p.get("titulares")]
    print(f"\nVigilados con huella propia: {len(vigilados)} de {len(padron)}")
    if fallan:
        print(f"Le cierran la puerta al vigía: {', '.join(fallan)}. **Mirados y "
              f"rechazados, no ausentes**: varios de estos sitios abren "
              f"normalmente en un navegador y sólo rechazan a la máquina. Pasan "
              f"a la revisión diaria.")
    if nunca:
        print(f"Sin mirar todavía: {', '.join(nunca)}. El padrón entero tarda "
              f"media hora en barrerse; si alguno sigue así después de una hora, "
              f"su huella no entra en los 10 ms.")


def _juzgar(clave_org, iso3, organismo, sitio, html, cuando, acum,
            materia="electoral", idioma="es"):
    """Compara los titulares de una portada con su instantánea y declara.

    Es el único juez, y lo usan los dos caminos: lo que trae el vigía de
    Cloudflare y la revisión propia del robot. Tener dos copias de esta lógica
    sería tener dos criterios, y entonces un mismo organismo diría cosas
    distintas según desde dónde se lo mire.
    """
    ahora = titulares(html)
    if not ahora:
        print(f"  {clave_org}: la portada vino sin titulares. No se juzga.")
        return False

    previos = {t.lower() for t in instantanea(clave_org).get("titulares", [])}
    nuevos = [t for t in ahora if t.lower() not in previos]
    guardar_instantanea(clave_org, ahora, cuando)
    # La serie va por Estado: dos organismos del mismo Estado suman.
    acum["por_pais"][iso3] = acum["por_pais"].get(iso3, 0) + len(nuevos)

    if not previos:
        print(f"  {clave_org}: primera instantánea, {len(ahora)} titulares. "
              f"No se declara cambio contra la nada.")
        return True

    con_senal = 0
    eje = _voc.eje_de(materia)
    for t in nuevos:
        palabra = _voc.menciona(t, materia, idioma)
        if not palabra:
            # Lo que NO coincide también se guarda. Es lo único que muestra qué
            # se está perdiendo el vocabulario, y una tasa de disparo no puede
            # mostrarlo: un vocabulario demasiado angosto no dispara, y por eso
            # parece que no pasa nada.
            acum["sin_senal"].append((iso3, t))
            continue
        con_senal += 1
        acum["por_eje"][(iso3, eje)] = acum["por_eje"].get((iso3, eje), 0) + 1
        acum["eventos"].append({
            # El identificador lleva la hora de la mirada, no la de la corrida:
            # así dos corridas que vean lo mismo no lo cuentan dos veces.
            "id": f"vigia-{clave_org}-{cuando}-{abs(hash(t.lower())) % 10**10}",
            "fecha": str(cuando)[:10],
            "iso3": iso3, "senal": "vigia_organismo",
            "eje": eje, "familia": "oficial", "materia": materia,
            "detalle": f"«{t[:220]}» — publicado por {organismo}; "
                       f"coincide con «{palabra}» ({materia})",
            "fuente": organismo, "url": sitio})
    if nuevos:
        print(f"  {clave_org}: {len(nuevos)} titulares nuevos, "
              f"{con_senal} con vocabulario de calendario")
    return True


def _padron():
    d = json.loads((RAIZ / "autoridades.json").read_text(encoding="utf-8"))
    return {(a.get("clave") or a["iso3"]): a for a in d.get("autoridades", [])
            if a.get("sitio")}


# Resultados del vigía que significan «no pude mirarlo»: son los que este
# programa se reparte. «sin titulares» NO entra: esa portada no tiene texto que
# mirar desde ninguna red, y meterla acá sería repetir la ceguera con otro
# disfraz.
RECHAZOS = ("HTTP", "no respondió")


def revision_propia(url, clave, acum, cuando):
    """Los organismos que el vigía no alcanza, mirados desde el robot.

    **Por qué hace falta.** Medido el 2/10/2026 en tres redes distintas: seis
    organismos rechazan al vigía desde Cloudflare, los seis responden 200 desde
    la máquina de la Oficina —con el nombre propio de la casa y sin disfraz— y
    cinco de los seis responden también desde el robot de GitHub. Así que el
    problema nunca fue quién pregunta: es desde dónde. Preguntar desde la red
    que sí llega sube la cobertura de 8 organismos a 13.

    **Qué se pierde.** Latencia: el vigía barre cada media hora y esto corre una
    vez por hora. Peor que el vigía, incomparablemente mejor que no mirar.

    **Por qué la lista no está escrita a mano.** Sale del estado del propio
    vigía en cada corrida. Si mañana un organismo vuelve a aceptar a Cloudflare,
    deja de mirarse acá sin que nadie toque nada; y si uno nuevo empieza a
    rechazarlo, entra solo. Una lista fija envejecería en silencio.
    """
    try:
        estado = _llamar(url, "/estado", clave)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"Revisión propia: no se pudo leer el estado del vigía "
              f"({type(e).__name__}). No se mira nada por esta vía.")
        return
    padron = _padron()
    rechazados = [p for p in estado.get("padron", [])
                  if str(p.get("resultado") or "").startswith(RECHAZOS)]
    if not rechazados:
        print("Revisión propia: el vigía llega a todos. Nada que repartirse.")
        return

    print(f"Revisión propia: {len(rechazados)} organismos que el vigía no alcanza")
    logrados, fallados, sin_texto = [], [], []
    for p in rechazados:
        clave_org = p.get("clave") or p.get("iso3")
        a = padron.get(clave_org)
        if not a:
            continue
        # Dos intentos, y no por insistir: **la Junta Central Electoral de la
        # República Dominicana alterna** entre su portada y una pantalla
        # intermedia de protección. Medido el 2/10/2026: 73 kB con 128 titulares
        # desde la Oficina, y 0 titulares desde el robot en la misma hora. Un
        # segundo pedido cae del otro lado de la moneda bastantes veces como
        # para que valga los dos segundos que cuesta.
        visto = False
        for intento in (1, 2):
            try:
                html = pedir(a["sitio"], segundos=60)[:TOPE_CUERPO].decode("utf-8", "replace")
            except Exception as e:  # noqa: BLE001 — uno que falla no tumba la corrida
                if intento == 2:
                    fallados.append(f"{clave_org} ({type(e).__name__})")
                continue
            if _juzgar(clave_org, a["iso3"], a["nombre"], a["sitio"], html, cuando, acum,
                   a.get("materia", "electoral"), a.get("idioma", "es")):
                logrados.append(clave_org)
                visto = True
                break
            if intento == 1:
                time.sleep(3)
        if not visto and clave_org not in [f.split(" ")[0] for f in fallados]:
            sin_texto.append(clave_org)
    print(f"  mirados desde el robot: {', '.join(logrados) or 'ninguno'}")
    if sin_texto:
        print(f"  respondieron sin texto que mirar: {', '.join(sin_texto)}. "
              f"Sirven una pantalla intermedia en lugar de su portada, y no son "
              f"vigilables por titulares desde ninguna red.")
    if fallados:
        print(f"  tampoco responden acá: {', '.join(fallados)}. "
              f"Estos no los alcanza ninguna de las dos redes y quedan en "
              f"revisión manual, declarados como tales.")


def main():
    url, clave = configuracion()
    if not url:
        return
    cuando = datetime.now(timezone.utc).isoformat(timespec="seconds")
    hoy = cuando[:10]
    acum = {"eventos": [], "por_pais": {}, "sin_senal": [], "por_eje": {}}
    confirmadas = []

    # 1 · Lo que encontró el vigía de Cloudflare, que es el camino rápido.
    try:
        pendientes = _llamar(url, "/novedades", clave).get("novedades", [])
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"Vigía: no se pudo retirar ({type(e).__name__}). No se toca nada.")
        pendientes = []
    if pendientes:
        print(f"Vigía: {len(pendientes)} organismos se movieron")
    else:
        print("Vigía: sin novedades. El padrón quedó quieto desde la última corrida.")
    for n in pendientes:
        clave_org = n.get("clave") or n.get("iso3")
        try:
            html = pedir(n["sitio"], segundos=60)[:TOPE_CUERPO].decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            print(f"  {clave_org}: se movió pero no respondió al leerlo "
                  f"({type(e).__name__}). Queda pendiente para la próxima.")
            continue
        ficha = _padron().get(clave_org, {})
        _juzgar(clave_org, n.get("iso3"), n.get("organismo", "el organismo"),
                n.get("sitio", ""), html, n.get("cuando", cuando), acum,
                ficha.get("materia", "electoral"), ficha.get("idioma", "es"))
        confirmadas.append(n["llave"])

    # 2 · Y los que el vigía no alcanza, mirados desde acá.
    revision_propia(url, clave, acum, cuando)

    guardar_serie("vigia_titulares_nuevos",
                  [(hoy, iso3, n) for iso3, n in acum["por_pais"].items()])
    # Una serie por eje: es lo que convierte al vigía en una FAMILIA que el
    # detector puede contar, y no en un registro suelto de eventos.
    for eje, serie in (("gobernabilidad", "oficial_gobernabilidad"),
                       ("seguridad", "oficial_seguridad"),
                       ("entorno informativo", "oficial_entorno")):
        filas = [(hoy, iso3, n) for (iso3, e), n in acum["por_eje"].items() if e == eje]
        if filas:
            guardar_serie(serie, filas)
    guardar_eventos("vigia_organismo", acum["eventos"])

    # Se confirma recién ahora. Si la corrida se cayó antes de esta línea, las
    # novedades siguen en el vigía y la corrida siguiente las vuelve a tomar.
    if confirmadas:
        try:
            borradas = _llamar(url, "/visto", clave, {"llaves": confirmadas}).get("borradas")
            print(f"Confirmadas y borradas del vigía: {borradas}")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"Vigía: se procesó todo pero no se pudo confirmar ({type(e).__name__}). "
                  f"La próxima corrida lo verá de nuevo; los hechos no se duplican "
                  f"porque el identificador lleva la hora de la mirada.")

    print(f"Total: {len(acum['eventos'])} hechos de calendario · "
          f"{len(acum['sin_senal'])} titulares nuevos sin vocabulario de calendario")
    for iso3, t in acum["sin_senal"][:10]:
        print(f"    sin señal · {iso3} · {t[:110]}")




if __name__ == "__main__":
    if "--estado" in sys.argv:
        estado()
    else:
        main()
