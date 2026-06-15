# -*- coding: utf-8 -*-
"""
Retrieval v2: исправление граблей baseline (60% top-1).
Грабля: лексический TF-IDF не справляется с русской морфологией и синонимами.
Фикс (честный, переносимый в прод):
  1. char_wb n-граммы (3-5) ловят основу слова независимо от окончания (формальдегид/формальдегида).
  2. бустинг по названию вещества и синонимам (едкий натр/каустик/щёлочь -> NaOH).
  3. взвешенная комбинация слово-уровень + символ-уровень.
В проде эти же 60% -> закрываются семантическими эмбеддингами (GigaChat / multilingual-e5).
"""
import re
import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from build_corpus import build_chunks, CORPUS
from eval_retrieval import TESTS, tokenize

# Синонимы/триггеры -> doc_id для бустинга (имитация сущностного слоя)
SYN = {
    "h2so4": ["серн", "кислот", "h2so4", "купорос"],
    "ch3oh": ["метанол", "метилов", "ch3oh", "древесн спирт"],
    "nh3": ["аммиак", "нашатыр", "nh3"],
    "c3h6o": ["ацетон", "пропанон", "c3h6o"],
    "hcho": ["формальдегид", "формалин", "hcho", "канцероген"],
    "naoh": ["натр", "едк", "каустик", "щелоч", "щёлоч", "naoh", "сода"],
}

class RetrieverV2:
    def __init__(self, chunks):
        self.chunks = chunks
        texts = [c["text"] + " " + c["substance"] + " " + c["section"] for c in chunks]
        self.word = TfidfVectorizer(tokenizer=tokenize, token_pattern=None, ngram_range=(1,2), min_df=1)
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3,5), min_df=1, lowercase=True)
        self.Wm = self.word.fit_transform(texts)
        self.Cm = self.char.fit_transform(texts)
        self.doc_ids = [c["doc_id"] for c in chunks]

    def query(self, q, k=3, w_word=0.45, w_char=0.55, boost=0.18):
        qw = self.word.transform([q]); qc = self.char.transform([q])
        s = w_word * cosine_similarity(qw, self.Wm)[0] + w_char * cosine_similarity(qc, self.Cm)[0]
        ql = q.lower()
        for di, kws in SYN.items():
            if any(kw in ql for kw in kws):
                for i, d in enumerate(self.doc_ids):
                    if d == di:
                        s[i] += boost
        idx = s.argsort()[::-1][:k]
        return [(self.chunks[i], float(s[i])) for i in idx]

if __name__ == "__main__":
    chunks = build_chunks(CORPUS)
    r = RetrieverV2(chunks)
    h1 = h3 = sec = 0
    print("=" * 72)
    for t in TESTS:
        res = r.query(t["q"], k=3); top = res[0][0]
        in3 = any(c["doc_id"] == t["doc"] for c, _ in res)
        ok1 = top["doc_id"] == t["doc"]
        h1 += ok1; h3 += in3
        sec_ok = (t["sec_kw"] is None) or (t["sec_kw"].lower() in top["section"].lower())
        if ok1 and sec_ok: sec += 1
        flag = "OK " if ok1 else ("~3 " if in3 else "MISS")
        print(f"[{flag}] {t['q'][:46]:46} -> {top['substance']} / {top['section'][:20]} ({res[0][1]:.2f})")
    n = len(TESTS)
    print("=" * 72)
    print(f"Top-1 вещество:        {h1}/{n} = {h1/n:.0%}   (baseline было 60%)")
    print(f"Top-3 вещество:        {h3}/{n} = {h3/n:.0%}   (baseline было 80%)")
    print(f"Top-1 вещество+раздел: {sec}/{n} = {sec/n:.0%}   (baseline было 50%)")
