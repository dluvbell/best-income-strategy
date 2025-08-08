import streamlit as st
import pandas as pd
import copy

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

def run_simulation(inputs, mode, strategies):
    assets = copy.deepcopy(inputs['assets'])
    common = inputs['common']
    
    # Pre-retirement asset growth
    years_to_retirement = common['retirement_age'] - assets['user1']['current_age']
    for _ in range(years_to_retirement):
        for user in ['user1', 'user2']:
            for acc_type in ['rrsp', 'tfsa', 'non_reg']:
                assets[user][acc_type] *= (1 + common['investment_return'])

    # Post-retirement simulation
    results = []
    age1 = common['retirement_age']
    spending = common['annual_spending']
    
    df_columns = ['Age', 'Start of Year Assets', 'Annual Spending', 'Pension Split Amount', 'Total Tax', 'End of Year Assets', 'Notes']

    for i in range(common['end_age'] - common['retirement_age'] + 1):
        current_age = age1 + i
        total_assets_start = sum(assets[u][acc] for u in ['user1', 'user2'] for acc in ['rrsp', 'tfsa', 'non_reg'])

        if total_assets_start <= 0:
            results.append({col: 0 for col in df_columns})
            results[-1]['Age'] = current_age
            results[-1]['Notes'] = 'Assets Depleted'
            break

        # --- Withdrawal Logic ---
        withdrawals = {'user1': {'rrsp': 0, 'tfsa': 0, 'non_reg': 0}, 'user2': {'rrsp': 0, 'tfsa': 0, 'non_reg': 0}}
        incomes = {'user1': 0, 'user2': 0}
        
        needed_after_tax = spending
        
        if mode == 'Automatic Optimization (Recommended)':
            estimated_tax_rate = 0.20
            needed_before_tax = needed_after_tax / (1 - estimated_tax_rate)
            
            # Withdrawal Order: 1. Non-Reg -> 2. RRSP -> 3. TFSA
            
            # Non-Reg withdrawal
            total_withdrawn = 0
            for user in ['user1', 'user2']:
                w_amount = min(needed_before_tax / 2, assets[user]['non_reg'])
                withdrawals[user]['non_reg'] = w_amount
                total_withdrawn += w_amount
            
            # RRSP withdrawal
            remaining_needed = needed_before_tax - total_withdrawn
            if remaining_needed > 0:
                user_order = sorted(['user1', 'user2'], key=lambda u: assets[u]['rrsp'], reverse=True)
                for user in user_order:
                    if remaining_needed > 0:
                        w_amount = min(remaining_needed, assets[user]['rrsp'])
                        withdrawals[user]['rrsp'] += w_amount
                        remaining_needed -= w_amount
        else: # Manual Withdrawal Plan
            withdrawals = strategies['manual_withdrawals']

        # Execute withdrawals and calculate income
        for user in ['user1', 'user2']:
            for acc_type in ['rrsp', 'tfsa', 'non_reg']:
                w_amount = min(withdrawals[user][acc_type], assets[user][acc_type])
                withdrawals[user][acc_type] = w_amount
                assets[user][acc_type] -= w_amount
                
                if acc_type == 'rrsp':
                    incomes[user] += w_amount
                elif acc_type == 'non_reg' and w_amount > 0:
                    cost_base_total = assets[user]['non_reg'] + w_amount
                    cost_ratio = assets[user]['non_reg_cost'] / cost_base_total if cost_base_total > 0 else 0
                    capital_gain = w_amount * (1 - cost_ratio)
                    incomes[user] += capital_gain * 0.5
                    assets[user]['non_reg_cost'] *= (1 - w_amount / cost_base_total) if cost_base_total > 0 else 1

        # Apply Pension Income Splitting
        pension_split_amount = 0
        if strategies.get('apply_pension_splitting', False):
            rrif_income1 = withdrawals['user1']['rrsp']
            rrif_income2 = withdrawals['user2']['rrsp']
            
            if (incomes['user1'] - rrif_income1) > (incomes['user2'] - rrif_income2):
                potential_split = (incomes['user1'] - incomes['user2']) / 2
                pension_split_amount = min(rrif_income1 * 0.5, potential_split)
                incomes['user1'] -= pension_split_amount
                incomes['user2'] += pension_split_amount
            else:
                potential_split = (incomes['user2'] - incomes['user1']) / 2
                pension_split_amount = min(rrif_income2 * 0.5, potential_split)
                incomes['user2'] -= pension_split_amount
                incomes['user1'] += pension_split_amount

        # Calculate taxes
        tax1 = calculate_tax(incomes['user1'], common['province']) + calculate_oas_clawback(incomes['user1'])
        tax2 = calculate_tax(incomes['user2'], common['province']) + calculate_oas_clawback(incomes['user2'])
        total_tax = tax1 + tax2
        
        # Cover spending and taxes, withdrawing from TFSA if needed
        net_withdrawal = sum(w for u in ['user1', 'user2'] for w in withdrawals[u].values()) - total_tax
        shortfall = spending - net_withdrawal
        
        if shortfall > 0:
            for user in ['user1', 'user2']:
                if shortfall <= 0: break
                w_amount = min(shortfall, assets[user]['tfsa'])
                withdrawals[user]['tfsa'] += w_amount
                assets[user]['tfsa'] -= w_amount
                shortfall -= w_amount

        # End of year assets with investment growth
        for user in ['user1', 'user2']:
            for acc_type in ['rrsp', 'tfsa', 'non_reg']:
                assets[user][acc_type] *= (1 + common['investment_return'])
            if assets[user]['non_reg'] > 0:
                growth = assets[user]['non_reg'] * common['investment_return'] / (1 + common['investment_return'])
                assets[user]['non_reg_cost'] += growth

        total_assets_end = sum(assets[u][acc] for u in ['user1', 'user2'] for acc in ['rrsp', 'tfsa', 'non_reg'])

        results.append({
            'Age': current_age, 'Start of Year Assets': total_assets_start, 'Annual Spending': spending,
            'Pension Split Amount': pension_split_amount, 'Total Tax': total_tax, 'End of Year Assets': total_assets_end, 'Notes': ''
        })
        spending *= (1 + common['inflation_rate'])
        
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
    annual_spending = st.number_input("Annual Spending (in today's dollars, $)", 0, None, 60000, 5000)
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
        st.subheader("Annual Withdrawal Plan (Fixed Amount)")
        strategies['apply_pension_splitting'] = st.checkbox('Apply Pension Income Splitting', value=True)
        manual_withdrawals = {'user1': {}, 'user2': {}}
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**User 1 (You)**")
            manual_withdrawals['user1']['rrsp'] = st.number_input("RRSP Withdrawal", 0, None, 30000, 1000, key='u1_rrsp')
            manual_withdrawals['user1']['non_reg'] = st.number_input("Non-Reg Withdrawal", 0, None, 0, 1000, key='u1_nonreg')
            manual_withdrawals['user1']['tfsa'] = st.number_input("TFSA Withdrawal", 0, None, 0, 1000, key='u1_tfsa')
        with c2:
            st.markdown("**User 2 (Spouse)**")
            manual_withdrawals['user2']['rrsp'] = st.number_input("RRSP Withdrawal", 0, None, 30000, 1000, key='u2_rrsp')
            manual_withdrawals['user2']['non_reg'] = st.number_input("Non-Reg Withdrawal", 0, None, 0, 1000, key='u2_nonreg')
            manual_withdrawals['user2']['tfsa'] = st.number_input("TFSA Withdrawal", 0, None, 0, 1000, key='u2_tfsa')
        strategies['manual_withdrawals'] = manual_withdrawals

    calculate_btn = st.button("🚀 Start Simulation", use_container_width=True, type="primary")

# --- Main Screen ---
if calculate_btn:
    inputs = {
        'assets': {
            'user1': {'current_age': user1_current_age, 'rrsp': user1_rrsp, 'tfsa': user1_tfsa, 'non_reg': user1_non_reg, 'non_reg_cost': user1_non_reg_cost},
            'user2': {'current_age': user2_current_age, 'rrsp': user2_rrsp, 'tfsa': user2_tfsa, 'non_reg': user2_non_reg, 'non_reg_cost': user2_non_reg_cost}
        },
        'common': {'retirement_age': retirement_age, 'end_age': end_age, 'annual_spending': annual_spending, 'investment_return': investment_return, 'inflation_rate': inflation_rate, 'province': province}
    }

    with st.spinner('Calculating... 🏃‍♂️'):
        if mode == 'Manual Withdrawal Plan':
            st.header("📈 My Plan vs. Automatic Optimization")
            
            # 1. Run user's manual plan
            manual_results_df = run_simulation(inputs, 'Manual Withdrawal Plan', strategies)
            
            # 2. Run the automatically optimized plan for comparison
            auto_strategies = {'apply_pension_splitting': True}
            auto_results_df = run_simulation(inputs, 'Automatic Optimization (Recommended)', auto_strategies)

            # --- NEW: Create and display comparison chart ---
            st.subheader("Asset Growth Comparison: My Plan vs. Optimized")
            comparison_df = pd.DataFrame({
                'Age': manual_results_df['Age'],
                'My Plan': manual_results_df['End of Year Assets'],
                'Optimized Plan': auto_results_df['End of Year Assets']
            }).set_index('Age')
            st.line_chart(comparison_df)
            # --- END NEW ---

            # Summary Comparison
            manual_last_year = manual_results_df.iloc[-1]
            auto_last_year = auto_results_df.iloc[-1]
            
            manual_total_tax = manual_results_df['Total Tax'].sum()
            auto_total_tax = auto_results_df['Total Tax'].sum()

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("My Plan Results")
                if manual_last_year['Notes'] == 'Assets Depleted':
                    st.error(f"**Assets depleted at age {int(manual_last_year['Age'])}**")
                else:
                    st.success(f"**${manual_last_year['End of Year Assets']:,.0f}** remaining at age {end_age}")
                st.metric(label="Total Taxes Paid", value=f"${manual_total_tax:,.0f}", delta=f"${manual_total_tax - auto_total_tax:,.0f} (vs. Optimized)")
            
            with col2:
                st.subheader("Automatic Optimization Results")
                if auto_last_year['Notes'] == 'Assets Depleted':
                    st.error(f"**Assets depleted at age {int(auto_last_year['Age'])}**")
                else:
                    st.success(f"**${auto_last_year['End of Year Assets']:,.0f}** remaining at age {end_age}")
                st.metric(label="Total Taxes Paid", value=f"${auto_total_tax:,.0f}")
            
            st.info(f"**Analysis:** The automatic optimization strategy could save you **${manual_total_tax - auto_total_tax:,.0f}** in taxes, leaving you with **${auto_last_year['End of Year Assets'] - manual_last_year['End of Year Assets']:,.0f}** more in assets.")
            
            # Detailed Table for Manual Plan
            st.subheader("Detailed Annual Flow (My Plan)")
            st.dataframe(manual_results_df.style.format('${:,.0f}', subset=['Start of Year Assets', 'Annual Spending', 'Pension Split Amount', 'Total Tax', 'End of Year Assets']), use_container_width=True)

        else: # Automatic Optimization Mode
            st.header("📊 Automatic Optimization Simulation Results")
            results_df = run_simulation(inputs, 'Automatic Optimization (Recommended)', strategies)
            last_year = results_df.iloc[-1]
            if last_year['Notes'] == 'Assets Depleted':
                st.error(f"**Assets Depleted:** Based on the simulation, your assets are projected to run out at age **{int(last_year['Age'])}**.")
            else:
                st.success(f"**Plan Successful!** You can maintain your spending until age **{end_age}**, with an estimated **${last_year['End of Year Assets']:,.0f}** remaining.")
            
            st.line_chart(results_df, x='Age', y='End of Year Assets')
            st.dataframe(results_df.style.format('${:,.0f}', subset=['Start of Year Assets', 'Annual Spending', 'Pension Split Amount', 'Total Tax', 'End of Year Assets']), use_container_width=True)
else:
    st.info("👈 Enter your information in the sidebar and click 'Start Simulation' to begin.")
