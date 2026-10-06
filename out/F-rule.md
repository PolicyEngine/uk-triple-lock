## Model v2 statutory uncertainty screen: pre-registration (C2)

<!-- C2 frozen rule begins -->
This is the new rule required by Max's d955(c) decision of 5 October 2026.
Commit and push this section alone before any C2 scoring or implementation;
record that commit's SHA separately afterwards. It is an adequacy screen for
statutory behaviour, not evidence of calibrated predictive probabilities.

**Disclosure of the change after scoring.** All five forms failed C1's common
coverage gate on test A with published earnings: terminal coverage was 1/6,
driven by the 2021 furlough base effect. There were additional candidate-specific
failures, retained in the C1 record. This rule was changed after those scores
were seen. The reason is that the analysis models statutory behaviour, and
Parliament suspended the earnings leg for April 2022. The original C1 rule,
scores and failures remain in the record; C2 does not turn C1 into a pass.

**Treatment and legal exclusion.** Score April 2022 as the law applied it:
for its determination year, replace earnings with CPI in both forecast draws
and outturns. More generally the legal regime supplies the determination years
whose earnings leg is suspended; the scoring rule must work for any such year.
Exclude from coverage, bias and proper scores every statistic cell whose
forecast and outturn are both fixed by that legal rule, rather than choosing
cells from their numerical values. Under the C1 origins this removes the
determination-year 2021 earnings-minus-CPI cell from each window containing it:
four of test A's 24 annual gap cells. Pool the remaining annual cells with equal
cell weight (20 in test A), retaining per-origin rows, counts and overlap SEs.
Apply the same exclusion to annual gap CRPS and annual gap bias. Do not exclude
an accidentally zero draw or observation. The suspended year's CPI level,
earnings-below-floor indicator and joint CPI/earnings components are not fixed
by law and remain scored. Joint energy and variogram scores retain their C1
components and pairs unless a component is itself fixed by law.

Terminal policy gaps spanning a suspended year retain that year in the complete
compounded policy path, with earnings equal to CPI in both draws and outturns.
They remain scored when other uncertain years or CPI/floor effects make them
nonconstant; a whole statistic fixed by the legal rule would be excluded, with
its denominator disclosed. No suspended year is deleted from policy arithmetic,
lead-switch counts or floor fractions.

**Unchanged C1 thresholds and design.** Keep the five C1 candidates, fits,
pre-origin training boundaries, mean shifts, test A chronological and test B
all-complete spring origins, score definitions and descriptive SE conventions.
These forms share means and much of their residual pool and are not independent
tests. Keep the annual form's existing block alignment; C2 does not repair or
promote it after seeing scores. Apply every C1 threshold to **suspended treatment
only**, in both tests: annual and terminal central-80% coverage in [0.50, 1.00];
the descriptive terminal-coverage 95% Wilson band containing 0.80; absolute
gap bias at most 1.5 percentage points, switch bias at most 1.0 per four-year
path and floor-fraction bias at most 0.25; each of the five proper scores no
worse than 1.25 times the original primary for that test/treatment (zero
reference permits only zero); the uncalibrated pre-2011 past-years realised
terminal gap within the 5th–95th percentiles; finite paths and scores, complete
origins and successful fits. No other threshold changes.

**Sensitivity, primary and automatic fallback.** Report published-earnings
scoring beside every C2 result, including the past-years check, as a sensitivity
with no influence on the C2 verdict. The original monthly VAR(1) residual
bootstrap stays primary if it passes C2. Never promote another form on C2 scores;
report passing alternatives individually and never average forms. Only a
passing primary permits an expected value, labelled **model-conditional** and
shown beside the **scenario envelope**: the central path, OBR wedge,
last-decade replay and paired −0.5/+0.5 percentage-point earnings mean paths.
If the primary fails C2, the build automatically takes ruling (a): no expected
value, scenarios only, recording the failure and fallback without another
method choice. Monte Carlo precision stays separate from that envelope.

**Binding data and handoff.** The binding C2 score uses September 2026 CPI,
May–July 2026 AWE, and the OBR's Budget-day (28 October 2026) forecast means,
plus every forecast origin those inputs make complete. Re-score after the
Budget inputs are committed. A run on earlier inputs is a **dry run** and must
be labelled so throughout; it cannot authorize a binding rebuild. Record the
screen name, pre-registration commit SHA, data hashes/vintage, run status and
C1 failure in the handoff and results provenance. Refuse a handoff with a rule
SHA different from this committed pre-registration. The certified policyengine.py
bundle authorized by d778 follows the uk-data batch d833 and is required for
the fiscal rebuild. No PolicyEngine runs or survey data enter this screen.
<!-- C2 frozen rule ends -->
