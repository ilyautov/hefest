# -*- coding: utf-8 -*-
"""
Недеструктивное применение обогащения АХОВ (data/ahov_enrich.json) к substances_clean.json.

Режимы записи на вещество (_mode):
  fill_empty — заполнить ТОЛЬКО пустые поля существующего вещества (не перетирать данные);
  add        — добавить новое вещество, если его ещё нет.

Перед записью делает резервную копию substances_clean.json -> substances_clean.bak.json.
Помечает обогащённые/добавленные записи "enriched": true. Идемпотентно.
"""
import os, json, shutil

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
SUBS = os.path.join(DATA, "substances_clean.json")
ENR = os.path.join(DATA, "ahov_enrich.json")
BAK = os.path.join(DATA, "substances_clean.bak.json")

# Полная схема поля -> дефолт (чтобы новые вещества имели тот же набор ключей).
SCHEMA = ["name", "formula", "cas", "pdk_mgm3", "hazard_class", "ghs", "storage",
          "ppe", "first_aid", "flash_point_c", "special", "source_tier", "confidence", "skin_hazard"]


def main():
    subs = json.load(open(SUBS, encoding="utf-8"))
    enr = json.load(open(ENR, encoding="utf-8"))["enrich"]
    by_name = {s["name"].lower(): s for s in subs}

    if not os.path.exists(BAK):
        shutil.copy(SUBS, BAK)
        print(f"[backup] {os.path.basename(BAK)}")

    filled, added, skipped = 0, 0, 0
    for name, e in enr.items():
        mode = e.get("_mode", "fill_empty")
        payload = {k: v for k, v in e.items() if not k.startswith("_") and not k.endswith("_legacy")}
        cur = by_name.get(name.lower())

        if mode == "add":
            if cur:
                # вещество уже есть -> ведём себя как fill_empty (идемпотентность)
                mode = "fill_empty"
            else:
                rec = {k: None for k in SCHEMA}
                rec.update({"name": name, "ghs": [], "skin_hazard": False})
                rec.update(payload)
                rec["enriched"] = True
                subs.append(rec); by_name[name.lower()] = rec
                added += 1
                print(f"[add ] {name}")
                continue

        if mode == "fill_empty":
            if not cur:
                print(f"[skip] {name}: нет в базе для fill_empty"); skipped += 1; continue
            changed = []
            for k, v in payload.items():
                old = cur.get(k)
                empty = old in (None, "", [], "О") or (isinstance(old, list) and not old)
                if empty and v not in (None, "", []):
                    cur[k] = v; changed.append(k)
            if changed:
                cur["enriched"] = True
                filled += 1
                print(f"[fill] {name}: {', '.join(changed)}")
            else:
                skipped += 1
                print(f"[noop] {name}: пустых полей не осталось")

    json.dump(subs, open(SUBS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nИтог: добавлено {added}, обогащено {filled}, без изменений {skipped}. Всего веществ: {len(subs)}")


if __name__ == "__main__":
    main()
