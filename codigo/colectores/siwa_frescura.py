# -*- coding: utf-8 -*-
"""La frescura de SIWA, cruzada con lo que el vigía mira.

**Por qué el vigía necesita esto.** El vigía de FEMÓNOE sabe si un organismo
**publicó** algo. No sabe si lo que ese organismo publica **ya está contado** en
algún lado, ni si la cifra que la casa usaría para interpretarlo es de este año
o de hace cinco. Son dos preguntas distintas y hasta ahora sólo se contestaba la
primera.

SIWA mide la segunda y la publica: su termómetro de frescura dice, indicador por
indicador, de qué año es el dato más reciente que tiene. Medido el 5/10/2026:
192 indicadores, 118 al día, 59 tibios y 15 atrasados de cuatro años o más.

**Qué cruce hace este programa.** Para cada Estado del padrón, junta:
  · si el vigía lo está mirando, y qué le contestó la última vez
  · qué tan fresca está la base de SIWA sobre la que se lo interpretaría

y deja ver los dos casos que importan:
  **ciego y viejo** — ni el vigía lo alcanza ni SIWA tiene dato reciente. Sobre
  ese Estado la casa no puede decir casi nada, y conviene saber cuáles son antes
  de que alguien pregunte.
  **vigilado pero viejo** — el vigía llega, pero el contexto con que se leería lo
  que encuentre está atrasado. Una publicación nueva interpretada contra una
  cifra de hace cinco años es una interpretación de hace cinco años.

**Lo que NO hace.** No recalifica nada de SIWA ni escribe en su depósito. Lee su
JSON público —CC BY 4.0— por HTTP, como cualquier otra fuente, y la atribución
viaja en el registro. El cruce va en un solo sentido, que es lo que fijó el acta
el 21/9/2026.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

RAIZ = Path(__file__).resolve().parent.parent
FRESCURA = "https://siwa.fundacionkent.org/datos/publico/frescura.json"
SALIDA = RAIZ / "datos" / "frescura_siwa.json"
UA = "FEMONOE-robot/0.1 (Fundacion Sherman Kent; +https://fundacionkent.org)"


def traer(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _estado_del_vigia():
    """Lo que el vigía contestó por organismo, si está desplegado.

    Si no lo está, se devuelve vacío y se dice. Suponer que el vigía mira lo que
    no mira sería exactamente el defecto que se corrigió el 2/10/2026.
    """
    url = (RAIZ / "vigia" / "url.txt")
    clave = os.environ.get("WA_ROBOT_CLAVE", "")
    if not url.exists() or not clave:
        return None
    try:
        req = urllib.request.Request(
            url.read_text(encoding="utf-8").strip() + "/estado", data=b"{}", method="POST",
            headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json",
                     "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None


def main():
    try:
        f = traer(FRESCURA)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"SIWA no respondió ({type(e).__name__}). No se toca nada.")
        return
    resumen = f.get("resumen") or {}
    indicadores = f.get("indicadores") or []
    cortes = f.get("cortes_del_termometro") or {}
    atrasados = [i for i in (f.get("ranking_mas_atrasados") or [])][:15]

    vig = _estado_del_vigia()
    padron = vig.get("padron", []) if vig else []
    mirados = [p for p in padron
               if p.get("titulares") and not str(p.get("resultado") or "").startswith(
                   ("HTTP", "no respondió", "sin titulares"))]
    ciegos = [p for p in padron if p not in mirados]

    registro = {
        "que_es": ("Qué tan fresca está la base de SIWA con la que se interpretaría lo "
                   "que el vigía encuentre, y sobre qué organismos el vigía no llega."),
        "traido_el": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": {"nombre": "SIWA · Fundación Sherman Kent", "url": FRESCURA,
                   "licencia": "CC BY 4.0", "corrida_de_siwa": f.get("corrida")},
        "cortes_del_termometro": cortes,
        "resumen_siwa": resumen,
        "mas_atrasados": [{"clave": i.get("clave"), "rotulo": i.get("rotulo"),
                           "eje": i.get("eje"), "fuente": i.get("fuente")}
                          for i in atrasados],
        "vigia": ({"desplegado": True,
                   "organismos": len(padron),
                   "vigilados": [p.get("clave") for p in mirados],
                   "no_vigilados": [{"clave": p.get("clave"), "por_que": p.get("resultado")}
                                    for p in ciegos]}
                  if vig else
                  {"desplegado": False,
                   "por_que": ("No está desplegado o falta la clave del robot. No se "
                               "supone lo que mira: se dice que no se pudo saber.")}),
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Frescura de SIWA · corrida {str(f.get('corrida', ''))[:10]}")
    print(f"  {resumen.get('indicadores_medidos', '—')} indicadores · "
          f"al día {resumen.get('al_dia_1_anio_o_menos', '—')} · "
          f"tibios {resumen.get('tibio_2_a_3_anios', '—')} · "
          f"atrasados {resumen.get('atrasado_4_anios_o_mas', '—')}")
    print(f"  mediana de antigüedad: {resumen.get('mediana_antiguedad_anios', '—')} año(s)")
    if vig:
        print(f"  vigía: {len(mirados)} organismo(s) vigilados de {len(padron)}; "
              f"{len(ciegos)} que no alcanza")
    else:
        print("  vigía: no se pudo leer su estado. No se supone lo que mira.")
    if atrasados:
        print("  lo más atrasado de SIWA, para no interpretar contra una cifra vieja:")
        for i in atrasados[:4]:
            print(f"    · {i.get('rotulo')} ({i.get('eje')})")


if __name__ == "__main__":
    main()
