# -*- coding: utf-8 -*-
"""
Семантическая индексация полной базы через ЛОКАЛЬНУЮ Ollama (bge-m3).
Запускается на машине Ильи (Ollama на localhost). Не через MCP-чат: 26к эмбеддингов
гонятся напрямую в Ollama, с прогрессом и чекпойнтом.

Выход: data/embeddings.npy (float32, N x 1024) + data/embed_ids.json (порядок чанков).
Запуск:  python3 build_semantic_index.py            # вся база
         python3 build_semantic_index.py --limit 480   # только showcase (быстро)
"""
import json, os, sys, time, argparse, urllib.request
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "..", "data")
OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.getenv("EMBED_MODEL", "bge-m3")
BATCH = int(os.getenv("EMBED_BATCH", "64"))
SAVE_EVERY = int(os.getenv("EMBED_SAVE_EVERY", "1600"))  # чекпойнт на диск реже, чем печать прогресса

def embed_batch(texts):
    # /api/embed (батч): один HTTP-вызов на пачку текстов, GPU считает пачкой.
    # Вектора нормированные (|v|=1); направление идентично старому /api/embeddings (cos=1).
    req = urllib.request.Request(f"{OLLAMA}/api/embed",
        data=json.dumps({"model": MODEL, "input": texts}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["embeddings"]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=0); a = ap.parse_args()
    corpus_file = os.getenv("CORPUS_FILE", "corpus_full_clean.json")   # параметризовано: clean-реиндекс в отд. файлы
    chunks = json.load(open(os.path.join(DATA, corpus_file), encoding="utf-8"))["chunks"]
    if a.limit: chunks = chunks[:a.limit]
    n = len(chunks)
    emb_path = os.path.join(DATA, os.getenv("EMB_FILE", "embeddings_clean.npy"))
    ids_path = os.path.join(DATA, os.getenv("IDS_FILE", "embed_ids_clean.json"))

    # резюмирование с чекпойнта (только если он уже нормированный — батч-формат)
    start = 0; vecs = None
    if os.path.exists(emb_path) and os.path.exists(ids_path):
        done_ids = json.load(open(ids_path, encoding="utf-8"))
        m = np.load(emb_path)
        normalized = m.shape[0] and abs(float(np.linalg.norm(m[0])) - 1.0) < 1e-3
        if len(done_ids) <= n and normalized:
            vecs = list(m); start = len(vecs)
            print(f"резюмирую с чекпойнта: {start}/{n}")
        elif not normalized:
            print("старый чекпойнт (сырые вектора) -> чистый пересбор на /api/embed")
    if vecs is None: vecs = []

    t0 = time.time()
    if start == 0: print(f"модель {MODEL}, батч {BATCH}, /api/embed")
    last_save = start
    for i in range(start, n, BATCH):
        batch = [c["text"] for c in chunks[i:i + BATCH]]
        vecs.extend(embed_batch(batch))
        done = len(vecs)
        if done - last_save >= SAVE_EVERY or done == n:
            np.save(emb_path, np.asarray(vecs, dtype=np.float32))
            json.dump([c["citation"] for c in chunks[:done]], open(ids_path, "w", encoding="utf-8"), ensure_ascii=False)
            last_save = done
        rate = done / (time.time() - t0 + 1e-9)
        eta = (n - done) / (rate + 1e-9)
        print(f"  {done}/{n}  {rate:.0f} эмб/с  ETA {eta/60:.1f} мин", flush=True)

    np.save(emb_path, np.asarray(vecs, dtype=np.float32))
    json.dump([c["citation"] for c in chunks], open(ids_path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"готово: {len(vecs)} векторов -> {emb_path}")

if __name__ == "__main__":
    main()
