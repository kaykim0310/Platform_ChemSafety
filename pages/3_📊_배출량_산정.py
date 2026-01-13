#!/usr/bin/env python3
"""
📊 배출량 산정 페이지
"""
import streamlit as st

st.set_page_config(page_title="배출량 산정", page_icon="📊", layout="wide")

st.title("📊 배출량 산정")
st.markdown("---")

st.info("🚧 이 모듈은 PRTR 배출량 산정 및 신고서 작성 기능을 제공합니다.")

st.markdown("""
### 주요 기능
- 🧮 **Tier 3: 물질수지법**
  - 투입량 - 회수량 - 파괴량 = 배출량
- 📈 **Tier 4: 배출계수법**
  - 활동량 × 배출계수 × (1 - 방지효율)
- 📋 **PRTR 대상물질 확인**
  - 1그룹 (20종): 1톤/년 이상
  - 2그룹 (395종): 10톤/년 이상
- 📄 **신고서 자동 생성**

### 개발 상태
- ✅ 배출량 계산 로직 완료
- ✅ PRTR 대상물질 DB 구축
- 🔄 신고서 양식 개발 중
- ⏳ 2025년 2월 출시 예정
""")

# 간단한 계산기
st.markdown("---")
st.subheader("🧮 빠른 배출량 계산")

calc_method = st.radio("산정방법", ["물질수지법", "배출계수법"], horizontal=True)

if calc_method == "물질수지법":
    col1, col2, col3 = st.columns(3)
    with col1:
        input_amt = st.number_input("투입량 (kg/년)", min_value=0.0, value=1000.0)
    with col2:
        recovery = st.number_input("회수량 (kg/년)", min_value=0.0, value=400.0)
    with col3:
        destroy = st.number_input("파괴량 (kg/년)", min_value=0.0, value=500.0)
    
    emission = max(input_amt - recovery - destroy, 0)
    st.success(f"**대기배출량: {emission:,.1f} kg/년**")

else:
    col1, col2, col3 = st.columns(3)
    with col1:
        activity = st.number_input("활동량 (단위/년)", min_value=0.0, value=10000.0)
    with col2:
        ef = st.number_input("배출계수 (kg/단위)", min_value=0.0, value=0.01, format="%.4f")
    with col3:
        efficiency = st.number_input("방지효율 (%)", min_value=0.0, max_value=100.0, value=90.0)
    
    emission = activity * ef * (1 - efficiency / 100)
    st.success(f"**대기배출량: {emission:,.1f} kg/년**")

if st.button("🏠 홈으로 돌아가기"):
    st.switch_page("main.py")
