# -*- coding: utf-8 -*-
"""Control de salida: que no llegue Markdown crudo a la vista del lector.

**Por qué existe.** La Oficina escribe los fundamentos, los dictámenes y los
criterios de resolución con las marcas de Markdown, porque así se redacta en el
expediente. Cuando un campo nuevo se muestra en la página y nadie se acuerda de
convertirlas, los asteriscos salen crudos. Medido el 2/10/2026, antes de este
control: **diecinueve marcas a la vista del lector** repartidas en seis páginas,
incluido un «**más de 628.755 electores inscriptos**» en el cuerpo de la alerta
de Haití. Lo encontró la dirección leyendo una captura, que es el peor lugar
donde puede encontrarse un defecto de edición.

**Qué hace.** Mira lo que el lector ve: saca los programas, los estilos y los
comentarios, y después busca marcas de Markdown en lo que queda. Si encuentra
alguna, **frena la publicación**. No propone, no avisa: frena. Un control que
sólo avisa es un control que alguien va a ignorar un viernes a la tarde.

**Lo que no controla.** Si la conversión es correcta —si `**x**` quedó como
negrita y no como otra cosa—. Eso lo mira una persona. Esto sólo garantiza que
no queda marca cruda, que es un defecto que ninguna persona debería tener que
buscar a mano en quince páginas.

    python control_marcas.py            revisa tablero/ y frena si hay marcas
    python control_marcas.py <carpeta>  revisa otra carpeta
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Lo que el lector no ve no se controla: un `**` dentro de un comentario o de un
# programa es legítimo y marcarlo sería gritar por nada.
SCRIPT = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
COMENTARIO = re.compile(r"(?s)<!--.*?-->")
ETIQUETA = re.compile(r"<[^>]+>")

MARCAS = [
    ("negrita", re.compile(r"\*\*")),
    ("cursiva o viñeta", re.compile(r"(?<![\w*])\*(?!\*)\s*\S")),
    ("título", re.compile(r"(?m)^\s*#{1,6}\s")),
    ("código", re.compile(r"`")),
    ("enlace", re.compile(r"\[[^\]]{1,80}\]\([^)]{1,120}\)")),
]


def visible(html):
    """Lo que de verdad lee una persona."""
    return ETIQUETA.sub(" ", COMENTARIO.sub(" ", SCRIPT.sub(" ", html)))


def revisar(carpeta):
    paginas = sorted(Path(carpeta).rglob("*.html"))
    if not paginas:
        print(f"No hay páginas en {carpeta}. No se controla nada y eso también se dice.")
        return 1
    total = 0
    for f in paginas:
        texto = visible(f.read_text(encoding="utf-8"))
        hallazgos = []
        for nombre, patron in MARCAS:
            for m in patron.finditer(texto):
                ctx = re.sub(r"\s+", " ", texto[max(0, m.start() - 55):m.start() + 55]).strip()
                hallazgos.append((nombre, ctx))
        if hallazgos:
            total += len(hallazgos)
            print(f"\n{f.as_posix()} · {len(hallazgos)} marca(s)")
            for nombre, ctx in hallazgos[:8]:
                print(f"   [{nombre}] …{ctx}…")
            if len(hallazgos) > 8:
                print(f"   … y {len(hallazgos) - 8} más")
    print(f"\n{'=' * 62}")
    if total:
        print(f"  FRENADO: {total} marca(s) de Markdown a la vista en "
              f"{len(paginas)} páginas revisadas.")
        print(f"  El campo que las trae hay que pasarlo por `_negritas` en el "
              f"generador que lo escribe.")
        return 1
    print(f"  {len(paginas)} páginas revisadas, sin marcas crudas a la vista.")
    return 0


if __name__ == "__main__":
    sys.exit(revisar(sys.argv[1] if len(sys.argv) > 1 else RAIZ / "tablero"))
