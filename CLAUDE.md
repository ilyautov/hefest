# HEFEST — инструкции проекта

On-prem RAG-ассистент по российским паспортам безопасности химвеществ (ГОСТ 30333-2022).
Рабочее имя репозитория — `rag-sds`. Имя продукта/бренд — **HEFEST** (см. `BRAND.md`).

## ⚠️ Святое правило (safety-critical) — НЕ нарушать

Цена ошибки = здоровье человека. **Никогда не выдумывать нормативку** (ПДК, ОБУВ, IDLH, ФККО,
номера ООН, классы опасности, разделы/названия ГОСТ, первую помощь, GHS). Каждое значение —
из авторитетного источника, **с провенансом**, помечено `needs_review` до подписи эксперта завода.
При локализации описаний **числа и единицы НЕ пересчитывать** (°F не → °C). Где данных нет — писать
«нет данных», а не додумывать. Даты пересмотра паспортов не синтезировать.

## Запуск сервиса (порт 8012, без `--reload` — после правок кода нужен рестарт)

Лексический режим (быстро, без Ollama):
```bash
SUBS_FILE=substances_clean.json CORPUS_FILE=corpus_full_clean.json LLM_BACKEND=extractive \
python3 -m uvicorn service:app --app-dir engine --port 8012
```
Семантический режим (нужны эмбеддинги + Ollama bge-m3 и qwen2.5:7b):
```bash
SUBS_FILE=substances_clean.json CORPUS_FILE=corpus_full_clean.json \
RETRIEVER=semantic EMB_FILE=embeddings_clean.npy IDS_FILE=embed_ids_clean.json \
LLM_BACKEND=ollama OLLAMA_LLM=qwen2.5:7b python3 -m uvicorn service:app --app-dir engine --port 8012
```
Здоровье: `GET /health`. Остановить: `pkill -f "uvicorn service:app"`.

## Стек

FastAPI (~37 эндпоинтов), 12 HTML-экранов (каждый со своим `<style>`). Ретриверы: lexical /
semantic (numpy `embeddings_clean.npy`) / qdrant. Эмбеддинги **bge-m3** (1024) через Ollama,
генерация **qwen2.5:7b**, опц. реранкер cross-encoder. Всё on-prem/офлайн (152-ФЗ, КИИ/187-ФЗ).

## Git / GitHub / LFS

- Remote: `git@github.com:ilyautov/hefest.git` (приватный), основная ветка `main`.
- **Коммитить/пушить только по явной просьбе.** На default-ветке — сначала ветка. Сообщения
  коммитов завершать строкой `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Push требует сети — в этом окружении sandbox её режет, нужен `dangerouslyDisableSandbox`.
- **Git LFS**: `data/embeddings_clean.npy` (~106 МБ) хранится через LFS (`.gitattributes`);
  остальные `*.npy`, Qdrant-индекс, `.bak`, кэши, `.env`, `.claude/` — в `.gitignore`.
- Клон под ключ: `git lfs install && git clone … && git lfs pull`. Без LFS — `bash rebuild_index.sh`
  (пересборка индекса из корпуса через Ollama). Подробно — `КЛОН.md`.

## Данные (живые счётчики /health, /quality)

2597 веществ, 25970 разделов-чанков, 13 заводов. Корпус: реальные регуляторные значения
(ГН 2.2.5/СанПиН), форма паспорта сгенерирована. Полнота честная и градуированная: passport 52 /
baseline 2545, needs_review 2546 — это фича (не маскируем типовое под паспортное).

## Рабочие договорённости

- Русскоязычный пользователь — общаться по-русски.
- Хронику вести в `WORKLOG.md`, заметные изменения — в `CHANGELOG.md`.
- UI/вёрстку проверять реально: Playwright-скриншоты глушит таймаут харнесса → снимать через
  headless Chrome (`/Applications/Google Chrome.app/...`), причём на macOS окно Chrome не уже ~450px
  (для мобайла мерить через Playwright `getBoundingClientRect`, а не пиксельный скрин узкого окна).

## Ключевые доки

`README.md` · `docs/О-СИСТЕМЕ.md` (заказчику) · `docs/АРХИТЕКТУРА.md` (схемы) ·
`docs/ВЛАДЕЛЬЦУ-полная-дока.md` (внутр.) · `BRAND.md` · `MARKET.md` · `docs/ДОМЕН-для-предпринимателя.md` ·
`docs/КЕЙС-HEFEST.md` / `docs/КАРТОЧКА-ХЛОР.md` (лендинг) · `КЛОН.md` (клон/запуск).
