# -*- coding: utf-8 -*-
"""
Чистка bulk-артефактов ингеста ГН — НЕДЕСТРУКТИВНО (originals не трогаем).
Демонстрация навыка аудит-спринта на грязных данных.

Что делает (детерминированный transform существующих чанков corpus_full.json):
  1. «+» в конце имени -> поле skin_hazard=True (в ГН «+» = «опасно при попадании на кожу»),
     «+» убирается из имени и из ведущего имени в тексте чанка.
  2. 3 истинных дубля (азотная/бензол/серная кислота+) -> их чанки отбрасываются
     (базовая запись без «+» уже есть), skin_hazard переносится на базу.
  3. Строки-контроли («контроль по…», «а)/б)…») -> помечаются is_control=True (НЕ удаляются:
     это регуляторные записи, ПДК по прокси-веществу).
Verified-48 (confidence != needs_review) не затрагиваются — артефакты только в needs_review.

Выход: data/corpus_full_clean.json, data/substances_clean.json + отчёт в stdout.
"""
import json, os, re, collections

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "..", "data")

def is_control(n):
    return bool(re.match(r"^[а-г]\)\s", n.strip().lower())) or "контроль по" in n.lower()

def clean_name(n):
    s = n.strip()
    skin = s.endswith("+")
    s = s.rstrip("+").strip()
    return s, skin

def strip_paren(n):
    return re.sub(r"\s*\([^)]+\)\s*$", "", n).strip()

def dupe_target(orig, names):
    """Истинный дубль: после снятия «+» ИЛИ хвостовой «(…)» имя совпало с ДРУГОЙ существующей
    записью. Возвращает (base|None, skin). Скобки снимаем только когда это даёт дубль —
    легитимные «(…)» (1428 шт.) не трогаем."""
    s1, skin = clean_name(orig)
    if s1 != orig and s1 in names:                 # «+»-дубль (3 шт.)
        return s1, skin
    s2 = strip_paren(s1)
    if s2 != s1 and s2 in names:                   # скобочный синоним-дубль (4 шт.)
        return s2, skin
    return None, skin

def main():
    corpus = json.load(open(os.path.join(DATA, "corpus_full.json"), encoding="utf-8"))
    subs = json.load(open(os.path.join(DATA, "substances_all.json"), encoding="utf-8"))
    names = {s["name"] for s in subs}
    base_skin = set()                                  # базы, на которые переносим кожный маркер от дубля

    new_chunks, dropped = [], 0
    stats = collections.Counter()
    for c in corpus["chunks"]:
        orig = c["substance"]
        clean, skin = clean_name(orig)
        ctrl = is_control(orig)
        # истинный дубль («+» или скобочный синоним) -> чанк отбрасываем (база уже есть)
        tgt, _ = dupe_target(orig, names)
        if tgt is not None:
            dropped += 1
            if skin: base_skin.add(tgt)
            stats["dup_dropped"] += 1; continue
        c2 = dict(c)
        c2["substance"] = clean
        if skin: c2["skin_hazard"] = True; stats["skin_marked"] += 1
        if ctrl: c2["is_control"] = True; stats["control_marked"] += 1
        if c["text"].startswith(orig):                 # чиним ведущее имя в тексте
            c2["text"] = clean + c["text"][len(orig):]
        new_chunks.append(c2)

    # вещества: то же снятие «+» + флаги, перенос skin на базы-дубли
    new_subs, seen = [], set()
    for s in subs:
        clean, skin = clean_name(s["name"])
        if dupe_target(s["name"], names)[0] is not None:
            continue                                   # дубль-вещество убираем (база остаётся)
        s2 = dict(s); s2["name"] = clean
        if skin or clean in base_skin: s2["skin_hazard"] = True
        if is_control(s["name"]): s2["is_control"] = True
        if clean in seen: continue
        seen.add(clean); new_subs.append(s2)

    out_c = dict(corpus); out_c["chunks"] = new_chunks
    out_c["meta"] = {**corpus.get("meta", {}), "cleaned": True,
                     "chunks": len(new_chunks), "substances": len(new_subs)}
    json.dump(out_c, open(os.path.join(DATA, "corpus_full_clean.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(new_subs, open(os.path.join(DATA, "substances_clean.json"), "w", encoding="utf-8"), ensure_ascii=False)

    print(f"чанков: {len(corpus['chunks'])} -> {len(new_chunks)} (отброшено дубль-чанков: {dropped})")
    print(f"веществ: {len(subs)} -> {len(new_subs)}")
    print(f"помечено skin_hazard: {stats['skin_marked']} чанков | is_control: {stats['control_marked']} чанков")
    print(f"истинных дубль-веществ слито: {stats['dup_dropped']//10 if stats['dup_dropped'] else 0} (~)")
    print("-> data/corpus_full_clean.json, data/substances_clean.json")

if __name__ == "__main__":
    main()
