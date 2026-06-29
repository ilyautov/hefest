# -*- coding: utf-8 -*-
"""
Подбор СИЗ (средств индивидуальной защиты) по веществу.

СВЯТОЕ ПРАВИЛО (safety-critical): цена ошибки = здоровье человека. Никогда не выдумывать
нормативку. Каждое значение СИЗ — ЛИБО из паспорта вещества (поле `ppe`, grade="passport",
source_tier T1/T2), ЛИБО типовое по химической группе из baseline.py (grade="baseline",
с явным дисклеймером «НЕ из паспорта конкретного вещества — требует проверки»). Где данных
нет — пишем «нет данных», а не додумываем. Числа/единицы не пересчитываем.

Модуль ИЗОЛИРОВАННЫЙ: не редактирует существующий код, переиспользует baseline.baseline_for
(типовые меры по группе) и compat.classify (сегрегационные группы — как контекст).

Раскладка СИЗ по категориям (органы дыхания / руки / глаза-лицо / кожа) — ЭВРИСТИКА ТОЛЬКО
ДЛЯ ОТОБРАЖЕНИЯ: разбивает уже готовый текст рекомендации на смысловые куски по ключевым
словам. Новых требований не добавляет, текст не переписывает.
"""
import re

import baseline
import compat

# Известные операции (для честного ответа «нет данных по операции», без фабрикации мер).
KNOWN_OPERATIONS = ("хранение", "перелив", "авария", "уборка пролива")

# Эвристика категорий СИЗ — порядок важен (проверяем дыхание раньше «лица», т.к. маска/аппарат
# относятся к органам дыхания). Только для раскладки готового текста по полкам отображения.
_CATEGORY_RULES = (
    ("respiratory", "органы дыхания",
     re.compile(r"респиратор|противогаз|изолирующ|сизод|фильтр|дыхательн|аппарат|маск|"
                r"самоспасат|противоаэрозол|противокислотн|марк[аи] фильтра", re.I)),
    ("hands", "руки",
     re.compile(r"перчат|рукавиц", re.I)),
    ("eyes_face", "глаза и лицо",
     re.compile(r"очк|щиток|лицев|экран|защит[аы]? глаз|защит[аы]? лица", re.I)),
    ("skin", "кожа и тело",
     re.compile(r"костюм|фартук|комбинезон|спецодежд|\bодежд|сапог|\bобувь|химкостюм|"
                r"защит[аы]? кожи|антистатич|прорезинен|нарукавник", re.I)),
)


def _split_items(text: str) -> list:
    """Разбить текст рекомендации на отдельные элементы СИЗ по пунктуации.
    Не переписывает и не нормализует формулировки — только режет по разделителям."""
    if not text:
        return []
    parts = re.split(r"[;,|]|\bи\b(?=\s)|·", text)
    return [p.strip(" .") for p in parts if p and p.strip(" .")]


def categorize(text: str) -> dict:
    """Разложить текст СИЗ по категориям отображения. Каждый кусок попадает в первую
    подходящую категорию; нераспознанные — в `other` (показываем как есть, не теряем)."""
    cats = {"respiratory": [], "hands": [], "eyes_face": [], "skin": [], "other": []}
    for item in _split_items(text):
        placed = False
        for key, _label, rx in _CATEGORY_RULES:
            if rx.search(item):
                cats[key].append(item)
                placed = True
                break
        if not placed:
            cats["other"].append(item)
    return cats


CATEGORY_LABELS = {
    "respiratory": "органы дыхания",
    "hands": "руки",
    "eyes_face": "глаза и лицо",
    "skin": "кожа и тело",
    "other": "прочее / общие меры",
}


def _context(sub: dict) -> dict:
    """Класс опасности / ПДК / GHS как контекст — строго с провенансом, без фабрикации."""
    hc = sub.get("hazard_class")
    pdk = sub.get("pdk_mgm3")
    ghs = sub.get("ghs") or []
    return {
        "hazard_class": (
            {"value": str(hc), "source": "нормативная база (ГН 2.2.5 / СанПиН 1.2.3685-21)"}
            if hc not in (None, "") else {"value": None, "note": "нет данных"}
        ),
        "pdk_mgm3": (
            {"value": pdk, "unit": "мг/м³", "source": "нормативная база (ГН 2.2.5 / СанПиН 1.2.3685-21)"}
            if pdk not in (None, "") else {"value": None, "note": "нет данных"}
        ),
        "ghs": (
            {"value": list(ghs), "source": "паспорт / классификация вещества"}
            if ghs else {"value": [], "note": "нет данных"}
        ),
    }


def _operation_note(operation) -> dict:
    """Честный ответ по операции: данных по конкретной операции в источнике нет — не выдумываем."""
    op = (operation or "").strip().lower()
    if not op:
        return {"requested": None, "note": None}
    known = op in KNOWN_OPERATIONS
    return {
        "requested": operation,
        "recognized": known,
        # СИЗ под конкретную операцию нигде не паспортизованы → не фабрикуем, говорим прямо.
        "note": (f"Уточнение СИЗ по операции «{operation}»: нет данных в источнике. "
                 f"Показаны общие СИЗ по веществу — оцените достаточность под операцию по месту."),
    }


def recommend_ppe(sub: dict, operation=None) -> dict:
    """Рекомендация СИЗ по веществу.

    Источник СИЗ:
      • если у вещества есть паспортный `ppe` → grade="passport" (source: паспорт);
      • иначе → baseline.baseline_for(sub) → grade="baseline" (типовое по группе + дисклеймер).

    Возвращает чистый детерминированный dict. Контекст (класс/ПДК/GHS) — с провенансом.
    operation — если задана, честно помечается «нет данных по операции».
    """
    name = sub.get("name")
    passport_ppe = (sub.get("ppe") or "").strip()
    groups = [compat.GROUPS[g] for g in compat.classify(sub)]

    if passport_ppe:
        tier = sub.get("source_tier") or "—"
        ppe = {
            "value": passport_ppe,
            "grade": "passport",
            "source": "паспорт безопасности (раздел 8 «Средства контроля/защиты»)",
            "citation": f"паспорт вещества «{name}», уровень источника {tier}",
            "disclaimer": None,
        }
    else:
        b = baseline.baseline_for(sub)
        ppe = {
            "value": b["ppe"]["value"],
            "grade": "baseline",
            "source": "типовое по химической группе (baseline) — НЕ из паспорта вещества",
            "citation": None,
            "disclaimer": b["disclaimer"],
        }

    return {
        "substance": name,
        "ppe": ppe,
        "categories": categorize(ppe["value"]),
        "category_labels": CATEGORY_LABELS,
        "groups": groups,
        "context": _context(sub),
        "operation": _operation_note(operation),
        "confidence": "needs_review",
    }


if __name__ == "__main__":
    # Юнит-самопроверка на 3 веществах (без сети, на статике). Печатает и проверяет инварианты.
    import json
    import os

    data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data",
                        "substances_clean.json")
    subs = {s["name"].lower(): s for s in json.load(open(data, encoding="utf-8"))}

    def pick(*names):
        for n in names:
            if n.lower() in subs:
                return subs[n.lower()]
            for k, v in subs.items():
                if n.lower() in k:
                    return v
        raise SystemExit(f"не найдено вещество для теста: {names}")

    # 1) серная кислота — есть паспортный ppe → grade=passport
    sulf = pick("серная кислота")
    r1 = recommend_ppe(sulf)
    assert r1["ppe"]["grade"] == "passport", r1["ppe"]["grade"]
    assert r1["ppe"]["disclaimer"] is None
    assert r1["categories"]["respiratory"], "респиратор не распознан в категориях"
    assert r1["categories"]["hands"], "перчатки не распознаны"

    # 2) вещество БЕЗ паспортного ppe → grade=baseline + дисклеймер (борная кислота в наборе
    #    паспортизована, поэтому для демонстрации baseline берём кислоту без поля ppe).
    base_acid = next((s for s in subs.values()
                      if not s.get("ppe") and "acid" in compat.classify(s)), None)
    assert base_acid is not None, "нет кислоты без ppe для baseline-теста"
    r2 = recommend_ppe(base_acid, operation="перелив")
    assert r2["ppe"]["grade"] == "baseline", r2["ppe"]["grade"]
    assert r2["ppe"]["disclaimer"], "у baseline должен быть дисклеймер"
    assert r2["operation"]["note"] and "нет данных" in r2["operation"]["note"]

    # 3) аммиак — токсичный газ; проверяем контекст и провенанс
    amm = pick("аммиак")
    r3 = recommend_ppe(amm)
    assert r3["ppe"]["grade"] in ("passport", "baseline")
    assert "hazard_class" in r3["context"] and "ghs" in r3["context"]

    print("=== САМОПРОВЕРКА ppe.recommend_ppe ===")
    for tag, r in (("серная кислота", r1), ("baseline-кислота", r2), ("аммиак", r3)):
        print(f"\n[{tag}] {r['substance']}  grade={r['ppe']['grade']}  groups={r['groups']}")
        print("  СИЗ:", r["ppe"]["value"])
        for ckey in ("respiratory", "hands", "eyes_face", "skin", "other"):
            if r["categories"][ckey]:
                print(f"   - {CATEGORY_LABELS[ckey]}: {r['categories'][ckey]}")
        print("  контекст:", {k: v.get("value") for k, v in r["context"].items()})
        if r["ppe"]["disclaimer"]:
            print("  дисклеймер:", r["ppe"]["disclaimer"])
        if r["operation"]["note"]:
            print("  операция:", r["operation"]["note"])
    print("\nOK: все инварианты выполнены (passport/baseline/нет-данных, провенанс, категории).")
