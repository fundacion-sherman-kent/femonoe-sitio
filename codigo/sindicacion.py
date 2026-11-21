# -*- coding: utf-8 -*-
"""FEMÓNOE · quiénes son, en los hechos, una sola fuente.

**Por qué existe.** La señal de difusión coordinada marcaba cuando tres cuentas
publicaban el mismo texto el mismo día. Medido el 27/9/2026 sobre cinco días de
material: **40 fuentes del padrón reprodujeron texto de otra, 157 veces**. No es
coordinación, es el cable de agencia de todos los días. `doctrina/fuentes.md`
§2 lo dice desde siempre: *tres medios que citan el mismo cable son UNA fuente,
no tres*.

**Qué hace.** Mide qué parejas de fuentes repiten texto **de forma rutinaria** y
las agrupa. Dos fuentes que comparten un texto una vez cubrieron la misma
noticia; dos que lo comparten varias veces y en días distintos tienen una
relación estable —sindicación, propiedad común, o la misma casa en dos
plataformas—. El detector después cuenta **grupos, no cuentas**.

**Lo que esto NO es.** No es un juicio sobre nadie: no dice que una fuente copie
mal ni que sea menos fiable. Dice que, para contar corroboración, esas dos valen
una. Y no resuelve el caso difícil —dos medios que levantan el mismo cable sin
relación entre sí—, que con este método quedan agrupados igual. Es el error
prudente: **agrupa de más, nunca de menos**, porque contar dos fuentes como una
subestima la corroboración y contar una como dos la inventa.

  python sindicacion.py            muestra los grupos
  python sindicacion.py --escribir guarda sindicacion.json para el colector
"""
import hashlib
import itertools
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
MENSAJES = RAIZ / "datos" / "mensajes"
SALIDA = RAIZ / "sindicacion.json"
PADRON = RAIZ / "redes.json"

# Una repetición es una noticia compartida; varias, en días distintos, es una
# relación. Con más material recolectado estos dos números suben.
TEXTOS_MINIMOS = 4
DIAS_MINIMOS = 2


def _huella(texto):
    """**La misma huella que usa el colector**, carácter por carácter.

    No es un detalle: el colector no colapsa los espacios, así que una copia
    hecha con otra normalización agrupa distinto y mide otra cosa. Se probó el
    27/9 con una versión propia y daba un tercio de las coincidencias."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return hashlib.sha1(
        re.sub(r"https?://\S+|[^a-z0-9 ]", "", t)[:140].encode()).hexdigest()


def _mensajes():
    for f in sorted(MENSAJES.glob("*.jsonl")):
        for linea in f.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                try:
                    yield json.loads(linea)
                except json.JSONDecodeError:
                    continue


def _del_padron():
    """Sólo las fuentes que hoy están en el padrón. Una que se dio de baja no
    tiene por qué seguir agrupando a las demás."""
    d = json.loads(PADRON.read_text(encoding="utf-8"))
    vivas = set()
    for k, v in d.items():
        if not isinstance(v, list):
            continue
        for x in v:
            ident = (x.get("url_rss") if k == "rss" else
                     x.get("canal_id") if k == "youtube" else
                     x.get("instancia") if k == "mastodon" else x.get("canal"))
            if ident:
                vivas.add(ident)
    return vivas


def parejas():
    vivas = _del_padron()
    huellas = defaultdict(list)
    for m in _mensajes():
        if m.get("cuenta") not in vivas or not (m.get("texto") or "").strip():
            continue
        huellas[_huella(m["texto"])].append(
            (m.get("fecha", "")[:10], m.get("cuenta")))
    textos, dias = Counter(), defaultdict(set)
    for grupo in huellas.values():
        cuentas = {c for _, c in grupo}
        if len(cuentas) < 2:
            continue
        cuando = min(d for d, _ in grupo)
        for a, b in itertools.combinations(sorted(cuentas), 2):
            textos[(a, b)] += 1
            dias[(a, b)].add(cuando)
    return {p: (n, sorted(dias[p])) for p, n in textos.items()
            if n >= TEXTOS_MINIMOS and len(dias[p]) >= DIAS_MINIMOS}


def grupos(pares=None):
    """Une las parejas en grupos. Si A va con B y B con C, los tres son uno."""
    pares = parejas() if pares is None else pares
    padre = {}

    def raiz(x):
        padre.setdefault(x, x)
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for a, b in pares:
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            padre[ra] = rb
    juntos = defaultdict(list)
    for x in padre:
        juntos[raiz(x)].append(x)
    return [sorted(v) for v in juntos.values() if len(v) > 1], pares


def main():
    gs, pares = grupos()
    dias = sorted({f.stem for f in MENSAJES.glob("*.jsonl")})
    print("FEMÓNOE · fuentes que en los hechos son una sola\n")
    print(f"Material: {len(dias)} días ({dias[0]} a {dias[-1]}). Criterio: "
          f"{TEXTOS_MINIMOS} textos o más compartidos, en {DIAS_MINIMOS} días "
          "distintos o más.\n")
    for g in sorted(gs, key=len, reverse=True):
        print(f"· grupo de {len(g)}:")
        for c in g:
            print(f"    {c[:78]}")
        pruebas = [(p, v) for p, v in pares.items() if p[0] in g and p[1] in g]
        for (a, b), (n, ds) in sorted(pruebas, key=lambda kv: -kv[1][0])[:3]:
            print(f"      {n} textos en {len(ds)} días · {a[:32]} / {b[:32]}")
        print()
    cuentas = sum(len(g) for g in gs)
    print(f"{len(gs)} grupos, {cuentas} fuentes. Para contar corroboración valen "
          f"{len(gs)}, no {cuentas}.")
    if "--escribir" in sys.argv:
        SALIDA.write_text(json.dumps({
            "generado": date.today().isoformat(),
            "criterio": {"textos_minimos": TEXTOS_MINIMOS,
                         "dias_minimos": DIAS_MINIMOS,
                         "ventana_dias": len(dias)},
            "nota": ("Fuentes que repiten texto de forma rutinaria. El colector "
                     "cuenta grupos y no cuentas al armar redes_coordinado. "
                     "Agrupa de más antes que de menos: contar una fuente como "
                     "dos inventa corroboración."),
            "grupos": sorted(gs, key=len, reverse=True),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nEscrito {SALIDA.name}. El colector lo lee en la próxima corrida.")
    else:
        print("\nNada escrito. Con --escribir se guarda para el colector.")


if __name__ == "__main__":
    main()
