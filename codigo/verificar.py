# -*- coding: utf-8 -*-
"""Verifica las fuentes del padrón: cuáles siguen publicando y cuáles murieron.

Una fuente muerta en el padrón es peor que una fuente que falta: **aparenta
cobertura**. El motor de automejora cuenta las fuentes activas por Estado, así
que una lista con feeds rotos le hace creer que un país está mirado cuando no lo
está.

Esto pide cada RSS, comprueba que responda, que sea un feed y que traiga notas
con fecha, e informa la del último artículo.

  python verificar.py                    verifica todo el padrón
  python verificar.py ATG DMA GRD        sólo esos Estados
  python verificar.py --marcar           anota los fallos y apaga las que dejaron
                                         de publicar; una fuente sólo se apaga por
                                         falta de acceso tras tres fallos seguidos
  python verificar.py --descubrir        a las que fallan, les pregunta al sitio
                                         cuál es su feed
"""
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PADRON = RAIZ / "redes.json"
UA = "FEMONOE-robot/0.1 (Fundacion Sherman Kent; +https://fundacionkent.org)"
DIAS_MUERTA = 30


def _fecha(texto):
    for patron in (r"<pubDate>([^<]+)</pubDate>", r"<updated>([^<]+)</updated>",
                   r"<published>([^<]+)</published>", r"<dc:date>([^<]+)</dc:date>"):
        m = re.search(patron, texto, re.I)
        if not m:
            continue
        crudo = m.group(1).strip()
        try:
            return parsedate_to_datetime(crudo)
        except (TypeError, ValueError):
            pass
        try:
            return datetime.fromisoformat(crudo.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def verificar(entrada):
    url = entrada.get("url_rss")
    salida = {**entrada, "url": url}
    if not url:
        return {**salida, "estado": "sin url"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "application/rss+xml, application/xml, text/xml, */*"})
        with urllib.request.urlopen(req, timeout=45) as r:
            crudo = r.read(600_000).decode("utf-8", "replace")
            codigo = r.status
    except urllib.error.HTTPError as e:
        return {**salida, "estado": f"HTTP {e.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {**salida, "estado": f"no responde ({type(e).__name__})"}
    notas = len(re.findall(r"<item[ >]|<entry[ >]", crudo, re.I))
    if not notas:
        return {**salida, "estado": "no es un feed", "codigo": codigo}
    fecha = _fecha(crudo)
    if fecha is None:
        # Un feed sin fecha no está muerto: es un feed que no la declara. El
        # colector lo lee igual. Se anota la limitación y sigue en el padrón.
        return {**salida, "estado": "viva", "notas": notas, "sin_fecha": True}
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    dias = (datetime.now(timezone.utc) - fecha).days
    estado = "viva" if dias <= DIAS_MUERTA else f"quieta hace {dias} días"
    return {**salida, "estado": estado, "notas": notas, "dias": dias,
            "ultima": fecha.date().isoformat()}


def descubrir(url):
    """Ante un feed roto, se le pregunta al sitio cuál es el suyo: los feeds se
    declaran en el encabezado de la portada. Es preferible a adivinar direcciones."""
    raiz = re.match(r"https?://[^/]+", url)
    if not raiz:
        return []
    try:
        req = urllib.request.Request(raiz.group(0), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            html = r.read(900_000).decode("utf-8", "replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        return [f"la portada tampoco responde: {type(e).__name__}"]
    hallados = []
    for etiqueta in re.findall(r"<link[^>]+>", html, re.I):
        if "alternate" in etiqueta.lower() and ("rss" in etiqueta.lower() or "atom" in etiqueta.lower()):
            m = re.search(r"href=[\"']([^\"']+)[\"']", etiqueta, re.I)
            if m:
                destino = m.group(1)
                if destino.startswith("/"):
                    destino = raiz.group(0) + destino
                hallados.append(destino)
    return hallados


def main():
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    marcar = "--marcar" in sys.argv
    buscar = "--descubrir" in sys.argv
    padron = json.loads(PADRON.read_text(encoding="utf-8"))
    entradas = [e for e in padron.get("rss", [])
                if not argumentos or e.get("iso3") in argumentos]
    print(f"Verificando {len(entradas)} fuentes RSS…")
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(verificar, entradas))
    vivas = [r for r in resultados if r["estado"] == "viva"]
    problemas = [r for r in resultados if r["estado"] != "viva"]
    for r in sorted(resultados, key=lambda x: (x["estado"] != "viva", x.get("iso3", ""))):
        marca = "ok  " if r["estado"] == "viva" else "MAL "
        if r.get("sin_fecha"):
            r = {**r, "estado": "viva, sin fecha declarada"}
        print(f"  {marca}{r.get('iso3')} · {r.get('nombre', '')[:34]:36s} {r['estado']}"
              + (f" · última {r['ultima']}" if r.get("ultima") else ""))
    print(f"\n{len(vivas)} vivas · {len(problemas)} con problema")
    # El recuento queda escrito: la barra de estado del tablero se arma con esto y
    # así puede decir cuántas respondieron de cuántas, en vez de sugerir que todas.
    if not argumentos:
        (RAIZ / "datos").mkdir(exist_ok=True)
        (RAIZ / "datos" / "verificacion.json").write_text(json.dumps({
            "fecha": datetime.now().date().isoformat(),
            "revisadas": len(resultados), "vivas": len(vivas),
            "con_problema": len(problemas),
            "detalle": [{"iso3": r.get("iso3"), "nombre": r.get("nombre"),
                         "estado": r["estado"]} for r in problemas],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    if buscar:
        for r in problemas:
            print(chr(10) + f"{r.get('nombre')} ({r.get('iso3')}) · feeds que declara el sitio:")
            for f in descubrir(r.get("url_rss") or "") or ["ninguno declarado"]:
                print("   ", f)
    if marcar:
        # Un 403 o un límite de peticiones no es una fuente muerta: es un mal día.
        # Sólo se apaga lo que dejó de publicar, o lo que falla tres veces seguidas.
        hoy = datetime.now(timezone.utc).date().isoformat()
        por_url = {r.get("url_rss"): r for r in resultados}
        apagadas, restauradas = 0, 0
        for e in padron["rss"]:
            r = por_url.get(e.get("url_rss"))
            if not r:
                continue
            if r["estado"] == "viva":
                if not e.get("activo", True) and e.get("fallos"):
                    restauradas += 1
                e["activo"] = True
                e.pop("fallos", None)
                e["nota"] = re.sub(r"(Apagada|Sin acceso) el [0-9-]+: [^.]*[.] ?", "",
                                   e.get("nota") or "").strip() or e.get("nota", "")
            elif "quieta hace" in r["estado"]:
                e["activo"] = False
                e["nota"] = f"Apagada el {hoy}: {r['estado']}. " + (e.get("nota") or "")
                apagadas += 1
            else:
                e["fallos"] = int(e.get("fallos", 0)) + 1
                if e["fallos"] >= 3:
                    e["activo"] = False
                    e["nota"] = (f"Apagada el {hoy}: {r['estado']} tres veces seguidas. "
                                 + (e.get("nota") or ""))
                    apagadas += 1
                else:
                    e["nota"] = (f"Sin acceso el {hoy}: {r['estado']} "
                                 f"({e['fallos']} de 3). " + (e.get("nota") or ""))
        PADRON.write_text(json.dumps(padron, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Padrón: {apagadas} apagadas, {restauradas} restauradas.")


if __name__ == "__main__":
    main()
