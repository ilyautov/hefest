"""Святое правило, часть 2: нормативка не выдумывается, пропуски остаются пропусками.

Где данных нет — система обязана сказать «нет данных», а не подставить правдоподобное
число. Где данные типовые (по химической группе), она обязана это пометить, а не выдать
типовое за паспортное. Эти тесты фиксируют оба контракта.
"""
import hygiene
import ppe
import waste_calc


class TestКлассОтходаНеПрисваиваетсяНаГлаз:
    """Приказ 536: без первичных показателей класс не определяется. Никогда."""

    def test_без_показателей_класс_не_присвоен(self):
        out = waste_calc.estimate_waste_class([{"substance": "хлор", "Ci_fraction": 1.0}])
        assert out["class"] is None
        assert out["confidence"] == "insufficient_data"

    def test_итог_всегда_помечен_как_требующий_проверки_эколога(self):
        out = waste_calc.estimate_waste_class([{"substance": "хлор", "Ci_fraction": 1.0}])
        assert out["needs_review"] is True
        assert "эколог" in out["note"]

    def test_видно_чего_именно_не_хватает(self):
        out = waste_calc.estimate_waste_class([{"substance": "хлор", "Ci_fraction": 1.0}])
        assert out["missing_overall"], "honest-gap без перечня недостающего бесполезен"
        assert out["blockers"], "пользователь должен видеть, что догрузить"

    def test_неизвестное_вещество_не_подменяется_похожим(self):
        out = waste_calc.estimate_waste_class(
            [{"substance": "вещество-которого-нет-12345", "Ci_fraction": 1.0}])
        component = out["per_component"][0]
        assert component["matched"] is False
        assert component["wi"] == "нет данных"

    def test_ссылка_на_нормативную_рамку_не_теряется(self):
        out = waste_calc.estimate_waste_class([{"substance": "хлор", "Ci_fraction": 1.0}])
        assert "536" in out["framework_ref"]

    def test_несходящийся_состав_вызывает_предупреждение(self):
        out = waste_calc.estimate_waste_class([{"substance": "хлор", "Ci_fraction": 0.3}])
        assert "сумма долей" in out["note"]


class TestТиповоеНеВыдаётсяЗаПаспортное:
    """Градация источника СИЗ: passport vs baseline. Смешивать их — прямое нарушение правила."""

    def test_паспортные_СИЗ_помечены_как_паспортные_и_имеют_источник(self, substances):
        хлор = next(r for r in substances if r.get("name") == "хлор")
        block = ppe.recommend_ppe(хлор)["ppe"]
        assert block["grade"] == "passport"
        assert block["source"], "паспортное значение без ссылки на источник недопустимо"

    def test_типовые_СИЗ_помечены_и_несут_дисклеймер(self, substances):
        baseline = next(r for r in substances if r.get("confidence") == "needs_review")
        block = ppe.recommend_ppe(baseline)["ppe"]
        assert block["grade"] != "passport"
        assert block["disclaimer"], "типовое без дисклеймера читается как паспортное"
        assert "НЕ из паспорта" in block["source"]

    def test_у_типовых_СИЗ_нет_фальшивой_цитаты(self, substances):
        baseline = next(r for r in substances if r.get("confidence") == "needs_review")
        assert ppe.recommend_ppe(baseline)["ppe"]["citation"] is None


class TestДашбордКачестваНеПриукрашивает:
    """/quality — витрина честности. Она обязана показывать разрыв, а не сглаживать его."""

    def test_градация_полноты_разделена_на_три_уровня(self, substances):
        grades = hygiene.quality_dashboard(substances)["data_grade"]
        assert set(grades) >= {"passport", "baseline"}

    def test_baseline_не_учитывается_как_паспортное(self, substances):
        dash = hygiene.quality_dashboard(substances)
        assert dash["data_grade"]["passport"] < dash["substances"], \
            "если бы всё было паспортным, честная градация была бы фикцией"

    def test_needs_review_не_прячется(self, substances):
        dash = hygiene.quality_dashboard(substances)
        assert dash["needs_review"] > 0
        assert dash["by_confidence"]["needs_review"] == dash["needs_review"]

    def test_пропуски_полей_показаны_явно(self, substances):
        assert hygiene.quality_dashboard(substances)["field_gaps"]

    def test_состояние_паспорта_называет_недостающие_поля(self, substances):
        baseline = next(r for r in substances if r.get("confidence") == "needs_review")
        state = hygiene.passport_state(baseline)
        assert state["state"] == "needs_review"
        assert state["missing"], "«требует проверки» без перечня — пустой ярлык"
