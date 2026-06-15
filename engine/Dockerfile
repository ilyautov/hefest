# Образ сервиса SDS Safety Assistant (on-prem, air-gapped).
# ВАЖНО: контекст сборки = КОРЕНЬ РЕПОЗИТОРИЯ, а не папка engine/.
#   Сборка:  docker build -f engine/Dockerfile -t rag-sds .
#   (или просто `docker compose build` — compose уже задаёт context: . и dockerfile: engine/Dockerfile)
# Почему: сервис читает данные из ../data, и COPY не может выходить за пределы
# контекста сборки. Поэтому контекст — корень, а пути ниже даны от корня (engine/ и data/).
# В образ НЕ тянется ничего из интернета на рантайме: только pip-зависимости на этапе сборки
# (их в air-gap-контуре ставят с локального зеркала, см. DEPLOY.md).
FROM python:3.11-slim
WORKDIR /app

# Зависимости ставим первыми — кэш слоёв не инвалидируется при правках кода.
COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код сервиса -> /app/engine, данные -> /app/data (сервис ждёт корпус/эмбеддинги в ../data).
COPY engine/ /app/engine/
COPY data/ /app/data/

# Прод on-prem по умолчанию: генерация через локальный Ollama на железе завода.
# Хост Ollama берётся из OLLAMA_HOST (в контейнере -> host.docker.internal, см. docker-compose.yml).
# Дефолты ниже соответствуют прод-команде запуска (RETRIEVER=semantic, LLM_BACKEND=ollama).
# Переопределяются через .env / docker-compose без пересборки образа.
ENV RETRIEVER=semantic \
    LLM_BACKEND=ollama \
    OLLAMA_LLM=qwen2.5:7b \
    EMBED_MODEL=bge-m3 \
    OLLAMA_HOST=http://host.docker.internal:11434 \
    CORPUS_FILE=corpus_full_clean.json \
    EMB_FILE=embeddings_clean.npy \
    IDS_FILE=embed_ids_clean.json \
    SUBS_FILE=substances_clean.json \
    ABSTAIN_THRESHOLD=0.62

EXPOSE 8000
WORKDIR /app/engine
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]
