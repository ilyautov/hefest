#!/usr/bin/env bash
# Развёртывание AI-помощника по химбезопасности на одной машине (без Docker).
# Один прогон: проверка зависимостей -> модели Ollama -> данные -> запуск.
# Для КИИ-контура: сначала собрать data/ на машине с интернетом (fetch_*.py), перенести,
# затем запускать этот скрипт уже в закрытом контуре (он в интернет не ходит).
#
# Требования к железу (ориентир): qwen2.5:7b — ~6 ГБ VRAM/RAM, bge-m3 — ~1 ГБ.
# Комфортно: GPU 8+ ГБ или Apple Silicon 16+ ГБ. CPU-only работает, но медленнее.
#
# Запуск:  bash setup.sh            # проверка + запуск
#          bash setup.sh --check    # только проверка готовности, без запуска
set -euo pipefail
cd "$(dirname "$0")"
ENGINE=engine
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
fail=0
ok(){ echo "  ✓ $1"; }
bad(){ echo "  ✗ $1"; fail=1; }

echo "[1/5] Python и зависимости"
python3 --version >/dev/null 2>&1 && ok "python3 $(python3 -V 2>&1 | awk '{print $2}')" || bad "нет python3"
python3 - <<'PY' && ok "ключевые пакеты (fastapi, uvicorn, numpy) на месте" || bad "не хватает пакетов — pip install -r engine/requirements.txt"
import importlib.util, sys
miss=[m for m in ("fastapi","uvicorn","numpy") if importlib.util.find_spec(m) is None]
sys.exit(1 if miss else 0)
PY

echo "[2/5] Данные (data/)"
for f in substances_clean.json corpus_full_clean.json embeddings_clean.npy embed_ids_clean.json; do
  [ -f "data/$f" ] && ok "data/$f" || bad "нет data/$f (собрать на машине с интернетом и перенести)"
done

echo "[3/5] Ollama и модели"
if curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
  ok "Ollama доступен ($OLLAMA_HOST)"
  tags=$(curl -fsS "$OLLAMA_HOST/api/tags")
  echo "$tags" | grep -q "bge-m3"   && ok "модель bge-m3"   || { echo "    -> ollama pull bge-m3";   bad "нет модели bge-m3"; }
  echo "$tags" | grep -q "qwen2.5"  && ok "модель qwen2.5"  || { echo "    -> ollama pull qwen2.5:7b"; bad "нет модели qwen2.5:7b"; }
else
  bad "Ollama недоступен на $OLLAMA_HOST (установить ollama и запустить). Без него — только LLM_BACKEND=extractive"
fi

echo "[4/5] Самопроверка импорта сервиса"
( cd "$ENGINE" && python3 -c "import ast; ast.parse(open('service.py').read())" ) && ok "service.py разбирается" || bad "ошибка в service.py"

echo "[5/5] Готовность"
if [ "$fail" -ne 0 ]; then
  echo "⚠ Есть незакрытые пункты выше — устраните перед запуском в прод."
  [ "${1:-}" = "--check" ] && exit 1 || exit 1
fi
echo "✓ Всё на месте."
[ "${1:-}" = "--check" ] && { echo "(--check: запуск пропущен)"; exit 0; }

echo
echo "Запускаю сервис на http://0.0.0.0:8000  (UI: открой / в браузере)"
cd "$ENGINE"
exec env \
  RETRIEVER="${RETRIEVER:-semantic}" \
  LLM_BACKEND="${LLM_BACKEND:-ollama}" \
  CORPUS_FILE="${CORPUS_FILE:-../data/corpus_full_clean.json}" \
  EMB_FILE="${EMB_FILE:-../data/embeddings_clean.npy}" \
  IDS_FILE="${IDS_FILE:-../data/embed_ids_clean.json}" \
  SUBS_FILE="${SUBS_FILE:-substances_clean.json}" \
  python3 -m uvicorn service:app --host 0.0.0.0 --port 8000
