"""Can cash savings be read off rule arithmetic? A check on the single-path runs stored in data/results.json.

The results file holds full microsimulation runs for five single paths (the OBR central path, the OBR long-term
path and three simulated paths). The 160 runs behind each earnings scenario are stored only as stratified averages,
so they cannot be used here. For every path and year with a gap between the rules this checks:

* gross = share x base, with share = 1 - adjusted level / triple-lock level and base the central path's basic and
  new State Pension spending under the triple lock, scaled by the path's triple-lock level over the central path's;
* net = rho x gross, with rho fitted on the other paths (leave one path out).

It runs no microsimulation and writes data/c4/emulator_check.json. Five paths make this a weak check.

    PYTHONPATH=src python scripts/c4_emulator_check.py
"""

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def rows(R):
    paths = {p["id"]: p for p in R["trajectories"]["paths"]}
    paths["obr_wedge"] = R["scenario_envelope"]["obr_wedge"]["run"]
    central, out = paths["central"], []
    for pid, p in paths.items():
        for y in map(str, R["horizon"]):
            tl, bp = (p["weekly"][k]["new_state_pension"][y] for k in ("triple_lock", "burnham_2030"))
            if tl - bp <= 1e-9 * tl:
                continue
            base = central["totals_bn"]["triple_lock"][y]["state_pension_flat_rate"]
            out.append({"path": pid, "year": int(y), "share": 1 - bp / tl,
                        "scaled_base": base * tl / central["weekly"]["triple_lock"]["new_state_pension"][y],
                        "gross": p["saving_bn"][y]["gross"], "net": p["saving_bn"][y]["net"]})
    return out


def leave_one_path_out(data, x, y):
    """Errors of y = k x with k fitted by least squares on the other paths."""
    errors, slopes = [], {}
    for pid in dict.fromkeys(r["path"] for r in data):
        train = [r for r in data if r["path"] != pid]
        a, b = np.array([x(r) for r in train]), np.array([r[y] for r in train])
        slopes[pid] = float(a @ b / (a @ a))
        errors += [(r, slopes[pid] * x(r) - r[y]) for r in data if r["path"] == pid]
    absolute = np.array([abs(e) for _, e in errors])
    relative = np.array([abs(e) / abs(r[y]) for r, e in errors])
    return {"slope_by_left_out_path": slopes, "mean_abs_error_bn": float(absolute.mean()),
            "max_abs_error_bn": float(absolute.max()), "mean_abs_error_pct": float(100 * relative.mean()),
            "max_abs_error_pct": float(100 * relative.max()),
            "final_year": {r["path"]: {"actual_bn": r[y], "error_bn": float(e)} for r, e in errors
                           if r["year"] == max(q["year"] for q in data)}}


def main():
    R = json.loads((ROOT / "data" / "results.json").read_text())
    data = rows(R)
    identity = np.array([r["share"] * r["scaled_base"] - r["gross"] for r in data])
    out = {
        "per_path_runs_stored": sorted({r["path"] for r in data}),
        "scenario_runs": "the 160 runs behind each earnings scenario are stored as stratified averages only",
        "path_years_with_a_gap": len(data),
        "gross_identity_no_fit": {"max_abs_error_bn": float(np.abs(identity).max()),
                                  "max_abs_error_pct": float(100 * np.max(np.abs(identity) / [r["gross"] for r in data]))},
        "gross_leave_one_path_out": leave_one_path_out(data, lambda r: r["share"] * r["scaled_base"], "gross"),
        "net_over_gross_leave_one_path_out": leave_one_path_out(data, lambda r: r["gross"], "net"),
        "caveat": "five paths, all on one population and one set of offsets; a weak check",
    }
    (ROOT / "data" / "c4" / "emulator_check.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
