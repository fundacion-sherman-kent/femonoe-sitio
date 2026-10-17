# -*- coding: utf-8 -*-
"""Las zonas transfronterizas: dónde FEMÓNOE mira la región y no el país.

**El problema que resuelve.** El detector agrupa por país y por eje. Un hecho
repartido entre tres Estados produce **tres señales separadas y más débiles**, y
la corroboración —que exige dos familias dentro del mismo país y eje— cae por
debajo del umbral con más facilidad que el mismo hecho ocurrido dentro de uno
solo. El resultado es que las zonas de frontera, que es donde más pasa, estaban
**estructuralmente subrepresentadas**. No era un olvido: era el diseño.

**Cómo lo resuelve.** Agrega **antes** de medir el desvío, no después. La serie
de la zona es la suma de las series de sus Estados, y se compara contra su
propia línea de base. Tres países con un alza del treinta por ciento cada uno
—que por separado no pasan ningún umbral— juntos sí lo pasan, y es correcto que
lo pasen: es un solo hecho.

**Y la corroboración se cuenta a nivel de zona.** Si GDELT se mueve del lado
paraguayo y las redes del lado brasileño, eso es un hecho visto por dos familias
distintas. Contarlo como dos señales de fuente única era perder información que
ya teníamos.

**Lo que esto NO hace.** No reemplaza al país: lo complementa. Una señal de zona
nombra a la zona, y el expediente sigue diciendo de qué Estado salió cada dato.
Y no inventa fronteras: el criterio de inclusión está escrito en `zonas.json` y
la frontera norte de México queda afuera porque su otro lado no está en el
padrón de los 33. Es un hueco declarado.
"""
import json
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
_CONF = json.loads((RAIZ / "zonas.json").read_text(encoding="utf-8"))


def zonas():
    return _CONF["zonas"]


def por_codigo(codigo):
    return next((z for z in zonas() if z["codigo"] == codigo), None)


def de_que_zonas(iso3):
    """Las zonas que incluyen a ese Estado. Un Estado puede estar en varias:
    Colombia está en cuatro, y eso no es un error de carga sino la realidad de
    un país con fronteras en todas partes."""
    return [z for z in zonas() if iso3 in z["estados"]]


def _plano(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


_PATRON = {z["codigo"]: re.compile(r"\b(" + "|".join(
    re.escape(_plano(t)) for t in z["toponimos"]) + r")\b") for z in zonas()}


def nombra(texto):
    """Qué zonas nombra un texto, por sus topónimos propios.

    Los topónimos marcados `ambiguos` en `zonas.json` —«Ciudad del Este», que
    es también un centro comercial costarricense; «Arica», que hay en Chile y
    en Colombia— **no alcanzan solos**: hace falta que el texto nombre además
    algún otro topónimo de la zona, o la zona misma. Es la regla de la casa
    aplicada a los lugares: un nombre ambiguo no asigna por sí solo."""
    t = _plano(texto)
    salida = []
    for z in zonas():
        hallados = set(_PATRON[z["codigo"]].findall(t))
        if not hallados:
            continue
        ambiguos = {_plano(a) for a in z.get("ambiguos", [])}
        if hallados <= ambiguos:
            continue            # sólo nombres ambiguos: no alcanza
        salida.append(z["codigo"])
    return salida


def serie_de_zona(series_por_pais, zona):
    """Suma las series diarias de los Estados de la zona.

    Suma y no promedia: lo que se mide es cuánto pasa en la zona, y la zona es
    el conjunto. Promediar escondería que un lado concentra el fenómeno."""
    total = {}
    for iso3 in zona["estados"]:
        for dia, valor in (series_por_pais.get(iso3) or {}).items():
            total[dia] = total.get(dia, 0) + valor
    return total
