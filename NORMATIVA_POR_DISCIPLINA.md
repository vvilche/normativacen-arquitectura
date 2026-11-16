# Qué documentación normativa deberíamos tener, por disciplina

Medido sobre el corpus real de `RadarNormativoCEN`: **13.983 cartas** en el registro,
**5.612 con texto leído** (rango 02-ene-2025 a 01-nov-2026).

La pregunta no es "qué normativa existe" sino **qué nos va a pedir un cliente o el
Coordinador**, y de eso el corpus es la evidencia más honesta que tenemos: si el CEN
nunca lo pide, no es urgente tenerlo.

---

## El hallazgo que ordena todo

El corpus es **abrumadoramente eléctrico y de mercado**. Las cuatro disciplinas que
preguntaste existen, pero con un peso muy distinto:

| Disciplina | Cartas que la tocan | % del corpus | Veredicto |
|---|---|---|---|
| **Eléctrica / operación** | ~2.046 (NTSyCS) + 450 (SE/transformador/protección) | ~40 % | Es el negocio |
| **Mecánica** | 54 | 1,0 % | Periférico, pero aparece |
| **Ambiental** | 31 | 0,6 % | Aparece y puede frenar un proyecto |
| **Sísmica** | 20 | 0,4 % | Casi ausente |
| **Incendio / PCI** | 11 | 0,2 % | Casi ausente |

Cifras contadas con patrones de palabra completa, después de descartar falsos positivos
(`SMA` matcheaba "alguna", `deriva` matcheaba "derivado", `RCA` matcheaba "ARCA VERDE" y
"CRCA Bolero").

**Lo que esto significa:** no hay que construir cinco bibliotecas igual de profundas.
Hay que construir una completa (eléctrica) y cuatro delgadas, con lo justo para no
quedar en blanco cuando un cliente pregunte.

---

## 1. Eléctrica y operación — el núcleo

Acá ya tenemos material real. Normas y anexos que el Coordinador invoca efectivamente:

### Normas técnicas (4)

| Norma | Cartas | Qué gobierna |
|---|---|---|
| **NT SSCC** | 733 | Servicios complementarios: CPF, CSF, CT, CTF |
| **NT ISC** | 642 | Indisponibilidad de suministro y compensaciones (EAF, ENS) |
| **NT SyCS** | 486 | Seguridad y calidad de servicio |
| **NT CyO** | 131 | Coordinación y operación, programación |

### Anexos técnicos (10)

| Anexo | Cartas |
|---|---|
| Verificación de Instalaciones para prestación de SSCC | 597 |
| SITR | 205 |
| Pruebas de Potencia Máxima en Unidades Generadoras | 149 |
| Plan de Recuperación del Servicio (PRS) | 124 |
| Medición Fasorial (PMU/PDC) | 81 |
| Automatismos (EDAC/EDAG) | 55 |
| Determinación de Consumos Específicos | 40 |
| Definición de Parámetros Técnicos y Operativos | 33 |
| Sistema de Monitoreo (ATSM) | 25 |
| Registro de Protecciones (SLRP) | 18 |

### Anexos que el corpus revela y no teníamos catalogados

- **Determinación de Mínimos Técnicos en Unidades Generadoras** (99 cartas)
- **Parámetros para Procesos de Partida y Detención** (149)
- **Verificación de Partida Autónoma (PA)** (109)
- **Instalaciones Basadas en Convertidores** (27)
- **Mínimos Técnicos PMG** (2 — aparece poco con ese nombre exacto)
- **NTCO PMGD** (7 — norma técnica de coordinación para PMGD)

Nota: estas seis se detectaron buscando por frase, no por el nombre canónico del anexo.
Pueden solaparse entre sí y con los 10 anteriores. Hay que revisar una por una antes de
darlas por anexos distintos.

### Marco legal citado

| Norma | Cartas |
|---|---|
| **DFL 4** — Ley General de Servicios Eléctricos | 73 |
| **DS 88** | 13 (+ 6 en otras grafías) |
| **DS 125** | 15 (+ variantes) |
| **DS 130** | 7 |
| **DS 5**, **DS 4**, **DS 32**, **DS 52** | 10, 6, 2, 1 |
| **SEC** — Superintendencia, oficios electrónicos | 354 |

### Estándares internacionales que aparecen

| Norma | Menciones | Para qué |
|---|---|---|
| **IEC 60255** | 4 | Relés de protección |
| **IEC 61850** | 2 | Comunicaciones de subestación |
| **IEC 60870** | 2 | Telecontrol (IEC 60870-5-101/104) |
| **IEC 61439** | 2 | Tableros de baja tensión |
| **IEC 62443** | 1 | Ciberseguridad industrial — **empieza a aparecer** |
| **IEC 27019** | 1 | Seguridad de la información en energía |

---

## 2. Ambiental — delgada, pero puede frenar un proyecto

**31 cartas (0,6 %).** No es negocio recurrente; es **riesgo de cronograma**.

Lo que aparece realmente:

| Instrumento | Cartas | Qué es |
|---|---|---|
| **DS 40/2012 MMA** — Reglamento del SEIA | — | El reglamento que gobierna la RCA |
| **RCA** — Resolución de Calificación Ambiental | 9 | La autorización previa a construir |
| **SEIA** | 2 | El sistema de evaluación |
| **SMA** — Superintendencia del Medio Ambiente | 3 | Fiscalización y sanción |

**El caso real del corpus:** una central tuvo su construcción detenida esperando la RCA
por medidas de rescate y relocalización de fauna. El Coordinador no tiene nada que ver
con eso, pero el cronograma de conexión sí depende.

**Qué deberíamos tener:**
- DS 40/2012 completo y comentado (reglamento del SEIA)
- Ley 19.300 (Bases Generales del Medio Ambiente)
- Guías de la SMA sobre fiscalización
- **DS 38/2011** — norma de emisión para centrales termoeléctricas (aparece poco, pero aplica a generación)
- Plantilla de "estado ambiental del proyecto" para no prometer fechas sin verificar la RCA

**Lo que NO necesitamos:** ingeniería ambiental de detalle. No competimos ahí.

---

## 3. Mecánica — periférica, atada a las máquinas

**54 cartas (1,0 %).** Casi todo aparece por una razón: **turbinas** (34 cartas).

Lo que aparece:

| Materia | Cartas |
|---|---|
| Turbinas | 34 |
| Mecánicos / mecánica | 10 |
| Bombas | 6 |
| Caudal | 7 |
| Vibración | 4 |
| Lubricación | 3 |
| Presión de aceite | 2 |
| Compresores | 1 |

**El patrón:** la mecánica entra al corpus cuando una falla mecánica afecta la
disponibilidad o la potencia máxima declarada — o sea, cuando **se convierte en un
problema eléctrico**.

**Qué deberíamos tener:**
- Normas de la unidad generadora: curvas de potencia vs. condiciones (ISO 3046 para motores, IEC 60034 para generadores)
- API 670 (monitoreo de vibración de maquinaria rotativa) y API 610/617 (bombas, compresores)
- ISO 10816 (vibración de máquinas) y ISO 20816 (su reemplazo)
- Guía de "cómo una falla mecánica afecta la declaración de potencia máxima"

**Lo que NO necesitamos:** diseño mecánico. Solo el puente entre falla mecánica y
cumplimiento normativo.

---

## 4. Sísmica — casi ausente, pero es riesgo país

**20 cartas (0,4 %).** Solo 14 mencionan terremoto, 5 "sísmico", 2 amortiguamiento.

Chile es país sísmico y el CEN **no** exige análisis sísmico en sus cartas. Pero:

- Las subestaciones se diseñan con **NCh 2369** (diseño sísmico de estructuras e instalaciones industriales) y **NCh 433** (diseño sísmico de edificios) — **cero menciones en el corpus**.
- Un evento sísmico sí aparece: como causa de falla, después del hecho.

**Qué deberíamos tener (delgado):**
- NCh 2369 y NCh 433: los criterios de diseño
- **DS 61/2011** — reglamento que hace obligatoria la NCh 2369
- Ficha de "verificación sísmica post-evento" para actuar cuando tiemble
- Registro de acelerogramas del evento (el CEN y la U. de Chile los publican)

**Uso real:** cuando un cliente pregunta "¿mi subestación aguanta?", tener la norma y
un formato de respuesta. No hacer cálculo estructural.

---

## 5. Incendio / PCI — la más delgada

**11 cartas (0,2 %).** Solo la palabra "incendio", cero menciones a NFPA en el corpus.

Pero es una **línea de producto activa de CONECTA** (skill `conecta-leads-pci`, RPTD 08).

**Qué deberíamos tener:**
- **RPTD 08** — el reglamento técnico de protección contra incendios (que ya trabajamos)
- **NFPA 850** — protección contra incendio en plantas de generación
- **NFPA 70E** — seguridad eléctrica en el trabajo (aparece por el lado de arco eléctrico)
- **DS 93/2011** — reglamento de instalaciones de combustibles (si hay grupo electrógeno o transformador con aceite)
- Ficha "PCI en subestación": qué exige, qué instala CONECTA, qué deja a terceros

---

## Qué construir, en orden

1. **El catálogo eléctrico completo** — ya está en `CATALOGO_NORMATIVO.html`, pero le
   faltan los 6 anexos que este análisis reveló (mínimos técnicos, partida/detención,
   partida autónoma, convertidores, PMG, NTCO PMGD).
2. **Las cuatro fichas delgadas** (ambiental, mecánica, sísmica, PCI) — una plana cada
   una, con la norma, cuándo aparece y qué responder. **Un día de trabajo, no un mes.**
3. **El puente con producto**: qué vende CONECTA cuando el Coordinador exige cada
   entregable. Es lo que convierte el catálogo en cotización.

---

## Advertencia metodológica

Las cifras de cartas miden **cuántas cartas mencionan el tema**, no su importancia
normativa. Un anexo con 18 cartas puede ser más vinculante que uno con 200. Lo que este
documento mide es **frecuencia de invocación real**, que es la mejor proxy que tenemos
de "qué nos van a pedir".

Los articulados citados (DS 40/2012, NCh 2369, NFPA 850, etc.) son **conocimiento
general de la disciplina**, no extraídos del corpus — el corpus solo confirma que el
tema aparece. Están marcados así a propósito.
