# -*- coding: utf-8 -*-
"""
Semantic cache для LLM-ответов (паттерн из vc.ru-разбора, адаптирован под безопасность).
L2 exact-match (hash) + L3 semantic (косинус по эмбеддингу).
КРИТИЧНО: параметрические запросы (номера партий, ID, даты) исключаются из L3 —
иначе 'партия 42' и 'партия 43' дадут один ответ. Только L2 для них.
Эмбеддер инъектируется (lexical в песочнице, Ollama/GigaChat в проде).
"""
import re, hashlib, time

PARAM_PATTERNS = [r"\b\d{3,}\b", r"\b[A-ZА-Я]{2,}\d{2,}\b", r"парти[яи]\s*\w*\d", r"№\s*\d", r"\d{2}\.\d{2}\.\d{2,4}"]

def is_parametric(q):
    return any(re.search(p, q) for p in PARAM_PATTERNS)

def _cos(a, b):
    s = sum(x*y for x, y in zip(a, b))
    na = sum(x*x for x in a) ** 0.5; nb = sum(y*y for y in b) ** 0.5
    return s / (na*nb + 1e-9)

class SemanticCache:
    def __init__(self, embed_fn=None, threshold=0.92, ttl_sec=86400):
        self.exact = {}              # hash -> (answer, ts)
        self.sem = []                # list of (vec, query, answer, ts)
        self.embed_fn = embed_fn     # callable(text)->vector, optional
        self.threshold = threshold
        self.ttl = ttl_sec
        self.stats = {"l2_hit":0, "l3_hit":0, "miss":0, "param_skip":0}

    def _key(self, q):
        return hashlib.sha256(q.strip().lower().encode()).hexdigest()

    def get(self, q):
        now = time.time()
        k = self._key(q)
        if k in self.exact and now - self.exact[k][1] < self.ttl:
            self.stats["l2_hit"] += 1
            return self.exact[k][0]
        if is_parametric(q):
            self.stats["param_skip"] += 1
            return None  # параметрический -> только L2, в L3 не идём
        if self.embed_fn:
            qv = self.embed_fn(q)
            best, ba = 0.0, None
            for vec, _, ans, ts in self.sem:
                if now - ts > self.ttl: continue
                c = _cos(qv, vec)
                if c > best: best, ba = c, ans
            if best >= self.threshold:
                self.stats["l3_hit"] += 1
                return ba
        self.stats["miss"] += 1
        return None

    def put(self, q, answer):
        self.exact[self._key(q)] = (answer, time.time())
        if self.embed_fn and not is_parametric(q):
            self.sem.append((self.embed_fn(q), q, answer, time.time()))

    def hit_rate(self):
        h = self.stats["l2_hit"] + self.stats["l3_hit"]
        tot = h + self.stats["miss"]
        return h / tot if tot else 0.0


if __name__ == "__main__":
    # Демо-эмбеддер: char-bag (только для теста логики кэша, в проде Ollama bge-m3)
    def toy_embed(t):
        v = [0]*64
        for ch in t.lower():
            v[ord(ch) % 64] += 1
        return v
    c = SemanticCache(embed_fn=toy_embed, threshold=0.97)
    c.put("как хранить серную кислоту", "ОТВЕТ_серная_хранение")
    print("точный повтор:", c.get("как хранить серную кислоту"))        # L2 hit
    print("перефраз:", c.get("как хранить  серную   кислоту"))           # L3 близко
    print("параметрический (партия 42):", c.get("брак партии 42 серная")) # param skip -> None
    print("параметрический (партия 43):", c.get("брак партии 43 серная")) # param skip -> None
    print("новый:", c.get("ПДК аммиака"))                                 # miss
    print("stats:", c.stats, "hit_rate:", round(c.hit_rate(),2))
