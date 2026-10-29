"""The OBR wedge's definition (trajectories.obr_premium_spec), checked on the rules alone (no model run).

The scenario pays the OBR's long-term 'Triple lock' row only in the Aprils whose inputs the central path takes from
the long-term determinants. Before those Aprils the October 2026 outlook sets every rate (d2124), so both rules pay
the central path's rates, and the adjusted Triple Lock pays them in every year.
"""

import copy
import re

from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import engine, rules
from triple_lock.central import central_path
from triple_lock.config import HORIZON, REFORM_POLICY as REFORM, STATUTORY_YEARS
from triple_lock.pipeline import forecast_vintages
from triple_lock.trajectories import central_spec, obr_premium_spec

CENTRAL = central_path()


def long_term_aprils(central):
    return [y for y in HORIZON if central["statutory_source"].get(y - 1) == "calendar"]


def test_the_row_is_paid_from_the_first_long_term_april():
    """From April 2032 on the committed sources: the first rise forecast_vintages labels long-term."""
    spec = obr_premium_spec(CENTRAL)
    first = forecast_vintages(CENTRAL)["long_term"]["april_rises"][0]
    assert first == 2032
    assert spec["specified_rates"] == {"triple_lock": {y: CENTRAL["obr_triple_lock_uprating"][y - 1]
                                                      for y in HORIZON if y >= first}}
    assert f"April {first}" in spec["label"] and f"April {first}" in spec["source"]
    assert "October 2026" in spec["source"] and "March 2026" in spec["source"]


def test_april_2028_follows_the_october_outlook():
    """The case that prompted the fix: the March row reads 2.5% for April 2028, the October path's rule 3.4%."""
    assert CENTRAL["obr_triple_lock_uprating"][2027] == 0.025
    _, _, central_rates = engine.spec_rates(central_spec(CENTRAL))
    _, _, wedge_rates = engine.spec_rates(obr_premium_spec(CENTRAL))
    assert central_rates["triple_lock"][2028] == wedge_rates["triple_lock"][2028] == 0.034


def test_the_central_label_names_the_october_outlook():
    assert central_spec(CENTRAL)["source"].startswith("OBR October 2026 forecast to 2030 and the OBR's March 2026 "
                                                      "long-term determinants after")


def test_both_sources_name_the_months_of_the_path_s_own_sources():
    """A path on the March 2026 outlook (a historical replay) is named as March, never as October."""
    march = copy.deepcopy(CENTRAL)
    for key in ("efo_calendar", "efo_quarterly"):
        march["sources"][key]["title"] = "OBR Economic and fiscal outlook, March 2026 (detailed forecast tables)"
    for spec in (central_spec(march), obr_premium_spec(march)):
        assert "March 2026" in spec["source"] and "October" not in spec["source"] + spec["label"], spec["id"]
    wedge = obr_premium_spec(CENTRAL)["source"]
    assert "April 2027 on published inputs, then the OBR's October 2026 outlook" in wedge
    assert "OBR Long-term economic determinants, March 2026 EFO (dated 28 May 2026)" in wedge


def test_a_path_without_named_sources_gets_no_invented_month():
    bare = {k: v for k, v in CENTRAL.items() if k != "sources"}
    for spec in (central_spec(bare), obr_premium_spec(bare)):
        assert not re.search(r"(March|October) 20\d\d", spec["source"] + spec["label"]), spec["id"]


rate = st.floats(-0.02, 0.12, allow_nan=False, allow_infinity=False)


@settings(max_examples=60, deadline=None, derandomize=True)
@given(cpi=st.lists(rate, min_size=len(STATUTORY_YEARS), max_size=len(STATUTORY_YEARS)),
       earnings=st.lists(rate, min_size=len(STATUTORY_YEARS), max_size=len(STATUTORY_YEARS)),
       row=st.lists(rate, min_size=len(STATUTORY_YEARS), max_size=len(STATUTORY_YEARS)))
def test_the_wedge_moves_only_the_triple_lock_in_the_long_term_years(cpi, earnings, row):
    """For any statutory inputs and any OBR row: before the first long-term April both rules pay the central path's
    rates; the adjusted Triple Lock pays them in every year (it anchors on the same 2029-30 level and runs its own
    rule after); from that April the triple lock pays the row, rounded as the rules round a rate."""
    central = copy.deepcopy(CENTRAL)
    central["statutory"]["cpi"] = dict(zip(STATUTORY_YEARS, cpi))
    central["statutory"]["earnings"] = dict(zip(STATUTORY_YEARS, earnings))
    central["obr_triple_lock_uprating"] = {**central["obr_triple_lock_uprating"], **dict(zip(STATUTORY_YEARS, row))}
    base, wedge = central_spec(central), obr_premium_spec(central)
    first = long_term_aprils(central)[0]
    _, _, base_rates = engine.spec_rates(base)
    _, _, wedge_rates = engine.spec_rates(wedge)
    decimals = base["rate_decimals"]
    for y in HORIZON:
        assert wedge_rates[REFORM][y] == base_rates[REFORM][y], y
        if y < first:
            assert wedge_rates["triple_lock"][y] == base_rates["triple_lock"][y], y
        else:
            assert wedge_rates["triple_lock"][y] == float(rules.round_rate(central["obr_triple_lock_uprating"][y - 1],
                                                                           decimals)), y
