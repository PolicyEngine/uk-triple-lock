# First C2 dry run: preserved and superseded by the arithmetic correction

Current-input draw/scoring run at implementation 67b10d3 completed with zero
PolicyEngine jobs. Required primary A figures reproduced: 4/6 terminal hits,
80.0% annual coverage over 20 cells (four legal exclusions). Primary, VAR2,
Student-t and Gaussian passed; annual switch CRPS ratio 1.279 failed.

A broader comparison then found inherited rounding leakage into terminal and
past-years statistics: C1's candidate branch originally called an unrounded
`gap_pct` at 4c663d0, while the 52b80bf merge retained the older comparator's
fiscal-rounding default. The frozen C1 and C2 documents require unrounded
candidate-screen terminal arithmetic. Primary A suspended terminal bias here
is −0.740863183578 pp versus recorded C1 −0.745270269389 pp. Coverage stays 4/6.

Preserve this first run's scores/selection/handoff as the debugging record.
It is a dry run, all forms fiscal_eligible=false, and authorizes no EV. The
candidate/past screen now explicitly selects decimals=None, leaving fiscal
spec precision and older forecast-error comparators unchanged. The definitive
dry run follows that correction; do not quote this table as final C2.
