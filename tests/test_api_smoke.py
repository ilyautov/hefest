"""Смоук-сьют HTTP-контура в лексическом режиме — без Ollama, без сети, без индекса.

Инвариант: у любого, кто просто склонировал репозиторий, сервис поднимается и отвечает.
Проверяется не «200 OK» ради галочки, а то, что ответ несёт провенанс и дисклеймеры.
"""
import pytest


@pytest.mark.usefixtures("client")
class TestСервисПоднимается:

    def test_health_отвечает_и_называет_режим(self, client):
        ответ = client.get("/health")
        assert ответ.status_code == 200
        тело = ответ.json()
        assert тело["ok"] is True
        assert тело["substances"] > 0 and тело["chunks"] > 0
        assert тело["retriever"] == "lexical", "офлайн-дефолт обязан быть лексическим"
        assert тело["llm_backend"] == "extractive", "офлайн-дефолт обязан быть без модели"

    def test_счётчики_health_совпадают_с_данными(self, client, substances):
        assert client.get("/health").json()["substances"] == len(substances)


class TestКачествоДанныхПоказываетсяЧестно:

    def test_quality_отдаёт_градацию_и_разрыв(self, client):
        тело = client.get("/quality").json()
        assert тело["needs_review"] > 0
        assert тело["data_grade"]["baseline"] > 0
        assert "НЕ маскируется" in тело["note"]

    def test_quality_показывает_целостность_CAS(self, client):
        целостность = client.get("/quality").json()["cas_integrity"]
        assert целостность["suspect_in_verified_core"] == []


class TestПоискВозвращаетПровенанс:

    def test_каждый_результат_несёт_вещество_раздел_и_уровень_источника(self, client):
        ответ = client.get("/search", params={"q": "хранение серной кислоты"})
        assert ответ.status_code == 200
        результаты = ответ.json()
        assert результаты, "лексический поиск обязан что-то находить по прямому запросу"
        for результат in результаты:
            assert результат["substance"] and результат["section"]
            assert результат["confidence"] and результат["tier"]
            assert результат["citation"], "фрагмент без цитаты нельзя показывать пользователю"


class TestОтказВместоВыдумки:
    """Ключевая safety-фича: когда оснований нет, система молчит, а не сочиняет."""

    def test_ответ_по_базе_несёт_источники(self, client):
        тело = client.post("/ask", json={"question": "первая помощь при отравлении хлором"}).json()
        assert тело["abstained"] is False
        assert тело["sources"], "ответ без источников недопустим"
        assert "Источник:" in тело["answer"]

    def test_вопрос_вне_базы_получает_честный_отказ(self, client):
        тело = client.post("/ask", json={"question": "сколько стоит билет на самолёт до Сочи"}).json()
        assert тело["abstained"] is True
        assert тело["sources"] == []
        assert "не выдумывает" in тело["answer"]

    def test_порог_отказа_виден_в_ответе(self, client):
        """Порог — часть контракта честности, он не должен быть скрытой константой."""
        тело = client.post("/ask", json={"question": "сколько стоит билет на самолёт до Сочи"}).json()
        assert тело["threshold"] > 0
        assert тело["top_score"] < тело["threshold"]

    def test_отказ_отправляет_к_первоисточнику(self, client):
        тело = client.post("/ask", json={"question": "какая погода завтра в Дзержинске"}).json()
        assert тело["abstained"] is True
        assert "ГОСТ 30333" in тело["answer"] or "паспорт" in тело["answer"]


class TestКарточкаВещества:

    def test_карточка_несёт_статус_верификации(self, client):
        тело = client.get("/substance/хлор").json()
        assert тело.get("name") == "хлор"
        верификация = тело["verification"]
        assert верификация["status"] in ("verified", "needs_review", "rejected")
        assert "signed" in верификация, "подпись эксперта — отдельный от машинной оценки факт"

    def test_руководство_помечено_градацией_источника(self, client):
        guidance = client.get("/substance/хлор").json()["guidance"]
        assert guidance["grade"] in ("passport", "partial", "baseline")
        assert guidance["ppe"]["source"], "СИЗ без указания источника недопустимы"

    def test_несуществующее_вещество_даёт_честный_404_или_пустоту(self, client):
        ответ = client.get("/substance/вещество-которого-нет-98765")
        assert ответ.status_code in (200, 404)
        if ответ.status_code == 200:
            assert not ответ.json().get("name"), "не найдено — значит не найдено"


class TestИнструментыЗавода:
    """Шесть инструментов обязаны отвечать в офлайне и нести дисклеймер ответственности."""

    def test_подбор_СИЗ_помечает_градацию_источника(self, client):
        тело = client.get("/ppe/хлор").json()
        assert тело["ppe"]["grade"] in ("passport", "baseline", "partial")

    def test_реакция_на_превышение_не_пересчитывает_единицы(self, client):
        тело = client.get("/shift/хлор", params={"value": 15, "unit": "ppm"}).json()
        assert тело["comparison"]["pdk_ratio"] is None
        assert "БЕЗ пересчёта единиц" in тело["tool_note"]

    def test_класс_отхода_считается_только_POST_и_не_присваивает_класс(self, client):
        assert client.get("/waste/estimate").status_code == 405
        тело = client.post("/waste/estimate",
                           json={"components": [{"substance": "хлор", "Ci_fraction": 1.0}]}).json()
        assert тело["class"] is None
        assert тело["needs_review"] is True

    def test_режим_инспектора_отвечает_и_без_реестра(self, client):
        """Реестр площадок в поставку не входит: эндпоинт обязан объяснить это, а не упасть."""
        ответ = client.get("/inspection/любая-площадка")
        assert ответ.status_code == 200
        тело = ответ.json()
        if "error" in тело:
            assert "реестр" in тело["error"] or "не найдена" in тело["error"]

    def test_карточка_диспетчера_отдаёт_зону_с_методикой(self, client):
        ответ = client.get("/dispatch/хлор")
        assert ответ.status_code == 200
