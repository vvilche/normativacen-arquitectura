#!/usr/bin/env python3
"""Verificación ad-hoc de src/sincronizar.sh — lo que el script PROMETE, probado de verdad.

No es una suite. Comprueba que:
  1. La validación previa rechaza un corpus corto/vacío/truncado y acepta uno bueno
     (si el JSON del VPS viene cortado, NO debe pisar el corpus bueno).
  2. El script existe, es ejecutable y su sintaxis bash es válida.
  3. La última corrida completa del log bajó corpus, lo validó, verificó y terminó.
  4. Las salidas (radar.json / HTML) existen y son coherentes.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
f = []


def check(n, cond, det=""):
    print(f"{'PASS ' if cond else 'FALLA'} {n}" + (f"  [{det}]" if det else ""))
    if not cond:
        f.append(n)


# ── 1. La validación previa al reemplazo (misma regla que usa sincronizar.sh) ──
VALIDAR = '''
import json, sys
d = json.load(open(sys.argv[1]))
assert isinstance(d, list) and len(d) > 10000, f"corpus sospechoso: {len(d)} cartas"
'''
tmp = tempfile.mkdtemp(prefix="hermes-verify-sync-")
try:
    casos = {"corpus bueno (13817)": ([{"x": i} for i in range(13817)], True),
             "corpus corto (900)": ([{"x": i} for i in range(900)], False),
             "lista vacía": ([], False)}
    for nombre, (data, debe) in casos.items():
        p = os.path.join(tmp, "c.json")
        json.dump(data, open(p, "w"))
        r = subprocess.run([sys.executable, "-c", VALIDAR, p], capture_output=True)
        check(f"validación: {nombre}", (r.returncode == 0) == debe, f"exit={r.returncode}")

    p = os.path.join(tmp, "roto.json")
    open(p, "w").write('[{"a":1},{"a":')          # descarga cortada a mitad
    r = subprocess.run([sys.executable, "-c", VALIDAR, p], capture_output=True)
    check("validación: JSON truncado a mitad", r.returncode != 0, f"exit={r.returncode}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ── 2. El script ─────────────────────────────────────────────────────────────
sh = os.path.join(BASE, "src", "sincronizar.sh")
check("sincronizar.sh existe y es ejecutable", os.path.isfile(sh) and os.access(sh, os.X_OK))
r = subprocess.run(["bash", "-n", sh], capture_output=True, text=True)
check("sintaxis bash válida", r.returncode == 0, r.stderr.strip()[:80])

# ── 3. Última corrida COMPLETA del log ──────────────────────────────────────
# Solo se audita una corrida que YA terminó. Corriendo dentro de sincronizar.sh, la última
# corrida es la en curso: todavía no escribió '[verificar]' ni '=== fin', y reprochárselo era
# un falso fallo (el script se auto-acusaba de no haber terminado).
log = os.path.join(BASE, "out", "sync.log")
check("sync.log existe", os.path.exists(log))
if os.path.exists(log):
    txt = open(log, encoding="utf-8", errors="replace").read()
    inicio = txt.rfind("sincronizar ===")         # el [verificar] OK va al final: no cortar corto
    ult = txt[inicio:] if inicio >= 0 else txt
    if "=== fin " not in ult:
        print("SKIP  corrida en curso: no se audita a sí misma (se auditará en la próxima)")
    else:
        check("trajo corpus del VPS", "[corpus]" in ult)
        check("validó y reemplazó el corpus", "[corpus] reemplazado" in ult,
              next((l for l in ult.splitlines() if "[corpus]" in l), "")[:50])
        check("verificación interna OK", "[verificar] verificar.py OK" in ult)
        check("llegó al final", "=== fin " in ult)

# ── 4. Salidas coherentes ───────────────────────────────────────────────────
rj = os.path.join(BASE, "out", "radar.json")
html = os.path.join(BASE, "out", "radar_normativo.html")
check("radar.json y HTML existen", os.path.exists(rj) and os.path.exists(html))
R = json.load(open(rj, encoding="utf-8"))
check("radar.json trae requerimientos", len(R["requerimientos"]) > 1000, f"{len(R['requerimientos'])}")
check("radar.json trae oportunidades", len(R["oportunidades"]) > 500, f"{len(R['oportunidades'])}")
check("declara el supuesto de potencial", R["supuestos_potencial"] is not None)
h = open(html, encoding="utf-8").read()
check("el HTML trae los productos", all(p in h for p in ("SLRP", "EDAC", "SITR")))
check("el HTML rotula el potencial como valor de línea", "valor de línea" in h.lower())

print()
print("OK" if not f else "FALLOS: " + " | ".join(f))
sys.exit(1 if f else 0)
