# -*- coding: utf-8 -*-
"""
Потребитель физико-химических свойств из data/physchem.json (собрано fetch_physchem.py из PubChem,
NIH public domain). Отдаёт карточке вещества свойства, важные для пожарной безопасности и хранения.

ПРИНЦИП БЕЗОПАСНОСТИ: модуль НЕ выбирает «единственно верное» число и НЕ пересчитывает единицы.
Он отдаёт сырые значения PubChem как есть, с источником каждого. Если значений несколько (разные
справочники/единицы) — показываем все; расхождение видит эксперт. Всё помечено needs_review.
"""
import os, json
import physchem_l10n as _l10n

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
_PATH = os.path.join(DATA, "physchem.json")

# наш ключ -> (русская подпись, зачем это важно)
LABELS = {
    "flash_point":      ("Температура вспышки", "пожароопасность: можно ли работать рядом с огнём"),
    "flammable_limits": ("Пределы воспламенения (НКПР/ВКПР)", "взрывоопасность паровоздушной смеси"),
    "boiling_point":    ("Температура кипения", ""),
    "melting_point":    ("Температура плавления", ""),
    "vapor_pressure":   ("Давление пара", "летучесть при разливе"),
    "density":          ("Плотность", "плавает/тонет в воде при разливе"),
    "solubility":       ("Растворимость в воде", ""),
}
# Порядок вывода: сначала безопасно-критичные.
ORDER = ["flash_point", "flammable_limits", "vapor_pressure", "boiling_point",
         "density", "solubility", "melting_point"]

_CACHE = None
_MTIME = None


def _load():
    global _CACHE, _MTIME
    try:
        m = os.path.getmtime(_PATH)
    except OSError:
        _CACHE, _MTIME = {}, None
        return _CACHE
    if _CACHE is None or m != _MTIME:
        try:
            _CACHE = json.load(open(_PATH, encoding="utf-8"))
        except Exception:
            _CACHE = {}
        _MTIME = m
    return _CACHE


def for_cas(cas):
    """CAS -> {props:[{key,label,why,values:[{value,source}]}], source, needs_review} либо None."""
    if not cas:
        return None
    rec = _load().get(cas)
    if not rec or rec == "_meta":
        return None
    props = rec.get("props", {}) or {}
    out = []
    for key in ORDER:
        vals = props.get(key)
        if not vals:
            continue
        # локализуем описания (числа/единицы/источник — дословно) и схлопываем дубли,
        # объединяя источники: одинаковое значение из 3 справочников -> одна строка, 3 источника.
        merged = {}
        order = []
        for v in vals:
            loc = _l10n.localize(v.get("value", ""))
            if not loc:                       # отброшенный мусор (навигация HSDB и т.п.)
                continue
            src = v.get("source", "")
            if loc not in merged:
                merged[loc] = []
                order.append(loc)
            if src and src not in merged[loc]:
                merged[loc].append(src)
        values = [{"value": loc, "sources": merged[loc]} for loc in order]
        if not values:
            continue
        label, why = LABELS.get(key, (key, ""))
        out.append({"key": key, "label": label, "why": why, "values": values})
    if not out:
        return None
    return {"props": out,
            "source": rec.get("source", "PubChem (NIH, public domain)"),
            "needs_review": True,
            "note": "Свойства из агрегата справочников PubChem (HSDB, CAMEO, NIOSH, ICSC и др.), "
                    "описания локализованы, числа и единицы — как в источнике (без пересчёта). "
                    "Несколько значений = разные источники/единицы. Сверьте с паспортом перед применением."}


def summary_counts():
    """Для дашборда: сколько веществ имеют физхимию и по каким полям."""
    d = _load()
    n = 0
    by_field = {k: 0 for k in LABELS}
    for cas, rec in d.items():
        if cas == "_meta" or not rec:
            continue
        n += 1
        for k in (rec.get("props") or {}):
            if k in by_field:
                by_field[k] += 1
    return {"substances_with_physchem": n, "by_field": by_field}
