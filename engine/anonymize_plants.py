# -*- coding: utf-8 -*-
"""Обезличивание реестра предприятий для публичной демонстрации.

Зачем. В поставке `plants.json` содержит реальные юрлица с ИНН, а связь «предприятие ↔
вещество» выведена из публичных каталогов продукции — это НЕ инвентаризация опасных веществ
площадки (см. DATA-LICENSE.md, раздел 4). Для публичного демо этого достаточно, чтобы
показать работу поиска по площадке, но не обязательно называть организации.

Скрипт делает копию реестра, в которой:
  · название заменено на «Химическое предприятие №N»,
  · ИНН и сайт удалены,
  · ОКВЭД, продуктовые линейки и связи с веществами СОХРАНЕНЫ — иначе демо теряет смысл.

Что скрипт НЕ делает: не меняет данные о веществах и не трогает нормативные значения.

    python3 engine/anonymize_plants.py            # → data/plants_demo.json + plants_linked_demo.json
    PLANTS_FILE=plants_linked_demo.json python3 -m uvicorn service:app --app-dir engine --port 8012
"""
import json
import os

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

ШАБЛОН_ИМЕНИ = "Химическое предприятие №{номер}"
УДАЛЯЕМЫЕ_ПОЛЯ = ("inn", "website", "address", "phone", "email")


def _обезличить(запись, номер):
    очищенная = {ключ: значение for ключ, значение in запись.items()
                 if ключ not in УДАЛЯЕМЫЕ_ПОЛЯ}
    очищенная["plant"] = ШАБЛОН_ИМЕНИ.format(номер=номер)
    очищенная["anonymized"] = True
    очищенная["anonymization_note"] = (
        "Название организации скрыто. Профиль продукции и связи с веществами сохранены "
        "как демонстрационная модель и не описывают фактическое обращение опасных веществ "
        "на конкретной площадке.")
    return очищенная


def построить():
    исходный = os.path.join(_DATA, "plants.json")
    if not os.path.exists(исходный):
        raise SystemExit("нет data/plants.json — обезличивать нечего")

    with open(исходный, encoding="utf-8") as fh:
        предприятия = json.load(fh)

    переименование = {}
    обезличенные = []
    for номер, запись in enumerate(предприятия, start=1):
        новая = _обезличить(запись, номер)
        переименование[запись.get("plant")] = новая["plant"]
        обезличенные.append(новая)

    путь_реестра = os.path.join(_DATA, "plants_demo.json")
    with open(путь_реестра, "w", encoding="utf-8") as fh:
        json.dump(обезличенные, fh, ensure_ascii=False, indent=1)
    print(f"data/plants_demo.json: {len(обезличенные)} записей обезличено")

    # Связанный индекс, который читает сервис, — перестраиваем той же подстановкой имён,
    # чтобы не гонять полную пересборку корпуса ради переименования.
    путь_связей = os.path.join(_DATA, "plants_linked.json")
    if not os.path.exists(путь_связей):
        print("data/plants_linked.json не найден — пропускаю связанный индекс")
        return

    with open(путь_связей, encoding="utf-8") as fh:
        связи = json.load(fh)

    связи["plants"] = [_обезличить(запись, номер)
                       for номер, запись in enumerate(связи["plants"], start=1)]
    связи["substance_to_plants"] = {
        вещество: [переименование.get(имя, имя) for имя in имена]
        for вещество, имена in связи.get("substance_to_plants", {}).items()
    }
    выход = os.path.join(_DATA, "plants_linked_demo.json")
    with open(выход, "w", encoding="utf-8") as fh:
        json.dump(связи, fh, ensure_ascii=False, indent=1)
    print(f"data/plants_linked_demo.json: {len(связи['plants'])} предприятий, "
          f"{len(связи['substance_to_plants'])} веществ со связями")


if __name__ == "__main__":
    построить()
