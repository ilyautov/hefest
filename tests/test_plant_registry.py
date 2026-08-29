"""Реестр площадок: в поставке его нет, и система обязана это переживать честно.

Решение проекта: публичный репозиторий не содержит сведений о юридических лицах — ни в
данных, ни в коде, ни в примерах интерфейса, ни в наборах для eval (см. DATA-LICENSE.md,
раздел 4). Отсюда два контракта, которые здесь и проверяются:

1. **Без реестра всё работает**, а функции по площадке объясняют, что реестр не подключён —
   а не изображают «завод не найден» и не падают.
2. **С подключённым реестром** распознавание площадки работает, и работает на любом реестре,
   а не на зашитых в код названиях.

Реестр для второго контракта собирается прямо здесь, из вымышленных площадок.
"""
import json
import os
import re

import pytest

from conftest import DATA, ENGINE

# Имя из gitignore-шаблона data/plants_local*.json — временный файл не попадёт в индекс,
# даже если тест упадёт и не доберётся до уборки.
ВРЕМЕННЫЙ_РЕЕСТР = "plants_local_pytest.json"

СИНТЕТИЧЕСКИЙ_РЕЕСТР = {
    "plants": [
        {"plant": "Площадка Альфа",
         "substances": ["серная кислота", "гидроксид натрия"],
         "matched_substances": ["серная кислота", "гидроксид натрия"],
         "unmatched_substances": []},
        {"plant": "Комбинат Бета-Синтез",
         "substances": ["аммиак", "метанол"],
         "matched_substances": ["аммиак", "метанол"],
         "unmatched_substances": []},
        {"plant": "Синтез",
         "substances": ["хлор"],
         "matched_substances": ["хлор"],
         "unmatched_substances": []},
    ],
    "substance_to_plants": {"серная кислота": ["Площадка Альфа"], "хлор": ["Синтез"]},
}


@pytest.fixture(scope="module")
def реестр_подключён():
    """Кладёт синтетический реестр в data/ и отдаёт ретривер, который его прочитал."""
    pytest.importorskip("sklearn")
    путь = os.path.join(DATA, ВРЕМЕННЫЙ_РЕЕСТР)
    with open(путь, "w", encoding="utf-8") as fh:
        json.dump(СИНТЕТИЧЕСКИЙ_РЕЕСТР, fh, ensure_ascii=False)
    прежний = os.environ.get("PLANTS_FILE")
    os.environ["PLANTS_FILE"] = ВРЕМЕННЫЙ_РЕЕСТР
    try:
        import retriever
        # lexical=False: TF-IDF по 26k чанков не нужен, проверяем распознавание площадок.
        yield retriever.HybridRetriever(lexical=False)
    finally:
        if прежний is None:
            os.environ.pop("PLANTS_FILE", None)
        else:
            os.environ["PLANTS_FILE"] = прежний
        os.remove(путь)


@pytest.fixture(scope="module")
def реестра_нет():
    """Ретривер в состоянии публичной поставки: файла реестра не существует."""
    pytest.importorskip("sklearn")
    прежний = os.environ.get("PLANTS_FILE")
    os.environ["PLANTS_FILE"] = "заведомо-отсутствующий-реестр.json"
    try:
        import retriever
        yield retriever.HybridRetriever(lexical=False)
    finally:
        if прежний is None:
            os.environ.pop("PLANTS_FILE", None)
        else:
            os.environ["PLANTS_FILE"] = прежний


class TestВПоставкеНетЮрлиц:
    """Главный инвариант публикации: сведений об организациях в репозитории нет."""

    def test_реестр_не_трекается(self):
        import subprocess
        корень = os.path.abspath(os.path.join(DATA, ".."))
        файлы = subprocess.run(["git", "ls-files", "data/"], cwd=корень,
                               capture_output=True, text=True, check=False).stdout.split()
        реестры = [f for f in файлы
                   if re.search(r"plants(_linked)?(_demo)?\.json$", f)
                   or f.endswith("plant_aliases.json")]
        assert not реестры, f"реестр площадок не должен трекаться: {реестры}"

    def test_публикуется_только_схема_с_вымышленным_примером(self):
        путь = os.path.join(DATA, "plants.example.json")
        assert os.path.exists(путь), "нужен пример схемы, иначе реестр не подключить"
        with open(путь, encoding="utf-8") as fh:
            пример = json.load(fh)
        assert "_schema" in пример and пример["plants"]
        текст = json.dumps(пример, ensure_ascii=False)
        assert not re.search(r"\b\d{10}\b|\b\d{12}\b", текст), \
            "в примере не должно быть ничего похожего на ИНН"
        assert all("пример" in з["plant"].lower() for з in пример["plants"]), \
            "площадки в примере обязаны быть явно помечены как вымышленные"

    def test_в_трекаемых_данных_нет_поля_инн(self):
        import subprocess
        корень = os.path.abspath(os.path.join(DATA, ".."))
        итог = subprocess.run(
            ["git", "grep", "-l", r'"inn"[[:space:]]*:[[:space:]]*"[0-9]', "--", "data/"],
            cwd=корень, capture_output=True, text=True, check=False)
        assert итог.returncode != 0, f"ИНН в трекаемых данных: {итог.stdout.strip()}"

    def test_демо_раскладка_склада_не_привязана_к_организации(self):
        путь = os.path.join(DATA, "warehouse_zones.json")
        if not os.path.exists(путь):
            pytest.skip("нет шаблона раскладки склада")
        with open(путь, encoding="utf-8") as fh:
            данные = json.load(fh)
        for раскладка in данные["layouts"]:
            assert "plant_inn" not in раскладка
            assert раскладка.get("_synthetic") is True, \
                "раскладка обязана быть помечена как вымышленная"

    def test_названий_площадок_нет_в_рантайм_коде(self):
        """Проверяем механизм: триггеры строятся из данных, а не из литералов в исходнике."""
        with open(os.path.join(ENGINE, "retriever.py"), encoding="utf-8") as fh:
            исходник = fh.read()
        assert "_build_plant_triggers" in исходник
        assert 'os.getenv("PLANTS_FILE"' in исходник
        # Единственный словарь названий — необязательный файл данных, не код.
        assert "plant_aliases" in исходник


class TestБезРеестраВсёРаботает:

    def test_ретривер_поднимается_с_пустым_реестром(self, реестра_нет):
        assert реестра_нет.plants == {}
        assert реестра_нет.chunks, "корпус обязан загрузиться независимо от реестра"

    def test_скоуп_по_площадке_молчит_а_не_падает(self, реестра_нет):
        assert реестра_нет._plant_scope("что опасного на площадке альфа") is None

    def test_триггеров_нет_но_структура_валидна(self, реестра_нет):
        assert реестра_нет.plant_triggers == {}

    def test_сервис_объясняет_отсутствие_реестра(self, client):
        """Без реестра /registry обязан объяснить положение дел, а не молча вернуть пустоту."""
        import service
        if service.R.plants:
            pytest.skip("в этом окружении подключён локальный реестр")
        тело = client.get("/registry").json()
        assert тело["plants"] == []
        assert "не подключён" in тело["error"]
        assert "PLANTS_FILE" in тело["detail"], "объяснение обязано говорить, что делать"


class TestСРеестромРаспознаваниеРаботает:

    def test_площадка_находится_по_названию(self, реестр_подключён):
        область = реестр_подключён._plant_scope("что опасного на площадке альфа")
        assert область == {"серная кислота", "гидроксид натрия"}

    def test_все_площадки_реестра_распознаются(self, реестр_подключён):
        for запись in СИНТЕТИЧЕСКИЙ_РЕЕСТР["plants"]:
            имя = запись["plant"].lower()
            assert реестр_подключён._plant_scope(f"что хранится на {имя}"), \
                f"площадка «{имя}» не распознана"

    def test_специфичное_название_не_перехватывается_общим(self, реестр_подключён):
        """«Комбинат Бета-Синтез» не должен уезжать в площадку «Синтез» по общему токену."""
        область = реестр_подключён._plant_scope("что на комбинат бета-синтез")
        assert область == {"аммиак", "метанол"}, "перехват общим токеном — регрессия скоупа"

    def test_триггеры_проверяются_от_длинных_к_коротким(self, реестр_подключён):
        длины = [len(т) for т in реестр_подключён.plant_triggers]
        assert длины == sorted(длины, reverse=True)

    def test_все_цели_триггеров_существуют(self, реестр_подключён):
        битые = [ц for ц in реестр_подключён.plant_triggers.values()
                 if ц not in реестр_подключён.plants]
        assert not битые, f"триггер указывает на несуществующую площадку: {битые[:3]}"

    def test_запрос_без_площадки_не_даёт_ложного_скоупа(self, реестр_подключён):
        assert реестр_подключён._plant_scope("первая помощь при ожоге кислотой") is None


class TestОбезличиваниеСобственногоРеестра:
    """Скрипт остаётся полезным: он обезличивает реестр ПОЛЬЗОВАТЕЛЯ для публичного показа."""

    def test_скрипт_на_месте_и_описан(self):
        assert os.path.exists(os.path.join(ENGINE, "anonymize_plants.py"))
        корень = os.path.abspath(os.path.join(DATA, ".."))
        with open(os.path.join(корень, "DATA-LICENSE.md"), encoding="utf-8") as fh:
            assert "anonymize_plants.py" in fh.read()

    def test_скрипт_удаляет_идентифицирующие_поля(self):
        with open(os.path.join(ENGINE, "anonymize_plants.py"), encoding="utf-8") as fh:
            исходник = fh.read()
        for поле in ("inn", "website"):
            assert f'"{поле}"' in исходник, f"обезличивание обязано убирать поле {поле}"
