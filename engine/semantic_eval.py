# -*- coding: utf-8 -*-
"""
Семантический retrieval (bge-m3) поверх проиндексированной базы + тот же eval-набор.
Сравнение с лексическим гибридом на полном масштабе. Запуск на машине Ильи (Ollama локально).
Требует: сначала прогнать build_semantic_index.py.
"""
import json, os, time, urllib.request
import numpy as np
from evaluate import TESTS, PLANT_SCOPE

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "..", "data")
OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"); MODEL = os.getenv("EMBED_MODEL", "bge-m3")

def embed(text):
    req = urllib.request.Request(f"{OLLAMA}/api/embeddings",
        data=json.dumps({"model": MODEL, "prompt": text}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["embedding"]

def main():
    chunks = json.load(open(os.path.join(DATA, "corpus_full.json"), encoding="utf-8"))["chunks"]
    M = np.load(os.path.join(DATA, "embeddings.npy")).astype(np.float32)
    chunks = chunks[:len(M)]
    Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    subs = [c["substance"] for c in chunks]; secs = [c["section"] for c in chunks]

    def search(q, k=3):
        qv = np.asarray(embed(q), dtype=np.float32); qv /= (np.linalg.norm(qv) + 1e-9)
        sims = Mn @ qv
        idx = sims.argsort()[::-1][:k]
        return [(chunks[i], float(sims[i])) for i in idx]

    h1 = h3 = sec = pl_ok = pl_n = subj = 0; lat = []
    print("=" * 76)
    for q, exp, kw in TESTS:
        t = time.time(); res = search(q, 3); lat.append((time.time() - t) * 1000)
        top = res[0][0]
        if q in PLANT_SCOPE:
            pl_n += 1; ok = top["substance"] in PLANT_SCOPE[q]; pl_ok += ok
            print(f"[{'OK ' if ok else 'MISS'}|PLANT] {q[:40]:40} -> {top['substance']}"); continue
        subj += 1
        in3 = any(c["substance"] == exp for c, _ in res); ok1 = top["substance"] == exp
        h1 += ok1; h3 += in3
        seck = (kw is None) or (kw.lower() in top["section"].lower())
        if ok1 and seck: sec += 1
        flag = "OK " if ok1 else ("~3 " if in3 else "MISS")
        print(f"[{flag}] {q[:46]:46} -> {top['substance']} / {top['section'][:22]}")
    print("=" * 76)
    print(f"СЕМАНТИКА (bge-m3) на полной базе {len(chunks)} чанков:")
    print(f"Вещество top-1:        {h1}/{subj} = {h1/subj:.0%}   (лексика на масштабе была 60%)")
    print(f"Вещество top-3:        {h3}/{subj} = {h3/subj:.0%}   (лексика 84%)")
    print(f"Вещество+раздел top-1: {sec}/{subj} = {sec/subj:.0%}   (лексика 52%)")
    print(f"Плант-скоуп top-1:     {pl_ok}/{pl_n} = {pl_ok/pl_n:.0%}")
    print(f"Latency: median {sorted(lat)[len(lat)//2]:.0f} ms (вкл. вызов Ollama)")

if __name__ == "__main__":
    main()
