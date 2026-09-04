"""Reproduce the AlgoGators crack-spread hypothesis tests and backtests.

The script uses only files stored in this repository.
It keeps the 2021-2025 segment separate in every output table and applies a
conservative six-calendar-day delay to weekly EIA observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
MARKET_PATH = ROOT / "data/processed/quantconnect_crack_daily.csv"
INVENTORY_PATH = ROOT / "data/processed/WDISTUS1w.xlsx"
DEMAND_PATH = ROOT / "data/processed/WDIUPUS2w.xlsx"
UTILIZATION_PATH = ROOT / "data/processed/WPULEUS3w.xlsx"
YAHOO_HO_PATH = ROOT / "data/raw/yahoo/HO_F_2010_2025.json"
YAHOO_CL_PATH = ROOT / "data/raw/yahoo/CL_F_2010_2025.json"
PROCESSED = ROOT / "data/processed"
FIGURES = ROOT / "figures"

CAPITAL = 1_000_000.0
TARGET_VOLATILITY = 0.10
HO_TICK_DOLLARS = 4.20
CL_TICK_DOLLARS = 10.00
BASE_SLIPPAGE_TICKS = 1.0
BASE_FEE_PER_CONTRACT_SIDE = 2.50
BASE_PAIR_COST = (
    HO_TICK_DOLLARS * BASE_SLIPPAGE_TICKS
    + CL_TICK_DOLLARS * BASE_SLIPPAGE_TICKS
    + 2.0 * BASE_FEE_PER_CONTRACT_SIDE
)
DEVELOPMENT_END = pd.Timestamp("2020-12-31")


@dataclass(frozen=True)
class BacktestResult:
    daily: pd.DataFrame
    trades: pd.DataFrame


def _load_eia(path: Path, name: str) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name="Data 1", skiprows=2)
    frame.columns = ["week_end", name]
    frame["week_end"] = pd.to_datetime(frame["week_end"])
    return frame


def _seasonal_trailing_zscore(
    frame: pd.DataFrame,
    column: str,
    years: int = 5,
    week_band: int = 2,
) -> pd.Series:
    """Compute a seasonal z-score using only earlier observations."""
    week_number = frame["week_end"].dt.isocalendar().week.astype(int)
    result: list[float] = []
    for index, row in frame.iterrows():
        prior = frame.iloc[:index]
        prior_week = week_number.iloc[:index]
        current_week = int(week_number.iloc[index])
        distance = np.minimum(
            (prior_week - current_week) % 52,
            (current_week - prior_week) % 52,
        )
        sample = prior.loc[
            (prior["week_end"] >= row["week_end"] - pd.DateOffset(years=years))
            & (distance <= week_band),
            column,
        ].dropna()
        standard_deviation = sample.std(ddof=1)
        if len(sample) < 15 or not np.isfinite(standard_deviation) or standard_deviation == 0:
            result.append(np.nan)
        else:
            result.append((row[column] - sample.mean()) / standard_deviation)
    return pd.Series(result, index=frame.index, dtype=float)


def build_research_panel() -> pd.DataFrame:
    market = pd.read_csv(
        MARKET_PATH,
        parse_dates=["date", "delivery_month", "expiry_ho", "expiry_cl"],
    ).sort_values("date")
    market = market.reset_index(drop=True)
    market["spread_change"] = market["gross_change_per_bbl"]
    market["year"] = market["date"].dt.year
    market["month"] = market["date"].dt.month

    for horizon in (5, 10, 20):
        market[f"forward_{horizon}d"] = sum(
            market["spread_change"].shift(-offset)
            for offset in range(1, horizon + 1)
        )
    for horizon in (10, 20, 40):
        market[f"momentum_{horizon}d"] = (
            market["synthetic_crack_index"]
            - market["synthetic_crack_index"].shift(horizon)
        )

    eia = _load_eia(INVENTORY_PATH, "inventory")
    eia = eia.merge(_load_eia(DEMAND_PATH, "demand"), on="week_end", how="outer")
    eia = eia.merge(
        _load_eia(UTILIZATION_PATH, "utilization"),
        on="week_end",
        how="outer",
    ).sort_values("week_end")
    eia = eia.reset_index(drop=True)

    for column in ("inventory", "demand", "utilization"):
        eia[f"{column}_z"] = _seasonal_trailing_zscore(eia, column)
        eia[f"{column}_change_4w"] = eia[column].diff(4)

    # EIA normally publishes the Friday observation on Wednesday.
    # Thursday availability is used to remain conservative around holidays.
    eia["available_date"] = eia["week_end"] + pd.Timedelta(days=6)
    panel = pd.merge_asof(
        market,
        eia,
        left_on="date",
        right_on="available_date",
        direction="backward",
    )
    panel["eia_update"] = panel["week_end"].ne(panel["week_end"].shift())
    panel["period"] = np.where(
        panel["date"] <= DEVELOPMENT_END,
        "2010-2020 development",
        "2021-2025 validation",
    )

    assert len(panel) == 4_031
    assert panel["date"].is_monotonic_increasing
    assert panel["gross_pnl"].iloc[1:].notna().all()
    assert not (panel["available_date"] > panel["date"]).any()
    assert panel.loc[panel["date"] == "2020-04-20", "contract_alias_cl"].item() == "CL19M20"
    return panel


def hypothesis_tables(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    monthly = (
        panel.groupby(["period", "year", "month"], as_index=False)["spread_change"]
        .sum()
        .groupby(["period", "month"])["spread_change"]
        .agg(["count", "mean", "std"])
        .reset_index()
    )
    monthly["t_stat_across_years"] = monthly["mean"] / (
        monthly["std"] / np.sqrt(monthly["count"])
    )

    development = panel[panel["date"] <= DEVELOPMENT_END]
    momentum_rows = []
    for horizon in (10, 20, 40):
        column = f"momentum_{horizon}d"
        cutoffs = development[column].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
        bins = [-np.inf, *cutoffs, np.inf]
        for period, group in panel.groupby("period", sort=False):
            bucket = pd.cut(
                group[column],
                bins=bins,
                labels=[1, 2, 3, 4, 5],
                include_lowest=True,
            )
            summary = group.groupby(bucket, observed=True)["forward_20d"].agg(
                ["count", "mean", "median", "std"]
            )
            for bucket_number, row in summary.iterrows():
                momentum_rows.append(
                    {
                        "period": period,
                        "momentum_horizon": horizon,
                        "bucket": int(bucket_number),
                        **row.to_dict(),
                    }
                )
    momentum = pd.DataFrame(momentum_rows)

    inventory_cutoffs = development["inventory_z"].quantile([1 / 3, 2 / 3]).to_numpy()
    inventory_rows = []
    for period, group in panel.groupby("period", sort=False):
        bucket = pd.cut(
            group["inventory_z"],
            bins=[-np.inf, *inventory_cutoffs, np.inf],
            labels=["low", "normal", "high"],
        )
        summary = group.groupby(bucket, observed=True).agg(
            count=("forward_20d", "count"),
            forward_5d=("forward_5d", "mean"),
            forward_10d=("forward_10d", "mean"),
            forward_20d=("forward_20d", "mean"),
        )
        for inventory_bucket, row in summary.iterrows():
            inventory_rows.append(
                {
                    "period": period,
                    "inventory_bucket": inventory_bucket,
                    **row.to_dict(),
                }
            )
    inventory = pd.DataFrame(inventory_rows)

    return {
        "monthly": monthly,
        "momentum": momentum,
        "inventory": inventory,
    }


def _load_yahoo_chart(path: Path, name: str) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    dates = (
        pd.to_datetime(result["timestamp"], unit="s", utc=True)
        .tz_convert("America/New_York")
        .normalize()
        .tz_localize(None)
    )
    return pd.DataFrame({"date": dates, name: quote["close"]}).dropna()


def free_secondary_validation(panel: pd.DataFrame) -> tuple[dict[str, float], pd.DataFrame]:
    """Compare the primary series with free vendor-built continuous data."""
    yahoo = _load_yahoo_chart(YAHOO_HO_PATH, "yahoo_ho").merge(
        _load_yahoo_chart(YAHOO_CL_PATH, "yahoo_cl"),
        on="date",
        how="inner",
    )
    yahoo["yahoo_crack"] = 42.0 * yahoo["yahoo_ho"] - yahoo["yahoo_cl"]
    yahoo["yahoo_change"] = yahoo["yahoo_crack"].diff()
    comparison = panel.merge(yahoo, on="date", how="inner")
    valid = comparison.dropna(subset=["yahoo_change", "spread_change"])
    non_roll = valid[~valid["is_roll"]]
    roll = valid[valid["is_roll"]]
    summary = {
        "matched_sessions": int(len(comparison)),
        "ho_price_level_correlation": float(comparison["yahoo_ho"].corr(comparison["close_ho"])),
        "cl_price_level_correlation": float(comparison["yahoo_cl"].corr(comparison["close_cl"])),
        "daily_crack_change_correlation": float(valid["yahoo_change"].corr(valid["spread_change"])),
        "non_roll_daily_change_correlation": float(non_roll["yahoo_change"].corr(non_roll["spread_change"])),
        "roll_daily_change_correlation": float(roll["yahoo_change"].corr(roll["spread_change"])),
        "non_roll_direction_agreement": float(
            (np.sign(non_roll["yahoo_change"]) == np.sign(non_roll["spread_change"])).mean()
        ),
        "non_roll_mean_absolute_difference": float(
            (non_roll["yahoo_change"] - non_roll["spread_change"]).abs().mean()
        ),
    }
    comparison["year"] = comparison["date"].dt.year
    comparison["month"] = comparison["date"].dt.month
    comparison["period"] = np.where(
        comparison["date"] <= DEVELOPMENT_END,
        "2010-2020 development",
        "2021-2025 validation",
    )
    monthly = (
        comparison.groupby(["period", "year", "month"], as_index=False)["yahoo_change"]
        .sum()
        .groupby(["period", "month"])["yahoo_change"]
        .agg(["count", "mean", "std"])
        .reset_index()
    )
    return summary, monthly


def _trade_episodes(daily: pd.DataFrame) -> pd.DataFrame:
    """Group holding days into campaigns using entry-adjusted cost attribution.

    A cost booked at the close of session t that opens or increases exposure is
    only paid for by the position held from t+1 onward, so charging it to
    session t would leave it outside the episode entirely. ``attributed_cost``
    moves those opening costs one session forward, which makes the sum of trade
    net P&L reconcile exactly with the daily net P&L series.
    """
    active = daily["held_units"] != 0
    episode_start = active & ~active.shift(fill_value=False)
    episode_id = episode_start.cumsum().where(active)
    trades = (
        daily.loc[active]
        .assign(episode=episode_id[active])
        .groupby("episode", as_index=False)
        .agg(
            entry_date=("date", "min"),
            exit_date=("date", "max"),
            direction=("held_units", lambda values: int(np.sign(values.iloc[0]))),
            gross_pnl=("gross_pnl_strategy", "sum"),
            costs=("attributed_cost", "sum"),
        )
    )
    trades["net_pnl"] = trades["gross_pnl"] - trades["costs"]
    return trades


def backtest_signal(
    panel: pd.DataFrame,
    signal: pd.Series,
    rebalance: pd.Series,
    volatility_window: int = 60,
    pair_cost: float = BASE_PAIR_COST,
) -> BacktestResult:
    output = panel[["date", "gross_pnl", "is_roll"]].copy()
    output["signal_at_close"] = signal.astype(float)
    trailing_volatility = panel["gross_pnl"].rolling(
        volatility_window,
        min_periods=max(30, volatility_window // 2),
    ).std()
    daily_risk_budget = TARGET_VOLATILITY * CAPITAL / math.sqrt(252.0)
    target_units = np.floor(daily_risk_budget / trailing_volatility).clip(0, 10)
    desired = (output["signal_at_close"] * target_units).where(rebalance).ffill().fillna(0.0)
    output["desired_units_at_close"] = desired
    output["held_units"] = desired.shift(1).fillna(0.0)
    output["gross_pnl_strategy"] = (
        output["held_units"] * output["gross_pnl"].fillna(0.0)
    )

    previous_desired = desired.shift(1).fillna(0.0)
    overlap = np.where(
        np.sign(previous_desired) == np.sign(desired),
        np.minimum(previous_desired.abs(), desired.abs()),
        0.0,
    )
    closed_units = previous_desired.abs() - overlap
    opened_units = desired.abs() - overlap
    output["signal_trade_cost"] = (closed_units + opened_units) * pair_cost
    previous_held = output["held_units"].shift(1).fillna(0.0)
    same_direction_carry = output["held_units"] * previous_held > 0
    carried_units = np.minimum(output["held_units"].abs(), previous_held.abs())
    output["roll_cost"] = np.where(
        output["is_roll"] & same_direction_carry,
        carried_units * 2.0 * pair_cost,
        0.0,
    )
    output["cost"] = output["signal_trade_cost"] + output["roll_cost"]
    # Opening costs are paid at close of t but belong to the position held from
    # t+1, so shift them forward before attributing costs to a campaign.
    output["attributed_cost"] = (
        closed_units * pair_cost
        + output["roll_cost"]
        + (opened_units * pair_cost).shift(1).fillna(0.0)
    )
    output["net_pnl_strategy"] = output["gross_pnl_strategy"] - output["cost"]
    output["return"] = output["net_pnl_strategy"] / CAPITAL
    output["equity"] = CAPITAL + output["net_pnl_strategy"].cumsum()
    output["drawdown"] = output["equity"] / output["equity"].cummax() - 1.0
    return BacktestResult(output, _trade_episodes(output))


def calculate_metrics(result: BacktestResult, start: str, end: str) -> dict[str, float]:
    start_date = pd.Timestamp(start)
    end_date = pd.Timestamp(end)
    daily = result.daily[result.daily["date"].between(start_date, end_date)].copy()
    trades = result.trades[
        result.trades["entry_date"].between(start_date, end_date)
    ].copy()
    returns = daily["return"]
    annual_return = returns.mean() * 252.0
    annual_volatility = returns.std(ddof=1) * math.sqrt(252.0)
    downside = np.sqrt(np.mean(np.minimum(returns, 0.0) ** 2)) * math.sqrt(252.0)
    equity = CAPITAL + daily["net_pnl_strategy"].cumsum()
    max_drawdown = (equity / equity.cummax() - 1.0).min()
    positive = trades.loc[trades["net_pnl"] > 0, "net_pnl"]
    negative = trades.loc[trades["net_pnl"] < 0, "net_pnl"]
    years = len(daily) / 252.0
    return {
        "annualized_return": annual_return,
        "annualized_volatility": annual_volatility,
        "sharpe": annual_return / annual_volatility if annual_volatility else np.nan,
        "sortino": annual_return / downside if downside else np.nan,
        "maximum_drawdown": max_drawdown,
        "calmar": annual_return / abs(max_drawdown) if max_drawdown else np.nan,
        "net_pnl": daily["net_pnl_strategy"].sum(),
        "gross_pnl": daily["gross_pnl_strategy"].sum(),
        "costs": daily["cost"].sum(),
        "trade_count": len(trades),
        "win_rate": (trades["net_pnl"] > 0).mean() if len(trades) else np.nan,
        "average_winner": positive.mean() if len(positive) else np.nan,
        "average_loser": negative.mean() if len(negative) else np.nan,
        "profit_factor": positive.sum() / abs(negative.sum()) if len(negative) else np.nan,
        "exposure": (daily["held_units"] != 0).mean(),
        "spread_unit_turnover_per_year": (
            daily["desired_units_at_close"].diff().abs().sum() / years
            if years
            else np.nan
        ),
    }


def seasonal_signal(panel: pd.DataFrame, start_month: int, end_month: int) -> pd.Series:
    # The close-of-session decision determines exposure for the next interval.
    # Use the next observed session's month so every selected month's return is
    # included without carrying the position into the following month.
    next_month = panel["month"].shift(-1)
    return next_month.between(start_month, end_month).astype(float)


def weekly_or_signal_change(panel: pd.DataFrame, signal: pd.Series) -> pd.Series:
    iso = panel["date"].dt.isocalendar()
    week_key = iso["year"].astype(str) + "-" + iso["week"].astype(str)
    return week_key.ne(week_key.shift()) | signal.ne(signal.shift())


def run_backtests(panel: pd.DataFrame) -> dict[str, object]:
    primary_signal = seasonal_signal(panel, 7, 10)
    primary = backtest_signal(
        panel,
        primary_signal,
        weekly_or_signal_change(panel, primary_signal),
    )

    development = panel[panel["date"] <= DEVELOPMENT_END]
    low_inventory, high_inventory = development["inventory_z"].quantile([1 / 3, 2 / 3])
    original_signal = pd.Series(
        np.where(
            (panel["momentum_20d"] > 0) & (panel["inventory_z"] < low_inventory),
            1.0,
            np.where(
                (panel["momentum_20d"] < 0)
                & (panel["inventory_z"] > high_inventory),
                -1.0,
                0.0,
            ),
        ),
        index=panel.index,
    )
    original = backtest_signal(panel, original_signal, panel["eia_update"])

    periods = {
        "2010-2020 development": ("2010-01-01", "2020-12-31"),
        "2021-2025 validation": ("2021-01-01", "2025-12-31"),
        "2010-2025 full": ("2010-01-01", "2025-12-31"),
    }
    metric_rows = []
    for strategy_name, result in (
        ("July-October seasonal", primary),
        ("Original momentum-inventory", original),
    ):
        for period_name, (start, end) in periods.items():
            metric_rows.append(
                {
                    "strategy": strategy_name,
                    "period": period_name,
                    **calculate_metrics(result, start, end),
                }
            )
    metrics = pd.DataFrame(metric_rows)

    window_rows = []
    for start_month, end_month in ((6, 10), (7, 9), (7, 10), (8, 10), (7, 11)):
        signal = seasonal_signal(panel, start_month, end_month)
        result = backtest_signal(panel, signal, weekly_or_signal_change(panel, signal))
        for period_name, (start, end) in periods.items():
            row = calculate_metrics(result, start, end)
            window_rows.append(
                {
                    "start_month": start_month,
                    "end_month": end_month,
                    "period": period_name,
                    "annualized_return": row["annualized_return"],
                    "annualized_volatility": row["annualized_volatility"],
                    "sharpe": row["sharpe"],
                    "maximum_drawdown": row["maximum_drawdown"],
                    "trade_count": row["trade_count"],
                }
            )
    windows = pd.DataFrame(window_rows)

    cost_rows = []
    for ticks in (0.5, 1.0, 2.0):
        for fee in (0.0, 2.5, 5.0):
            pair_cost = HO_TICK_DOLLARS * ticks + CL_TICK_DOLLARS * ticks + 2.0 * fee
            result = backtest_signal(
                panel,
                primary_signal,
                weekly_or_signal_change(panel, primary_signal),
                pair_cost=pair_cost,
            )
            row = calculate_metrics(result, "2010-01-01", "2025-12-31")
            cost_rows.append(
                {
                    "slippage_ticks_per_contract_side": ticks,
                    "fee_per_contract_side": fee,
                    "annualized_return": row["annualized_return"],
                    "sharpe": row["sharpe"],
                    "maximum_drawdown": row["maximum_drawdown"],
                    "total_costs": row["costs"],
                }
            )
    costs = pd.DataFrame(cost_rows)

    yearly = (
        primary.daily.assign(year=primary.daily["date"].dt.year)
        .groupby("year", as_index=False)
        .agg(
            gross_pnl=("gross_pnl_strategy", "sum"),
            costs=("cost", "sum"),
            net_pnl=("net_pnl_strategy", "sum"),
            maximum_drawdown=("drawdown", "min"),
        )
    )
    return {
        "primary": primary,
        "original": original,
        "metrics": metrics,
        "windows": windows,
        "costs": costs,
        "yearly": yearly,
        "inventory_cutoffs": {
            "low": float(low_inventory),
            "high": float(high_inventory),
        },
    }


def campaign_bootstrap(
    trades: pd.DataFrame,
    draws: int = 20_000,
    seed: int = 20260903,
) -> dict[str, float]:
    """Resample annual campaign P&L to bound the mean campaign outcome.

    The strategy holds one position per year, so the 16 campaigns - not the
    ~1,375 holding days - are the independent observations. The interval below
    only reflects sampling noise and says nothing about structural change.
    """
    outcomes = trades["net_pnl"].to_numpy(dtype=float)
    generator = np.random.default_rng(seed)
    sample_means = generator.choice(
        outcomes,
        size=(draws, len(outcomes)),
        replace=True,
    ).mean(axis=1)
    standard_error = outcomes.std(ddof=1) / math.sqrt(len(outcomes))
    return {
        "campaigns": int(len(outcomes)),
        "draws": draws,
        "seed": seed,
        "mean_campaign_pnl": float(outcomes.mean()),
        "median_campaign_pnl": float(np.median(outcomes)),
        "bootstrap_mean_lower_95": float(np.percentile(sample_means, 2.5)),
        "bootstrap_mean_upper_95": float(np.percentile(sample_means, 97.5)),
        "share_of_draws_above_zero": float((sample_means > 0).mean()),
        "campaign_t_statistic": float(outcomes.mean() / standard_error),
    }


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "Arial Bold.ttf" if bold else "Arial.ttf"
    return ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{filename}", size)


def _draw_axes(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str) -> None:
    x0, y0, x1, y1 = box
    draw.text((x0, y0 - 42), title, fill="#14213d", font=_font(25, True))
    draw.line((x0, y1, x1, y1), fill="#6b7280", width=2)
    draw.line((x0, y0, x0, y1), fill="#6b7280", width=2)


def create_figures(
    panel: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    backtests: dict[str, object],
) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1800, 1200), "#fbfbf8")
    draw = ImageDraw.Draw(image)
    draw.text((70, 28), "ULSD-WTI Crack Spread Research Summary", fill="#102a43", font=_font(36, True))
    draw.text(
        (70, 75),
        "One HO contract long, one CL contract short; roll-aware daily P&L",
        fill="#486581",
        font=_font(20),
    )

    # Panel 1: average monthly spread change across years.
    box1 = (90, 175, 850, 520)
    _draw_axes(draw, box1, "Average monthly change by calendar month ($/bbl)")
    monthly = tables["monthly"]
    dev = monthly[monthly["period"] == "2010-2020 development"].set_index("month")["mean"]
    val = monthly[monthly["period"] == "2021-2025 validation"].set_index("month")["mean"]
    maximum = max(abs(pd.concat([dev, val])).max(), 1.0)
    center = (box1[1] + box1[3]) / 2
    draw.line((box1[0], center, box1[2], center), fill="#9ca3af", width=1)
    draw.text((box1[0] - 62, box1[1] - 8), f"+{maximum:.1f}", fill="#4b5563", font=_font(15))
    draw.text((box1[0] - 58, center - 10), "0", fill="#4b5563", font=_font(15))
    draw.text((box1[0] - 58, box1[3] - 18), f"-{maximum:.1f}", fill="#4b5563", font=_font(15))
    slot = (box1[2] - box1[0]) / 12
    for month in range(1, 13):
        left = box1[0] + (month - 1) * slot + 8
        for value, color, offset in ((dev[month], "#2f6f9f", 0), (val[month], "#e07a5f", 19)):
            height = value / maximum * 135
            top = center - height if value >= 0 else center
            bottom = center if value >= 0 else center - height
            draw.rectangle((left + offset, top, left + offset + 15, bottom), fill=color)
        draw.text((left + 7, box1[3] + 8), str(month), fill="#4b5563", font=_font(16))
    draw.rectangle((box1[0] + 15, box1[1] + 10, box1[0] + 35, box1[1] + 30), fill="#2f6f9f")
    draw.text((box1[0] + 43, box1[1] + 9), "Development", fill="#374151", font=_font(17))
    draw.rectangle((box1[0] + 165, box1[1] + 10, box1[0] + 185, box1[1] + 30), fill="#e07a5f")
    draw.text((box1[0] + 193, box1[1] + 9), "Validation", fill="#374151", font=_font(17))

    # Panel 2: inventory relationship changes sign across samples.
    box2 = (980, 175, 1720, 520)
    _draw_axes(draw, box2, "20-day forward change by inventory state ($/bbl)")
    inv = tables["inventory"]
    labels = ["low", "normal", "high"]
    values = []
    for label in labels:
        values.extend(
            inv.loc[inv["inventory_bucket"] == label, "forward_20d"].tolist()
        )
    minimum, maximum_inv = min(values + [0]), max(values + [0])
    scale = 240 / max(maximum_inv - minimum, 1.0)
    zero_y = box2[3] - (0 - minimum) * scale
    draw.line((box2[0], zero_y, box2[2], zero_y), fill="#9ca3af", width=1)
    draw.text((box2[0] - 55, box2[1] - 8), f"{maximum_inv:.1f}", fill="#4b5563", font=_font(15))
    draw.text((box2[0] - 35, zero_y - 10), "0", fill="#4b5563", font=_font(15))
    for index, label in enumerate(labels):
        base_x = box2[0] + 80 + index * 210
        counts = []
        for period, color, offset in (
            ("2010-2020 development", "#2f6f9f", 0),
            ("2021-2025 validation", "#e07a5f", 48),
        ):
            row = inv.loc[
                (inv["period"] == period) & (inv["inventory_bucket"] == label)
            ]
            value = row["forward_20d"].item()
            counts.append(int(row["count"].item()))
            value_y = zero_y - value * scale
            draw.rectangle(
                (base_x + offset, min(zero_y, value_y), base_x + offset + 38, max(zero_y, value_y)),
                fill=color,
            )
        draw.text((base_x + 20, box2[3] + 8), label.title(), fill="#4b5563", font=_font(17))
        draw.text(
            (base_x - 2, box2[3] + 30),
            f"n={counts[0]} / {counts[1]}",
            fill="#6b7280",
            font=_font(14),
        )
    draw.text(
        (box2[0], box2[3] + 56),
        "Buckets use development terciles; validation rarely reached the high-inventory state.",
        fill="#6b7280",
        font=_font(14),
    )

    # Panel 3: cumulative net P&L for the two rule sets.
    box3 = (90, 675, 1150, 1080)
    _draw_axes(draw, box3, "Cumulative net P&L on $1 million risk budget")
    lines = [
        (backtests["primary"].daily, "#2a9d8f", "July-October seasonal"),
        (backtests["original"].daily, "#9b2226", "Original momentum-inventory"),
    ]
    all_curves = [item[0]["net_pnl_strategy"].cumsum() for item in lines]
    ymin = min(curve.min() for curve in all_curves)
    ymax = max(curve.max() for curve in all_curves)
    for data, color, _ in lines:
        curve = data["net_pnl_strategy"].cumsum().to_numpy()
        points = []
        for index, value in enumerate(curve):
            x = box3[0] + index / (len(curve) - 1) * (box3[2] - box3[0])
            y = box3[3] - (value - ymin) / (ymax - ymin) * (box3[3] - box3[1])
            points.append((x, y))
        draw.line(points, fill=color, width=4)
    draw.text((box3[0] - 78, box3[1] - 8), f"${ymax/1000:.0f}k", fill="#4b5563", font=_font(15))
    draw.text((box3[0] - 78, box3[3] - 18), f"${ymin/1000:.0f}k", fill="#4b5563", font=_font(15))
    split_index = panel.index[panel["date"] >= "2021-01-01"][0]
    split_x = box3[0] + split_index / (len(panel) - 1) * (box3[2] - box3[0])
    draw.line((split_x, box3[1], split_x, box3[3]), fill="#6b7280", width=2)
    draw.text((split_x + 8, box3[1] + 8), "2021 validation start", fill="#4b5563", font=_font(16))
    for year in (2010, 2015, 2020, 2025):
        year_index = panel.index[panel["date"].dt.year >= year][0]
        year_x = box3[0] + year_index / (len(panel) - 1) * (box3[2] - box3[0])
        draw.text((year_x - 18, box3[3] + 8), str(year), fill="#4b5563", font=_font(15))
    for index, (_, color, label) in enumerate(lines):
        y = box3[1] + 45 + index * 30
        draw.line((box3[0] + 15, y, box3[0] + 55, y), fill=color, width=5)
        draw.text((box3[0] + 65, y - 10), label, fill="#374151", font=_font(17))

    # Panel 4: compact measured conclusion.
    box4 = (1230, 675, 1720, 1080)
    draw.rounded_rectangle(box4, radius=18, fill="#eef4f7", outline="#9fb3c8", width=2)
    draw.text((box4[0] + 30, box4[1] + 28), "Measured conclusion", fill="#102a43", font=_font(25, True))
    conclusion_lines = [
        "• Winter was not consistently bullish.",
        "• 10-40 day momentum was weak.",
        "• Inventory effects reversed by sample.",
        "• July-October was the most stable",
        "  simple seasonal window.",
        "• The original thesis is not yet",
        "  validated as a robust alpha signal.",
    ]
    y = box4[1] + 90
    for line in conclusion_lines:
        draw.text((box4[0] + 30, y), line, fill="#334e68", font=_font(20))
        y += 40

    image.save(FIGURES / "research_summary.png")


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    panel = build_research_panel()
    tables = hypothesis_tables(panel)
    backtests = run_backtests(panel)
    secondary_summary, secondary_monthly = free_secondary_validation(panel)

    panel.to_csv(PROCESSED / "research_panel.csv", index=False)
    tables["monthly"].to_csv(PROCESSED / "seasonality_monthly.csv", index=False)
    tables["momentum"].to_csv(PROCESSED / "momentum_quantiles.csv", index=False)
    tables["inventory"].to_csv(PROCESSED / "inventory_terciles.csv", index=False)
    backtests["primary"].daily.to_csv(PROCESSED / "strategy_daily.csv", index=False)
    backtests["primary"].trades.to_csv(PROCESSED / "strategy_trades.csv", index=False)
    backtests["original"].daily.to_csv(PROCESSED / "original_strategy_daily.csv", index=False)
    backtests["metrics"].to_csv(PROCESSED / "strategy_metrics.csv", index=False)
    backtests["windows"].to_csv(PROCESSED / "robustness_windows.csv", index=False)
    backtests["costs"].to_csv(PROCESSED / "cost_sensitivity.csv", index=False)
    backtests["yearly"].to_csv(PROCESSED / "strategy_yearly.csv", index=False)
    secondary_monthly.to_csv(PROCESSED / "free_validation_monthly.csv", index=False)
    (PROCESSED / "free_validation_summary.json").write_text(
        json.dumps(secondary_summary, indent=2),
        encoding="utf-8",
    )

    summary = {
        "data": {
            "first_date": panel["date"].min().date().isoformat(),
            "last_date": panel["date"].max().date().isoformat(),
            "sessions": len(panel),
            "rolls_excluding_initial": int(panel["is_roll"].sum() - 1),
            "eia_publication_delay_days": 6,
        },
        "inventory_z_development_terciles": backtests["inventory_cutoffs"],
        "campaign_bootstrap": campaign_bootstrap(backtests["primary"].trades),
        "free_secondary_validation": secondary_summary,
        "metrics": backtests["metrics"].to_dict(orient="records"),
        "conclusion": (
            "The pre-specified momentum plus low-inventory thesis is unstable. "
            "A contiguous July-October long crack window is the strongest simple "
            "candidate, but it remains a research candidate rather than validated alpha."
        ),
    }
    (PROCESSED / "research_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    create_figures(panel, tables, backtests)


if __name__ == "__main__":
    main()
