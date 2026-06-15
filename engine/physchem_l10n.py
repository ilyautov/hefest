# -*- coding: utf-8 -*-
"""
Локализация ТЕКСТОВЫХ описаний физико-химических свойств (PubChem-агрегат) на русский.

ГРАНИЦА БЕЗОПАСНОСТИ (важно при «цена ошибки = здоровье»):
  • Переводим ТОЛЬКО словесные описания по выверенному словарю (растворимость, горючесть, агрегатное
    состояние и т.п.).
  • Числа, единицы измерения (°F, °C, mmHg, atm, mg/mL, kPa…) и метки-источники «(NTP, 1992)»,
    «(NIOSH, 2024)» оставляем ДОСЛОВНО. Единицы НЕ пересчитываем (°F не превращаем в °C) — баг в
    пересчёте опаснее английской единицы.
  • Чего нет в словаре — остаётся как есть (по-английски). Это сознательно: лучше частичный перевод,
    чем выдумка. Данные и так помечены needs_review с источником.

Применяется при выдаче в physchem.for_cas(); файл data/physchem.json не мутируется.
"""
import re

# ── 1. Метка-источник в хвосте строки: "(NTP, 1992)", "(NIOSH, 2024)", "(USCG, 1999)", "(approx)" ──
_TAIL = re.compile(
    r"\s*\((?:approx|NTP|NIOSH|USCG|EPA|HSDB|CAMEO|PAC|OSHA|NJ-?DOH)[^()]*\)\s*$",
    re.IGNORECASE,
)

# ── 2. Точные переводы целых описаний (после отрезания хвоста-источника) ──
# Ключи нормализуются: trim + схлопывание пробелов; сравнение регистронезависимое.
_EXACT = {
    # растворимость
    "solubility in water: none": "Растворимость в воде: нет",
    "solubility in water: miscible": "Растворимость в воде: смешивается",
    "solubility in water: reaction": "Растворимость в воде: реагирует с водой",
    "solubility in water: poor": "Растворимость в воде: плохая",
    "solubility in water: very poor": "Растворимость в воде: очень плохая",
    "solubility in water: good": "Растворимость в воде: хорошая",
    "solubility in water: moderate": "Растворимость в воде: умеренная",
    "soluble in water": "Растворим в воде",
    "insoluble in water": "Нерастворим в воде",
    "miscible with water": "Смешивается с водой",
    "slightly soluble in water": "Слабо растворим в воде",
    "soluble (in ethanol)": "Растворим (в этаноле)",
    "insoluble": "Нерастворим",
    "soluble": "Растворим",
    "miscible": "Смешивается",
    "slightly soluble": "Слабо растворим",
    "very soluble": "Хорошо растворим",
    "sparingly soluble": "Малорастворим",
    "freely soluble": "Легко растворим",
    "practically insoluble": "Практически нерастворим",
    "reaction": "Реагирует с водой",
    "negligible": "пренебрежимо мало",
    # агрегатное состояние / горючесть (термины ГОСТ: ЛВЖ — flammable, ГЖ — combustible)
    "noncombustible solid": "Негорючее твёрдое вещество",
    "combustible solid": "Горючее твёрдое вещество",
    "noncombustible liquid": "Негорючая жидкость",
    "combustible liquid": "Горючая жидкость (ГЖ)",
    "flammable liquid": "Легковоспламеняющаяся жидкость (ЛВЖ)",
    "nonflammable gas": "Негорючий газ",
    "flammable gas": "Горючий газ",
    "nonflammable gas, but a strong oxidizer.": "Негорючий газ, но сильный окислитель.",
    "decomposes": "Разлагается",
    "sublimes": "Возгоняется",
    "stable": "Стабилен",
    "unstable": "Нестабилен",
}

# ── 3. Структурные шаблоны (числа/единицы сохраняются в группах) ──
def _sub_class(m):
    """'Class IB Flammable Liquid: Fl.P. below 73 °F and BP at or above 100 °F.'"""
    code = m.group("code")
    kind = ("легковоспламеняющаяся жидкость (ЛВЖ)"
            if m.group("kind").lower() == "flammable"
            else "горючая жидкость (ГЖ)")
    rest = m.group("rest")
    rest = rest.replace("Fl.P.", "т. вспышки").replace("BP", "т. кипения")
    rest = re.sub(r"\bat or above\b", "не ниже", rest, flags=re.I)
    rest = re.sub(r"\bat or below\b", "не выше", rest, flags=re.I)
    rest = re.sub(r"\bbelow\b", "ниже", rest, flags=re.I)
    rest = re.sub(r"\babove\b", "выше", rest, flags=re.I)
    rest = re.sub(r"\band\b", "и", rest, flags=re.I)
    return f"Класс {code}, {kind}: {rest}".rstrip()

_PATTERNS = [
    (re.compile(r"^Class\s+(?P<code>[IVXABC]+)\s+(?P<kind>Flammable|Combustible)\s+Liquid:\s*(?P<rest>.+)$", re.I),
     _sub_class),
    (re.compile(r"^Relative density \(water\s*=\s*1\):\s*(.+)$", re.I),
     r"Относительная плотность (вода = 1): \1"),
    (re.compile(r"^Vapor pressure,\s*(.+?)\s+at\s+(.+?):\s*(.+)$", re.I),
     r"Давление пара, \1 при \2: \3"),
    (re.compile(r"^Vapor pressure,\s*(.+?)\s+at\s+(.+?):\s*$", re.I),
     r"Давление пара, \1 при \2:"),
    (re.compile(r"^Vapor pressure at\s+(.+?):\s*(.+)$", re.I),
     r"Давление пара при \1: \2"),
    (re.compile(r"^In water,\s*(.+)$", re.I),
     r"В воде: \1"),
    (re.compile(r"^Solubility in water,\s*(.+)$", re.I),
     r"Растворимость в воде: \1"),
    (re.compile(r"^Heat of (fusion|vaporization)[^=]*=\s*(.+)$", re.I),
     lambda m: ("Теплота плавления = " if m.group(1).lower() == "fusion"
                else "Теплота парообразования = ") + m.group(2)),
    (re.compile(r"^less than or equal to\s+(.+?)\s+at\s+(.+)$", re.I),
     r"не более \1 при \2"),
    (re.compile(r"^greater than or equal to\s+(.+?)\s+at\s+(.+)$", re.I),
     r"не менее \1 при \2"),
    (re.compile(r"^less than\s+(.+?)\s+at\s+(.+)$", re.I),
     r"менее \1 при \2"),
    (re.compile(r"^greater than\s+(.+?)\s+at\s+(.+)$", re.I),
     r"более \1 при \2"),
    (re.compile(r"^less than\s+(.+)$", re.I),  r"менее \1"),
    (re.compile(r"^greater than\s+(.+)$", re.I), r"более \1"),
    (re.compile(r"^(.+?)\s+at\s+(\d.+°[FC].*)$", re.I), r"\1 при \2"),
]

# ── 3b. Строки-«мусор» (навигация HSDB, не данные) — выкидываем целиком ──
_DROP = re.compile(r"please visit the HSDB record page", re.I)

# ── 4. Упорядоченные фразовые+словарные замены (whole-word, регистронезависимо).
#    Порядок ВАЖЕН: более длинные/специфичные фразы раньше коротких, иначе короткая
#    замена разрежет длинную. Русские слова уже не совпадут — повторного перевода нет.
_WORDS = [
    # составные термины-свойства (раньше одиночных слов)
    (r"vapor pressure", "давление пара"),
    (r"relative density", "относительная плотность"),
    (r"specific gravity", "относительная плотность"),
    (r"boiling point", "т. кипения"),
    (r"melting point", "т. плавления"),
    (r"flash point", "т. вспышки"),
    (r"freezing point", "т. замерзания"),
    (r"lower flammable limit", "нижний предел воспламенения"),
    (r"upper flammable limit", "верхний предел воспламенения"),
    (r"flammable limits in air", "пределы воспламенения в воздухе"),
    (r"flammable limits", "пределы воспламенения"),
    (r"latent heat of fusion", "удельная теплота плавления"),
    (r"heat of sublimation", "теплота возгонки"),
    (r"% by volume", "% об."),
    (r"by volume", "(об.)"),
    (r"in all proportions", "в любых пропорциях"),
    (r"lower:", "нижний:"),
    (r"upper:", "верхний:"),
    # глагольные обороты растворимости (фраза «… soluble in/with» — раньше одиночного «soluble»)
    (r"practically insoluble in", "практически нерастворим в"),
    (r"very soluble in", "хорошо растворим в"),
    (r"freely soluble in", "легко растворим в"),
    (r"sparingly soluble in", "малорастворим в"),
    (r"slightly soluble in", "слабо растворим в"),
    (r"readily soluble in", "легко растворим в"),
    (r"insoluble in", "нерастворим в"),
    (r"soluble in", "растворим в"),
    (r"miscible with", "неограниченно растворим в"),   # «в любых пропорциях» — предложный падеж
    (r"miscible in", "неограниченно растворим в"),
    (r"solubility in water,", "растворимость в воде,"),
    (r"in water,", "в воде,"),
    # плотность / поведение при разливе
    (r"less dense than water", "легче воды"),
    (r"denser than water", "тяжелее воды"),
    (r"will sink", "тонет"),
    (r"will float", "всплывает"),
    (r"sinks in water", "тонет в воде"),
    (r"floats on water", "всплывает на воде"),
    # скобочные уточнения метода
    (r"closed cup", "закрытый тигель"),
    (r"open cup", "открытый тигель"),
    (r"calculated", "расчётное"),
    (r"estimated", "оценка"),
    (r"extrapolated", "экстраполяция"),
    (r"sealed tube", "запаянная трубка"),
    (r"molten solid", "расплав"),
    (r"sublimes without melting", "возгоняется без плавления"),
    (r"boiling water", "кипящей воде"),
    # растворители — даём сразу предложный падеж (после «в …»); составные раньше одиночных
    (r"carbon disulfide", "сероуглероде"),
    (r"carbon tetrachloride", "четырёххлористом углероде"),
    (r"petroleum ether", "петролейном эфире"),
    (r"ethyl ether", "этиловом эфире"),
    (r"ethyl alcohol", "этиловом спирте"),
    (r"ethyl acetate", "этилацетате"),
    (r"methanol", "метаноле"), (r"ethanol", "этаноле"), (r"acetone", "ацетоне"),
    (r"chloroform", "хлороформе"), (r"toluene", "толуоле"), (r"benzene", "бензоле"),
    (r"alcohols", "спиртах"), (r"alcohol", "спирте"), (r"ether", "эфире"),
    (r"acetic acid", "уксусной кислоте"), (r"acids", "кислотах"), (r"acid", "кислоте"),
    (r"alkalies", "щелочах"), (r"alkali", "щёлочи"), (r"hexane", "гексане"),
    (r"glycerol", "глицерине"), (r"oils", "маслах"), (r"solvents", "растворителях"),
    (r"organic solvents", "органических растворителях"),
    # одиночные качественные слова
    (r"negligible", "пренебрежимо мало"),
    (r"decomposes", "разлагается"),
    (r"sublimes", "возгоняется"),
    (r"insoluble", "нерастворим"),
    (r"miscible", "смешивается"),
    (r"approx", "прибл."),
    (r"\band\b", "и"),
]
_WORDS = [(re.compile(r"(?<![A-Za-zА-Яа-я])" + p + r"(?![A-Za-zА-Яа-я])", re.I), r) for p, r in _WORDS]


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def localize(text):
    """Английское описание физ-хим свойства -> русское (числа/единицы/источник сохранены)."""
    if not text:
        return text
    s = _norm(text)
    if _DROP.search(s):                         # навигационный мусор HSDB — не данные
        return ""
    if not re.search(r"[A-Za-z]{3,}", s):       # «число+единица»: слов нет, но связку at->при дать надо
        return re.sub(r"\bat\b", "при", s)
    # отрезаем метку-источник, переведём «голову», вернём хвост на место
    tail = ""
    m = _TAIL.search(s)
    if m:
        tail = s[m.start():]
        s = s[:m.start()].rstrip()
    low = s.lower()
    if low in _EXACT:
        head = _EXACT[low]
    else:
        head = s
        for rx, rep in _PATTERNS:               # применяем все по порядку (шаблоны заякорены, не конфликтуют)
            head = rx.sub(rep, head)
    out = _norm(head + " " + tail) if tail else head
    for rx, rep in _WORDS:                       # добиваем остаточные слова и в хвосте «(approx)»
        out = rx.sub(rep, out)
    out = re.sub(r"\bat\b(?=\s*[\d<>~.+-])", "при", out)   # «at 760 mmHg», «at 25 °C» -> «при …» (глобально)
    out = re.sub(r",\s+и\b", " и", out)          # «эфире, и ацетоне» -> «эфире и ацетоне»
    out = _norm(out)
    if out and out[0].isalpha():                 # значение-описание с заглавной («давление…»->«Давление…»)
        out = out[0].upper() + out[1:]
    return out
