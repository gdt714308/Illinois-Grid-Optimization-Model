
import numpy as np
from scipy.optimize import linprog
import sys, os
sys.path.insert(0, os.path.expanduser('~/Desktop/illinois_grid_model'))
from constants import *
from storage_model_v2 import load_inputs
from demand_model_v2 import get_demand_trajectory_v2

# Thermal backup schedule: gas retires progressively per CEJA
# Simple-cycle retires 2037, combined-cycle retires 2045
# This is the firm dispatchable backup the grid still has each period
def gas_backup_GW(end_yr):
    if end_yr <= 2036: return GAS_GW           # 9.8 GW full gas fleet
    if end_yr <= 2044: return GAS_GW * 0.55    # simple-cycle retired, ~5.4 GW remains
    return 0.0                                  # all gas retired by 2045

GAS_GW = 9.8  # total current gas fleet

def run_optimizer_v2(gen_data, policy, demand_df, scenario="medium"):
    traj = {t["year"]: t for t in get_demand_trajectory_v2(policy, scenario=scenario)}
    h = HOURS_PER_YEAR
    wind_twh  = WIND_CF  * h / 1000
    solar_twh = SOLAR_CF * h / 1000
    nuclear_twh = NUCLEAR_TWH

    periods = [
        (2025, 2028, "Coal phase-out",             0.63),
        (2029, 2032, "Coal fully retired",          0.71),
        (2033, 2036, "Simple-cycle gas phase-out",  0.80),
        (2037, 2040, "Combined-cycle transition",   0.88),
        (2041, 2045, "Final push 95pct clean",      0.95),
    ]

    cum_wind = cum_solar = cum_batt = total_capex = 0.0
    all_results = []

    print("\n" + "="*115)
    print(f"OPTIMIZER V2  {scenario.upper()}  |  Composite obj: cost/TWh + capacity value + diversification")
    print(f"TV +{TIME_VALUE_STEP*100:.0f}%/period  |  Storage disc up to {WIND_SOLAR_STORAGE_DISCOUNT*100:.0f}%  |"
          f"  Min 1.5GW/yr  |  DC {DC_OBLIGATION_TWH:.0f}TWh Pillar2")
    print(f"Reliability: gas backup included until retirement  |  25% min wind+solar floor each")
    print("="*115)
    print(f"{'Period':<12}{'Demand':>8}{'StateOb':>9}{'Tgt':>6}"
          f"{'Wind':>7}{'Solar':>7}{'Batt':>7}{'Clean':>8}"
          f"{'CapexB':>8}{'TV':>6}{'Disc':>6}{'Rate':>8}{'Sol%':>6}{'GasBk':>7}")
    print("-"*115)

    for idx, (start_yr, end_yr, label, clean_target) in enumerate(periods):
        t_end     = traj[end_yr]
        total_TWh = t_end["total_TWh"]
        peak_GW   = t_end["peak_GW"]
        yrs       = end_yr - start_yr + 1
        state_ob  = total_TWh - DC_OBLIGATION_TWH

        tot_wind  = WIND_GW  + cum_wind
        tot_solar = SOLAR_GW + cum_solar

        already = (nuclear_twh +
                   tot_wind  * wind_twh +
                   tot_solar * solar_twh)
        if idx == 0:
            already += PIPELINE_TWH

        state_gap = max(total_TWh * clean_target - already, 0)

        # Wind-solar complementarity storage discount
        wind_e  = tot_wind  * WIND_CF
        solar_e = tot_solar * SOLAR_CF
        tot_re  = wind_e + solar_e
        if tot_re > 0:
            bal    = 1 - abs(wind_e - solar_e) / tot_re
            comp_d = WIND_SOLAR_STORAGE_DISCOUNT * bal
        else:
            bal = 0; comp_d = 0

        # Storage sizing with complementarity discount
        clean_dispatch_MW = (NUCLEAR_GW * NUCLEAR_CF * 1000 +
                             tot_wind  * 0.35 * 1000 +
                             tot_solar * 0.15 * 1000)
        peak_req_MW = peak_GW * (1 + RESERVE_MARGIN) * 1000
        deficit_MW  = max(peak_req_MW - clean_dispatch_MW, 200)
        raw_batt    = deficit_MW * STORAGE_HOURS / 1000
        need_batt   = raw_batt * (1 - comp_d)
        new_batt    = max(need_batt - cum_batt, 0)

        # Cost trajectory at mid-year
        mid_yr = (start_yr + end_yr) // 2
        w_kw   = capex_in_year(WIND_CAPEX_KW,  WIND_COST_DECLINE_2050, mid_yr)
        s_kw   = capex_in_year(SOLAR_CAPEX_KW, SOLAR_COST_DECLINE_2050, mid_yr)
        w_cap  = w_kw / 1000
        s_cap  = s_kw / 1000
        b_cap  = BATTERY_CAPEX_KW / 4 / 1e6

        tv = 1.0 + idx * TIME_VALUE_STEP

        # Annualized per GW
        w_ann_gw  = w_cap * annuity(DISCOUNT_RATE, 25)
        s_ann_gw  = s_cap * annuity(DISCOUNT_RATE, 30)
        b_ann_gwh = b_cap * annuity(DISCOUNT_RATE, 15)

        # Composite objective: cost/TWh - capacity credit + diversification weight
        w_per_twh = w_ann_gw / wind_twh
        s_per_twh = s_ann_gw / solar_twh
        cap_price = 0.050   # $50/kW-yr capacity price proxy
        w_cap_cr  = 0.35 * cap_price
        s_cap_cr  = 0.15 * cap_price
        batt_ann  = b_cap * annuity(DISCOUNT_RATE, 15)
        div_value = deficit_MW * STORAGE_HOURS / 1000 * batt_ann * WIND_SOLAR_STORAGE_DISCOUNT
        div_per_gw = div_value / max(1.5 * yrs, 1) * 0.5
        if wind_e >= solar_e:
            w_div = +div_per_gw * 0.3; s_div = -div_per_gw
        else:
            w_div = -div_per_gw;       s_div = +div_per_gw * 0.3

        w_obj = (w_per_twh - w_cap_cr + w_div) * tv
        s_obj = (s_per_twh - s_cap_cr + s_div) * tv
        b_obj = b_ann_gwh * tv

        c = np.array([w_obj, s_obj, b_obj])
        A_ub = []; b_ub = []

        # C1: Build rate ceiling 2.0 GW/yr
        A_ub.append([1, 1, 0])
        b_ub.append(MAX_BUILD_GW_YR * yrs)

        # C2: Mandatory minimum 1.5 GW/yr
        A_ub.append([-1, -1, 0])
        b_ub.append(-1.5 * yrs)

        # C3: Peak reliability — CORRECTED
        # Gas backup covers firm dispatchable need until it retires
        # New clean capacity only needs to cover gap above nuclear + gas + existing RE
        gas_bk  = gas_backup_GW(end_yr)
        req_cap = peak_GW * (1 + RESERVE_MARGIN)
        exist_rel = (NUCLEAR_GW * NUCLEAR_CF +
                     tot_wind  * 0.35 +
                     tot_solar * 0.15 +
                     gas_bk)                    # gas covers dispatchable until retired
        new_rel = max(req_cap - exist_rel, 0)
        A_ub.append([-0.35, -0.15, -0.25])
        b_ub.append(-new_rel)

        # C4: Generation gap
        if state_gap > 0:
            A_ub.append([-wind_twh, -solar_twh, 0])
            b_ub.append(-state_gap)

        # C5: Storage floor
        if new_batt > 0:
            A_ub.append([0, 0, -1])
            b_ub.append(-new_batt)

        # C6: Wind minimum 25% of new builds by GW
        A_ub.append([-0.75, 0.25, 0])
        b_ub.append(0)

        # C7: Solar minimum 25% of new builds by GW
        A_ub.append([0.25, -0.75, 0])
        b_ub.append(0)

        A_eq = [[0, 0, 0]]; b_eq = [0]
        bounds = [(0, None), (0, None), (0, None)]

        result = linprog(c, A_ub=A_ub, b_ub=b_ub,
                         A_eq=A_eq, b_eq=b_eq,
                         bounds=bounds, method="highs")

        if result.success:
            w, s, b = result.x
            cum_wind  += w
            cum_solar += s
            cum_batt  += b + new_batt

            tw = WIND_GW  + cum_wind
            ts = SOLAR_GW + cum_solar
            clean_out = nuclear_twh + tw*wind_twh + ts*solar_twh
            ach   = clean_out / total_TWh * 100
            pcap  = w*w_cap + s*s_cap + (b+new_batt)*b_cap
            total_capex += pcap
            rate  = (w + s) / yrs
            sol_p = s/(w+s)*100 if (w+s) > 0 else 0

            print(f"{start_yr}-{end_yr:<5}"
                  f"{total_TWh:>8.1f}{state_ob:>9.1f}"
                  f"{clean_target*100:>5.0f}%"
                  f"{w:>7.1f}{s:>7.1f}{cum_batt:>7.0f}"
                  f"{ach:>7.1f}%"
                  f" {pcap:>7.2f}"
                  f" {tv:>4.2f}x"
                  f" {comp_d*100:>4.0f}%"
                  f" {rate:>5.1f}GW/yr"
                  f" {sol_p:>5.0f}%"
                  f" {gas_bk:>6.1f}GW")

            all_results.append({
                "period": f"{start_yr}-{end_yr}", "label": label,
                "demand_TWh": round(total_TWh,1), "state_ob": round(state_ob,1),
                "target": clean_target, "gas_backup": round(gas_bk,1),
                "new_wind": round(w,1), "new_solar": round(s,1),
                "cum_wind": round(cum_wind,1), "cum_solar": round(cum_solar,1),
                "cum_batt": round(cum_batt,0), "achieved": round(ach,1),
                "capex": round(pcap,2), "cum_capex": round(total_capex,2),
                "rate": round(rate,2), "tv": tv,
                "comp_d": round(comp_d*100,1),
                "w_kw_adj": round(w_kw), "sol_pct": round(sol_p,1),
            })
        else:
            gap_gw  = state_gap / wind_twh if state_gap > 0 else 0
            need_gw = max(gap_gw, 1.5*yrs)
            gas_bk  = gas_backup_GW(end_yr)
            print(f"{start_yr}-{end_yr}  NO SOLUTION  "
                  f"gap {state_gap:.1f}TWh  gas_backup {gas_bk:.1f}GW  "
                  f"need {need_gw:.1f}GW @ {need_gw/yrs:.1f}GW/yr")

    if all_results:
        f    = all_results[-1]
        dc_tot = DC_GW_OBLIGATION * (
            capex_in_year(WIND_CAPEX_KW, WIND_COST_DECLINE_2050, 2035)/1000)
        tw_f = WIND_GW  + f["cum_wind"]
        ts_f = SOLAR_GW + f["cum_solar"]
        avg_disc = sum(r["comp_d"] for r in all_results)/len(all_results)
        avg_sol  = sum(r["sol_pct"] for r in all_results)/len(all_results)

        print("\n" + "="*65)
        print(f"2045 SUMMARY  {scenario.upper()}")
        print(f"  Wind fleet:     {tw_f:.1f} GW  (+{f['cum_wind']:.1f} new)")
        print(f"  Solar fleet:    {ts_f:.1f} GW  (+{f['cum_solar']:.1f} new)")
        print(f"  Batteries:      {f['cum_batt']:.0f} GWh")
        print(f"  Clean output:   {f['achieved']}% of {f['demand_TWh']} TWh")
        print(f"  Gas backup:     retired by 2045")
        print(f"  Avg storage discount (wind-solar): {avg_disc:.1f}%")
        print(f"  Avg solar share of new builds:     {avg_sol:.0f}%")
        print(f"  State capex (P1+P3):   ${f['cum_capex']:.2f}B")
        print(f"  DC capex    (P2):      ${dc_tot:.2f}B")
        print(f"  Combined:              ${f['cum_capex']+dc_tot:.2f}B")
        print("\n  Period-by-period:")
        for r in all_results:
            print(f"    {r['period']}: {r['rate']:.1f}GW/yr  "
                  f"wind ${r['w_kw_adj']:,}/KW  TV {r['tv']:.2f}x  "
                  f"disc {r['comp_d']:.0f}%  sol {r['sol_pct']:.0f}%  "
                  f"gas_bk {r['gas_backup']:.1f}GW")

    return all_results, f["cum_capex"] if all_results else 0, dc_tot

if __name__ == "__main__":
    gen_data, policy, demand_df = load_inputs()
    results, state_c, dc_c = run_optimizer_v2(
        gen_data, policy, demand_df, scenario="medium")
    from fiscal_model_v2 import run_fiscal_model_v2
    storage_gwh = results[-1]["cum_batt"] if results else 300
    run_fiscal_model_v2(state_capex_B=state_c, dc_capex_B=dc_c,
                        storage_GWh=storage_gwh)
