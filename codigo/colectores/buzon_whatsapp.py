# -*- coding: utf-8 -*-
"""Buzón de WhatsApp de FEMÓNOE · retira lo que las personas reenviaron al número
del buzón, desde el receptor de Cloudflare (whatsapp-buzon/worker.js).

Es la vía oficial: el número de la Fundación recibe lo que se le reenvía, y la
API de WhatsApp se lo entrega al receptor. No se lee ningún canal ni ningún chat.
Sólo entra lo de remitentes autorizados (buzon.json, "whatsapp"); lo demás queda
aparte hasta que la dirección lo autorice. Sin tokens de IA."""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

from comun import RAIZ, UA

sys.path.insert(0, os.path.dirname(__file__))
from redes import MENSAJES, _clasificar  # noqa: E402

URL = RAIZ / "whatsapp-buzon" / "url.txt"
PENDIENTES = RAIZ / "datos" / "buzon_pendientes.jsonl"


def main():
    clave = os.environ.get("WA_ROBOT_CLAVE")
    if not clave or not URL.exists() or not URL.read_text().strip():
        print("Buzón de WhatsApp: el receptor todavía no está desplegado")
        return
    req = urllib.request.Request(URL.read_text().strip() + "/retirar", method="POST",
                                 headers={"Authorization": f"Bearer {clave}", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        mensajes = json.load(r).get("mensajes", [])
    from buzon import remitentes
    autorizados = set(remitentes().get("whatsapp", []))
    MENSAJES.mkdir(parents=True, exist_ok=True)
    hoy = datetime.now(timezone.utc).date()
    entraron = aparte = 0
    for m in mensajes:
        registro = {
            "fuente": "whatsapp-buzon", "cuenta": "reenvio" if m.get("reenviado") else "directo",
            "fecha": datetime.fromtimestamp(int(m.get("fecha") or 0), timezone.utc).isoformat(),
            "texto": (m.get("texto") or "")[:600],
            # WhatsApp no conserva de qué canal viene un reenvío (probado el 22/9/2026: sólo
            # marca "forwarded"). El enlace que trae el texto identifica al medio: se usa ese.
            "enlace": (re.search(r"https?://\S+", m.get("texto") or "") or [f"whatsapp-buzon-{m.get('id')}"])[0],
            "iso3_fuente": (re.search(r"#([A-Z]{3})", m.get("texto") or "") or [None, "REG"])[1],
            "contexto": m.get("contexto"),
        }
        if m.get("remitente") not in autorizados:
            registro["remitente"] = m.get("remitente")
            with PENDIENTES.open("a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            aparte += 1
            continue
        _clasificar(registro)
        with (MENSAJES / f"{hoy}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        entraron += 1
    print(f"Buzón de WhatsApp: {entraron} aportes incorporados, {aparte} de remitentes sin autorizar")


if __name__ == "__main__":
    main()
