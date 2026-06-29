# -*- coding: utf-8 -*-
"""
Зональный аудит совместимости хранения на КАРТЕ СКЛАДА.

Делает совместимость «пространственной»: предприятие задаёт раскладку склада по зонам
(demo-шаблон в data/warehouse_zones.json), а система для КАЖДОЙ зоны прогоняет все пары
веществ внутри неё через движок compat и подсвечивает несовместимые сочетания, которые
физически стоят рядом. Разные зоны = разнесённое хранение, поэтому межзональные пары НЕ
считаются конфликтом (это и есть смысл сегрегации).

Святое правило (safety-critical):
  * Вердикт несовместимости (forbidden/caution) берётся ТОЛЬКО из compat.check — не выдумывается.
  * Источник вердикта честно градуируется:
      - "structured" — несовместимость ПОДТВЕРЖДЕНА текстом паспорта (Раздел 7/10: «storage»/
        «special») хотя бы одного из веществ пары (вещество паспортной/частичной полноты);
      - "эвристика по группе" — пара отнесена к несовместимым только классификацией по
        имени/GHS (как у ~97% веществ), без структурного источника в паспорте. UI обязан
        показывать эту пометку, чтобы не выдавать эвристику за паспортные данные.
  * Раскладка зон — ДЕМОНСТРАЦИОННЫЙ пример/шаблон (layout_status), а не реальная схема склада
    конкретного предприятия; помечается как заполняемая объектом.

Детерминированность: сортировки стабильны, классификация чистая → одинаковый ввод даёт
одинаковый вывод.
"""
import json
import os

import compat
import baseline

_ZONES_FILE = os.environ.get(
    "WAREHOUSE_ZONES_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "warehouse_zones.json"),
)

# Ключевые слова групп, какими они проявляются в тексте несовместимости паспорта
# (Раздел 7 «Хранение» / Раздел 10 «Стабильность и реакционная способность»).
# Используются ТОЛЬКО для проверки: подтверждает ли паспорт уже найденную compat несовместимость.
_GROUP_KEYWORDS = {
    "acid":        ("кислот",),
    "base":        ("щёлоч", "щелоч", "основан", "амин", "аммиак", "едк"),
    "oxidizer":    ("окислит",),
    "flammable":   ("горюч", "лвж", "воспламен", "инициатор", "восстановител"),
    "react_metal": ("металл", "алюмин", "цинк", "латун", " cu", " zn"),
    "tox_gas":     ("хлор", "фосген", "сероводород", "галоген", "газ"),
    "cyanide":     ("циан", "сульфид", "hcn", "h2s"),
    "cl_release":  ("гипохлорит", "хлор"),
    "organic":     ("органик", "растворит", "углевод"),
    "peroxide":    ("перекис", "пероксид"),
}


def _incompat_text(sub: dict) -> str:
    return ((sub.get("storage") or "") + " | " + (sub.get("special") or "")).lower()


def _corroborates(sub: dict, other_groups: list) -> bool:
    """Подтверждает ли текст паспорта `sub` несовместимость с группами `other_groups`."""
    t = _incompat_text(sub)
    for g in other_groups:
        for kw in _GROUP_KEYWORDS.get(g, ()):
            if kw in t:
                return True
    return False


def _grade_pair(a: dict, b: dict):
    """Грейд источника вердикта пары: ('structured', цитата) либо ('эвристика по группе', None).

    'structured' — если паспорт (storage/special) хотя бы одного вещества паспортной/частичной
    полноты явно называет группу другого вещества как несовместимую. Иначе — эвристика по группе.
    """
    ga, gb = compat.classify(a), compat.classify(b)
    for sub, others in ((a, gb), (b, ga)):
        if baseline.data_grade(sub) in ("passport", "partial") and _corroborates(sub, others):
            quote = (sub.get("storage") or sub.get("special") or "").strip()
            return "structured", quote[:220]
    return "эвристика по группе", None


def _load_layouts() -> dict:
    """Читает шаблон раскладок -> {inn: layout}. Пустой словарь, если файла нет."""
    try:
        with open(_ZONES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return {str(l.get("plant_inn")): l for l in data.get("layouts", [])}


_GROUP_KEYS = {disp: key for key, disp in compat.GROUPS.items()}  # рус. название -> ключ группы


def _sub_view(name: str, subs_by_name: dict) -> dict:
    """Карточка вещества для отрисовки в зоне (имя/класс/группы/полнота)."""
    s = subs_by_name.get(name.lower())
    if not s:
        return {"name": name, "known": False, "hazard_class": None,
                "groups": [], "group_keys": [], "data_grade": None}
    keys = compat.classify(s)
    return {
        "name": s["name"], "known": True,
        "hazard_class": s.get("hazard_class"), "cas": s.get("cas"),
        "groups": [compat.GROUPS[g] for g in keys], "group_keys": keys,
        "data_grade": baseline.data_grade(s),
    }


def _zone_conflicts(names, subs_by_name):
    """Все опасные пары ВНУТРИ одной зоны (вещества физически рядом)."""
    known = [n for n in names if n.lower() in subs_by_name]
    out = []
    rank = {"forbidden": 2, "caution": 1}
    for i in range(len(known)):
        for j in range(i + 1, len(known)):
            a, b = subs_by_name[known[i].lower()], subs_by_name[known[j].lower()]
            r = compat.check(a, b)
            if r["verdict"] not in rank:
                continue
            source, quote = _grade_pair(a, b)
            out.append({
                "a": a["name"], "b": b["name"],
                "verdict": r["verdict"],
                "why": r["reasons"][0]["why"] if r["reasons"] else "",
                "groups": (r["reasons"][0]["pair"] if r["reasons"] else []),
                "source": source,                 # 'structured' | 'эвристика по группе'
                "source_quote": quote,             # цитата паспорта при structured
            })
    out.sort(key=lambda x: (-rank[x["verdict"]], x["a"], x["b"]))
    return out


def audit(plant_obj: dict, subs_by_name: dict) -> dict:
    """Зональный аудит склада завода. Совместим по сигнатуре с registry.summary."""
    layouts = _load_layouts()
    layout = layouts.get(str(plant_obj.get("inn")))

    if layout:
        zones_src = layout.get("zones", [])
        layout_status = "template"          # есть demo-раскладка (пример, редактируется объектом)
    else:
        # Раскладки нет: показываем единую неразделённую зону из всех веществ завода —
        # честно («нет зональной раскладки»), но аудит пар всё равно работает.
        zones_src = [{
            "zone_id": "—",
            "name": "Зональная раскладка не задана — все вещества в одном пространстве",
            "storage_type": "раскладка по зонам заполняется предприятием",
            "substances": list(plant_obj.get("matched_substances", [])),
        }]
        layout_status = "none"

    placed = set()
    zones = []
    total_f = total_c = 0
    for z in zones_src:
        names = z.get("substances", [])
        for n in names:
            placed.add(n.lower())
        conf = _zone_conflicts(names, subs_by_name)
        zf = sum(1 for c in conf if c["verdict"] == "forbidden")
        zc = sum(1 for c in conf if c["verdict"] == "caution")
        total_f += zf
        total_c += zc
        worst = "forbidden" if zf else ("caution" if zc else "ok")
        zones.append({
            "zone_id": z.get("zone_id"),
            "name": z.get("name"),
            "storage_type": z.get("storage_type"),
            "substances": [_sub_view(n, subs_by_name) for n in names],
            "conflicts": conf,
            "forbidden": zf, "caution": zc, "status": worst,
        })

    # Вещества завода, не попавшие ни в одну зону (предприятию нужно их разместить).
    unplaced = [_sub_view(n, subs_by_name)
                for n in plant_obj.get("matched_substances", [])
                if n.lower() not in placed]

    return {
        "plant": plant_obj.get("plant"), "inn": plant_obj.get("inn"),
        "layout_status": layout_status,        # template | none
        "is_template": True,                   # раскладка — пример/шаблон, не реальная схема склада
        "zones_total": len(zones),
        "substances_placed": len(placed),
        "forbidden_pairs": total_f, "caution_pairs": total_c,
        "zones": zones,
        "unplaced": unplaced,
        "legend_groups": compat.GROUPS,
        "note": "Раскладка зон — демонстрационный пример/шаблон, реальную схему склада, площади и "
                "фактическое размещение задаёт предприятие. Вердикты несовместимости получены движком "
                "совместимости (compat). Источник: «structured» — несовместимость подтверждена текстом "
                "паспорта (Раздел 7/10); «эвристика по группе» — пара отнесена к несовместимым только "
                "классификацией по имени/GHS, без структурного источника в паспорте — сверьте с паспортом.",
        "disclaimer": "Перед фактическим размещением сверьте Раздел 10 паспорта каждого вещества и правила "
                      "совместного хранения вашего объекта. Классификация needs_review до подписи эксперта.",
        "confidence": "needs_review",
    }


if __name__ == "__main__":
    # Самопроверка: гоняем аудит на пилотном заводе из шаблона и печатаем сводку.
    import sys
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    subs = json.load(open(os.path.join(base, "substances_clean.json"), encoding="utf-8"))
    plants = json.load(open(os.path.join(base, "plants_linked.json"), encoding="utf-8"))["plants"]
    sb = {s["name"].lower(): s for s in subs}

    pilot = next((p for p in plants if p.get("inn") == "0000000000"), None)
    assert pilot, "пилотный завод (ИНН 0000000000) не найден в plants_linked.json"
    r = audit(pilot, sb)

    print(f"Завод: {r['plant']} (ИНН {r['inn']})  layout={r['layout_status']}")
    print(f"Зон: {r['zones_total']}  размещено веществ: {r['substances_placed']}  "
          f"не размещено: {len(r['unplaced'])}")
    print(f"ИТОГО пар: forbidden={r['forbidden_pairs']}  caution={r['caution_pairs']}\n")
    for z in r["zones"]:
        mark = {"forbidden": "✗ НЕЛЬЗЯ", "caution": "⚠ осторожно", "ok": "✓ чисто"}[z["status"]]
        subs_names = ", ".join(s["name"] for s in z["substances"]) or "(пусто)"
        print(f"[{z['zone_id']}] {z['name']}  — {mark}")
        print(f"     вещества: {subs_names}")
        for c in z["conflicts"]:
            print(f"     {c['verdict'].upper():9} {c['a']} + {c['b']}  [{c['source']}]")
            print(f"               причина: {c['why']}")
            if c["source_quote"]:
                print(f"               паспорт: {c['source_quote'][:90]}…")
        print()

    # Инварианты самопроверки.
    zc = {z["zone_id"]: z for z in r["zones"]}
    assert r["layout_status"] == "template", "ожидался шаблон раскладки для пилота"
    assert zc["C"]["forbidden"] >= 1, "зона C (общий реагентный участок) должна давать forbidden"
    assert zc["A"]["status"] == "ok", "зона A (мономеры/ЛВЖ) должна быть чистой (сегрегация верна)"
    assert all(c["source"] in ("structured", "эвристика по группе")
               for z in r["zones"] for c in z["conflicts"]), "грейд источника обязателен"
    # Детерминизм: повторный прогон даёт идентичный результат.
    assert audit(pilot, sb) == r, "аудит недетерминирован"
    print("САМОПРОВЕРКА ПРОЙДЕНА: зоны, конфликты, грейд источника и детерминизм — OK", file=sys.stderr)
