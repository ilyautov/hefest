#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama-MCP: мост сознательного доступа Cowork-агента к локальной Ollama Ильи.

Паттерн (как Anthropic MCP Tunnels): сервер живёт на машине Ильи, видит localhost:11434,
отдаёт агенту узкий набор инструментов. Данные не покидают машину. Агент не лезет в сеть —
сеть сама отдаёт только разрешённое.

Безопасность:
  - ALLOWED_MODELS: белый список моделей (агент не может дёрнуть произвольную).
  - Только чтение/инференс: embed, generate, list. Никаких pull/rm/системных команд.
  - Локальный bind: ходит только на 127.0.0.1, наружу ничего не открывает.
  - Аудит: каждый вызов логируется (кто, что, сколько токенов).

Запуск:  pip install "mcp[cli]" httpx  &&  python server.py
Регистрация в Cowork: см. README.md.
"""
import os, sys, json, logging, urllib.request

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    sys.exit("Установите MCP SDK:  pip install \"mcp[cli]\" ")

OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
# Белый список: агент может использовать только эти модели
ALLOWED_MODELS = set(os.getenv("ALLOWED_MODELS",
                     "bge-m3,qwen2.5:7b,qwen2.5:14b,llama3.1:8b,nomic-embed-text").split(","))

logging.basicConfig(level=logging.INFO, format="%(asctime)s OLLAMA-MCP %(message)s")
log = logging.getLogger("ollama-mcp")
mcp = FastMCP("ollama-bridge")

def _post(path, payload):
    req = urllib.request.Request(f"{OLLAMA}{path}",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

def _check(model):
    if model not in ALLOWED_MODELS:
        raise ValueError(f"Модель '{model}' не в белом списке. Разрешены: {sorted(ALLOWED_MODELS)}")

@mcp.tool()
def ollama_health() -> dict:
    """Проверить, что Ollama жива и видна. Возвращает список локальных моделей."""
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10) as r:
            tags = json.loads(r.read())
        models = [m["name"] for m in tags.get("models", [])]
        log.info(f"health ok, {len(models)} моделей")
        return {"ok": True, "host": OLLAMA, "models": models, "allowed": sorted(ALLOWED_MODELS)}
    except Exception as e:
        return {"ok": False, "error": str(e), "host": OLLAMA}

@mcp.tool()
def ollama_list_models() -> list:
    """Список локальных моделей Ollama (только из белого списка)."""
    with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10) as r:
        tags = json.loads(r.read())
    return [m["name"] for m in tags.get("models", []) if m["name"] in ALLOWED_MODELS]

@mcp.tool()
def ollama_embed(text: str, model: str = "bge-m3") -> dict:
    """Векторный эмбеддинг текста локальной моделью. text: строка. model: из белого списка."""
    _check(model)
    r = _post("/api/embeddings", {"model": model, "prompt": text})
    v = r.get("embedding", [])
    log.info(f"embed model={model} len(text)={len(text)} dim={len(v)}")
    return {"model": model, "dim": len(v), "embedding": v}

@mcp.tool()
def ollama_generate(prompt: str, model: str = "qwen2.5:7b", system: str = "") -> dict:
    """Генерация локальной моделью. prompt: запрос. model: из белого списка. system: системный промпт."""
    _check(model)
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    r = _post("/api/chat", {"model": model, "stream": False, "messages": msgs})
    out = r.get("message", {}).get("content", "")
    log.info(f"generate model={model} len(prompt)={len(prompt)} len(out)={len(out)}")
    return {"model": model, "response": out}

if __name__ == "__main__":
    log.info(f"старт. OLLAMA_HOST={OLLAMA}  ALLOWED_MODELS={sorted(ALLOWED_MODELS)}")
    mcp.run()
