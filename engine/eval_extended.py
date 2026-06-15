# -*- coding: utf-8 -*-
"""
Расширенный eval: 25 исходных запросов + ~22 новых по verified-ядру (confidence != needs_review),
которые ещё не были покрыты. Цель — честнее метрика (README сам зовёт 28 запросов иллюстрацией).
Вопросы заземлены на реальные данные веществ (ПДК/класс/вспышка), ответ однозначен.

Пайплайн: семантика (bge-m3) + плант-скоуп (+ опц. реранк через RERANK_BACKEND).
Запуск:  python3 eval_extended.py                       # без реранка
         RERANK_BACKEND=crossencoder python3 eval_extended.py
"""
import os, time
from evaluate import TESTS, PLANT_SCOPE
from retriever import SemanticRetriever

# (запрос, ожидаемое вещество, ключевое слово раздела|None) — по verified-ядру, не дублирует TESTS
TESTS_EXT = [
    ("температура вспышки уайт-спирита", "уайт-спирит", "пожаротуш"),
    ("ПДК соляной кислоты в рабочей зоне", "соляная кислота", "Токсиколог"),
    ("первая помощь при отравлении цианидом калия", "цианид калия", "помощи"),
    ("температура вспышки изопропанола", "изопропанол", "пожаротуш"),
    ("класс опасности диборана", "диборан", None),
    ("ПДК толуилендиизоцианата ТДИ рабочая зона", "толуилендиизоцианат (ТДИ)", "Токсиколог"),
    ("чем опасен серный ангидрид триоксид серы", "серный ангидрид (триоксид серы)", None),
    ("температура вспышки этиленгликоля", "этиленгликоль", "пожаротуш"),
    ("как хранить уксусную кислоту", "уксусная кислота", "хранен"),
    ("температура вспышки винилацетата", "винилацетат", "пожаротуш"),
    ("ПДК борной кислоты", "борная кислота", "Токсиколог"),
    ("чем опасен метилметакрилат", "метилметакрилат", None),
    ("температура вспышки ксилола", "ксилол", "пожаротуш"),
    ("какие СИЗ при работе с трифторидом бора", "трифторид бора", "Средства защиты"),
    ("первая помощь при контакте с моноэтаноламином", "моноэтаноламин", "помощи"),
    ("как хранить акриловую кислоту, опасность полимеризации", "акриловая кислота", "хранен"),
    ("ПДК ортофосфорной кислоты", "ортофосфорная кислота", "Токсиколог"),
    ("температура вспышки бутилацетата", "бутилацетат", "пожаротуш"),
    ("чем опасен персульфат аммония как окислитель", "персульфат аммония", None),
    ("температура вспышки метилакрилата", "метилакрилат", "пожаротуш"),
    ("ПДК диэтаноламина в воздухе рабочей зоны", "диэтаноламин", "Токсиколог"),
    ("чем опасен циановодород синильная кислота", "циановодород (синильная кислота)", None),
]

def make_reranker():
    b = os.getenv("RERANK_BACKEND")
    if b == "crossencoder":
        from reranker_model import CrossEncoderReranker; return CrossEncoderReranker(), "crossencoder"
    if b == "llm":
        from reranker_llm import LLMReranker; return LLMReranker(), "llm"
    return None, "нет"

def main():
    rk, tag = make_reranker()
    r = SemanticRetriever(reranker=rk, rerank_n=int(os.getenv("RERANK_N", "20"))) if rk else SemanticRetriever()
    alltests = list(TESTS) + list(TESTS_EXT)

    def run(tests):
        h1 = h3 = sec = subj = 0; lat = []
        for q, exp, kw in tests:
            if q in PLANT_SCOPE: continue
            t = time.time(); res = r.query(q, 3); lat.append((time.time() - t) * 1000)
            subj += 1
            in3 = any(c["substance"] == exp for c, _ in res); ok1 = res[0][0]["substance"] == exp
            h1 += ok1; h3 += in3
            if ok1 and ((kw is None) or (kw.lower() in res[0][0]["section"].lower())): sec += 1
            if not ok1:
                print(f"  [{'~3' if in3 else 'MISS'}] {q[:46]:46} -> {res[0][0]['substance']}")
        return h1, h3, sec, subj, lat

    print(f"=== РАСШИРЕННЫЙ EVAL (реранк: {tag}) — промахи: ===")
    h1, h3, sec, subj, lat = run(alltests)
    med = sorted(lat)[len(lat)//2]
    print("=" * 70)
    print(f"Предметных запросов: {subj} (было 25, +{subj-25} новых по verified-ядру)")
    print(f"Вещество top-1:        {h1}/{subj} = {h1/subj:.0%}")
    print(f"Вещество top-3:        {h3}/{subj} = {h3/subj:.0%}")
    print(f"Вещество+раздел top-1: {sec}/{subj} = {sec/subj:.0%}")
    print(f"Latency median: {med:.0f} ms")

if __name__ == "__main__":
    main()
