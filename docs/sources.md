# Sources

## DWP

- **State Pension uprating analysis 2026 (29 September 2026).** Defines the adjusted triple lock and costs it at -£15bn in 2039-40 and -£50bn in 2049-50 (nominal; -£11bn and -£30bn in 2025-26 prices), from Pensim3, Great Britain, direct AME. https://www.gov.uk/government/publications/state-pension-uprating-analysis-2026/state-pension-uprating — text saved as `data/raw/dwp-state-pension-uprating-analysis-2026.txt`.
- **Benefit expenditure and caseload tables 2026 (Spring Forecast 2026).** State Pension, Pension Credit and Housing Benefit spending and caseloads for 2026-27, Great Britain plus benefits paid overseas. https://www.gov.uk/government/publications/benefit-expenditure-and-caseload-tables-2026 — workbook saved as `data/raw/dwp-outturn-and-forecast-tables-spring-2026.xlsx`, read by `src/triple_lock/dwp.py`.

# OBR forecast errors for CPI and earnings

All files were downloaded on **29 September 2026** into `data/raw/`. The derived CSVs are rebuilt by
`python3 scripts/build_forecast_errors.py`. obr.uk sits behind Cloudflare, so `curl` needs a browser
User-Agent header or it gets a challenge page.

## Data sources

- **OBR Historical official forecasts database, Spring 2026 (March 2026 EFO update).** The sheets used are `CPI` and `Earnings`. They hold every EFO forecast since June 2010 plus an outturn row "as available at last forecast".
  - Landing page: https://obr.uk/data/
  - Unversioned download slug: https://obr.uk/download/historical-official-forecasts-database/ (after the next EFO this will point to a newer file)
  - Resolved file (recorded as `source_url`): https://obr.uk/docs/dlm_uploads/Historical_official_forecasts_database_Spring_2026.xlsx
  - Local copy: `data/raw/Historical_official_forecasts_database_Spring_2026.xlsx`
- **OBR March 2026 EFO, published 3 March 2026.** Page: https://obr.uk/efo/economic-and-fiscal-outlook-march-2026/
  - Detailed forecast tables, economy. Table 1.6 gives earnings and Table 1.7 gives CPI. https://obr.uk/docs/d055fbf02d5b3g6jq8l2/efo-march-2026-detailed-forecast-tables-economy.xlsx
  - Charts and tables, chapter 2. Chart 2.9 is the CPI fan chart with deciles p10 to p90 for 2026 to 2030. https://obr.uk/docs/d055fbf02d5b3g6jq8l2/efo-march-2026-charts-and-tables-chapter-2.xlsx
  - Long-term economic determinants, dated 28 May 2026. It gives fiscal-year CPI, average earnings and the OBR "Triple Lock" uprating row (whose long-term growth-rate note reads "Average earnings growth plus 0.6 percentage points"); the build reads them to 2040-41. https://obr.uk/docs/dlm_uploads/Long-term-economic-determinants-March-2026-EFO.xlsx
- **OBR Forecast evaluation report, July 2025, Annex A (supplementary economy tables).** It was downloaded for reference but not used in the error calculations. The historical official forecasts database covers the same vintages in a consistent layout.
  - Page: https://obr.uk/forecast-evaluation-reports/
  - File: https://obr.uk/docs/dlm_uploads/Forecast-evaluation-report-%E2%80%93-July-2025-annex-A-%E2%80%93-supplementary-economy-tables.xlsx
- **ONS time series.** These are CSV generator downloads from the Sept 2026 releases: MM23 was released 16 Sept 2026, LMS on 15 Sept 2026 and UKEA on 30 June 2026.
  - D7G7, the CPI 12-month rate (monthly and calendar-year): https://www.ons.gov.uk/generator?format=csv&uri=/economy/inflationandpriceindices/timeseries/d7g7/mm23
  - KAB9, the AWE whole-economy total pay level (£/week, SA): https://www.ons.gov.uk/generator?format=csv&uri=/employmentandlabourmarket/peopleinwork/earningsandworkinghours/timeseries/kab9/lms
  - KAC3, AWE whole-economy total pay growth (3-month average on a year earlier). The July value covers May to July, which is the triple lock earnings input. https://www.ons.gov.uk/generator?format=csv&uri=/employmentandlabourmarket/peopleinwork/earningsandworkinghours/timeseries/kac3/lms
  - DTWM is compensation of employees and ROYK is employers' social contributions. MGRZ is employment aged 16+ and MGRQ is self-employment aged 16+. Together they rebuild the OBR earnings definition. The URLs follow the same pattern: `/economy/grossdomesticproductgdp/timeseries/{dtwm,royk}/ukea` and `/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/timeseries/{mgrz,mgrq}/lms`

## Definitions and caveats

- **Timing basis.** All errors are on a **calendar-year** basis: annual-average growth on the previous year, which is how the database stores both variables. The triple lock instead uses **September** CPI (12-month rate) and **May to July** AWE total pay growth (KAC3). `obr_central_forecast.csv` also carries Q3 CPI and Q2 earnings as the closest quarterly proxies from the March 2026 EFO. `triple_lock_actual_inputs.csv` gives the actual inputs.
- **CPI.** The OBR outturn matches ONS D7G7 calendar-year averages to rounding in every year from 2010 to 2025. September CPI less calendar-year CPI has mean 0.0 pp and SD 0.5 pp over 2010 to 2025.
- **Earnings.** OBR "average earnings" is **national-accounts wages and salaries divided by employees**: (DTWM − ROYK) / (MGRZ − MGRQ). It is **not AWE**. May–July AWE (KAC3) minus the OBR earnings outturn has mean +0.3 pp and **SD 1.4 pp** over 2010 to 2024, and reaches +3.4 pp in 2021 and +2.3 pp in 2023. This definitional gap is about as large as a one-year forecast error. Errors in the triple lock's earnings input are therefore larger than the errors estimated here. Year-by-year figures are in `data/obr_outturn_crosscheck.csv`.
- **Earnings outturn for 2025.** The database's earnings outturn row ends in 2024. The 2025 value (4.12%) was rebuilt from the latest ONS series using the OBR definition. The same rebuild reproduces the database's outturn to 2 dp for 2012 to 2023; for 2024 it gives 5.01% against the database's 5.09%, because of later revisions. Rows that use it list the database URL followed by the four ONS URLs in `source_url`, separated by ` | `. The March 2026 EFO estimated 2025 earnings growth at 5.31%, so later data revised it down substantially.
- **Vintages.** The main file uses **one vintage per year**: the June 2010 Budget forecast (the OBR's first; the first document titled EFO was November 2010), then each March EFO from 2011 to 2024. The March 2025 EFO has no outturned horizon of at least 1 year. Autumn vintages are in `obr_forecast_errors_all_vintages.csv`. They overlap the same target years, so pooling them double-counts shocks.
- **Horizons.** Spring vintages run only to vintage year + 4 in calendar terms. **Horizon 5 exists only for June 2010** (n = 1). Horizon 5 has n ≈ 11 only in the all-vintages file, from autumn vintages. Horizon 0 (the current-year nowcast) is excluded.
- **Precision.** Vintages up to March 2016 are published to 1 dp; later vintages are unrounded.
- **Outturn vintage.** CPI outturns are unrevised. Earnings outturns before 2025 are the database's March 2026-vintage figures, not first releases.
- **Serial dependence.** One shock (for example 2022 to 2023) enters several vintages at different horizons. Errors are not independent across rows, and the effective sample is much smaller than n. The summary file includes a sample that excludes target years 2020 to 2023 for sensitivity.
- **Triple lock suspension.** The earnings leg was suspended for the April 2022 uprating (a double lock applied). `triple_lock_actual_inputs.csv` uses the latest ONS vintage; the statutory uprating used first-published figures, which can differ.

## Gaps (not fabricated, left out)

- **Calendar year 2031 CPI and earnings.** The March 2026 EFO ends at 2030 (quarterly data to 2031Q1). Fiscal years 2031-32 to 2040-41 are included from the long-term economic determinants file and are labelled as a long-term projection, not a forecast.
- **CPI fan chart.** Deciles are published for calendar years 2026 to 2030 only. No OBR fan chart or range is published for earnings.
- **Earnings outturn on the AWE basis.** It is not used for errors, because the forecasts are on the OBR definition.
- **September CPI and May–July AWE forecasts by vintage.** Historical EFOs have no consistent monthly or quarterly archive in the database, so the errors are calendar-year only.

## Existing analysis: public costings of the triple lock

Each page or PDF below was fetched and read on 29 Sept 2026, and the figure checked against the text.

- **OBR, *Fiscal risks and sustainability*, July 2025 (8 July 2025).** "the triple lock is expected to have cost £15.5 billion annually by 2029-30, around three times higher than initial expectations". The comparison is triple lock versus earnings uprating since 2012; the original 2012 estimate was £5.2bn. If volatility persists, it adds a further 1.5% of GDP (£43bn in 2024-25 terms) to state pension spending by the early 2070s.
  - https://obr.uk/frs/fiscal-risks-and-sustainability-july-2025/
  - PDF: https://obr.uk/docs/dlm_uploads/Fiscal-risks-and-sustainability-report-July-2025.pdf
- **OBR, *Fiscal risks and sustainability*, July 2026 (7 July 2026).** In the baseline, state pension spending rises from 5% to around 9% of GDP over the 50-year projection, driven by ageing and triple-lock uprating (calibrated to historical inflation and earnings volatility). Under earnings uprating it reaches around 7% of GDP.
  - https://obr.uk/frs/fiscal-risks-and-sustainability-july-2026/
- **Resolution Foundation, *What a ratchet!* (Curtice and Clegg, 10 June 2026).** The State Pension bill is £12.6bn higher than under a smoothed earnings link since 2012, or about £9bn net of tax and means-tested benefit interactions. Switching to a smoothed earnings link from next year would save a net £650m in 2029-30. The OBR's +£80bn 50-year rise "could easily be £40 billion higher or lower".
  - https://www.resolutionfoundation.org/publications/what-a-ratchet/
- **IFS, *The future of the state pension* (Pensions Review, R291, December 2023).** The 80% range for additional state pension spending in 2050 due to the triple lock, above earnings indexation, is £5bn to £40bn a year in today's terms.
  - https://ifs.org.uk/sites/default/files/2023-12/IFS-R291-The-future-of-the-state-pension.pdf
- **IFS, *The triple lock: uncertainty for pension incomes and the public finances* (Cribb, Emmerson and Karjalainen, R272, September 2023).** The triple lock adds £11bn a year compared with price or earnings uprating since 2011. The 80% range for additional spending in 2050 above earnings indexation is £5bn to £45bn a year in today's terms. This is the closest methodological precedent: it uses a stochastic simulation of inflation and earnings.
  - https://ifs.org.uk/sites/default/files/2023-09/R272-The-triple-lock-costs-and-uncertainty.pdf
- **Pensions Policy Institute, *Triple Lock Briefing Paper* (General Election 2024, 29 May 2024).** State pension spending is 4.6% of GDP in 2023/24 and is forecast at 5.1% in 2025/26 under the triple lock (PPI analysis of the March 2024 EFO). The Conservative "triple lock plus" was costed at £2.4bn a year by 2029/30.
  - https://www.pensionspolicyinstitute.org.uk/media/ltjjqtd5/20240529-general-election-briefing-paper-1-triple-lock.pdf
- **Pensions Policy Institute, Briefing Note 96 (May 2017).** Citing the IFS, it says a double lock would be "only slightly less expensive (0.2% GDP) than the triple lock". It also says that with earnings uprating the new State Pension would cost less than the old basic State Pension system from about 2030, a saving of about 1% of GDP by 2060. That comparison is against the old system, not a direct comparison of the triple lock with earnings uprating.
  - https://www.pensionspolicyinstitute.org.uk/media/j35l21qb/201705-bn96-everything-you-always-wanted-to-know-about-the-triple-lock-but-were-afraid-to-ask.pdf
- **Not verified:** IFS article pages (ifs.org.uk/articles/...) and the House of Commons Library briefing CBP-11126 returned HTTP 403 to automated fetches, so they are not cited here.
