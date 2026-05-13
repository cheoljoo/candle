#!/bin/bash
export PATH=$HOME/.local/bin:$PATH

CANDLE_DIR="/home/cheoljoo/code/candle"
LOGFILE="${CANDLE_DIR}/candle-v2.log"

# ── 실행 ──
cd "${CANDLE_DIR}"
set -o pipefail
make v2-all 2>&1 | tee "${LOGFILE}"

# ── 날짜별 log backup ──
LOGBASE="${CANDLE_DIR}/candle-v2-$(date +%Y_%m_%d)"
BACKUP="${LOGBASE}.log"
COUNTER=1

while [ -f "$BACKUP" ]; do
    BACKUP="${LOGBASE}-${COUNTER}.log"
    COUNTER=$((COUNTER + 1))
done

cp "${LOGFILE}" "$BACKUP"
echo "Log backed up to: $BACKUP"
