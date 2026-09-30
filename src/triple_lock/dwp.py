"""DWP figures the results are set against.

* ``coverage_targets``: 2026-27 spending and caseloads from DWP's benefit
  expenditure and caseload tables (Spring Forecast 2026; Great Britain plus UK
  benefits paid to people overseas), read from the workbook by row label.
* ``UPRATING_ANALYSIS``: DWP's State Pension uprating analysis (29 September
  2026), which costs the plan with its dynamic microsimulation model Pensim3 on
  one deterministic path, Great Britain, direct AME only (no tax or debt
  interest effects), rounded to the nearest £1bn.
"""

import openpyxl

from .config import RAW

TABLES = RAW / "dwp-outturn-and-forecast-tables-spring-2026.xlsx"
TABLES_URL = ("https://assets.publishing.service.gov.uk/media/69dcdc8c6b695d635c34dcc4/"
              "outturn-and-forecast-tables-spring-forecast-2026.xlsx")
TABLES_PAGE = "https://www.gov.uk/government/publications/benefit-expenditure-and-caseload-tables-2026"
YEAR = "2026/27"
# (sheet, block title, row label) -> key. The first block of each sheet is £ million nominal; caseloads are thousands.
ROWS = {
    "state_pension_total": ("State Pension", "State Pension expenditure,", "Total"),
    "state_pension_basic": ("State Pension", "State Pension expenditure,", "of which State Pension (basic)"),
    "state_pension_new": ("State Pension", "State Pension expenditure,",
                          "of which new State Pension  (excluding protected payments)"),
    "state_pension_new_protected": ("State Pension", "State Pension expenditure,",
                                    "of which new State Pension Protected Payments (including inherited elements)"),
    "state_pension_second": ("State Pension", "State Pension expenditure,", "of which State Second Pension"),
    "state_pension_abroad": ("State Pension", "State Pension expenditure,", "State Pension paid outside UK included above"),
    "state_pension_caseload": ("State Pension", "State Pension caseload,", "Total State Pension Caseload"),
    "state_pension_caseload_abroad": ("State Pension", "State Pension caseload,",
                                      "State Pension paid outside UK included above"),
    "pension_credit": ("Pension Credit", "Pension Credit expenditure,", "Total Pension Credit"),
    "pension_credit_caseload": ("Pension Credit", "Pension Credit caseload,", "Pension Credit"),
    "housing_benefit_capped": ("Housing benefits", "Housing benefits expenditure",
                               "of which Housing Benefit AME within Welfare Cap"),
    "housing_benefit_la_funded": ("Housing benefits", "Housing benefits expenditure", "of which LA funded"),
    "housing_benefit_pension_age": ("Housing benefits", "Housing benefits expenditure",
                                    "Housing Benefit over Pension Credit qualifying age"),
}

UPRATING_ANALYSIS = {
    "title": "State Pension uprating analysis 2026",
    "publisher": "Department for Work and Pensions",
    "date": "2026-09-29",
    "url": "https://www.gov.uk/government/publications/state-pension-uprating-analysis-2026/state-pension-uprating",
    "file": "data/raw/dwp-state-pension-uprating-analysis-2026.txt",
    "definition": "In any given year it will go up by at least inflation or 2.5% – and anything more that is needed "
                  "to retain that value [the 2029-30 ratio to earnings]",
    "saving_bn": {"2039": {"nominal": 15, "real_2025_26_prices": 11}, "2049": {"nominal": 50, "real_2025_26_prices": 30}},
    "model": "Pensim3, DWP's dynamic microsimulation model (population and pension outcomes projected to 2100, ONS "
             "2024-based population projections)",
    "coverage": "Great Britain; direct Annually Managed Expenditure, no tax or debt interest effects; rounded to the "
                "nearest £1bn; one deterministic uprating path, not stated",
}


def _read(path=TABLES):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return {name: list(wb[name].iter_rows(values_only=True)) for name in {s for s, _, _ in ROWS.values()}}


def coverage_targets(path=TABLES):
    """{key: value} for 2026-27 (£bn or millions of people/claims); raises if a label or the year is missing."""
    sheets = _read(path)
    out = {}
    for key, (sheet, block, label) in ROWS.items():
        rows = sheets[sheet]
        start = next(i for i, r in enumerate(rows) if isinstance(r[1], str) and r[1].replace("\n", " ").strip()
                     .startswith(block.rstrip(",").strip()))
        col = next(j for j, c in enumerate(rows[start]) if isinstance(c, str) and c.replace("\n", " ").startswith(YEAR))
        row = next(r for r in rows[start + 1:] if isinstance(r[1], str) and r[1].replace("\n", " ").strip() == label.strip())
        value = row[col]
        if not isinstance(value, (int, float)):
            raise ValueError(f"{sheet} / {label}: {YEAR} is not a number ({value!r})")
        out[key] = float(value) / 1000  # £ million -> £bn; thousands -> millions
    out["state_pension_in_gb"] = out["state_pension_total"] - out["state_pension_abroad"]
    out["state_pension_caseload_in_gb"] = out["state_pension_caseload"] - out["state_pension_caseload_abroad"]
    out["state_pension_flat_rate"] = out["state_pension_basic"] + out["state_pension_new"]
    out["housing_benefit"] = out["housing_benefit_capped"] + out["housing_benefit_la_funded"]
    return {"year": YEAR, "source": TABLES_PAGE, "url": TABLES_URL,
            "geography": "Great Britain, plus UK benefits paid to people resident overseas (removed where the "
                         "tables separate them)", "values": out}
