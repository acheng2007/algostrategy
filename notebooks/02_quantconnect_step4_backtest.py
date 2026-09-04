"""QuantConnect backtest fallback for Step 4 contract-series validation.

Paste this file into ``main.py`` in the QuantConnect cloud project and run a
backtest.  It computes a matched HO-CL series without placing trades.  Only
summary diagnostics are written to the log.
"""

from AlgorithmImports import *
from collections import defaultdict
from datetime import timedelta
from statistics import median, stdev


class StepFourCrackValidation(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2010, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(1_000_000)

        self.ho = self.add_future(
            Futures.Energy.HEATING_OIL,
            Resolution.DAILY,
            extended_market_hours=False,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            data_normalization_mode=DataNormalizationMode.RAW,
            contract_depth_offset=0,
        )
        self.cl = self.add_future(
            Futures.Energy.CRUDE_OIL_WTI,
            Resolution.DAILY,
            extended_market_hours=False,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            data_normalization_mode=DataNormalizationMode.RAW,
            contract_depth_offset=0,
        )
        self.ho.set_filter(0, 180)
        self.cl.set_filter(0, 180)

        self.previous_prices = {}
        self.previous_pair = None
        self.previous_date = None
        self.previous_crack = None
        self.sessions = 0
        self.intervals = 0
        self.rolls = 0
        self.missing_pair_sessions = 0
        self.missing_reference_intervals = 0
        self.bad_month_advances = 0
        self.bad_roll_cutoffs = 0
        self.gross_pnl = []
        self.roll_pnl = []
        self.non_roll_pnl = []
        self.roll_gap_errors = []
        self.roll_dates = []
        self.roll_sides = 0
        self.min_cl_price = float("inf")
        self.min_cl_symbol = None
        self.min_cl_date = None
        self.negative_cl_count = 0
        self.first_selected_date = None
        self.last_selected_date = None
        self.month_counts = defaultdict(int)

    @staticmethod
    def _contract_month(contract):
        """Use the common expiry month as a delivery-month proxy.

        Standard HO and CL contracts for the same delivery month both expire
        in the preceding calendar month, although on different days.
        """
        expiry = contract.expiry
        return expiry.year, expiry.month

    @staticmethod
    def _business_days_after(start_date, end_date):
        count = 0
        day = start_date + timedelta(days=1)
        while day <= end_date:
            if day.weekday() < 5:
                count += 1
            day += timedelta(days=1)
        return count

    def _contracts_by_month(self, chain):
        result = {}
        for contract in chain:
            if contract.last_price == 0:
                continue
            key = self._contract_month(contract)
            current = result.get(key)
            if current is None or contract.expiry < current.expiry:
                result[key] = contract
        return result

    def on_data(self, data: Slice) -> None:
        ho_chain = data.future_chains.get(self.ho.symbol)
        cl_chain = data.future_chains.get(self.cl.symbol)
        if ho_chain is None or cl_chain is None:
            self.missing_pair_sessions += 1
            return

        ho_by_month = self._contracts_by_month(ho_chain)
        cl_by_month = self._contracts_by_month(cl_chain)
        today = self.time.date()

        for contract in cl_chain:
            price = float(contract.last_price)
            if price < self.min_cl_price:
                self.min_cl_price = price
                self.min_cl_symbol = str(contract.symbol)
                self.min_cl_date = today
            if price < 0:
                self.negative_cl_count += 1

        current_prices = {}
        for contract in list(ho_chain) + list(cl_chain):
            current_prices[contract.symbol] = float(contract.last_price)

        candidates = []
        for month in set(ho_by_month).intersection(cl_by_month):
            ho_contract = ho_by_month[month]
            cl_contract = cl_by_month[month]
            earlier_expiry = min(ho_contract.expiry, cl_contract.expiry).date()
            if self._business_days_after(today, earlier_expiry) >= 5:
                candidates.append((month, ho_contract, cl_contract))

        if not candidates:
            self.missing_pair_sessions += 1
            self.previous_prices = current_prices
            return

        month, ho_contract, cl_contract = min(candidates, key=lambda row: row[0])
        pair = (
            month,
            ho_contract.symbol,
            cl_contract.symbol,
            ho_contract.expiry.date(),
            cl_contract.expiry.date(),
        )
        ho_price = float(ho_contract.last_price)
        cl_price = float(cl_contract.last_price)
        crack = 42.0 * ho_price - cl_price
        is_roll = self.previous_pair is not None and pair[0] != self.previous_pair[0]

        self.sessions += 1
        self.month_counts[month] += 1
        self.first_selected_date = self.first_selected_date or today
        self.last_selected_date = today

        if self.previous_pair is None:
            self.roll_sides += 2
        else:
            reference_ho = self.previous_prices.get(ho_contract.symbol)
            reference_cl = self.previous_prices.get(cl_contract.symbol)
            if reference_ho is None or reference_cl is None:
                self.missing_reference_intervals += 1
            else:
                gross = (
                    42_000.0 * (ho_price - reference_ho)
                    - 1_000.0 * (cl_price - reference_cl)
                )
                naive = 1_000.0 * (crack - self.previous_crack)
                self.gross_pnl.append(gross)
                self.intervals += 1
                if is_roll:
                    self.roll_pnl.append(gross)
                    self.roll_gap_errors.append(naive - gross)
                else:
                    self.non_roll_pnl.append(gross)

        if is_roll:
            self.rolls += 1
            self.roll_sides += 4
            old_month = self.previous_pair[0]
            months_advanced = (
                (month[0] - old_month[0]) * 12 + month[1] - old_month[1]
            )
            if months_advanced != 1:
                self.bad_month_advances += 1
            earlier_old_expiry = min(
                self.previous_pair[3], self.previous_pair[4]
            )
            days_before = self._business_days_after(
                self.previous_date, earlier_old_expiry
            )
            if days_before < 5:
                self.bad_roll_cutoffs += 1
            if len(self.roll_dates) < 12:
                self.roll_dates.append(
                    (self.previous_date, old_month, month, days_before)
                )

        self.previous_pair = pair
        self.previous_date = today
        self.previous_crack = crack
        self.previous_prices = current_prices

    @staticmethod
    def _sample_std(values):
        return stdev(values) if len(values) > 1 else float("nan")

    def on_end_of_algorithm(self) -> None:
        assert self.sessions > 0
        assert self.intervals > 0
        assert self.missing_reference_intervals == 0
        assert self.bad_month_advances == 0
        assert self.bad_roll_cutoffs == 0
        absolute_errors = [abs(value) for value in self.roll_gap_errors]
        base_cost = self.roll_sides * (4.20 + 10.00 + 2 * 2.50) / 2

        self.log(
            "STEP4 COVERAGE | sessions={} | intervals={} | rolls={} | "
            "first={} | last={} | missing_pair_sessions={} | "
            "missing_reference_intervals={}".format(
                self.sessions,
                self.intervals,
                self.rolls,
                self.first_selected_date,
                self.last_selected_date,
                self.missing_pair_sessions,
                self.missing_reference_intervals,
            )
        )
        self.log(
            "STEP4 ROLL AUDIT | bad_month_advances={} | "
            "bad_roll_cutoffs={} | examples={}".format(
                self.bad_month_advances,
                self.bad_roll_cutoffs,
                self.roll_dates,
            )
        )
        self.log(
            "STEP4 PNL | daily_std={:.2f} | roll_std={:.2f} | "
            "non_roll_std={:.2f} | median_abs_roll_gap={:.2f} | "
            "max_abs_roll_gap={:.2f}".format(
                self._sample_std(self.gross_pnl),
                self._sample_std(self.roll_pnl),
                self._sample_std(self.non_roll_pnl),
                median(absolute_errors),
                max(absolute_errors),
            )
        )
        self.log(
            "STEP4 NEGATIVE CL | minimum={} | symbol={} | date={} | "
            "negative_observations={}".format(
                self.min_cl_price,
                self.min_cl_symbol,
                self.min_cl_date,
                self.negative_cl_count,
            )
        )
        self.log(
            "STEP4 BASE MAINTENANCE COST | contract_sides={} | total={:.2f}".format(
                self.roll_sides,
                base_cost,
            )
        )
        for ticks in (0.5, 1.0, 2.0):
            for fee in (0.0, 2.5, 5.0):
                cost_per_coordinated_side = 4.20 * ticks + 10.00 * ticks + 2 * fee
                total_cost = self.roll_sides * cost_per_coordinated_side / 2
                self.log(
                    "STEP4 COST | ticks={} | fee={} | total={:.2f}".format(
                        ticks, fee, total_cost
                    )
                )
        self.log(
            "STEP4 NEGATIVE VENDOR CLOSE CHECK | expected_minus_13_10={}".format(
                abs(self.min_cl_price + 13.10) < 1e-9
            )
        )
        self.log("PASS: Step 4 roll and P&L internal audits are complete.")
