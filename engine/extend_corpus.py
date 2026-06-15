# -*- coding: utf-8 -*-
"""
Инкрементальное расширение семантического индекса на обогащённые/новые АХОВ.

Зачем: после обогащения (apply_enrich.py) хлор получил СИЗ/первую помощь/хранение/GHS, а
сероводород/диоксид серы/хлороводород добавлены как вещества — но в корпусе их разделов не было,
поэтому /search их не находил. Здесь:
  REFRESH — у веществ, чьи чанки уже есть, но текст устарел (хлор), перегенерируем разделы
            и ПЕРЕ-эмбеддим строки НА ТЕХ ЖЕ позициях (выравнивание chunks[i] <-> emb[i] сохраняется);
  ADD     — у новых веществ строим 10 разделов, эмбеддим и ДОПИСЫВАЕМ чанки и строки эмбеддингов.

Эмбеддинги — локальная Ollama bge-m3 (/api/embed, нормированные вектора), как в build_semantic_index.
Недеструктивно: бэкап corpus_full_clean.json и embeddings_clean.npy перед записью. Идемпотентно.
"""
import os, json, shutil, urllib.request
import numpy as np
from corpus import build_sections

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
CORPUS = os.path.join(DATA, "corpus_full_clean.json")
EMB = os.path.join(DATA, "embeddings_clean.npy")
IDS = os.path.join(DATA, "embed_ids_clean.json")
SUBS = os.path.join(DATA, "substances_clean.json")
HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.getenv("EMB_MODEL", "bge-m3")

# Что обновляем. REFRESH — уже в корпусе, но данные изменились; ADD — новые.
REFRESH = ["хлор"]
ADD = ["сероводород", "диоксид серы", "хлороводород"]


def embed_batch(texts):
    req = urllib.request.Request(
        HOST + "/api/embed",
        data=json.dumps({"model": MODEL, "input": texts}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return np.array(json.load(r)["embeddings"], dtype=np.float32)


def make_chunks(s):
    """Чанки разделов для вещества s в схеме корпуса."""
    out = []
    for sec, text in build_sections(s).items():
        out.append({
            "doc_id": s["name"], "substance": s["name"], "formula": s.get("formula", ""),
            "cas": s.get("cas", ""), "hazard_class": s.get("hazard_class"),
            "section": sec, "text": text, "source_tier": s.get("source_tier"),
            "confidence": s.get("confidence"),
            "citation": f'{s["name"]} ({s.get("formula","")}, CAS {s.get("cas","")}), {sec}',
            "skin_hazard": s.get("skin_hazard", False),
        })
    return out


def main():
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    chunks = corpus["chunks"]
    M = np.load(EMB).astype(np.float32)
    subs = json.load(open(SUBS, encoding="utf-8"))
    by_name = {s["name"].lower(): s for s in subs}
    assert len(chunks) == M.shape[0], f"рассинхрон: {len(chunks)} чанков vs {M.shape[0]} эмбеддингов"

    # бэкапы
    for src, suf in [(CORPUS, ".bak.json"), (EMB, ".bak.npy")]:
        bak = src.replace(".json", suf).replace(".npy", suf)
        if not os.path.exists(bak):
            shutil.copy(src, bak); print(f"[backup] {os.path.basename(bak)}")

    present = {c["substance"] for c in chunks}

    # --- REFRESH: перегенерация на тех же позициях ---
    for name in REFRESH:
        s = by_name.get(name.lower())
        if not s:
            print(f"[skip] {name}: нет в substances_clean"); continue
        new = {c["section"]: c for c in make_chunks(s)}
        idxs = [i for i, c in enumerate(chunks) if c["substance"] == name]
        if not idxs:
            print(f"[warn] {name}: чанков в корпусе нет -> уйдёт в ADD"); ADD.append(name); continue
        texts, positions = [], []
        for i in idxs:
            sec = chunks[i]["section"]
            if sec in new:
                chunks[i] = new[sec]                 # обновляем текст/цитату/поля
                texts.append(new[sec]["text"]); positions.append(i)
        vecs = embed_batch(texts)
        for p, v in zip(positions, vecs):
            M[p] = v                                 # ПЕРЕ-эмбед на той же строке
        print(f"[refresh] {name}: обновлено разделов {len(positions)}")

    # --- ADD: новые вещества дописываем в конец ---
    new_chunks, new_texts = [], []
    for name in ADD:
        if name in present:
            print(f"[noop] {name}: уже в корпусе"); continue
        s = by_name.get(name.lower())
        if not s:
            print(f"[skip] {name}: нет в substances_clean"); continue
        cs = make_chunks(s)
        new_chunks.extend(cs); new_texts.extend([c["text"] for c in cs])
        print(f"[add] {name}: +{len(cs)} разделов")
    if new_texts:
        vecs = embed_batch(new_texts)
        chunks.extend(new_chunks)
        M = np.vstack([M, vecs])

    assert len(chunks) == M.shape[0], "после расширения рассинхрон chunks/emb"
    corpus["meta"]["chunks"] = len(chunks)
    json.dump(corpus, open(CORPUS, "w", encoding="utf-8"), ensure_ascii=False)
    np.save(EMB, M)
    json.dump([c["citation"] for c in chunks], open(IDS, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\nИтог: чанков {len(chunks)}, эмбеддингов {M.shape[0]}. Готово.")


if __name__ == "__main__":
    main()
