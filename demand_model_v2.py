"""
demand_model_v2.py

Replaces hand-estimated growth rates with Synapse Energy Economics
load forecast components from:
"A Snapshot of the Energy Landscape in Illinois" (April 2025)

Three scenarios — low, medium, high — matching Synapse's definitions.
Components:
  1. Conventional load   : flat ~140 TWh (PJM/MISO forecast)
  2. Data center load    : low=20 TWh by 2050, med=103, high=322
  3. EV load             : low=10 TWh by 2050, med=35,  high=43
  4. Building electrif.  : low=0,              med=15,  high=20
  5. Industrial electrif.: low=0,              med=45,  high=70
  6. Energy efficiency   : low=0 savings,      med=-13, high=-29 (offsets)

Peak demand derived from TWh using a load factor.
Data centers add flat baseload (high utilization ~86%).
EVs add overnight peak.
Building electrif. shifts winter morning peak.
"""

from storage_model import load_inputs

# Synapse forecast endpoint values at 2050 (TWh)
# Interpolated linearly between 2024 baseline and 2050 endpoint
# except data centers which follow an S-curve per Synapse Figure 15

SYNAPSE = {
    'conventional': {
        'low':    140, 'medium': 140, 'high':   140   # flat per Synapse Fig 14
    },
    'data_center_2030': {
        'low':    10,  'medium':  18, 'high':    20   # TWh by 2030
    },
    'data_center_2050': {
        'low':    20,  'medium': 103, 'high':   322   # TWh by 2050
    },
    'ev_2050': {
        'low':    10,  'medium':  35, 'high':    43
    },
    'ev_start_year': 2025,   # EVs already beginning to ramp
    'building_2050': {
        'low':     0,  'medium':  15, 'high':    20
    },
    'building_start': 2027,  # heat pump adoption ramps mid-period
    'industrial_2050': {
        'low':     0,  'medium':  45, 'high':    70
    },
    'industrial_start': 2031,  # Synapse: trajectories begin 2031
    'efficiency_2050': {       # negative = savings (offsets demand)
        'low':     0,  'medium': -13, 'high':   -29
    },
    'efficiency_start': 2025,
}


def interpolate(start_yr, end_yr, start_val, end_val, year):
    """Linear interpolation between two endpoints."""
    if year <= start_yr:
        return start_val
    if year >= end_yr:
        return end_val
    frac = (year - start_yr) / (end_yr - start_yr)
    return start_val + frac * (end_val - start_val)


def data_center_TWh(year, scenario):
    """
    Data center load follows an S-curve.
    Grows rapidly 2025-2035, slows after per Synapse medium scenario.
    Uses 2030 and 2050 anchors from Synapse.
    """
    baseline_2023 = 7  # TWh, Synapse confirmed
    target_2030   = SYNAPSE['data_center_2030'][scenario]
    target_2050   = SYNAPSE['data_center_2050'][scenario]

    if year <= 2023:
        return baseline_2023
    elif year <= 2030:
        return interpolate(2023, 2030, baseline_2023, target_2030, year)
    elif year <= 2050:
        return interpolate(2030, 2050, target_2030, target_2050, year)
    return target_2050


def get_demand_trajectory_v2(policy, scenario='medium',
                              start_year=2025, end_year=2045):
    """
    Returns year-by-year demand trajectory using Synapse forecast components.

    scenario: 'low', 'medium', or 'high'
    """
    trajectory = []

    for year in range(start_year, end_year + 1):

        # 1. Conventional load — flat per Synapse
        conv_TWh = SYNAPSE['conventional'][scenario]

        # 2. Data centers — S-curve anchored to Synapse
        dc_TWh = data_center_TWh(year, scenario)
        # Subtract 2024 baseline (already in conventional)
        dc_incremental = max(dc_TWh - 7, 0)

        # 3. EVs — linear ramp from EV start year to 2050
        ev_TWh = interpolate(
            SYNAPSE['ev_start_year'], 2050,
            0, SYNAPSE['ev_2050'][scenario], year
        )

        # 4. Building electrification — linear from start to 2050
        bldg_TWh = interpolate(
            SYNAPSE['building_start'], 2050,
            0, SYNAPSE['building_2050'][scenario], year
        )

        # 5. Industrial electrification — linear from 2031 to 2050
        ind_TWh = interpolate(
            SYNAPSE['industrial_start'], 2050,
            0, SYNAPSE['industrial_2050'][scenario], year
        )

        # 6. Energy efficiency — negative (savings offset demand)
        eff_TWh = interpolate(
            SYNAPSE['efficiency_start'], 2050,
            0, SYNAPSE['efficiency_2050'][scenario], year
        )

        total_TWh = conv_TWh + dc_incremental + ev_TWh + bldg_TWh + ind_TWh + eff_TWh

        # Peak demand derivation:
        # Base peak uses a load factor of ~18% of annual TWh
        # (23.4 GW peak / 139 TWh baseline = 0.168)
        base_load_factor = 23.4 / 139

        # Data centers run ~86% utilization — mostly flat load, low peak contribution
        dc_peak = dc_incremental * 1000 / 8760 * (1 / 0.86) * 1.05  # GW

        # EVs add overnight peak — worst case winter morning
        ev_peak = ev_TWh * 1000 / 8760 * (1 / 0.15) * 0.20  # GW
        # (15% avg CF for EVs charging, 20% contribution to winter peak)

        # Building electrification adds winter morning peak (heat pumps)
        bldg_peak = bldg_TWh * 1000 / 8760 * (1 / 0.25) * 0.30  # GW

        # Industrial electrification: mostly flat process heat
        ind_peak = ind_TWh * 1000 / 8760 * (1 / 0.70) * 0.15  # GW

        base_peak = conv_TWh * base_load_factor
        total_peak_GW = base_peak + dc_peak + ev_peak + bldg_peak + ind_peak

        trajectory.append({
            'year':          year,
            'scenario':      scenario,
            'conv_TWh':      round(conv_TWh, 1),
            'dc_TWh':        round(dc_incremental, 1),
            'ev_TWh':        round(ev_TWh, 1),
            'bldg_TWh':      round(bldg_TWh, 1),
            'ind_TWh':       round(ind_TWh, 1),
            'eff_TWh':       round(eff_TWh, 1),
            'total_TWh':     round(total_TWh, 1),
            'peak_GW':       round(total_peak_GW, 1),
        })

    return trajectory


def print_trajectory_v2(trajectory):
    scen = trajectory[0]['scenario'].upper()
    print(f"\nSYNAPSE-BASED DEMAND TRAJECTORY — {scen} SCENARIO")
    print(f"{'Year':<6} {'Conv':<8} {'DC':<8} {'EV':<8} "
          f"{'Bldg':<8} {'Ind':<8} {'Eff':<8} {'Total TWh':<12} {'Peak GW':<10} {'vs 2024'}")
    print("-"*88)

    key_years = [2025, 2027, 2029, 2030, 2032, 2035, 2037, 2040, 2042, 2045]
    for t in trajectory:
        if t['year'] in key_years:
            pct = (t['total_TWh'] - 139) / 139 * 100
            sign = "+" if pct >= 0 else ""
            print(f"{t['year']:<6} {t['conv_TWh']:<8} {t['dc_TWh']:<8} "
                  f"{t['ev_TWh']:<8} {t['bldg_TWh']:<8} {t['ind_TWh']:<8} "
                  f"{t['eff_TWh']:<8} {t['total_TWh']:<12} {t['peak_GW']:<10} "
                  f"{sign}{pct:.1f}%")

    final = trajectory[-1]
    print(f"\nKEY FINDINGS ({scen} scenario, 2045):")
    print(f"  Total demand:          {final['total_TWh']} TWh"
          f"  (+{(final['total_TWh']-139)/139*100:.1f}% vs 2024)")
    print(f"  Peak demand:           {final['peak_GW']} GW")
    print(f"  Data center load:      {final['dc_TWh']} TWh  (Synapse medium = ~75 TWh by 2045)")
    print(f"  EV load:               {final['ev_TWh']} TWh")
    print(f"  Building electrif.:    {final['bldg_TWh']} TWh")
    print(f"  Industrial electrif.:  {final['ind_TWh']} TWh")
    print(f"  Efficiency savings:    {final['eff_TWh']} TWh")


def compare_scenarios(policy):
    """Print all three scenarios side by side at key years."""
    print(f"\n{'='*70}")
    print(f"THREE-SCENARIO COMPARISON (Synapse low / medium / high)")
    print(f"{'='*70}")
    print(f"{'Year':<8} {'Low TWh':<12} {'Med TWh':<12} {'High TWh':<12} "
          f"{'Low Peak':<10} {'Med Peak':<10} {'High Peak'}")
    print("-"*70)

    trajs = {s: get_demand_trajectory_v2(policy, scenario=s)
             for s in ['low', 'medium', 'high']}
    traj_by_year = {}
    for s, traj in trajs.items():
        for t in traj:
            yr = t['year']
            if yr not in traj_by_year:
                traj_by_year[yr] = {}
            traj_by_year[yr][s] = t

    key_years = [2025, 2028, 2030, 2033, 2035, 2037, 2040, 2042, 2045]
    for yr in key_years:
        if yr in traj_by_year:
            d = traj_by_year[yr]
            print(f"{yr:<8} "
                  f"{d['low']['total_TWh']:<12} "
                  f"{d['medium']['total_TWh']:<12} "
                  f"{d['high']['total_TWh']:<12} "
                  f"{d['low']['peak_GW']:<10} "
                  f"{d['medium']['peak_GW']:<10} "
                  f"{d['high']['peak_GW']}")

    # Funding gap check at 2045
    print(f"\nFUNDING ADEQUACY CHECK — moderate externality fund = $7.53B")
    print(f"(Each GW of wind costs $1.45B; each TWh gap needs ~0.30 GW of wind)")
    for s in ['low', 'medium', 'high']:
        traj = trajs[s]
        final = traj[-1]
        # Gap vs current clean fleet (125.6 TWh) at 100% target
        gap = max(final['total_TWh'] - 125.6, 0)
        wind_needed = gap / (0.38 * 8760 / 1000)
        capex = wind_needed * 1.45
        coverage = min(7.53 / capex * 100, 100) if capex > 0 else 100
        print(f"  {s.upper():<8} 2045 demand: {final['total_TWh']} TWh  "
              f"Gap: {gap:.1f} TWh  "
              f"Wind needed: {wind_needed:.1f} GW  "
              f"Capex: ${capex:.2f}B  "
              f"Fund covers: {coverage:.0f}%")


if __name__ == '__main__':
    gen_data, policy, demand_df = load_inputs()

    # Print medium scenario in detail
    traj_med = get_demand_trajectory_v2(policy, scenario='medium')
    print_trajectory_v2(traj_med)

    # Compare all three
    compare_scenarios(policy)
