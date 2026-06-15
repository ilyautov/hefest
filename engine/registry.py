# -*- coding: utf-8 -*-
"""
Реестр химикатов по площадкам + авто-аудит несовместимости хранения.

Делает совместимость хранения ПРИМЕНИМОЙ в реальных условиях: для каждого завода берём
его вещества (связка plants_linked) и автоматически находим опасные пары для совместного
хранения (через compat). Поля количества/места/ответственного — заполняются пользователем
(не выдумываем), но опасные сочетания видны сразу из имеющихся данных.
"""
import compat, baseline


def registry(plant_obj, subs_by_name):
    """Список веществ площадки с классом/ПДК/группой/полнотой данных."""
    rows = []
    for name in plant_obj.get("matched_substances", []):
        s = subs_by_name.get(name.lower())
        if not s:
            continue
        rows.append({
            "name": s["name"], "formula": s.get("formula"), "cas": s.get("cas"),
            "hazard_class": s.get("hazard_class"), "pdk_mgm3": s.get("pdk_mgm3"),
            "groups": [compat.GROUPS[g] for g in compat.classify(s)],
            "data_grade": baseline.data_grade(s),
        })
    rows.sort(key=lambda r: (str(r["hazard_class"] or "9"), r["name"]))
    return rows


def conflicts(plant_obj, subs_by_name):
    """Пары веществ площадки, опасные для совместного хранения (forbidden/caution)."""
    names = [n for n in plant_obj.get("matched_substances", []) if n.lower() in subs_by_name]
    out = []
    rank = {"forbidden": 2, "caution": 1}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = subs_by_name[names[i].lower()], subs_by_name[names[j].lower()]
            r = compat.check(a, b)
            if r["verdict"] in rank:
                out.append({"a": a["name"], "b": b["name"], "verdict": r["verdict"],
                            "why": r["reasons"][0]["why"] if r["reasons"] else ""})
    out.sort(key=lambda x: -rank[x["verdict"]])
    return out


def summary(plant_obj, subs_by_name):
    rows = registry(plant_obj, subs_by_name)
    conf = conflicts(plant_obj, subs_by_name)
    return {
        "plant": plant_obj.get("plant"), "inn": plant_obj.get("inn"),
        "substances_total": len(rows),
        "forbidden_pairs": sum(1 for c in conf if c["verdict"] == "forbidden"),
        "caution_pairs": sum(1 for c in conf if c["verdict"] == "caution"),
        "rows": rows, "conflicts": conf,
        "note": "Опасные пары найдены автоматически по матрице совместимости. Количество, место "
                "хранения и ответственного заполняет пользователь — эти данные не синтезируются.",
    }
