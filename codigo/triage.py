# -*- coding: utf-8 -*-
"""La pasada gratuita que abre el borrador de una alerta. No juzga.

**El problema que vino a resolver, medido el 17/11/2026.** En 56 días el
detector produjo **37 señales en 15 Estados** y la casa abrió **10 alertas**.
Desde el 22 de octubre —veintiséis días— produjo **12 señales más en 7 Estados**
y **no se abrió ni una**. No fallaba el detector, ni la cobertura, ni el tope de
cinco por semana: **fallaba que el paso que convierte una señal en alerta no
corría solo**. FEMÓNOE recolecta, detecta, maqueta y publica cada cuatro horas
sin que nadie la toque; el panel ciego sólo corría cuando alguien lo corría a
mano, en una conversación. Por eso las alertas aparecían cuando la dirección y
la Oficina se sentaban a trabajar, y no cuando pasaba algo en la región.

**Qué hace este programa, y qué NO hace.**

Hace: por cada señal nueva, le pregunta a un modelo **gratuito** si amerita
panel; para las que sí, corre `alerta.py abrir` —que no gasta tokens— y
`expediente.py`, que reúne serie, tasa base, calendario y prensa del país. El
resultado es un **borrador con su expediente listo**, esperando al panel.

**No hace: ningún juicio.** No fija el hecho anunciado, no fija banda de Kent,
no fija plazo, no publica. Eso es del panel ciego, del décimo hombre y de la
dirección, y así queda. La regla de la casa es automatizar el proceso y nunca
el juicio: **abrir el expediente es proceso; decir qué va a pasar es juicio.**

**Por qué falla hacia ABRIR y no hacia descartar.** Si el modelo no contesta,
si no hay clave o si su respuesta no se entiende, la señal **pasa igual**. Un
filtro que descarta en silencio cuando su modelo está caído es peor que no
tener filtro: la casa perdería señales sin enterarse, que es exactamente el
defecto que este programa vino a arreglar. El motivo de cada decisión queda
escrito, incluido «el modelo no contestó».

**El tope.** Como mucho TOPE_POR_PASADA borradores por corrida. Una ráfaga no
puede llenar la cola de la casa en una tarde, y el tope de cinco alertas nuevas
por semana sigue siendo de la dirección, no de este programa.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SENALES = RAIZ / "senales"
ALERTAS = RAIZ / "alertas"
COLA = RAIZ / "datos" / "cola-de-panel.json"
DIAS_ATRAS = 7              # una señal más vieja que esto ya no se abre
TOPE_POR_PASADA = 3
UA = "FEMONOE-robot/0.1 (Fundacion Sherman Kent; +https://fundacionkent.org)"
MODELOS = "https://api.groq.com/openai/v1/models"
CHARLA = "https://api.groq.com/openai/v1/chat/completions"
# QUÉ MODELO SE ELIGE, Y POR QUÉ ESTA LISTA Y NO OTRA.
#
# La primera corrida en el robot, el 17/11/2026, eligió
# `canopylabs/orpheus-arabic-saudi`, que es un modelo de VOZ: el filtro de la
# primera versión no lo atrapaba y la elección era «el primero que quede».
# Se copian las dos listas que el motor de automejora ya tenía probadas, en vez
# de inventar unas nuevas: una descarta lo que no escribe texto y la otra
# ordena por capacidad, para que el oficial de guardia sea el mejor modelo
# gratuito que la cuenta ofrezca ese día y no el primero del listado.
NO_ESCRIBEN = ("whisper", "guard", "orpheus", "tts", "embed", "rerank", "safeguard")
PREFERIDOS = ("gpt-oss-120b", "llama-3.3-70b", "qwen", "gpt-oss-20b", "allam")

SISTEMA = (
    "Sos un oficial de guardia de una oficina de inteligencia. Tu unico trabajo "
    "es decidir si una anomalia estadistica merece que un panel de analistas la "
    "estudie, o si es ruido. NO sos el analista: no digas que va a pasar, no "
    "pongas probabilidades, no pronostiques. Respondes en espanol rioplatense, "
    "en este formato exacto y nada mas:\n"
    "VEREDICTO: PANEL o RUIDO\n"
    "MOTIVO: una sola oracion, concreta."
)


def _clave():
    return os.environ.get("GROQ_CLAVE") or os.environ.get("GROQ_API_KEY")


def _modelo(clave):
    try:
        req = urllib.request.Request(MODELOS, headers={
            "Authorization": "Bearer " + clave, "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            datos = json.load(r).get("data") or []
    except Exception:  # noqa: BLE001
        return None
    nombres = [m.get("id", "") for m in datos]
    buenos = [m for m in nombres if not any(x in m.lower() for x in NO_ESCRIBEN)]
    if not buenos:
        return None
    return next((m for p in PREFERIDOS for m in buenos if p in m.lower()), buenos[0])


def _preguntar(clave, modelo, pregunta):
    cuerpo = json.dumps({
        "model": modelo, "temperature": 0.2, "max_tokens": 400,
        "messages": [{"role": "system", "content": SISTEMA},
                     {"role": "user", "content": pregunta}]}).encode("utf-8")
    req = urllib.request.Request(CHARLA, data=cuerpo, headers={
        "Authorization": "Bearer " + clave, "User-Agent": UA,
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    return (d.get("choices") or [{}])[0].get("message", {}).get("content", "")


def _pregunta(s, pais):
    det = "; ".join(
        "{} = {} contra una mediana de {}".format(
            x.get("senal"), x.get("valor"), x.get("mediana"))
        for x in (s.get("detalle") or [])[:4])
    fam = ", ".join(s.get("familias") or []) or "sin declarar"
    extra = ""
    if s.get("fuente_unica"):
        extra += " (FUENTE UNICA)"
    if s.get("hecho_duro"):
        extra += " (HECHO DURO)"
    return (
        "Estado: {}. Eje: {}. Dia: {}.\n".format(pais, s.get("eje"), s.get("fecha"))
        + "Lo que se salio de lo normal: {}.\n".format(det or "sin detalle")
        + "Familias de fuentes que lo sostienen: {}{}.\n\n".format(fam, extra)
        + "Esto amerita que un panel de analistas lo estudie, o es ruido "
          "estadistico? Tene en cuenta que la oficina puede estudiar pocas por "
          "semana, asi que RUIDO es una respuesta legitima y frecuente.")


def _ya_tiene_alerta(fecha, iso3, eje):
    """Esta señal ya tiene expediente abierto?

    Se mira por Estado y eje en una ventana, no por fecha exacta: abrir dos
    alertas del mismo Estado y el mismo eje en días seguidos es duplicar el
    mismo hecho con dos expedientes.
    """
    d0 = date.fromisoformat(fecha)
    inicial = (eje or " ")[0].upper()
    for f in ALERTAS.glob("????-??-??-???-?.json"):
        n = f.name
        try:
            d1 = date.fromisoformat(n[:10])
        except ValueError:
            continue
        if n[11:14] == iso3 and n[15] == inicial and abs((d0 - d1).days) <= DIAS_ATRAS:
            return n[:-5]
    return None


def _veredicto(clave, modelo, s, iso3):
    """(veredicto, motivo). Ante cualquier duda, PANEL: ver la cabecera."""
    if not (clave and modelo):
        return "PANEL", "sin modelo gratuito disponible: pasa igual, por diseño"
    try:
        r = _preguntar(clave, modelo, _pregunta(s, iso3)) or ""
    except Exception as e:  # noqa: BLE001
        return "PANEL", "el modelo no contestó ({}): pasa igual".format(type(e).__name__)
    lineas = [x.strip() for x in r.splitlines() if x.strip()]
    cabeza = next((x for x in lineas if x.upper().startswith("VEREDICTO")), "")
    mot = next((x for x in lineas if x.upper().startswith("MOTIVO")), "")
    motivo = mot.split(":", 1)[-1].strip() or "el modelo no dio motivo"
    if "RUIDO" in cabeza.upper():
        return "RUIDO", motivo
    if "PANEL" in cabeza.upper():
        return "PANEL", motivo
    return "PANEL", "no se entendió la respuesta, pasa igual: " + r[:80]


def main():
    hoy = date.today()
    clave = _clave()
    modelo = _modelo(clave) if clave else None
    cola, abiertos = [], 0

    for k in range(DIAS_ATRAS, -1, -1):
        dia = (hoy - timedelta(days=k)).isoformat()
        f = SENALES / (dia + ".json")
        if not f.exists():
            continue
        try:
            senales = json.loads(f.read_text(encoding="utf-8")).get("senales") or []
        except ValueError:
            continue
        for n, s in enumerate(senales, 1):
            iso3, eje = s.get("iso3"), s.get("eje")
            if not iso3:
                continue
            ya = _ya_tiene_alerta(dia, iso3, eje)
            if ya:
                cola.append({"dia": dia, "iso3": iso3, "eje": eje,
                             "veredicto": "YA ABIERTA", "motivo": "existe " + ya})
                continue

            veredicto, motivo = _veredicto(clave, modelo, s, iso3)
            fila = {"dia": dia, "iso3": iso3, "eje": eje, "n": n,
                    "veredicto": veredicto, "motivo": motivo,
                    "modelo": modelo or "sin clave"}

            if veredicto == "PANEL" and abiertos < TOPE_POR_PASADA:
                try:
                    subprocess.run([sys.executable, "alerta.py", "abrir", dia, str(n)],
                                   cwd=str(RAIZ), check=True, capture_output=True,
                                   timeout=120)
                    ident = _ya_tiene_alerta(dia, iso3, eje)
                    fila["abierta"] = ident
                    abiertos += 1
                    if ident:
                        subprocess.run([sys.executable, "expediente.py", ident],
                                       cwd=str(RAIZ), check=False, capture_output=True,
                                       timeout=180)
                        fila["expediente"] = "alertas/" + ident + "-expediente.md"
                except Exception as e:  # noqa: BLE001
                    fila["abierta"] = "no se pudo abrir ({})".format(type(e).__name__)
            elif veredicto == "PANEL":
                fila["abierta"] = "tope de la pasada alcanzado; vuelve en la próxima"
            cola.append(fila)

    COLA.parent.mkdir(parents=True, exist_ok=True)
    COLA.write_text(json.dumps({
        "medido": hoy.isoformat(),
        "modelo": modelo or "sin clave",
        "_nota": ("Pasada gratuita de guardia. Decide si una señal merece panel; "
                  "NO juzga. Si el modelo no contesta, la señal pasa igual: un "
                  "filtro que descarta en silencio cuando su modelo está caído "
                  "es peor que no tener filtro."),
        "abiertos_en_esta_pasada": abiertos,
        "cola": cola,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    panel = [c for c in cola if c["veredicto"] == "PANEL"]
    ruido = [c for c in cola if c["veredicto"] == "RUIDO"]
    print("Triage ({}): {} señales miradas · {} a panel · {} ruido · "
          "{} borrador(es) abierto(s)".format(
              modelo or "sin clave", len(cola), len(panel), len(ruido), abiertos))
    for c in cola:
        if c["veredicto"] != "YA ABIERTA":
            print("   {} {} {:14s} {:6s} · {}".format(
                c["dia"], c["iso3"], (c.get("eje") or "")[:14],
                c["veredicto"], c["motivo"][:80]))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
