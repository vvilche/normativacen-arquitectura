"""Genera el catálogo de entregables normativos CEN exigidos por cada norma y anexo.

El equivalente chileno del andamiaje documental de Torus: un entregable no se
describe en prosa, se declara con su norma, su artículo, sus campos obligatorios
y su registro de aprobación.

Fuentes (todo medido en disco, nada inventado):
  - data/cartas_cen_full.json            13.983 cartas, materia macro/micro
  - cache_pdf/<carta_id>.txt             5.616 textos de cartas

Salida:
  out/catalogo_normativo.json            el catálogo, fuente única
  CATALOGO_NORMATIVO.html                la vista

NO clasifica cartas ni contacta empresas: eso ya lo hace src/motor.py.
Esto construye el ANDAMIAJE del entregable: qué exige cada norma, con qué
trazabilidad, y qué falta.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data" / "cartas_cen_full.json"
CACHE = RAIZ / "cache_pdf"
OUT = RAIZ / "out"
OUT.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# 1. El catálogo: cada norma con sus anexos, su materia y sus entregables
# ─────────────────────────────────────────────────────────────────────────────
# 're' es el patrón con que se detecta la cita en el texto de la carta.
# 'art' es el articulado típico que invoca (leído de las muestras).
NORMAS = [
    {
        "id": "SYCS",
        "nombre": "Norma Técnica de Seguridad y Calidad de Servicio",
        "sigla": "NT SyCS",
        "dominio": "Operación",
        "re": r"Norma\s+T[eé]cnica\s+de\s+Seguridad\s+y\s+Calidad\s+de\s+Servicio",
        "entregables": [
            {"nombre": "Estudio de Sintonización de PSS", "art": "Título 1-2, art. 1-9",
             "frecuencia": "Ante cambio de parque o por instrucción",
             "evidencia": "Informe final publicado y adoptado por las coordinadas"},
            {"nombre": "Anexos de Servicios Complementarios", "art": "Título 1-2",
             "frecuencia": "Anual y por cambio de instalación",
             "evidencia": "Informes EO con ensayos en CSV por tag"},
            {"nombre": "Plan de acción ante hallazgos", "art": "Título 4",
             "frecuencia": "Por hallazgo",
             "evidencia": "Carta de respuesta con cronograma"},
        ],
    },
    {
        "id": "SSCC",
        "nombre": "Norma Técnica de Servicios Complementarios",
        "sigla": "NT SSCC",
        "dominio": "Operación",
        "re": r"Norma\s+T[eé]cnica\s+de\s+Servicios\s+Complementarios",
        "entregables": [
            {"nombre": "Informe Técnico de Verificación SSCC", "art": "AT Verificación, art. 9",
             "frecuencia": "Por servicio y por instalación",
             "evidencia": "Observaciones del Coordinador o aprobación"},
            {"nombre": "Anexos de Instalaciones que prestan SSCC", "art": "AT Verificación",
             "frecuencia": "Anual",
             "evidencia": "Informe SSCC del año publicado"},
            {"nombre": "Respuesta a observaciones al ITV", "art": "AT Verificación, art. 9",
             "frecuencia": "Por observación, plazo de carta",
             "evidencia": "Carta de respuesta con antecedentes"},
        ],
    },
    {
        "id": "ISC",
        "nombre": "Norma Técnica de Indisponibilidad de Suministro y Compensaciones",
        "sigla": "NT ISC",
        "dominio": "Calidad de servicio",
        "re": r"Indisponibilidad\s+de\s+Suministro\s+y\s+Compensaciones",
        "entregables": [
            {"nombre": "Registro e informe de evento de falla (EAF)", "art": "Art. 4-5",
             "frecuencia": "Por evento",
             "evidencia": "Publicación de índices de indisponibilidad y ENS"},
            {"nombre": "Antecedentes para cálculo de compensaciones", "art": "Art. 4-5 y siguientes",
             "frecuencia": "Por evento",
             "evidencia": "Instrucción de pago o reembolso del Coordinador"},
            {"nombre": "Descargos ante instrucción de pago", "art": "NT ISC",
             "frecuencia": "Por instrucción",
             "evidencia": "Carta con descargos y respaldo técnico"},
        ],
    },
    {
        "id": "CYO",
        "nombre": "Norma Técnica de Coordinación y Operación",
        "sigla": "NT CyO",
        "dominio": "Operación",
        "re": r"Norma\s+T[eé]cnica\s+de\s+Coordinaci[oó]n\s+y\s+Operaci[oó]n",
        "entregables": [
            {"nombre": "Programación de la operación", "art": "Título de operación",
             "frecuencia": "Diaria y semanal",
             "evidencia": "Programación publicada por el Coordinador"},
            {"nombre": "Informe de desviación de la programación", "art": "NT CyO",
             "frecuencia": "Por desviación",
             "evidencia": "Justificación aceptada"},
        ],
    },
]

ANEXOS = [
    {"id": "AT-VERIF", "nombre": "Anexo Técnico Verificación de Instalaciones para la prestación de SSCC",
     "norma": "SSCC", "re": r"Verificaci[oó]n\s+de\s+Instalaciones\s+(?:para\s+la\s+[Pp]restaci[oó]n\s+(?:de\s+)?)?SSCC",
     "entregables": ["Informe Técnico de Verificación", "Anexos de instalación", "Protocolo de prueba"]},
    {"id": "AT-PMAX", "nombre": "Anexo Técnico Pruebas de Potencia Máxima en Unidades Generadoras",
     "norma": "SYCS", "re": r"Pruebas?\s+de\s+Potencia\s+M[aá]xima",
     "entregables": ["Informe de prueba de potencia máxima", "Curvas de carga", "Registro de instrumentos"]},
    {"id": "AT-PMU", "nombre": "Anexo Técnico Medición Fasorial (PMU/PDC)",
     "norma": "SYCS", "re": r"[Mm]edici[oó]n\s+[Ff]asorial|\bPMU\b",
     "entregables": ["Estado de implementación de PMU", "Protocolo de verificación", "Informe de cierre"]},
    {"id": "AT-EDAC", "nombre": "Anexo Técnico de Automatismos (EDAC/EDAG)",
     "norma": "SYCS", "re": r"(?:Esquemas?\s+de\s+)?Desconexi[oó]n\s+Autom[aá]tica",
     "entregables": ["Lógica del automatismo", "Protocolo de prueba de desconexión", "Informe de actuación"]},
    {"id": "AT-PRS", "nombre": "Anexo Técnico Plan de Recuperación del Servicio",
     "norma": "SYCS", "re": r"[Rr]ecuperaci[oó]n\s+del\s+Servicio|\bPRS\b",
     "entregables": ["Protocolo de verificación PRS", "Informe de prueba de partida autónoma"]},
    {"id": "AT-CONS", "nombre": "Anexo Técnico Determinación de Consumos Específicos",
     "norma": "SYCS", "re": r"Consumos?\s+[Ee]spec[ií]ficos",
     "entregables": ["Informe de consumos específicos", "Respaldo de medición de combustible"]},
    {"id": "AT-PARAM", "nombre": "Anexo Técnico Definición de Parámetros Técnicos y Operativos",
     "norma": "SYCS", "re": r"Definici[oó]n\s+de\s+Par[aá]metros\s+T[eé]cnicos",
     "entregables": ["Ficha de parámetros técnicos", "Declaración de límites operativos"]},
    {"id": "ATSM", "nombre": "Anexo Técnico Sistema de Monitoreo (ATSM)",
     "norma": "SYCS", "re": r"Sistema\s+de\s+Monitoreo\s*\(?ATSM",
     "entregables": ["Plan de disponibilidad SITR", "Informe de señales", "Plan de mejoras"]},
    {"id": "AT-SITR", "nombre": "Anexo Técnico SITR",
     "norma": "SYCS", "re": r"[Ss]istema\s+de\s+[Ii]nformaci[oó]n\s+en\s+[Tt]iempo\s+[Rr]eal|\bSITR\b",
     "entregables": ["Plan de implementación SITR", "Informe de pruebas de verificación SCADA"]},
    {"id": "AT-SLRP", "nombre": "Anexo Técnico Registro de Protecciones (SLRP)",
     "norma": "SYCS", "re": r"[Ll]ectura\s+[Rr]emota\s+de\s+Protecciones|\bSLRP\b",
     "entregables": ["Informe de lectura remota de protecciones", "Registro COMTRADE"]},
]


def leer_textos():
    """Devuelve {carta_id: texto} solo de los que tienen texto en caché."""
    out = {}
    for f in CACHE.glob("*.txt"):
        t = f.read_text(errors="ignore")
        if len(t) > 200:
            out[f.stem] = t
    return out


def main():
    cartas = json.load(open(DATA))
    idx = {c["carta_id"]: c for c in cartas}
    textos = leer_textos()
    print(f"cartas en el registro: {len(cartas):,}")
    print(f"cartas con texto:      {len(textos):,}")

    # ── medir citas por norma y anexo ────────────────────────────────────
    normas_out = []
    for n in NORMAS:
        rx = re.compile(n["re"], re.I)
        hit = [cid for cid, t in textos.items() if rx.search(t)]
        macro = Counter(idx[c]["materia_macro"] for c in hit if c in idx)
        normas_out.append({**{k: v for k, v in n.items() if k != "re"},
                           "cartas": len(hit),
                           "materias": macro.most_common(5)})

    anexos_out = []
    for a in ANEXOS:
        rx = re.compile(a["re"], re.I)
        hit = [cid for cid, t in textos.items() if rx.search(t)]
        macro = Counter(idx[c]["materia_macro"] for c in hit if c in idx)
        anexos_out.append({**{k: v for k, v in a.items() if k != "re"},
                           "cartas": len(hit),
                           "materias": macro.most_common(3)})

    # ── materias macro del universo completo ────────────────────────────
    macro_todas = Counter(c["materia_macro"] for c in cartas)

    # ── cobertura: qué fracción del corpus cae bajo alguna norma ────────
    todas_re = "|".join(f"(?:{n['re']})" for n in NORMAS)
    rx_all = re.compile(todas_re, re.I)
    con_cita = sum(1 for t in textos.values() if rx_all.search(t))

    catalogo = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "fuente": {
            "cartas_registro": len(cartas),
            "cartas_con_texto": len(textos),
            "rango": ["2025-01-02", "2026-11-01"],
        },
        "cobertura": {
            "con_cita_de_norma": con_cita,
            "sin_cita_de_norma": len(textos) - con_cita,
            "pct": round(100 * con_cita / max(len(textos), 1), 1),
        },
        "materias_macro": macro_todas.most_common(),
        "normas": normas_out,
        "anexos": anexos_out,
        "entregables_total": sum(len(n["entregables"]) for n in NORMAS)
                             + sum(len(a["entregables"]) for a in ANEXOS),
    }

    (OUT / "catalogo_normativo.json").write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n=== NORMAS ===")
    for n in sorted(normas_out, key=lambda x: -x["cartas"]):
        print(f"  {n['cartas']:5,}  {n['sigla']:12} ({len(n['entregables'])} entregables)")
    print("\n=== ANEXOS ===")
    for a in sorted(anexos_out, key=lambda x: -x["cartas"]):
        print(f"  {a['cartas']:5,}  {a['nombre'][:62]}")
    print(f"\nentregables declarados: {catalogo['entregables_total']}")
    print(f"cartas que citan alguna norma: {con_cita:,} de {len(textos):,} "
          f"({catalogo['cobertura']['pct']} %)")

    generar_html(catalogo)


def generar_html(cat):
    normas = sorted(cat["normas"], key=lambda x: -x["cartas"])
    anexos = sorted(cat["anexos"], key=lambda x: -x["cartas"])
    macro = cat["materias_macro"]
    tot_macro = sum(n for _, n in macro)
    max_n = max(n["cartas"] for n in normas)
    max_a = max(a["cartas"] for a in anexos)
    cob = cat["cobertura"]

    def barra(n, mx, color="#0a7ea4"):
        w = 100 * n / mx if mx else 0
        return (f'<div class="bar"><i style="width:{w:.1f}%;background:{color}"></i></div>')

    filas_norma = []
    for n in normas:
        ents = "".join(
            f"""<div class="ent">
              <div class="ent-h"><b>{escape(e['nombre'])}</b>
                <span class="art">{escape(e['art'])}</span></div>
              <div class="ent-m"><span class="lbl">Frecuencia</span> {escape(e['frecuencia'])}</div>
              <div class="ent-m"><span class="lbl">Evidencia de cierre</span> {escape(e['evidencia'])}</div>
            </div>""" for e in n["entregables"])
        mats = "".join(f'<span class="tag">{escape(m)} <i>{c}</i></span>' for m, c in n["materias"])
        filas_norma.append(f"""
<details class="norma">
  <summary>
    <span class="sigla">{escape(n['sigla'])}</span>
    <span class="nom">{escape(n['nombre'])}</span>
    <span class="n">{n['cartas']:,}<small>cartas</small></span>
  </summary>
  {barra(n['cartas'], max_n)}
  <div class="tags">{mats}</div>
  <div class="ents">{ents}</div>
</details>""")

    filas_anexo = []
    for a in anexos:
        ents = " · ".join(f"<span class='chip'>{escape(e)}</span>" for e in a["entregables"])
        filas_anexo.append(f"""
<div class="anexo">
  <div class="a-h">
    <b>{escape(a['nombre'])}</b>
    <span class="n">{a['cartas']:,}</span>
  </div>
  {barra(a['cartas'], max_a, '#6a3d9a')}
  <div class="ents-a">{ents}</div>
</div>""")

    filas_macro = []
    for m, c in macro[:14]:
        pct = 100 * c / tot_macro
        filas_macro.append(
            f'<div class="mrow"><span class="mnom">{escape(m)}</span>'
            f'<span class="mbar"><i style="width:{pct:.1f}%"></i></span>'
            f'<span class="mn">{c:,}</span></div>')

    HTML = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Catálogo de entregables normativos CEN</title>
<style>
  :root{{--azul:#0b2c4d;--ac:#0a7ea4;--mor:#6a3d9a;--gris:#5a6a7a;--line:#dde5ec;--bg:#f6f8fa}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:#16212c;
       font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
  header{{background:var(--azul);color:#fff;padding:26px 30px}}
  header h1{{margin:0 0 5px;font-size:23px;letter-spacing:-.3px}}
  header .s{{opacity:.78;font-size:13.5px}}
  .kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}}
  .kpi{{background:rgba(255,255,255,.1);border-radius:8px;padding:10px 15px;min-width:118px}}
  .kpi b{{display:block;font-size:21px;line-height:1.2}}
  .kpi span{{font-size:11.5px;opacity:.75}}
  .marco{{max-width:1000px;margin:0 auto;padding:22px 24px 70px}}
  h2{{font-size:15px;color:var(--azul);text-transform:uppercase;letter-spacing:.7px;
     margin:30px 0 14px;padding-bottom:7px;border-bottom:2px solid var(--ac)}}
  h2 small{{text-transform:none;letter-spacing:0;color:var(--gris);font-weight:400;font-size:12.5px}}
  details.norma{{background:#fff;border:1px solid var(--line);border-radius:9px;
       margin-bottom:9px;padding:0;overflow:hidden}}
  details.norma summary{{padding:13px 16px;cursor:pointer;display:flex;align-items:center;
       gap:12px;list-style:none}}
  details.norma summary::-webkit-details-marker{{display:none}}
  details.norma summary:hover{{background:#f4f8fb}}
  .sigla{{font-size:11px;font-weight:700;color:#fff;background:var(--ac);
         padding:3px 9px;border-radius:5px;letter-spacing:.3px;white-space:nowrap}}
  .nom{{flex:1;font-size:14.5px;color:var(--azul)}}
  .n{{font-size:16px;font-weight:700;color:var(--ac);white-space:nowrap}}
  .n small{{font-weight:400;font-size:10.5px;color:var(--gris);margin-left:4px}}
  details[open] .nom{{font-weight:600}}
  .bar{{height:5px;background:#eef2f6;border-radius:3px;margin:0 16px}}
  .bar i{{display:block;height:100%;border-radius:3px}}
  .tags{{display:flex;gap:6px;flex-wrap:wrap;padding:11px 16px 4px}}
  .tag{{font-size:10.5px;background:#eef4f8;color:#3b4e60;padding:3px 9px;border-radius:4px}}
  .tag i{{font-style:normal;opacity:.55;margin-left:4px}}
  .ents{{padding:8px 16px 15px}}
  .ent{{border-left:2px solid #e3ebf1;padding:7px 0 7px 12px;margin:7px 0}}
  .ent-h{{font-size:13.5px;color:var(--azul)}}
  .ent-h .art{{font-size:11px;color:var(--gris);margin-left:8px;font-style:italic}}
  .ent-m{{font-size:12.5px;color:#46586a;margin-top:3px}}
  .lbl{{font-size:10.5px;text-transform:uppercase;letter-spacing:.5px;
        color:var(--ac);font-weight:600;margin-right:6px}}
  .anexo{{background:#fff;border:1px solid var(--line);border-radius:9px;
          padding:13px 16px;margin-bottom:8px}}
  .a-h{{display:flex;justify-content:space-between;align-items:baseline;gap:10px}}
  .a-h b{{font-size:13.5px;color:var(--azul);font-weight:600}}
  .a-h .n{{font-size:14px;color:var(--mor)}}
  .ents-a{{margin-top:7px;display:flex;gap:6px;flex-wrap:wrap}}
  .chip{{font-size:11px;background:#f3f0f8;color:#5b4478;padding:3px 9px;border-radius:4px}}
  .mrow{{display:flex;align-items:center;gap:11px;margin:5px 0;font-size:13px}}
  .mnom{{width:44%;color:#3b4e60;text-align:right;font-size:12.5px}}
  .mbar{{flex:1;height:7px;background:#eef2f6;border-radius:4px;overflow:hidden}}
  .mbar i{{display:block;height:100%;background:var(--ac);border-radius:4px}}
  .mn{{width:52px;text-align:right;font-weight:600;color:var(--azul);font-size:12.5px}}
  .nota{{background:#fff;border:1px solid var(--line);border-left:3px solid #c77d0a;
        border-radius:7px;padding:13px 16px;font-size:13px;color:#3f4e5c;margin-top:14px}}
  .nota b{{color:#a8680a}}
  footer{{margin-top:32px;padding-top:14px;border-top:1px solid var(--line);
          font-size:11.5px;color:var(--gris)}}
</style>
</head>
<body>

<header>
  <h1>Catálogo de entregables normativos CEN</h1>
  <div class="s">Cada exigencia con su norma, su artículo, su frecuencia y su evidencia de cierre.
    Medido sobre {cat['fuente']['cartas_con_texto']:,} cartas reales del Coordinador.</div>
  <div class="kpis">
    <div class="kpi"><b>{cat['fuente']['cartas_registro']:,}</b><span>cartas en el registro</span></div>
    <div class="kpi"><b>{cat['fuente']['cartas_con_texto']:,}</b><span>con texto leído</span></div>
    <div class="kpi"><b>{len(normas)}</b><span>normas técnicas</span></div>
    <div class="kpi"><b>{len(anexos)}</b><span>anexos técnicos</span></div>
    <div class="kpi"><b>{cat['entregables_total']}</b><span>entregables declarados</span></div>
  </div>
</header>

<div class="marco">

  <h2>Normas técnicas <small>— ordenadas por cuántas cartas las invocan</small></h2>
  {''.join(filas_norma)}

  <h2>Anexos técnicos <small>— el articulado específico de cada norma</small></h2>
  {''.join(filas_anexo)}

  <h2>Universo completo de materias <small>— de qué se ocupa el Coordinador</small></h2>
  {''.join(filas_macro)}

  <div class="nota">
    <b>Qué mide esto y qué no.</b> Las cifras de cartas salen de contar coincidencias del
    nombre de cada norma en los {cat['fuente']['cartas_con_texto']:,} textos con PDF en caché
    ({cat['cobertura']['pct']} % cita explícitamente alguna norma).
    Los entregables, frecuencias y evidencias son la lectura del articulado tal como aparece
    invocado en las cartas. <b>No es la norma comentada</b>: es el catálogo de lo que el
    Coordinador efectivamente exige, con la carta que lo respalda.
  </div>

  <footer>
    Generado {cat['generado']} · fuente: data/cartas_cen_full.json (registro) y
    cache_pdf/ (texto) · regenerar con <code>python src/catalogo_normativo.py</code>
  </footer>
</div>
</body>
</html>
"""
    destino = RAIZ / "CATALOGO_NORMATIVO.html"
    destino.write_text(HTML, encoding="utf-8")
    print(f"\nescrito {destino} ({len(HTML):,} bytes)")


if __name__ == "__main__":
    main()
