#!/bin/bash
# Sincroniza el corpus de cartas CEN desde el VPS y baja los PDFs que falten.
# El corpus vivo (scrapeado por Playwright) vive en el VPS: el Mac no puede pasar Cloudflare.
#
# Uso:  bash src/sincronizar.sh
# Cron (lunes 07:00): 0 7 * * 1 cd ~/orca/projects/RadarNormativoCEN && bash src/sincronizar.sh
set -uo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
PY=~/.hermes/hermes-agent/venv/bin/python
VPS=root@100.94.162.88
KEY=~/.ssh/id_ed25519_hermes
LOG="$BASE/out/sync.log"

mkdir -p "$BASE/out" "$BASE/data"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') sincronizar ===" >> "$LOG"

# 1. Corpus: traer el JSON del VPS (si el VPS no responde, seguir con el local y avisar)
if scp -q -i "$KEY" -o ConnectTimeout=20 -o StrictHostKeyChecking=no \
      "$VPS:/root/cartas_cen_full.json" "$BASE/data/cartas_cen_full.json.new" 2>>"$LOG"; then
  # Validar antes de reemplazar: un JSON cortado no debe pisar un corpus bueno.
  if "$PY" - "$BASE/data/cartas_cen_full.json.new" >>"$LOG" 2>&1 <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert isinstance(d, list) and len(d) > 10000, f"corpus sospechoso: {len(d)} cartas"
print(f"[corpus] {len(d)} cartas OK")
PY
  then
    mv "$BASE/data/cartas_cen_full.json.new" "$BASE/data/cartas_cen_full.json"
    echo "[corpus] reemplazado" >> "$LOG"
  else
    rm -f "$BASE/data/cartas_cen_full.json.new"
    echo "[corpus] DESCARTADO (no valida): se mantiene el anterior" >> "$LOG"
  fi
else
  echo "[corpus] VPS no disponible: se usa el corpus local" >> "$LOG"
fi

# 2. PDFs de las cartas que piden algo (cachea: correr dos veces no vuelve a bajar)
"$PY" "$BASE/src/bajar_pdfs.py" >> "$LOG" 2>&1 || echo "[pdfs] falló" >> "$LOG"

# 3. Análisis + reportes
# ORDEN IMPORTA: el motor integra out/cruce_odoo.json en radar.json, así que el cruce con Odoo
# se calcula ANTES. Al revés, radar.json llevaba el cruce de la corrida anterior.
"$PY" "$BASE/src/cruce_odoo.py" >> "$LOG" 2>&1 || echo "[cruce_odoo] falló (se sigue sin ERP)" >> "$LOG"
"$PY" "$BASE/src/motor.py" --pdfs >> "$LOG" 2>&1 || { echo "[motor] FALLÓ" >> "$LOG"; exit 1; }
# Cruce con la base instalada (BOMs + OTs): clasifica cliente / prospecto antes de reportar
"$PY" "$BASE/src/cruce_base.py" >> "$LOG" 2>&1 || echo "[cruce_base] falló" >> "$LOG"
"$PY" "$BASE/src/reporte.py" >> "$LOG" 2>&1 || { echo "[reporte] FALLÓ" >> "$LOG"; exit 1; }
"$PY" "$BASE/src/reporte_campana.py" >> "$LOG" 2>&1 || echo "[reporte_campana] falló" >> "$LOG"

# 4. Verificación: si no cuadra contra los casos conocidos, se dice en el log (no se maquilla)
for V in verificar.py verificar_sync.py verificar_campana.py; do
  if "$PY" "$BASE/src/$V" >> "$LOG" 2>&1; then
    echo "[verificar] $V OK" >> "$LOG"
  else
    echo "[verificar] $V HAY FALLOS: revisar $LOG" >> "$LOG"
  fi
done

echo "=== fin $(date '+%Y-%m-%d %H:%M:%S') · reporte: $BASE/out/radar_normativo.html" >> "$LOG"

# 5. Envío por correo del reporte de oportunidades (Resend).
#    Va al final y solo si el pipeline llegó hasta acá: si el motor falló, no se manda nada.
#    Desactivar con RADAR_SIN_CORREO=1.
if [ "${RADAR_SIN_CORREO:-0}" = "1" ]; then
  echo "[correo] omitido (RADAR_SIN_CORREO=1)" >> "$LOG"
else
  if "$PY" "$HOME/.hermes/scripts/enviar_radar_cen.py" --para "${RADAR_DESTINO:-victor.vilche@conecta.cl}" --enviar >> "$LOG" 2>&1; then
    echo "[correo] enviado a ${RADAR_DESTINO:-victor.vilche@conecta.cl}" >> "$LOG"
  else
    echo "[correo] FALLÓ el envío: revisar $LOG" >> "$LOG"
  fi
fi

echo "reporte: $BASE/out/radar_normativo.html"
