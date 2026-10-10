# -*- coding: utf-8 -*-
"""FEMÓNOE · lectura DISARM de una señal del entorno informativo.

**Qué resuelve.** Hasta hoy FEMÓNOE medía el entorno informativo —bloqueos,
caídas de conectividad, difusión coordinada— y no tenía con qué **nombrarlo**.
Sin vocabulario común, cada analista describía lo mismo con otras palabras y el
lector no podía comparar una alerta de Venezuela con una de Nicaragua.

**De dónde sale el vocabulario.** De DISARM (DISARM Foundation, CC BY 4.0), el
marco abierto de técnicas de manipulación informativa. **No se inventa
taxonomía propia**: se adopta la que ya usan los destinatarios.

Quién la usa, verificado el 27/9/2026 contra las fuentes primarias y no contra
la página del propio marco: el **Servicio Europeo de Acción Exterior** la aplica
en sus informes de amenazas FIMI; **ENISA**, la agencia europea de
ciberseguridad, en su panorama de amenazas FIMI y ciberseguridad; y el **Hybrid
CoE** de Helsinki —centro de excelencia conjunto de la UE y la OTAN, que no es
la OTAN— le dedicó su Informe de Investigación 7. Copia local del índice en
`disarm.json`, leída el 27/9/2026.

**La regla que gobierna este archivo, y no es negociable.**
Observar amplificación **no prueba** una operación. Tres cuentas que repiten el
mismo texto pueden ser una campaña o pueden ser tres medios copiando el mismo
comunicado. Un bloqueo medido por OONI puede ser censura, una orden judicial o
un error de configuración. Una caída de conectividad puede ser un apagón.

Por eso FEMÓNOE **nunca afirma la técnica**: dice que lo observado es
**compatible con** ella, y en la misma línea dice qué haría falta para
afirmarla —y que eso no lo tiene—. Cada entrada del mapa lleva su `no_prueba`
escrito al lado, y sale impreso junto con la técnica: la advertencia viaja
pegada al hallazgo, no en una nota al pie que nadie lee.

  python disarm.py                 lectura de las señales de ayer
  python disarm.py 2026-09-24      lectura de un día
  python disarm.py --catalogo      el mapa: qué observable habilita qué técnica
  python disarm.py --vacios        lo que el marco nombra y todavía no medimos
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
FICHERO = RAIZ / "disarm.json"
FUENTE = "DISARM Foundation · github.com/DISARMFoundation/DISARMframeworks · CC BY 4.0"

# Cada entrada: qué serie lo hace visible, con qué técnicas es compatible, y
# —sobre todo— qué NO prueba y qué haría falta para afirmarlo.
MAPA = [
    {
        "observable": "difusión coordinada",
        "series": ["redes_coordinado"],
        "se_mide_asi": ("tres cuentas o más publican el mismo texto —primeros 140 "
                        "caracteres, normalizados— el mismo día, atribuido al país"),
        "tecnicas": ["T0084.001", "T0049", "T0049.003", "T0119"],
        "no_prueba": ("no prueba inautenticidad ni automatización: tres medios que "
                      "reproducen un comunicado oficial producen la misma huella"),
        "haria_falta": ("antigüedad y patrón horario de las cuentas, y quién publicó "
                        "primero. FEMÓNOE no lo tiene: lee canales públicos, no cuentas"),
    },
    {
        "observable": "bloqueo confirmado",
        "series": ["ooni_confirmados"],
        "se_mide_asi": ("OONI confirma que un sitio o una aplicación está bloqueado en "
                        "la red del país, por interferencia comprobada y no por caída"),
        "tecnicas": ["T0123.002", "T0047", "T0124"],
        "no_prueba": ("no prueba intención política: un bloqueo puede venir de una "
                      "orden judicial, de una disputa comercial o de un error de la red"),
        "haria_falta": ("el acto administrativo o la orden que lo dispone, y a quién "
                        "alcanza. Cuando existe y es público, entra como hecho duro"),
    },
    {
        "observable": "caída de conectividad",
        "series": ["ioda_alertas"],
        "se_mide_asi": ("IODA detecta que el tráfico del país —o de una porción— cae "
                        "por debajo de lo esperado para esa hora y ese día"),
        "tecnicas": ["T0123"],
        "no_prueba": ("no prueba que sea deliberada: un cable cortado, un temporal o "
                      "un corte de energía se ven exactamente igual desde afuera"),
        "haria_falta": ("el alcance —si cae todo el país o sólo ciertos servicios—, la "
                        "hora de inicio contra el hecho político, y el aviso del operador"),
    },
    {
        "observable": "salto de volumen informativo",
        "series": ["redes_informativo"],
        "se_mide_asi": ("los canales públicos del país publican sobre el entorno "
                        "informativo muy por encima de su mediana"),
        "tecnicas": ["T0049", "T0049.005"],
        "no_prueba": ("no prueba nada por sí solo: un salto de volumen es lo que hace "
                      "cualquier noticia grande, sea verdadera o sea falsa"),
        "haria_falta": ("que el salto no se explique por un hecho público de esa "
                        "magnitud. Eso lo juzga el panel, no la serie"),
    },
]

# Lo que el marco nombra, FEMÓNOE querría evidenciar y hoy **no mide**. Está acá
# escrito y no en una lista de deseos aparte: un vacío declarado es doctrina, un
# vacío sin declarar es un descuido.
VACIOS = [
    ("T0015", "uso y creación de etiquetas",
     "no se extraen etiquetas de los mensajes"),
    ("T0049.002", "inundar una etiqueta existente",
     "ídem: haría falta medir por etiqueta, no por país y eje"),
    ("T0049.007", "sitios inauténticos que amplifican",
     "haría falta el padrón de sitios sin firma responsable y su fecha de registro"),
    ("T0131", "explotar las reglas de la plataforma para bajar contenido",
     "sólo es visible desde adentro de la plataforma"),
    ("T0129.005", "coordinación en redes cerradas",
     "por decisión de la casa no se entra a canales cerrados"),
]


def catalogo() -> dict:
    """Las técnicas, tal como las publica DISARM. No se editan: se citan."""
    if not FICHERO.exists():
        sys.exit("Falta disarm.json. Se baja del índice público de DISARM.")
    d = json.loads(FICHERO.read_text(encoding="utf-8"))
    return {t["id"]: t for t in d["tecnicas"]}


def lectura(detalle: list) -> list:
    """Dada la lista `senal.detalle` de una alerta —o las señales crudas del
    detector—, devuelve las entradas del mapa que esa señal habilita."""
    cat = catalogo()
    vistas = {x.get("senal") for x in detalle if isinstance(x, dict)}
    salida = []
    for entrada in MAPA:
        tocadas = [s for s in entrada["series"] if s in vistas]
        if not tocadas:
            continue
        salida.append({
            "observable": entrada["observable"],
            "series": tocadas,
            "se_mide_asi": entrada["se_mide_asi"],
            "no_prueba": entrada["no_prueba"],
            "haria_falta": entrada["haria_falta"],
            "tecnicas": [{"id": i,
                          "nombre": cat.get(i, {}).get("nombre", i),
                          "tactica": cat.get(i, {}).get("tactica", "")}
                         for i in entrada["tecnicas"]],
        })
    return salida


def frase(lec: dict) -> str:
    """Cómo se escribe en el producto. La única forma autorizada."""
    ids = ", ".join(f"{t['id']} ({t['nombre']})" for t in lec["tecnicas"])
    return (f"Lo observado —{lec['se_mide_asi']}— es compatible con "
            f"{ids} del marco DISARM. No las afirma: {lec['no_prueba']}.")


def _mostrar(dia):
    f = RAIZ / "senales" / f"{dia}.json"
    if not f.exists():
        sys.exit(f"No hay señales del {dia}.")
    registro = json.loads(f.read_text(encoding="utf-8"))
    print(f"FEMÓNOE · lectura DISARM de las señales del {dia}\n")
    hubo = False
    for i, s in enumerate(registro["senales"], 1):
        lecs = lectura(s.get("senales", []))
        if not lecs:
            continue
        hubo = True
        print(f"{i}. {s['pais']} · {s['eje']}")
        for lec in lecs:
            print(f"   {frase(lec)}")
            print(f"   Haría falta: {lec['haria_falta']}.\n")
    if not hubo:
        print("Ninguna señal del día toca el entorno informativo. "
              "No se omite: se dice.\n")
    print(FUENTE)


def main():
    if "--catalogo" in sys.argv:
        cat = catalogo()
        print("FEMÓNOE · mapa de lectura DISARM\n")
        for e in MAPA:
            print(f"· {e['observable']}  ({', '.join(e['series'])})")
            print(f"    se mide así: {e['se_mide_asi']}")
            for i in e["tecnicas"]:
                t = cat.get(i, {})
                print(f"    compatible con  {i:12s} {t.get('tactica', ''):5s} "
                      f"{t.get('nombre', '')}")
            print(f"    NO prueba:   {e['no_prueba']}")
            print(f"    haría falta: {e['haria_falta']}\n")
        print(f"{len(cat)} técnicas en la copia local · {FUENTE}")
    elif "--vacios" in sys.argv:
        cat = catalogo()
        print("FEMÓNOE · lo que DISARM nombra y todavía no medimos\n")
        for i, que, por in VACIOS:
            print(f"· {i:12s} {cat.get(i, {}).get('nombre', que)}")
            print(f"    {por}\n")
        print("Declarado, no escondido: un producto sin vacíos declarados se rechaza.")
    else:
        libres = [a for a in sys.argv[1:] if not a.startswith("--")]
        _mostrar(libres[0] if libres
                 else (date.today() - timedelta(days=1)).isoformat())


if __name__ == "__main__":
    main()
