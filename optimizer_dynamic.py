import numpy as np
from scipy.optimize import linprog
from storage_model import load_inputs
from demand_model import get_demand_trajectory

def run_dynamic_optimizer(gen_data, policy, demand_df, scenario="moderate"):

    trajectory = get_demand_trajectory(policy)

    # Index trajectory by year for easy lookup
    traj = {t['year']: t for t in trajectory}

    nuclear_GW       = gen_data["Nuclear"]["current_GW"]
    nuclear_cf       = gen_data["Nuclear"]["capacity_factor"]
    current_wind_GW  = gen_data["Onshore_Wind"]["current_GW"]
    current_solar_GW = gen_data["Utility_Solar"]["current_GW"]
    wind_cf          = gen_data["Onshore_Wind"]["capacity_factor"]
    solar_cf         = gen_data["Utility_Solar"]["capacity_factor"]
    geo_cf           = gen_data["Geothermal"]["capacity_factor"]
    r                = policy["discount_rate"]
    reserve_margin   = policy["reserve_margin"]
    max_build_GW_yr  = policy["max_annual_build_GW"]
    storage_hours    = policy["storage_min_hours"]
    hours_per_year   = 8760

    def annuity(r, n):
        return r * (1+r)**n / ((1+r)**n - 1)

    # Annualized costs $B/GW or $B/GWh
    wind_ann_B  = gen_data["Onshore_Wind"]["capital_cost"] * 1_000_000 * annuity(r,25) / 1e9
    solar_ann_B = gen_data["Utility_Solar"]["capital_cost"] * 1_000_000 * annuity(r,30) / 1e9
    geo_ann_B   = gen_data["Geothermal"]["capital_cost"]   * 1_000_000 * annuity(r,30) / 1e9
    batt_ann_B  = gen_data["Battery_BESS"]["capital_cost"] / 4 / 1e6 * annuity(r,15)

    # Capital costs $B/GW or $B/GWh for reporting
    wind_cap_B  = gen_data["Onshore_Wind"]["capital_cost"] / 1000
    solar_cap_B = gen_data["Utility_Solar"]["capital_cost"] / 1000
    geo_cap_B   = gen_data["Geothermal"]["capital_cost"]   / 1000
    batt_cap_B  = gen_data["Battery_BESS"]["capital_cost"] / 4 / 1e6

    # Existing clean generation TWh
    nuclear_TWh     = nuclear_GW * nuclear_cf * hours_per_year / 1000
    existing_re_TWh = (current_wind_GW * wind_cf * hours_per_year / 1000 +
                       current_solar_GW * solar_cf * hours_per_year / 1000)
    already_clean   = nuclear_TWh + existing_re_TWh

    wind_TWh_per_GW  = wind_cf  * hours_per_year / 1000
    solar_TWh_per_GW = solar_cf * hours_per_year / 1000
    geo_TWh_per_GW   = geo_cf   * hours_per_year / 1000

    c = np.array([wind_ann_B, solar_ann_B, geo_ann_B, batt_ann_B])

    print(f"\nDYNAMIC GRID OPTIMIZER — scenario: {scenario.upper()}")
    print(f"Using demand trajectory through 2045")
    print("="*65)
    print(f"{'Year':<6} {'Demand TWh':<12} {'Peak GW':<10} {'Gap TWh':<10} "
          f"{'Wind GW':<10} {'Solar GW':<9} {'Batt GWh':<10} {'Capex $B'}")
    print("-"*85)

    all_results = []

    for target_year in [2028, 2030, 2033, 2035, 2037, 2040, 2042, 2045]:
        t           = traj[target_year]
        total_TWh   = t['total_TWh']
        peak_GW     = t['peak_GW']
        years_build = target_year - 2024

        # CEJA target percentage for this year
        if target_year <= 2030:
            target_pct = policy["ceja_target_2030_pct"]      # 0.40
        elif target_year <= 2040:
            target_pct = policy["ceja_target_2040_pct"]      # 0.50
        else:
            target_pct = policy["ceja_target_2045_pct"]      # 1.00

        required_clean_TWh = total_TWh * target_pct
        gap_TWh = max(required_clean_TWh - already_clean, 0)

        # Storage floor scales with peak deficit
        # As peak grows, deficit grows proportionally
        base_deficit_MW   = 4600
        scaled_deficit_MW = base_deficit_MW * (peak_GW / 23.4)
        storage_floor_GWh = scaled_deficit_MW * storage_hours / 1000

        A_ub = []
        b_ub = []

        # 1. Build rate constraint
        A_ub.append([1, 1, 1, 0])
        b_ub.append(max_build_GW_yr * years_build)

        # 2. Peak reliability — scales with actual future peak
        required_cap_GW      = peak_GW * (1 + reserve_margin)
        existing_reliable_GW = (nuclear_GW * nuclear_cf +
                                 current_wind_GW  * 0.35 +
                                 current_solar_GW * 0.15)
        new_reliable_needed  = required_cap_GW - existing_reliable_GW
        A_ub.append([-0.35, -0.15, -1.0, -0.25])
        b_ub.append(-new_reliable_needed)

        # 3. Storage floor — scales with future peak deficit
        A_ub.append([0, 0, 0, -1])
        b_ub.append(-storage_floor_GWh)

        if gap_TWh > 0:
            A_eq = [[wind_TWh_per_GW, solar_TWh_per_GW, geo_TWh_per_GW, 0]]
            b_eq = [gap_TWh]
        else:
            A_eq = [[0, 0, 0, 0]]
            b_eq = [0]

        bounds = [(0, None), (0, None), (0, None), (0, None)]

        result = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                         bounds=bounds, method="highs")

        if result.success:
            wind_new, solar_new, geo_new, batt_new = result.x
            total_capex = (wind_new  * wind_cap_B  +
                           solar_new * solar_cap_B +
                           geo_new   * geo_cap_B   +
                           batt_new  * batt_cap_B)

            total_wind_GW   = current_wind_GW  + wind_new
            total_solar_GW  = current_solar_GW + solar_new
            total_clean_TWh = (total_wind_GW  * wind_cf  * hours_per_year/1000 +
                               total_solar_GW * solar_cf * hours_per_year/1000 +
                               geo_new * geo_cf * hours_per_year/1000 +
                               nuclear_TWh)
            clean_pct = total_clean_TWh / total_TWh * 100

            print(f"{target_year:<6} {total_TWh:<12.1f} {peak_GW:<10.1f} "
                  f"{gap_TWh:<10.1f} {wind_new:<10.1f} {solar_new:<9.1f} "
                  f"{batt_new:<10.0f} ${total_capex:.2f}B")

            all_results.append({
                'year':           target_year,
                'demand_TWh':     total_TWh,
                'peak_GW':        peak_GW,
                'gap_TWh':        gap_TWh,
                'new_wind_GW':    round(wind_new, 1),
                'new_solar_GW':   round(solar_new, 1),
                'new_geo_GW':     round(geo_new, 2),
                'new_batt_GWh':   round(batt_new, 0),
                'total_wind_GW':  round(total_wind_GW, 1),
                'total_solar_GW': round(total_solar_GW, 1),
                'total_clean_TWh':round(total_clean_TWh, 1),
                'clean_pct':      round(clean_pct, 1),
                'total_capex_B':  round(total_capex, 2),
                'storage_GWh':    round(storage_floor_GWh, 0),
            })
        else:
            print(f"{target_year:<6} {total_TWh:<12.1f} {peak_GW:<10.1f} "
                  f"{gap_TWh:<10.1f} {'INFEASIBLE'}")

    # Summary
    print(f"\n{'='*65}")
    print(f"CUMULATIVE BUILD REQUIREMENT BY 2045")
    print(f"{'='*65}")
    if all_results:
        final = all_results[-1]
        static = {'new_wind_GW': 4.0, 'new_batt_GWh': 331, 'total_capex_B': 5.94}

        print(f"  New wind needed:       {final['new_wind_GW']} GW"
              f"  (static model said {static['new_wind_GW']} GW)")
        print(f"  New solar needed:      {final['new_solar_GW']} GW")
        print(f"  New batteries needed:  {final['new_batt_GWh']} GWh"
              f"  (static model said {static['new_batt_GWh']} GWh)")
        print(f"  Total capital:         ${final['total_capex_B']}B"
              f"  (static model said ${static['total_capex_B']}B)")
        print(f"  Total clean output:    {final['total_clean_TWh']} TWh"
              f" ({final['clean_pct']}% of {final['demand_TWh']} TWh demand)")
        print(f"  Moderate fund:         $7.53B available")
        fund_gap = final['total_capex_B'] - 7.53
        if fund_gap > 0:
            print(f"  FUNDING GAP:           ${fund_gap:.2f}B"
                  f" -- fund insufficient at this demand level")
        else:
            print(f"  Fund surplus:          ${abs(fund_gap):.2f}B")
        print(f"\n  KEY IMPLICATION: Demand growth adds"
              f" {final['new_wind_GW'] - static['new_wind_GW']:.1f} GW"
              f" of wind and ${final['total_capex_B'] - static['total_capex_B']:.2f}B"
              f" of capital vs static assumption")

    return all_results


if __name__ == "__main__":
    gen_data, policy, demand_df = load_inputs()
    run_dynamic_optimizer(gen_data, policy, demand_df, scenario="moderate")
