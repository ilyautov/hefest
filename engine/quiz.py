# -*- coding: utf-8 -*-
"""
Обучающий квиз по веществу — для инструктажа персонала.

ОСОЗНАННО детерминированный (без генерации LLM): ответы берутся напрямую из паспорта,
в безопасность-критичном обучении галлюцинации недопустимы. Где есть числовой параметр
(класс опасности, ПДК) — даём варианты ответа с правдоподобными отвлекающими. Для СИЗ/первой
помощи/хранения — открытый вопрос с эталонным ответом (с пометкой источника: паспорт/типовое).
"""
import baseline

_HAZ = {"1": "1 — чрезвычайно опасное", "2": "2 — высокоопасное",
        "3": "3 — умеренно опасное", "4": "4 — малоопасное"}


def _pdk_options(pdk):
    """Варианты для ПДК: верный + правдоподобные кратные."""
    try:
        v = float(str(pdk).replace(",", "."))
    except (TypeError, ValueError):
        return None
    cand = [v, round(v * 10, 3), round(v / 10, 4) if v >= 0.1 else round(v * 5, 4), round(v * 2, 3)]
    seen, opts = set(), []
    for c in cand:
        cs = (f"{c:g}")
        if cs not in seen:
            seen.add(cs); opts.append(f"{cs} мг/м³")
    return {"options": opts[:4], "answer": f"{v:g} мг/м³"} if len(opts) >= 2 else None


def build_quiz(sub):
    name = sub["name"]
    g = baseline.baseline_for(sub)
    items = []

    hc = str(sub.get("hazard_class") or "")
    if hc in _HAZ:
        opts = [_HAZ[k] for k in ("1", "2", "3", "4")]
        items.append({"type": "choice", "q": f"Класс опасности «{name}» по ГОСТ 12.1.007?",
                      "options": opts, "answer": _HAZ[hc], "source": "паспорт"})

    p = _pdk_options(sub.get("pdk_mgm3"))
    if p:
        items.append({"type": "choice", "q": f"ПДК «{name}» в воздухе рабочей зоны?",
                      "options": p["options"], "answer": p["answer"], "source": "паспорт"})

    items.append({"type": "open", "q": f"Какие средства защиты (СИЗ) применять при работе с «{name}»?",
                  "answer": g["ppe"]["value"], "source": g["ppe"]["source"]})
    items.append({"type": "open", "q": f"Первая помощь при воздействии «{name}»?",
                  "answer": g["first_aid"]["value"], "source": g["first_aid"]["source"]})
    items.append({"type": "open", "q": f"Условия хранения и несовместимости «{name}»?",
                  "answer": g["storage"]["value"], "source": g["storage"]["source"]})

    return {"substance": name, "questions": items,
            "note": "Вопросы и ответы детерминированы из паспорта (не генерируются ИИ). "
                    "Где источник «типовое по группе» — ответ ориентировочный, сверьте с паспортом."}
