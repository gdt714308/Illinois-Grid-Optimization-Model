
import sys, os
sys.path.insert(0, os.path.expanduser('~/Desktop/illinois_grid_model'))
from constants import *

def run_fiscal_model_v2(state_capex_B, dc_capex_B, storage_GWh,
                         transition_capex_B=1.38, retrain_B=0.133):
    storage_capex_B = storage_GWh * (BATTERY_CAPEX_KW / 4) / 1e6

    coal_by_period = {'2025-2029':23.5,'2030-2045':0.0}
    gas_by_period  = {'2025-2029':22.9,'2030-2036':22.9,'2037-2044':11.5,'2045':0.0}
    def period(y):
        if y<=2029: return '2025-2029'
        if y<=2036: return '2030-2036'
        if y<=2044: return '2037-2044'
        return '2045'

    total_rev=total_reb=total_fund=0
    for year in range(2025,2046):
        p = period(year)
        coal = coal_by_period.get(p,0)
        gas  = gas_by_period.get(p,0)
        rev  = (coal*TAX_COAL_MODERATE + gas*TAX_GAS_MODERATE)/1000
        imp  = rev*PASSTHROUGH_RATE
        reb  = imp*REBATE_FRACTION
        total_rev+=rev; total_reb+=reb; total_fund+=(rev-reb)

    rebate_hh    = total_reb*1e9/HOUSEHOLDS/21
    price_impact = (total_rev*PASSTHROUGH_RATE*1e9/(BASELINE_CONSUMPTION*1e9*21)*100)
    dc_ann       = dc_capex_B * annuity(DISCOUNT_RATE,25)

    total_state_need = state_capex_B + storage_capex_B + transition_capex_B + retrain_B
    p3_gross   = max(total_state_need - total_fund, 0)
    p3_grants  = max(p3_gross - FED_GRANTS_AWARDED, 0)
    bond_cap   = total_fund * 0.5
    p3_bond    = max(p3_grants - bond_cap, 0)

    print(f"\n{'='*65}")
    print(f"THREE-PILLAR FINANCING  2025-2045")
    print(f"{'='*65}")
    print(f"\nPILLAR 1  Moderate Externality Tax")
    print(f"  Total revenue:           ${total_rev:.2f}B")
    print(f"  Consumer rebates:        ${total_reb:.2f}B")
    print(f"  Renewable fund:          ${total_fund:.2f}B")
    print(f"  Avg rebate/HH/yr:        ${rebate_hh:.0f}")
    print(f"  Price impact (gross):    {price_impact:.2f} cents/kWh")
    print(f"\nPILLAR 2  Data Center Clean PPA Mandate")
    print(f"  DC load obligation:      {DC_OBLIGATION_TWH:.0f} TWh = {DC_GW_OBLIGATION:.1f} GW")
    print(f"  Capital cost (to DCs):   ${dc_capex_B:.2f}B")
    print(f"  Annualized 25yr PPA:     ${dc_ann:.3f}B/yr")
    print(f"  State cost:              $0.00B")
    print(f"\nPILLAR 3  Green Bonds + Federal Grants")
    print(f"  Total state need:        ${total_state_need:.2f}B")
    print(f"  Less Pillar 1:          -${total_fund:.2f}B")
    print(f"  Gross P3 need:           ${p3_gross:.2f}B")
    print(f"  Less federal grants:    -${FED_GRANTS_AWARDED:.3f}B")
    print(f"  Less green bonds:       -${bond_cap:.2f}B")
    print(f"  Residual gap:            ${p3_bond:.2f}B")
    status = 'FEASIBLE' if p3_bond<=2 else ('MANAGEABLE' if p3_bond<=5 else 'CHALLENGING')
    print(f"  Status:                  {status}")
    print(f"\n{'='*65}")
    print(f"TOTAL INVESTMENT MOBILIZED")
    print(f"  State (P1+P3):           ${total_state_need:.2f}B")
    print(f"  Data centers (P2):       ${dc_capex_B:.2f}B")
    print(f"  Federal grants:          ${FED_GRANTS_AWARDED:.3f}B")
    print(f"  Private announced:       ${PRIVATE_INVESTMENT_B:.0f}B through 2030")
    print(f"  Total public:            ${total_state_need+dc_capex_B+FED_GRANTS_AWARDED:.2f}B")
    return {'p1_fund':total_fund,'p2_dc':dc_capex_B,'p3_gap':p3_bond,
            'state_need':total_state_need,'rebate_hh':rebate_hh,
            'price_cents':price_impact,'storage_capex':storage_capex_B}

if __name__ == '__main__':
    run_fiscal_model_v2(state_capex_B=16.51, dc_capex_B=12.94,
                        storage_GWh=250.0)
