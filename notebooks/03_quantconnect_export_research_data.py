"""Export the coordinated HO-CL research series from QuantConnect.

Paste this file into ``main.py`` in your QuantConnect project and run a
backtest.  The algorithm does not place trades.  It writes the selected daily
contract pair and roll-aware P&L to the project Object Store so the hypothesis
tests can be reproduced locally.
"""

from AlgorithmImports import *
from datetime import timedelta
import csv
import io


class CrackResearchExport(QCAlgorithm):

    object_store_key = "algogators/crack_research_daily.csv"

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
        self.rows = []
        self.synthetic_crack_index = 0.0

    @staticmethod
    def _contract_month(contract):
        """Return the common expiry month used by the validated Step 4 audit."""
        return contract.expiry.year, contract.expiry.month

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
            return

        ho_by_month = self._contracts_by_month(ho_chain)
        cl_by_month = self._contracts_by_month(cl_chain)
        today = self.time.date()

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
        quoted_crack = 42.0 * ho_price - cl_price
        is_roll = self.previous_pair is not None and month != self.previous_pair[0]

        gross_pnl = None
        spread_change = None
        if self.previous_pair is not None:
            reference_ho = self.previous_prices.get(ho_contract.symbol)
            reference_cl = self.previous_prices.get(cl_contract.symbol)
            if reference_ho is None or reference_cl is None:
                raise ValueError("Missing same-contract reference price")
            gross_pnl = (
                42_000.0 * (ho_price - reference_ho)
                - 1_000.0 * (cl_price - reference_cl)
            )
            spread_change = gross_pnl / 1_000.0
            self.synthetic_crack_index += spread_change

        earlier_expiry = min(ho_contract.expiry, cl_contract.expiry).date()
        self.rows.append(
            {
                "date": today.isoformat(),
                "delivery_year": month[0],
                "delivery_month": month[1],
                "ho_symbol": str(ho_contract.symbol),
                "cl_symbol": str(cl_contract.symbol),
                "ho_expiry": ho_contract.expiry.date().isoformat(),
                "cl_expiry": cl_contract.expiry.date().isoformat(),
                "business_days_to_earlier_expiry": self._business_days_after(
                    today, earlier_expiry
                ),
                "ho_price_usd_per_gallon": "{:.8f}".format(ho_price),
                "cl_price_usd_per_barrel": "{:.8f}".format(cl_price),
                "quoted_crack_usd_per_barrel": "{:.8f}".format(quoted_crack),
                "spread_change_usd_per_barrel": (
                    "" if spread_change is None else "{:.8f}".format(spread_change)
                ),
                "gross_pnl_usd_per_spread": (
                    "" if gross_pnl is None else "{:.4f}".format(gross_pnl)
                ),
                "synthetic_crack_index": "{:.8f}".format(
                    self.synthetic_crack_index
                ),
                "is_roll": int(is_roll),
            }
        )

        self.previous_pair = pair
        self.previous_date = today
        self.previous_prices = current_prices

    def on_end_of_algorithm(self) -> None:
        if len(self.rows) < 4_000:
            raise ValueError("Unexpectedly short coordinated crack series")

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(self.rows[0]))
        writer.writeheader()
        writer.writerows(self.rows)
        saved = self.object_store.save(self.object_store_key, output.getvalue())
        if not saved:
            raise ValueError("Object Store export failed")

        self.log(
            "RESEARCH EXPORT | rows={} | first={} | last={} | key={}".format(
                len(self.rows),
                self.rows[0]["date"],
                self.rows[-1]["date"],
                self.object_store_key,
            )
        )
