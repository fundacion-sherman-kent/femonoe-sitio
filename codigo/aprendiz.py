# -*- coding: utf-8 -*-
"""Aprendiz de curaduría · aprende de lo que la dirección corrige y propone
automatizarlo.

El cuello de botella de FEMÓNOE no es redactar ni impugnar: es **curar**. Los
agentes multiplican lo primero; esto ataca lo segundo.

Cómo funciona, en una línea: **cada vez que la dirección cura o descarta una
alerta se anota qué cambió respecto de lo que propuso el panel.** Con esos
registros, el aprendiz busca la corrección que se repite —«siempre baja una banda
la probabilidad», «acorta el plazo», «no aprueba las de fuente única»— y **propone
convertirla en regla**.

**La regla no se aplica hasta que la dirección la aprueba, una vez.** A partir de
ahí el panel la aplica solo, y la alerta le llega a la dirección ya corregida: no
se automatiza el juicio, se deja de pedirle la misma corrección dos veces. Cada
regla aplicada queda escrita en la alerta, se puede revocar, y el aprendiz mide
si sigue acertando.

  python aprendiz.py                 lee el registro y escribe el informe
  python aprendiz.py aprobar R-2     la dirección autoriza una regla
  python aprendiz.py revocar R-2     la deja sin efecto
  python aprendiz.py --ver           muestra el estado de las reglas
"""
import json
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CARPETA = RAIZ / "curaduria"
REGISTRO = CARPETA / "registro.jsonl"
REGLAS = CARPETA / "reglas.json"
BANDAS = ["casi con certeza no", "muy improbable", "improbable", "posibilidades parejas",
          "probable", "muy probable", "casi con certeza"]
MINIMO = 5          # menos de cinco casos no son una costumbre, son una casualidad
ACUERDO = 0.7       # y siete de cada diez tienen que ir en el mismo sentido


def _registros():
    if not REGISTRO.exists():
        return []
    salida = []
    for linea in REGISTRO.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea:
            try:
                salida.append(json.loads(linea))
            except ValueError:
                continue
    return salida


def _reglas():
    return json.loads(REGLAS.read_text(encoding="utf-8")) if REGLAS.exists() else []


def _guardar_reglas(reglas):
    CARPETA.mkdir(exist_ok=True)
    REGLAS.write_text(json.dumps(reglas, ensure_ascii=False, indent=1), encoding="utf-8")


def _mezclar(nuevas):
    """Conserva lo que la dirección ya decidió: una regla aprobada o revocada no
    vuelve al estado de propuesta porque haya llegado un caso más."""
    viejas = {r["id"]: r for r in _reglas()}
    salida = []
    for r in nuevas:
        previa = viejas.get(r["id"])
        if previa and previa.get("estado") in ("aprobada", "revocada"):
            r["estado"] = previa["estado"]
            r["desde"] = previa.get("desde")
        else:
            r["estado"] = "propuesta"
        salida.append(r)
    for ident, previa in viejas.items():
        if ident not in {r["id"] for r in salida}:
            salida.append(previa)
    return salida


# --------------------------------------------------------------------------
def aprender(registros):
    curadas = [r for r in registros if r["accion"] == "curada" and r.get("propuesto")]
    descartadas = [r for r in registros if r["accion"] == "descartada"]
    reglas, notas = [], []

    # 1 · La banda. ¿La dirección corrige siempre para el mismo lado?
    saltos = []
    for r in curadas:
        p, f = r["propuesto"].get("probabilidad"), r["final"].get("probabilidad")
        if p in BANDAS and f in BANDAS:
            saltos.append(BANDAS.index(f) - BANDAS.index(p))
    if len(saltos) >= MINIMO:
        cuenta = Counter(saltos)
        salto, veces = cuenta.most_common(1)[0]
        if salto != 0 and veces / len(saltos) >= ACUERDO:
            reglas.append({
                "id": "R-banda", "tipo": "banda", "ajuste": salto,
                "descripcion": (f"Corregir la banda {abs(salto)} posición"
                                f"{'es' if abs(salto) > 1 else ''} hacia "
                                f"{'abajo' if salto < 0 else 'arriba'} al consolidar el panel"),
                "evidencia": {"casos": len(saltos), "coinciden": veces,
                              "proporcion": round(veces / len(saltos), 2)}})
        elif cuenta.get(0, 0) / len(saltos) >= 0.9:
            notas.append(f"La banda del panel se aprueba sin cambios en "
                         f"{cuenta[0]} de {len(saltos)} casos: no hay nada que corregir.")

    # 2 · El plazo.
    deltas = []
    for r in curadas:
        p, f = r["propuesto"].get("plazo_dias"), r["final"].get("plazo_dias")
        if isinstance(p, int) and isinstance(f, int):
            deltas.append(f - p)
    if len(deltas) >= MINIMO:
        mismo_signo = [d for d in deltas if d and (d > 0) == (statistics.median(deltas) > 0)]
        if statistics.median(deltas) != 0 and len(mismo_signo) / len(deltas) >= ACUERDO:
            ajuste = int(statistics.median(deltas))
            reglas.append({
                "id": "R-plazo", "tipo": "plazo", "ajuste": ajuste,
                "descripcion": (f"{'Acortar' if ajuste < 0 else 'Estirar'} el plazo "
                                f"{abs(ajuste)} días al consolidar el panel"),
                "evidencia": {"casos": len(deltas), "coinciden": len(mismo_signo),
                              "proporcion": round(len(mismo_signo) / len(deltas), 2)}})

    # 3 · La fuente única. ¿Vale la pena elevarlas?
    unicas = [r for r in registros if r.get("fuente_unica")]
    if len(unicas) >= 3:
        rechazadas = [r for r in unicas if r["accion"] == "descartada"]
        if len(rechazadas) / len(unicas) >= ACUERDO:
            reglas.append({
                "id": "R-fuente-unica", "tipo": "fuente_unica", "ajuste": 0,
                "descripcion": "No elevar a curaduría las alertas con una sola familia de "
                               "fuentes: quedan detenidas hasta que corrobore una segunda",
                "evidencia": {"casos": len(unicas), "coinciden": len(rechazadas),
                              "proporcion": round(len(rechazadas) / len(unicas), 2)}})

    # 4 · Lo que no se automatiza, pero se le dice a los analistas.
    reescritos = [r for r in curadas if "hecho_anunciado" in r.get("cambios", [])]
    if curadas and len(reescritos) / len(curadas) >= 0.5:
        notas.append(f"La dirección reescribe el hecho anunciado en {len(reescritos)} de "
                     f"{len(curadas)} alertas. **Eso no se automatiza**: es instrucción para "
                     f"los analistas, y conviene sumarla a su entrenamiento con dos ejemplos "
                     f"de los motivos anotados.")
    motivos = [r.get("motivo") for r in descartadas if r.get("motivo")]
    if motivos:
        notas.append("Motivos de descarte anotados: " + " · ".join(f"«{m}»" for m in motivos[-5:]))
    return reglas, notas, curadas, descartadas


def medir(registros):
    """El marcador del aprendiz: qué proporción de alertas llega a la dirección
    sin necesitar corrección. Es el número que tiene que subir."""
    curadas = [r for r in registros if r["accion"] == "curada"]
    if not curadas:
        return None
    limpias = [r for r in curadas if not r.get("cambios")]
    ultimas = curadas[-10:]
    limpias_ultimas = [r for r in ultimas if not r.get("cambios")]
    return {"curadas": len(curadas), "sin_correccion": len(limpias),
            "porcentaje": round(len(limpias) / len(curadas) * 100),
            "ultimas": len(ultimas),
            "porcentaje_ultimas": round(len(limpias_ultimas) / len(ultimas) * 100)}


def escribir(reglas, notas, medida, registros):
    CARPETA.mkdir(exist_ok=True)
    L = [f"# FEMÓNOE · aprendiz de curaduría — {date.today()}", "",
         f"Registros leídos: **{len(registros)}**. El aprendiz propone; "
         "**la dirección aprueba, y recién ahí una regla empieza a aplicarse**.", ""]
    if medida:
        L += ["## Cuánto se automatizó", "",
              f"- Alertas curadas: **{medida['curadas']}**",
              f"- Llegaron sin necesitar corrección: **{medida['sin_correccion']}** "
              f"(**{medida['porcentaje']} %**)",
              f"- En las últimas {medida['ultimas']}: **{medida['porcentaje_ultimas']} %**", ""]
    else:
        L += ["## Cuánto se automatizó", "",
              "Sin alertas curadas todavía. El aprendiz empieza a medir con la primera.", ""]
    L += ["## Reglas", ""]
    if not reglas:
        L.append("Ninguna costumbre alcanzó el mínimo de cinco casos con siete de cada diez "
                 "en el mismo sentido. Sin eso no es una costumbre: es una casualidad.")
    else:
        L += ["| Regla | Qué haría | Evidencia | Estado |", "|---|---|---|---|"]
        for r in reglas:
            e = r["evidencia"]
            L.append(f"| `{r['id']}` | {r['descripcion']} | {e['coinciden']} de {e['casos']} "
                     f"({e['proporcion']:.0%}) | **{r['estado']}** |")
        L += ["", "Para autorizar una: `python aprendiz.py aprobar <regla>`. "
                  "Para dejarla sin efecto: `revocar`."]
    if notas:
        L += ["", "## Lo que no se automatiza", ""]
        L += [f"- {n}" for n in notas]
    L += ["", "---", "",
          "El aprendiz no reemplaza la curaduría: **le saca de encima la corrección que ya "
          "hizo cinco veces.** Cada regla aplicada queda escrita en la alerta y puede "
          "revocarse."]
    (CARPETA / "aprendizaje.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return CARPETA / "aprendizaje.md"


def cambiar_estado(ident, estado):
    reglas = _reglas()
    for r in reglas:
        if r["id"] == ident:
            r["estado"] = estado
            r["desde"] = date.today().isoformat()
            _guardar_reglas(reglas)
            print(f"{ident}: {estado}. {r['descripcion']}")
            return
    sys.exit(f"No existe la regla {ident}")


def main():
    if len(sys.argv) > 2 and sys.argv[1] in ("aprobar", "revocar"):
        cambiar_estado(sys.argv[2], "aprobada" if sys.argv[1] == "aprobar" else "revocada")
        return
    if "--ver" in sys.argv:
        ruta = CARPETA / "aprendizaje.md"
        print(ruta.read_text(encoding="utf-8") if ruta.exists() else "Todavía no hay informe.")
        return
    registros = _registros()
    reglas, notas, curadas, _ = aprender(registros)
    reglas = _mezclar(reglas)
    _guardar_reglas(reglas)
    medida = medir(registros)
    ruta = escribir(reglas, notas, medida, registros)
    print(f"Aprendiz: {len(registros)} registros · {len(reglas)} reglas · {ruta.name}")
    if medida:
        print(f"  alertas que no necesitaron corrección: {medida['porcentaje']} %")
    for r in reglas:
        print(f"  {r['id']} [{r['estado']}] {r['descripcion']}")


if __name__ == "__main__":
    main()
