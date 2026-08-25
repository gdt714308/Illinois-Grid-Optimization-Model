# Illinois Clean Energy Grid Optimization Model

A techno-economic optimization model for Illinois' transition to a 100% renewable, affordable, and equitable electrical grid by 2045. Built for the **2026 Climate Case Competition**, where it took first place.

The model pairs a linear-programming grid buildout optimizer with a three-pillar financing framework designed to hit CEJA-aligned clean energy targets while minimizing the burden on state finances and household electricity bills.

---

## The Challenge

Posed by the World Resources Institute: *How does Illinois achieve a 100% renewable, affordable, and equitable electrical grid by 2045?*

The answer this model develops rests on three findings:

- A "bring your own renewables" policy tied to new data center development is a necessary financing lever.
- Prioritizing wind buildout in northern Illinois optimizes grid efficiency at scale.
- Transitioning retiring fossil fuel plants to battery storage and renewable production preserves both workforces and existing infrastructure value.

---

## Results

Against E3-moderated demand of 247.5 TWh (2045 base case), the optimized transition delivers:

| Metric | Value |
| Clean electricity share by 2045 | 95.1% |
| Net supply gap after data center self-supply | 0.0 TWh |
| Wind fleet | 32.3 GW (+25.3 GW new) |
| Solar fleet | 11.6 GW (+8.4 GW new) |
| Battery storage | 2,114 GWh |
| State capital expenditure | $40.74B |
| Data center capital expenditure (private) | $16.94B |
| Combined capital expenditure | $57.68B |

---

## Model Architecture

The model is organized into six Python modules:

- **`constants.py`** — Shared parameters, cost assumptions, capacity factors, and policy targets used across the model.
- **`demand_model_v2.py`** — Projects statewide electricity demand across the transition period, including incremental data center load.
- **`storage_model_v2.py`** — Sizes battery storage, applying a wind–solar complementarity discount to avoid over-building.
- **`transition_model.py`** — Handles the fossil fleet retirement schedule and the repurposing of plant sites to storage and renewables.
- **`fiscal_model_v2.py`** — Implements the three-pillar financing framework and computes household bill impacts.
- **`optimizer_v2.py`** — The core `scipy.optimize.linprog` optimizer that selects the least-cost, most-reliable buildout path.

Outputs are written to an Excel workbook (`Results_Final.xlsx`) with a consolidated results dashboard, plus diagram exports of the transition pathway.

---

## Methodology

The optimizer minimizes a **composite objective function** combining:

- **Cost per TWh generated** — the primary least-cost signal.
- **Capacity value credit** — peak accreditation of 35% for wind and 15% for solar, so the optimizer values firm capacity rather than raw energy.
- **Diversification weight** — rewards wind–solar storage complementarity to build a more resilient generation mix.

A **time-value penalty of 3% per period** discourages the optimizer from deferring construction to later periods, front-loading the buildout.

Key modeling decisions:

- **Demand basis:** E3-moderated 247.5 TWh from the official Illinois Resource Adequacy Study, rather than Synapse's higher 277.2 TWh medium scenario.
- **Reliability:** Gas backup remains in the reliability constraint until retirement (simple-cycle 2037, combined-cycle 2045), avoiding an infeasible demand for full peak replacement in a single period.
- **Storage:** A maximum 30% wind–solar complementarity discount on required storage.
- **Build targets:** Period targets are derived analytically from what is physically achievable at a 2.0 GW/year build ceiling, rather than set to aspirational CEJA percentages.

---

## Three-Pillar Financing Framework

The plan closes the funding gap while ring-fencing data center demand as a private financial obligation:

**Pillar 1 — Externality Tax.** A moderate tax ($100/MWh coal, $25/MWh gas) generates $7.53B for a renewable fund, returned as a $128/household/year rebate. Gross price impact: 0.57 cents/kWh.

**Pillar 2 — Data Center Self-Supply.** Conditions Illinois Data Center Investment Program tax exemptions on binding clean PPAs covering 100% of incremental data center load — 45 TWh / 13.5 GW backed by $16.94B in private capital, at zero cost to the state.

**Pillar 3 — Public Financing.** Illinois Green Bonds plus federal grants cover the residual $31.08B gap.

---

## Repository Structure

```
illinois-grid-model/
├── constants.py
├── demand_model_v2.py
├── storage_model_v2.py
├── transition_model.py
├── fiscal_model_v2.py
├── optimizer_v2.py
├── outputs/
│   ├── Results_Final.xlsx
│   ├── transition_pathway.png
│   └── transition_pathway.pdf
├── requirements.txt
└── README.md
```

---

## Running the Model

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python optimizer_v2.py
```

The optimizer solves the buildout path and writes results to `outputs/Results_Final.xlsx`.

Dependencies: `numpy`, `scipy`, `pandas`, `openpyxl`, `matplotlib`.

---

## Data Sources

- **Illinois Resource Adequacy Study** (December 2025) — demand projections and reliability parameters.
- **DOE Illinois Fact Sheet** (December 2024) — existing generation fleet and capacity baseline.

---

## Team

- Gabriel Thomas
- Alethea Oakley
- Nicholas McNamara
- Will Vanman

Organized by the UChicago Institute for Climate and Sustainable Growth and the Phoenix Sustainability Initiative. Judged by the World Resources Institute.
