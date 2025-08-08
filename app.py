import streamlit as st
import pandas as pd
import copy
import numpy as np

# --- Page Config ---
st.set_page_config(
    page_title="Canadian Retirement Strategy Simulator",
    page_icon="🧠",
    layout="wide"
)

# --- Tax Information (Simplified for 2024) ---
TAX_BRACKETS = {
    'ON': {
        'federal': [{'rate': 0.15, 'limit': 55867}, {'rate': 0.205, 'limit': 111733}, {'rate': 0.26, 'limit': 173205}, {'rate': 0.29, 'limit': 246752}, {'rate': 0.33, 'limit': float('inf')}],
        'provincial': [{'rate': 0.0505, 'limit': 51446}, {'rate': 0.0915, 'limit': 102894}, {'rate': 0.1116, 'limit': 150000}, {'rate': 0.1216, 'limit': 220000}, {'rate': 0.1316, 'limit': float('inf')}],
        'basic_personal_amount': {'federal': 15705, 'provincial': 12399}
    },
    'BC': {
        'federal': [{'rate': 0.15, 'limit': 55867}, {'rate': 0.205, 'limit': 111733}, {'rate': 0.26, 'limit': 173205}, {'rate': 0.29, 'limit': 246752}, {'rate': 0.33, 'limit': float('inf')}],
        'provincial': [{'rate': 0.0506, 'limit': 47937}, {'rate': 0.077, 'limit': 95875}, {'rate': 0.105, 'limit': 110070}, {'rate': 0.1229, 'limit': 133664}, {'rate': 0.147, 'limit': 181232}, {'rate': 0.168, 'limit': 252752}, {'rate': 0.205, 'limit': float('inf')}],
        'basic_personal_amount': {'federal': 15705, 'provincial': 12580}
    },
    'AB': {
        'federal': [{'rate': 0.15, 'limit': 55867}, {'rate': 0.205, 'limit': 111733}, {'rate': 0.26, 'limit': 173205}, {'rate': 0.29, 'limit': 246752}, {'rate': 0.33, 'limit': float('inf')}],
        'provincial': [{'rate': 0.10, 'limit': 148269}, {'rate': 0.12, 'limit': 177922}, {'rate': 0.13, 'limit': 237230}, {'rate': 0.14, 'limit': 355845}, {'rate': 0.15, 'limit': float('inf')}],
        'basic_personal_amount': {'federal': 15705, 'provincial': 21885}
    }
}
OAS_CLAWBACK_THRESHOLD = 90997

# --- Calculation Functions ---
def calculate_tax(income, province):
    brackets = TAX_BRACKETS.get(province)
    if not brackets: return 0
    tax = 0
    # Federal Tax
    fed_taxable_income = max(0, income - brackets['basic_personal_amount']['federal'])
    last_limit = 0
    for bracket in brackets['federal']:
        if fed_taxable_income <= 0: break
        taxable_in_bracket = min(fed_taxable_income, bracket['limit'] - last_limit)
        tax += taxable_in_bracket * bracket['rate']
        fed_taxable_income -= taxable_in_bracket
        last_limit = bracket['limit']
    # Provincial Tax
    prov_taxable_income = max(0, income - brackets['basic_personal_amount']['provincial'])
    last_limit = 0
    for bracket in brackets['provincial']:
        if prov_taxable_income <= 0: break
        taxable_in_bracket = min(prov_taxable_income, bracket['limit'] - last_limit)
        tax += taxable_in_bracket * bracket['rate']
        prov_taxable_income -= taxable_in_bracket
        last_limit = bracket['limit']
    return tax

def calculate_oas_clawback(income):
    if income <= OAS_CLAWBACK_THRESHOLD: return 0
    return (income - OAS_CLAWBACK_THRESHOLD) * 0.15

def get_tax_for_withdrawals(withdrawals, assets, province, apply_pension_splitting):
    incomes = {'user1': 0, 'user2': 0}
    for user in ['user1', 'user2']:
        w_non_reg = min(withdrawals[user]['non_reg'], assets[user]['non_reg'])
        if w_non_reg > 0:
            cost_base_total = assets[user]['non_reg']
            cost_ratio = assets[user]['non_reg_cost'] / cost_base_total if cost_base_total > 0 else 0
            capital_gain = w_non_reg * (1 - cost_ratio)
            incomes[user] += capital_gain * 0.5
        
        w_rrsp = min(withdrawals[user]['rrsp'], assets[user]['rrsp'])
        incomes[user] += w_rrsp

    final_incomes = incomes.copy()
    if apply_pension_splitting:
        rrif_income1 = min(withdrawals['user1']['rrsp'], assets['user1']['rrsp'])
        rrif_income2 = min(withdrawals['user2']['rrsp'], assets['user2']['rrsp'])
        
        if (final_incomes['user1']) > (final_incomes['user2']):
            potential_split = (final_incomes['user1'] - final_incomes['user2']) / 2
            pension_split_amount = min(rrif_income1 * 0.5, potential_split)
            final_incomes['user1'] -= pension_split_amount
            final_incomes['user2'] += pension_split_amount
        else:
            potential_split = (final_incomes['user2'] - final_incomes['user1']) / 2
            pension_split_amount = min(rrif_income2 * 0.5, potential_split)
            final_incomes['user2'] -= pension_split_amount
            final_incomes['user1'] += pension_split_amount
        
    tax1 = calculate_tax(final_incomes['user1'], province) + calculate_oas_clawback(final_incomes['user1'])
    tax2 = calculate_tax(final_incomes['user2'], province) + calculate_oas_clawback(final_incomes['user2'])
    
    return tax1 + tax2

def run_simulation(inputs, mode, strategies):
    assets = copy.deepcopy(inputs['assets'])
    common = inputs['common']
    
    years_to_retirement = common['retirement_age'] - assets['user1']['current_age']
    for _ in range(years_to_retirement):
        for user in ['user1', 'user2']:
            for acc_type in ['rrsp', 'tfsa', 'non_reg']:
                assets[user][acc_type] *= (1 + common['investment_return'])

    results = []
    annual_withdrawal_base = common.get('annual_withdrawal', 0)

    df_columns = ['Age', 'Start of Year Assets', 'Net Income (After-Tax)', 'Total Tax', 'RRSP %', 'Non-Reg %', 'TFSA %', 'End of Year Assets', 'Notes']

    for i in range(common['end_age'] - common['retirement_age'] + 1):
        current_age = common['retirement_age'] + i
        total_assets_start = sum(assets[u][acc] for u in ['user1', 'user2'] for acc in ['rrsp', 'tfsa', 'non_reg'])
        
        current_withdrawal_target = annual_withdrawal_base * ((1 + common['inflation_rate']) ** i)

        if total_assets_start <= 0:
            results.append({col: 0 for col in df_columns})
            results[-1]['Age'] = current_age
            results[-1]['Notes'] = 'Assets Depleted'
            break

        withdrawals = {'user1': {'rrsp': 0, 'tfsa': 0, 'non_reg': 0}, 'user2': {'rrsp': 0, 'tfsa': 0, 'non_reg': 0}}
        
        if mode == 'Automatic Optimization (Recommended)':
            best_mix = {'total_tax': float('inf'), 'rrsp_ratio': 0}
            
            for rrsp_ratio in np.arange(0, 1.01, 0.05):
                temp_withdrawals = {
                    'user1': {'rrsp': current_withdrawal_target * rrsp_ratio / 2, 'non_reg': current_withdrawal_target * (1-rrsp_ratio) / 2},
                    'user2': {'rrsp': current_withdrawal_target * rrsp_ratio / 2, 'non_reg': current_withdrawal_target * (1-rrsp_ratio) / 2}
                }
                current_tax = get_tax_for_withdrawals(temp_withdrawals, assets, common['province'], strategies.get('apply_pension_splitting', False))

                if current_tax < best_mix['total_tax']:
                    best_mix['total_tax'] = current_tax
                    best_mix['rrsp_ratio'] = rrsp_ratio

            rrsp_pct = best_mix['rrsp_ratio']
            non_reg_pct = 1 - rrsp_pct
            tfsa_pct = 0
        else: # Manual Withdrawal Plan
            rrsp_pct = strategies['manual_mix']['rrsp'] / 100
            non_reg_pct = strategies['manual_mix']['non_reg'] / 100
            tfsa_pct = strategies['manual_mix']['tfsa'] / 100
        
        total_gross_w = current_withdrawal_target
        total_rrsp_w = min(total_gross_w * rrsp_pct, assets['user1']['rrsp'] + assets['user2']['rrsp'])
        total_non_reg_w = min(total_gross_w * non_reg_pct, assets['user1']['non_reg'] + assets['user2']['non_reg'])
        total_tfsa_w = min(total_gross_w * tfsa_pct, assets['user1']['tfsa'] + assets['user2']['tfsa'])

        user_order = sorted(['user1', 'user2'], key=lambda u: assets[u]['rrsp'], reverse=True)
        temp_rrsp = total_rrsp_w
        for user in user_order:
            w = min(temp_rrsp, assets[user]['rrsp'])
            withdrawals[user]['rrsp'] = w
            temp_rrsp -= w
        
        temp_non_reg = total_non_reg_w
        for user in user_order:
            w = min(temp_non_reg/2, assets[user]['non_reg'])
            withdrawals[user]['non_reg'] = w
            temp_non_reg -= w
            
        temp_tfsa = total_tfsa_w
        for user in user_order:
            w = min(temp_tfsa/2, assets[user]['tfsa'])
            withdrawals[user]['tfsa'] = w
            temp_tfsa -= w
        
        final_tax = get_tax_for_withdrawals(withdrawals, assets, common['province'], strategies.get('apply_pension_splitting', False))
        
        for user in ['user1', 'user2']:
            for acc_type in ['rrsp', 'tfsa', 'non_reg']:
                w_amount = withdrawals[user][acc_type]
                assets[user][acc_type] -= w_amount
                if acc_type == 'non_reg' and w_amount > 0:
                    cost_base_total = assets[user]['non_reg'] + w_amount
                    assets[user]['non_reg_cost'] *= (1 - w_amount / cost_base_total) if cost_base_total > 0 else 1

        for user in ['user1', 'user2']:
            for acc_type in ['rrsp', 'tfsa', 'non_reg']:
                assets[user][acc_type] *= (1 + common['investment_return'])
            if assets[user]['non_reg'] > 0:
                growth = assets[user]['non_reg'] * common['investment_return'] / (1 + common['investment_return'])
                assets[user]['non_reg_cost'] += growth

        total_assets_end = sum(assets[u][acc] for u in ['user1', 'user2'] for acc in ['rrsp', 'tfsa', 'non_reg'])
        total_withdrawal_final = sum(v for w in withdrawals.values() for v in w.values())
        net_income = total_withdrawal_final - final_tax

        results.append({
            'Age': current_age, 'Start of Year Assets': total_assets_start, 'Net Income (After-Tax)': net_income,
            'Total Tax': final_tax, 
            'RRSP %': (sum(withdrawals[u]['rrsp'] for u in ['user1', 'user2']) / total_withdrawal_final * 100) if total_withdrawal_final > 0 else 0,
            'Non-Reg %': (sum(withdrawals[u]['non_reg'] for u in ['user1', 'user2']) / total_withdrawal_final * 100) if total_withdrawal_final > 0 else 0,
            'TFSA %': (sum(withdrawals[u]['tfsa'] for u in ['user1', 'user2']) / total_withdrawal_final * 100) if total_withdrawal_final > 0 else 0,
            'End of Year Assets': total_assets_end, 'Notes': ''
        })
        
    return pd.DataFrame(results, columns=df_columns)

# --- Streamlit UI ---
st.title("🧠 Canadian Retirement Strategy Simulator")
st.markdown("Compare and analyze your retirement plan by applying various **withdrawal strategies** and **tax optimization** options.")

with st.sidebar:
    st.header("1. Basic Information")
    tab1, tab2 = st.tabs(["User 1 (You)", "User 2 (Spouse)"])
    with tab1:
        user1_current_age = st.number_input("Current Age (User 1)", 20, 100, 40)
        user1_rrsp = st.number_input("RRSP/RRIF ($) (User 1)", 0, None, 300000, 10000)
        user1_tfsa = st.number_input("TFSA ($) (User 1)", 0, None, 80000, 10000)
        user1_non_reg = st.number_input("Non-Registered ($) (User 1)", 0, None, 50000, 10000)
        user1_non_reg_cost = st.number_input("Non-Reg Cost Basis ($) (User 1)", 0, None, 40000, 10000)
    with tab2:
        user2_current_age = st.number_input("Current Age (User 2)", 20, 100, 40)
        user2_rrsp = st.number_input("RRSP/RRIF ($) (User 2)", 0, None, 200000, 10000)
        user2_tfsa = st.number_input("TFSA ($) (User 2)", 0, None, 60000, 10000)
        user2_non_reg = st.number_input("Non-Registered ($) (User 2)", 0, None, 20000, 10000)
        user2_non_reg_cost = st.number_input("Non-Reg Cost Basis ($) (User 2)", 0, None, 15000, 10000)

    st.divider()
    st.header("2. Common Settings")
    retirement_age = st.number_input("Retirement Age", 40, 80, 65)
    end_age = st.number_input("End of Simulation Age", 70, 120, 95)
    annual_withdrawal = st.number_input("Target Annual Withdrawal (pre-tax, $)", 0, None, 80000, 5000, help="The total amount you plan to withdraw each year before taxes. This amount will be adjusted for inflation annually.")
    investment_return = st.slider("Annual Investment Return (%)", 0.0, 15.0, 5.0, 0.5) / 100
    inflation_rate = st.slider("Annual Inflation Rate (%)", 0.0, 10.0, 2.0, 0.1) / 100
    province = st.selectbox("Province of Residence", ['ON', 'BC', 'AB'])
    
    st.divider()
    st.header("3. Withdrawal Strategy")
    mode = st.radio("Simulation Mode", ['Automatic Optimization (Recommended)', 'Manual Withdrawal Plan'], horizontal=True)
    
    strategies = {}
    if mode == 'Automatic Optimization (Recommended)':
        strategies['apply_pension_splitting'] = st.checkbox('Apply Pension Income Splitting', value=True)
    else:
        st.subheader("**Manual Withdrawal Plan**")
        strategies['apply_pension_splitting'] = st.checkbox('Apply Pension Income Splitting', value=True)
        
        st.markdown("**Withdrawal Mix (%)**")
        
        col1, col2 = st.columns(2)
        with col1:
            manual_rrsp_pct = st.number_input("RRSP", min_value=0, max_value=100, value=50, step=1, key='rrsp_pct_input')
        with col2:
            max_non_reg = 100 - manual_rrsp_pct
            manual_nonreg_pct = st.number_input("Non-Reg", min_value=0, max_value=max_non_reg, value=min(50, max_non_reg), step=1, key='nonreg_pct_input')

        manual_tfsa_pct = 100 - manual_rrsp_pct - manual_nonreg_pct
        
        st.info(f"TFSA: **{manual_tfsa_pct}%** (auto-calculated)")

        strategies['manual_mix'] = {'rrsp': manual_rrsp_pct, 'non_reg': manual_nonreg_pct, 'tfsa': manual_tfsa_pct}
        
        rrsp_draw = annual_withdrawal * (manual_rrsp_pct / 100)
        nonreg_draw = annual_withdrawal * (manual_nonreg_pct / 100)
        tfsa_draw = annual_withdrawal * (manual_tfsa_pct / 100)

        st.markdown(f"""
        <div style="font-size: 1rem; color: #FFFFFF; background-color: #4A5568; padding: 10px; border-radius: 5px;">
        <strong>Approx. first-year withdrawals:</strong>
        <ul style="margin-top: 5px; list-style-position: inside;">
            <li>RRSP: ${rrsp_draw:,.0f}</li>
            <li>Non-Reg: ${nonreg_draw:,.0f}</li>
            <li>TFSA: ${tfsa_draw:,.0f}</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)

    calculate_btn = st.button("🚀 Start Simulation", use_container_width=True, type="primary")

# --- Main Screen ---
if calculate_btn:
    inputs = {
        'assets': {
            'user1': {'current_age': user1_current_age, 'rrsp': user1_rrsp, 'tfsa': user1_tfsa, 'non_reg': user1_non_reg, 'non_reg_cost': user1_non_reg_cost},
            'user2': {'current_age': user2_current_age, 'rrsp': user2_rrsp, 'tfsa': user2_tfsa, 'non_reg': user2_non_reg, 'non_reg_cost': user2_non_reg_cost}
        },
        'common': {'retirement_age': retirement_age, 'end_age': end_age, 'annual_withdrawal': annual_withdrawal, 'investment_return': investment_return, 'inflation_rate': inflation_rate, 'province': province}
    }

    with st.spinner('Running advanced simulations... 🧠'):
        if mode == 'Manual Withdrawal Plan':
            st.header("📈 My Plan vs. Automatic Optimization")
            
            manual_results_df = run_simulation(inputs, 'Manual Withdrawal Plan', strategies)
            
            # FIX: Create a clean, independent strategy dictionary for the benchmark auto-plan
            auto_strategies = {'apply_pension_splitting': True}
            auto_results_df = run_simulation(inputs, 'Automatic Optimization (Recommended)', auto_strategies)

            st.subheader("Asset Growth Comparison: My Plan vs. Optimized")
            comparison_df = pd.DataFrame({
                'Age': manual_results_df['Age'],
                'My Plan': manual_results_df['End of Year Assets'],
                'Optimized Plan': auto_results_df['End of Year Assets']
            }).set_index('Age')
            st.line_chart(comparison_df)
            
            manual_last_year = manual_results_df.iloc[-1]
            auto_last_year = auto_results_df.iloc[-1]
            manual_total_tax = manual_results_df['Total Tax'].sum()
            auto_total_tax = auto_results_df['Total Tax'].sum()

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("My Plan Results")
                if manual_last_year['Notes'] == 'Assets Depleted': st.error(f"**Assets depleted at age {int(manual_last_year['Age'])}**")
                else: st.success(f"**${manual_last_year['End of Year Assets']:,.0f}** remaining at age {end_age}")
                st.metric(label="Total Taxes Paid", value=f"${manual_total_tax:,.0f}", delta=f"${manual_total_tax - auto_total_tax:,.0f} (vs. Optimized)")
            
            with col2:
                st.subheader("Automatic Optimization Results")
                if auto_last_year['Notes'] == 'Assets Depleted': st.error(f"**Assets depleted at age {int(auto_last_year['Age'])}**")
                else: st.success(f"**${auto_last_year['End of Year Assets']:,.0f}** remaining at age {end_age}")
                st.metric(label="Total Taxes Paid", value=f"${auto_total_tax:,.0f}")
            
            tax_savings = manual_total_tax - auto_total_tax
            asset_difference = auto_last_year['End of Year Assets'] - manual_last_year['End of Year Assets']
            st.info(f"**Analysis:** The automatic optimization strategy could save you **${tax_savings:,.0f}** in taxes, leaving you with **${asset_difference:,.0f}** more in assets.")
            
            st.subheader("Detailed Annual Flow (My Plan)")
            st.dataframe(manual_results_df.style.format('${:,.0f}', subset=['Start of Year Assets', 'Net Income (After-Tax)', 'Total Tax', 'End of Year Assets']).format('{:.1f}%', subset=['RRSP %', 'Non-Reg %', 'TFSA %']), use_container_width=True)

        else: # Automatic Optimization Mode
            st.header("📊 Automatic Optimization Simulation Results")
            results_df = run_simulation(inputs, 'Automatic Optimization (Recommended)', strategies)
            last_year = results_df.iloc[-1]
            if last_year['Notes'] == 'Assets Depleted':
                st.error(f"**Assets Depleted:** Based on the simulation, your assets are projected to run out at age **{int(last_year['Age'])}**.")
            else:
                st.success(f"**Plan Successful!** Your assets are projected to last until age **{end_age}**, with an estimated **${last_year['End of Year Assets']:,.0f}** remaining.")
            
            st.line_chart(results_df, x='Age', y='End of Year Assets')
            st.dataframe(results_df.style.format('${:,.0f}', subset=['Start of Year Assets', 'Net Income (After-Tax)', 'Total Tax', 'End of Year Assets']).format('{:.1f}%', subset=['RRSP %', 'Non-Reg %', 'TFSA %']), use_container_width=True)
else:
    st.info("👈 Enter your information in the sidebar and click 'Start Simulation' to begin.")
