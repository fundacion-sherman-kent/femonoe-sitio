# -*- coding: utf-8 -*-
"""Buzón de FEMÓNOE · lo que las personas reenvían al bot de Telegram.

Es la vía para WhatsApp y las redes que no se pueden leer con un programa: una
persona ve algo, lo reenvía al bot, y este colector lo recoge con fecha y enlace.
Usa la API oficial de bots de Telegram, que permite exactamente esto. Sin tokens.

Telegram guarda los mensajes pendientes de un bot sólo 24 horas: por eso este
colector corre cada cuatro horas, en su propio robot (buzon.yml).

Sólo entra lo que mandan los remitentes autorizados (buzon.json). Lo de un
remitente desconocido queda aparte, sin clasificar, hasta que la dirección lo
autorice: así nadie puede llenar FEMÓNOE de basura con sólo encontrar el bot."""
import json
import os
import re
import sys
from datetime import datetime, timezone

from comun import RAIZ, pedir_json

sys.path.insert(0, os.path.dirname(__file__))
from redes import MENSAJES, _clasificar  # noqa: E402

CONF = RAIZ / "buzon.json"

def remitentes():
    """Quiénes pueden escribirle al buzón.

    Se lee del secreto BUZON_REMITENTES —un JSON igual al que tenía
    `buzon.json`— y, si no está, del archivo local. **El archivo no se versiona**:
    guarda números de teléfono, y el depósito va a ser público. Es protección de
    fuente, no un recorte de la recolección: entra exactamente lo mismo que antes.
    """
    crudo = os.environ.get("BUZON_REMITENTES")
    if crudo:
        try:
            return json.loads(crudo)
        except ValueError:
            print("BUZON_REMITENTES no es un JSON válido; se ignora")
    archivo = RAIZ / "buzon.json"
    if archivo.exists():
        return json.loads(archivo.read_text(encoding="utf-8"))
    return {"remitentes": [], "whatsapp": []}

ESTADO = RAIZ / "datos" / "buzon_estado.json"
PENDIENTES = RAIZ / "datos" / "buzon_pendientes.jsonl"


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:  # hasta que la dirección cree el bot, no hay nada que leer: no es una falla
        print("Buzón: todavía no está cargado el secreto TELEGRAM_BOT_TOKEN")
        return
    autorizados = set(json.loads(CONF.read_text(encoding="utf-8")).get("remitentes", []))
    estado = json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.exists() else {"offset": 0}
    datos = pedir_json(f"https://api.telegram.org/bot{token}/getUpdates?timeout=0&offset={estado['offset']}",
                       segundos=60)
    MENSAJES.mkdir(parents=True, exist_ok=True)
    hoy = datetime.now(timezone.utc).date()
    entraron = aparte = 0
    for u in datos.get("result", []):
        estado["offset"] = u["update_id"] + 1
        m = u.get("message") or {}
        remitente = (m.get("from") or {}).get("id")
        texto = m.get("text") or m.get("caption") or ""
        if not texto:
            continue
        registro = {
            "fuente": "buzon",
            "cuenta": ("reenvio-" + m["forward_origin"].get("type", "")) if m.get("forward_origin") else "directo",
            "fecha": datetime.fromtimestamp(m.get("date", 0), timezone.utc).isoformat(),
            "texto": texto[:600],
            "enlace": (re.search(r"https?://\S+", texto) or [f"telegram-buzon-{u['update_id']}"])[0],
            "iso3_fuente": (re.search(r"#([A-Z]{3})\b", texto) or [None, "REG"])[1],
        }
        if remitente not in autorizados:
            registro["remitente"] = remitente
            with PENDIENTES.open("a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            aparte += 1
            continue
        _clasificar(registro)
        with (MENSAJES / f"{hoy}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        entraron += 1
    ESTADO.write_text(json.dumps(estado), encoding="utf-8")
    print(f"Buzón: {entraron} aportes incorporados, {aparte} de remitentes sin autorizar (quedan aparte)")


if __name__ == "__main__":
    main()
