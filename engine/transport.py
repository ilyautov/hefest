# -*- coding: utf-8 -*-
"""
Потребитель транспортной идентификации (data/transport.json, собрано fetch_transport.py из PubChem,
NIH public domain): номер ООН, гид ERG, транспортная метка опасности.

ПРИНЦИП БЕЗОПАСНОСТИ: номер ООН и гид ERG — языконезависимые числа, отдаём как есть. Транспортную метку
(DOT Label) НЕ переводим вольно (риск исказить класс) — показываем оригинал с пометкой источника. Несколько
номеров ООН = разные формы вещества (форма в аннотации), выбор за экспертом. needs_review.

Соответствие нашим кураторским АХОВ: если у вещества уже есть номер ООН из ahov_cards (ДОПОГ), он
приоритетнее — этот модуль дополняет базу там, где кураторских данных нет.
"""
import os, json

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
_PATH = os.path.join(DATA, "transport.json")
_CACHE, _MTIME = None, None

# Стандартные метки DOT -> класс ООН/ДОПОГ (стандартные термины, не вольный перевод).
_LABEL_RU = {
    "poison gas": "Ядовитый газ (класс 2.3)",
    "flammable gas": "Воспламеняющийся газ (класс 2.1)",
    "non-flammable gas": "Невоспламеняющийся газ (класс 2.2)",
    "flammable liquid": "Легковоспламеняющаяся жидкость (класс 3)",
    "flammable solid": "Легковоспламеняющееся твёрдое вещество (класс 4.1)",
    "oxidizer": "Окислитель (класс 5.1)",
    "organic peroxide": "Органический пероксид (класс 5.2)",
    "corrosive": "Коррозионное вещество (класс 8)",
    "poison": "Ядовитое вещество (класс 6.1)",
    "inhalation hazard": "Опасность при вдыхании",
    "explosive": "Взрывчатое вещество (класс 1)",
    "radioactive": "Радиоактивный материал (класс 7)",
    "spontaneously combustible": "Самовозгорающееся вещество (класс 4.2)",
    "dangerous when wet": "Опасно при намокании (класс 4.3)",
}


def _load():
    global _CACHE, _MTIME
    try:
        m = os.path.getmtime(_PATH)
    except OSError:
        _CACHE = {}; return _CACHE
    if _CACHE is None or m != _MTIME:
        try:
            _CACHE = json.load(open(_PATH, encoding="utf-8"))
        except Exception:
            _CACHE = {}
        _MTIME = m
    return _CACHE


def _label_hint(label):
    """Подсказка по стандартным DOT-меткам (поиск ключевых слов), либо None. Оригинал всё равно показываем."""
    low = (label or "").lower()
    hits = [ru for en, ru in _LABEL_RU.items() if en in low]
    return hits or None


def for_cas(cas):
    """CAS -> {un:[{un,erg_guide,form}], labels:[{raw,hint}], source, needs_review} либо None."""
    if not cas:
        return None
    rec = _load().get(cas)
    if not rec or rec == "_meta":
        return None
    uns = rec.get("un") or []
    labels = [{"raw": l, "hint": _label_hint(l)} for l in (rec.get("labels") or [])]
    if not uns and not labels:
        return None
    return {"un": uns, "labels": labels,
            "source": rec.get("source", "PubChem / DOT (NIH, public domain)"),
            "needs_review": True,
            "note": "Номер ООН — международный (совпадает с ДОПОГ). Несколько номеров = разные формы "
                    "(безводный/раствор/смесь) — выберите по реальному продукту. Гид — ERG-2024."}


def count():
    d = _load()
    return sum(1 for k, v in d.items() if v and k != "_meta")
