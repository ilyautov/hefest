# -*- coding: utf-8 -*-
"""
Слой ОЦЕНКИ ВЫДАЧИ (answer-level review) — отдельный от верификации данных вещества.

verification.py подписывает СТАТИЧНЫЕ ДАННЫЕ вещества («ПДК хлора подтверждён экспертом»).
Здесь — человек оценивает КОНКРЕТНУЮ ВЫДАЧУ на КОНКРЕТНЫЙ запрос: правильно ли система достала
первичку (retrieval) и собрала из неё ответ (extraction), и полезно ли это. Так копится размеченный
лог качества — для доверия (видно, кто и что подтвердил) и для калибровки (порог отказа, эвал).

Принцип безопасности: каждая оценка ПОДПИСАНА (кто/когда) — это не «лайк», а ответственная отметка
специалиста. Никаких анонимных правок: verdict без поля `by` отклоняется.
"""
import os, json, threading

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
_PATH = os.path.join(DATA, "answer_reviews.json")
_LOCK = threading.Lock()
_VERDICTS = ("correct", "incorrect", "partial")

_SEED = {"_meta": {
    "scheme": "answer-review v1",
    "disclaimer": "Оценки выдачи специалистами предприятия. verdict: correct=выдача верна, "
                  "partial=частично, incorrect=неверна. data_ok=данные соответствуют первичке, "
                  "useful=ответ полезен. Каждая оценка подписана (кто/когда).",
    "note": "Это НЕ верификация данных вещества (см. verification.json) — это оценка ответа на запрос.",
}}


def _load():
    if not os.path.exists(_PATH):
        return dict(_SEED)
    try:
        return json.load(open(_PATH, encoding="utf-8"))
    except Exception:
        return dict(_SEED)


def _save(d):
    tmp = _PATH + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, _PATH)


def add(question, verdict, by, answer=None, top_score=None, data_ok=None, useful=None,
        sources=None, note=None, role=None, now=None):
    """Записать оценку выдачи. verdict in correct|incorrect|partial; by обязателен."""
    verdict = (verdict or "").strip().lower()
    if verdict not in _VERDICTS:
        raise ValueError(f"verdict должен быть из {_VERDICTS}")
    if not (by or "").strip():
        raise ValueError("оценка должна быть подписана (поле by) — анонимные отметки не принимаются")
    rec = {
        "question": question, "answer": answer, "top_score": top_score,
        "verdict": verdict, "data_ok": data_ok, "useful": useful,
        "sources": sources or [],         # [{citation, substance, relevant: bool}]
        "by": by.strip(), "role": (role or "").strip() or None,
        "note": (note or "").strip() or None, "at": now or _now(),
    }
    with _LOCK:
        d = _load()
        d.setdefault("records", []).append(rec)
        d["_meta"] = _SEED["_meta"]
        _save(d)
    return rec


def _now():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def records(limit=None):
    d = _load()
    recs = list(reversed(d.get("records", [])))   # свежие сверху
    return recs[:limit] if limit else recs


def summary():
    recs = _load().get("records", [])
    n = len(recs)
    by_verdict = {v: sum(1 for r in recs if r.get("verdict") == v) for v in _VERDICTS}
    useful_yes = sum(1 for r in recs if r.get("useful") is True)
    data_bad = sum(1 for r in recs if r.get("data_ok") is False)
    # доля «не в тему» источников (сигнал проблем retrieval)
    irrel = sum(1 for r in recs for s in (r.get("sources") or []) if s.get("relevant") is False)
    return {
        "total": n,
        "correct": by_verdict["correct"], "partial": by_verdict["partial"],
        "incorrect": by_verdict["incorrect"],
        "correct_pct": round(100 * by_verdict["correct"] / n) if n else None,
        "useful_yes": useful_yes,
        "data_mismatch": data_bad,            # данные не сошлись с первичкой
        "irrelevant_sources": irrel,          # подтянули не тот документ (retrieval)
        "reviewers": sorted({r["by"] for r in recs if r.get("by")}),
    }
