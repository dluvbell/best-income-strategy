import streamlit as st
import pandas as pd
import copy

# --- 페이지 기본 설정 ---
st.set_page_config(
    page_title="캐나다 은퇴 계획 통합 시뮬레이터",
    page_icon="🇨🇦",
    layout="wide"
)

# --- 세금 정보 (2024년 기준 단순화) ---
# 실제 적용 시에는 매년 업데이트된 세율 및 정부 데이터(OAS 등) 필요
TAX_BRACKETS = {
    'ON': {
        'federal': [
            {'rate': 0.15, 'limit': 55867}, {'rate': 0.205, 'limit': 111733},
            {'rate': 0.26, 'limit': 173205}, {'rate': 0.29, 'limit': 246752},
            {'rate': 0.33, 'limit': float('inf')}
        ],
        'provincial': [
            {'rate': 0.0505, 'limit': 51446}, {'rate': 0.0915, 'limit': 102894},
            {'rate': 0.1116, 'limit': 150000}, {'rate': 0.1216, 'limit': 220000},
            {'rate': 0.1316, 'limit': float('inf')}
        ],
        'basic_personal_amount': {'federal': 15705, 'provincial': 12399}
    },
    'BC': {
        'federal': [
            {'rate': 0.15, 'limit': 55867}, {'rate': 0.205, 'limit': 111733},
            {'rate': 0.26, 'limit': 173205}, {'rate': 0.29, 'limit': 246752},
            {'rate': 0.33, 'limit': float('inf')}
        ],
        'provincial': [
            {'rate': 0.0506, 'limit': 47937}, {'rate': 0.077, 'limit': 95875},
            {'rate': 0.105, 'limit': 110070}, {'rate': 0.1229, 'limit': 133664},
            {'rate': 0.147, 'limit': 181232}, {'rate': 0.168, 'limit': 252752},
            {'rate': 0.205, 'limit': float('inf')}
        ],
        'basic_personal_amount': {'federal': 15705, 'provincial': 12580}
    },
    'AB': {
        'federal': [
            {'rate': 0.15, 'limit': 55867}, {'rate': 0.205, 'limit': 111733},
            {'rate': 0.26, 'limit': 173205}, {'rate': 0.29, 'limit': 246752},
            {'rate': 0.33, 'limit': float('inf')}
        ],
        'provincial': [
            {'rate': 0.10, 'limit': 148269}, {'rate': 0.12, 'limit': 177922},
            {'rate': 0.13, 'limit': 237230}, {'rate': 0.14, 'limit': 355845},
            {'rate': 0.15, 'limit': float('inf')}
        ],
        'basic_personal_amount': {'federal': 15705, 'provincial': 21885}
    }
}
OAS_CLAWBACK_THRESHOLD = 90997 # 2024년 기준

# --- 계산 함수 ---
def calculate_tax(income, province):
    brackets = TAX_BRACKETS.get(province)
    if not brackets:
        return 0

    tax = 0
    
    # Federal Tax
    fed_taxable_income = max(0, income - brackets['basic_personal_amount']['federal'])
    last_limit = 0
    for bracket in brackets['federal']:
        if fed_taxable_income > 0:
            taxable_in_bracket = min(fed_taxable_income, bracket['limit'] - last_limit)
            tax += taxable_in_bracket * bracket['rate']
            fed_taxable_income -= taxable_in_bracket
            last_limit = bracket['limit']
            if fed_taxable_income <= 0:
                break

    # Provincial Tax
    prov_taxable_income = max(0, income - brackets['basic_personal_amount']['provincial'])
    last_limit = 0
    for bracket in brackets['provincial']:
        if prov_taxable_income > 0:
            taxable_in_bracket = min(prov_taxable_income, bracket['limit'] - last_limit)
            tax += taxable_in_bracket * bracket['rate']
            prov_taxable_income -= taxable_in_bracket
            last_limit = bracket['limit']
            if prov_taxable_income <= 0:
                break
    
    return tax

def calculate_oas_clawback(income):
    if income <= OAS_CLAWBACK_THRESHOLD:
        return 0
    return (income - OAS_CLAWBACK_THRESHOLD) * 0.15

def run_simulation(inputs):
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
    age2 = common['retirement_age'] + (assets['user2']['current_age'] - assets['user1']['current_age'])
    spending = common['annual_spending']

    for i in range(common['end_age'] - common['retirement_age'] + 1):
        current_age = age1 + i
        
        total_assets_start = sum(assets[u][acc] for u in ['user1', 'user2'] for acc in ['rrsp', 'tfsa', 'non_reg'])

        if total_assets_start <= 0:
            results.append({'나이': current_age, '연초 총자산': 0, '연간 생활비': 0, '총 세금': 0, '연말 총자산': 0, '비고': '자산 소진'})
            break

        needed_after_tax = spending
        
        # 세금을 포함한 필요 자금 추정 (반복 계산으로 정확도 향상 가능하나 여기서는 단순화)
        estimated_tax_rate = 0.20 
        needed_before_tax = needed_after_tax / (1 - estimated_tax_rate)
        
        # --- 인출 로직 ---
        # 1. Non-Registered 인출
        # 2. RRSP/RRIF 인출
        # 3. TFSA 인출
        
        withdrawals = {'user1': {'rrsp': 0, 'tfsa': 0, 'non_reg': 0}, 'user2': {'rrsp': 0, 'tfsa': 0, 'non_reg': 0}}
        incomes = {'user1': 0, 'user2': 0}
        
        # 인출 시뮬레이션 (세금 최소화를 위해 부부의 소득을 비슷하게 맞추는 것이 목표)
        # 이 로직은 매우 복잡하며, 여기서는 단순화된 접근법을 사용합니다.
        
        # 1. Non-Registered에서 인출하여 소득 발생
        for user in ['user1', 'user2']:
            if needed_before_tax > 0 and assets[user]['non_reg'] > 0:
                w_amount = min(needed_before_tax / 2, assets[user]['non_reg'])
                withdrawals[user]['non_reg'] = w_amount
                assets[user]['non_reg'] -= w_amount
                
                # 양도소득 계산 (단순화)
                cost_ratio = assets[user]['non_reg_cost'] / (assets[user]['non_reg'] + w_amount) if (assets[user]['non_reg'] + w_amount) > 0 else 0
                capital_gain = w_amount * (1 - cost_ratio)
                taxable_gain = capital_gain * 0.5
                incomes[user] += taxable_gain
                assets[user]['non_reg_cost'] *= (1 - w_amount / (assets[user]['non_reg'] + w_amount)) if (assets[user]['non_reg'] + w_amount) > 0 else 1
                
        # 2. RRSP/RRIF에서 나머지 필요금액 인출
        total_withdrawn = sum(withdrawals[u]['non_reg'] for u in ['user1', 'user2'])
        remaining_needed = needed_before_tax - total_withdrawn
        
        if remaining_needed > 0:
            # RRSP가 더 많은 쪽에서 우선 인출하여 연금 분할 효과 극대화
            user_order = sorted(['user1', 'user2'], key=lambda u: assets[u]['rrsp'], reverse=True)
            for user in user_order:
                if remaining_needed > 0:
                    w_amount = min(remaining_needed, assets[user]['rrsp'])
                    withdrawals[user]['rrsp'] = w_amount
                    assets[user]['rrsp'] -= w_amount
                    remaining_needed -= w_amount

        # 3. 과세 소득 및 연금 분할
        rrif_income1 = withdrawals['user1']['rrsp']
        rrif_income2 = withdrawals['user2']['rrsp']
        
        pension_split_amount = 0
        if rrif_income1 > rrif_income2:
            potential_split = (rrif_income1 - rrif_income2) / 2
            pension_split_amount = min(rrif_income1 * 0.5, potential_split)
            rrif_income1 -= pension_split_amount
            rrif_income2 += pension_split_amount
        else:
            potential_split = (rrif_income2 - rrif_income1) / 2
            pension_split_amount = min(rrif_income2 * 0.5, potential_split)
            rrif_income2 -= pension_split_amount
            rrif_income1 += pension_split_amount
            
        incomes['user1'] += rrif_income1
        incomes['user2'] += rrif_income2

        # 4. 세금 계산
        tax1 = calculate_tax(incomes['user1'], common['province']) + calculate_oas_clawback(incomes['user1'])
        tax2 = calculate_tax(incomes['user2'], common['province']) + calculate_oas_clawback(incomes['user2'])
        total_tax = tax1 + tax2
        
        # 5. 세후 실제 인출액과 생활비 비교 및 추가 인출 (TFSA)
        net_withdrawal = sum(withdrawals[u][acc] for u in ['user1', 'user2'] for acc in ['non_reg', 'rrsp']) - total_tax
        shortfall = spending - net_withdrawal
        
        if shortfall > 0:
            for user in ['user1', 'user2']:
                if shortfall > 0:
                    w_amount = min(shortfall, assets[user]['tfsa'])
                    withdrawals[user]['tfsa'] += w_amount
                    assets[user]['tfsa'] -= w_amount
                    shortfall -= w_amount
        
        # 연말 자산 (투자 성장 반영)
        for user in ['user1', 'user2']:
            for acc_type in ['rrsp', 'tfsa', 'non_reg']:
                assets[user][acc_type] *= (1 + common['investment_return'])
            # Non-reg 재투자 시 원금(Cost base)도 증가
            growth = assets[user]['non_reg'] * common['investment_return'] / (1 + common['investment_return'])
            assets[user]['non_reg_cost'] += growth

        total_assets_end = sum(assets[u][acc] for u in ['user1', 'user2'] for acc in ['rrsp', 'tfsa', 'non_reg'])

        results.append({
            '나이': current_age,
            '연초 총자산': total_assets_start,
            '연간 생활비': spending,
            '연금 분할액': pension_split_amount,
            '총 세금': total_tax,
            '연말 총자산': total_assets_end,
            '비고': ''
        })
        
        # 다음 해 준비
        spending *= (1 + common['inflation_rate'])
        
    return pd.DataFrame(results)


# --- Streamlit UI ---
st.title("🇨🇦 캐나다 은퇴 계획 통합 시뮬레이터")
st.markdown("부부의 세금 최적화(**연금 소득 분할**) 및 효율적인 **인출 전략**을 고려하여 현실적인 은퇴 계획을 시뮬레이션합니다.")

with st.sidebar:
    st.header("1. 정보 입력")

    tab1, tab2 = st.tabs(["본인", "배우자"])
    with tab1:
        st.subheader("본인 정보")
        user1_current_age = st.number_input("현재 나이 (본인)", min_value=20, max_value=100, value=40)
        user1_rrsp = st.number_input("RRSP/RRIF 자산 ($) (본인)", min_value=0, value=300000, step=10000)
        user1_tfsa = st.number_input("TFSA 자산 ($) (본인)", min_value=0, value=80000, step=10000)
        user1_non_reg = st.number_input("Non-Registered 자산 ($) (본인)", min_value=0, value=50000, step=10000)
        user1_non_reg_cost = st.number_input("Non-Registered 원금 ($) (본인)", min_value=0, value=40000, step=10000)

    with tab2:
        st.subheader("배우자 정보")
        user2_current_age = st.number_input("현재 나이 (배우자)", min_value=20, max_value=100, value=40)
        user2_rrsp = st.number_input("RRSP/RRIF 자산 ($) (배우자)", min_value=0, value=200000, step=10000)
        user2_tfsa = st.number_input("TFSA 자산 ($) (배우자)", min_value=0, value=60000, step=10000)
        user2_non_reg = st.number_input("Non-Registered 자산 ($) (배우자)", min_value=0, value=20000, step=10000)
        user2_non_reg_cost = st.number_input("Non-Registered 원금 ($) (배우자)", min_value=0, value=15000, step=10000)
    
    st.divider()
    
    st.header("2. 공통 설정")
    retirement_age = st.number_input("은퇴 목표 나이", min_value=40, max_value=80, value=65)
    end_age = st.number_input("시뮬레이션 종료 나이", min_value=70, max_value=120, value=95)
    annual_spending = st.number_input("연간 생활비 (현재 가치, $)", min_value=0, value=60000, step=5000)
    investment_return = st.slider("연평균 투자 수익률 (%)", 0.0, 15.0, 5.0, 0.5) / 100
    inflation_rate = st.slider("연평균 물가 상승률 (%)", 0.0, 10.0, 2.0, 0.1) / 100
    province = st.selectbox("거주 주 (Province)", options=['ON', 'BC', 'AB'], index=0)
    
    calculate_btn = st.button("📈 시뮬레이션 시작", use_container_width=True, type="primary")

# --- 메인 화면 ---
if calculate_btn:
    inputs = {
        'assets': {
            'user1': {
                'current_age': user1_current_age, 'rrsp': user1_rrsp, 'tfsa': user1_tfsa,
                'non_reg': user1_non_reg, 'non_reg_cost': user1_non_reg_cost
            },
            'user2': {
                'current_age': user2_current_age, 'rrsp': user2_rrsp, 'tfsa': user2_tfsa,
                'non_reg': user2_non_reg, 'non_reg_cost': user2_non_reg_cost
            }
        },
        'common': {
            'retirement_age': retirement_age, 'end_age': end_age, 'annual_spending': annual_spending,
            'investment_return': investment_return, 'inflation_rate': inflation_rate, 'province': province
        }
    }

    with st.spinner('열심히 계산 중입니다... 잠시만 기다려주세요.'):
        results_df = run_simulation(inputs)

    st.header("📊 시뮬레이션 결과")
    
    # 결과 요약
    last_year = results_df.iloc[-1]
    if last_year['비고'] == '자산 소진':
        st.error(f"**자산 소진 예상**\n\n시뮬레이션 결과, **{int(last_year['나이'])}세**에 자산이 모두 소진될 것으로 예상됩니다.")
    else:
        final_assets = last_year['연말 총자산']
        st.success(f"**계획 성공!**\n\n**{end_age}세**까지 생활비 유지가 가능하며, 예상 잔여 자산은 **${final_assets:,.0f}** 입니다.")

    # 차트
    st.subheader("연도별 자산 변화 추이")
    st.line_chart(results_df, x='나이', y='연말 총자산')
    
    # 상세 테이블
    st.subheader("상세 연간 흐름표")
    
    # 보기 좋게 포맷팅
    formatted_df = results_df.copy()
    for col in ['연초 총자산', '연간 생활비', '연금 분할액', '총 세금', '연말 총자산']:
        formatted_df[col] = formatted_df[col].apply(lambda x: f"${x:,.0f}")
        
    st.dataframe(formatted_df, use_container_width=True, hide_index=True)

else:
    st.info("좌측 사이드바에서 정보를 입력하고 '시뮬레이션 시작' 버튼을 눌러주세요.")
