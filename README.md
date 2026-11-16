# normativacen — Arquitectura

Página de arquitectura del agente normativo CONECTA sobre el Coordinador Eléctrico Nacional.

**Publicada en:** https://vvilche.github.io/normativacen-arquitectura/

## Qué muestra

1. **Flujo de una consulta** — orquestador LangGraph con 9 dominios especialistas y auditor de calidad.
2. **Pipeline de ingesta** — el camino de una carta del CEN desde el sitio del Coordinador hasta quedar consultable, con la separación entre datos crudos (leads) y texto anonimizado (indexable).
3. **Arquitectura de servicios** — nginx en el borde, servicios Python en localhost, Tailscale para acceso interno, SQLite como almacenamiento.
4. **Conocimiento RAG** — los dos índices y sus volúmenes.
5. **Operación nocturna** — los jobs de cron del servidor.

## Cifras

Todas las cifras de la página se leyeron directamente de las bases SQLite y de `systemd` en el VPS el 16-nov-2026. No hay estimaciones ni datos de ejemplo.

## Nota sobre datos

La página describe la arquitectura y no expone datos de clientes ni contenido de cartas. La separación entre `texto_crudo` (con RUT y correos, solo en el servidor) y `texto_anon` (lo único indexable) está explicada como parte del diseño, en cumplimiento de la Ley 21.719.

## Archivo

- `index.html` — la página completa, autocontenida (CSS y JS embebidos, SVG generado por JS).

Sin dependencias de build. Se sirve tal cual desde la rama `main`.
