# -*- coding: utf-8 -*-
"""
LLM-реранкер на локальной Ollama (без скачивания моделей с HF — air-gapped-friendly).
Listwise: даём вопрос + N пронумерованных фрагментов, модель возвращает порядок номеров
от самого релевантного. temperature 0. Тот же интерфейс .rerank(query, candidates, top_k),
что у кросс-энкодера -> взаимозаменяемы в SemanticRetriever.

Кросс-энкодер (bge-reranker-v2-m3) точнее и быстрее на инференсе, но требует HF-загрузки;
LLM-реранкер работает на уже поднятой модели (qwen2.5/gemma3) там, где HF недоступен.
"""
import os, json, re, urllib.request

HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.getenv("RERANK_LLM", "qwen2.5:7b")

SYS = ("Ты ранжируешь фрагменты паспортов безопасности по релевантности вопросу. "
       "Верни ТОЛЬКО JSON-массив номеров фрагментов от самого релевантного к менее релевантному, "
       "например [3,1,2]. Без пояснений, без текста вокруг.")

class LLMReranker:
    def __init__(self, host=HOST, model=MODEL, snippet=220):
        self.host, self.model, self.snippet = host, model, snippet

    def _chat(self, prompt):
        req = urllib.request.Request(f"{self.host}/api/chat",
            data=json.dumps({"model": self.model, "stream": False, "options": {"temperature": 0},
                "messages": [{"role": "system", "content": SYS},
                             {"role": "user", "content": prompt}]}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["message"]["content"]

    def rerank(self, query, candidates, top_k=3, text_key="text"):
        if not candidates:
            return []
        lines = []
        for i, c in enumerate(candidates, 1):
            txt = c[text_key][:self.snippet].replace("\n", " ")
            lines.append(f'{i}. [{c.get("substance","?")} / {c.get("section","?")}] {txt}')
        prompt = (f"Вопрос: {query}\n\nФрагменты:\n" + "\n".join(lines) +
                  f"\n\nВерни JSON-массив номеров (1..{len(candidates)}) по убыванию релевантности.")
        order = self._parse(self._chat(prompt), len(candidates))
        # псевдо-скор по убыванию ранга; хвост (не упомянутые) — в исходном порядке косинуса
        ranked = [candidates[i] for i in order]
        ranked += [c for j, c in enumerate(candidates) if j not in set(order)]
        n = len(ranked)
        return [(c, float(n - r)) for r, c in enumerate(ranked[:top_k])]

    @staticmethod
    def _parse(txt, n):
        m = re.search(r"\[[\d,\s]+\]", txt)
        if not m:
            return list(range(n))                       # фолбэк: исходный косинус-порядок
        try:
            arr = json.loads(m.group(0))
        except Exception:
            return list(range(n))
        seen, out = set(), []
        for x in arr:
            i = int(x) - 1                              # 1-based -> 0-based
            if 0 <= i < n and i not in seen:
                seen.add(i); out.append(i)
        return out or list(range(n))

_SINGLETON = None
def get_reranker():
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = LLMReranker()
    return _SINGLETON
