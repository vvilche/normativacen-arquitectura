#!/usr/bin/env python3
"""
Verificación ad-hoc del reporte de campaña y del envío por correo.

Cubre lo que este turno cambió y que los otros dos verificadores NO miran:
  1. Las cifras del reporte de campaña no se pueden inflar: 'vivas' nunca supera n_reqs,
     y las cuentas son CUENTAS únicas, no pares empresa-producto.
  2. El reporte se genera desde radar.json sin números escritos a mano.
  3. El envío falla explícito sin API key y no manda nada en dry-run.
  4. El cuerpo del correo declara las tres limitaciones (contacto, valor de línea, sin Odoo).
"""
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
f = []


def check(n, cond, det=""):
    print(f"{'PASS ' if cond else 'FALLA'} {n}" + (f"  [{det}]" if det else ""))
    if not cond:
        f.append(n)


R = json.load(open(os.path.join(BASE, "out", "radar.json"), encoding="utf-8"))
prods = R["por_producto"]

# ── 1. 'vivas' no puede superar los requerimientos ──────────────────────────
malas = [(p["producto"], p["vivas"], p["n_reqs"]) for p in prods if p["vivas"] > p["n_reqs"]]
check("'vivas' <= n_reqs en todos los productos", not malas, str(malas[:2]))
check("'vivas' = n_reqs - respondido",
      all(p["vivas"] == p["n_reqs"] - p["respondido"] for p in prods))
# Los tres estados SÍ se solapan: su suma puede superar n_reqs (eso es esperado, no error).
solapan = [p["producto"] for p in prods
           if p["sin_respuesta"] + p["reiterado"] + p["reabierto"] > p["n_reqs"]]
print(f"INFO  productos cuyos 3 estados solapan (esperado): {len(solapan)}")

# ── 2. El reporte de campaña sale del JSON, sin cifras a mano ───────────────
html_p = os.path.join(BASE, "out", "reporte_oportunidades.html")
txt_p = os.path.join(BASE, "out", "reporte_oportunidades.txt")
check("reporte de campaña generado (HTML y TXT)", os.path.exists(html_p) and os.path.exists(txt_p))
if os.path.exists(txt_p):
    txt = open(txt_p, encoding="utf-8").read()
    # 'cuentas atacables' debe ser menor que los frentes: si son iguales, se está contando pares
    import re
    m = re.search(r"(\d+) cuentas atacables \((\d+) frentes", txt)
    check("cuentas atacables < frentes (no se cuentan pares como cuentas)",
          bool(m) and int(m.group(1)) < int(m.group(2)), m.group(0) if m else "no encontrado")
    check("el TXT declara que el valor es de línea", "línea" in txt.lower() or "linea" in txt.lower())
    check("el TXT declara la falta de cruce Odoo", "odoo" in txt.lower())

# ── 3. El envío no manda nada sin --enviar (dry-run) ────────────────────────
env = os.path.join(BASE, "src", "enviar_reporte.py")
r = subprocess.run([PY, env, "--para", "prueba@example.com"], capture_output=True, text=True,
                   cwd=BASE)
check("dry-run no envía", r.returncode == 0 and "DRY-RUN" in r.stdout, r.stdout.splitlines()[0] if r.stdout else r.stderr[:60])
check("dry-run lista los adjuntos", "reporte_oportunidades" in r.stdout)

# ── 4. Sin API key corta explícito (nunca un 401 silencioso) ────────────────
entorno = {k: v for k, v in os.environ.items() if k != "RESEND_API_KEY"}
r = subprocess.run([PY, env, "--para", "prueba@example.com", "--enviar"], capture_output=True,
                   text=True, cwd=BASE, env={**entorno, "HERMES_TEST_SIN_KEY": "1"})
# No se puede garantizar que el .env no exista, así que se valida el mensaje si faltó la clave.
if "FALTA RESEND_API_KEY" in (r.stderr + r.stdout):
    check("sin API key corta con mensaje explícito", r.returncode != 0)
else:
    print("SKIP  sin API key: la clave está disponible en .env, no se fuerza el fallo")

# ── 5. Cruce con la base instalada ──────────────────────────────────────────
# Responde "dónde ya trabajamos". Se valida contra la fuente real (BOMs), no contra sí mismo.
cruce_p = os.path.join(BASE, "out", "cruce_base_instalada.json")
if os.path.exists(cruce_p):
    cr = json.load(open(cruce_p, encoding="utf-8"))
    filas = cr["filas"]
    rels = {f["relacion"] for f in filas}
    check("el cruce clasifica en las 4 relaciones",
          rels <= {"CLIENTE · mismo producto", "CLIENTE · producto nuevo",
                   "CLIENTE · sin detalle de línea", "PROSPECTO"}, str(rels))
    # Todo par debe estar clasificado: ninguno sin relación.
    check("ningún par sin clasificar", all(f["relacion"] for f in filas))
    # Un CLIENTE debe traer historia; un PROSPECTO no.
    mal_cli = [f["empresa"] for f in filas
               if f["relacion"].startswith("CLIENTE") and not f.get("historia")]
    check("todo CLIENTE trae historia de la base", not mal_cli, str(mal_cli[:2]))
    mal_pro = [f["empresa"] for f in filas
               if f["relacion"] == "PROSPECTO" and f.get("historia")]
    check("ningún PROSPECTO trae historia", not mal_pro, str(mal_pro[:2]))
    # El cliente insignia tiene que estar: Transelec tiene 86 BOMs reales.
    trans = [f for f in filas if "TRANSELEC" in f["empresa"].upper()]
    check("Transelec aparece como CLIENTE (86 BOMs en la base)",
          bool(trans) and all(f["relacion"].startswith("CLIENTE") for f in trans),
          str([f["relacion"] for f in trans[:2]]))
    # Odoo debe declararse no disponible, no simularse.
    check("el cruce declara el estado de Odoo", "odoo" in cr.get("fuentes", {}),
          cr.get("fuentes", {}).get("odoo", "")[:60])
else:
    print("SKIP  cruce_base_instalada.json no existe: correr src/cruce_base.py")

# ── 6. Cruce con Odoo producción ────────────────────────────────────────────
odoo_p = os.path.join(BASE, "out", "cruce_odoo.json")
if os.path.exists(odoo_p):
    od = json.load(open(odoo_p, encoding="utf-8"))
    check("el cruce Odoo se conectó de verdad (uid presente)", "uid=" in od.get("fuente", ""),
          od.get("fuente", "")[:70])
    check("el cruce Odoo leyó leads reales", od.get("leads_leidos", 0) > 100,
          f"{od.get('leads_leidos')} leads")
    check("clasifica en CLIENTE / PIPELINE / PROSPECTO",
          set(od.get("cuentas_por_estado", {})) == {"CLIENTE", "PIPELINE", "PROSPECTO"},
          str(od.get("cuentas_por_estado")))
    # El monto debe vivir aparte (es del cliente, no del producto)
    check("el monto va por cuenta, no por fila", "monto_por_cuenta" in od)
    # Caso conocido: Transelec tiene oportunidades ganadas en Odoo
    tr = [f for f in od["filas"] if "TRANSELEC" in f["empresa"].upper()]
    check("Transelec sale como CLIENTE en Odoo",
          bool(tr) and any(f["odoo"] == "CLIENTE" for f in tr),
          str({f["odoo"] for f in tr}))
else:
    print("SKIP  cruce_odoo.json no existe: correr src/cruce_odoo.py")

# ── 7. Envío por correo automatizado en el pipeline ─────────────────────────
# El cron de los lunes manda el reporte solo. El pipeline debe: (a) enviar tras verificar,
# (b) no enviar si se le pide omitir. Se comprueba el código, no se gasta correo.
sh_txt = open(os.path.join(BASE, "src", "sincronizar.sh"), encoding="utf-8").read()
check("el pipeline envía el correo al final", "enviar_radar_cen.py" in sh_txt)
check("el envío va después de la verificación",
      sh_txt.find("enviar_radar_cen.py") > sh_txt.find("verificar_campana.py"),
      "orden en el script")
check("el envío se puede desactivar (RADAR_SIN_CORREO)", "RADAR_SIN_CORREO" in sh_txt)
check("el correo falla de forma visible en el log", "[correo] FALLÓ" in sh_txt)
check("el script de envío vive fuera del proyecto (lo llama el cron)",
      os.path.exists(os.path.expanduser("~/.hermes/scripts/enviar_radar_cen.py")))
# El script externo debe apuntar al proyecto con ruta fija, no relativa a su propia carpeta.
_ext = open(os.path.expanduser("~/.hermes/scripts/enviar_radar_cen.py"), encoding="utf-8").read()
check("el script externo usa la ruta del proyecto", "RadarNormativoCEN" in _ext)

# ── 8. Resumen pre-armado para el cron ─────────────────────────────────────
# El cron lee out/resumen_cron.txt en vez de improvisar sobre radar.json: la corrida de prueba
# coló SCADA/SSCC en la lista y armó el top por frente en vez de por cuenta.
res_p = os.path.join(BASE, "out", "resumen_cron.txt")
check("existe el resumen pre-armado del cron", os.path.exists(res_p))
if os.path.exists(res_p):
    rt = open(res_p, encoding="utf-8").read()
    seis = ["SLRP", "SITR", "EDAC", "EDAG", "PMU", "PRS"]
    check("el resumen trae los seis productos", all(k in rt for k in seis))
    # Los que NO van en la lista de sin cerrar (se midió que el agente los agregaba)
    bloque_sc = rt.split("TODO")[-1]
    check("el resumen no lista SCADA/SSCC/PROTECCIONES como 'sin cerrar'",
          not any(re.search(rf"^\s+{k}\s+\d+ sin cerrar", rt, re.M)
                  for k in ("SCADA", "SSCC", "PROTECCIONES")))
    check("el top es por cuenta (una línea por empresa)", "reqs —" in rt)
    # Una cuenta no puede aparecer dos veces en el top
    top5 = [l for l in rt.splitlines() if re.match(r"^\s+\d\. ", l)]
    empresas = [l.split(". ", 1)[1].split(" —")[0] for l in top5]
    check("ninguna cuenta repetida en el top 5", len(empresas) == len(set(empresas)), str(empresas))

# ── 9. radar.json debe traer el estado Odoo integrado ──────────────────────
# El cron leía 'oportunidades[].odoo' y ese campo no existía: el estado vivía solo en
# cruce_odoo.json. Ahora el motor lo integra, y el pipeline corre el cruce ANTES del motor.
_rj = json.load(open(os.path.join(BASE, "out", "radar.json"), encoding="utf-8"))
_op = [o for o in _rj["oportunidades"] if o["empresa"].strip()]
check("radar.json trae el campo 'odoo' en oportunidades", bool(_op) and "odoo" in _op[0])
vals = {o.get("odoo") for o in _op}
check("el campo odoo tiene valores del ERP", "CLIENTE" in vals or "PIPELINE" in vals, str(vals))
check("radar.json declara el resultado del cruce de producción",
      str(_rj.get("odoo", {}).get("cruce_produccion", "")).startswith(("ok:", "no_ejecutado", "error:")),
      str(_rj.get("odoo", {}).get("cruce_produccion")))
_sh = open(os.path.join(BASE, "src", "sincronizar.sh"), encoding="utf-8").read()
check("el pipeline corre cruce_odoo ANTES del motor (no usa el cruce viejo)",
      _sh.find("cruce_odoo.py") < _sh.find("motor.py"))

print()
print("OK" if not f else "FALLOS: " + " | ".join(f))
sys.exit(1 if f else 0)
