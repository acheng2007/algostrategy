# Data rights and publication scope

Reviewed September 4, 2026.
The repository is intended to remain private for now.
Private hosting does not establish redistribution permission.

[QuantConnect licensing documentation](https://www.quantconnect.com/docs/v2/cloud-platform/datasets/licensing) distinguishes cloud access from download access and restricts redistribution of downloaded datasets.
It permits sharing chart images when the original data cannot be reconstructed from them.
No applicable permission to redistribute HO/CL histories was established.
Therefore all source prices, contract-day exports, merged panels, and daily P&L histories are excluded, even when transformed to CSV.
The included numerical tables are aggregate research outcomes rather than market-price observations, and the exhibit does not expose reconstructable individual-contract histories.
No claim is made that this review grants a general data license.
Recheck the applicable provider and exchange agreement before wider distribution or adding any new outputs.

EIA inputs are available from the official sources linked in the acquisition guide and are omitted for a consistent source-free repository.
Yahoo and Barchart histories, CME samples, and the third-party application guide and example are also omitted.
No API keys, credentials, account identifiers, environment folders, temporary files, or unrelated research are part of the intended upload.

No open-source license is granted by this repository at this stage.
Third-party packages retain their own licenses; a Python dependency license does not license vendor market data.
