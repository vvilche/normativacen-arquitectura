#!/usr/bin/env python3
"""
Baja los PDFs de los documentos ENVIADOS por el CEN que piden algo, para leer el texto completo
y la Lista de Distribución. Cachea en cache_pdf/<carta_id>.txt — correr dos veces no vuelve a bajar.

Los PDFs del CEN son texto nativo (verificado sobre DE03965-25): no hace falta OCR.

Uso:
  python3 src/bajar_pdfs.py              # todos los candidatos
  python3 src/bajar_pdfs.py --desde 2025-01-01
"""
import json
import os
import re
import sys
import time
import datetime
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))
import motor  # noqa: E402


def candidatos(desde=None):
    with open(os.path.join(BASE, "data", "cartas_cen_full.json"), encoding="utf-8") as f:
        crudo = json.load(f)
    out, visto = [], set()
    for c in crudo:
        if c.get("tipo") != "Enviado":
            continue
        mat = motor.limpiar_materia(c.get("materia_micro"))
        txt_listado = " ".join([mat, c.get("materia_macro") or ""])
        # interesa si pide algo Y toca un producto normativo (por el listado, aunque esté truncado)
        if not motor.REGEX_PIDE.search(txt_listado):
            continue
        if not motor.producto_de(txt_listado):
            continue
        f = motor.fecha(c.get("fecha"))
        if not f:
            continue
        if desde and f < desde:
            continue
        cid = c.get("carta_id")
        if not cid or cid in visto:
            continue
        visto.add(cid)
        out.append((cid, c.get("correlativo"), f))
    return out


def main():
    desde = None
    if "--desde" in sys.argv:
        desde = datetime.date.fromisoformat(sys.argv[sys.argv.index("--desde") + 1])
    cand = candidatos(desde)
    os.makedirs(motor.CACHE, exist_ok=True)
    pendientes = [c for c in cand if not os.path.exists(os.path.join(motor.CACHE, f"{c[0]}.txt"))]
    print(f"candidatos: {len(cand)} · ya en cache: {len(cand)-len(pendientes)} · a bajar: {len(pendientes)}")

    ok = falla = 0
    errores = {}

    def uno(c):
        nonlocal ok, falla
        t = motor.texto_pdf(c[0], bajar=True)
        if t:
            ok += 1
            return
        # reintento: el servidor del CEN corta cuando hay mucha concurrencia
        time.sleep(1.5)
        if motor.texto_pdf(c[0], bajar=True):
            ok += 1
        else:
            falla += 1
            errores[c[1]] = errores.get(c[1], 0) + 1

    t0 = time.time()
    # 2 hilos: con 6 el sitio devuelve conexiones cortadas (medido: 260/274 fallas)
    with ThreadPoolExecutor(max_workers=2) as ex:
        for i, _ in enumerate(ex.map(uno, pendientes), 1):
            if i % 25 == 0:
                print(f"  {i}/{len(pendientes)} ok={ok} falla={falla} "
                      f"({time.time()-t0:.0f}s)", flush=True)
    print(f"listo: ok={ok} falla={falla} en {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
