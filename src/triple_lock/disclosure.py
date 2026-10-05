"""What a published aggregate must rest on: at least ten survey records, or none.

No survey record's id, weight or amounts is published (FRS records are
licensed). An aggregate over fewer than ten contributing records is
suppressed, and so is enough of its neighbours that it cannot be recovered by
subtraction from a published total. A zero aggregate with no contributors
discloses nobody and is shown.
"""

import numpy as np

MIN_RECORDS = 10
BN = 1e9


def coverage_cell(values, weights, mask, min_records=MIN_RECORDS):
    """A State Pension coverage cell over the people in ``mask``: recipients, and each of ``values`` ({variable:
    per-person amounts}) in £bn, with basic and new recipients. Suppressed whole if any nonzero part rests on fewer
    than ``min_records`` records (a total would otherwise disclose a small part by subtraction)."""
    # Zero-weight synthetic records do not contribute to a published cell.
    mask = np.asarray(mask, dtype=bool) & (np.asarray(weights) > 0)
    recipient = mask & (values["state_pension"] > 0)
    if 0 < int(recipient.sum()) < min_records:
        return {"status": "suppressed", "records": None, "recipients_m": None,
                **{f"{v}_bn": None for v in values}, "basic_recipients_m": None, "new_recipients_m": None}
    row = {"status": "available", "records": int(recipient.sum()),
           "recipients_m": float(weights[recipient].sum() / 1e6)}
    for v, amounts in values.items():
        contributors = mask & (amounts > 0)
        n = int(contributors.sum())
        row[f"{v}_bn"] = None if 0 < n < min_records else float(weights[mask] @ amounts[mask] / BN)
        if v in ("basic_state_pension", "new_state_pension"):
            key = "basic" if v == "basic_state_pension" else "new"
            row[f"{key}_recipients_m"] = None if 0 < n < min_records else float(weights[contributors].sum() / 1e6)
    if any(value is None for value in row.values()):
        row = {key: "suppressed" if key == "status" else None for key in row}
    return row


def complementary_suppression(rows):
    """Prevent an unpublished small cell being recovered from a published marginal total: for every metric, hide the
    smallest other cell with at least ``MIN_RECORDS`` records that has it."""
    suppressed = [key for key, row in rows.items() if row["status"] == "suppressed"]
    if suppressed:
        available = {key: row for key, row in rows.items() if row["status"] == "available"}
        hide = set()
        metrics = [name for name in next(iter(rows.values())) if name.endswith(("_bn", "_m"))]
        for metric in metrics:
            candidates = [key for key, row in available.items()
                          if row["records"] >= MIN_RECORDS and row.get(metric) is not None and row[metric] > 0]
            if candidates and not hide.intersection(candidates):
                hide.add(min(candidates, key=lambda k: available[k]["records"]))
        for key in hide:
            rows[key] = {name: "suppressed" if name == "status" else None for name in rows[key]}
    return rows
