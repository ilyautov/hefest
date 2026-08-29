#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Собирает денайлист юридических лиц из приватного реестра площадок.

Зачем: главный инвариант публикации — в репозитории нет сведений о юридических лицах
(DATA-LICENSE.md, раздел 4). Сторож `guard.sh` проверяет это по списку названий, а список
легко отстаёт от данных: добавили площадку — сторож её не знает и молча пропускает утечку.
Скрипт делает список производным от данных, а не рукописным.

Список лежит ВНЕ репозитория (`.private/entities-denylist.txt`, каталог в .gitignore):
публичный код не должен носить перечень реальных компаний.

  python3 scripts/sync_denylist.py           # переписать список
  python3 scripts/sync_denylist.py --check   # только проверить, что не отстал (для guard)

Что попадает в список: название площадки, его вариант без скобок, содержимое скобок,
домен сайта и различающая метка домена. Что НЕ попадает: разговорные псевдонимы, которые
совпадают с названиями веществ («корунд» — абразив, «тосол» — этиленгликоль, «синтанол» —
ПАВ из СанПиН). Такой псевдоним в денайлисте сделал бы сторож вечно красным на легальной
химии, а сторож, который всегда красный, — это сторож, который отключают.
"""
import json
import os
import re
import sys

КОРЕНЬ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
РЕЕСТР = os.path.join(КОРЕНЬ, "data", "plants.json")
АЛИАСЫ = os.path.join(КОРЕНЬ, "data", "plant_aliases.json")
СПИСОК = os.path.join(КОРЕНЬ, ".private", "entities-denylist.txt")
ХИМИЯ = ("data/substances_all.json", "data/sanpin_atmo.json", "data/substances.json")

ШАПКА = """# Денайлист юридических лиц и их доменов для scripts/guard.sh.
# ЛЕЖИТ ВНЕ РЕПОЗИТОРИЯ (.private/ в .gitignore): публичный код не носит список компаний.
#
# НЕ ПРАВИТЬ РУКАМИ — файл собирается из data/plants.json и data/plant_aliases.json:
#   python3 scripts/sync_denylist.py
# guard.sh падает, если список отстал от реестра.
#
# Псевдонимы, совпадающие с названиями веществ, исключены намеренно (см. докстринг скрипта).
"""


def _химические_слова():
    """Слова, встречающиеся как названия веществ: их нельзя вносить в денайлист."""
    слова = set()
    for отн in ХИМИЯ:
        путь = os.path.join(КОРЕНЬ, отн)
        if not os.path.isfile(путь):
            continue
        try:
            данные = json.load(open(путь, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        # Берём КАЖДУЮ строку файла, а не только поле name: «тосолов» живёт в описании
        # этиленгликоля, «синтанолу» — в названии моющего средства. Пропустить такое поле
        # значит внести химический корень в денайлист и сделать сторож вечно красным.
        стек = [данные]
        while стек:
            узел = стек.pop()
            if isinstance(узел, dict):
                слова.update(
                    w for k in узел if isinstance(k, str)
                    for w in re.findall(r"[а-яёa-z]{4,}", k.lower())
                )
                стек.extend(узел.values())
            elif isinstance(узел, list):
                стек.extend(узел)
            elif isinstance(узел, str):
                слова.update(re.findall(r"[а-яёa-z]{4,}", узел.lower()))
    return слова


def собрать():
    if not os.path.isfile(РЕЕСТР):
        return None
    имена = set()
    for площадка in json.load(open(РЕЕСТР, encoding="utf-8")):
        название = (площадка.get("plant") or "").strip()
        if название:
            имена.add(название)
            имена.add(re.sub(r"\s*\([^)]*\)", "", название).strip())
            имена.update(m.strip() for m in re.findall(r"\(([^)]+)\)", название))
        сайт = (площадка.get("website") or "").strip()
        if сайт:
            хост = сайт.split("/")[0]
            имена.add(хост)
            метка = хост.split(".")[0]
            if len(метка) >= 4:
                имена.add(метка)

    химия = _химические_слова()
    if os.path.isfile(АЛИАСЫ):
        алиасы = json.load(open(АЛИАСЫ, encoding="utf-8")).get("aliases") or {}
        for ключ in алиасы:
            ключ = ключ.strip()
            # псевдоним берём, только если ни одно его слово не встречается внутри
            # названия вещества. Сравнение по вхождению, а не по равенству: в корпусе
            # лежит «акриловая», «тосолов», «синтанолу» — корень «акрилов» равен ничему,
            # но является частью легальной химии, и в денайлисте ему не место.
            слова = re.findall(r"[а-яёa-z]{4,}", ключ.lower())
            if слова and not any(any(w in х for х in химия) for w in слова):
                имена.add(ключ)

    return {n for n in имена if len(n) >= 4}


def прочитать():
    if not os.path.isfile(СПИСОК):
        return set()
    return {
        строка.strip()
        for строка in open(СПИСОК, encoding="utf-8")
        if строка.strip() and not строка.startswith("#")
    }


def main():
    нужно = собрать()
    if нужно is None:
        print("реестр площадок не подключён — денайлист не собрать, пропуск")
        return 0

    есть = прочитать()
    отстало = {n for n in нужно if not any(n.lower() == e.lower() for e in есть)}

    if "--check" in sys.argv:
        if отстало:
            print("денайлист отстал от реестра, не хватает названий: %d" % len(отстало))
            print("  почини: python3 scripts/sync_denylist.py")
            return 1
        print("денайлист покрывает реестр: %d записей" % len(есть))
        return 0

    итог = sorted(нужно | есть, key=str.lower)
    os.makedirs(os.path.dirname(СПИСОК), exist_ok=True)
    with open(СПИСОК, "w", encoding="utf-8") as ф:
        ф.write(ШАПКА + "\n".join(итог) + "\n")
    print("денайлист собран: %d записей (+%d)" % (len(итог), len(итог) - len(есть)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
