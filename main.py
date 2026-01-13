#!/usr/bin/env python3
"""
🧪 화학물질 통합 관리 플랫폼
- 모듈화된 서비스 제공
- 필요한 기능만 선택하여 사용
"""

import streamlit as st

# ============================================
# 페이지 설정
# ============================================
st.set_page_config(
    page_title="화학물질 통합 관리 플랫폼",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# 스타일
# ============================================
st.markdown("""
<style>
    .main-title {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        color: #1e3a5f;
        margin-bottom: 0.5rem;
    }
    .sub-title {
        font-size: 1.1rem;
        text-align: center;
        color: #64748b;
        margin-bottom: 2rem;
    }
    .module-card {
        padding: 2rem;
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        border-radius: 1rem;
        border: 1px solid #cbd5e1;
        text-align: center;
        transition: all 0.3s ease;
        cursor: pointer;
        height: 100%;
    }
    .module-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        border-color: #3b82f6;
    }
    .module-icon {
        font-size: 3rem;
        margin-bottom: 1rem;
    }
    .module-name {
        font-size: 1.3rem;
        font-weight: bold;
        color: #1e293b;
        margin-bottom: 0.5rem;
    }
    .module-desc {
        font-size: 0.9rem;
        color: #64748b;
    }
    .badge-new {
        display: inline-block;
        padding: 0.25rem 0.5rem;
        background: #22c55e;
        color: white;
        border-radius: 0.25rem;
        font-size: 0.7rem;
        font-weight: bold;
        margin-left: 0.5rem;
    }
    .badge-soon {
        display: inline-block;
        padding: 0.25rem 0.5rem;
        background: #f59e0b;
        color: white;
        border-radius: 0.25rem;
        font-size: 0.7rem;
        font-weight: bold;
        margin-left: 0.5rem;
    }
    .feature-list {
        text-align: left;
        padding-left: 1rem;
        margin-top: 1rem;
    }
    .feature-list li {
        margin: 0.3rem 0;
        font-size: 0.85rem;
        color: #475569;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# 헤더
# ============================================
st.markdown('<p class="main-title">🧪 화학물질 통합 관리 플랫폼</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">필요한 서비스만 선택하여 사용하세요 | KOSHA API 연동</p>', unsafe_allow_html=True)

# ============================================
# 모듈 선택
# ============================================
st.markdown("---")
st.subheader("📦 서비스 모듈 선택")

col1, col2, col3, col4 = st.columns(4)

# 모듈 1: MSDS 작성
with col1:
    st.markdown("""
    <div class="module-card">
        <div class="module-icon">📄</div>
        <div class="module-name">MSDS 작성<span class="badge-new">NEW</span></div>
        <div class="module-desc">물질안전보건자료 16개 항목 자동 생성</div>
        <ul class="feature-list">
            <li>CAS 번호 자동 조회</li>
            <li>GHS 분류 자동 적용</li>
            <li>Word/PDF 출력</li>
            <li>ATEmix 계산</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("📄 MSDS 작성 시작", key="btn_msds", use_container_width=True):
        st.switch_page("pages/1_📄_MSDS_작성.py")

# 모듈 2: 인벤토리 관리
with col2:
    st.markdown("""
    <div class="module-card">
        <div class="module-icon">📦</div>
        <div class="module-name">인벤토리 관리</div>
        <div class="module-desc">사업장 화학물질 목록 관리</div>
        <ul class="feature-list">
            <li>규제정보 자동 조회</li>
            <li>작업환경측정 대상 확인</li>
            <li>특수건강진단 대상 확인</li>
            <li>엑셀 업로드/다운로드</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("📦 인벤토리 관리", key="btn_inv", use_container_width=True):
        st.switch_page("pages/2_📦_인벤토리_관리.py")

# 모듈 3: 배출량 산정
with col3:
    st.markdown("""
    <div class="module-card">
        <div class="module-icon">📊</div>
        <div class="module-name">배출량 산정</div>
        <div class="module-desc">PRTR 배출량 계산 및 신고</div>
        <ul class="feature-list">
            <li>물질수지법 (Tier 3)</li>
            <li>배출계수법 (Tier 4)</li>
            <li>PRTR 대상물질 확인</li>
            <li>신고서 자동 생성</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("📊 배출량 산정", key="btn_emission", use_container_width=True):
        st.switch_page("pages/3_📊_배출량_산정.py")

# 모듈 4: 통합환경법
with col4:
    st.markdown("""
    <div class="module-card">
        <div class="module-icon">📋</div>
        <div class="module-name">통합환경법<span class="badge-soon">SOON</span></div>
        <div class="module-desc">통합환경법 제출자료 생성</div>
        <ul class="feature-list">
            <li>사업장 대기 배출량</li>
            <li>수질 배출량</li>
            <li>폐기물 이동량</li>
            <li>통합 보고서 생성</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("📋 통합환경법 (준비중)", key="btn_env", use_container_width=True, disabled=True):
        pass

# ============================================
# 빠른 도구
# ============================================
st.markdown("---")
st.subheader("🔧 빠른 도구")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("#### 🔍 CAS 번호 조회")
    quick_cas = st.text_input("CAS 번호 입력", placeholder="예: 67-64-1", label_visibility="collapsed")
    if st.button("조회", key="quick_search"):
        if quick_cas:
            st.info(f"'{quick_cas}' 조회 → MSDS 작성 페이지로 이동합니다.")
            # TODO: 세션에 CAS 저장 후 페이지 이동

with col2:
    st.markdown("#### 📤 파일 업로드")
    uploaded = st.file_uploader("엑셀/PDF 업로드", type=['xlsx', 'xls', 'pdf'], label_visibility="collapsed")
    if uploaded:
        st.success(f"✅ {uploaded.name} 업로드 완료")

with col3:
    st.markdown("#### 📚 가이드")
    st.markdown("""
    - [MSDS 작성 가이드](https://www.kosha.or.kr)
    - [PRTR 신고 안내](https://icis.me.go.kr)
    - [GHS 분류 기준](https://www.kosha.or.kr)
    """)

# ============================================
# 최근 활동 / 알림
# ============================================
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.subheader("📌 공지사항")
    st.markdown("""
    - **2025.01.15** - MSDS 작성 모듈 v1.0 출시 🎉
    - **2025.01.10** - KOSHA API 연동 완료
    - **2025.01.05** - 플랫폼 베타 오픈
    """)

with col2:
    st.subheader("📈 통계")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("등록 물질", "415종")
    with col_b:
        st.metric("MSDS 생성", "128건")
    with col_c:
        st.metric("API 조회", "2,341회")

# ============================================
# 푸터
# ============================================
st.markdown("---")
st.caption("© 2025 Kay's Chem Manager | 화학물질 통합 관리 플랫폼 | KOSHA API 연동")
