#!/usr/bin/env python3
"""
Genera el reporte semanal del Radar Normativo CEN en HTML (una sola vista, autónoma).

Entrada : out/radar.json (lo produce src/motor.py)
Salida  : out/radar_normativo.html

Diseño: una sola página, agrupada por producto normativo. Arriba el resumen (lo que se lee en 20
segundos); al hacer clic en un producto se abre el detalle de las empresas con su estado y su carta.
Sin dependencias externas: se abre con doble clic y funciona sin internet.
"""
import json
import os
import datetime
import collections
import html

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out")

ESTADOS = {
    "SIN_RESPUESTA": ("Sin respuesta", "#c0392b", "El CEN se lo pidió y el coordinado no ha respondido."),
    "REITERADO":     ("Reiterado",      "#d35400", "El CEN insistió: 2 o más cartas sobre lo mismo."),
    "REABIERTO":     ("Reabierto",      "#8e44ad", "Respondió y el CEN volvió a escribirle."),
    "RESPONDIDO":    ("Respondido",     "#1e8449", "Respondió y el CEN cerró."),
    "MIXTO":         ("Mixto",          "#7f8c8d", "Acumula varios estados a la vez."),
}


def e(s):
    return html.escape(str(s if s is not None else ""))


def fmt_clp(n):
    return f"${n:,.0f}".replace(",", ".")


def main():
    with open(os.path.join(OUT, "radar.json"), encoding="utf-8") as f:
        d = json.load(f)

    corp = d["corpus"]
    prods = d["por_producto"]
    opps = d["oportunidades"]
    sup = d["supuestos_potencial"]

    # ── Resumen: lo que un humano lee primero ────────────────────────────────
    total_vivo = sum(p["sin_respuesta"] + p["reiterado"] + p["reabierto"] for p in prods)
    empresas_vivas = len({o["empresa"] for o in opps})
    monto = sum(o["usd_venta"] for o in opps)

    # Top: la empresa más cargada, por producto
    por_prod_emp = collections.defaultdict(list)
    for o in opps:
        por_prod_emp[o["producto"]].append(o)
    for k in por_prod_emp:
        por_prod_emp[k].sort(key=lambda x: (-x["n_reqs"], -x["usd_venta"]))

    # ── Bloque Odoo ─────────────────────────────────────────────────────────
    odoo_txt = ""
    if d["odoo"]["estado"] not in ("ok",):
        odoo_txt = (f'<div class="warn">Cruce con Odoo: <b>no ejecutado</b> '
                    f'({e(d["odoo"]["estado"])}). Las cuentas de abajo no distinguen '
                    f'cliente / pipeline / prospecto.</div>')

    filas = []
    for p in prods:
        vivas = p["sin_respuesta"] + p["reiterado"] + p["reabierto"]
        emp_top = por_prod_emp.get(p["producto"], [])[:6]
        detalle = "".join(
            f'<tr><td>{e(o["empresa"])}</td>'
            f'<td><span class="pill" style="background:{ESTADOS[o["estado_peor"]][1]}">'
            f'{ESTADOS[o["estado_peor"]][0]}</span></td>'
            f'<td class="num">{o["n_reqs"]}</td>'
            f'<td class="num dim" title="Valor de la línea de producto, no de esta empresa">{fmt_clp(o["usd_venta"])}</td>'
            f'<td class="corr">{e(", ".join(o["correlativos"][:3]))}</td></tr>'
            for o in emp_top)
        circ = (f'<div class="nota">+ {p["circulares_sin_lista"]} circular(es) sobre {e(p["producto"])} '
                f'que piden algo y no se pudo leer su lista de distribución (sin PDF). '
                f'No están contadas arriba.</div>' if p["circulares_sin_lista"] else "")
        filas.append(f"""
<details class="prod">
 <summary>
   <span class="pname">{e(p["producto"])}</span>
   <span class="psub">{e(p["nombre"])}</span>
   <span class="counts">
     <span class="c red">{p["sin_respuesta"]}</span>
     <span class="c org">{p["reiterado"]}</span>
     <span class="c pur">{p["reabierto"]}</span>
     <span class="c grey">{vivas} vivas / {p["n_reqs"]} req</span>
   </span>
 </summary>
 <div class="body">
   <div class="sol"><b>Solución CONECTA:</b> {e(p["solucion"])}</div>
   <div class="sol dim"><b>Norma:</b> {e(p["norma"])} · {p["empresas"]} empresas · última carta {e(p["ultima"])}</div>
   <table>
     <thead><tr><th>Coordinado</th><th>Estado</th><th>Reqs</th><th>Valor línea</th><th>Correlativos</th></tr></thead>
     <tbody>{detalle}</tbody>
   </table>
   {circ}
 </div>
</details>""")

    leyenda = "".join(f'<span class="lg"><i style="background:{c}"></i>{n}: {e(t)}</span>'
                      for k, (n, c, t) in ESTADOS.items() if k != "MIXTO")

    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Radar Normativo CEN — {datetime.date.today().isoformat()}</title>
<style>
:root{{--ink:#1a1a1a;--dim:#6b6b6b;--line:#e4e4e7;--bg:#fafafa;--accent:#185fa5}}
*{{box-sizing:border-box}}
body{{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;
color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1080px;margin:0 auto;padding:32px 24px 80px}}
h1{{font-size:23px;font-weight:650;margin:0 0 4px;letter-spacing:-.01em}}
.sub{{color:var(--dim);font-size:13.5px;margin-bottom:26px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}}
.kpi{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
.kpi .n{{font-size:26px;font-weight:650;letter-spacing:-.02em;line-height:1.15}}
.kpi .l{{font-size:11.5px;color:var(--dim);text-transform:uppercase;letter-spacing:.04em;margin-top:3px}}
.kpi .h{{font-size:11.5px;color:var(--dim);margin-top:6px}}
.leyenda{{display:flex;flex-wrap:wrap;gap:16px;margin:18px 0 26px;font-size:12.5px;color:var(--dim)}}
.lg{{display:flex;align-items:center;gap:6px}}
.lg i{{width:9px;height:9px;border-radius:50%;display:inline-block}}
h2{{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);
font-weight:600;margin:30px 0 10px}}
details.prod{{background:#fff;border:1px solid var(--line);border-radius:10px;margin-bottom:8px;overflow:hidden}}
details.prod[open]{{border-color:#c9c9cf}}
summary{{cursor:pointer;padding:13px 16px;display:grid;grid-template-columns:110px 1fr auto;
align-items:center;gap:14px;list-style:none}}
summary::-webkit-details-marker{{display:none}}
summary:hover{{background:#fcfcfd}}
.pname{{font-weight:650;font-size:14.5px}}
.psub{{font-size:12.5px;color:var(--dim)}}
.counts{{display:flex;gap:7px;align-items:center}}
.c{{font-size:11.5px;font-weight:600;padding:2px 8px;border-radius:20px;background:#f2f2f4}}
.c.red{{background:#fdecea;color:#c0392b}} .c.org{{background:#fef2e6;color:#d35400}}
.c.pur{{background:#f5eafb;color:#8e44ad}} .c.grey{{background:#f2f2f4;color:#555}}
.body{{padding:2px 16px 16px;border-top:1px solid var(--line)}}
.sol{{font-size:13px;margin:12px 0 3px}}
.sol.dim{{color:var(--dim);font-size:12px;margin-bottom:12px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--dim);
font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line)}}
td{{padding:7px 8px;border-bottom:1px solid #f2f2f4;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.corr{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;color:var(--dim)}}
.pill{{font-size:11px;font-weight:600;color:#fff;padding:2px 8px;border-radius:20px;white-space:nowrap}}
.nota{{margin-top:10px;font-size:11.5px;color:#8a6d00;background:#fffbf0;border-left:3px solid #e6c34a;
padding:7px 10px;border-radius:0 5px 5px 0}}
.warn{{background:#fff4f4;border:1px solid #f0c2c2;border-left:3px solid #c0392b;padding:10px 13px;
border-radius:0 6px 6px 0;font-size:12.5px;margin-bottom:18px}}
footer{{margin-top:38px;padding-top:16px;border-top:1px solid var(--line);font-size:11.5px;color:var(--dim)}}
footer a{{color:var(--accent)}}
@media(max-width:720px){{.kpis{{grid-template-columns:repeat(2,1fr)}}
summary{{grid-template-columns:1fr;gap:6px}}}}
</style></head><body><div class="wrap">

<h1>Radar Normativo CEN</h1>
<div class="sub">Qué le pidió el Coordinador a quién, sobre qué producto normativo, y quién está al debe.
Generado {e(d["generado"][:16].replace("T"," "))} · cartas del {e(corp["rango"][0])} al {e(corp["rango"][1])}</div>

<div class="kpis">
  <div class="kpi"><div class="n">{total_vivo}</div><div class="l">Requermientos vivos</div>
    <div class="h">sin respuesta + reiterados + reabiertos</div></div>
  <div class="kpi"><div class="n">{empresas_vivas}</div><div class="l">Coordinados involucrados</div>
    <div class="h">con al menos una carta por responder</div></div>
  <div class="kpi"><div class="n">{fmt_clp(monto)}</div><div class="l">Valor de línea (USD)</div>
    <div class="h">suma de valores de producto, NO pipeline real</div></div>
  <div class="kpi"><div class="n">{corp["cartas_total"]:,}</div><div class="l">Documentos leídos</div>
    <div class="h">{corp["pdfs_leidos"]} con texto de PDF</div></div>
</div>

{odoo_txt}

<div class="leyenda">{leyenda}</div>

<h2>Por producto normativo</h2>
{"".join(filas)}

<footer>
<p><b>Valor de línea, y hay que leerlo como tal:</b> {e(sup["fuente"]) if sup else "sin tarifario"}.
Cálculo: HH mediana real de la línea de BOM × {e(sup["uf_h"]) if sup else "?"} UF/h
(mezcla 30% senior / 40% A / 30% B) × {e(sup["uf_usd"]) if sup else 40} USD/UF.
<b>El monto depende del PRODUCTO, no de la empresa</b>: todas las cuentas con el mismo producto
muestran el mismo valor, porque el dato del CEN no trae el tamaño de cada coordinado. Por eso el
reporte se ordena por gravedad de la mora, no por monto. Si se necesita un monto por empresa,
falta cruzarlo con el número de instalaciones de cada coordinado.</p>
<p><b>Método:</b> cartas ENVIADAS por el CEN que piden algo (excluye las respuestas del propio CEN
y los acuses de recibo). Una circular afecta a todas las empresas de su Lista de Distribución,
leída del PDF. Respuesta = carta recibida que cita el correlativo del requerimiento.
Estado calculado sobre {corp["cartas_total"]:,} documentos
({e(corp["clases"])}); {corp["truncadas_sin_pdf"]} tienen la materia truncada y sin PDF.</p>
<p>Fuente: cartas.coordinador.cl · corpus sincronizado en el VPS · proyecto
~/orca/projects/RadarNormativoCEN</p>
</footer>
</div></body></html>"""

    ruta = os.path.join(OUT, "radar_normativo.html")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(doc)
    print(ruta)


if __name__ == "__main__":
    main()
