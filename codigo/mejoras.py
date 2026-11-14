# -*- coding: utf-8 -*-
"""Motor de automejora de FEMÓNOE · mide, detecta y propone. No aplica nada.

La dirección lo pidió el 23/9/2026: la plataforma tiene que autoaprender, mejorar
sola y **proponer mejoras continuas**. Esto es esa máquina, y corre una vez por
semana en el robot, gratis y sin gastar un token.

Mira cinco cosas y escribe lo que encuentra en `mejoras/AAAA-MM-DD.md`:

1. **El pulso.** Cuántas señales por semana están saliendo, contra las ~5 con que
   se calibraron los umbrales. Si se desbordan o se apagan, lo dice con números.
2. **La salud de cada fuente.** Cuándo fue su último dato, a cuántos Estados
   llega, y si su volumen se derrumbó o se disparó contra su propia historia. Así
   se detecta sola una fuente que se muere —como pasó con ACLED y su atraso de
   doce meses— en vez de descubrirlo por casualidad.
3. **La cobertura de los 33.** Qué Estados están peor mirados, contando series
   con dato y fuentes en el padrón. El Caribe oriental es el sospechoso de
   siempre.
4. **La calibración.** De las alertas vencidas, cuántas ocurrieron por banda del
   léxico de Kent, contra el rango que esa banda declara en `doctrina/lexico.md`.
   Si una banda viene inflada, propone corregirla.
5. **Lo que falta.** Fuentes candidatas para los Estados peor cubiertos. Esta es
   la única parte que usa un modelo, y usa uno **gratuito** de Groq: el más capaz
   que la cuenta ofrezca ese día, elegido solo. Sin clave, el motor corre igual y
   lo dice.

**Lo que este programa nunca hace: cambiar un umbral, agregar una fuente o tocar
una alerta.** Propone; incorporar es decisión humana. Es la misma regla que rige
en SIWA y la que separa automatizar el proceso de automatizar el juicio.

  python mejoras.py            escribe el informe de la semana
  python mejoras.py --ver      muestra el último informe
"""
import csv
import json
import re
import os
import statistics
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SERIES = RAIZ / "datos" / "series"
INFORMES = RAIZ / "mejoras"
CONF = json.loads((RAIZ / "umbrales.json").read_text(encoding="utf-8"))
PADRON = json.loads((RAIZ / "padron.json").read_text(encoding="utf-8"))["estados"]
NOMBRE = {p["iso3"]: p["nombre"] for p in PADRON}
UA = "FEMONOE-robot/0.1 (Fundacion Sherman Kent; +https://fundacionkent.org)"

# Rangos del léxico de la casa (doctrina/lexico.md). No son invención de acá.
RANGOS = {
    "casi con certeza no": (1, 5), "muy improbable": (5, 20), "improbable": (20, 40),
    "posibilidades parejas": (40, 60), "probable": (60, 80), "muy probable": (80, 95),
    "casi con certeza": (95, 99),
}
SENALES_OBJETIVO = 5          # por semana, con que se calibraron los umbrales v0.5
DIAS_FUENTE_MUERTA = 14


# --------------------------------------------------------------------------
ES_ALERTA = re.compile(r"^\d{4}-\d{2}-\d{2}-[A-Z]{3}-[GSI]$")


def _senales(dias=90):
    salida = []
    desde = date.today() - timedelta(days=dias)
    for archivo in sorted((RAIZ / "senales").glob("2*.json")):
        try:
            if date.fromisoformat(archivo.stem) < desde:
                continue
        except ValueError:
            continue
        registro = json.loads(archivo.read_text(encoding="utf-8"))
        for s in registro["senales"]:
            salida.append({**s, "fecha": registro["fecha"]})
    return salida


def _dias_cubiertos(dias=90):
    """Cuántos días de los últimos N corrió el detector. Sin esto, «señales por
    semana» miente: no es lo mismo poco ruido que poco tiempo midiendo."""
    desde = date.today() - timedelta(days=dias)
    cuenta = 0
    for archivo in (RAIZ / "senales").glob("2*.json"):
        try:
            if date.fromisoformat(archivo.stem) >= desde:
                cuenta += 1
        except ValueError:
            continue
    return cuenta


def pulso():
    dias = _dias_cubiertos()
    senales = _senales()
    if not dias:
        return {"dias": 0, "por_semana": 0, "veredicto": "El detector todavía no corrió.",
                "propuesta": None, "por_eje": {}}
    por_semana = len(senales) / dias * 7
    if dias < 21:
        return {"dias": dias, "senales": len(senales), "por_semana": round(por_semana, 1),
                "por_eje": {s["eje"]: sum(1 for x in senales if x["eje"] == s["eje"])
                            for s in senales},
                "veredicto": f"Sin juicio todavía: {dias} días de corrida. Hacen falta 21.",
                "propuesta": None}
    por_eje = {}
    for s in senales:
        por_eje[s["eje"]] = por_eje.get(s["eje"], 0) + 1
    if por_semana > SENALES_OBJETIVO * 1.6:
        veredicto = "Se está desbordando."
        propuesta = (f"Subir el umbral de las señales que más aportan. Salen "
                     f"{por_semana:.1f} por semana contra las {SENALES_OBJETIVO} previstas: "
                     f"a ese ritmo el juicio humano no llega.")
    elif por_semana < SENALES_OBJETIVO * 0.4:
        veredicto = "Se está apagando."
        propuesta = (f"Bajar el umbral o sumar fuentes: salen {por_semana:.1f} señales por "
                     f"semana. Con tan pocas no se junta la calibración de 20 alertas.")
    else:
        veredicto = "En régimen."
        propuesta = None
    return {"dias": dias, "senales": len(senales), "por_semana": round(por_semana, 1),
            "por_eje": por_eje, "veredicto": veredicto, "propuesta": propuesta}


# --------------------------------------------------------------------------
def _leer(archivo):
    filas = []
    with archivo.open(encoding="utf-8") as fh:
        for fila in csv.DictReader(fh):
            try:
                filas.append((date.fromisoformat(fila["fecha"]), fila["iso3"],
                              float(fila["valor"] or 0)))
            except (ValueError, KeyError, TypeError):
                continue
    return filas


def fuentes():
    hoy = date.today()
    salida = []
    for archivo in sorted(SERIES.glob("*.csv")):
        filas = _leer(archivo)
        if not filas:
            salida.append({"serie": archivo.stem, "estado": "vacía", "detalle": "sin datos"})
            continue
        con_valor = [f for f in filas if f[2] > 0]
        ultimo = max((f[0] for f in con_valor), default=None)
        atraso = (hoy - ultimo).days if ultimo else None
        ventana = sum(f[2] for f in filas if hoy - timedelta(days=30) <= f[0] <= hoy)
        previa = sum(f[2] for f in filas
                     if hoy - timedelta(days=60) <= f[0] < hoy - timedelta(days=30))
        estados = len({f[1] for f in filas if f[0] >= hoy - timedelta(days=30) and f[2] > 0})
        # «Nueva» no es tener pocos días desde el primer dato: es no haber estado
        # midiendo. Una serie que el mes pasado sólo trajo dato tres días no se
        # disparó, arrancó. Compararla contra ese mes sería inventar una anomalía.
        dias_previos = len({f[0] for f in con_valor
                            if hoy - timedelta(days=60) <= f[0] < hoy - timedelta(days=30)})
        if dias_previos < 10 and atraso is not None and atraso <= DIAS_FUENTE_MUERTA:
            estado, detalle = "nueva", (f"sólo {dias_previos} días con dato en el mes previo: "
                                        f"está arrancando, no se puede comparar")
        elif atraso is None or atraso > DIAS_FUENTE_MUERTA:
            estado, detalle = "muerta", f"último dato hace {atraso} días" if atraso else "nunca trajo dato"
        elif previa and ventana < previa * 0.4:
            estado, detalle = "encogiendo", f"{ventana:.0f} contra {previa:.0f} el mes previo"
        elif previa and ventana > previa * 4:
            estado, detalle = "desbordada", f"{ventana:.0f} contra {previa:.0f} el mes previo"
        else:
            estado, detalle = "viva", f"{ventana:.0f} en 30 días, {estados} Estados"
        salida.append({"serie": archivo.stem, "estado": estado, "detalle": detalle,
                       "atraso_dias": atraso, "estados_30d": estados})
    return salida


# --------------------------------------------------------------------------
def cobertura():
    hoy = date.today()
    con_dato = {p["iso3"]: 0 for p in PADRON}
    for archivo in SERIES.glob("*.csv"):
        vistos = {f[1] for f in _leer(archivo) if f[0] >= hoy - timedelta(days=30) and f[2] > 0}
        for iso in vistos:
            if iso in con_dato:
                con_dato[iso] += 1
    padron_redes = json.loads((RAIZ / "redes.json").read_text(encoding="utf-8"))
    fuentes_por_pais = {p["iso3"]: 0 for p in PADRON}
    for clave in ("telegram", "youtube", "mastodon", "rss", "bluesky"):
        for entrada in padron_redes.get(clave, []):
            iso = entrada.get("iso3")
            if iso in fuentes_por_pais and entrada.get("activo", True):
                fuentes_por_pais[iso] += 1
    filas = [{"iso3": iso, "pais": NOMBRE[iso], "series": con_dato[iso],
              "fuentes": fuentes_por_pais[iso],
              "puntaje": con_dato[iso] * 2 + min(fuentes_por_pais[iso], 10)}
             for iso in con_dato]
    filas.sort(key=lambda f: f["puntaje"])
    return filas


# --------------------------------------------------------------------------
def calibracion():
    carpeta = RAIZ / "alertas"
    vencidas = []
    if carpeta.exists():
        for archivo in carpeta.glob("*.json"):
            if not ES_ALERTA.match(archivo.stem):
                continue
            a = json.loads(archivo.read_text(encoding="utf-8"))
            if a.get("estado") == "vencida":
                vencidas.append(a)
    if not vencidas:
        return {"total": 0, "bandas": [], "propuesta": None}
    bandas = []
    propuestas = []
    for banda, (bajo, alto) in RANGOS.items():
        de_la_banda = [a for a in vencidas if a["juicio"].get("probabilidad") == banda]
        calificables = [a for a in de_la_banda if a["resultado"]["valor"] != "sin_evidencia"]
        if len(calificables) < 5:      # con menos de cinco no se corrige nada
            if de_la_banda:
                bandas.append({"banda": banda, "n": len(de_la_banda), "medido": None,
                               "nota": "muestra corta: no se corrige"})
            continue
        ok = sum(1 for a in calificables if a["resultado"]["valor"] == "ocurrio")
        medido = ok / len(calificables) * 100
        bandas.append({"banda": banda, "n": len(calificables), "medido": round(medido),
                       "rango": [bajo, alto]})
        if medido < bajo:
            propuestas.append(f"«{banda}» viene inflada: se cumplió el {medido:.0f} % de "
                              f"{len(calificables)} casos, contra el {bajo}–{alto} % que "
                              f"declara el léxico. Bajar una banda lo anunciado en esa franja.")
        elif medido > alto:
            propuestas.append(f"«{banda}» viene subestimada: se cumplió el {medido:.0f} % de "
                              f"{len(calificables)} casos, por encima del {bajo}–{alto} %.")
    return {"total": len(vencidas), "bandas": bandas,
            "propuesta": " ".join(propuestas) if propuestas else None}


# --------------------------------------------------------------------------
def _llama(pregunta, sistema):
    """El único tramo que usa un modelo, y usa uno gratuito. Cada final posible
    devuelve su motivo: «sin clave» no es lo mismo que «no hay modelo» ni que
    «no respondió», y confundirlos deja al informe diciendo una cosa por otra."""
    clave = os.environ.get("GROQ_CLAVE") or os.environ.get("GROQ_API_KEY")
    if not clave:
        return {"modelo": "sin clave", "texto": ""}
    cab = {"Authorization": f"Bearer {clave}", "User-Agent": UA,
           "Content-Type": "application/json"}
    try:
        req = urllib.request.Request("https://api.groq.com/openai/v1/models", headers=cab)
        with urllib.request.urlopen(req, timeout=60) as r:
            modelos = [m["id"] for m in json.load(r).get("data", [])]
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            KeyError, ValueError) as e:
        return {"modelo": "error", "texto": f"No se pudo pedir la lista de modelos: {e}"}
    # El catálogo gratuito cambia solo: el 23/9/2026 Groq dejó de ofrecer Llama de
    # texto y los únicos «llama» que quedaron son clasificadores de seguridad. Por
    # eso no se pide un modelo por nombre: se descartan los que no escriben texto
    # —voz, transcripción y clasificadores— y se prefiere el más capaz que haya.
    NO_ESCRIBEN = ("whisper", "guard", "orpheus", "tts", "embed", "rerank", "safeguard")
    PREFERIDOS = ("gpt-oss-120b", "llama-3.3-70b", "qwen", "gpt-oss-20b", "allam")
    candidatos = [m for m in modelos if not any(x in m.lower() for x in NO_ESCRIBEN)]
    if not candidatos:
        return {"modelo": "sin modelo",
                "texto": f"La cuenta devolvió {len(modelos)} modelos y ninguno escribe texto. "
                         f"Disponibles: {', '.join(sorted(modelos)[:12])}"}
    modelo = next((m for p in PREFERIDOS for m in candidatos if p in m.lower()), candidatos[0])
    try:
        cuerpo = json.dumps({
            "model": modelo, "temperature": 0.2,
            "messages": [{"role": "system", "content": sistema},
                         {"role": "user", "content": pregunta}]}).encode()
        req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions",
                                     data=cuerpo, headers=cab)
        with urllib.request.urlopen(req, timeout=120) as r:
            return {"modelo": modelo, "texto": json.load(r)["choices"][0]["message"]["content"]}
    except urllib.error.HTTPError as e:
        detalle = e.read(2000).decode("utf-8", "replace")
        return {"modelo": "error", "texto": f"{modelo} respondió {e.code}: {detalle[:400]}"}
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        return {"modelo": "error", "texto": f"{modelo} no respondió: {e}"}


def candidatas(peor_cubiertos):
    nombres = ", ".join(f["pais"] for f in peor_cubiertos)
    sistema = ("Sos un documentalista de una fundación de análisis. Proponés fuentes de "
               "prensa públicas y verificables. Nunca inventás una dirección: si no estás "
               "seguro de la URL, das el nombre del medio y decís que hay que buscarla. "
               "Respondés en español rioplatense, en una lista corta.")
    pregunta = (f"Para vigilar gobernabilidad, seguridad y entorno informativo en estos "
                f"Estados del Caribe y América Latina: {nombres}. Nombrá hasta ocho medios "
                f"o boletines oficiales nacionales, con su país, que publiquen a diario y "
                f"tengan sitio web propio. Decí cuáles creés que ofrecen RSS.")
    return _llama(pregunta, sistema)


# --------------------------------------------------------------------------
def escribir(datos):
    INFORMES.mkdir(exist_ok=True)
    hoy = date.today()
    p, f, c, k = datos["pulso"], datos["fuentes"], datos["cobertura"], datos["calibracion"]
    L = [f"# FEMÓNOE · motor de automejora — {hoy}", "",
         "Lo escribe el robot, una vez por semana. **Nada de esto se aplica solo:**",
         "son propuestas, y la incorporación es decisión humana.", "",
         "## 1 · El pulso de las señales", ""]
    if not p["dias"]:
        L.append("El detector todavía no dejó corridas para medir.")
    else:
        L += [f"**{p['senales']} señales en {p['dias']} días con corrida** → "
              f"**{p['por_semana']} por semana** (previstas: {SENALES_OBJETIVO}). "
              f"**{p['veredicto']}**", ""]
        for eje, n in sorted(p["por_eje"].items(), key=lambda x: -x[1]):
            L.append(f"- {eje}: {n}")
        if p["propuesta"]:
            L += ["", f"> **Propuesta.** {p['propuesta']}"]
    L += ["", "## 2 · Salud de las fuentes", "", "| Serie | Estado | Detalle |", "|---|---|---|"]
    for s in f:
        L.append(f"| `{s['serie']}` | **{s['estado']}** | {s['detalle']} |")
    muertas = [s["serie"] for s in f if s["estado"] in ("muerta", "vacía")]
    if muertas:
        L += ["", f"> **Propuesta.** Revisar o reemplazar: {', '.join(muertas)}. "
                  f"Una fuente muerta no avisa: deja de aportar y el umbral sigue esperándola."]
    L += ["", "## 3 · Los Estados peor mirados", "",
          "| Estado | Series con dato (30 d) | Fuentes en el padrón |", "|---|---|---|"]
    for fila in c[:8]:
        L.append(f"| {fila['pais']} | {fila['series']} | {fila['fuentes']} |")
    sin_prensa = [f for f in c if f["fuentes"] <= 2]
    # Verificado el 23/9/2026: el Caribe oriental tiene prensa viva en el padrón y
    # pocas series con dato. El faltante no es prensa: es medición automática.
    solo_prensa = [f for f in c if f["fuentes"] >= 3 and f["series"] <= 4]
    if sin_prensa:
        L += ["", f"> **Propuesta.** {len(sin_prensa)} Estados tienen dos fuentes de prensa o "
                  f"menos en el padrón: {', '.join(f['pais'] for f in sin_prensa[:6])}. "
                  f"Conviene sumar medios nacionales antes de la Beta."]
    if solo_prensa:
        L += ["", f"> **Límite declarado.** {len(solo_prensa)} Estados —"
                  f"{', '.join(f['pais'] for f in solo_prensa[:6])}— tienen prensa en el padrón "
                  f"pero pocas series de medición: las familias automáticas (mediciones de "
                  f"bloqueo, cortes de conectividad y registros de hechos) casi no los "
                  f"alcanzan. **Una alerta sobre ellos se apoya en una sola familia de "
                  f"fuentes y no puede declarar confianza alta.** No se arregla sumando "
                  f"diarios: se declara."]
    L += ["", "## 4 · Calibración", ""]
    if not k["total"]:
        L.append("Todavía no venció ninguna alerta. Sin alertas cumplidas no hay nada que calibrar.")
    else:
        L += [f"**{k['total']} alertas vencidas.**", "",
              "| Banda | Casos | Se cumplió | Rango del léxico |", "|---|---|---|---|"]
        for b in k["bandas"]:
            medido = f"{b['medido']} %" if b.get("medido") is not None else b.get("nota", "—")
            rango = f"{b['rango'][0]}–{b['rango'][1]} %" if b.get("rango") else "—"
            L.append(f"| {b['banda']} | {b['n']} | {medido} | {rango} |")
        if k["propuesta"]:
            L += ["", f"> **Propuesta.** {k['propuesta']}"]
    L += ["", "## 5 · Fuentes candidatas", ""]
    c = datos["candidatas"] or {"modelo": "sin clave", "texto": ""}
    if c["modelo"] == "sin clave":
        L.append("Sin clave del modelo gratuito: este tramo no corrió. "
                 "Se carga `GROQ_CLAVE` en los secretos del depósito y vuelve a correr solo.")
    elif c["modelo"] in ("sin modelo", "error"):
        L.append(f"**El tramo no pudo correr.** {c['texto']}")
    else:
        L += [f"Propuestas por **{c['modelo']}**, gratis. "
              "**Ninguna entra al padrón sin verificarla en vivo**: el modelo puede "
              "equivocarse con una dirección, y acá no se incorpora nada sin comprobar.", "",
              c["texto"]]
    L += ["", "---", "",
          "Motor de automejora de FEMÓNOE · corre gratis, sin gastar tokens. "
          "Mide, detecta y propone; **no aplica**."]
    (INFORMES / f"{hoy}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (INFORMES / "ultimo.json").write_text(
        json.dumps({"fecha": hoy.isoformat(), **datos}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return INFORMES / f"{hoy}.md"


def main():
    if "--ver" in sys.argv:
        ultimos = sorted(INFORMES.glob("2*.md")) if INFORMES.exists() else []
        print(ultimos[-1].read_text(encoding="utf-8") if ultimos else "Todavía no hay informes.")
        return
    c = cobertura()
    datos = {"pulso": pulso(), "fuentes": fuentes(), "cobertura": c,
             "calibracion": calibracion(), "candidatas": candidatas(c[:6])}
    ruta = escribir(datos)
    p = datos["pulso"]
    print(f"Motor de automejora: {ruta.name}")
    print(f"  pulso: {p.get('por_semana')} señales por semana · {p.get('veredicto')}")
    print(f"  fuentes muertas o vacías: "
          f"{sum(1 for s in datos['fuentes'] if s['estado'] in ('muerta', 'vacía'))}")
    print(f"  Estados con una serie o menos: {sum(1 for f in c if f['series'] <= 1)}")
    print(f"  alertas vencidas para calibrar: {datos['calibracion']['total']}")


if __name__ == "__main__":
    main()
