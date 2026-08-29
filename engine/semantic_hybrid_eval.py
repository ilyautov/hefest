# -*- coding: utf-8 -*-
"""
Гибридный eval: семантическая база (bge-m3) + проверенные слои лексического ретривера.

Голая семантика (semantic_eval.py) даёт сильный top-1 по веществу, но теряет
плант-скоуп: запрос по площадке уезжает в созвучное вещество, а не в опасные
вещества завода. Лекарство — тот же детерминированный слой, что в retriever.py:
сущностный буст + интент раздела + scope по заводу. Здесь база заменена на
семантический косинус (прод-путь: bge-m3 + вектора), а слои переиспользованы
как есть (через HybridRetriever), с теми же коэффициентами — честная параллель.

Требует: build_semantic_index.py (data/embeddings.npy) + локальную Ollama.
"""
import json, os, time, urllib.request
import numpy as np
from evaluate import TESTS, PLANT_SCOPE
from retriever import HybridRetriever, SECTION_INTENT

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "..", "data")
OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"); MODEL = os.getenv("EMBED_MODEL", "bge-m3")

# Веса добавок. На полной базе (2601) глобальные добавки лексического гибрида
# шумят и роняют предметный top-1: сущностный буст (5-буквенные стеммы коллизируют:
# «кисло» от «кислот» ловит «кислоту») и интент раздела (+0.12 ко ВСЕМ чанкам нужного
# раздела по 2601 веществу промотирует правильный раздел НЕправильного вещества).
# Плант-скоуп безопасен: срабатывает только на плант-запросах, предметных не трогает.
# Дефолт на масштабе: только плант-скоуп. Подкрутить через env для экспериментов.
W_ENTITY = float(os.getenv("W_ENTITY", "0.0"))
W_INTENT = float(os.getenv("W_INTENT", "0.0"))
W_SCOPE_IN = float(os.getenv("W_SCOPE_IN", "0.15"))
W_SCOPE_OUT = float(os.getenv("W_SCOPE_OUT", "-0.10"))

def embed(text):
    req = urllib.request.Request(f"{OLLAMA}/api/embed",
        data=json.dumps({"model": MODEL, "input": [text]}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["embeddings"][0]

def main():
    r = HybridRetriever()                       # переиспользуем entity/plant/intent + chunks
    chunks = r.chunks
    M = np.load(os.path.join(DATA, "embeddings.npy")).astype(np.float32)
    chunks = chunks[:len(M)]
    Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    subs = np.array([c["substance"] for c in chunks])
    secs = [c["section"] for c in chunks]

    def search(q, k=3):
        ql = q.lower()
        qv = np.asarray(embed(q), dtype=np.float32); qv /= (np.linalg.norm(qv) + 1e-9)
        score = Mn @ qv                                              # семантическая база
        ents = r._entity_hits(ql)                                   # тот же сущностный слой
        intent_secs = [s for s, kws in SECTION_INTENT.items() if any(kw in ql for kw in kws)]
        scope = r._plant_scope(ql)                                  # тот же плант-скоуп
        if ents:
            score = score + W_ENTITY * np.isin(subs, list(ents))
        if intent_secs:
            score = score + W_INTENT * np.array([s in intent_secs for s in secs])
        if scope is not None:
            insc = np.isin(subs, list(scope))
            score = score + np.where(insc, W_SCOPE_IN, W_SCOPE_OUT)
        idx = score.argsort()[::-1][:k]
        return [(chunks[i], float(score[i])) for i in idx]

    h1 = h3 = sec = pl_ok = pl_n = subj = 0; lat = []
    print("=" * 78)
    for q, exp, kw in TESTS:
        t = time.time(); res = search(q, 3); lat.append((time.time() - t) * 1000)
        top = res[0][0]
        if q in PLANT_SCOPE:
            pl_n += 1; ok = top["substance"] in PLANT_SCOPE[q]; pl_ok += ok
            print(f"[{'OK ' if ok else 'MISS'}|PLANT] {q[:42]:42} -> {top['substance']}"); continue
        subj += 1
        in3 = any(c["substance"] == exp for c, _ in res); ok1 = top["substance"] == exp
        h1 += ok1; h3 += in3
        seck = (kw is None) or (kw.lower() in top["section"].lower())
        if ok1 and seck: sec += 1
        flag = "OK " if ok1 else ("~3 " if in3 else "MISS")
        print(f"[{flag}] {q[:46]:46} -> {top['substance']} / {top['section'][:24]}")
    layers = [n for n, w in [("entity", W_ENTITY), ("intent", W_INTENT), ("scope", W_SCOPE_IN)] if w]
    print("=" * 78)
    print(f"СЕМАНТИКА+СЛОИ (bge-m3 + {'+'.join(layers) or 'нет слоёв'}) на полной базе {len(chunks)} чанков:")
    print(f"Вещество top-1:        {h1}/{subj} = {h1/subj:.0%}   (голая семантика 84%, лексика 60%)")
    print(f"Вещество top-3:        {h3}/{subj} = {h3/subj:.0%}   (голая семантика 96%, лексика 84%)")
    print(f"Вещество+раздел top-1: {sec}/{subj} = {sec/subj:.0%}   (голая семантика 64%, лексика 52%)")
    print(f"Плант-скоуп top-1:     {pl_ok}/{pl_n} = {pl_ok/pl_n:.0%}   (голая семантика 33%)")
    print(f"Latency: median {sorted(lat)[len(lat)//2]:.0f} ms (вкл. вызов Ollama)")

if __name__ == "__main__":
    main()
