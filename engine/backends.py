# -*- coding: utf-8 -*-
"""
Сменные бэкенды эмбеддингов и генерации (вендор-нейтральность = отстройка).
Дефолт песочницы/демо: лексический (офлайн, без ключей).
Прод on-prem: Ollama на железе завода (данные не уходят).
Опции: OpenRouter (бенчмарк качества), GigaChat (РФ-облако под РФРИТ).
Все сетевые бэкенды реализованы по реальной форме API, но не вызываются в песочнице.
"""
import os, json, hashlib, urllib.request

# ---------- Эмбеддинги ----------
class EmbeddingBackend:
    def embed(self, texts): raise NotImplementedError

class OllamaEmbedding(EmbeddingBackend):
    """On-prem. Данные не покидают машину. Модель по умолчанию bge-m3 (сильный русский).
    Хост по умолчанию берётся из env OLLAMA_HOST (важно в контейнере: внутри
    Docker `localhost` указывает на сам контейнер, а Ollama живёт на хосте железа —
    тогда OLLAMA_HOST=http://host.docker.internal:11434). Локально без контейнера
    дефолт остаётся http://localhost:11434."""
    def __init__(self, host=None, model="bge-m3"):
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = model
    def embed(self, texts):
        out = []
        for t in texts:
            req = urllib.request.Request(
                f"{self.host}/api/embeddings",
                data=json.dumps({"model": self.model, "prompt": t}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                out.append(json.loads(r.read())["embedding"])
        return out

class OpenRouterEmbedding(EmbeddingBackend):
    """Бенчмарк качества. Данные уходят к провайдеру — НЕ для КИИ-контура."""
    def __init__(self, model="openai/text-embedding-3-small", key=None):
        self.model = model; self.key = key or os.getenv("OPENROUTER_API_KEY")
    def embed(self, texts):
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/embeddings",
            data=json.dumps({"model": self.model, "input": texts}).encode(),
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return [d["embedding"] for d in json.loads(r.read())["data"]]

class GigaChatEmbedding(EmbeddingBackend):
    """РФ-облако, реестровое ПО (под субсидию РФРИТ). OAuth + /embeddings."""
    def __init__(self, token=None, base="https://gigachat.devices.sberbank.ru/api/v1"):
        self.token = token or os.getenv("GIGACHAT_TOKEN"); self.base = base
    def embed(self, texts):
        req = urllib.request.Request(
            f"{self.base}/embeddings",
            data=json.dumps({"model": "Embeddings", "input": texts}).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return [d["embedding"] for d in json.loads(r.read())["data"]]

# ---------- Генерация (grounded, строго по контексту) ----------
SYSTEM = ("Ты помощник по промышленной безопасности. Отвечай СТРОГО по предоставленным "
          "разделам паспортов безопасности. Каждое утверждение сопровождай ссылкой на вещество и раздел. "
          "Если в контексте нет ответа — честно скажи 'в базе нет данных', не выдумывай. "
          "Цена ошибки — здоровье человека.")

def build_prompt(question, passages):
    ctx = "\n\n".join(f"[{i+1}] {p['citation']}:\n{p['text']}" for i, p in enumerate(passages))
    return (f"Контекст (разделы паспортов безопасности):\n{ctx}\n\n"
            f"Вопрос: {question}\n\nОтвет строго по контексту, со ссылками [N]:")

class LLMBackend:
    def generate(self, question, passages): raise NotImplementedError

class OllamaLLM(LLMBackend):
    # Хост по умолчанию из env OLLAMA_HOST (см. примечание в OllamaEmbedding):
    # в контейнере это http://host.docker.internal:11434, локально — http://localhost:11434.
    def __init__(self, host=None, model="qwen2.5:7b"):
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = model
        self._fallback = ExtractiveLLM()  # деградация: Ollama упал -> grounded-выжимка из паспорта
    def generate(self, question, passages):
        if not passages:
            return "В базе нет данных по этому запросу. Сверьтесь с действующим паспортом безопасности."
        # temperature 0 -> детерминированно и максимально по контексту (safety: цена ошибки = здоровье).
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps({"model": self.model, "stream": False,
                "options": {"temperature": 0},
                "messages": [{"role":"system","content":SYSTEM},
                             {"role":"user","content":build_prompt(question, passages)}]}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())["message"]["content"]
        except Exception as e:
            # Ollama недоступен/таймаут -> НЕ роняем запрос: отдаём grounded-выжимку из найденных разделов.
            # Безопасно: extractive не выдумывает, отдаёт ровно текст паспорта. Помечаем деградацию.
            print(f"[backends] Ollama недоступен ({type(e).__name__}: {e}) -> extractive-fallback")
            return ("⚠ Генеративная модель временно недоступна — ответ собран напрямую из разделов паспорта.\n\n"
                    + self._fallback.generate(question, passages))

class ExtractiveLLM(LLMBackend):
    """Бэкенд без модели (песочница/демо): собирает grounded-ответ из найденных разделов с цитатами.
    Честный fallback, нулевой риск галлюцинаций — отдаёт ровно то, что в базе."""
    def generate(self, question, passages):
        if not passages:
            return "В базе нет данных по этому запросу. Сверьтесь с действующим паспортом безопасности."
        p = passages[0]
        ans = f"По данным базы:\n\n{p['text']}\n\nИсточник: {p['citation']}."
        if len(passages) > 1:
            ans += f"\n\nСмежные разделы: " + "; ".join(x['citation'] for x in passages[1:])
        return ans

def get_embedding_backend(name="lexical"):
    return {"ollama":OllamaEmbedding, "openrouter":OpenRouterEmbedding, "gigachat":GigaChatEmbedding}.get(name, None)

def get_llm_backend(name="extractive", **kw):
    return {"ollama":OllamaLLM, "extractive":ExtractiveLLM}.get(name, ExtractiveLLM)(**kw) if name!="ollama" else OllamaLLM(**kw)
