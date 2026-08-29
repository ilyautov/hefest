# -*- coding: utf-8 -*-
"""Нормализация прочерков в поле CAS: «-» / «—» → пустое поле.

Зачем. В таблицах ГН прочерк означает «значения нет». Донесённый до карточки как есть, он
превращается в строку «регистрационный номер CAS -.», которую читатель принимает за
идентификатор. Пропуск должен выглядеть как пропуск.

Что скрипт делает: заменяет плейсхолдер на пустую строку в карточках веществ и
перегенерирует затронутые чанки корпуса (только раздел 1, только для этих веществ).
Чего НЕ делает: не подбирает «настоящий» CAS. Отсутствующий номер остаётся отсутствующим.

    python3 engine/fix_cas_placeholders.py --dry-run   # показать, что изменится
    python3 engine/fix_cas_placeholders.py             # применить
"""
import argparse
import json
import os
import sys

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
ПЛЕЙСХОЛДЕРЫ = {"-", "—", "–", "n/a", "нет", "unknown", "0-00-0"}
ФАЙЛЫ_ВЕЩЕСТВ = ["substances_clean.json", "substances_all.json", "substances_bulk.json"]
ФАЙЛЫ_КОРПУСА = ["corpus_full_clean.json", "corpus_full.json"]


def _плейсхолдер(значение) -> bool:
    return str(значение or "").strip().lower() in ПЛЕЙСХОЛДЕРЫ


def _путь(имя):
    return os.path.join(_DATA, имя)


def почистить(применять: bool) -> int:
    затронутые = set()

    for имя in ФАЙЛЫ_ВЕЩЕСТВ:
        путь = _путь(имя)
        if not os.path.exists(путь):
            continue
        with open(путь, encoding="utf-8") as fh:
            записи = json.load(fh)
        изменено = 0
        for запись in записи:
            if _плейсхолдер(запись.get("cas")):
                затронутые.add(запись.get("name"))
                изменено += 1
                if применять:
                    запись["cas"] = ""
        print(f"{имя}: плейсхолдеров CAS — {изменено}")
        if применять and изменено:
            with open(путь, "w", encoding="utf-8") as fh:
                json.dump(записи, fh, ensure_ascii=False, indent=1)

    for имя in ФАЙЛЫ_КОРПУСА:
        путь = _путь(имя)
        if not os.path.exists(путь):
            continue
        with open(путь, encoding="utf-8") as fh:
            корпус = json.load(fh)
        изменено = 0
        for чанк in корпус.get("chunks", []):
            if чанк.get("substance") not in затронутые:
                continue
            if _плейсхолдер(чанк.get("cas")):
                изменено += 1
                if применять:
                    чанк["cas"] = ""
                    чанк["text"] = (чанк["text"]
                                    .replace("регистрационный номер CAS -.",
                                             "регистрационный номер CAS не указан в источнике.")
                                    .replace("регистрационный номер CAS —.",
                                             "регистрационный номер CAS не указан в источнике."))
        print(f"{имя}: чанков с плейсхолдером — {изменено}")
        if применять and изменено:
            with open(путь, "w", encoding="utf-8") as fh:
                json.dump(корпус, fh, ensure_ascii=False)

    print(("применено" if применять else "сухой прогон") + f"; веществ затронуто: {len(затронутые)}")
    for имя in sorted(затронутые):
        print("  ·", имя)
    return len(затронутые)


if __name__ == "__main__":
    парсер = argparse.ArgumentParser(description=__doc__)
    парсер.add_argument("--dry-run", action="store_true", help="только показать, ничего не писать")
    аргументы = парсер.parse_args()
    sys.exit(0 if почистить(применять=not аргументы.dry_run) >= 0 else 1)
