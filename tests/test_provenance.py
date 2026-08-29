"""Провенанс: у каждого значения виден источник и уровень доверия.

Проект утверждает, что не выдаёт нормативку без происхождения. Это проверяемое
утверждение — здесь оно проверяется на всей базе, а не на витринных примерах.
"""
import json
import os

import pytest

import cas
import hygiene
from conftest import DATA

ДОПУСТИМАЯ_ДОСТОВЕРНОСТЬ = {"high", "medium", "low", "needs_review"}
ДОПУСТИМЫЕ_УРОВНИ_ИСТОЧНИКА = {"T1", "T2", "T3", "T1+T2"}


@pytest.fixture(scope="module")
def корпус():
    путь = os.path.join(DATA, "corpus_full_clean.json")
    if not os.path.exists(путь):
        pytest.skip("нет корпуса — проверка провенанса чанков пропущена")
    with open(путь, encoding="utf-8") as fh:
        return json.load(fh)


class TestКаждоеВеществоИмеетПровенанс:

    def test_у_всех_записей_есть_уровень_доверия(self, substances):
        без = [r.get("name") for r in substances if r.get("confidence") not in ДОПУСТИМАЯ_ДОСТОВЕРНОСТЬ]
        assert not без, f"записи без корректного confidence: {без[:5]}"

    def test_у_всех_записей_есть_уровень_источника(self, substances):
        без = [r.get("name") for r in substances
               if r.get("source_tier") not in ДОПУСТИМЫЕ_УРОВНИ_ИСТОЧНИКА]
        assert not без, f"записи без корректного source_tier: {без[:5]}"

    def test_у_каждой_записи_есть_имя(self, substances):
        assert all((r.get("name") or "").strip() for r in substances)

    def test_имена_не_дублируются(self, substances):
        имена = [r.get("name") for r in substances]
        assert len(имена) == len(set(имена)), "дубли имён ломают адресацию карточки"


class TestОтсутствующиеЗначенияОстаютсяПустыми:
    """Пропуск обязан выглядеть как пропуск: пустая строка/None, а не 0 и не выдумка."""

    def test_отсутствующая_ПДК_не_подменяется_нулём(self, substances):
        нули = [r.get("name") for r in substances
                if str(r.get("pdk_mgm3") or "").strip() in ("0", "0.0", "0,0")]
        assert not нули, f"ПДК=0 читается как «безопасно при любой концентрации»: {нули[:5]}"

    def test_часть_ПДК_честно_пуста(self, substances):
        пустых = sum(1 for r in substances if not str(r.get("pdk_mgm3") or "").strip())
        assert пустых > 0, ("если пустых ПДК не осталось ни одной — вероятно, пропуски "
                            "чем-то заполнили; это нарушение святого правила")

    def test_отсутствующий_CAS_остаётся_пустым(self, substances):
        # Пустой CAS — законное состояние. Заглушки-плейсхолдеры недопустимы.
        заглушки = [r.get("name") for r in substances
                    if str(r.get("cas") or "").strip().lower()
                    in ("n/a", "нет", "-", "0-00-0", "unknown")]
        assert not заглушки, f"CAS-заглушки вместо честного пропуска: {заглушки[:5]}"


class TestКонтрольнаяЦифраCAS:
    """CAS — ключ идентичности вещества: по нему подтягивается физхимия, GHS, транспорт.

    Опечатка в номере опасна тем, что может привести чужие данные. Контракт:
    (1) в верифицированном ядре битых номеров нет; (2) битый номер не тянет обогащение
    (fail-closed); (3) их количество видно в /quality, а не спрятано."""

    def test_в_верифицированном_ядре_нет_битых_номеров(self, substances):
        ядро = [r for r in substances if r.get("confidence") != "needs_review"]
        битые = [r["name"] for r in ядро if not cas.check(r.get("cas"))["ok"]
                 and cas.check(r.get("cas"))["status"] != cas.СТАТУС_ПУСТО]
        assert not битые, f"битый CAS в подписанном ядре: {битые}"

    def test_битый_номер_не_приводит_чужое_обогащение(self, substances):
        """Главный страх: неверный CAS совпал с ДРУГИМ реальным веществом и принёс его данные."""
        физхимия = _загрузить("physchem.json")
        битые = [r.get("cas") for r in substances
                 if (r.get("cas") or "").strip() and not cas.is_valid(r.get("cas"))]
        протёкшие = [c for c in битые if физхимия.get(c)]
        assert not протёкшие, f"по некорректному CAS подтянулись данные: {протёкшие[:5]}"

    def test_количество_битых_номеров_видно_в_дашборде(self, substances):
        целостность = hygiene.quality_dashboard(substances)["cas_integrity"]
        assert целостность["checked"] == len(substances)
        assert целостность["suspect_in_verified_core"] == []
        assert "НЕ исправляются автоматически" in целостность["note"]

    def test_карточка_битого_номера_несёт_предупреждение(self, substances):
        битое = next((r for r in substances
                      if (r.get("cas") or "").strip() and not cas.is_valid(r.get("cas"))), None)
        if битое is None:
            pytest.skip("битых CAS в базе нет — предупреждать не о чем")
        состояние = hygiene.passport_state(битое)
        assert состояние["cas_check"]["ok"] is False
        assert "сверьте с первоисточником" in состояние["hint"]

    def test_валидатор_не_чинит_номер_молча(self):
        # 1319-77-2 → верный номер крезола 1319-77-3. Подставлять его самостоятельно нельзя.
        итог = cas.check("1319-77-2")
        assert итог["status"] == cas.СТАТУС_СУММА
        assert итог["cas"] == "1319-77-2", "номер не должен подменяться «похожим верным»"


class TestВерифицированноеЯдроЧистое:

    def test_в_верифицированном_ядре_нет_артефактов_ингеста(self, substances):
        ядро = [r for r in substances if r.get("confidence") != "needs_review"]
        assert ядро, "верифицированное ядро не должно быть пустым"
        артефакты = [r["name"] for r in ядро if "+" in r.get("name", "")
                     or r.get("name", "").strip().startswith(("а)", "б)", "в)"))]
        assert not артефакты, f"артефакты HTML-ингеста просочились в ядро: {артефакты}"

    def test_ядро_меньше_базы_градация_не_фикция(self, substances):
        ядро = [r for r in substances if r.get("confidence") != "needs_review"]
        assert 0 < len(ядро) < len(substances)


class TestЧанкиКорпусаНесутИсточник:

    def test_метаданные_корпуса_называют_стандарт_и_природу_данных(self, корпус):
        meta = корпус["meta"]
        assert "30333" in meta["standard"]
        assert "сгенерирована" in meta["nature"], \
            "корпус обязан прямо говорить, что документ-форма сгенерирована"

    def test_у_каждого_чанка_есть_вещество_раздел_и_уровень_доверия(self, корпус):
        плохие = [c.get("doc_id") for c in корпус["chunks"]
                  if not c.get("substance") or not c.get("section")
                  or c.get("confidence") not in ДОПУСТИМАЯ_ДОСТОВЕРНОСТЬ]
        assert not плохие, f"чанки без провенанса: {плохие[:5]}"

    def test_счётчик_в_метаданных_совпадает_с_фактом(self, корпус):
        assert корпус["meta"]["chunks"] == len(корпус["chunks"])


def _загрузить(имя):
    путь = os.path.join(DATA, имя)
    if not os.path.exists(путь):
        pytest.skip(f"нет файла {имя}")
    with open(путь, encoding="utf-8") as fh:
        return json.load(fh)
