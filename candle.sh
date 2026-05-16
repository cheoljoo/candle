#!/bin/bash
# 사용법:
#   ./candle.sh        - 전체 파이프라인 (v2-all, 기존 동작)
#   ./candle.sh kr     - 한국장 종료 후 파이프라인 (v2-all-kr, ~16:00 KST)
#   ./candle.sh us     - 미국장 종료 후 파이프라인 (v2-all-us, ~09:00 KST)
export PATH=$HOME/.local/bin:$PATH

CANDLE_DIR="/home/cheoljoo/code/candle"

# ── 인자에 따라 make 타겟 / 로그파일명 결정 ──
MARKET="${1:-}"   # kr | us | (없으면 전체)

case "${MARKET}" in
    kr)
        MAKE_TARGET="v2-all-kr"
        LOGFILE="${CANDLE_DIR}/candle-v2-kr.log"
        LOGBASE_SUFFIX="kr"
        ;;
    us)
        MAKE_TARGET="v2-all-us"
        LOGFILE="${CANDLE_DIR}/candle-v2-us.log"
        LOGBASE_SUFFIX="us"
        ;;
    "")
        MAKE_TARGET="v2-all"
        LOGFILE="${CANDLE_DIR}/candle-v2.log"
        LOGBASE_SUFFIX=""
        ;;
    *)
        echo "Usage: $0 [kr|us]"
        exit 1
        ;;
esac

# ── 실행 ──
cd "${CANDLE_DIR}"
set -o pipefail
make "${MAKE_TARGET}" 2>&1 | tee "${LOGFILE}"

# ── 날짜별 log backup ──
if [ -n "${LOGBASE_SUFFIX}" ]; then
    LOGBASE="${CANDLE_DIR}/candle-v2-${LOGBASE_SUFFIX}-$(date +%Y_%m_%d)"
else
    LOGBASE="${CANDLE_DIR}/candle-v2-$(date +%Y_%m_%d)"
fi
BACKUP="${LOGBASE}.log"
COUNTER=1

while [ -f "$BACKUP" ]; do
    BACKUP="${LOGBASE}-${COUNTER}.log"
    COUNTER=$((COUNTER + 1))
done

cp "${LOGFILE}" "$BACKUP"
echo "Log backed up to: $BACKUP"
