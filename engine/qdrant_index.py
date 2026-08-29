# -*- coding: utf-8 -*-
"""
Qdrant как прод-векторная БД (зрелость сервиса). Локальный режим (on-disk, без Docker-сервера) —
тот же код, что для серверного Qdrant, меняется только URL. Плант-скоуп здесь = НАСТОЯЩИЙ
metadata-фильтр (payload.substance IN scope), а не доп. к скору: чище и масштабируемее numpy.

Билд:   python3 qdrant_index.py                          # из embeddings.npy + corpus_full.json
        EMB_FILE=embeddings_clean.npy CORPUS_FILE=corpus_full_clean.json python3 qdrant_index.py
Поиск:  класс QdrantRetriever (тот же .query(q, k, scope_substances), что у SemanticRetriever).
"""
import json, os, urllib.request
import numpy as np
from qdrant_client import QdrantClient, models

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "..", "data")
QPATH = os.getenv("QDRANT_PATH", os.path.join(DATA, "qdrant_local"))
COLL = os.getenv("QDRANT_COLLECTION", "sds")
OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"); EMODEL = os.getenv("EMBED_MODEL", "bge-m3")

def build():
    emb = np.load(os.path.join(DATA, os.getenv("EMB_FILE", "embeddings_clean.npy"))).astype(np.float32)
    chunks = json.load(open(os.path.join(DATA, os.getenv("CORPUS_FILE", "corpus_full_clean.json")), encoding="utf-8"))["chunks"]
    chunks = chunks[:len(emb)]
    cli = QdrantClient(path=QPATH)
    cli.recreate_collection(COLL, vectors_config=models.VectorParams(
        size=emb.shape[1], distance=models.Distance.COSINE))
    B = 1000
    for i in range(0, len(chunks), B):
        pts = [models.PointStruct(id=j, vector=emb[j].tolist(),
                  payload={"substance": chunks[j]["substance"], "section": chunks[j]["section"],
                           "citation": chunks[j]["citation"], "text": chunks[j]["text"]})
               for j in range(i, min(i + B, len(chunks)))]
        cli.upsert(COLL, points=pts)
        print(f"  upsert {min(i+B,len(chunks))}/{len(chunks)}", flush=True)
    print(f"готово: коллекция '{COLL}' в {QPATH} ({len(chunks)} точек)")

class QdrantRetriever:
    """Тот же интерфейс, что SemanticRetriever, но поверх Qdrant. Плант-скоуп = payload-фильтр."""
    def __init__(self, path=QPATH, collection=COLL, host=OLLAMA, model=EMODEL):
        self.cli = QdrantClient(path=path); self.coll = collection
        self.host, self.model = host, model
        from retriever import HybridRetriever
        self._scoper = HybridRetriever(lexical=False)   # переиспользуем _plant_scope/plant_triggers
        self.plant_triggers = self._scoper.plant_triggers; self.plants = self._scoper.plants
        self.subs = self._scoper.subs; self.chunks = self._scoper.chunks

    def _embed(self, text):
        req = urllib.request.Request(f"{self.host}/api/embed",
            data=json.dumps({"model": self.model, "input": [text]}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["embeddings"][0]

    def _plant_scope(self, ql): return self._scoper._plant_scope(ql)

    def query(self, q, k=3, scope_substances=None):
        qv = self._embed(q)
        scope = scope_substances or self._plant_scope(q.lower())
        flt = None
        if scope is not None:
            flt = models.Filter(must=[models.FieldCondition(
                key="substance", match=models.MatchAny(any=list(scope)))])
        resp = self.cli.query_points(self.coll, query=qv, limit=k, query_filter=flt)
        return [(h.payload, float(h.score)) for h in resp.points]

if __name__ == "__main__":
    build()
