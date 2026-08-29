"""Общая обвязка офлайн-сьюта.

Инвариант, который защищает весь набор: тесты должны проходить у любого, кто просто
склонировал репозиторий — без Ollama, без сети, без собранного семантического индекса.
Поэтому здесь: (1) песочница сокетов — исходящая сеть физически запрещена, (2) окружение
переводится в лексический режим, (3) engine/ добавляется в sys.path (сервис запускается
через `--app-dir engine`, у пакета нет __init__).
"""
import os
import socket
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "engine")
DATA = os.path.join(ROOT, "data")

if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)

# Лексический режим по умолчанию: без модели и без эмбеддингов.
os.environ.setdefault("SUBS_FILE", "substances_clean.json")
os.environ.setdefault("CORPUS_FILE", "corpus_full_clean.json")
os.environ.setdefault("RETRIEVER", "lexical")
os.environ.setdefault("LLM_BACKEND", "extractive")
os.environ.setdefault("RERANK", "0")
# Заведомо мёртвый адрес: если код всё же полезет в Ollama, он должен деградировать, а не висеть.
os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:59999")


class NetworkBlocked(RuntimeError):
    """Тест попытался выйти в сеть. В офлайн-сьюте это дефект, а не среда."""


@pytest.fixture(autouse=True, scope="session")
def _no_network():
    """Запрещает исходящие соединения на всю сессию (loopback разрешён — TestClient локальный)."""
    real_connect = socket.socket.connect

    def guarded(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in ("127.0.0.1", "::1", "localhost"):
            raise NetworkBlocked(f"исходящее соединение запрещено в офлайн-сьюте: {address}")
        return real_connect(self, address, *args, **kwargs)

    socket.socket.connect = guarded
    yield
    socket.socket.connect = real_connect


def _require(path):
    if not os.path.exists(path):
        pytest.skip(f"нет файла данных {os.path.basename(path)} — сьют данных пропущен")
    return path


@pytest.fixture(scope="session")
def substances():
    import json
    with open(_require(os.path.join(DATA, "substances_clean.json")), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def client():
    """FastAPI TestClient в лексическом режиме. Пропускается, если стек не установлен."""
    pytest.importorskip("fastapi")
    starlette_testclient = pytest.importorskip("starlette.testclient")
    _require(os.path.join(DATA, "corpus_full_clean.json"))
    import service
    return starlette_testclient.TestClient(service.app)
