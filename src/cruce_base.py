#!/usr/bin/env python3
"""
Cruce del radar normativo contra la BASE INSTALADA de CONECTA.

Responde la pregunta comercial que importa: de las cuentas con mora normativa, ¿a cuáles ya les
vendimos algo? A un cliente existente no se le vende de cero: se le cierra lo vendido o se le amplía.

Fuentes (todas en disco, ninguna inventada):
  1. ~/conecta-agentes/indices/motor_bom.jsonl  → 1.133 BOMs con cliente y línea.
     Es la historia comercial real: qué se cotizó, a quién y por cuánto.
  2. ~/conocimiento_operaciones/OT 7000/        → OTs ejecutadas (carpetas por proyecto).
  3. Odoo producción                            → NO DISPONIBLE (la key es de la base de test,
     que ya no existe). Se declara como pendiente, no se simula.

Salida: out/cruce_base_instalada.json + las columnas "relación" y "historia" en el reporte de campaña.
"""
import json
import os
import re
import unicodedata
import collections

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOM = os.path.expanduser("~/conecta-agentes/indices/motor_bom.jsonl")
OTS = os.path.expanduser("~/conocimiento_operaciones")

# Línea de BOM → producto normativo del radar. Traduce "qué le vendimos" a "qué le pidieron".
LINEA_A_PRODUCTO = {
    "PMU": {"PMU"},
    "PDC": {"PMU"},
    "EDAC": {"EDAC", "EDAG"},
    "Repro": {"PROTECCIONES", "SLRP"},
    "SCADA": {"SCADA", "SITR"},
    "RTU": {"SITR", "SCADA"},
    "Medición": {"SSCC"},
    "GPS": set(),
    "Licencias": set(),
}

STOP = {"SA", "SPA", "LTDA", "LIMITADA", "CHILE", "DEL", "LOS", "LAS", "DE", "Y", "EMPRESA",
        "ELECTRICA", "SOCIEDAD", "GENERACION", "ENERGIA", "COMPANIA", "INVERSIONES", "TRANSMISORA",
        "GENERADORA", "PARQUE", "CHILENA", "GRUPO", "ANDES"}


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").upper()
    s = re.sub(r"\b(S\.?A\.?|SPA|LTDA|LIMITADA|CHILE)\b", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return " ".join(w for w in s.split() if w and w not in STOP)


def tokens(s):
    return {w for w in norm(s).split() if len(w) > 2}


def misma(a, b):
    """Mismo cliente: comparten el nombre propio (la base usa nombres cortos: 'Transelec', 'AES')."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    for x in ta:
        for y in tb:
            if x == y:
                return True
            if min(len(x), len(y)) >= 5 and (x.startswith(y) or y.startswith(x)):
                return True
    return False


def cargar_boms():
    if not os.path.exists(BOM):
        return []
    out = []
    for line in open(BOM, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        out.append({
            "cliente": (r.get("cliente") or "").strip(),
            "linea": r.get("linea") or "",
            "total_hh": r.get("total_hh") or 0,
            "uf": r.get("uf") or 0,
        })
    return out


def cargar_ots():
    """OTs ejecutadas: nombre de carpeta 'OT 7066 - GENERADORA METROPOLITANA - Licencia PMU...'"""
    d = os.path.join(OTS, "OT 7000")
    if not os.path.isdir(d):
        return []
    out = []
    for name in os.listdir(d):
        m = re.match(r"OT\s*(\d{4})[^\-]*-\s*(.+?)\s*-\s*(.+)$", name)
        if m:
            out.append({"ot": f"OT {m.group(1)}", "cliente": m.group(2).strip(),
                        "proyecto": m.group(3).strip()})
    return out


def main():
    radar = json.load(open(os.path.join(BASE, "out", "radar.json"), encoding="utf-8"))
    opps = [o for o in radar["oportunidades"] if o["empresa"].strip()]
    boms = cargar_boms()
    ots = cargar_ots()

    # Resumen de historia por cliente (una sola vez)
    hist = collections.defaultdict(lambda: {"lineas": set(), "n_bom": 0, "hh": 0.0, "uf": 0.0,
                                            "ots": []})
    for b in boms:
        if not b["cliente"]:
            continue
        h = hist[norm(b["cliente"])]
        h["lineas"].add(b["linea"])
        h["n_bom"] += 1
        h["hh"] += b["total_hh"]
        h["uf"] += b["uf"]
        h.setdefault("nombre", b["cliente"])
    for o in ots:
        h = hist[norm(o["cliente"])]
        h["ots"].append(f"{o['ot']} · {o['proyecto']}")
        h.setdefault("nombre", o["cliente"])

    # Cruzar cada oportunidad
    filas, cuenta = [], collections.Counter()
    for o in opps:
        h = None
        for k, v in hist.items():
            if misma(o["empresa"], v.get("nombre", "") or k):
                h = v
                break
        if h:
            prods_vendidos = set()
            for ln in h["lineas"]:
                prods_vendidos |= LINEA_A_PRODUCTO.get(ln, set())
            lineas_ok = {x for x in h["lineas"] if x}
            if not lineas_ok:
                # 392 de 1.133 BOMs no traen línea (35%): es cliente, pero no se puede afirmar qué
                # se le vendió. Decirlo así, en vez de clasificarlo como si se supiera.
                rel = "CLIENTE · sin detalle de línea"
            elif o["producto"] in prods_vendidos:
                rel = "CLIENTE · mismo producto"
            else:
                rel = "CLIENTE · producto nuevo"
        else:
            rel = "PROSPECTO"
            prods_vendidos = set()
        cuenta[rel] += 1
        filas.append({**o, "relacion": rel,
                      "historia": ({"lineas": sorted(x for x in h["lineas"] if x),
                                    "n_bom": h["n_bom"], "hh": round(h["hh"]),
                                    "uf": round(h["uf"], 1),
                                    "ots": h["ots"][:3]} if h else None)})

    # Un cliente que ya compró exactamente lo que el CEN le pide = conversación de cierre, no de venta
    cierre = [f for f in filas if f["relacion"] == "CLIENTE · mismo producto"]
    cierre.sort(key=lambda x: (-x["n_reqs"], -x["dias_max"]))
    clientes = [f for f in filas if f["relacion"].startswith("CLIENTE")]

    out = {
        "fuentes": {
            "boms": f"{len(boms)} BOMs de {len({b['cliente'] for b in boms if b['cliente']})} clientes",
            "ots": f"{len(ots)} OTs ejecutadas",
            "odoo": "NO DISPONIBLE: la key disponible es de la base de test (ya no existe) "
                    "y no autentica en producción",
        },
        "cuentas_por_relacion": dict(cuenta),
        "filas": filas,
    }
    ruta = os.path.join(BASE, "out", "cruce_base_instalada.json")
    json.dump(out, open(ruta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # Devuelve las listas que el reporte de campaña necesita
    print(f"pares cruzados        : {len(filas)}")
    for k, v in cuenta.most_common():
        print(f"  {k:28s} {v}")
    print(f"\nCLIENTES con el CEN pidiendo lo mismo que ya les vendimos: {len(cierre)}")
    for f in cierre[:12]:
        h = f["historia"]
        print(f"  {f['empresa'][:32]:34s} {f['producto']:12s} {f['n_reqs']:2d} req · "
              f"{', '.join(h['lineas'])} · {h['n_bom']} BOMs")
    print(f"\n→ {ruta}")


if __name__ == "__main__":
    main()
