#!/usr/bin/env python3
"""
Genera el REPORTE DE OPORTUNIDADES para campaña normativa (HTML para correo + versión texto).

Fuente única: out/radar.json. Contactos: catálogo CEN de coordinados (patrón de correo real).

Reglas de honestidad del entregable:
  - El monto es valor de LÍNEA de producto (HH mediana real de BOM), no pipeline por empresa.
  - El contacto del catálogo CEN es el encargado regulatorio/facturación que la empresa declara
    al Coordinador. NO es el comprador técnico, y en 752 de 1.353 registros el nombre no calza
    con el correo (la fuente trae las dos cosas juntas pero de personas distintas): se usa como
    PUERTA y patrón de dominio, nunca para saludar por nombre.
  - Sin cruce Odoo no se distingue cliente / pipeline / prospecto. Se dice.
"""
import json
import os
import re
import unicodedata
import datetime
import html

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = os.path.expanduser("~/Documents/ConocimientoSupcon/supcon-catalogo/datos/cen_coordinados_correos.json")

# Qué se le vende a cada producto (de las skills de producto CONECTA)
PITCH = {
    "SLRP": "Gateway serial→IP (Moxa/SEL-3620) + IEC 61850 MMS + COMTRADE. Ojo: SLRP ≠ SITR.",
    "SITR": "Gateway SCADA→CEN (Orion RTU / SOLISCADA), señales SSCC y plan de disponibilidad.",
    "EDAC": "Automatismo EDAC: lógica, pruebas de desconexión e integración SCADA.",
    "EDAG": "Automatismo EDAG: lógica, pruebas e integración con unidades generadoras.",
    "PMU": "PMU Vizimax + PDC, protocolo de verificación y cierre de implementación.",
    "PRS": "Protocolo de verificación PRS y pruebas de partida autónoma.",
    "SSCC": "Medición clase 0,2 y protocolo de verificación de SSCC.",
    "SCADA": "Gateway SCADA→CEN, Tier0 UNS y arquitectura de comunicaciones.",
    "PROTECCIONES": "Retrofit de relés, backup y análisis de eventos.",
}

# La palanca: por qué el cliente tiene que moverse ahora
PALANCA = {
    "SIN_RESPUESTA": "El CEN le escribió y no hay respuesta registrada.",
    "REITERADO": "El CEN tuvo que repetir el pedido.",
    "REABIERTO": "Respondió y el CEN volvió a la carga.",
    "MIXTO": "Acumula varias señales.",
}


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def cargar_contactos():
    if not os.path.exists(CAT):
        return {}
    d = json.load(open(CAT, encoding="utf-8"))
    idx = {}
    for dom, items in d.get("por_dominio", {}).items():
        for it in items:
            emp = it.get("empresa") or ""
            if not emp:
                continue
            idx.setdefault(norm(emp), []).append({
                "nombre": it.get("nombre") or "",
                "rol": it.get("rol") or "",
                "correo": it.get("correo") or "",
                "dominio": dom,
            })
    return idx


def elegir_contacto(lista):
    """Prefiere Gerente General (firma), luego Encargado Titular."""
    orden = {"Gerente General": 0, "Encargado Titular": 1, "Encargado Suplente": 2}
    return sorted(lista, key=lambda x: orden.get(x["rol"], 9))[0]


def main():
    r = json.load(open(os.path.join(BASE, "out", "radar.json"), encoding="utf-8"))
    O = [o for o in r["oportunidades"] if o["empresa"].strip()]
    contactos = cargar_contactos()

    # ── Cruce con la base instalada (BOMs + OTs). Si no se ha corrido, se sigue sin él. ──
    cruce_p = os.path.join(BASE, "out", "cruce_base_instalada.json")
    rel = {}
    if os.path.exists(cruce_p):
        cr = json.load(open(cruce_p, encoding="utf-8"))
        for f in cr["filas"]:
            rel[(f["empresa"], f["producto"])] = (f["relacion"], f.get("historia"))
        resumen_rel = cr.get("cuentas_por_relacion", {})
        fuentes_cruce = cr.get("fuentes", {})
    else:
        resumen_rel, fuentes_cruce = {}, {}

    # ── Cruce con Odoo producción (etapa y monto reales). Manda sobre el cruce por BOMs. ──
    odoo_p = os.path.join(BASE, "out", "cruce_odoo.json")
    odoo_estado, odoo_resumen, odoo_monto = {}, {}, {}
    if os.path.exists(odoo_p):
        od = json.load(open(odoo_p, encoding="utf-8"))
        for f in od["filas"]:
            odoo_estado[(f["empresa"], f["producto"])] = (f["odoo"], f.get("odoo_etapas"),
                                                          f.get("odoo_leads"))
        odoo_resumen = od.get("cuentas_por_estado", {})
        odoo_monto = od.get("monto_por_cuenta", {})
        odoo_fuente = od.get("fuente", "")
    else:
        odoo_fuente = "no ejecutado"

    # Enriquecer
    filas = []
    for o in O:
        c = contactos.get(norm(o["empresa"]))
        ct = elegir_contacto(c) if c else None
        filas.append({**o, "contacto": ct})

    con_contacto = [f for f in filas if f["contacto"]]
    # Relación con CONECTA: Odoo manda (etapa real); si no hay, se usa el cruce por BOMs.
    for f in filas:
        r_, h_ = rel.get((f["empresa"], f["producto"]), ("PROSPECTO", None))
        oe = odoo_estado.get((f["empresa"], f["producto"]))
        if oe and oe[0]:
            rel_txt = {"CLIENTE": "ODOO · cliente", "PIPELINE": "ODOO · pipeline",
                       "PROSPECTO": "ODOO · prospecto"}[oe[0]]
            f["relacion"], f["historia"] = rel_txt, h_
            f["odoo_etapas"], f["odoo_leads"] = oe[1], oe[2]
        else:
            f["relacion"], f["historia"] = r_, h_
            f["odoo_etapas"] = f["odoo_leads"] = None
    # Prioridad de campaña: cliente primero (ir directo es más fácil), luego pipeline, luego prospecto.
    ORDEN_REL = {"ODOO · cliente": 0, "CLIENTE · mismo producto": 1, "CLIENTE · producto nuevo": 2,
                 "CLIENTE · sin detalle de línea": 3, "ODOO · pipeline": 4, "PROSPECTO": 6,
                 "ODOO · prospecto": 6}
    vivas = [f for f in filas if f["estado_peor"] in ("MIXTO", "SIN_RESPUESTA", "REABIERTO")]
    atacables = sorted([f for f in vivas if f["contacto"]],
                       key=lambda f: (ORDEN_REL.get(f["relacion"], 9), -f["gravedad"]))
    # Los que ya compraron justo lo que el CEN les pide: conversación de cierre, no de venta
    cierre = [f for f in atacables if f["relacion"] == "CLIENTE · mismo producto"]

    # CUENTAS únicas: 'atacables' son pares empresa-producto. Una empresa con SSCC y SITR es UNA
    # cuenta con dos frentes, no dos cuentas (medido: 678 pares = 330 cuentas reales).
    cuentas_atacables = len({norm(f["empresa"]) for f in atacables})
    cuentas_vivas = len({norm(f["empresa"]) for f in vivas})
    cuentas_total = len({norm(f["empresa"]) for f in filas})
    cuentas_con_contacto = len({norm(f["empresa"]) for f in con_contacto})

    por_prod = {}
    for p in r["por_producto"]:
        por_prod[p["producto"]] = p

    hoy = datetime.date.today().strftime("%d-%m-%Y")

    # ── Tabla de las mejores cuentas para atacar (con contacto) ──────────────
    top = atacables[:25]
    filas_html = []
    for i, f in enumerate(top, 1):
        ct = f["contacto"]
        h = f.get("historia") or {}
        badge = {
            "ODOO · cliente": ('#1e8449', 'ODOO · CLIENTE'),
            "ODOO · pipeline": ('#2874a6', 'ODOO · PIPELINE'),
            "ODOO · prospecto": ('#b9770e', 'PROSPECTO'),
            "CLIENTE · mismo producto": ('#1e8449', 'CLIENTE · ya le vendimos esto'),
            "CLIENTE · producto nuevo": ('#2874a6', 'CLIENTE · producto nuevo'),
            "CLIENTE · sin detalle de línea": ('#7f8c8d', 'CLIENTE · s/detalle'),
            "PROSPECTO": ('#b9770e', 'PROSPECTO'),
        }.get(f["relacion"], ('#7f8c8d', f["relacion"]))
        hist_txt = ""
        if f.get("odoo_etapas"):
            et = sorted(f["odoo_etapas"].items(), key=lambda x: -x[1])[:2]
            hist_txt = " · ".join(f"{k} ({v})" for k, v in et)
        elif h.get("lineas"):
            hist_txt = f"{', '.join(h['lineas'])} · {h['n_bom']} BOMs"
        elif h.get("ots"):
            hist_txt = h["ots"][0][:46]
        filas_html.append(f"""
        <tr>
          <td class="n">{i}</td>
          <td><b>{html.escape(f['empresa'])}</b><div class="corr">{html.escape(', '.join(f['correlativos'][:2]))}</div></td>
          <td><span style="display:inline-block;font-size:10.5px;font-weight:600;color:#fff;padding:2px 7px;border-radius:4px;background:{badge[0]}">{badge[1]}</span>
              <div class="corr">{html.escape(hist_txt)}</div></td>
          <td><span class="tag">{f['producto']}</span></td>
          <td>{PALANCA.get(f['estado_peor'], f['estado_peor'])}<div class="corr">{f['n_reqs']} req · {f['dias_max']}d</div></td>
          <td>{html.escape(ct['correo'])}<div class="corr">{html.escape(ct['rol'])}</div></td>
        </tr>""")

    # ── Resumen por producto ─────────────────────────────────────────────────
    orden = ["SLRP", "SITR", "EDAC", "EDAG", "PMU", "PRS", "SSCC", "SCADA", "PROTECCIONES"]
    prod_html = []
    for k in orden:
        p = por_prod.get(k)
        if not p:
            continue
        # OJO: sin_respuesta / reiterado / reabierto NO son excluyentes (un requerimiento puede
        # llevar las tres). Sumarlos da 'vivas' mayor que los requerimientos totales (medido:
        # SITR mostraba 2120 vivas sobre 899 reqs). 'Vivas' = requerimientos sin cerrar.
        vivas_p = p.get("vivas", p["n_reqs"] - p.get("respondido", 0))
        prod_html.append(f"""
        <tr>
          <td><b>{k}</b></td>
          <td class="n">{p['n_reqs']}</td>
          <td class="n">{p['empresas']}</td>
          <td class="n hot">{vivas_p}</td>
          <td>{html.escape(PITCH.get(k, ''))}</td>
        </tr>""")

    monto_linea = {}
    for f in filas:
        monto_linea.setdefault(f["producto"], f["usd_venta"])

    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CONECTA · Oportunidades normativas CEN — {hoy}</title></head>
<body style="margin:0;padding:0;background:#f4f5f7;">
<div style="max-width:980px;margin:0 auto;padding:24px 18px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#1a1a1a;line-height:1.55;">

  <div style="background:#0f2743;color:#fff;padding:22px 24px;border-radius:10px 10px 0 0;">
    <div style="font-size:11px;letter-spacing:.12em;opacity:.75;">CONECTA INGENIERÍA · PARTNER SUPCON CHILE</div>
    <div style="font-size:22px;font-weight:700;margin-top:6px;">Oportunidades normativas CEN</div>
    <div style="font-size:13px;opacity:.85;margin-top:4px;">Campaña desde incumplimiento y mora documentada · {hoy}</div>
  </div>

  <div style="background:#fff;padding:20px 24px;border-left:1px solid #e4e4e7;border-right:1px solid #e4e4e7;">

    <table style="width:100%;border-collapse:collapse;margin-bottom:6px;">
      <tr>
        <td style="padding:8px 10px;background:#f8f9fb;border-radius:6px;">
          <div style="font-size:24px;font-weight:700;">{cuentas_atacables}</div>
          <div style="font-size:11px;color:#6b6b6b;text-transform:uppercase;letter-spacing:.04em;">cuentas atacables</div>
          <div style="font-size:11px;color:#6b6b6b;">{len(atacables)} frentes (empresa × producto)</div>
        </td>
        <td style="width:10px;"></td>
        <td style="padding:8px 10px;background:#f8f9fb;border-radius:6px;">
          <div style="font-size:24px;font-weight:700;">{cuentas_vivas}</div>
          <div style="font-size:11px;color:#6b6b6b;text-transform:uppercase;letter-spacing:.04em;">cuentas con mora viva</div>
          <div style="font-size:11px;color:#6b6b6b;">{len(vivas)} frentes abiertos</div>
        </td>
        <td style="width:10px;"></td>
        <td style="padding:8px 10px;background:#f8f9fb;border-radius:6px;">
          <div style="font-size:24px;font-weight:700;">{cuentas_con_contacto}</div>
          <div style="font-size:11px;color:#6b6b6b;text-transform:uppercase;letter-spacing:.04em;">con contacto</div>
          <div style="font-size:11px;color:#6b6b6b;">de {cuentas_total} cuentas del padrón</div>
        </td>
        <td style="width:10px;"></td>
        <td style="padding:8px 10px;background:#f8f9fb;border-radius:6px;">
          <div style="font-size:24px;font-weight:700;">{len(filas)}</div>
          <div style="font-size:11px;color:#6b6b6b;text-transform:uppercase;letter-spacing:.04em;">pares empresa-producto</div>
          <div style="font-size:11px;color:#6b6b6b;">padrón completo del radar</div>
        </td>
      </tr>
    </table>

    <div style="font-size:12px;color:#8a6d00;background:#fffbf0;border-left:3px solid #e6c34a;padding:9px 12px;margin:14px 0;">
      <b>Cómo leer el contacto:</b> es el encargado regulatorio o de facturación que la empresa declara al
      Coordinador. Sirve como <b>puerta de entrada y patrón de correo real del dominio</b>, no como comprador técnico.
      No saludar por nombre sin verificar: en buena parte de los registros el nombre y el correo de la fuente
      son de personas distintas.
    </div>

    <h2 style="font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;margin:24px 0 8px;">Mora por producto normativo</h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <tr style="text-align:left;color:#6b6b6b;font-size:11px;text-transform:uppercase;letter-spacing:.04em;">
        <th style="padding:6px 8px;border-bottom:1px solid #e4e4e7;">Producto</th>
        <th style="padding:6px 8px;border-bottom:1px solid #e4e4e7;text-align:right;">Reqs</th>
        <th style="padding:6px 8px;border-bottom:1px solid #e4e4e7;text-align:right;">Empresas</th>
        <th style="padding:6px 8px;border-bottom:1px solid #e4e4e7;text-align:right;">Vivas</th>
        <th style="padding:6px 8px;border-bottom:1px solid #e4e4e7;">Qué vende CONECTA</th>
      </tr>
      {''.join(prod_html)}
    </table>

    <h2 style="font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;margin:24px 0 8px;">Dónde ya trabajamos</h2>
    <div style="font-size:11.5px;color:#6b6b6b;margin-bottom:10px;">
      Fuente: {html.escape(odoo_fuente)} — etapa y monto reales del ERP.
      {html.escape(str(odoo_resumen.get('CLIENTE', 0)))} CLIENTE ·
      {html.escape(str(odoo_resumen.get('PIPELINE', 0)))} PIPELINE ·
      {html.escape(str(odoo_resumen.get('PROSPECTO', 0)))} sin registro (frentes).
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:6px;">
      <tr>
        <td style="padding:7px 10px;background:#eafaf1;border-left:3px solid #1e8449;">
          <b>{resumen_rel.get('CLIENTE · mismo producto', 0)}</b> frentes donde el CEN pide
          <b>justo lo que ya le vendimos</b> → cerrar lo vendido, no vender de nuevo.
        </td>
      </tr>
      <tr><td style="height:6px;"></td></tr>
      <tr>
        <td style="padding:7px 10px;background:#eef5fb;border-left:3px solid #2874a6;">
          <b>{resumen_rel.get('CLIENTE · producto nuevo', 0)}</b> frentes en clientes con otro producto →
          ampliación, con la ventaja de la relación abierta.
        </td>
      </tr>
      <tr><td style="height:6px;"></td></tr>
      <tr>
        <td style="padding:7px 10px;background:#f4f4f5;border-left:3px solid #7f8c8d;">
          <b>{resumen_rel.get('CLIENTE · sin detalle de línea', 0)}</b> frentes en clientes donde la base
          no registra qué se le vendió (392 de 1.133 BOMs no traen línea) → verificar antes de ofrecer.
        </td>
      </tr>
      <tr><td style="height:6px;"></td></tr>
      <tr>
        <td style="padding:7px 10px;background:#fdf6ec;border-left:3px solid #b9770e;">
          <b>{resumen_rel.get('PROSPECTO', 0)}</b> frentes en prospectos puros → venta limpia con la carta como dolor.
        </td>
      </tr>
    </table>
    <div style="font-size:11px;color:#6b6b6b;margin:8px 0 0;">
      Cruce contra: {html.escape(fuentes_cruce.get('boms', 'base no disponible'))} ·
      {html.escape(fuentes_cruce.get('ots', ''))}
    </div>

    <h2 style="font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;margin:26px 0 8px;">Las {len(top)} cuentas a atacar esta semana</h2>
  <div style="font-size:11.5px;color:#6b6b6b;margin-bottom:10px;">Clientes CONECTA primero (ir directo es más fácil), luego prospectos. Dentro de cada grupo, por gravedad de mora.</div>
    <table style="width:100%;border-collapse:collapse;font-size:12.5px;">
      <tr style="text-align:left;color:#6b6b6b;font-size:11px;text-transform:uppercase;letter-spacing:.04em;">
        <th style="padding:6px;border-bottom:1px solid #e4e4e7;">#</th>
        <th style="padding:6px;border-bottom:1px solid #e4e4e7;">Cuenta</th>
        <th style="padding:6px;border-bottom:1px solid #e4e4e7;">Relación CONECTA</th>
        <th style="padding:6px;border-bottom:1px solid #e4e4e7;">Producto</th>
        <th style="padding:6px;border-bottom:1px solid #e4e4e7;">Palanca</th>
        <th style="padding:6px;border-bottom:1px solid #e4e4e7;">Contacto</th>
      </tr>
      {''.join(filas_html)}
    </table>

    <div style="margin-top:22px;padding:14px 16px;background:#0f2743;color:#fff;border-radius:8px;">
      <div style="font-size:14px;font-weight:600;">Siguiente paso</div>
      <div style="font-size:13px;opacity:.9;margin-top:5px;">
        El gancho de entrada es la carta, no el producto: “el Coordinador le pidió X el {hoy[:0]}…”.
        Cada cuenta de arriba trae el correlativo para citar la carta exacta.
        Secuencia sugerida: día 0 correo con la carta citada · día 3 llamada · día 7 caso resuelto · día 14 último intento.
      </div>
    </div>

  </div>

  <div style="background:#fafafa;border:1px solid #e4e4e7;border-top:none;border-radius:0 0 10px 10px;padding:16px 24px;font-size:11.5px;color:#6b6b6b;">
    <p style="margin:0 0 6px;"><b>Valor de línea:</b> el monto por producto sale de la HH mediana real de los BOMs de CONECTA
    (1.133 BOMs). <b>Depende del producto, no de la empresa</b>: el CEN no publica el tamaño de cada coordinado, así que dos
    cuentas del mismo producto muestran el mismo valor. Por eso el orden es por gravedad de mora, no por monto.</p>
    <p style="margin:0 0 6px;"><b>Cruce con cartera Odoo:</b> no ejecutado. No se distingue cliente / pipeline / prospecto
    en este informe; todas las cuentas salen del padrón del CEN. Verificar en el ERP antes de contactar a un cliente existente.</p>
    <p style="margin:0;"><b>Fuente:</b> cartas.coordinador.cl · {r['corpus']['cartas_total']:,} documentos ·
    {len(r['requerimientos']):,} requerimientos · generado {r['generado'][:16].replace('T',' ')}.
    Proyecto: ~/orca/projects/RadarNormativoCEN</p>
  </div>

</div></body></html>"""

    ruta = os.path.join(BASE, "out", "reporte_oportunidades.html")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(doc)

    # ── versión texto (cuerpo del correo, sin depender de imágenes) ──────────
    lineas = [
        f"OPORTUNIDADES NORMATIVAS CEN — {hoy}",
        "",
        f"{cuentas_atacables} cuentas atacables ({len(atacables)} frentes empresa-producto), "
        f"de {cuentas_total} cuentas en el padrón CEN.",
        "",
        "MORA POR PRODUCTO",
    ]
    for k in orden:
        p = por_prod.get(k)
        if p:
            vivas_p = p.get("vivas", p["n_reqs"] - p.get("respondido", 0))
            lineas.append(f"  {k:13s} {p['n_reqs']:4d} req · {p['empresas']:3d} empresas · {vivas_p:4d} sin cerrar")
    lineas += ["", "DÓNDE YA TRABAJAMOS"]
    if odoo_resumen:
        lineas.append(f"  Fuente: {odoo_fuente}")
        for k, v in odoo_resumen.items():
            lineas.append(f"  {k:32s} {v} frentes")
        lineas.append(f"  Monto en ERP: {len(odoo_monto)} cuentas con expected_revenue registrado")
    else:
        for k in ("CLIENTE · mismo producto", "CLIENTE · producto nuevo",
                  "CLIENTE · sin detalle de línea", "PROSPECTO"):
            lineas.append(f"  {k:32s} {resumen_rel.get(k, 0)} frentes")
    lineas += ["", "TOP CUENTAS A ATACAR (clientes primero)"]
    for i, f in enumerate(top, 1):
        ct = f["contacto"]
        h = f.get("historia") or {}
        hist = f" [{', '.join(h['lineas'])}]" if h.get("lineas") else ""
        lineas.append(
            f"  {i:2d}. {f['empresa'][:30]:32s} {f['producto']:12s} {f['n_reqs']:2d} req / {f['dias_max']:3d}d"
            f"  {f['relacion'][:26]:28s} {ct['correo']}{hist}")
    lineas += ["",
               "VALOR DE LÍNEA: depende del PRODUCTO, no de la empresa. Sale de la HH mediana real de 1.133 BOMs.",
               "MONTO EN ODOO: el expected_revenue es del CLIENTE y se repite en cada frente de la misma cuenta.",
               f"Fuente: cartas.coordinador.cl · {odoo_fuente or 'Odoo no ejecutado'}"]
    with open(os.path.join(BASE, "out", "reporte_oportunidades.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))

    # ── Resumen corto para el cron de los lunes ─────────────────────────────
    # Solo los seis productos que Victor pidió, y el top por CUENTA (no por frente).
    # Existe para que el agente del cron lea esto en vez de improvisar sobre radar.json
    # (medido: se colaron SCADA/SSCC y el top salió por frente, no por cuenta).
    seis = ("SLRP", "SITR", "EDAC", "EDAG", "PMU", "PRS")
    corto = [f"RADAR NORMATIVO CEN — {hoy}", ""]
    for k in seis:
        p = por_prod.get(k)
        if p:
            corto.append(f"  {k:5s} {p['vivas']:4d} sin cerrar · {p['empresas']:3d} empresas")
    corto += ["", "ODOO"]
    for k in ("CLIENTE", "PIPELINE", "PROSPECTO"):
        corto.append(f"  {k:10s} {odoo_resumen.get(k, 0)} frentes")
    corto += ["", "TOP 5 CUENTAS (solo ODOO cliente, reqs sumados)"]
    cuentas_cli = {}
    for f in filas:
        if f.get("relacion") != "ODOO · cliente":
            continue
        e = cuentas_cli.setdefault(f["empresa"], {"reqs": 0, "prods": set()})
        e["reqs"] += f["n_reqs"]
        e["prods"].add(f["producto"])
    for i, (emp, d) in enumerate(
            sorted(cuentas_cli.items(), key=lambda x: -x[1]["reqs"])[:5], 1):
        corto.append(f"  {i}. {emp} — {d['reqs']} reqs — {', '.join(sorted(d['prods']))}")
    with open(os.path.join(BASE, "out", "resumen_cron.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(corto))

    print(f"atacables: {len(atacables)} · con mora viva: {len(vivas)} · con contacto: {len(con_contacto)}")
    print(ruta)
    return atacables, top


if __name__ == "__main__":
    main()
