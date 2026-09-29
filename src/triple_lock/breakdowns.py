"""Household breakdowns of the income change, computed with microdf.

Every aggregate is a weighted microdf operation (MicroSeries / MicroDataFrame
sums, means and groupbys) on PolicyEngine's own weighted outputs; nothing
here multiplies by weights by hand. Group labels are explicit mappings from
PolicyEngine values, and an unmapped value raises.
"""

import microdf as mdf
import numpy as np

BN = 1e9
LOSS_THRESHOLD_GBP = 1.0

REGION_LABELS = {
    "NORTH_EAST": "North East",
    "NORTH_WEST": "North West",
    "YORKSHIRE": "Yorkshire and the Humber",
    "EAST_MIDLANDS": "East Midlands",
    "WEST_MIDLANDS": "West Midlands",
    "EAST_OF_ENGLAND": "East of England",
    "LONDON": "London",
    "SOUTH_EAST": "South East",
    "SOUTH_WEST": "South West",
    "WALES": "Wales",
    "SCOTLAND": "Scotland",
    "NORTHERN_IRELAND": "Northern Ireland",
}
TENURE_GROUPS = {
    "OWNED_OUTRIGHT": "owner_outright",
    "OWNED_WITH_MORTGAGE": "mortgage",
    "RENT_FROM_COUNCIL": "social_rent",
    "RENT_FROM_HA": "social_rent",
    "RENT_PRIVATELY": "private_rent",
}
TENURE_LABELS = {
    "owner_outright": "Owned outright",
    "mortgage": "Owned with mortgage",
    "social_rent": "Social rent",
    "private_rent": "Private rent",
}
HH_TYPE_LABELS = {
    "single_pensioner": "Single pensioner",
    "pensioner_couple": "Pensioner couple (all adults over State Pension age)",
    "mixed_age": "Pensioner with working-age adults or children",
    "working_age_with_children": "Working-age with children",
    "working_age_no_children": "Working-age without children",
}
# The FRS top-codes age at 80, so the oldest band is 75+.
AGE_BANDS = [(0, 66, "under_66", "Under 66"), (66, 75, "66_74", "66-74"), (75, 200, "75_plus", "75+")]
AGE_LABELS = {key: label for _, _, key, label in AGE_BANDS}
DECILE_LABELS = {d: f"Decile {d}" for d in range(1, 11)}
QUINTILE_LABELS = {q: f"Quintile {q}" for q in range(1, 6)}

BREAKDOWNS = {
    # result key: (group column, labels in display order)
    "by_decile": ("decile", DECILE_LABELS),
    "by_quintile": ("quintile", QUINTILE_LABELS),
    "by_region": ("region", REGION_LABELS),
    "by_hh_type": ("hh_type", HH_TYPE_LABELS),
    "by_tenure": ("tenure", TENURE_LABELS),
    "by_age_band": ("age_band", AGE_LABELS),
}

NOTES = {
    "decile": "household_income_decile: PolicyEngine's deciles of equivalised household "
    "net income (baseline), with boundaries set so each holds a tenth of people "
    "(person-weighted). Households PolicyEngine marks -1 (negative net income) are "
    "assigned to decile 1.",
    "quintile": "pairs of those deciles: 1-2, 3-4, 5-6, 7-8, 9-10",
    "hh_type": "from counts of adults, adults over State Pension age and children in "
    "the household",
    "tenure": "tenure_type; council and housing association rents combined as social rent",
    "age_band": "age of the household head as recorded in the survey (the population is "
    "not aged forward); FRS ages are top-coded at 80",
    "rows": "mean_change_gbp: mean change in household net income, £ a year per "
    "household; pct_income_change: total change as % of the group's baseline net "
    "income; total_bn: total change, £bn; share_of_households_pct: group's share of "
    "all households. Group total_bn sums to the net cost (the change in household net "
    "income).",
}


def decile_groups(decile):
    decile = np.asarray(decile).astype(int)
    unexpected = set(np.unique(decile)) - set(range(1, 11)) - {-1}
    if unexpected:
        raise ValueError(f"unexpected income decile values {sorted(unexpected)}")
    decile = np.where(decile == -1, 1, decile)
    return decile, (decile + 1) // 2


def map_labels(values, mapping, what):
    values = np.asarray(values).astype(str)
    unknown = set(np.unique(values)) - set(mapping)
    if unknown:
        raise KeyError(f"unmapped {what} values {sorted(unknown)}")
    return np.array([mapping[v] for v in values])


def household_type(adults, pension_age_adults, children):
    adults, pension_age_adults, children = (np.asarray(a) for a in (adults, pension_age_adults, children))
    if (adults < 1).any():
        raise ValueError("household with no adults")
    all_pension = pension_age_adults == adults
    return np.select(
        [
            all_pension & (adults == 1) & (children == 0),
            all_pension & (adults >= 2) & (children == 0),
            pension_age_adults > 0,
            children > 0,
        ],
        ["single_pensioner", "pensioner_couple", "mixed_age", "working_age_with_children"],
        "working_age_no_children",
    )


def age_band(age):
    age = np.asarray(age)
    out = np.empty(age.shape, dtype=object)
    for lo, hi, key, _ in AGE_BANDS:
        out[(age >= lo) & (age < hi)] = key
    if any(v is None for v in out):
        raise ValueError("age outside every band")
    return out.astype(str)


def household_frame(change, baseline_income, groups):
    """MicroDataFrame of the change, baseline income and group labels.

    ``change`` and ``baseline_income`` are PolicyEngine MicroSeries on the
    same households; the frame carries their (identical) household weights.
    """
    weights = baseline_income.weights.to_numpy()
    if not np.array_equal(change.weights.to_numpy(), weights):
        raise ValueError("reform and baseline household weights differ")
    columns = {
        "change": np.asarray(change.to_numpy()),
        "base": np.asarray(baseline_income.to_numpy()),
        "households": np.ones(len(weights)),
        **groups,
    }
    return mdf.MicroDataFrame(columns, weights=weights)


def breakdown(frame, column, labels):
    grouped = frame.groupby(column)
    change_sum = grouped.change.sum()
    change_mean = grouped.change.mean()
    base_sum = grouped.base.sum()
    households = grouped.households.sum()
    all_households = frame.households.sum()
    rows = []
    for group, label in labels.items():
        if group not in change_sum.index:
            raise KeyError(f"no households in {column} group {group!r}")
        if not base_sum[group] > 0:
            raise ValueError(f"non-positive baseline income in {column} group {group!r}")
        rows.append(
            {
                column: group if isinstance(group, str) else int(group),
                "label": label,
                "mean_change_gbp": round(float(change_mean[group]), 2),
                "pct_income_change": round(100 * float(change_sum[group] / base_sum[group]), 3),
                "total_bn": round(float(change_sum[group]) / BN, 3),
                "share_of_households_pct": round(100 * float(households[group] / all_households), 2),
            }
        )
    return rows


def households_affected(change):
    """Share of households losing more than £1 a year, and their mean loss (positive)."""
    losing = change < -LOSS_THRESHOLD_GBP
    if not losing.to_numpy().any():
        # A rule identical to the triple lock that year (e.g. before it diverges).
        return {"losing_pct": 0.0, "mean_loss_gbp": 0.0}
    return {
        "losing_pct": round(100 * float(losing.mean()), 2),
        "mean_loss_gbp": round(-float(change[losing].mean()), 2),
    }


def all_breakdowns(change, baseline_income, groups):
    frame = household_frame(change, baseline_income, groups)
    out = {key: breakdown(frame, column, labels) for key, (column, labels) in BREAKDOWNS.items()}
    out["households_affected"] = households_affected(change)
    return out


def largest_household_contribution(change):
    """The single survey household that moves the net cost most.

    Means-tested eligibility cliffs can move one heavily weighted record by
    thousands of pounds on a small pension change. Per-record diagnostic: its
    weight is read from the MicroSeries.
    """
    values = change.to_numpy()
    weights = change.weights.to_numpy()
    i = int(np.argmax(np.abs(values * weights)))
    return {
        "contribution_bn": round(float(values[i] * weights[i]) / BN, 3),
        "household_weight": round(float(weights[i]), 1),
        "income_change_gbp": round(float(values[i]), 2),
    }
