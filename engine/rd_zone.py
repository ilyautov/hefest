# -*- coding: utf-8 -*-
"""
Расчёт глубины зоны заражения АХОВ по РД 52.04.253-90.

Закрывает сознательный пробел пилота: раньше зоны эвакуации НЕ давали («нельзя без
расчёта»). Теперь даём — но строго по утверждённой методике ГО, с верифицированными
коэффициентами (data/rd_ahov.json), с явным вводом (масса, ветер, метео) и пометкой
needs_review. Это прогноз по типовой методике, НЕ замена утверждённого расчёта объекта.

Методика (первичное + вторичное облако):
  Qэ1 = K1·K3·K5·K7'·Q0                                  (первичное облако)
  T   = h·d / (K2·K4·K7'')                               (время испарения, ч)
  K6  = N^0.8 (N<T) | T^0.8 (N>=T) | 1 (T<1ч -> берут 1ч)
  Qэ2 = (1-K1)·K2·K3·K4·K5·K6·K7''·Q0 / (h·d)            (вторичное облако)
  Г1=depth(Qэ1), Г2=depth(Qэ2);  Г = max(Г1,Г2) + 0.5·min(Г1,Г2)

Замечание о ветре: верифицирована колонка таблицы П2 для ветра 1 м/с (даёт МАКСИМАЛЬНУЮ,
наиболее консервативную глубину). K4 (ветер) корректно входит в Qэ2. Предельный перенос
(Гп = N·v) НЕ применяется → возможна переоценка глубины (в безопасную сторону).
"""
import os, json, math

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
_RD = json.load(open(os.path.join(_DATA, "rd_ahov.json"), encoding="utf-8"))
AHOV = _RD["ahov"]
_DEPTH = _RD["depth_table_v1"]            # [[Qэкв, Г_км], ...] для ветра 1 м/с
_K4 = _RD["k4_wind"]
_K5 = _RD["k5_stability"]
_T7 = [-40, -20, 0, 20, 40]              # температурные узлы K7


def _alias_lookup(name: str):
    key = name.lower().strip()
    if key in AHOV:
        return key, AHOV[key]
    for k, v in AHOV.items():
        if key in (a.lower() for a in v.get("aliases", [])):
            return k, v
    return None, None


def _interp(x, pts):
    """Линейная интерполяция по списку [(x_i, y_i)] (x возрастает); кламп по краям."""
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for i in range(1, len(pts)):
        x0, y0 = pts[i - 1]; x1, y1 = pts[i]
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def _k7(coef, temp, idx):
    """K7 по температуре, idx=0 первичное / 1 вторичное; интерполяция между узлами."""
    pts = []
    for t in _T7:
        v = coef["k7"][str(t)]
        pts.append((t, v[idx] if isinstance(v, list) else v))
    return _interp(temp, pts)


def _k4(wind):
    pts = sorted((float(k), v) for k, v in _K4.items())
    return _interp(wind, pts)


def _depth(qe):
    if qe <= 0:
        return 0.0
    return _interp(qe, [(p[0], p[1]) for p in _DEPTH])


def calc(name, q0_t, wind=1.0, temp=20.0, stability="изотермия", n_hours=1.0,
         spill="свободный", dike_h=None):
    """Прогноз глубины зоны заражения. q0_t — масса выброса, т.
    spill: 'свободный' (h=0.05м) | 'поддон'/'обваловка' (h=dike_h-0.2, м)."""
    key, c = _alias_lookup(name)
    if not c:
        in_rd = name.lower() in [x.lower() for x in _RD["_meta"].get("not_in_rd", [])]
        return {"error": ("вещество отсутствует в перечне 34 АХОВ РД 52.04.253-90 — "
                          "табличных коэффициентов нет, расчёт не даём" if in_rd
                          else "нет коэффициентов РД для вещества"),
                "name": name, "available": sorted(AHOV.keys())}
    stab = stability.lower().strip()
    if stab not in _K5:
        return {"error": f"степень устойчивости должна быть из {list(_K5)}", "name": name}

    d = c["rho_liq"]                                  # плотность АХОВ, т/м3
    h = 0.05 if spill == "свободный" else max((dike_h or 0.2) - 0.2, 0.05)
    K1, K2, K3 = c["k1"], c["k2"], c["k3"]
    K4 = _k4(wind); K5 = _K5[stab]
    K7_1 = _k7(c, temp, 0); K7_2 = _k7(c, temp, 1)

    # Первичное облако
    Qe1 = K1 * K3 * K5 * K7_1 * q0_t

    # Время испарения и K6
    denom = K2 * K4 * K7_2
    T_evap = (h * d) / denom if denom > 0 else float("inf")
    n_eff = max(n_hours, 0.0)
    if T_evap < 1:
        K6 = 1.0
    elif n_eff >= T_evap:
        K6 = T_evap ** 0.8
    else:
        K6 = max(n_eff, 1.0) ** 0.8 if n_eff >= 1 else n_eff ** 0.8

    # Вторичное облако
    Qe2 = ((1 - K1) * K2 * K3 * K4 * K5 * K6 * K7_2 * q0_t) / (h * d) if h * d > 0 else 0.0

    G1, G2 = _depth(Qe1), _depth(Qe2)
    G = max(G1, G2) + 0.5 * min(G1, G2)

    return {
        "name": key, "input": {"q0_t": q0_t, "wind_ms": wind, "temp_c": temp,
                               "stability": stab, "n_hours": n_hours, "spill": spill, "h_m": round(h, 3)},
        "coeffs": {"K1": K1, "K2": K2, "K3": K3, "K4": round(K4, 3), "K5": K5,
                   "K6": round(K6, 3), "K7_prim": round(K7_1, 3), "K7_sec": round(K7_2, 3),
                   "rho_liq": d, "toxodose_mgmin_l": c["toxodose"]},
        "equiv_primary_t": round(Qe1, 4), "equiv_secondary_t": round(Qe2, 4),
        "evap_time_h": round(T_evap, 2) if T_evap != float("inf") else None,
        "depth_primary_km": round(G1, 2), "depth_secondary_km": round(G2, 2),
        "depth_total_km": round(G, 2),
        "method": "РД 52.04.253-90 (Прил. 2, 3); глубина по колонке ветра 1 м/с (консервативно)",
        "disclaimer": _RD["_meta"]["disclaimer"],
        "confidence": "needs_review",
    }
