"""Святое правило, часть 1: единицы измерения НЕ пересчитываются.

Цена ошибки — здоровье человека. Пересчёт ppm ↔ мг/м³ требует молярной массы и условий;
система его не делает никогда. Если единицы измеренного значения и порога расходятся —
кратность не считается, а пользователю честно говорят «сверьте вручную».

Эти тесты — контракт: если кто-то однажды «добавит удобный автопересчёт», сьют упадёт.
"""
import pytest

import shift_alert


class TestНормализацияЕдиниц:
    """_norm_unit приводит написание к каноническому виду, но НЕ конвертирует величины."""

    @pytest.mark.parametrize("written", ["мг/м3", "мг/м³", "mg/m3", "МГ/М3", " мг/м³ "])
    def test_варианты_написания_мг_м3_сводятся_к_одному(self, written):
        assert shift_alert._norm_unit(written) == "мг/м³"

    @pytest.mark.parametrize("written", ["ppm", "PPM", "млн-1", "частей/млн"])
    def test_варианты_написания_ppm_сводятся_к_одному(self, written):
        assert shift_alert._norm_unit(written) == "ppm"

    def test_ppm_и_мг_м3_остаются_разными_единицами(self):
        assert shift_alert._norm_unit("ppm") != shift_alert._norm_unit("мг/м³")

    def test_нераспознанная_единица_не_подменяется_догадкой(self):
        assert shift_alert._norm_unit("объёмных %") == "объёмных %"


class TestКратностьПДК:
    """Кратность считается ТОЛЬКО при совпадении единиц."""

    @staticmethod
    def _порог(value, unit, present=True):
        return {"present": present, "numeric": value, "value": value, "unit": unit}

    def test_единицы_совпали_кратность_посчитана(self):
        comparison, severity = shift_alert._compare(
            measured_num=3.0, measured_unit_norm="мг/м³",
            pdk=self._порог(1.0, "мг/м³"), idlh=self._порог(None, None, present=False))
        assert comparison["pdk_ratio"] == 3.0
        assert comparison["pdk_exceeded"] is True
        assert severity["code"] == "above_pdk"

    def test_единицы_разошлись_кратность_НЕ_считается(self):
        comparison, severity = shift_alert._compare(
            measured_num=15.0, measured_unit_norm="ppm",
            pdk=self._порог(1.0, "мг/м³"), idlh=self._порог(None, None, present=False))
        assert comparison["pdk_ratio"] is None, "пересчёт ppm→мг/м³ запрещён"
        assert comparison["units_match_pdk"] is False
        assert "не пересчитываем" in comparison["pdk_ratio_reason"]
        assert severity["code"] == "undetermined"

    def test_разные_единицы_не_дают_вердикта_превышения(self):
        comparison, _ = shift_alert._compare(
            measured_num=10_000.0, measured_unit_norm="ppm",
            pdk=self._порог(1.0, "мг/м³"), idlh=self._порог(10.0, "мг/м³"))
        assert comparison["pdk_exceeded"] is None
        assert comparison["idlh_exceeded"] is None, "огромное число в чужих единицах — всё равно не вердикт"

    def test_порога_нет_в_данных_честный_пропуск(self):
        comparison, severity = shift_alert._compare(
            measured_num=5.0, measured_unit_norm="мг/м³",
            pdk=self._порог(None, None, present=False), idlh=self._порог(None, None, present=False))
        assert comparison["pdk_ratio"] is None
        assert "нет в данных" in comparison["pdk_ratio_reason"]
        assert severity["code"] == "undetermined"

    def test_нечисловой_порог_не_парсится_на_глаз(self):
        comparison, _ = shift_alert._compare(
            measured_num=5.0, measured_unit_norm="мг/м³",
            pdk={"present": True, "numeric": None, "value": "0,3/0,1", "unit": "мг/м³"},
            idlh=self._порог(None, None, present=False))
        assert comparison["pdk_ratio"] is None
        assert comparison["pdk_comparable"] is False

    def test_деление_на_нулевой_порог_не_роняет_и_не_врёт(self):
        comparison, _ = shift_alert._compare(
            measured_num=5.0, measured_unit_norm="мг/м³",
            pdk=self._порог(0.0, "мг/м³"), idlh=self._порог(None, None, present=False))
        assert comparison["pdk_ratio"] is None


class TestСквознойСценарийСмены:
    """assess_exceedance целиком: измерение газоанализатора → вердикт."""

    @staticmethod
    def _вещество(subs, имя):
        for rec in subs:
            if (rec.get("name") or "").strip().lower() == имя:
                return rec
        pytest.skip(f"вещества «{имя}» нет в базе — сценарный тест пропущен")

    def test_хлор_15_ppm_выше_IDLH_но_кратность_ПДК_не_считается(self, substances):
        out = shift_alert.assess_exceedance(self._вещество(substances, "хлор"), value=15, unit="ppm")
        assert out["severity"]["code"] == "above_idlh"
        assert out["comparison"]["pdk_ratio"] is None, "ПДК хлора в мг/м³ — кратность к ppm запрещена"
        assert "БЕЗ пересчёта единиц" in out["tool_note"], "дисклеймер о непересчёте единиц обязателен"

    def test_вещество_без_порогов_не_получает_вердикт(self, substances):
        out = shift_alert.assess_exceedance(
            {"name": "вымышленное вещество без данных"}, value=5, unit="мг/м³")
        assert out["severity"]["code"] == "undetermined"
        assert out["severity"]["level"] == -1

    def test_у_вердикта_всегда_есть_обоснование(self, substances):
        out = shift_alert.assess_exceedance(self._вещество(substances, "хлор"), value=15, unit="ppm")
        assert out["severity"]["basis"], "вердикт без основания — это догадка"
