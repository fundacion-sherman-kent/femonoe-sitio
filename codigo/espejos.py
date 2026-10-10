# -*- coding: utf-8 -*-
"""Busca dónde más publica un emisor que sólo tenemos en un canal cerrado.

**El problema.** Los canales de WhatsApp no se pueden leer con un robot:
verificado el 25/9/2026 contra la documentación de Meta, que **no menciona los
canales en ninguna parte**, y contra la página pública del canal, que muestra la
tarjeta y ninguna publicación.

**La salida.** Casi ningún emisor publica en un solo lado. Si el mismo que tiene
el canal también tiene Telegram, sitio o YouTube, **se automatiza el espejo** y
el canal deja de importar.

**Cómo se comprueba que es el mismo, y no un homónimo.** Ésta es la parte que
importa: el 23/9 el modelo confundió Granada del Caribe con Granada de España y
sus tres feeds funcionaban. Acá se exige **una prueba dura**, una de dos:

1. el candidato **enlaza al canal** —su identificador aparece en la página—, o
2. el candidato **repite la descripción del canal**, palabra por palabra.

Sin una de las dos, la candidata queda anotada como «sin confirmar» y **no entra
al padrón**.

**Por qué no busca en un buscador.** Se probó el 25/9: DuckDuckGo bloquea al
robot, Mojeek responde 403 y las instancias públicas de Searx caen o limitan. Así
que no se busca: **se prueban las direcciones donde ese nombre estaría, y se
comprueba.**

  python espejos.py "Cisne Negro" 0029VadZflaJ93wX7c5bim0j
  python espejos.py "Cisne Negro" 0029Vad... --incorporar
"""
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
from verificar import UA, verificar  # noqa: E402

PADRON = RAIZ / "redes.json"
PROPUESTAS = RAIZ / "propuestas"
CAMINOS_RSS = ("/feed/", "/rss", "/rss.xml", "/feed", "/index.xml")


def _simple(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def variantes(nombre):
    """Las formas en que un mismo nombre aparece como usuario."""
    base = _simple(nombre)
    palabras = [_simple(p) for p in (nombre or "").split() if _simple(p)]
    salida = {base, "".join(palabras), "_".join(palabras), "-".join(palabras)}
    if len(palabras) > 1:
        salida.add(palabras[0] + palabras[-1])
        salida.add(palabras[0])
    return sorted(x for x in salida if len(x) >= 4)


def _bajar(url, limite=500_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(limite).decode("utf-8", "replace")


def _es_el_mismo(html, canal_id, descripcion):
    """La prueba dura. Sin esto no se incorpora nada."""
    plano = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).lower()
    if canal_id and canal_id.lower() in html.lower():
        return "enlaza al canal"
    if descripcion and len(descripcion) > 40:
        trozo = re.sub(r"\s+", " ", descripcion).strip().lower()[:80]
        if trozo and trozo in plano:
            return "repite la descripción del canal"
    return ""


def tarjeta_del_canal(canal_id):
    """Lo único que WhatsApp publica de un canal: nombre y descripción."""
    try:
        html = _bajar(f"https://www.whatsapp.com/channel/{canal_id}", 300_000)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return {}
    desc = re.search(r'property="og:description"\s+content="([^"]*)"', html)
    tit = re.search(r'property="og:title"\s+content="([^"]*)"', html)
    limpio = lambda s: re.sub(r"&#x([0-9a-f]+);", lambda m: chr(int(m.group(1), 16)), s or "")
    return {"nombre": limpio(tit.group(1) if tit else ""),
            "descripcion": limpio(desc.group(1) if desc else "")}


def probar(nombre, canal_id, descripcion):
    """Prueba las direcciones donde ese emisor estaría, y comprueba cada una."""
    hallazgos = []
    for v in variantes(nombre):
        candidatas = [
            ("telegram", f"https://t.me/s/{v}", f"https://t.me/s/{v}"),
            ("youtube", f"https://www.youtube.com/@{v}", f"https://www.youtube.com/@{v}"),
            ("sitio", f"https://{v}.com", f"https://{v}.com"),
            ("sitio", f"https://{v}.com.ar", f"https://{v}.com.ar"),
            ("sitio", f"https://{v}.org", f"https://{v}.org"),
            ("instagram", f"https://www.instagram.com/{v}/", f"https://www.instagram.com/{v}/"),
        ]
        for plataforma, url, visita in candidatas:
            try:
                html = _bajar(visita, 900_000)
            except (urllib.error.HTTPError, urllib.error.URLError, OSError, UnicodeError):
                continue
            prueba = _es_el_mismo(html, canal_id, descripcion)
            registro = {"plataforma": plataforma, "url": url, "variante": v,
                        "prueba": prueba or "sin confirmar"}
            if plataforma == "sitio" and prueba:
                for camino in CAMINOS_RSS:
                    r = verificar({"url_rss": url.rstrip("/") + camino})
                    if r["estado"] == "viva":
                        registro["url_rss"] = url.rstrip("/") + camino
                        registro["ultima"] = r.get("ultima")
                        break
            hallazgos.append(registro)
            print(f"  {'CONFIRMADO' if prueba else 'sin prueba '} {plataforma:9s} {url[:58]}"
                  + (f"  ({prueba})" if prueba else ""))
    return hallazgos


def main():
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(argumentos) < 1:
        sys.exit(__doc__)
    nombre = argumentos[0]
    canal_id = argumentos[1] if len(argumentos) > 1 else ""
    tarjeta = tarjeta_del_canal(canal_id) if canal_id else {}
    if tarjeta:
        print(f"Canal: {tarjeta.get('nombre')} · {tarjeta.get('descripcion')[:90]}")
    print(f"Probando variantes de «{nombre}»: {', '.join(variantes(nombre))}\n")
    hallazgos = probar(nombre, canal_id, tarjeta.get("descripcion", ""))
    confirmados = [h for h in hallazgos if h["prueba"] != "sin confirmar"]
    PROPUESTAS.mkdir(exist_ok=True)
    (PROPUESTAS / f"espejos-{_simple(nombre)}-{date.today()}.json").write_text(
        json.dumps({"canal": canal_id, "tarjeta": tarjeta, "hallazgos": hallazgos},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(confirmados)} espejos confirmados de {len(hallazgos)} candidatos probados.")
    if not confirmados:
        print("Ninguno pasó la prueba dura. **No se incorpora nada**: un homónimo con el "
              "mismo nombre no es el mismo emisor, y eso ya nos pasó con Granada.")


if __name__ == "__main__":
    main()
