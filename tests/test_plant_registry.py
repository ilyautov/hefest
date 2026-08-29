"""Реестр предприятий: названия живут в данных, а не в коде.

Публичная публикация проекта требует, чтобы подмена реестра на обезличенный действительно
обезличивала систему целиком. Пока названия зашиты в исходник, это невозможно.
"""
import json
import os
import re

import pytest

from conftest import DATA, ENGINE


@pytest.fixture(scope="module")
def ретривер():
    pytest.importorskip("sklearn")
    import retriever
    # lexical=False: TF-IDF по 26k чанков не нужен, проверяем только распознавание площадок.
    return retriever.HybridRetriever(lexical=False)


class TestНазванияНеЗахардкожены:

    def test_в_исходнике_ретривера_нет_словаря_реальных_названий(self):
        with open(os.path.join(ENGINE, "retriever.py"), encoding="utf-8") as fh:
            исходник = fh.read()
        # Псевдонимы площадок обязаны приходить из data/plant_aliases.json.
        assert "plant_aliases" in исходник
        for имя in ("ПЛОЩАДКА", "ПЛОЩАДКА", "ПЛОЩАДКА"):
            assert имя not in исходник.lower(), f"название «{имя}» зашито в код"

    def test_реестр_читается_из_переменной_окружения(self):
        with open(os.path.join(ENGINE, "retriever.py"), encoding="utf-8") as fh:
            assert 'os.getenv("PLANTS_FILE"' in fh.read()


class TestРаспознаваниеПлощадки:

    def test_площадка_находится_по_разговорному_псевдониму(self, ретривер):
        assert ретривер._plant_scope("что опасного на заводе корунд")

    def test_площадка_находится_по_собственному_названию(self, ретривер):
        любая = next(iter(ретривер.plants))
        assert ретривер._plant_scope(f"что хранится на площадке {любая}")

    def test_специфичный_триггер_не_перехватывается_общим(self, ретривер):
        """«ПЛОЩАДКА» не должен уезжать в другую площадку по общему токену «синтез»."""
        триггеры = list(ретривер.plant_triggers)
        длины = [len(т) for т in триггеры]
        assert длины == sorted(длины, reverse=True), \
            "триггеры обязаны проверяться от длинных к коротким"

    def test_все_цели_триггеров_существуют_в_реестре(self, ретривер):
        битые = [цель for цель in ретривер.plant_triggers.values() if цель not in ретривер.plants]
        assert not битые, f"триггер указывает на несуществующую площадку: {битые[:3]}"

    def test_запрос_без_площадки_не_даёт_ложного_скоупа(self, ретривер):
        assert ретривер._plant_scope("первая помощь при ожоге кислотой") is None


class TestОбезличиваниеПолное:

    def test_словарь_псевдонимов_валиден_и_бьётся_с_реестром(self):
        путь = os.path.join(DATA, "plant_aliases.json")
        if not os.path.exists(путь):
            pytest.skip("словарь псевдонимов отсутствует — режим без псевдонимов допустим")
        with open(путь, encoding="utf-8") as fh:
            данные = json.load(fh)
        assert "aliases" in данные and данные["aliases"]
        assert all(псевдоним == псевдоним.lower() for псевдоним in данные["aliases"]), \
            "псевдонимы сравниваются в нижнем регистре"

    def test_обезличенный_реестр_не_содержит_идентификаторов(self):
        путь = os.path.join(DATA, "plants_linked_demo.json")
        if not os.path.exists(путь):
            pytest.skip("обезличенный реестр не собран (engine/anonymize_plants.py)")
        with open(путь, encoding="utf-8") as fh:
            текст = fh.read()
        assert not re.search(r'"inn"\s*:', текст), "ИНН обязан быть удалён"
        assert not re.search(r'"website"\s*:', текст), "сайт обязан быть удалён"
        данные = json.loads(текст)
        assert all(з.get("anonymized") for з in данные["plants"])
        assert all("Химическое предприятие" in з["plant"] for з in данные["plants"])
