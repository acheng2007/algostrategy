# Seasonal Distillate Margin Expansion

A focused AlgoGators application studying the same-delivery-month NYMEX ULSD (HO) minus WTI (CL) crack spread.
Start with the [final four-page report](output/pdf/algogators_crack_spread_research.pdf).
This is a provisional research candidate, not a production trading system.

## Strategy

One spread unit is long one HO contract and short one CL contract of the same delivery month.
The quoted spread is `42 * HO - CL` in dollars per barrel; unit P&L is `42,000 * change(HO) - 1,000 * change(CL)`.
Both legs roll together five business days before the earlier expiry, using the newly selected pair at both endpoints of the roll interval.

The frozen seasonal rule enters at the final June close and exits at the final October close.
Sizing updates weekly using trailing 60-session volatility, targeting 10% annualized volatility on a constant $1 million risk budget, with whole contracts capped at 10 spread units.
Close decisions apply to the next P&L interval.
Base costs are one tick per leg plus $2.50 per contract side, or $19.20 per one-way spread unit.

## Results

| Period | Annualized return | Volatility | Sharpe | Maximum drawdown |
| --- | ---: | ---: | ---: | ---: |
| 2010-2020 development | 2.95% | 5.09% | 0.58 | -7.66% |
| 2021-2025 validation | 3.27% | 5.42% | 0.60 | -10.83% |
| 2010-2025 full | 3.05% | 5.19% | 0.59 | -8.53% |

These are simulated net results on a constant risk budget, with arithmetic annualization rather than CAGR; collateral interest is not included.
Thirteen of 16 annual campaigns were profitable, with total net P&L of $488,590.
The original momentum and low-inventory hypothesis was rejected because its relationships changed sign across samples.
The 2021-2025 period was reserved for validation and must not be used to retune the rule.

## Run locally

The recorded environment is Python 3.14.7 with the exact package versions in `requirements.txt`.
From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The default suite runs synthetic accounting and timing tests plus reconciliation of the published output tables.
Six historical integration tests are explicitly skipped until private inputs are supplied.
Synthetic fixtures are invented test data, not empirical evidence.

To reproduce the complete historical research, follow [data acquisition and input formats](docs/data-acquisition.md), then run:

```sh
RUN_PRIVATE_DATA_TESTS=1 python -m unittest discover -s tests -v
python src/research_pipeline.py
python submission/build_pdf.py
```

The PDF can also be rebuilt directly from the included aggregate tables and figure, without private data.
The research figure renderer currently requires macOS Arial fonts at `/System/Library/Fonts/Supplemental/`; calculation and tests are independent of those fonts.
The `notebooks/` scripts require QuantConnect's hosted Research or LEAN environment and are not ordinary local Python programs.

## Architecture

| Path | Responsibility |
| --- | --- |
| `notebooks/01_quantconnect_data_validation.py` | Contract history, gap repair, coordinated rolls, export |
| `notebooks/02_quantconnect_step4_backtest.py` | Independent LEAN construction audit |
| `notebooks/03_quantconnect_export_research_data.py` | Alternative LEAN export, not the exact report dataset |
| `src/research_pipeline.py` | Input alignment, hypotheses, signals, sizing, costs, campaigns, metrics, robustness, figures |
| `tests/` | Synthetic invariants, published-result reconciliation, optional historical integration |
| `submission/` | Shared application prose and PDF builder |
| `data/processed/` | Selected aggregate results only |
| `figures/` and `output/pdf/` | Selected exhibit and final report |

Opening transaction costs are attributed to the subsequent holding interval so campaign P&L reconciles to daily P&L, including entry costs.
The tests check this accounting explicitly.

## Limitations and data policy

Only 16 annual campaigns exist, so daily observation count overstates independent evidence.
Official CME settlement reconciliation remains open: a secondary 20-price Barchart check matched only two prices within one tick and reversed one roll interval's direction.
QuantConnect vendor closes must not be treated as official settlements.
EIA availability is approximated by observation date plus six calendar days rather than a verified historical release calendar.
Execution, margin, market impact, and live order handling remain research assumptions; this repository does not place production orders.

No raw or daily vendor price data, merged research panel, daily strategy series, account configuration, application-guide PDFs, unrelated experiments, or virtual environment is included.
Only summary statistics, campaign outcomes, and the report exhibit are retained.
See [data rights and publication scope](docs/data-rights.md) before adding data or changing visibility.
