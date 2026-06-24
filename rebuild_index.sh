#!/usr/bin/env bash
# Пересборка семантического индекса HEFEST из корпуса (для чистого клона без LFS-эмбеддингов).
# Гонит 26k чанков через ЛОКАЛЬНУЮ Ollama (bge-m3) -> data/embeddings_clean.npy + data/embed_ids_clean.json.
# С чекпойнтом: можно прервать и перезапустить — продолжит с места.
#
# Требуется: Ollama (https://ollama.com) + модель bge-m3 (~1 ГБ). Интернет НЕ нужен после загрузки модели.
# Время: ориентир 5–20 мин на Apple Silicon / GPU; на CPU дольше.
#
# Запуск:  bash rebuild_index.sh
set -euo pipefail
cd "$(dirname "$0")"

OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
EMBED_MODEL="${EMBED_MODEL:-bge-m3}"

echo "[1/3] Проверка Ollama ($OLLAMA_HOST) и модели $EMBED_MODEL"
if ! curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
  echo "  ✗ Ollama недоступна на $OLLAMA_HOST. Запусти 'ollama serve' (или задай OLLAMA_HOST)." >&2
  exit 1
fi
if ! curl -fsS "$OLLAMA_HOST/api/tags" | grep -q "$EMBED_MODEL"; then
  echo "  • модели $EMBED_MODEL нет — тяну (ollama pull $EMBED_MODEL)…"
  ollama pull "$EMBED_MODEL"
fi
echo "  ✓ Ollama и $EMBED_MODEL готовы"

echo "[2/3] Эмбеддинги корпуса -> data/embeddings_clean.npy (чекпойнт каждые ~1600)"
CORPUS_FILE=corpus_full_clean.json \
EMB_FILE=embeddings_clean.npy \
IDS_FILE=embed_ids_clean.json \
OLLAMA_HOST="$OLLAMA_HOST" \
EMBED_MODEL="$EMBED_MODEL" \
  python3 engine/build_semantic_index.py "$@"

echo "[3/3] Готово. Запуск сервиса в семантическом режиме:"
cat <<'RUN'
  SUBS_FILE=substances_clean.json CORPUS_FILE=corpus_full_clean.json \
  RETRIEVER=semantic EMB_FILE=embeddings_clean.npy IDS_FILE=embed_ids_clean.json \
  LLM_BACKEND=ollama OLLAMA_LLM=qwen2.5:7b \
  python3 -m uvicorn service:app --app-dir engine --port 8012
RUN
