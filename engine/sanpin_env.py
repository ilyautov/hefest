# -*- coding: utf-8 -*-
"""
Потребитель экологических ПДК из СанПиН 1.2.3685-21 (официальный нормативный акт РФ, ст. 1259 п.6 ГК —
не охраняется авторским правом):
  - ПДК атмосферного воздуха населённых мест  (data/sanpin_atmo.json, Табл. 1.1)
  - ПДК воды водных объектов                   (data/sanpin_water.json, Табл. 3.13) — если собрана

Зачем отдельно от sanpin.py: тот модуль — про воздух РАБОЧЕЙ ЗОНЫ (где работает персонал). Здесь —
про НАСЕЛЁННЫЕ МЕСТА и ВОДУ (что уходит за забор при выбросе/разливе). Это разные нормативы и разные
решения (экологический контроль, оповещение населения, сбросы). Путать их нельзя — цена ошибки = здоровье.

ПРИНЦИП БЕЗОПАСНОСТИ: значения отдаются как в официальном акте, с провенансом и needs_review. Ничего
не пересчитываем. Атмосферный ПДК показываем ОТДЕЛЬНО и подписанным, чтобы не спутать с ПДК рабочей зоны.
"""
import os, json

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
_PATHS = {"atmo": os.path.join(DATA, "sanpin_atmo.json"),
          "water": os.path.join(DATA, "sanpin_water.json")}
_CACHE, _MTIME = {}, {}


def _load(kind):
    p = _PATHS[kind]
    try:
        m = os.path.getmtime(p)
    except OSError:
        _CACHE[kind] = {}; return {}
    if _CACHE.get(kind) is None or _MTIME.get(kind) != m:
        try:
            _CACHE[kind] = json.load(open(p, encoding="utf-8"))
        except Exception:
            _CACHE[kind] = {}
        _MTIME[kind] = m
    return _CACHE.get(kind, {})


def _lookup(kind, cas, name):
    d = _load(kind)
    if not d:
        return None
    if cas and cas in d:
        return d[cas]
    if name:
        r = d.get("_by_name", {}).get(name.lower())
        if r:
            return r
    return None


def atmo_for(cas, name=None):
    """ПДК (или ОБУВ — ориентир.) атмосферного воздуха населённых мест по CAS/имени или None."""
    r = _lookup("atmo", cas, name)
    if not r:
        return None
    if r.get("norm_type") == "ОБУВ":
        if not r.get("obuv_raw"):
            return None
        return {
            "norm_type": "ОБУВ", "obuv": r.get("obuv_raw"),
            "source": r.get("source"), "needs_review": True,
            "note": "ОБУВ — ориентировочный безопасный уровень воздействия (атмосфера населённых мест), "
                    "для веществ без утверждённого ПДК. Слабее ПДК по статусу. Официальный акт; сверьте.",
        }
    if not (r.get("pdk_mr_raw") or r.get("pdk_ss_raw") or r.get("emission_prohibited")):
        return None
    return {
        "norm_type": "ПДК",
        "pdk_mr": r.get("pdk_mr_raw"), "pdk_ss": r.get("pdk_ss_raw"),
        "limit": r.get("limit"), "hazard_class": r.get("hazard_class"),
        "emission_prohibited": r.get("emission_prohibited"),
        "source": r.get("source"), "needs_review": True,
        "note": "ПДК АТМОСФЕРНОГО воздуха населённых мест (не рабочей зоны). "
                "Официальный акт; сверьте с действующей редакцией.",
    }


def water_for(cas, name=None):
    """ПДК (или ОДУ — ориентир.) воды водных объектов по CAS/имени или None."""
    r = _lookup("water", cas, name)
    if not r:
        return None
    if r.get("norm_type") == "ОДУ":
        if not r.get("odu_raw"):
            return None
        return {
            "norm_type": "ОДУ", "odu": r.get("odu_raw"), "lpv": r.get("lpv"),
            "hazard_class": r.get("hazard_class"), "source": r.get("source"), "needs_review": True,
            "note": "ОДУ — ориентировочный допустимый уровень в воде, для веществ без утверждённого ПДК. "
                    "Слабее ПДК по статусу. Официальный акт; сверьте.",
        }
    if not r.get("pdk_raw"):
        return None
    return {
        "norm_type": "ПДК",
        "pdk": r.get("pdk_raw"), "lpv": r.get("lpv"), "hazard_class": r.get("hazard_class"),
        "source": r.get("source"), "needs_review": True,
        "note": "ПДК воды водных объектов хоз.-питьевого/культ.-бытового водопользования. "
                "Официальный акт; сверьте с действующей редакцией.",
    }


def for_substance(cas, name=None):
    """Сводка экологических ПДК для карточки: {atmo, water} (что есть) или None."""
    a, w = atmo_for(cas, name), water_for(cas, name)
    if not a and not w:
        return None
    out = {}
    if a:
        out["atmo"] = a
    if w:
        out["water"] = w
    return out


def counts():
    a = _load("atmo"); w = _load("water")
    na = sum(1 for k, v in a.items() if k not in ("_meta", "_by_name") and v)
    nw = sum(1 for k, v in w.items() if k not in ("_meta", "_by_name") and v)
    return {"atmo_substances": na, "water_substances": nw}
