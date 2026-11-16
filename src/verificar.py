#!/usr/bin/env python3
"""
Verificación ad-hoc del Radar Normativo CEN — estado ACTUAL del motor.

Contexto que importa: el motor NO está confiable en el padrón de empresas. Esta verificación
NO dice "todo bien". Verifica exactamente dos cosas, y deja constancia de la que falla:

  A) Lo que SÍ quedó firme: normalización, matcher de empresas y extracción de la LISTA DE
     DISTRIBUCIÓN en formato lista (no tabla). Se prueba contra cartas contadas a mano.
  B) Lo que HOY NO sirve: las cartas cuyo "padrón" es una TABLA de instalaciones (coordinado +
     nombre de planta + encabezados de columna). Ahí el motor infla los conteos, y el script lo
     deja en rojo a propósito en vez de maquillarlo.
"""
import json
import os
import re
import sys
import tempfile

BASE = "/Users/victorvilche/orca/projects/RadarNormativoCEN"
sys.path.insert(0, os.path.join(BASE, "src"))
import motor as M  # noqa: E402

f = []


def check(n, cond, det=""):
    print(f"{'PASS ' if cond else 'FALLA'} {n}" + (f"  [{det}]" if det else ""))
    if not cond:
        f.append(n)


# ── A. Lo firme ──────────────────────────────────────────────────────────────
check("norm_empresa colapsa sufijos",
      len({M.norm_empresa(x) for x in ["Colbún S.A.", "COLBUN S.A", "Colbun SpA", "colbun limitada"]}) == 1,
      M.norm_empresa("Colbún S.A."))
check("placeholder 'Ver × Empresas Cerrar' detectado", M.es_placeholder("Ver &times; Empresas Cerrar"))

PARES = [("Codelco (Corporación Nacional del Cobre)", "Codelco (Corporación Nacional del Cobr…", True),
         ("Eletrans II S.A.", "Eletrans III S.A.", False),
         ("Sonnedix Don Goyo Transmisión S.A.", "SonnediDon Goyo Transmisión S.A.", True),
         ("Enel Generación Chile S.A.", "Enel Green Power Chile S.A.", False),
         ("Chilquinta Distribución S.A.", "Enel Distribución Chile S.A.", False),
         ("Colbún S.A.", "COLBUN SpA", True)]
malos = [(a, b) for a, b, esp in PARES if M.misma_empresa(a, b) != esp]
check(f"misma_empresa: {len(PARES)} parejas", not malos, str(malos[:2]))

# Las palabras que también son razón social NO deben filtrarse (bug medido: Chilquinta/Enel Distribución)
check("'Distribución' no se filtra como frase basura",
      not M.FRASE_NO_EMPRESA.search("Chilquinta Distribución S.A."))
check("el pie de página SÍ se filtra",
      bool(M.FRASE_NO_EMPRESA.search("Av. Parque Isidora N°1061, Pudahuel")))

cartas, _d, _i = M.cargar()
# NO indexar por correlativo: el corpus trae documentos distintos con el mismo número (el de la
# empresa). Se busca la carta por correlativo Y por tener lista.
def con_lista(corr):
    return [c for c in cartas if c["correlativo"] == corr and c["destinatarios"]]

# Cartas contadas A MANO sobre el PDF, una por formato de lista
A_MANO = {"DE03965-25": 83, "DE04877-26": 23, "DE05627-26": 3,
          "DE02839-26": 170, "DE06736-26": 157}
for corr, n in A_MANO.items():
    cs = con_lista(corr)
    check(f"{corr}: lista de distribución = {n} (contadas a mano)",
          bool(cs) and len(cs[0]["destinatarios"]) == n,
          f"motor={len(cs[0]['destinatarios']) if cs else 'sin lista'}")

# El correlativo solo puede ser del CEN: el de la empresa no se toma como tal
check("correlativo de la empresa (CGET00527-2026) NO pasa como DE05627-26",
      M.correlativo_cen("CGET00527-2026") == "" and M.correlativo_cen("DE 05627-26") == "DE05627-26")
falsos = [c for c in cartas if c["correlativo"] and not M.CORRELATIVO_CEN.match(c["correlativo"])]
check("ningún correlativo fuera de formato del CEN en el corpus", not falsos, str(falsos[:2]))
# Las mineras que no llevan 'S.A.' no pueden desaparecer de la lista
slrp = (con_lista("DE03965-25") or [None])[0]
if slrp:
    dest = " | ".join(slrp["destinatarios"]).upper()
    for minera in ("CODELCO", "CENTINELA", "ANTUCOYA", "CERRO COLORADO", "CANDELARIA", "ANDACOLLO"):
        check(f"minera '{minera}' presente en DE03965-25", minera in dest)

# ── B. Lo que NO sirve (se reporta, no se esconde) ───────────────────────────
con = [c for c in cartas if c["destinatarios"]]
MAX_PLAUSIBLE = 150          # ninguna circular real nombra más de ~150 coordinados
infladas = [c for c in con if len(c["destinatarios"]) > MAX_PLAUSIBLE]
print(f"\nINFO  cartas con lista > {MAX_PLAUSIBLE} 'empresas': {len(infladas)} "
      f"(máx {max((len(c['destinatarios']) for c in con), default=0)})")

# La basura reconocible de una tabla: encabezados de columna y plantas SIN razón social.
# OJO: 'PFV El Cuervo SpA' o 'PMGD Calle Larga SpA' SÍ son empresas (sociedades dueñas de
# plantas, con razón social y RUT). Planta es solo la que no lleva razón social al final.
BASURA = re.compile(r"^(Control (Primario|Secundario|Terciario|de Tensión)|Partida Autónoma|"
                    r"Aislamiento Rápido|Combustible|Nombre (Coordinado|Unidad)|"
                    r"Descripción del)\b", re.I)
RS = re.compile(r"(?i)(S\.A\.?|SpA|LTDA|Limitada)\s*\.?\)?\s*$")
sucias = [(c["correlativo"], d) for c in con for d in c["destinatarios"]
          if BASURA.match(d) or (re.match(r"(?i)^(PMGD|PFV)\b", d) and not RS.search(d))]
print(f"INFO  filas basura de tabla / planta sin razón social: {len(sucias)}")
check("las listas NO traen encabezados de columna ni plantas sin razón social",
      not sucias, f"{len(sucias)} casos, ej: {sucias[:2]}")

# ── Circular con padrón en ANEXO (no en el PDF): no debe perderse ────────────
# DE01500-26 dice 'Solicita Informe según Lista de Distribución' y el padrón va en un Excel
# adjunto. Antes caía como DIRECTA con empresa 'Circular general' y se descartaba entera,
# perdiendo sus 42 respuestas citadas. Ahora: clase CIRCULAR y el requerimiento se registra
# (con destinatario vacío, sin inventarle dueño).
anejo = [c for c in cartas if c["correlativo"] == "DE01500-26"]
check("DE01500-26 se clasifica CIRCULAR (padrón en anexo)",
      bool(anejo) and anejo[0]["clase"] == "CIRCULAR",
      anejo[0]["clase"] if anejo else "ausente")
rj = os.path.join(BASE, "out", "radar.json")
if os.path.exists(rj):
    with open(rj, encoding="utf-8") as fh:
        _R = json.load(fh)
    en_radar = [r for r in _R["requerimientos"] if r["correlativo"] == "DE01500-26"]
    check("DE01500-26 llega al radar (no se descarta)", bool(en_radar), f"{len(en_radar)} fila(s)")
    # Las respuestas del tramo sin dueño no se pierden: el producto debe tener respondidos.
    sitr_resp = sum(r["n_respuestas"] for r in _R["requerimientos"] if r["producto"] == "SITR")
    check("SITR tiene respuestas atribuidas (>0)", sitr_resp > 0, f"{sitr_resp} en total")

# ── Ranking: sin filas anónimas arriba y un nombre por empresa ──────────────
# Hallazgos de la prueba 2 (no los vio el motor): una fila sin empresa con 362 reqs encabezaba
# el ranking, y Engie salía con dos tipografías distintas en productos distintos.
if os.path.exists(rj):
    with open(rj, encoding="utf-8") as fh:
        _R = json.load(fh)
    _O = _R["oportunidades"]
    _top = [o for o in _O[:10] if o["empresa"].strip()]
    check("el top 10 no tiene filas sin empresa", len(_top) == 10,
          f"{10 - len(_top)} anónimas en el top")
    nombres_engie = {o["empresa"] for o in _O if "ENGIE" in o["empresa"].upper()}
    check("una empresa = un nombre visible (Engie)", len(nombres_engie) == 1, str(sorted(nombres_engie)))
    grads = {o["gravedad"] for o in _O}
    check("la gravedad desempata (más de 70 valores distintos)", len(grads) > 70, f"{len(grads)} valores")

print()
print("OK" if not f else "FALLOS: " + " | ".join(f))
sys.exit(1 if f else 0)
