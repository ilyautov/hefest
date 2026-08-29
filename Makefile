# HEFEST — рабочие ритуалы.
# Требуется Python 3.10–3.13 с установленным requirements/dev.txt.
PY ?= python3

.PHONY: help install test guard run run-semantic demo lint clean check

help:
	@echo "make install       — поставить зависимости базового контура + тесты"
	@echo "make test          — офлайн-сьют: без Ollama, без сети, без индекса"
	@echo "make guard         — предпубликационный сторож (секреты, .env, обезличивание)"
	@echo "make check         — guard + test + компиляция: полный прогон перед push"
	@echo "make run           — сервис на :8012 в лексическом режиме (работает из коробки)"
	@echo "make run-semantic  — сервис в семантическом режиме (нужны Ollama и эмбеддинги)"
	@echo "make demo          — обезличить реестр площадок и поднять сервис на нём"
	@echo "make clean         — убрать кэши интерпретатора"

install:
	$(PY) -m pip install -r requirements/dev.txt

# Офлайн-инвариант: мёртвый адрес Ollama гарантирует, что тесты не зависят от локальной модели.
test:
	OLLAMA_HOST=http://127.0.0.1:59999 $(PY) -m pytest tests/ -q

guard:
	sh scripts/guard.sh

check: guard
	git ls-files '*.py' | xargs -r $(PY) -m py_compile
	$(MAKE) test

# Дефолты в коде указывают на канонические clean-файлы, поэтому переменные не нужны.
run:
	$(PY) -m uvicorn service:app --app-dir engine --port 8012

run-semantic:
	RETRIEVER=semantic LLM_BACKEND=ollama OLLAMA_LLM=qwen2.5:7b \
	$(PY) -m uvicorn service:app --app-dir engine --port 8012

# Публичный показ без привязки к реальным юрлицам (см. DATA-LICENSE.md, раздел 4).
demo:
	$(PY) engine/anonymize_plants.py
	PLANTS_FILE=plants_linked_demo.json \
	$(PY) -m uvicorn service:app --app-dir engine --port 8012

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete
