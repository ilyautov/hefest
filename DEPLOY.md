# Деплой SDS Safety Assistant (on-prem, контур КИИ / 152-ФЗ)

RAG-сервис по химической безопасности (русские паспорта безопасности, SDS).
Рассчитан на работу в **air-gapped** контуре химзавода: на рантайме нет выхода
в интернет, все вычисления (поиск и генерация) — на локальном железе.

---

## 1. Компоненты

| Компонент | Где работает | Назначение |
|-----------|--------------|------------|
| FastAPI-сервис (`engine/service.py`) | контейнер `sds`, порт 8000 | API: `/health`, `/ask`, `/substance`, `/search` и др. |
| Ollama | **на хосте** железа завода, порт 11434 | эмбеддинги `bge-m3` + генерация `qwen2.5:7b` |
| Qdrant (опц.) | контейнер `qdrant`, профиль `qdrant` | векторная БД; по умолчанию НЕ нужна |
| `data/` | том, проброшен в контейнер read-only | корпус, эмбеддинги, справочники |

Ollama сознательно вынесена на хост, а не в compose: модель и веса остаются
на машине оператора, контейнер обращается к ней по `host.docker.internal`
(подробнее о сетевом выборе — в `docker-compose.yml`).

---

## 2. Подготовка (однократно, на машине С интернетом)

Этот этап выполняется ОДИН раз вне контура КИИ. В контур переносится только
готовая папка `data/` (см. раздел 5 «Офлайн-гарантия»).

1. Собрать/обновить корпус и справочники (скрипты `engine/fetch_*.py`,
   `engine/build_corpus.py`, `engine/ingest_*.py`). Они ходят в интернет
   (PubChem, CDC, Wikidata) — это нормально на этапе сборки данных.
2. Построить семантический индекс:
   ```bash
   cd engine
   python build_semantic_index.py    # пишет data/embeddings_clean.npy + embed_ids
   ```
3. Очистить/нормализовать данные (`engine/clean_data.py`) — получаем
   `*_clean.json` / `*_clean.npy`.
4. Скачать оффлайн-артефакты для air-gap:
   - модели Ollama: `ollama pull bge-m3` и `ollama pull qwen2.5:7b`
     (затем перенести `~/.ollama/models` в контур);
   - python-зависимости (`engine/requirements.txt`) — собрать в локальное
     зеркало / `pip download` для офлайн-установки.

---

## 3. Установка в контуре КИИ (БЕЗ интернета)

1. Перенести в контур: репозиторий, готовую папку `data/`, веса моделей Ollama,
   офлайн-набор pip-пакетов и (при использовании Docker) базовые образы
   `python:3.11-slim` и `qdrant/qdrant` через `docker save`/`docker load`.
2. Поднять Ollama на хосте и убедиться, что модели на месте:
   ```bash
   ollama list        # должны быть bge-m3 и qwen2.5:7b
   curl http://127.0.0.1:11434/api/tags
   ```
3. Настроить окружение:
   ```bash
   cp .env.example .env
   # для прода КИИ оставить: RETRIEVER=semantic, LLM_BACKEND=ollama,
   # OLLAMA_HOST=http://host.docker.internal:11434
   ```
4. Запуск через Docker Compose (контекст сборки = корень репозитория):
   ```bash
   docker compose build
   docker compose up -d
   docker compose ps        # sds должен стать healthy (healthcheck на /health)
   ```
   С опциональной Qdrant:
   ```bash
   docker compose --profile qdrant up -d   # при RETRIEVER=qdrant
   ```

### Альтернатива без Docker (прямой запуск)

```bash
cd engine
CORPUS_FILE=corpus_full_clean.json EMB_FILE=embeddings_clean.npy \
IDS_FILE=embed_ids_clean.json SUBS_FILE=substances_clean.json \
RETRIEVER=semantic LLM_BACKEND=ollama OLLAMA_HOST=http://127.0.0.1:11434 \
python3 -m uvicorn service:app --host 0.0.0.0 --port 8000
```
(При прямом запуске Ollama на той же машине — `OLLAMA_HOST=http://127.0.0.1:11434`,
без `host.docker.internal`.)

---

## 4. Проверка работоспособности

```bash
curl http://127.0.0.1:8000/health
# {"ok": true, "retriever": "semantic", "llm_backend": "ollama", ...}

curl -s -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"как хранить серную кислоту"}'

curl -s "http://127.0.0.1:8000/substance/серная%20кислота"
```

---

## 5. Офлайн-гарантия / air-gap

**Тезис: на рантайме сервис обращается ТОЛЬКО к локальным сервисам —
к Ollama на хосте (порт 11434) и опционально к локальному Qdrant.
Никаких внешних/облачных вызовов рантайм не делает.**

### 5.1. Подтверждение по коду

Прогон по всем модулям движка (`grep -nE "urlopen|requests|httpx|https?://" engine/*.py`)
даёт следующую картину сетевых вызовов:

**Рантайм (используется при работе сервиса) — только localhost:**

| Файл | Куда обращается | Внешний? |
|------|-----------------|----------|
| `engine/backends.py` (`OllamaEmbedding`, `OllamaLLM`) | `OLLAMA_HOST` → `host.docker.internal` / `localhost:11434` | НЕТ |
| `engine/retriever.py` (`SemanticRetriever._embed`) | `OLLAMA_HOST` → `127.0.0.1:11434` | НЕТ |
| `engine/qdrant_index.py` | `QDRANT_PATH` (embedded) / локальный Qdrant; эмбеддинги через `OLLAMA_HOST` | НЕТ |
| `engine/reranker_llm.py` | локальный Ollama (`OLLAMA_HOST`) | НЕТ |

**Внешние хосты — есть, но ВНЕ рантайм-пути:**

| Файл | Внешний хост | Когда вызывается |
|------|--------------|------------------|
| `engine/fetch_pubchem.py` | `pubchem.ncbi.nlm.nih.gov` | этап подготовки данных, не рантайм |
| `engine/fetch_idlh.py` | `www.cdc.gov` | этап подготовки данных, не рантайм |
| `engine/fetch_synonyms.py` | `www.wikidata.org` | этап подготовки данных, не рантайм |
| `engine/backends.py` (`OpenRouterEmbedding`) | `openrouter.ai` | облачный бэкенд бенчмарка; в КИИ НЕ включается |
| `engine/backends.py` (`GigaChatEmbedding`) | `gigachat.devices.sberbank.ru` | РФ-облачный бэкенд; в КИИ НЕ включается |

Замечания:
- **`fetch_*.py`** — это этап сборки данных (раздел 2), выполняется ОДИН раз на
  машине с интернетом. В контур КИИ переносится только готовый `data/`; сами
  `fetch_*.py` на рантайме сервиса не импортируются и не вызываются.
- **OpenRouter / GigaChat** — облачные бэкенды эмбеддингов для бенчмарка качества
  (`get_embedding_backend("openrouter"|"gigachat")`). Активируются только явным
  выбором и требуют API-ключей. В проде КИИ выбирается `RETRIEVER=semantic` +
  `LLM_BACKEND=ollama`, эти классы не инстанцируются. В air-gap дополнительно
  гарантируется отсутствием исходящего трафика (см. чеклист).
- Остальные совпадения `https?://` в `engine/*.py` относятся к `eval_*`-скриптам
  (оценка качества вне рантайма) — на боевом пути сервиса не задействованы.

### 5.2. Чеклист проверки офлайн-режима

Цель — доказать, что `/ask` и `/substance` работают при полностью
заблокированном исходящем трафике (всё идёт через локальный Ollama).

1. **Заблокировать исходящий трафик** на хосте сервиса (оставив только loopback
   и, при контейнере, мост к хосту для порта 11434). Примеры (Linux, осторожно):
   ```bash
   # Разрешить только loopback и установленные соединения, остальной OUTPUT — DROP.
   # Адаптируйте под свою сетевую политику; проверяйте на стенде, не на проде вслепую.
   sudo iptables -A OUTPUT -o lo -j ACCEPT
   sudo iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
   sudo iptables -A OUTPUT -j DROP
   ```
   Либо физически отключить сетевой интерфейс (для финальной приёмки в КИИ).
2. **Убедиться, что внешка недоступна** (должно ОТВАЛИТЬСЯ по таймауту/ошибке):
   ```bash
   curl -m 5 https://pubchem.ncbi.nlm.nih.gov   # ожидаем сбой соединения
   curl -m 5 https://openrouter.ai              # ожидаем сбой соединения
   ```
3. **Локальный Ollama доступен:**
   ```bash
   curl http://127.0.0.1:11434/api/tags         # 200 OK, список моделей
   ```
4. **Сервис здоров:**
   ```bash
   curl http://127.0.0.1:8000/health            # {"ok": true, "llm_backend": "ollama", ...}
   ```
5. **`/ask` работает (генерация через локальный Ollama):**
   ```bash
   curl -s -X POST http://127.0.0.1:8000/ask \
     -H 'Content-Type: application/json' \
     -d '{"question":"антидот при отравлении цианидом"}'
   # Ожидаем содержательный grounded-ответ со ссылками ИЛИ честный отказ —
   # БЕЗ ошибок сетевого доступа во внешку.
   ```
6. **`/substance` работает:**
   ```bash
   curl -s "http://127.0.0.1:8000/substance/серная%20кислота"
   ```
7. **Зафиксировать**, что в системных логах хоста за время теста нет исходящих
   соединений к внешним адресам (только `:11434` и при наличии Qdrant `:6333`).

Если шаги 5–6 проходят при заблокированной внешке — офлайн-гарантия подтверждена:
весь рантайм-путь замкнут на локальный Ollama (и опц. локальный Qdrant).
