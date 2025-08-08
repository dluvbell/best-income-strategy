import streamlit as st
import pandas as pd
import copy

# --- 페이지 기본 설정 ---
st.set_page_config(
    page_title="캐나다 은퇴 전략 시뮬레이터",
    page_icon="🧠",
    layout="wide"
)

# --- 세금 정보 (2024년 기준 단순화) ---
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

# --- 계산 함수 ---
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
    
    # 은퇴 전 자산 성장
    years_to_retirement = common['retirement_age'] - assets['user1']['current_age']
    for _ in range(years_to_retirement):
        for user in ['user1', 'user2']:
            for acc_type in ['rrsp', 'tfsa', 'non_reg']:
                assets[user][acc_type] *= (1 + common['investment_return'])

    # 은퇴 후 시뮬레이션
    results = []
    age1 = common['retirement_age']
    spending = common['annual_spending']

    for i in range(common['end_age'] - common['retirement_age'] + 1):
        current_age = age1 + i
        total_assets_start = sum(assets[u][acc] for u in ['user1', 'user2'] for acc in ['rrsp', 'tfsa', 'non_reg'])

        if total_assets_start <= 0:
            results.append({'나이': current_age, '연초 총자산': 0, '연간 생활비': 0, '총 세금': 0, '연말 총자산': 0, '비고': '자산 소진'})
            break

        # --- 인출 로직 시작 ---
        withdrawals = {'user1': {'rrsp': 0, 'tfsa': 0, 'non_reg': 0}, 'user2': {'rrsp': 0, 'tfsa': 0, 'non_reg': 0}}
        incomes = {'user1': 0, 'user2': 0}
        
        needed_after_tax = spending
        
        if mode == '자동 최적화 (추천)':
            estimated_tax_rate = 0.20
            needed_before_tax = needed_after_tax / (1 - estimated_tax_rate)
            
            # 1. Non-Reg -> 2. RRSP -> 3. TFSA 순서로 인출
            # 이 로직은 복잡하며, 여기서는 단순화된 접근법을 사용합니다.
            
            # Non-Reg 인출
            total_withdrawn = 0
            for user in ['user1', 'user2']:
                w_amount = min(needed_before_tax / 2, assets[user]['non_reg'])
                withdrawals[user]['non_reg'] = w_amount
                total_withdrawn += w_amount
            
            # RRSP 인출
            remaining_needed = needed_before_tax - total_withdrawn
            if remaining_needed > 0:
                user_order = sorted(['user1', 'user2'], key=lambda u: assets[u]['rrsp'], reverse=True)
                for user in user_order:
                    if remaining_needed > 0:
                        w_amount = min(remaining_needed, assets[user]['rrsp'])
                        withdrawals[user]['rrsp'] += w_amount
                        remaining_needed -= w_amount
        else: # 수동 인출 계획
            withdrawals = strategies['manual_withdrawals']

        # 인출 실행 및 소득 계산
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

        # 연금 소득 분할 적용
        pension_split_amount = 0
        if strategies.get('apply_pension_splitting', False):
            rrif_income1 = withdrawals['user1']['rrsp']
            rrif_income2 = withdrawals['user2']['rrsp']
            
            # 소득이 높은 쪽에서 낮은 쪽으로 분할
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

        # 세금 계산
        tax1 = calculate_tax(incomes['user1'], common['province']) + calculate_oas_clawback(incomes['user1'])
        tax2 = calculate_tax(incomes['user2'], common['province']) + calculate_oas_clawback(incomes['user2'])
        total_tax = tax1 + tax2
        
        # 세후 실제 인출액과 생활비 비교 및 추가 인출 (TFSA에서 최우선)
        net_withdrawal = sum(w for u in ['user1', 'user2'] for w in withdrawals[u].values()) - total_tax
        shortfall = spending - net_withdrawal
        
        if shortfall > 0:
            for user in ['user1', 'user2']:
                if shortfall <= 0: break
                w_amount = min(shortfall, assets[user]['tfsa'])
                withdrawals[user]['tfsa'] += w_amount
                assets[user]['tfsa'] -= w_amount
                shortfall -= w_amount

        # 연말 자산 (투자 성장 반영)
        for user in ['user1', 'user2']:
            for acc_type in ['rrsp', 'tfsa', 'non_reg']:
                assets[user][acc_type] *= (1 + common['investment_return'])
            if assets[user]['non_reg'] > 0:
                growth = assets[user]['non_reg'] * common['investment_return'] / (1 + common['investment_return'])
                assets[user]['non_reg_cost'] += growth

        total_assets_end = sum(assets[u][acc] for u in ['user1', 'user2'] for acc in ['rrsp', 'tfsa', 'non_reg'])

        results.append({
            '나이': current_age, '연초 총자산': total_assets_start, '연간 생활비': spending,
            '연금 분할액': pension_split_amount, '총 세금': total_tax, '연말 총자산': total_assets_end, '비고': ''
        })
        spending *= (1 + common['inflation_rate'])
        
    return pd.DataFrame(results)


# --- Streamlit UI ---
st.title("🧠 캐나다 은퇴 전략 시뮬레이터")
st.markdown("다양한 **인출 전략**과 **세금 최적화** 옵션을 적용하여 나만의 은퇴 계획을 비교하고 분석해보세요.")

with st.sidebar:
    st.header("1. 기본 정보")
    tab1, tab2 = st.tabs(["본인", "배우자"])
    with tab1:
        user1_current_age = st.number_input("현재 나이 (본인)", 20, 100, 40)
        user1_rrsp = st.number_input("RRSP/RRIF ($) (본인)", 0, None, 300000, 10000)
        user1_tfsa = st.number_input("TFSA ($) (본인)", 0, None, 80000, 10000)
        user1_non_reg = st.number_input("Non-Registered ($) (본인)", 0, None, 50000, 10000)
        user1_non_reg_cost = st.number_input("Non-Reg 원금 ($) (본인)", 0, None, 40000, 10000)
    with tab2:
        user2_current_age = st.number_input("현재 나이 (배우자)", 20, 100, 40)
        user2_rrsp = st.number_input("RRSP/RRIF ($) (배우자)", 0, None, 200000, 10000)
        user2_tfsa = st.number_input("TFSA ($) (배우자)", 0, None, 60000, 10000)
        user2_non_reg = st.number_input("Non-Registered ($) (배우자)", 0, None, 20000, 10000)
        user2_non_reg_cost = st.number_input("Non-Reg 원금 ($) (배우자)", 0, None, 15000, 10000)
    
    st.divider()
    st.header("2. 공통 설정")
    retirement_age = st.number_input("은퇴 목표 나이", 40, 80, 65)
    end_age = st.number_input("시뮬레이션 종료 나이", 70, 120, 95)
    annual_spending = st.number_input("연간 생활비 (현재 가치, $)", 0, None, 60000, 5000)
    investment_return = st.slider("연평균 투자 수익률 (%)", 0.0, 15.0, 5.0, 0.5) / 100
    inflation_rate = st.slider("연평균 물가 상승률 (%)", 0.0, 10.0, 2.0, 0.1) / 100
    province = st.selectbox("거주 주 (Province)", ['ON', 'BC', 'AB'])
    
    st.divider()
    st.header("3. 인출 전략")
    mode = st.radio("시뮬레이션 모드 선택", ['자동 최적화 (추천)', '수동 인출 계획'], horizontal=True)
    
    strategies = {}
    if mode == '자동 최적화 (추천)':
        strategies['apply_pension_splitting'] = st.checkbox('연금 소득 분할 (Pension Income Splitting) 적용', value=True)
    else:
        st.subheader("연간 인출 계획 (고정 금액)")
        strategies['apply_pension_splitting'] = st.checkbox('연금 소득 분할 (Pension Income Splitting) 적용', value=True)
        manual_withdrawals = {'user1': {}, 'user2': {}}
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**본인**")
            manual_withdrawals['user1']['rrsp'] = st.number_input("RRSP 인출액", 0, None, 30000, 1000, key='u1_rrsp')
            manual_withdrawals['user1']['non_reg'] = st.number_input("Non-Reg 인출액", 0, None, 0, 1000, key='u1_nonreg')
            manual_withdrawals['user1']['tfsa'] = st.number_input("TFSA 인출액", 0, None, 0, 1000, key='u1_tfsa')
        with c2:
            st.markdown("**배우자**")
            manual_withdrawals['user2']['rrsp'] = st.number_input("RRSP 인출액", 0, None, 30000, 1000, key='u2_rrsp')
            manual_withdrawals['user2']['non_reg'] = st.number_input("Non-Reg 인출액", 0, None, 0, 1000, key='u2_nonreg')
            manual_withdrawals['user2']['tfsa'] = st.number_input("TFSA 인출액", 0, None, 0, 1000, key='u2_tfsa')
        strategies['manual_withdrawals'] = manual_withdrawals

    calculate_btn = st.button("🚀 시뮬레이션 시작", use_container_width=True, type="primary")

# --- 메인 화면 ---
if calculate_btn:
    inputs = {
        'assets': {
            'user1': {'current_age': user1_current_age, 'rrsp': user1_rrsp, 'tfsa': user1_tfsa, 'non_reg': user1_non_reg, 'non_reg_cost': user1_non_reg_cost},
            'user2': {'current_age': user2_current_age, 'rrsp': user2_rrsp, 'tfsa': user2_tfsa, 'non_reg': user2_non_reg, 'non_reg_cost': user2_non_reg_cost}
        },
        'common': {'retirement_age': retirement_age, 'end_age': end_age, 'annual_spending': annual_spending, 'investment_return': investment_return, 'inflation_rate': inflation_rate, 'province': province}
    }

    with st.spinner('열심히 계산 중입니다... 🏃‍♂️'):
        if mode == '수동 인출 계획':
            st.header("📈 나의 계획 vs 자동 최적화 비교")
            
            # 1. 나의 계획 실행
            manual_results_df = run_simulation(inputs, '수동 인출 계획', strategies)
            
            # 2. 자동 최적화 계획 실행
            auto_strategies = {'apply_pension_splitting': True} # 자동은 항상 연금분할 적용
            auto_results_df = run_simulation(inputs, '자동 최적화 (추천)', auto_strategies)

            # 비교 요약
            manual_last_year = manual_results_df.iloc[-1]
            auto_last_year = auto_results_df.iloc[-1]
            
            manual_total_tax = manual_results_df['총 세금'].sum()
            auto_total_tax = auto_results_df['총 세금'].sum()

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("나의 계획 결과")
                if manual_last_year['비고'] == '자산 소진':
                    st.error(f"**{int(manual_last_year['나이'])}세**에 자산 소진")
                else:
                    st.success(f"**{end_age}세**에 **${manual_last_year['연말 총자산']:,.0f}** 남음")
                st.metric(label="총 납부 세금", value=f"${manual_total_tax:,.0f}", delta=f"${manual_total_tax - auto_total_tax:,.0f} (최적화 대비)")
            
            with col2:
                st.subheader("자동 최적화 결과")
                if auto_last_year['비고'] == '자산 소진':
                    st.error(f"**{int(auto_last_year['나이'])}세**에 자산 소진")
                else:
                    st.success(f"**{end_age}세**에 **${auto_last_year['연말 총자산']:,.0f}** 남음")
                st.metric(label="총 납부 세금", value=f"${auto_total_tax:,.0f}")
            
            st.info(f"**분석:** 자동 최적화 전략을 통해 총 **${manual_total_tax - auto_total_tax:,.0f}**의 세금을 절약하고, 자산을 **${auto_last_year['연말 총자산'] - manual_last_year['연말 총자산']:,.0f}** 더 많이 남길 수 있습니다.")
            
            # 상세 테이블
            st.subheader("상세 연간 흐름표 (나의 계획)")
            st.dataframe(manual_results_df.style.format('${:,.0f}', subset=['연초 총자산', '연간 생활비', '연금 분할액', '총 세금', '연말 총자산']), use_container_width=True)

        else: # 자동 최적화 모드
            st.header("📊 자동 최적화 시뮬레이션 결과")
            results_df = run_simulation(inputs, '자동 최적화 (추천)', strategies)
            last_year = results_df.iloc[-1]
            if last_year['비고'] == '자산 소진':
                st.error(f"**자산 소진 예상:** 시뮬레이션 결과, **{int(last_year['나이'])}세**에 자산이 모두 소진될 것으로 예상됩니다.")
            else:
                st.success(f"**계획 성공!** **{end_age}세**까지 생활비 유지가 가능하며, 예상 잔여 자산은 **${last_year['연말 총자산']:,.0f}** 입니다.")
            
            st.line_chart(results_df, x='나이', y='연말 총자산')
            st.dataframe(results_df.style.format('${:,.0f}', subset=['연초 총자산', '연간 생활비', '연금 분할액', '총 세금', '연말 총자산']), use_container_width=True)
else:
    st.info("👈 좌측 사이드바에서 정보를 입력하고 '시뮬레이션 시작' 버튼을 눌러주세요.")
