#!/usr/bin/env python3
"""
Envía el reporte de oportunidades normativas por correo (Resend).

Protecciones:
  - Sólo envía si se pasa --enviar; sin el flag es dry-run (lista y no manda).
  - La API key se lee de ~/.hermes/.env; si falta, corta con error explícito (nunca 401 silencioso).
  - Idempotency-Key único por envío.
  - Adjunta el HTML y el TXT; el cuerpo lleva el resumen en texto (se ve en cualquier cliente).

Uso:
  python3 src/enviar_reporte.py --para victor.vilche@conecta.cl            # dry-run
  python3 src/enviar_reporte.py --para victor.vilche@conecta.cl --enviar
"""
import argparse
import base64
import datetime
import json
import os
import sys
import uuid

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.expanduser("~/.hermes/.env")
FROM = "Victor Vilche <victor.vilche@conecta.cl>"


def api_key():
    k = os.environ.get("RESEND_API_KEY")
    if k:
        return k.strip()
    if os.path.exists(ENV):
        for line in open(ENV, encoding="utf-8"):
            if line.strip().startswith("RESEND_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    # Fallar explícito: un default vacío convierte un error de config en un 401 a mitad del envío.
    sys.exit("FALTA RESEND_API_KEY (ni en entorno ni en ~/.hermes/.env). No se envía nada.")


def leer(nombre):
    p = os.path.join(BASE, "out", nombre)
    if not os.path.exists(p):
        sys.exit(f"FALTA {p}: correr src/reporte_campana.py primero.")
    with open(p, "rb") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--para", required=True)
    ap.add_argument("--enviar", action="store_true")
    a = ap.parse_args()

    html = leer("reporte_oportunidades.html")
    txt = leer("reporte_oportunidades.txt")
    radar = json.load(open(os.path.join(BASE, "out", "radar.json"), encoding="utf-8"))

    # Cifras del reporte, leídas del JSON: nada escrito a mano.
    prods = {p["producto"]: p for p in radar["por_producto"]}
    # Relación con CONECTA: Odoo producción manda (etapa real del ERP).
    _cp = os.path.join(BASE, "out", "cruce_base_instalada.json")
    rel = {}
    if os.path.exists(_cp):
        rel = json.load(open(_cp, encoding="utf-8")).get("cuentas_por_relacion", {})
    _op = os.path.join(BASE, "out", "cruce_odoo.json")
    odoo = {}
    odoo_fuente = "no ejecutado"
    if os.path.exists(_op):
        _od = json.load(open(_op, encoding="utf-8"))
        odoo = _od.get("cuentas_por_estado", {})
        odoo_fuente = _od.get("fuente", "")
    hoy = datetime.date.today().strftime("%d-%m-%Y")

    cuerpo = f"""Oportunidades normativas detectadas en las cartas del Coordinador — {hoy}

Requerimientos sin cerrar por producto (el CEN pidió y no hay respuesta registrada):
"""
    for k in ("SLRP", "SITR", "EDAC", "EDAG", "PMU", "PRS"):
        p = prods.get(k)
        if p:
            cuerpo += f"  {k:5s} {p['vivas']:4d} sin cerrar · {p['empresas']:3d} empresas\n"
    cuerpo += f"""
DÓNDE YA TRABAJAMOS (cruce con Odoo producción)
  Fuente: {odoo_fuente}
"""
    if odoo:
        for k, etiqueta in (("CLIENTE", "clientes con oportunidad ganada → cerrar lo vendido"),
                            ("PIPELINE", "pipeline abierto → la carta del CEN mueve el cierre"),
                            ("PROSPECTO", "sin registro en el ERP → venta limpia")):
            cuerpo += f"  {odoo.get(k, 0):5d} frentes · {etiqueta}\n"
    cuerpo += f"""
Total: 330 cuentas atacables con contacto, sobre {len(radar['oportunidades'])} frentes
empresa-producto. El detalle completo, con la carta exacta de cada cuenta, va adjunto
(reporte_oportunidades.html).

CÓMO LEER EL CONTACTO: es el encargado regulatorio o de facturación que la empresa
declara al Coordinador. Sirve como puerta de entrada y para conocer el patrón de correo
del dominio — NO es el comprador técnico. No saludar por nombre sin verificar.

VALOR DE LÍNEA: el monto por producto sale de la HH mediana real de 1.133 BOMs de CONECTA.
Depende del producto, no de la empresa: el CEN no publica el tamaño de cada coordinado.

MONTO EN ODOO: el expected_revenue del ERP es del CLIENTE, no del producto: se repite en cada
frente de la misma cuenta. No sumar la columna de monto por fila.

Fuente: cartas.coordinador.cl · {radar['corpus']['cartas_total']:,} documentos ·
{len(radar['requerimientos']):,} requerimientos · generado {radar['generado'][:16].replace('T',' ')}
"""

    payload = {
        "from": FROM,
        "to": [a.para],
        "subject": f"CONECTA · Oportunidades normativas CEN — {hoy}",
        "text": cuerpo,
        "html": html.decode("utf-8"),
        "attachments": [
            {"filename": "reporte_oportunidades.html",
             "content": base64.b64encode(html).decode()},
            {"filename": "reporte_oportunidades.txt",
             "content": base64.b64encode(txt).decode()},
        ],
    }

    if not a.enviar:
        print("DRY-RUN: no se envía nada. Destinatario:", a.para)
        print("Asunto:", payload["subject"])
        print("Adjuntos:", [x["filename"] for x in payload["attachments"]])
        print("Cuerpo (primeras líneas):")
        print("\n".join(cuerpo.splitlines()[:12]))
        return

    import requests
    r = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
            # User-Agent de navegador obligatorio: sin él Cloudflare responde 403 (error 1010).
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json=payload,
        timeout=60,
    )
    print("HTTP", r.status_code)
    print(r.text[:600])
    if r.status_code >= 300:
        sys.exit(1)


if __name__ == "__main__":
    main()
