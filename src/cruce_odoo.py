#!/usr/bin/env python3
"""
Cruce del radar contra ODOO PRODUCCIÓN: ¿en qué etapa está cada cuenta y por cuánto?

Endpoint: https://conecta-erp.odoo.com · db conecta-aws-odoo-conecta-odoo-17929454 · uid 21
Credencial: ~/CONECTA_Proyecto/CONECTA_Conocimiento/odoo_prod_creds.json (verificada).

Pitfalls que respeta (de la skill odoo-jsonrpc-integration):
  - Matchear por partner_id, NO por el nombre del lead: en Odoo una PMU puede llamarse
    "2 x PMU - Central Lautaro" sin decir el cliente.
  - No pedir campos con punto ('partner_id.name') en search_read: el error se confunde con
    "no hay datos". Se pide 'partner_id' y se resuelve el nombre desde la tupla.
  - Deduplicar por id de lead.
  - Solo campos que existen: hay Studio que agrega x_studio_*, no se asume.

Salida: out/cruce_odoo.json
"""
import json
import os
import re
import sys
import unicodedata

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDS = os.path.expanduser("~/CONECTA_Proyecto/CONECTA_Conocimiento/odoo_prod_creds.json")

STOP = {"SA", "SPA", "LTDA", "LIMITADA", "CHILE", "DEL", "LOS", "LAS", "DE", "Y", "EMPRESA",
        "ELECTRICA", "SOCIEDAD", "GENERACION", "ENERGIA", "COMPANIA", "INVERSIONES", "TRANSMISORA",
        "GENERADORA", "PARQUE", "CHILENA", "GRUPO"}


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").upper()
    s = re.sub(r"\b(S\.?A\.?|SPA|LTDA|LIMITADA|CHILE)\b", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return " ".join(w for w in s.split() if w and w not in STOP)


class Odoo:
    def __init__(self, path=CREDS):
        c = json.load(open(path))
        self.host = (c.get("host") or "").rstrip("/")
        self.db = c.get("db")
        self.user = c.get("username") or c.get("user")
        self.key = c.get("api_key") or c.get("apikey")
        self.uid = self._call("common", "login", [self.db, self.user, self.key])
        if not self.uid:
            sys.exit("Odoo producción: login falló (uid=False). No se genera el cruce.")

    def _call(self, svc, mtd, args):
        r = requests.post(self.host + "/jsonrpc", json={
            "jsonrpc": "2.0", "method": "call", "id": 1,
            "params": {"service": svc, "method": mtd, "args": args}}, timeout=90)
        j = r.json()
        if "error" in j:
            raise RuntimeError(str(j["error"])[:300])
        return j.get("result")

    def kw(self, model, method, args, kw=None):
        return self._call("object", "execute_kw",
                          [self.db, self.uid, self.key, model, method, args, kw or {}])


def main():
    o = Odoo()

    # Leads con partner (el nombre del lead no sirve para identificar al cliente)
    campos = ["id", "name", "partner_id", "stage_id", "type"]
    leads = o.kw("crm.lead", "search_read", [[["partner_id", "!=", False]]],
                 {"fields": campos, "limit": 5000}) or []

    # importe esperado: se pide aparte por si el campo no existe en esta base
    try:
        entra = o.kw("crm.lead", "search_read", [[["partner_id", "!=", False]]],
                     {"fields": ["id", "expected_revenue"], "limit": 5000}) or []
        rev = {x["id"]: x.get("expected_revenue") or 0 for x in entra}
    except Exception:
        rev = {}

    idx = {}
    seen = set()
    for l in leads:
        if l["id"] in seen:            # dedupe por id
            continue
        seen.add(l["id"])
        p = l.get("partner_id")
        if not p:
            continue
        k = norm(p[1])
        e = idx.setdefault(k, {"partner": p[1], "leads": 0, "etapas": {}, "usd": 0.0,
                               "abiertos": 0, "ganados": 0})
        e["leads"] += 1
        etapa = (l.get("stage_id") or [0, "?"])[1]
        e["etapas"][etapa] = e["etapas"].get(etapa, 0) + 1
        e["usd"] += rev.get(l["id"], 0) or 0
        if re.search(r"won|ganad", etapa, re.I):
            e["ganados"] += 1
        elif not re.search(r"lost|perdid|cancel|fuera", etapa, re.I):
            e["abiertos"] += 1

    radar = json.load(open(os.path.join(BASE, "out", "radar.json"), encoding="utf-8"))
    opps = [x for x in radar["oportunidades"] if x["empresa"].strip()]

    filas, cuenta = [], {"CLIENTE": 0, "PIPELINE": 0, "PROSPECTO": 0}
    for x in opps:
        k = norm(x["empresa"])
        e = idx.get(k)
        # segundo intento por prefijo (filiales y nombres mutilados del CEN)
        if not e:
            for kk, vv in idx.items():
                if kk and k and (kk.startswith(k[:12]) or k.startswith(kk[:12])):
                    e = vv
                    break
        if e and e["ganados"]:
            estado = "CLIENTE"
        elif e and e["leads"]:
            estado = "PIPELINE"
        else:
            estado = "PROSPECTO"
        cuenta[estado] += 1
        filas.append({**x, "odoo": (estado if e else None),
                      "odoo_etapas": (e["etapas"] if e else None),
                      "odoo_usd": (round(e["usd"]) if e else None),
                      "odoo_leads": (e["leads"] if e else None),
                      "odoo_partner": (e["partner"] if e else None)})

    out = {"fuente": f"Odoo producción {o.host} db={o.db} uid={o.uid}",
           "leads_leidos": len(leads), "partners": len(idx),
           "cuentas_por_estado": cuenta, "filas": filas,
           # El monto de Odoo es del CLIENTE, no del producto: se repite en cada fila de ese
           # cliente. Va aparte para que no se lea como "USD por producto" ni se sume por fila.
           "monto_por_cuenta": {v["partner"]: round(v["usd"]) for v in idx.values() if v["usd"]}}
    ruta = os.path.join(BASE, "out", "cruce_odoo.json")
    json.dump(out, open(ruta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"Odoo: {o.host} uid={o.uid} · {len(leads)} leads · {len(idx)} partners")
    for k, v in cuenta.items():
        print(f"  {k:10s} {v}")
    print(f"→ {ruta}")


if __name__ == "__main__":
    main()
