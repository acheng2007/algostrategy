# Reproducing the historical inputs

Inputs are intentionally absent from Git.
Obtain your own vendor entitlements and confirm permitted local research use before downloading or exporting data.
Keep immutable original exports under `data/raw/<provider>/` and working inputs under `data/processed/`.

## QuantConnect HO/CL research export

In your own entitled QuantConnect Research project, run `notebooks/01_quantconnect_data_validation.py` in notebook cells in order.
It requests individual-contract data, repairs missing sessions, matches delivery months, audits rolls, and writes `algogators/crack_research_daily.csv` to Object Store.
Where your license permits, download that object as `data/processed/quantconnect_crack_daily.csv`.
Do not commit it.
The report dataset contains 4,031 sessions from 2010-01-04 through 2025-12-31 and 192 rolls after the initial selection.
The pipeline intentionally asserts this historical coverage, so revised vendor histories require a documented reconciliation rather than silently changing those assertions.

`02_quantconnect_step4_backtest.py` is an independent LEAN audit.
`03_quantconnect_export_research_data.py` is an alternative engine export whose session coverage can differ; it is not a byte-identical substitute for the Research export used in the report.
Record the cloud environment and data revision when acquiring a fresh copy.

CSV header:

```csv
date,delivery_month,contract_alias_ho,contract_alias_cl,expiry_ho,expiry_cl,close_ho,close_cl,crack_close,gross_change_per_bbl,gross_pnl,synthetic_crack_index,is_roll,base_cost,net_pnl
```

Dates are ISO dates; contract aliases identify individual futures; `is_roll` is `True` or `False`.
HO close is USD/gallon, CL close is USD/barrel, and `crack_close = 42 * close_ho - close_cl`.
`gross_change_per_bbl` uses the selected contract pair at both interval endpoints, including roll dates; `gross_pnl = 1000 * gross_change_per_bbl` is dollars per spread unit.
`synthetic_crack_index` is the cumulative roll-aware per-barrel change, with an initial zero.
`base_cost` and `net_pnl` are the extraction audit's unit-cost fields, not the final sized strategy results.
An initial missing P&L interval is allowed; subsequent intervals must be complete.
Do not replace roll-aware P&L with differences of concatenated contract prices.

## EIA weekly spreadsheets

Download the official Excel series and place unchanged files at:

| Local path | Official source |
| --- | --- |
| `data/processed/WDISTUS1w.xlsx` | https://www.eia.gov/dnav/pet/hist_xls/WDISTUS1w.xls |
| `data/processed/WDIUPUS2w.xlsx` | https://www.eia.gov/dnav/pet/hist_xls/WDIUPUS2w.xls |
| `data/processed/WPULEUS3w.xlsx` | https://www.eia.gov/dnav/pet/hist_xls/WPULEUS3w.xls |

The historical local filenames end in `.xlsx`, although the downloaded payload can be legacy XLS; pandas detects the format and `xlrd` is included.
The loader reads sheet `Data 1`, skips two rows, and expects two columns: week-ending date and numeric observation.
Series are total U.S. distillate stocks, distillate product supplied, and refinery utilization.
Availability is approximated as week ending plus six calendar days and joined backward to market sessions.
This conservative normal-week approximation is not a complete historical publication-date audit.

## Yahoo secondary smoke test

The full pipeline also expects `data/raw/yahoo/HO_F_2010_2025.json` and `data/raw/yahoo/CL_F_2010_2025.json` from an authorized Yahoo chart response covering 2010-2025 for `HO=F` and `CL=F`.
The JSON fields are `chart.result[0].timestamp` (Unix seconds) and `chart.result[0].indicators.quote[0].close` (price array of equal length).
The loader interprets timestamps in America/New_York.
Follow the provider's current access terms; no Yahoo payload is shared here.
These inputs are required by the full pipeline but not by the historical integration tests or PDF rebuild.
They are only a smoke test because continuous-contract conventions are undocumented.

## Official settlement gate

Obtain exchange-originated HO and CL historical settlements plus expiry metadata, preferably February-April 2019 and March-May 2020.
Keep the licensed export privately under `data/raw/cme/`.
Reconcile at least 20 prices and two coordinated roll windows before treating vendor closes as settlement-equivalent.
The current report deliberately leaves this gate open.
