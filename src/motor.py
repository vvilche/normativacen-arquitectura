#!/usr/bin/env python3
"""
Radar Normativo CEN — motor determinístico (v2).

Qué hace, en una frase: lee el corpus de documentos del CEN, identifica QUÉ le pidieron a QUÉ empresa
sobre QUÉ producto normativo, mide el estado de la mora y valoriza la oportunidad.

MODELO DEL DATO (esto gobierna todo; si se cambia, cambia el reporte)
────────────────────────────────────────────────────────────────────
El CEN publica tres clases de documento por el mismo canal, y solo mirar `empresa` las confunde:

  1. DE directa        → carta a UNA empresa. El campo `empresa` trae el nombre. (12.016 docs)
  2. Circular a lista  → carta con "Lista de Distribución" en el PDF; el campo `empresa` dice
                         "Circular general". Afecta a N empresas que solo están en el PDF. (series
                         masivas de SLRP, EDAG, SITR, EDAC)
  3. OP / CD           → ingresos de coordinados y documentos varios del CEN. (937 + 15)

Regla de oro: el campo `materia_micro` viene TRUNCADO en ~72% del corpus ("Solicita cumplir con la
implementación del Si..."). Por eso el texto se toma del PDF, no del listado. Sin PDF, un
requerimiento circular queda sin producto y sin destinatarios → se reporta como tal, no se inventa.

Estado de mora (los tres, siempre por separado — criterio de Victor, 23-oct-2026):
  SIN_RESPUESTA : el destinatario no ha respondido todavía.
  REITERADO     : el CEN tiene 2+ requerimientos sobre el mismo producto y la misma empresa.
  REABIERTO     : respondió y el CEN volvió a escribirle del mismo producto después.

Uso:
  python3 src/motor.py                # sin PDFs (rápido): sirve para ver la estructura
  python3 src/motor.py --pdfs         # con texto de PDFs (lento la primera vez, cachea)
  python3 src/motor.py --pdfs --odoo  # + cruce con Odoo producción (si hay credenciales)
"""
import json
import re
import unicodedata
import datetime
import collections
import hashlib
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
CACHE = os.path.join(BASE, "cache_pdf")
OUT = os.path.join(BASE, "out")
HOY = datetime.date.today()
UF_USD = 40          # de conecta-valorizacion (misma fuente que los BOMs)

# ─────────────────────────────────────────────────────────────────────────────
# Productos normativos: regex + solución CONECTA + línea de BOM para el potencial
# ─────────────────────────────────────────────────────────────────────────────
PRODUCTOS = {
    "SLRP": {
        "nombre": "SLRP — Sistema de Lectura Remota de Protecciones",
        "regex": r"\bSLRP\b|lectura remota de protecciones",
        "solucion": "Gateway serial→IP (Moxa/SEL-3620), IEC 61850 MMS, COMTRADE. NO es SITR.",
        "linea_bom": "Repro",
        "norma": "ATSM / NTSyCS — Módulo de Registro de Protecciones",
    },
    "SITR": {
        "nombre": "SITR — Sistema de Información en Tiempo Real",
        "regex": r"\bSITR\b|sistema de informaci[oó]n en tiempo real",
        "solucion": "Gateway SCADA→CEN (Orion RTU / SOLISCADA), señales SSCC, plan de disponibilidad",
        "linea_bom": "RTU",
        "norma": "ATSM / NTSyCS",
    },
    "EDAC": {
        "nombre": "EDAC — Desconexión Automática de Carga",
        "regex": r"\bEDAC\b|desconexi[oó]n autom[aá]tica de carga",
        "solucion": "Automatismo EDAC: lógica, pruebas de desconexión, integración SCADA",
        "linea_bom": "EDAC",
        "norma": "AT de Automatismos / PDCE",
    },
    "EDAG": {
        "nombre": "EDAG — Desconexión Automática de Generación",
        "regex": r"\bEDAG\b|desconexi[oó]n autom[aá]tica de generaci[oó]n",
        "solucion": "Automatismo EDAG: lógica, pruebas, integración con unidades generadoras",
        "linea_bom": "EDAC",
        "norma": "AT de Automatismos / PDCE",
    },
    "PMU": {
        "nombre": "PMU — Medición Fasorial",
        "regex": r"\bPMU\b|\bPDC\b|medici[oó]n fasorial|fasorial",
        "solucion": "PMU Vizimax + PDC, protocolo de verificación, cierre de implementación",
        "linea_bom": "PMU",
        "norma": "AT de Monitoreo / Módulo Medición Fasorial",
    },
    "PRS": {
        "nombre": "PRS — Plan de Recuperación del Servicio",
        "regex": r"\bPRS\b|recuperaci[oó]n del servicio",
        "solucion": "Protocolo de verificación PRS, pruebas de partida autónoma, expediente",
        "linea_bom": "SCADA",
        "norma": "AT de SSCC",
    },
    "SSCC": {
        "nombre": "SSCC — Servicios Complementarios",
        "regex": r"\bSSCC\b|servicios? complementarios?",
        "solucion": "Medición clase 0,2, protocolo de verificación, CDT/CSF",
        "linea_bom": "Medición",
        "norma": "AT de SSCC",
    },
    "SCADA": {
        "nombre": "SCADA — Plataforma de operación",
        "regex": r"\bSCADA\b",
        "solucion": "Gateway SCADA→CEN, Tier0 UNS, arquitectura de comunicaciones",
        "linea_bom": "SCADA",
        "norma": "ATSM",
    },
    "PROTECCIONES": {
        "nombre": "Protecciones / teleprotección",
        "regex": r"protecci[oó]n(es)?\b|teleprotecci[oó]n|\bIED\b",
        "solucion": "Retrofit de relés, backup, análisis de eventos, coordinación",
        "linea_bom": "Repro",
        "norma": "AT de Protecciones",
    },
}

# Precedencia cuando una carta nombra varios productos: el más específico gana.
PRECEDENCIA = ["SLRP", "SITR", "EDAG", "EDAC", "PMU", "PRS", "SSCC", "SCADA", "PROTECCIONES"]

NO_CUENTA = re.compile(
    r"circular general|m[uú]ltiples empresas|superintendencia de electricidad|"
    r"ministerio de energ[ií]a|comisi[oó]n nacional de energ[ií]a|senado|"
    r"c[aá]mara de diputados|^direcci[oó]n ejecutiva", re.I)

# El CEN "pide algo": verbos de exigencia. Sin esto, los informes y las respuestas entran como requerimientos.
REGEX_PIDE = re.compile(
    r"solicita|requiere|requerimiento|instruye|ordena|exige|"
    r"cumplimiento|incumplimiento|reitera|plazo|plan de (trabajo|acci[oó]n|mejora)|"
    r"implementaci[oó]n|brecha|subsan|correcci[oó]n|disponibilidad|"
    r"precisa|observaciones|rechaz|atraso|regulariz", re.I)

# El CEN "solo acusa/cierra": si empieza así, no es un requerimiento nuevo aunque mencione 'cumplimiento'
REGEX_MERA_RESPUESTA = re.compile(r"^\s*(responde|respuesta|acusa recibo|toma conocimiento|aprueba|informa)\b", re.I)


# ─────────────────────────────────────────────────────────────────────────────
# Normalización
# ─────────────────────────────────────────────────────────────────────────────
def norm_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def limpiar_materia(s):
    s = norm_ws(s)
    s = re.split(r"Ver m[aá]s\s*.{0,3}\s*Referencias", s)[0]
    s = s.replace("&times;", "×")
    s = re.sub(r"Cerrado\s*\d{0,2}", "", s, flags=re.I)
    return norm_ws(s)


def norm_empresa(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").upper()
    s = s.replace("&TIMES;", " ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    # El sufijo societario se normaliza ANTES de colapsar espacios: "S.A." ya es "S A" aquí.
    s = re.sub(r"\bS\s*A\b|\bSPA\b|\bSOCIEDAD\s+ANONIMA\b", " ", s)
    s = re.sub(r"\bLTDA\b|\bLIMITADA\b|\bCHILE\b", " ", s)
    return norm_ws(s)


PLACEHOLDER = re.compile(r"ver\s*(&times;|×|x)\s*empresas\s*cerrar|^ver\s*empresas", re.I)


def es_placeholder(s):
    """El sitio devuelve 'Ver × Empresas Cerrar' cuando el modal no cargó. No es una cuenta."""
    return bool(PLACEHOLDER.search(unicodedata.normalize("NFD", s or "").upper()))


def fecha(s):
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", (s or "").strip())
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    try:
        return datetime.date(y, mo, d)
    except ValueError:
        return None


REF = re.compile(r"\b(DE|OP)\s?0?(\d{3,5})\s?-\s?(\d{2})\b", re.I)

# El campo 'correlativo' del corpus NO siempre trae el correlativo del CEN: en 946 recibidas
# viene el número de documento de la propia empresa ('CGET00527-2026' matchea como DE05627-26).
# Eso contamina el cruce respuesta→requerimiento. Solo el formato del CEN es correlativo.
CORRELATIVO_CEN = re.compile(r"^(DE|OP)\d{5}-\d{2}$")


def correlativo_cen(s):
    """Normaliza el correlativo y devuelve '' si no es del CEN (no se inventa uno)."""
    c = norm_ws(s).upper().replace(" ", "")
    return c if CORRELATIVO_CEN.match(c) else ""


def extraer_refs(texto):
    return {f"{p.upper()}{n.zfill(5)}-{yy}" for p, n, yy in REF.findall(texto or "")}


# ─────────────────────────────────────────────────────────────────────────────
# Extracción de texto del PDF (cacheada por carta_id)
# ─────────────────────────────────────────────────────────────────────────────
def texto_pdf(carta_id, bajar=False):
    """
    Texto del PDF. Los PDFs del CEN son texto nativo (verificado): no hace falta OCR.
    Con bajar=False devuelve lo que haya en caché (o None).
    """
    ruta = os.path.join(CACHE, f"{carta_id}.txt")
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            return f.read()
    if not bajar:
        return None
    try:
        import requests
        import pymupdf
        r = requests.get(f"https://cartas.coordinador.cl/download_saved_file/{carta_id}",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        if r.status_code != 200 or len(r.content) < 1000:
            return None
        doc = pymupdf.open(stream=r.content, filetype="pdf")
        txt = "\n".join(p.get_text() for p in doc)
        if len(txt.strip()) < 120:      # PDF escaneado: no hay capa de texto útil
            return None
        os.makedirs(CACHE, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(txt)
        return txt
    except Exception:
        return None


# Frases que NO son nombres de empresa (pies de página, titulares de tabla, notas al pie).
# OJO con las palabras que también son parte de una razón social: 'Distribución' está en
# Chilquinta Distribución S.A. y Enel Distribución Chile S.A. — filtrarla borraba esas cuentas.
FRASE_NO_EMPRESA = re.compile(
    r"^\s*av\.|www\.|tel[eé]fono|coordinador el[eé]ctrico nacional|pudahuel|"
    r"lista de distribuci[oó]n|seg[uú]n lista de|"
    r"^(señor|señora|listado|anexo|p[aá]gina|grupo correspondencia|referencias?)\b|"
    r"saluda atentamente|sin otro particular|adjunto|incluye|"
    r"\bgerente general|\bsubgerente|\bjefe de|encargado titular|encargado suplente", re.I)


def lista_distribucion(txt):
    """
    Empresas afectadas por una circular del CEN. Hay DOS formatos y hay que respetar los dos:

      A) 'Lista de Distribución:' y debajo la lista de razones sociales, a veces numerada.
      B) 'Anexo: Coordinados que...' seguido de una TABLA (columnas Coordinado / Central / Año…).
         Ahí las empresas están dentro de la tabla, no en una lista.

    Dos trampas medidas:
      - La primera mención de "Lista de Distribución" está en el cuerpo ("según lista de
        distribución") y tomar esa arrastra toda la carta.
      - El bloque es FINITO: termina en el pie de página, en el Anexo, en 'c.c.:' o en un titular
        de tabla. Sin acotarlo, se meten pies de página, RUT, notas al pie y hasta el texto
        de la carta como si fueran empresas.
    """
    if not txt:
        return []
    # Se toma la ÚLTIMA aparición del encabezado, sobre su PROPIA LÍNEA o al final de una línea.
    # Ojo con el cuerpo de la carta: 'Lista de Distribución) Presente' aparece a mitad de texto y
    # tomar eso metía 565 líneas de prosa como si fueran empresas. Por eso el encabezado tiene que
    # estar solo (admitiendo un paréntesis de cierre), sin más palabras en la línea.
    m = None
    for mm in re.finditer(r"(?i)^[ \t]*Lista de Distribuci[oó]n[ \t]*[:)]?[ \t]*$", txt,
                          re.MULTILINE):
        m = mm
    if m is not None:
        resto = txt[m.end():]
        corte = re.search(
            r"(?im)^\s*(?:Anexo\b|ANEXO\b|c\.c\.\s*:|Sin otro particular|Saluda)", resto)
        if corte:
            resto = resto[:corte.start()]
        # El pie de página se repite en medio de la lista al cambiar de página: se quita la LÍNEA
        # del pie, no se corta el bloque ahí (cortar botaba media lista: 83 → 52 empresas).
        lineas = [l.strip() for l in resto.split("\n")
                  if not re.match(r"(?i)^\s*(av\.\s*parque|www\.coordinador)", l.strip())]
    else:
        # Formato TABLA sin "Lista de Distribución": 'NOMBRE COORDINADO / RUT COORDINADO' y luego
        # pares nombre–RUT alternados. Ahí la empresa es la línea que NO es un RUT.
        mi = re.search(r"(?im)^\s*(?:NOMBRE\s+(?:DE\s+)?COORDINADO|RUT\s+(?:GRUPO|COORDINADO))\s*$",
                       txt)
        if mi:
            resto = txt[mi.end():]
            corte = re.search(r"(?im)^\s*(?:Anexo\b|ANEXO\b|Nota|\(\*\)|Av\.\s*Parque)", resto)
            if corte:
                resto = resto[:corte.start()]
            lineas = [l.strip() for l in resto.split("\n")]
        else:
            # Sin lista ni tabla reconocible: NO se inventa un padrón a partir del texto corrido.
            # (DE05310-25 y DE05203-25 aterrizan acá: su 'lista' es la tabla de plantas PMGD.)
            return []

    empresas = []
    for ln in lineas:
        ln = norm_ws(ln)
        if not ln or len(ln) > 90:
            continue
        if FRASE_NO_EMPRESA.search(ln):
            continue
        # número de lista ('1.' / '27' / '1)') al inicio
        ln = re.sub(r"^\d{1,3}\s*[.)\-]?\s*", "", ln)
        # RUT y números de cliente no son empresas
        if re.match(r"^[\d.\-]+$", ln) or re.fullmatch(r"[\d.\-]{6,}", ln):
            continue
        # tiene que parecer una razón social: al menos 2 palabras, sin terminar en dos puntos
        # (los titulares de tabla terminan así), sin paréntesis de nota al pie
        if ln.endswith(":") or re.match(r"^\(", ln):
            continue
        # encabezados de columna: 'NOMBRE DE COORDINADO', 'RUT GRUPO', 'CENTRAL' a secas.
        # Pero 'CENTRAL COLMITO S.A.' es una empresa: solo se descarta si NO tiene razón social
        # ni numeral (los nombres de columna nunca la llevan).
        if re.match(r"(?i)^\s*(NOMBRE|RUT|COORDINADO|CENTRAL|UNIDAD|GRUPO)\b", ln) and not re.search(
                r"(?i)(S\.A\.?|SpA|LTDA|Limitada)\s*\.?$|\d", ln):
            continue
        # En las cartas PMGD la "lista" mezcla PLANTAS ('PMGD TER YUMBEL') con EMPRESAS cuyo nombre
        # legal empieza con PMGD ('PMGD Calle Larga SpA', 'PMGD HOLDCO SpA'). La regla que los
        # separa sin ambigüedad: la razón social al final. Planta = no la lleva.
        if re.match(r"(?i)^\s*(PMGD|PFV)\b", ln) and not re.search(
                r"(?i)(S\.A\.?|SpA|LTDA|Limitada)\s*\.?\)?\s*$", ln):
            continue
        # prosa con comillas o de largo de frase: es el cuerpo de una carta citada, no una empresa
        if re.search(r"[\"“”]", ln) or len(ln.split()) > 9:
            continue
        palabras = ln.split()
        if len(palabras) < 2:
            continue
        if not re.match(r"^[A-ZÁÉÍÓÚÑÜ]", ln):
            continue
        if not any(re.match(r"^[A-ZÁÉÍÓÚÑÜ]", p) for p in palabras[1:]):
            continue
        empresas.append(ln.rstrip(".,;"))
    # Si la lista encabeza con CATEGORÍAS ('Empresa Generadora propietaria u operadora de parques
    # ERV'), se quitan esas líneas y se conservan las razones sociales que vienen debajo: en
    # DE02631-25 conviven 4 categorías con ~400 empresas reales.
    # CUIDADO: 'Empresa Eléctrica Pehuenche S.A.' también empieza con 'Empresa'. Solo es categoría
    # si NO tiene razón social y describe un rubro ('propietaria u operadora de ...').
    genericas = re.compile(
        r"(?i)^(empresas?\s+(generadoras?|transmisoras?|propietarias?|coordinadas?)\b(?!.*\b"
        r"(S\.A|SpA|LTDA|Limitada))|propietaria u operadora|operadora de|coordinados?$|encargados?)")
    filtradas = [e for e in empresas if not genericas.match(e)]
    # Si al quitar las categorías no queda nada, no había padrón.
    return list(dict.fromkeys(filtradas))


def producto_de(txt):
    """Producto dominante del texto completo (por precedencia, no por orden de aparición)."""
    hits = [k for k in PRECEDENCIA if re.search(PRODUCTOS[k]["regex"], txt or "", re.I)]
    return hits


# ─────────────────────────────────────────────────────────────────────────────
# Carga del corpus
# ─────────────────────────────────────────────────────────────────────────────
def cargar(usar_pdf=False):
    """
    usar_pdf=True  → lee el texto de la caché (cache_pdf/). NO baja nada: la descarga la hace
                     src/bajar_pdfs.py, que sabe qué PDFs importan y reintenta.
    Bajarlos acá era un bug medido: el motor intentaba 2.443 cartas que no son candidatas,
    60 s de timeout cada una, y la corrida nunca terminaba.
    """
    ruta = os.path.join(DATA, "cartas_cen_full.json")
    if not os.path.exists(ruta):
        sys.exit(f"FALTA el corpus: {ruta}\nCorrer: bash src/bajar_corpus.sh")
    with open(ruta, encoding="utf-8") as f:
        crudo = json.load(f)

    cartas, desc = [], collections.Counter()
    visto = set()
    for c in crudo:
        f = fecha(c.get("fecha"))
        if not f:
            desc["fecha_invalida"] += 1
            continue
        cid = c.get("carta_id") or c.get("correlativo")
        if not cid or cid in visto:
            desc["duplicada"] += 1
            continue
        visto.add(cid)
        emp = norm_ws(c.get("empresa"))
        if es_placeholder(emp):
            emp = ""                     # no es cuenta; se recupera del PDF si es circular
        materia = limpiar_materia(c.get("materia_micro"))
        cartas.append({
            "correlativo": correlativo_cen(c.get("correlativo")),
            "carta_id": cid,
            "tipo": c.get("tipo") or "",
            "fecha": f,
            "empresa": emp,
            "remitente": norm_ws(c.get("remitente")),
            "materia_macro": norm_ws(c.get("materia_macro")),
            "materia_micro": materia,
            "truncada": materia.endswith("..."),
        })

    # Texto de PDF desde la caché: la materia del listado viene truncada (72%), el PDF trae
    # el texto completo y la Lista de Distribución. Bajar = tarea de src/bajar_pdfs.py
    con_pdf = 0
    for c in cartas:
        txt = texto_pdf(c["carta_id"], bajar=False)
        if txt:
            con_pdf += 1
        c["texto"] = txt
        c["destinatarios"] = lista_distribucion(txt) if txt else []

    for c in cartas:
        # El texto de trabajo: el PDF si existe; si no, el listado (truncado pero útil)
        t = c["texto"] or " ".join([c["materia_micro"], c["materia_macro"], c["correlativo"]])
        c["productos"] = producto_de(t)
        c["refs"] = extraer_refs(t)
        # Empresa faltante: el listado la trae vacía en las respuestas a circulares. Se recupera
        # del PDF (encabezado), no se deja vacía ni se inventa.
        if not c["empresa"] and c["texto"]:
            emp_pdf = empresa_desde_pdf(c["texto"])
            if emp_pdf:
                c["empresa"] = emp_pdf
                c["empresa_key"] = norm_empresa(emp_pdf)
                c["empresa_de_pdf"] = True
        c["es_cuenta"] = bool(c["empresa"]) and not NO_CUENTA.search(c["empresa"])
        pide = bool(REGEX_PIDE.search(t)) and not REGEX_MERA_RESPUESTA.search(c["materia_micro"])
        c["pide"] = pide
        # clase de documento
        if c["correlativo"].startswith("OP"):
            c["clase"] = "INGRESO"
        elif c["destinatarios"] or (not c["empresa"] and c["tipo"] == "Enviado"):
            c["clase"] = "CIRCULAR"
        elif c["tipo"] == "Enviado" and (
                NO_CUENTA.search(c["empresa"])
                or re.search(r"(?i)lista de distribuci[oó]n", c["texto"] or c["materia_micro"])):
            # Circular con el padrón en un anexo ('Lista de Distribución Adjunta (planilla Excel)'):
            # NO es directa. Antes caía como DIRECTA y se perdían todas sus respuestas
            # (medido: DE01500-26, 42 respuestas citadas, descartada).
            c["clase"] = "CIRCULAR"
        elif c["tipo"] == "Enviado":
            c["clase"] = "DIRECTA"
        else:
            c["clase"] = "RECIBIDA"
    return cartas, desc, {"con_pdf": con_pdf, "usar_pdf": usar_pdf}


# ─────────────────────────────────────────────────────────────────────────────
# Requerimientos y estado
# ─────────────────────────────────────────────────────────────────────────────
CONTEO = {"CORPORACION", "NACIONAL", "COBRE", "MINERA", "COMPANIA", "ELECTRICA",
          "DEL", "LOS", "LAS", "DE", "Y", "SA", "SPA", "LTDA", "LIMITADA", "CHILE", "ENERGIA",
          "GENERACION", "TRANSMISORA", "SOCIEDAD", "EMPRESA", "PARQUE", "CHILENA"}

# Números romanos: Eletrans II, Eletrans III y Eletrans son TRES cuentas distintas.
# Solo I/II/III: 'V' y 'VI' chocaban con letras sueltas ('GREEN POWER VOLT' daba romano 'V').
ROMANO = re.compile(r"\b(I{1,3})\b")

# Los sufijos societarios desaparecen antes de comparar; si no, "S.A." tapa el numeral romano.
SOCIETARIO = re.compile(r"\bS\.?\s?A\.?\b|\bSPA\b|\bLTDA\b|\bLIMITADA\b", re.I)
NO_ALFA = re.compile(r"[^A-Z0-9]+")


def _base(nombre):
    """Nombre en mayúsculas sin tildes, sin sufijo societario y sin puntuación. Base de comparación."""
    s = unicodedata.normalize("NFD", nombre or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").upper()
    return NO_ALFA.sub(" ", SOCIETARIO.sub(" ", s)).strip()


def tokens_empresa(nombre):
    """
    Tokens distintivos de un nombre de empresa, para comparar el PDF del CEN con las cartas.
    El paréntesis NO se borra: ahí va el nombre comercial ('Codelco (Corporación...)'), y el
    nombre de la carta llega truncado ('...del Cobr…'), así que comparar la cadena entera falla.
    Los genéricos se filtran: 'DEL' hacía match entre cualquier par (falso positivo medido).
    """
    base = _base(nombre)
    toks = {t for t in base.split() if len(t) > 2 and t not in CONTEO}
    m = ROMANO.search(base)
    if m:
        toks.add(m.group(1))
    return toks


def misma_empresa(a, b):
    """
    ¿Son la misma cuenta? Se compara el NOMBRE PROPIO, no la cadena.

    El corpus trae el mismo nombre de tres formas distintas, y las tres hay que aceptar:
      'Codelco (Corporación Nacional del Cobre)'  ← lista de distribución del PDF
      'Codelco (Corporación Nacional del Cobr…'   ← carta con el nombre truncado
      'SonnediDon Goyo' / 'Sonnedix Don Goyo'     ← nombre pegado o mutilado

    Regla: los dos lados tienen que ser variantes del MISMO nombre. Se acepta que la versión
    larga contenga a la corta (CODELCO está en los dos, y 'COBR' es prefijo de 'COBRE').
    Se rechaza cuando lo que difiere es la identidad: 'GENERACION' vs 'GREEN POWER', 'BAQUEDANO'
    vs 'MELIPEuco', 'ELETRANS' vs 'ELETRANS II'. Por eso el numeral romano tiene que coincidir,
    y por eso comparar solo el primer token (o prefijar a lo bruto) no sirve.
    """
    sa, sb = _base(a), _base(b)
    ra, rb = ROMANO.search(sa), ROMANO.search(sb)
    if (ra is None) != (rb is None):
        return False
    if ra and ra.group(1) != rb.group(1):
        return False
    ta, tb = tokens_empresa(a), tokens_empresa(b)
    if not ta or not tb:
        return False

    corto, largo = (ta, tb) if len(ta) <= len(tb) else (tb, ta)

    def levenshtein(x, y):
        if len(x) < len(y):
            x, y = y, x
        prev = list(range(len(y) + 1))
        for i, cx in enumerate(x, 1):
            cur = [i]
            for j, cy in enumerate(y, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cx != cy)))
            prev = cur
        return prev[-1]

    # Comparación sobre el nombre propio completo, sin espacios ni puntuación. Es la única forma
    # que resuelve los tres casos del corpus a la vez:
    #   'CODELCO CORPORACION NACIONAL DEL COBR' ~ 'CODELCO CORPORACION NACIONAL DEL COBRE'  (truncado)
    #   'SONNEDI DON GOYO' ~ 'SONNEDIX DON GOYO'                                            (pegado)
    #   'ENEL GENERACION' vs 'ENEL GREEN POWER'  → distancia 6, NO alcanza                   (filiales)
    # El umbral es proporcional: 1 error por cada 8 caracteres, con un máximo de 2 en nombres cortos.
    ja = "".join(_base(a).split())
    jb = "".join(_base(b).split())
    if not ja or not jb:
        return False
    n = max(len(ja), len(jb))
    umbral = max(1, min(2, n // 8))
    return levenshtein(ja, jb) <= umbral


# Muletillas de redacción que quedan pegadas al nombre cuando el regex agarra la frase entera.
RELLENO = re.compile(
    r"^(?:a\s+trav[eé]s\s+de\s+la\s+presente\s+comunicaci[oó]n|"
    r"por\s+medio\s+de\s+la\s+presente|mediante\s+la\s+presente|"
    r"en\s+representaci[oó]n\s+de|la\s+sociedad|la\s+empresa|"
    r"correo\s+electr[oó]nico)[,:;\s]+", re.I)


def empresa_desde_pdf(txt):
    """
    Las cartas RECIBIDAS que responden a una circular llegan con la empresa VACÍA en el listado
    (el modal del sitio falla en esas filas). Sin esto, la respuesta existe pero no se le puede
    atribuir a nadie y el requerimiento aparece como 'sin respuesta' para siempre.
    El nombre está en el encabezado del PDF, antes de 'Señor:'.

    El regex puede agarrar la frase entera ('Por medio del presente, y en representación de
    Interchile S.A.'). En vez de perseguir cada muletilla, se toma el ÚLTIMO segmento tras coma
    que tenga forma de razón social: el nombre legal siempre va al final de la frase.
    """
    if not txt:
        return ""
    cab = txt[:900]
    patrones = [
        r"([A-ZÁÉÍÓÚÑÜ][\wáéíóúñüÁÉÍÓÚÑÜ&.,'\- ]{3,70}?\s(?:S\.A\.|SpA|LTDA|Limitada|S\.A))",
        r"^\s*([A-Z][\wáéíóúñüÁÉÍÓÚÑÜ&.\- ]{4,60}?(?:Energía|Generación|Transmisión|Holding|Chile))\.",
    ]
    for p in patrones:
        m = re.search(p, cab, re.M)
        if not m:
            continue
        frase = norm_ws(m.group(1))
        # de la frase, el último trozo que empieza con mayúscula y termina en razón social
        trozos = [t.strip() for t in re.split(r",|;| que | y en ", frase) if t.strip()]
        cand = frase
        for t in reversed(trozos):
            if re.search(r"(S\.A\.?|SpA|LTDA|Limitada)\s*$", t):
                cand = t
                break
        cand = norm_ws(re.sub(r"^[a-záéíóúñü ,;]*(?=[A-Z])", "", cand))
        if not NO_CUENTA.search(cand) and len(cand) > 3:
            return cand
    return ""


def analizar(cartas):
    # respuestas: cartas recibidas que citan el correlativo de un requerimiento
    respuestas = collections.defaultdict(list)
    for c in cartas:
        if c["tipo"] != "Recibido":
            continue
        for r in c["refs"]:
            if r != c["correlativo"]:
                respuestas[r].append(c)

    reqs = []
    for c in cartas:
        if c["tipo"] != "Enviado" or not c["pide"] or not c["productos"]:
            continue
        if c["clase"] not in ("DIRECTA", "CIRCULAR"):
            continue
        # destinatarios: la empresa directa, o la lista de distribución de la circular
        if c["clase"] == "DIRECTA":
            if not c["es_cuenta"]:
                continue
            destinos = [c["empresa"]]
        else:
            destinos = c["destinatarios"]
            if not destinos:
                # Circular con padrón en anexo/Excel: no se sabe a quién exactamente, pero el CEN
                # SÍ lo pidió y los coordinados SÍ responden. Antes se descartaba entera y se
                # perdían esas respuestas (medido: DE01500-26, 42 respuestas citadas).
                # Se registra con destinatario vacío: cuenta como requerimiento, no se le inventa dueño.
                destinos = [""]
        resp = sorted(respuestas.get(c["correlativo"], []), key=lambda x: x["fecha"])
        for destino in destinos:
            propias = [r for r in resp if r["empresa"] and misma_empresa(destino, r["empresa"])]
            reqs.append({
                "correlativo": c["correlativo"], "carta_id": c["carta_id"],
                "clase": c["clase"], "fecha": c["fecha"],
                "empresa": destino, "empresa_key": norm_empresa(destino),
                "productos": c["productos"], "producto": c["productos"][0],
                "materia_macro": c["materia_macro"],
                "materia_micro": c["materia_micro"],
                "n_respuestas": len(propias),
                "fecha_respuesta": propias[-1]["fecha"] if propias else None,
                "respuestas": [{"correlativo": r["correlativo"], "fecha": r["fecha"].isoformat(),
                                "materia": r["materia_micro"][:180]} for r in propias[-3:]],
            })

    # REITERADO: el CEN volvió a pedir lo mismo a la misma empresa. Se marca la carta que INSISTE
    # (todas menos la primera), no todas: marcar las dos inflaba el conteo al doble y mezclaba
    # "pidió una vez" con "tuvo que repetirlo".
    grupo = collections.defaultdict(list)
    for r in reqs:
        grupo[(r["empresa_key"], r["producto"])].append(r)
    reiterados = {}
    for lst in grupo.values():
        if len(lst) < 2:
            continue
        lst = sorted(lst, key=lambda x: x["fecha"])
        for r in lst[1:]:
            reiterados[r["correlativo"]] = len(lst)

    # REABIERTO: el CEN volvió a escribir del mismo producto después de la respuesta
    por_emp_prod = collections.defaultdict(list)
    for r in reqs:
        por_emp_prod[(r["empresa_key"], r["producto"])].append(r)
    reabiertos = {}
    for r in reqs:
        if not r["fecha_respuesta"]:
            continue
        post = [x for x in por_emp_prod[(r["empresa_key"], r["producto"])]
                if x["fecha"] > r["fecha_respuesta"] and x["correlativo"] != r["correlativo"]]
        if post:
            reabiertos[r["correlativo"]] = [{"correlativo": x["correlativo"],
                                             "fecha": x["fecha"].isoformat(),
                                             "materia": x["materia_micro"][:180]}
                                            for x in sorted(post, key=lambda z: z["fecha"])[-2:]]

    for r in reqs:
        flags = []
        if r["n_respuestas"] == 0:
            flags.append("SIN_RESPUESTA")
        if r["correlativo"] in reiterados:
            flags.append("REITERADO")
        if r["correlativo"] in reabiertos:
            flags.append("REABIERTO")
        if not flags:
            flags.append("RESPONDIDO")
        r["estados"] = flags
        r["estado"] = flags[0] if len(flags) == 1 else "MIXTO"
        r["dias_abierto"] = (HOY - r["fecha"]).days
        r["reiteraciones"] = reiterados.get(r["correlativo"], 1)
        r["carta_posterior"] = reabiertos.get(r["correlativo"], [])
    return reqs


# ─────────────────────────────────────────────────────────────────────────────
# Potencial (precios reales de BOMs, supuesto a la vista)
# ─────────────────────────────────────────────────────────────────────────────
def cargar_potencial():
    ruta = os.path.expanduser("~/conecta-agentes/indices/motor_bom_resumen.json")
    if not os.path.exists(ruta):
        return None, None
    with open(ruta) as f:
        res = json.load(f)
    t = res.get("tarifas_oficina", {})
    try:
        uf_h = 0.30 * t["ing_norm_s"] + 0.40 * t["ing_norm_a"] + 0.30 * t["ing_norm_b"]
    except KeyError:
        return res, None
    return res, round(uf_h, 4)


ORDEN_ESTADO = {"MIXTO": 5, "SIN_RESPUESTA": 4, "REABIERTO": 3, "REITERADO": 2, "RESPONDIDO": 1}


def peor(estados):
    return max(estados, key=lambda s: ORDEN_ESTADO.get(s, 0)) if estados else "RESPONDIDO"


def potencial(reqs, res, uf_h):
    if not res or not uf_h:
        return [], None
    # Agrupar por NOMBRE NORMALIZADO, no por la cadena: 'Colbún S.A.' y 'COLBÚN S.A.' son la
    # misma cuenta y el corpus las escribe de las dos formas. Se conserva la variante más frecuente
    # como nombre visible, para que el reporte no muestre un nombre inventado.
    opp = collections.defaultdict(lambda: {"reqs": [], "estados": set()})
    variantes = collections.Counter()
    for r in reqs:
        opp[(r["empresa_key"], r["producto"])]["reqs"].append(r)
        opp[(r["empresa_key"], r["producto"])]["estados"].update(r["estados"])
        variantes[(r["empresa_key"], r["producto"], r["empresa"])] += 1

    # El MISMO cliente aparece escrito distinto según el producto ('Engie Energía Chile S.A.' en
    # SSCC y 'ENGIE ENERGÍA CHILE S.A' en SITR). Un registro por producto es correcto, pero el
    # nombre debe ser uno solo: se elige el mejor por empresa y se usa en todos sus productos.
    mejor_por_empresa = {}
    for (k, p, e), n in variantes.items():
        clave = (-n, -len(e), e != e.upper())
        if k not in mejor_por_empresa or clave < mejor_por_empresa[k][0]:
            mejor_por_empresa[k] = (clave, e)

    filas = []
    for (ekey, prod), v in opp.items():
        emp = mejor_por_empresa.get(ekey, ((0,), ""))[1] if ekey else ""
        linea = PRODUCTOS[prod]["linea_bom"]
        base = res.get(linea)
        if not base:
            continue
        hh, margen = base["hh_mediana"], base["margen_mediana"] / 100
        usd = round(hh * uf_h * UF_USD)
        filas.append({
            "empresa": emp, "producto": prod, "linea_bom": linea,
            "n_reqs": len(v["reqs"]), "estados": sorted(v["estados"]),
            "estado_peor": peor(v["estados"]),
            "correlativos": sorted({r["correlativo"] for r in v["reqs"]})[:6],
            "hh_mediana": hh, "n_bom": base["n"],
            "dias_max": max(r["dias_abierto"] for r in v["reqs"]),
            "usd_venta": usd, "usd_margen": round(usd * margen), "margen_pct": base["margen_mediana"],
        })
    # Orden por GRAVEDAD de la mora, no por plata: el monto depende solo del producto, así que
    # ordenar por monto deja cientos empatadas y no prioriza nada.
    # Gravedad = estado (sin respuesta > reabierto > reiterado) + insistencia + antigüedad en meses.
    for f in filas:
        # Gravedad con decimales: la parte entera manda el orden (estado, insistencia, meses) y el
        # resto desempata por lo poco que queda. Sin esto, 330 cuentas empataban en 410 y dentro
        # del empate ordenaba el alfabeto: el 5º puesto lo decidía la letra, no la mora.
        f["gravedad"] = (ORDEN_ESTADO.get(f["estado_peor"], 0) * 100
                         + min(f["n_reqs"], 20) * 3
                         + min(f["dias_max"], 730) // 60
                         + min(f["n_reqs"], 20) / 100          # más cartas del CEN = más insistencia
                         + min(f["dias_max"], 730) / 100000)   # más antigüedad = más grave
        f["gravedad"] = round(f["gravedad"], 4)
    # Las filas SIN EMPRESA son las circulares con el padrón en anexo: se registran para no perder
    # sus respuestas, pero no son una cuenta y no pueden encabezar el ranking de cuentas
    # (medido: una fila anónima con 362 reqs salía 1ª del top). Van al final.
    filas.sort(key=lambda x: (not x["empresa"].strip(), -x["gravedad"], x["empresa"].upper()))
    return filas, {"uf_h": uf_h, "uf_usd": UF_USD,
                   "fuente": "~/conecta-agentes/indices/motor_bom_resumen.json (1.133 BOMs reales)"}


# ─────────────────────────────────────────────────────────────────────────────
# Odoo (opcional)
# ─────────────────────────────────────────────────────────────────────────────
def cruce_odoo():
    ruta = os.path.expanduser("~/.hermes/cache/odoo_prod_creds.json")
    if not os.path.exists(ruta):
        return None, "sin_credenciales_produccion"
    try:
        import requests
        with open(ruta) as f:
            cr = json.load(f)
        url = cr["host"].rstrip("/") + "/jsonrpc"

        def call(svc, mtd, args):
            r = requests.post(url, json={"jsonrpc": "2.0", "method": "call", "id": 1,
                                         "params": {"service": svc, "method": mtd, "args": args}}, timeout=60)
            r.raise_for_status()
            return r.json().get("result")
        uid = call("common", "login", [cr["db"], cr["username"], cr["api_key"]])
        if not uid:
            return None, "login_fallido"
        leads = call("object", "execute_kw", [cr["db"], uid, cr["api_key"], "crm.lead", "search_read",
                                              [[["partner_id", "!=", False]]],
                                              {"fields": ["id", "name", "partner_id", "stage_id"],
                                               "limit": 5000}]) or []
        idx = {}
        for l in leads:
            p = l.get("partner_id")
            if not p:
                continue
            k = norm_empresa(p[1])
            st = (l.get("stage_id") or [0, ""])[1]
            e = idx.setdefault(k, {"nombre": p[1], "leads": 0, "ganado": False, "etapas": set()})
            e["leads"] += 1
            e["ganado"] = e["ganado"] or bool(re.search(r"won|ganad", st, re.I))
            e["etapas"].add(st)
        for k in idx:
            idx[k]["etapas"] = sorted(x for x in idx[k]["etapas"] if x)
        return idx, "ok"
    except Exception as ex:
        return None, f"error:{type(ex).__name__}"


STOP = {"EMPRESA", "ELECTRICA", "SOCIEDAD", "GENERACION", "ENERGIA", "DEL", "LOS", "LAS",
        "Y", "DE", "COMPANIA", "INVERSIONES", "PARQUE", "EOLICO", "TRANSMISORA", "GENERADORA"}


def match_odoo(key, idx):
    a = {t for t in key.split() if t not in STOP and len(t) > 2}
    if not a:
        return None
    mejor, sc = None, 0.0
    for k, v in idx.items():
        b = {t for t in k.split() if t not in STOP and len(t) > 2}
        if not b:
            continue
        j = len(a & b) / len(a | b)
        if j > sc:
            mejor, sc = v, j
    if sc >= 0.6:
        return {"nombre": mejor["nombre"], "leads": mejor["leads"], "ganado": mejor["ganado"],
                "etapas": mejor["etapas"], "jaccard": round(sc, 2),
                "tipo": "CLIENTE" if mejor["ganado"] else "PIPELINE"}
    return None


# ─────────────────────────────────────────────────────────────────────────────
def main():
    usar_pdf = "--pdfs" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    cartas, desc, info_pdf = cargar(usar_pdf)
    reqs = analizar(cartas)

    # Circulares que piden algo pero no tienen lista (no se pudo leer el PDF): se declaran, no se esconden
    circulares_sin_lista = [c for c in cartas if c["tipo"] == "Enviado" and c["pide"]
                            and c["productos"] and not c["destinatarios"]
                            and (not c["empresa"] or NO_CUENTA.search(c["empresa"]))
                            and c["correlativo"].startswith("DE")]

    por_producto = []
    for k in PRECEDENCIA:
        rs = [r for r in reqs if k in r["productos"]]
        if not rs:
            continue
        # Los tres estados del CEN se reportan por separado (criterio de Victor). Pero 'respondido'
        # NO puede salir del estado RESPONDIDO: ese estado solo existe si el requerimiento no fue
        # ni reiterado ni reabierto, así que una carta respondida y luego reiterada quedaba fuera
        # y el producto marcaba 0 respondidos teniendo 204 con respuesta (medido en SITR).
        est = collections.Counter(e for r in rs for e in r["estados"])
        con_resp = sum(1 for r in rs if r["n_respuestas"] > 0)
        circ = [c for c in circulares_sin_lista if k in c["productos"]]
        por_producto.append({
            "producto": k, "nombre": PRODUCTOS[k]["nombre"], "solucion": PRODUCTOS[k]["solucion"],
            "norma": PRODUCTOS[k]["norma"],
            "n_reqs": len(rs), "empresas": len({r["empresa_key"] for r in rs}),
            "sin_respuesta": est["SIN_RESPUESTA"], "reiterado": est["REITERADO"],
            "reabierto": est["REABIERTO"], "respondido": con_resp,
            # 'vivas' = requerimientos del producto sin cerrar. Es la ÚNICA cifra que se puede
            # sumar: los tres estados se solapan y sumarlos da más que el total (2120 sobre 899).
            "vivas": len(rs) - con_resp,
            "circulares_sin_lista": len(circ),
            "ultima": max(r["fecha"] for r in rs).isoformat(),
        })
    por_producto.sort(key=lambda x: -(x["sin_respuesta"] + x["reiterado"] + x["reabierto"]))

    res, uf_h = cargar_potencial()
    filas, sup = potencial(reqs, res, uf_h)

    estado_odoo, clientes = "no_solicitado", None
    if "--odoo" in sys.argv:
        clientes, estado_odoo = cruce_odoo()
    if clientes:
        for f in filas:
            f["odoo"] = match_odoo(norm_empresa(f["empresa"]), clientes)

    # Integrar el cruce de PRODUCCIÓN (out/cruce_odoo.json, lo escribe cruce_odoo.py).
    # Se hace acá y no en el reportero para que radar.json sea la fuente única: el cron leía
    # 'oportunidades[].odoo' y ese campo no existía (el estado vivía solo en el otro archivo).
    cruce_p = os.path.join(OUT, "cruce_odoo.json")
    odoo_prod = "no_ejecutado"
    if os.path.exists(cruce_p):
        try:
            _od = json.load(open(cruce_p, encoding="utf-8"))
            _est = {(x["empresa"], x["producto"]): (x.get("odoo"), x.get("odoo_etapas"),
                                                    x.get("odoo_usd"), x.get("odoo_leads"))
                    for x in _od.get("filas", [])}
            n = 0
            for f in filas:
                e = _est.get((f["empresa"], f["producto"]))
                if e and e[0]:
                    f["odoo"] = e[0]
                    f["odoo_etapas"], f["odoo_usd"], f["odoo_leads"] = e[1], e[2], e[3]
                    n += 1
                else:
                    f.setdefault("odoo", None)
            odoo_prod = f"ok:{n}"
        except Exception as ex:                       # no romper el radar por el ERP
            odoo_prod = f"error:{type(ex).__name__}"
    else:
        for f in filas:
            f.setdefault("odoo", None)

    clases = collections.Counter(c["clase"] for c in cartas)
    salida = {
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "corpus": {
            "cartas_total": len(cartas), "descartadas": dict(desc),
            "pdfs_leidos": info_pdf["con_pdf"], "usar_pdf": info_pdf["usar_pdf"],
            "truncadas_sin_pdf": sum(1 for c in cartas if c["truncada"] and not c["texto"]),
            "rango": [min(c["fecha"] for c in cartas).isoformat(),
                      max(c["fecha"] for c in cartas).isoformat()],
            "clases": dict(clases),
            "circulares_sin_lista": len(circulares_sin_lista),
        },
        "por_producto": por_producto,
        "requerimientos": [{**{k: v for k, v in r.items() if k not in ("fecha", "fecha_respuesta")},
                            "fecha": r["fecha"].isoformat(),
                            "fecha_respuesta": r["fecha_respuesta"].isoformat() if r["fecha_respuesta"] else None}
                           for r in sorted(reqs, key=lambda x: -x["fecha"].toordinal())],
        "oportunidades": filas,
        "supuestos_potencial": sup,
        "odoo": {"estado": estado_odoo, "partners": len(clientes) if clientes else 0,
                 "cruce_produccion": odoo_prod},
    }
    with open(os.path.join(OUT, "radar.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1, default=str)

    print(f"documentos         : {len(cartas)}  {dict(clases)}")
    print(f"PDFs en cache      : {info_pdf['con_pdf']}")
    print(f"descartadas        : {dict(desc)}")
    print(f"requerimientos     : {len(reqs)}  (circulares sin lista: {len(circulares_sin_lista)})")
    for p in por_producto:
        print(f"  {p['producto']:12s} req={p['n_reqs']:4d} emp={p['empresas']:3d} "
              f"sin_resp={p['sin_respuesta']:3d} reiter={p['reiterado']:3d} reab={p['reabierto']:3d} "
              f"resp={p['respondido']:3d} circ_sin_lista={p['circulares_sin_lista']}")
    print(f"oportunidades      : {len(filas)}   odoo: {estado_odoo}")
    if sup:
        print(f"supuesto potencial : {sup['uf_h']} UF/h · UF={sup['uf_usd']} USD")
    print(f"→ {os.path.join(OUT,'radar.json')}")


if __name__ == "__main__":
    main()
