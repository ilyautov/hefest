# -*- coding: utf-8 -*-
"""
Retrieval поверх демо-корпуса SDS + честный eval.
TF-IDF (русская токенизация) + косинус. Baseline, который работает офлайн без ключей.
Прод-апгрейд: эмбеддинги GigaChat / multilingual-e5, гибридный реранк. Помечено в findings.
"""
import json, re, math
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from build_corpus import build_chunks, CORPUS

RU_STOP = set("и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее сейчас были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про всего них какая много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более всегда конечно всю между".split())

def tokenize(t):
    return [w for w in re.findall(r"[а-яёa-z0-9]+", t.lower()) if w not in RU_STOP and len(w) > 2]

class Retriever:
    def __init__(self, chunks):
        self.chunks = chunks
        self.vec = TfidfVectorizer(tokenizer=tokenize, token_pattern=None, ngram_range=(1,2), min_df=1)
        self.M = self.vec.fit_transform([c["text"] + " " + c["substance"] + " " + c["section"] for c in chunks])
    def query(self, q, k=3):
        qv = self.vec.transform([q])
        sims = cosine_similarity(qv, self.M)[0]
        idx = sims.argsort()[::-1][:k]
        return [(self.chunks[i], float(sims[i])) for i in idx]

# Eval: запрос -> ожидаемый doc_id (и/или раздел-ключ). Включены кросс-доковые и каверзные.
TESTS = [
    {"q": "при какой температуре вспыхивает ацетон", "doc": "c3h6o", "sec_kw": "пожар"},
    {"q": "что делать если метанол попал внутрь, антидот", "doc": "ch3oh", "sec_kw": "помощь"},
    {"q": "какие перчатки нужны для работы с ацетоном", "doc": "c3h6o", "sec_kw": "СИЗ"},
    {"q": "как хранить серную кислоту рядом с чем нельзя", "doc": "h2so4", "sec_kw": "Хранение"},
    {"q": "ПДК формальдегида в воздухе рабочей зоны", "doc": "hcho", "sec_kw": "Токсиколог"},
    {"q": "едкий натр выделяет водород с какими металлами", "doc": "naoh", "sec_kw": "пожар"},
    {"q": "первая помощь при ожоге глаз щёлочью", "doc": "naoh", "sec_kw": "помощь"},
    {"q": "какое вещество канцероген", "doc": "hcho", "sec_kw": None},
    {"q": "чем опасен аммиак при вдыхании", "doc": "nh3", "sec_kw": None},
    {"q": "куда приливать кислоту в воду или воду в кислоту", "doc": "h2so4", "sec_kw": "Хранение"},
]

if __name__ == "__main__":
    chunks = build_chunks(CORPUS)
    r = Retriever(chunks)
    hit_top1 = hit_top3 = sec_hit = 0
    print("=" * 70)
    for t in TESTS:
        res = r.query(t["q"], k=3)
        top = res[0][0]
        in3 = any(c["doc_id"] == t["doc"] for c, _ in res)
        ok1 = top["doc_id"] == t["doc"]
        hit_top1 += ok1; hit_top3 += in3
        sec_ok = (t["sec_kw"] is None) or (t["sec_kw"].lower() in top["section"].lower())
        if ok1 and sec_ok: sec_hit += 1
        flag = "OK " if ok1 else ("~3 " if in3 else "MISS")
        print(f"[{flag}] {t['q'][:48]:48} -> {top['substance']} / {top['section'][:22]} ({res[0][1]:.2f})")
    n = len(TESTS)
    print("=" * 70)
    print(f"Top-1 вещество: {hit_top1}/{n} = {hit_top1/n:.0%}")
    print(f"Top-3 вещество: {hit_top3}/{n} = {hit_top3/n:.0%}")
    print(f"Top-1 вещество+раздел: {sec_hit}/{n} = {sec_hit/n:.0%}")
