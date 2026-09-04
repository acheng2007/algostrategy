"""First QuantConnect research cell for validating HO and CL data coverage.

Run this in the project's ``research.ipynb`` cloud notebook.
The first pass deliberately uses one year so that symbol, entitlement, and
schema problems are caught before requesting the full 2010-2025 history.
"""

from AlgorithmImports import *
from datetime import datetime


qb = QuantBook()

sample_start = datetime(2024, 1, 1)
sample_end = datetime(2025, 1, 1)

tickers = {
    "HO": Futures.Energy.HEATING_OIL,
    "CL": Futures.Energy.CRUDE_OIL_WTI,
}

subscriptions = {
    root: qb.add_future(
        ticker,
        Resolution.DAILY,
        data_normalization_mode=DataNormalizationMode.RAW,
        data_mapping_mode=DataMappingMode.OPEN_INTEREST,
        contract_depth_offset=0,
    )
    for root, ticker in tickers.items()
}

sample_history = {}
roll_history = {}

for root, future in subscriptions.items():
    bars = qb.history(
        future.symbol,
        start=sample_start,
        end=sample_end,
        resolution=Resolution.DAILY,
        fill_forward=False,
        extended_market_hours=False,
        data_mapping_mode=DataMappingMode.OPEN_INTEREST,
        data_normalization_mode=DataNormalizationMode.RAW,
        contract_depth_offset=0,
    )
    rolls = qb.history(
        SymbolChangedEvent,
        future.symbol,
        sample_start,
        sample_end,
    )

    sample_history[root] = bars
    roll_history[root] = rolls

    print(f"{root}: {len(bars):,} daily rows")
    print(f"{root}: {len(rolls):,} mapped-contract changes")
    display(bars.head())
    display(bars.tail())
    display(rolls)

assert all(not frame.empty for frame in sample_history.values())
print("PASS: HO and CL daily history is available for the 2024 sample.")


# Full exploratory window through the latest complete calendar year.
# These independently mapped series are useful for coverage and level checks.
# They are not the final source of spread P&L because their roll dates can differ.
import pandas as pd


research_start = datetime(2010, 1, 1)
research_end = datetime(2026, 1, 1)

full_history = {}
full_roll_history = {}

for root, future in subscriptions.items():
    bars = qb.history(
        future.symbol,
        start=research_start,
        end=research_end,
        resolution=Resolution.DAILY,
        fill_forward=False,
        extended_market_hours=False,
        data_mapping_mode=DataMappingMode.OPEN_INTEREST,
        data_normalization_mode=DataNormalizationMode.RAW,
        contract_depth_offset=0,
    )
    rolls = qb.history(
        SymbolChangedEvent,
        future.symbol,
        research_start,
        research_end,
    )

    frame = bars.reset_index()
    frame["time"] = pd.to_datetime(frame["time"])
    frame = frame.set_index("time").sort_index()

    full_history[root] = frame
    full_roll_history[root] = rolls

    print(
        f"{root}: {len(frame):,} rows from "
        f"{frame.index.min()} through {frame.index.max()}"
    )
    print(f"{root}: {len(rolls):,} mapped-contract changes")

prices = pd.concat(
    [
        full_history["HO"]["close"].rename("ho_close_usd_per_gallon"),
        full_history["CL"]["close"].rename("cl_close_usd_per_bbl"),
    ],
    axis=1,
    join="inner",
).dropna()

prices["crack_usd_per_bbl"] = (
    42 * prices["ho_close_usd_per_gallon"]
    - prices["cl_close_usd_per_bbl"]
)

roll_dates = {}
for root, rolls in full_roll_history.items():
    roll_frame = rolls.reset_index()
    roll_dates[root] = pd.DatetimeIndex(
        pd.to_datetime(roll_frame["time"])
    ).normalize()

matched_roll_dates = roll_dates["HO"].intersection(roll_dates["CL"])
all_roll_dates = roll_dates["HO"].union(roll_dates["CL"])

print(f"Aligned daily observations: {len(prices):,}")
print(f"Same-day HO/CL rolls: {len(matched_roll_dates):,}")
print(f"Dates where at least one leg rolls: {len(all_roll_dates):,}")
print(
    "WARNING: independently mapped continuous series cannot be used "
    "directly for final crack-spread P&L."
)

display(prices.head())
display(prices.tail())
display(prices["crack_usd_per_bbl"].describe())


# Individual-contract history used for matched-delivery-month research.
# FutureUniverse supplies daily OHLCV and open interest for every contract in
# the selected chain.
from pandas.tseries.offsets import BDay
import numpy as np
import re


MONTH_CODES = {
    "F": 1,
    "G": 2,
    "H": 3,
    "J": 4,
    "K": 5,
    "M": 6,
    "N": 7,
    "Q": 8,
    "U": 9,
    "V": 10,
    "X": 11,
    "Z": 12,
}


def contract_alias(symbol):
    """Return a readable contract code such as HO29G10 or CL20G10."""
    try:
        return Symbol.get_alias(symbol.id)
    except Exception:
        return str(symbol)


def delivery_month(alias):
    """Extract the delivery month from a readable futures contract code."""
    match = re.search(r"([FGHJKMNQUVXZ])(\d{2})$", alias)
    if match is None:
        return pd.NaT

    month = MONTH_CODES[match.group(1)]
    year = 2000 + int(match.group(2))
    return pd.Timestamp(year=year, month=month, day=1)


qb_contracts = QuantBook()
contract_subscriptions = {
    "HO": qb_contracts.add_future(
        Futures.Energy.HEATING_OIL,
        Resolution.DAILY,
    ),
    "CL": qb_contracts.add_future(
        Futures.Energy.CRUDE_OIL_WTI,
        Resolution.DAILY,
    ),
}

for future in contract_subscriptions.values():
    future.set_filter(0, 180)


def load_contract_universe_yearly(future, root_name):
    """Load and normalize individual contracts in reliable yearly chunks."""
    chunks = []

    for year in range(2010, 2026):
        raw = qb_contracts.history(
            FutureUniverse,
            future.symbol,
            datetime(year, 1, 1),
            datetime(year + 1, 1, 1),
            Resolution.DAILY,
            flatten=True,
        )

        if raw.empty:
            print(f"{root_name} {year}: no rows returned")
            continue

        raw = raw.reset_index()

        # Some older responses leave the contract index unnamed, producing a
        # column called level_1 instead of symbol.
        # The contract object is consistently the second reset-index column.
        contract_values = raw.iloc[:, 1]
        raw["root"] = root_name
        raw["contract_symbol"] = contract_values
        raw["contract_alias"] = contract_values.map(contract_alias)
        raw["delivery_month"] = raw["contract_alias"].map(delivery_month)
        raw["expiry"] = contract_values.map(
            lambda symbol: pd.Timestamp(symbol.id.date)
        )

        # FutureUniverse stamps a session's daily bar at the following
        # midnight.
        # Subtract one day to recover the trading-session date.
        raw["qc_time"] = pd.to_datetime(raw["time"]).dt.normalize()
        raw["date"] = raw["qc_time"] - pd.Timedelta(days=1)

        columns = [
            "date",
            "qc_time",
            "root",
            "contract_symbol",
            "contract_alias",
            "delivery_month",
            "expiry",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "openinterest",
        ]
        chunks.append(raw.loc[:, columns].copy())

    if not chunks:
        raise ValueError(
            f"No individual-contract history returned for {root_name}"
        )

    clean = pd.concat(chunks, ignore_index=True)
    clean = clean.dropna(subset=["delivery_month", "close"])
    clean = clean.drop_duplicates(["date", "contract_symbol"])
    clean = clean.sort_values(["date", "delivery_month", "expiry"])

    assert clean["delivery_month"].notna().all()
    assert np.isfinite(clean["close"]).all()
    return clean.reset_index(drop=True)


ho_contracts = load_contract_universe_yearly(
    contract_subscriptions["HO"],
    "HO",
)
cl_contracts = load_contract_universe_yearly(
    contract_subscriptions["CL"],
    "CL",
)

individual_contract_history = {
    "HO": ho_contracts,
    "CL": cl_contracts,
}


def load_trade_history_year(future, root_name, year):
    """Load contract bars from the independent trade-history endpoint."""
    raw = qb_contracts.future_history(
        future.symbol,
        datetime(year, 1, 1),
        datetime(year + 1, 1, 1),
        Resolution.DAILY,
    ).data_frame.reset_index()

    if raw.empty:
        return raw

    contract_values = raw.loc[:, "symbol"]
    raw["root"] = root_name
    raw["contract_symbol"] = contract_values
    raw["contract_alias"] = contract_values.map(contract_alias)
    raw["delivery_month"] = raw["contract_alias"].map(delivery_month)
    raw["expiry"] = pd.to_datetime(raw["expiry"])
    raw["date"] = pd.to_datetime(raw["time"]).dt.normalize()
    raw["qc_time"] = raw["date"] + pd.Timedelta(days=1)
    raw["openinterest"] = np.nan

    columns = [
        "date",
        "qc_time",
        "root",
        "contract_symbol",
        "contract_alias",
        "delivery_month",
        "expiry",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "openinterest",
    ]
    return raw.loc[:, columns].copy()


# Use the continuous-series calendar only as a coverage reference.
# It is not used for contract selection, prices, or P&L.
reference_sessions = pd.DatetimeIndex(prices.index).normalize().unique()

for root_name, future in contract_subscriptions.items():
    contract_frame = individual_contract_history[root_name]
    available_sessions = pd.DatetimeIndex(
        contract_frame["date"].unique()
    )
    missing_sessions = reference_sessions.difference(available_sessions)
    repair_years = sorted(set(missing_sessions.year))

    repairs = [
        load_trade_history_year(future, root_name, year)
        for year in repair_years
    ]
    repairs = [frame for frame in repairs if not frame.empty]

    if repairs:
        contract_frame = pd.concat(
            [contract_frame, *repairs],
            ignore_index=True,
        )
        # Keep FutureUniverse rows when both sources contain a date because
        # those rows include open interest.
        contract_frame = contract_frame.drop_duplicates(
            ["date", "contract_symbol"],
            keep="first",
        )
        contract_frame = contract_frame.sort_values(
            ["date", "delivery_month", "expiry"]
        ).reset_index(drop=True)

    remaining_missing = reference_sessions.difference(
        pd.DatetimeIndex(contract_frame["date"].unique())
    )
    assert remaining_missing.empty, (
        f"{root_name} is still missing reference sessions: "
        f"{remaining_missing.tolist()}"
    )
    individual_contract_history[root_name] = contract_frame

ho_contracts = individual_contract_history["HO"]
cl_contracts = individual_contract_history["CL"]

matched_contracts = ho_contracts.merge(
    cl_contracts,
    on=["date", "delivery_month"],
    how="inner",
    suffixes=("_ho", "_cl"),
    validate="one_to_one",
)
matched_contracts["crack_close"] = (
    42.0 * matched_contracts["close_ho"]
    - matched_contracts["close_cl"]
)
matched_contracts["earlier_expiry"] = matched_contracts[
    ["expiry_ho", "expiry_cl"]
].min(axis=1)
matched_contracts["roll_cutoff"] = (
    matched_contracts["earlier_expiry"] - BDay(5)
)

# Both legs roll together to the next common delivery month.
eligible = matched_contracts[
    matched_contracts["date"] <= matched_contracts["roll_cutoff"]
].copy()
synchronized_crack = (
    eligible.sort_values(["date", "delivery_month"])
    .groupby("date", as_index=False)
    .first()
)
synchronized_crack["is_roll"] = (
    synchronized_crack["delivery_month"]
    != synchronized_crack["delivery_month"].shift(1)
)

assert synchronized_crack["date"].is_monotonic_increasing
assert synchronized_crack[["close_ho", "close_cl"]].notna().all().all()
assert (
    synchronized_crack["delivery_month"]
    == synchronized_crack["contract_alias_ho"].map(delivery_month)
).all()
assert (
    synchronized_crack["delivery_month"]
    == synchronized_crack["contract_alias_cl"].map(delivery_month)
).all()

for name, frame in individual_contract_history.items():
    print(
        f"{name}: {len(frame):,} contract-days, "
        f"{frame['contract_alias'].nunique():,} contracts, "
        f"{frame['date'].min().date()} to {frame['date'].max().date()}, "
        f"open-interest coverage "
        f"{frame['openinterest'].notna().mean():.1%}"
    )

print(
    f"Synchronized crack: {len(synchronized_crack):,} sessions and "
    f"{max(0, int(synchronized_crack['is_roll'].sum()) - 1):,} "
    "coordinated rolls"
)
print(
    "PASS: both legs use the same delivery month on every selected session."
)


# Roll-aware close-to-close P&L for one long HO and one short CL contract.
# Both legs switch at the prior session close on a coordinated roll.
held = synchronized_crack.sort_values("date").copy()
held["previous_session"] = held["date"].shift(1)

reference_prices = matched_contracts[
    ["date", "delivery_month", "close_ho", "close_cl"]
].rename(
    columns={
        "date": "previous_session",
        "close_ho": "reference_close_ho",
        "close_cl": "reference_close_cl",
    }
)
roll_aware_pnl = held.merge(
    reference_prices,
    on=["previous_session", "delivery_month"],
    how="left",
    validate="many_to_one",
)
roll_aware_pnl["ho_pnl"] = 42_000.0 * (
    roll_aware_pnl["close_ho"]
    - roll_aware_pnl["reference_close_ho"]
)
roll_aware_pnl["cl_pnl"] = -1_000.0 * (
    roll_aware_pnl["close_cl"]
    - roll_aware_pnl["reference_close_cl"]
)
roll_aware_pnl["gross_pnl"] = (
    roll_aware_pnl["ho_pnl"] + roll_aware_pnl["cl_pnl"]
)
roll_aware_pnl["gross_change_per_bbl"] = (
    roll_aware_pnl["gross_pnl"] / 1_000.0
)
roll_aware_pnl["naive_level_pnl"] = (
    roll_aware_pnl["crack_close"].diff() * 1_000.0
)
roll_aware_pnl["roll_gap_error"] = (
    roll_aware_pnl["naive_level_pnl"]
    - roll_aware_pnl["gross_pnl"]
)

# Explicit one-way implementation assumptions.
HO_TICK_DOLLARS = 4.20
CL_TICK_DOLLARS = 10.00
BASE_SLIPPAGE_TICKS = 1.0
BASE_FEE_PER_CONTRACT_SIDE = 2.50

roll_aware_pnl["ho_contract_sides"] = np.where(
    roll_aware_pnl.index == 0,
    1,
    np.where(roll_aware_pnl["is_roll"], 2, 0),
)
roll_aware_pnl["cl_contract_sides"] = roll_aware_pnl[
    "ho_contract_sides"
]
roll_aware_pnl["base_cost"] = (
    roll_aware_pnl["ho_contract_sides"]
    * (
        HO_TICK_DOLLARS * BASE_SLIPPAGE_TICKS
        + BASE_FEE_PER_CONTRACT_SIDE
    )
    + roll_aware_pnl["cl_contract_sides"]
    * (
        CL_TICK_DOLLARS * BASE_SLIPPAGE_TICKS
        + BASE_FEE_PER_CONTRACT_SIDE
    )
)
roll_aware_pnl["net_pnl"] = (
    roll_aware_pnl["gross_pnl"] - roll_aware_pnl["base_cost"]
)

valid_intervals = roll_aware_pnl.iloc[1:]
assert valid_intervals[
    ["reference_close_ho", "reference_close_cl", "gross_pnl"]
].notna().all().all()
assert np.isfinite(valid_intervals["gross_pnl"]).all()


# Verify that every coordinated roll advances one month and is executed at
# least five business days before the earlier expiry of the outgoing pair.
roll_audit = held.loc[held["is_roll"]].copy()
roll_audit["execution_date"] = held["date"].shift(1).loc[
    roll_audit.index
]
roll_audit["previous_delivery_month"] = held[
    "delivery_month"
].shift(1).loc[roll_audit.index]
roll_audit["previous_earlier_expiry"] = held[
    "earlier_expiry"
].shift(1).loc[roll_audit.index]
roll_audit = roll_audit.iloc[1:].copy()
roll_audit["months_advanced"] = (
    (
        roll_audit["delivery_month"].dt.year
        - roll_audit["previous_delivery_month"].dt.year
    )
    * 12
    + roll_audit["delivery_month"].dt.month
    - roll_audit["previous_delivery_month"].dt.month
)
roll_audit["business_days_before_earlier_expiry"] = [
    len(pd.bdate_range(execution, expiry, inclusive="right"))
    for execution, expiry in zip(
        roll_audit["execution_date"],
        roll_audit["previous_earlier_expiry"],
    )
]
assert (roll_audit["months_advanced"] == 1).all()
assert (
    roll_audit["business_days_before_earlier_expiry"] >= 5
).all()


negative_cl = cl_contracts.loc[
    cl_contracts["close"] < 0,
    [
        "date",
        "contract_alias",
        "delivery_month",
        "expiry",
        "close",
        "volume",
        "openinterest",
    ],
].sort_values("date")
assert not negative_cl.empty
assert np.isclose(negative_cl["close"].min(), -13.10)

april_2020_held = held.loc[
    held["date"].between("2020-04-13", "2020-04-24"),
    [
        "date",
        "delivery_month",
        "contract_alias_ho",
        "contract_alias_cl",
        "close_ho",
        "close_cl",
        "crack_close",
        "is_roll",
    ],
]

cost_rows = []
for ticks in [0.5, 1.0, 2.0]:
    for fee in [0.0, 2.5, 5.0]:
        total_cost = (
            roll_aware_pnl["ho_contract_sides"]
            * (HO_TICK_DOLLARS * ticks + fee)
            + roll_aware_pnl["cl_contract_sides"]
            * (CL_TICK_DOLLARS * ticks + fee)
        ).sum()
        cost_rows.append(
            {
                "slippage_ticks_per_side": ticks,
                "fee_per_contract_side": fee,
                "total_2010_2025_cost": total_cost,
                "average_cost_per_roll": total_cost / len(roll_audit),
            }
        )
cost_sensitivity = pd.DataFrame(cost_rows)

non_roll_days = valid_intervals.loc[~valid_intervals["is_roll"]]
roll_days = valid_intervals.loc[valid_intervals["is_roll"]]

print(
    f"P&L intervals: {len(valid_intervals):,}; "
    "all current-contract reference prices are present."
)
print(
    f"Rolls audited: {len(roll_audit):,}; all advance one delivery "
    "month and satisfy the five-business-day rule."
)
print(
    "Roll-aware daily P&L standard deviation: "
    f"USD {valid_intervals['gross_pnl'].std():,.0f}."
)
print(
    "Roll-day versus non-roll standard deviation: "
    f"USD {roll_days['gross_pnl'].std():,.0f} versus "
    f"USD {non_roll_days['gross_pnl'].std():,.0f}."
)
print(
    "Median absolute artificial jump avoided on roll days: "
    f"USD {roll_days['roll_gap_error'].abs().median():,.0f}; "
    f"maximum USD {roll_days['roll_gap_error'].abs().max():,.0f}."
)
print("Negative CL observations retained:")
print(negative_cl.to_string(index=False))
print("Cost sensitivity:")
print(cost_sensitivity.to_string(index=False))
print("PASS: roll-aware P&L and Step 4 internal audits are complete.")


# Persist the research-ready daily series for the local hypothesis tests.
# This export uses raw ``future_history`` repair rows.
# The current vendor extraction reports -13.10 rather than the official
# -37.63 May 2020 WTI settlement, so the price field remains provisional.
roll_aware_pnl["synthetic_crack_index"] = (
    roll_aware_pnl["gross_change_per_bbl"].fillna(0.0).cumsum()
)
export_columns = [
    "date",
    "delivery_month",
    "contract_alias_ho",
    "contract_alias_cl",
    "expiry_ho",
    "expiry_cl",
    "close_ho",
    "close_cl",
    "crack_close",
    "gross_change_per_bbl",
    "gross_pnl",
    "synthetic_crack_index",
    "is_roll",
    "base_cost",
    "net_pnl",
]
research_export = roll_aware_pnl.loc[:, export_columns].copy()
object_store_key = "algogators/crack_research_daily.csv"
saved = qb_contracts.object_store.save(
    object_store_key,
    research_export.to_csv(index=False),
)
assert saved, "QuantConnect Object Store export failed"
print(
    f"SAVED: {len(research_export):,} rows to Object Store key "
    f"{object_store_key}."
)
