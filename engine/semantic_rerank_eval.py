# -*- coding: utf-8 -*-
"""
Eval: семантика (bge-m3) + плант-скоуп + КРОСС-ЭНКОДЕР РЕРАНК (bge-reranker-v2-m3).
Конвейер: retrieve top-N косинусом(+скоуп) -> реранк top-N -> top-k. Цель — дотянуть
правильное вещество из top-3 в top-1. Сравнение с конфигом C (без реранка).
Требует: data/embeddings.npy + Ollama (bge-m3) + transformers (bge-reranker-v2-m3 на MPS).
Запуск:  python3 semantic_rerank_eval.py            # rerank_n=20
         RERANK_N=30 python3 semantic_rerank_eval.py
"""
import os, time
import numpy as np
from evaluate import TESTS, PLANT_SCOPE
from retriever import SemanticRetriever

BACKEND = os.getenv("RERANK_BACKEND", "crossencoder")  # crossencoder (bge-reranker-v2-m3) | llm (Ollama)

def main():
    rerank_n = int(os.getenv("RERANK_N", "20" if BACKEND == "crossencoder" else "10"))
    if BACKEND == "llm":
        from reranker_llm import LLMReranker
        rk = LLMReranker(); tag = f"LLM-реранк ({rk.model})"
    else:
        from reranker_model import CrossEncoderReranker
        rk = CrossEncoderReranker(); tag = "bge-reranker-v2-m3"
    r = SemanticRetriever(reranker=rk, rerank_n=rerank_n)

    h1 = h3 = sec = pl_ok = pl_n = subj = 0; lat = []
    print("=" * 78)
    for q, exp, kw in TESTS:
        t = time.time(); res = r.query(q, 3); lat.append((time.time() - t) * 1000)
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
    print("=" * 78)
    print(f"СЕМАНТИКА + ПЛАНТ-СКОУП + РЕРАНК ({tag}, N={rerank_n}) на {len(r.chunks)} чанках:")
    print(f"Вещество top-1:        {h1}/{subj} = {h1/subj:.0%}   (без реранка 84%)")
    print(f"Вещество top-3:        {h3}/{subj} = {h3/subj:.0%}   (без реранка 96%)")
    print(f"Вещество+раздел top-1: {sec}/{subj} = {sec/subj:.0%}   (без реранка 64%)")
    print(f"Плант-скоуп top-1:     {pl_ok}/{pl_n} = {pl_ok/pl_n:.0%}   (без реранка 100%)")
    print(f"Latency: median {sorted(lat)[len(lat)//2]:.0f} ms (вкл. Ollama + реранк на MPS)")

if __name__ == "__main__":
    main()
