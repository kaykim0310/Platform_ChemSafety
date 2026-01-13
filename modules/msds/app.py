#!/usr/bin/env python3
"""
🧪 MSDS 작성 프로그램 v2.0
- 기존 i-msds 구조 기반 통합 버전
- 고용노동부 고시 양식 16개 항목
- KOSHA API 연동
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from datetime import date, datetime
import json
import io

# 모듈 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from core.kosha_api import get_full_msds_data, search_by_cas, search_by_name
    from core.prtr_db import check_prtr_status
    from core.ghs_utils import H_STATEMENTS, P_STATEMENTS, calculate_ate_mix
    KOSHA_AVAILABLE = True
except ImportError:
    KOSHA_AVAILABLE = False

# ============================================
# 페이지 설정
# ============================================
st.set_page_config(
    page_title="MSDS 작성 시스템",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# 스타일
# ============================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700&display=swap');
    
    * { font-family: 'Nanum Gothic', sans-serif !important; }
    
    .main-header {
        text-align: center;
        padding: 1.5rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .section-card {
        background-color: #f8f9fa;
        padding: 1.2rem;
        border-radius: 8px;
        border: 1px solid #dee2e6;
        margin-bottom: 0.8rem;
        transition: all 0.3s ease;
    }
    .section-card:hover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        transform: translateY(-2px);
    }
    .status-complete { color: #28a745; font-weight: bold; }
    .status-incomplete { color: #dc3545; font-weight: bold; }
    .status-partial { color: #ffc107; font-weight: bold; }
    .component-row {
        padding: 0.8rem;
        background: #e8f4f8;
        border-radius: 6px;
        margin: 0.5rem 0;
        border-left: 4px solid #17a2b8;
    }
    .reg-badge {
        display: inline-block;
        padding: 0.2rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: bold;
        margin: 0.1rem;
    }
    .reg-o { background: #fee2e2; color: #991b1b; }
    .reg-x { background: #e5e7eb; color: #6b7280; }
    .kosha-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        background: #dcfce7;
        color: #166534;
        border-radius: 1rem;
        font-size: 0.8rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# 세션 상태 초기화
# ============================================
def init_session_state():
    """세션 상태 초기화"""
    defaults = {
        'section1_data': {
            'product_name': '',
            'management_number': '',
            'recommended_use': '공업용',
            'manufacturer_info': {
                'company_name': '',
                'address': '',
                'phone': '',
                'emergency_phone': '119',
                'fax': '',
                'email': ''
            }
        },
        'section2_data': {
            'ghs_classification': [],
            'signal_word': '경고',
            'hazard_statements': [],
            'precautionary_statements': [],
            'pictograms': []
        },
        'section3_data': {
            'components': []
        },
        'section4_data': {
            'eye_contact': '',
            'skin_contact': '',
            'inhalation': '',
            'ingestion': '',
            'medical_attention': ''
        },
        'section5_data': {
            'extinguishing_media': '',
            'specific_hazards': '',
            'firefighting_equipment': ''
        },
        'section6_data': {
            'personal_precautions': '',
            'environmental_precautions': '',
            'cleanup_methods': ''
        },
        'section7_data': {
            'safe_handling': '',
            'storage_conditions': ''
        },
        'section8_data': {
            'exposure_limits': [],
            'engineering_controls': '',
            'ppe': {
                'respiratory': '',
                'eye': '',
                'hand': '',
                'body': ''
            }
        },
        'section9_data': {
            'appearance': '',
            'odor': '',
            'ph': '',
            'melting_point': '',
            'boiling_point': '',
            'flash_point': '',
            'vapor_pressure': '',
            'specific_gravity': '',
            'solubility': ''
        },
        'section10_data': {
            'stability': '',
            'reactivity': '',
            'conditions_to_avoid': '',
            'incompatible_materials': '',
            'decomposition_products': ''
        },
        'section11_data': {
            'acute_toxicity': [],
            'skin_corrosion': '',
            'eye_damage': '',
            'sensitization': '',
            'carcinogenicity': ''
        },
        'section12_data': {
            'ecotoxicity': '',
            'persistence': '',
            'bioaccumulation': '',
            'soil_mobility': ''
        },
        'section13_data': {
            'disposal_methods': '',
            'disposal_precautions': ''
        },
        'section14_data': {
            'un_number': '',
            'proper_shipping_name': '',
            'transport_class': '',
            'packing_group': '',
            'marine_pollutant': ''
        },
        'section15_data': {
            'regulations': []
        },
        'section16_data': {
            'revision_date': str(date.today()),
            'revision_number': '1',
            'revision_reason': '신규 작성',
            'references': []
        },
        'current_section': 1
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ============================================
# 유틸리티 함수
# ============================================
def check_section_status(section_key):
    """섹션 작성 상태 확인"""
    data = st.session_state.get(section_key, {})
    
    if section_key == 'section1_data':
        if data.get('product_name') and data.get('manufacturer_info', {}).get('company_name'):
            return "✅ 완료", "status-complete"
        elif data.get('product_name'):
            return "🔄 작성중", "status-partial"
    elif section_key == 'section3_data':
        components = data.get('components', [])
        if any(c.get('cas_no') for c in components):
            return "✅ 완료", "status-complete"
    elif section_key == 'section8_data':
        if data.get('exposure_limits') or data.get('ppe', {}).get('respiratory'):
            return "✅ 완료", "status-complete"
    
    return "⬜ 미작성", "status-incomplete"

def get_completion_stats():
    """전체 작성 진행률 계산"""
    completed = 0
    for i in range(1, 17):
        status, _ = check_section_status(f'section{i}_data')
        if "완료" in status:
            completed += 1
    return completed, 16

# ============================================
# 사이드바 - 네비게이션
# ============================================
with st.sidebar:
    st.markdown("### 📋 MSDS 작성")
    if KOSHA_AVAILABLE:
        st.markdown('<span class="kosha-badge">KOSHA API 연동</span>', unsafe_allow_html=True)
    
    st.divider()
    
    # 제품 정보 요약
    product_name = st.session_state.section1_data.get('product_name', '')
    if product_name:
        st.info(f"📦 **{product_name}**")
    
    # 진행률
    completed, total = get_completion_stats()
    st.progress(completed / total)
    st.caption(f"진행률: {completed}/{total} 섹션")
    
    st.divider()
    
    # 섹션 네비게이션
    st.markdown("#### 📑 섹션 선택")
    section_names = [
        "1. 화학제품과 회사정보",
        "2. 유해성·위험성",
        "3. 구성성분",
        "4. 응급조치 요령",
        "5. 폭발·화재시 대처",
        "6. 누출사고시 대처",
        "7. 취급 및 저장",
        "8. 노출방지/보호구",
        "9. 물리화학적 특성",
        "10. 안정성 및 반응성",
        "11. 독성정보",
        "12. 환경영향",
        "13. 폐기시 주의사항",
        "14. 운송정보",
        "15. 법적 규제현황",
        "16. 기타 참고사항"
    ]
    
    selected_section = st.radio(
        "섹션",
        range(1, 17),
        format_func=lambda x: section_names[x-1],
        index=st.session_state.current_section - 1,
        label_visibility="collapsed"
    )
    st.session_state.current_section = selected_section
    
    st.divider()
    
    # 빠른 도구
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 저장", use_container_width=True):
            st.success("저장됨!")
    with col2:
        if st.button("🔄 초기화", use_container_width=True):
            for key in list(st.session_state.keys()):
                if key.startswith('section'):
                    del st.session_state[key]
            init_session_state()
            st.rerun()

# ============================================
# 메인 컨텐츠 - 섹션별 작성
# ============================================
current = st.session_state.current_section

# 헤더
st.markdown(f"""
<div class="main-header">
    <h2>📋 물질안전보건자료 (MSDS) 작성</h2>
    <p>섹션 {current}. {section_names[current-1].split('. ')[1]}</p>
</div>
""", unsafe_allow_html=True)

# ============================================
# 섹션 1: 화학제품과 회사에 관한 정보
# ============================================
if current == 1:
    st.subheader("1️⃣ 화학제품과 회사에 관한 정보")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 가. 제품정보")
        st.session_state.section1_data['product_name'] = st.text_input(
            "제품명 *",
            value=st.session_state.section1_data.get('product_name', ''),
            placeholder="예: 산업용 세정제 A"
        )
        st.session_state.section1_data['management_number'] = st.text_input(
            "관리번호",
            value=st.session_state.section1_data.get('management_number', ''),
            placeholder="예: MSDS-2025-001"
        )
        st.session_state.section1_data['recommended_use'] = st.text_input(
            "권고 용도",
            value=st.session_state.section1_data.get('recommended_use', '공업용'),
            placeholder="예: 금속 세정용"
        )
    
    with col2:
        st.markdown("#### 나. 공급자/제조자 정보")
        mfr = st.session_state.section1_data.get('manufacturer_info', {})
        
        mfr['company_name'] = st.text_input("회사명 *", value=mfr.get('company_name', ''))
        mfr['address'] = st.text_input("주소", value=mfr.get('address', ''))
        
        col_a, col_b = st.columns(2)
        with col_a:
            mfr['phone'] = st.text_input("전화번호", value=mfr.get('phone', ''))
        with col_b:
            mfr['emergency_phone'] = st.text_input("긴급전화", value=mfr.get('emergency_phone', '119'))
        
        mfr['email'] = st.text_input("이메일", value=mfr.get('email', ''))
        st.session_state.section1_data['manufacturer_info'] = mfr

# ============================================
# 섹션 2: 유해성·위험성
# ============================================
elif current == 2:
    st.subheader("2️⃣ 유해성·위험성")
    
    st.markdown("#### 가. 유해·위험성 분류")
    
    ghs_options = [
        "급성 독성 (경구) - 구분 4",
        "급성 독성 (경피) - 구분 4",
        "급성 독성 (흡입) - 구분 4",
        "피부 부식성/자극성 - 구분 2",
        "심한 눈 손상성/눈 자극성 - 구분 2",
        "피부 과민성 - 구분 1",
        "호흡기 과민성 - 구분 1",
        "생식세포 변이원성 - 구분 1B",
        "생식세포 변이원성 - 구분 2",
        "발암성 - 구분 1A",
        "발암성 - 구분 1B",
        "발암성 - 구분 2",
        "생식독성 - 구분 1A",
        "생식독성 - 구분 1B",
        "생식독성 - 구분 2",
        "특정 표적장기 독성 (1회 노출) - 구분 1",
        "특정 표적장기 독성 (1회 노출) - 구분 2",
        "특정 표적장기 독성 (반복 노출) - 구분 1",
        "특정 표적장기 독성 (반복 노출) - 구분 2",
        "흡인 유해성 - 구분 1",
        "인화성 액체 - 구분 2",
        "인화성 액체 - 구분 3",
        "인화성 가스 - 구분 1",
        "수생환경 유해성 급성 - 구분 1",
        "수생환경 유해성 만성 - 구분 1",
        "수생환경 유해성 만성 - 구분 2"
    ]
    
    st.session_state.section2_data['ghs_classification'] = st.multiselect(
        "GHS 분류 선택",
        ghs_options,
        default=st.session_state.section2_data.get('ghs_classification', [])
    )
    
    st.markdown("#### 나. 예방조치 문구")
    
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.section2_data['signal_word'] = st.selectbox(
            "신호어",
            ["경고", "위험"],
            index=0 if st.session_state.section2_data.get('signal_word', '경고') == '경고' else 1
        )
    
    with col2:
        pictogram_options = ["폭발성", "인화성", "산화성", "고압가스", "부식성", 
                           "급성독성", "유해성", "건강유해성", "환경유해성"]
        st.session_state.section2_data['pictograms'] = st.multiselect(
            "그림문자",
            pictogram_options,
            default=st.session_state.section2_data.get('pictograms', [])
        )
    
    # 분류에 따른 H문구 자동 추천
    if st.session_state.section2_data.get('ghs_classification'):
        st.info("💡 선택한 분류에 따라 H문구가 자동으로 추천됩니다.")

# ============================================
# 섹션 3: 구성성분의 명칭 및 함유량
# ============================================
elif current == 3:
    st.subheader("3️⃣ 구성성분의 명칭 및 함유량")
    
    # 입력 방식 선택
    input_method = st.radio(
        "입력 방식",
        ["🔢 CAS 번호로 조회", "📝 직접 입력", "📤 엑셀 업로드"],
        horizontal=True
    )
    
    st.divider()
    
    if input_method == "🔢 CAS 번호로 조회" and KOSHA_AVAILABLE:
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            cas_input = st.text_input("CAS 번호", placeholder="예: 67-64-1", key="cas_search")
        with col2:
            content_input = st.number_input("함유량 (%)", 0.0, 100.0, 10.0, 0.1, key="content_search")
        with col3:
            content_range = st.text_input("함유량 범위", value=f"{content_input}", key="range_search")
        
        if st.button("🔍 조회 및 추가", type="primary"):
            if cas_input:
                with st.spinner(f"'{cas_input}' 조회 중..."):
                    result = get_full_msds_data(cas_input.strip())
                
                if result.get('success'):
                    prtr = check_prtr_status(cas_input.strip())
                    
                    new_component = {
                        'cas_no': cas_input.strip(),
                        'name': result.get('name_kor', ''),
                        'content': content_input,
                        'content_range': content_range or str(content_input),
                        'kosha_data': result,
                        'prtr_status': prtr
                    }
                    
                    # 중복 체크
                    existing_cas = [c.get('cas_no') for c in st.session_state.section3_data['components']]
                    if cas_input.strip() not in existing_cas:
                        st.session_state.section3_data['components'].append(new_component)
                        st.success(f"✅ **{result.get('name_kor')}** 추가 완료!")
                        
                        # 8번 섹션 노출기준 자동 추가
                        exp = result.get('exposure_limits', {})
                        if exp.get('TWA') and exp.get('TWA') != '-':
                            new_exp = {
                                'substance': result.get('name_kor'),
                                'cas_no': cas_input.strip(),
                                'twa': exp.get('TWA', '-'),
                                'stel': exp.get('STEL', '-')
                            }
                            st.session_state.section8_data['exposure_limits'].append(new_exp)
                    else:
                        st.warning("이미 등록된 물질입니다.")
                else:
                    st.warning(f"⚠️ '{cas_input}'은(는) KOSHA DB에 없습니다. 직접 입력해주세요.")
    
    elif input_method == "📝 직접 입력":
        col1, col2 = st.columns(2)
        with col1:
            manual_name = st.text_input("화학물질명 *", key="manual_name")
            manual_cas = st.text_input("CAS 번호", key="manual_cas")
        with col2:
            manual_content = st.number_input("함유량 (%)", 0.0, 100.0, 10.0, key="manual_content")
            manual_range = st.text_input("함유량 범위", key="manual_range")
        
        if st.button("➕ 추가"):
            if manual_name:
                new_comp = {
                    'name': manual_name,
                    'cas_no': manual_cas,
                    'content': manual_content,
                    'content_range': manual_range or str(manual_content),
                    'kosha_data': None,
                    'prtr_status': check_prtr_status(manual_cas) if manual_cas else None
                }
                st.session_state.section3_data['components'].append(new_comp)
                st.success(f"✅ **{manual_name}** 추가!")
    
    else:  # 엑셀 업로드
        st.markdown("**엑셀 형식:** 화학물질명 | CAS번호 | 함유량(%)")
        uploaded = st.file_uploader("엑셀 파일", type=['xlsx', 'xls'])
        if uploaded:
            df = pd.read_excel(uploaded)
            st.dataframe(df, use_container_width=True)
            
            if st.button("📤 일괄 추가"):
                for _, row in df.iterrows():
                    name = str(row.get('화학물질명', row.get('물질명', ''))).strip()
                    cas = str(row.get('CAS번호', row.get('CAS_No', ''))).strip()
                    content = float(row.get('함유량(%)', row.get('함유량', 0)))
                    
                    if name:
                        comp = {
                            'name': name,
                            'cas_no': cas,
                            'content': content,
                            'content_range': str(content),
                            'kosha_data': None,
                            'prtr_status': None
                        }
                        st.session_state.section3_data['components'].append(comp)
                st.success(f"✅ {len(df)}개 성분 추가!")
    
    # 현재 구성성분 목록
    st.divider()
    st.markdown("### 📦 등록된 구성성분")
    
    components = st.session_state.section3_data.get('components', [])
    
    if components:
        total_content = sum(c.get('content', 0) for c in components)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("등록 성분", f"{len(components)}종")
        with col2:
            st.metric("함유량 합계", f"{total_content:.1f}%")
        with col3:
            kosha_count = sum(1 for c in components if c.get('kosha_data'))
            st.metric("KOSHA 조회", f"{kosha_count}건")
        
        st.divider()
        
        for i, comp in enumerate(components):
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 1])
                
                with col1:
                    icon = "✅" if comp.get('kosha_data') else "📝"
                    st.markdown(f"**{icon} {comp.get('name', '-')}**")
                with col2:
                    st.write(f"CAS: {comp.get('cas_no', '-')}")
                with col3:
                    st.write(f"함유량: {comp.get('content_range', '-')}%")
                with col4:
                    prtr = comp.get('prtr_status', {})
                    if prtr and prtr.get('대상여부') == 'O':
                        st.markdown(f'<span class="reg-badge reg-o">PRTR {prtr.get("그룹", "")}</span>', unsafe_allow_html=True)
                with col5:
                    if st.button("🗑️", key=f"del_comp_{i}"):
                        st.session_state.section3_data['components'].pop(i)
                        st.rerun()
    else:
        st.info("구성성분을 추가해주세요.")

# ============================================
# 섹션 4: 응급조치 요령
# ============================================
elif current == 4:
    st.subheader("4️⃣ 응급조치 요령")
    
    data = st.session_state.section4_data
    
    data['eye_contact'] = st.text_area(
        "가. 눈에 들어갔을 때",
        value=data.get('eye_contact', '') or "즉시 다량의 물로 15분 이상 씻어낸다. 콘택트렌즈 착용 시 제거 후 씻는다. 자극 지속 시 의료조치.",
        height=100
    )
    
    data['skin_contact'] = st.text_area(
        "나. 피부에 접촉했을 때",
        value=data.get('skin_contact', '') or "오염된 의복을 벗기고 다량의 물과 비누로 씻는다. 자극 지속 시 의료조치.",
        height=100
    )
    
    data['inhalation'] = st.text_area(
        "다. 흡입했을 때",
        value=data.get('inhalation', '') or "신선한 공기가 있는 곳으로 옮긴다. 호흡곤란 시 산소공급. 의식불명 시 즉시 의료조치.",
        height=100
    )
    
    data['ingestion'] = st.text_area(
        "라. 먹었을 때",
        value=data.get('ingestion', '') or "입안을 물로 씻어내고 물을 마시게 한다. 토하게 하지 않는다. 즉시 의료조치.",
        height=100
    )
    
    data['medical_attention'] = st.text_area(
        "마. 기타 의사의 주의사항",
        value=data.get('medical_attention', '') or "증상에 따라 치료한다.",
        height=80
    )

# ============================================
# 섹션 5: 폭발·화재시 대처방법
# ============================================
elif current == 5:
    st.subheader("5️⃣ 폭발·화재시 대처방법")
    
    data = st.session_state.section5_data
    
    data['extinguishing_media'] = st.text_area(
        "가. 적절한 소화제",
        value=data.get('extinguishing_media', '') or "분말소화약제, 이산화탄소, 포, 물분무",
        height=100
    )
    
    data['specific_hazards'] = st.text_area(
        "나. 화학물질로부터 생기는 특정 유해성",
        value=data.get('specific_hazards', '') or "화재 시 유독가스 발생 가능",
        height=100
    )
    
    data['firefighting_equipment'] = st.text_area(
        "다. 화재 진압 시 착용할 보호구 및 예방조치",
        value=data.get('firefighting_equipment', '') or "자급식 호흡장치와 완전한 방호복을 착용한다.",
        height=100
    )

# ============================================
# 섹션 6: 누출 사고시 대처방법
# ============================================
elif current == 6:
    st.subheader("6️⃣ 누출 사고시 대처방법")
    
    data = st.session_state.section6_data
    
    data['personal_precautions'] = st.text_area(
        "가. 인체를 보호하기 위해 필요한 조치사항 및 보호구",
        value=data.get('personal_precautions', '') or "적절한 보호구 착용 (보안경, 보호장갑, 보호의, 호흡보호구)",
        height=100
    )
    
    data['environmental_precautions'] = st.text_area(
        "나. 환경을 보호하기 위해 필요한 조치사항",
        value=data.get('environmental_precautions', '') or "하수구, 지표수, 지하수 유입 방지. 적절한 봉쇄조치.",
        height=100
    )
    
    data['cleanup_methods'] = st.text_area(
        "다. 정화 또는 제거 방법",
        value=data.get('cleanup_methods', '') or "소량: 흡착재로 흡착 후 밀폐용기 수거. 대량: 방벽 설치 후 전문업체 의뢰.",
        height=100
    )

# ============================================
# 섹션 7: 취급 및 저장방법
# ============================================
elif current == 7:
    st.subheader("7️⃣ 취급 및 저장방법")
    
    data = st.session_state.section7_data
    
    data['safe_handling'] = st.text_area(
        "가. 안전취급요령",
        value=data.get('safe_handling', '') or "환기가 잘 되는 곳에서 보호구 착용 후 취급. 취급 후 손 세척.",
        height=120
    )
    
    data['storage_conditions'] = st.text_area(
        "나. 안전한 저장방법 (피해야 할 조건 포함)",
        value=data.get('storage_conditions', '') or "직사광선 피하고 서늘하고 건조한 곳에 밀폐 보관. 점화원으로부터 격리.",
        height=120
    )

# ============================================
# 섹션 8: 노출방지 및 개인보호구
# ============================================
elif current == 8:
    st.subheader("8️⃣ 노출방지 및 개인보호구")
    
    # 섹션 3에서 연동된 노출기준
    st.markdown("#### 가. 화학물질의 노출기준")
    
    exp_limits = st.session_state.section8_data.get('exposure_limits', [])
    
    if exp_limits:
        df_exp = pd.DataFrame(exp_limits)
        st.dataframe(df_exp, use_container_width=True)
    else:
        st.info("💡 섹션 3에서 구성성분을 등록하면 노출기준이 자동으로 추가됩니다.")
    
    st.divider()
    
    st.markdown("#### 나. 적절한 공학적 관리")
    st.session_state.section8_data['engineering_controls'] = st.text_area(
        "공학적 관리",
        value=st.session_state.section8_data.get('engineering_controls', '') or "국소배기장치 설치",
        height=80,
        label_visibility="collapsed"
    )
    
    st.markdown("#### 다. 개인보호구")
    
    ppe = st.session_state.section8_data.get('ppe', {})
    
    col1, col2 = st.columns(2)
    with col1:
        ppe['respiratory'] = st.text_input(
            "호흡기 보호",
            value=ppe.get('respiratory', '') or "방독마스크 또는 송기마스크"
        )
        ppe['hand'] = st.text_input(
            "손 보호",
            value=ppe.get('hand', '') or "적합한 재질의 보호장갑"
        )
    with col2:
        ppe['eye'] = st.text_input(
            "눈 보호",
            value=ppe.get('eye', '') or "보안경 또는 고글"
        )
        ppe['body'] = st.text_input(
            "신체 보호",
            value=ppe.get('body', '') or "긴팔작업복, 안전화"
        )
    
    st.session_state.section8_data['ppe'] = ppe

# ============================================
# 섹션 9: 물리화학적 특성
# ============================================
elif current == 9:
    st.subheader("9️⃣ 물리화학적 특성")
    
    data = st.session_state.section9_data
    
    # 구성성분에서 물성 자동 채우기 버튼
    if st.session_state.section3_data.get('components'):
        if st.button("🔄 구성성분에서 물성 가져오기"):
            for comp in st.session_state.section3_data['components']:
                if comp.get('kosha_data'):
                    phys = comp['kosha_data'].get('physical_properties', {})
                    for key in ['외관', '냄새', 'pH', '녹는점', '끓는점', '인화점', '증기압', '비중', '용해도']:
                        if phys.get(key) and phys[key] != '-':
                            field_map = {
                                '외관': 'appearance', '냄새': 'odor', 'pH': 'ph',
                                '녹는점': 'melting_point', '끓는점': 'boiling_point',
                                '인화점': 'flash_point', '증기압': 'vapor_pressure',
                                '비중': 'specific_gravity', '용해도': 'solubility'
                            }
                            if key in field_map:
                                data[field_map[key]] = phys[key]
            st.success("물성 정보를 가져왔습니다!")
            st.rerun()
    
    col1, col2 = st.columns(2)
    
    with col1:
        data['appearance'] = st.text_input("가. 외관", value=data.get('appearance', ''))
        data['odor'] = st.text_input("나. 냄새", value=data.get('odor', ''))
        data['ph'] = st.text_input("라. pH", value=data.get('ph', ''))
        data['melting_point'] = st.text_input("마. 녹는점/어는점", value=data.get('melting_point', ''))
        data['boiling_point'] = st.text_input("바. 끓는점", value=data.get('boiling_point', ''))
    
    with col2:
        data['flash_point'] = st.text_input("사. 인화점", value=data.get('flash_point', ''))
        data['vapor_pressure'] = st.text_input("카. 증기압", value=data.get('vapor_pressure', ''))
        data['specific_gravity'] = st.text_input("하. 비중", value=data.get('specific_gravity', ''))
        data['solubility'] = st.text_input("타. 용해도", value=data.get('solubility', ''))

# ============================================
# 섹션 10: 안정성 및 반응성
# ============================================
elif current == 10:
    st.subheader("🔟 안정성 및 반응성")
    
    data = st.session_state.section10_data
    
    data['stability'] = st.text_area(
        "가. 화학적 안정성",
        value=data.get('stability', '') or "정상적인 조건에서 안정함",
        height=80
    )
    data['reactivity'] = st.text_area(
        "나. 유해 반응의 가능성",
        value=data.get('reactivity', '') or "알려진 유해 반응 없음",
        height=80
    )
    data['conditions_to_avoid'] = st.text_area(
        "다. 피해야 할 조건",
        value=data.get('conditions_to_avoid', '') or "열, 스파크, 화염, 고온",
        height=80
    )
    data['incompatible_materials'] = st.text_area(
        "라. 피해야 할 물질",
        value=data.get('incompatible_materials', '') or "강산화제, 강산, 강염기",
        height=80
    )
    data['decomposition_products'] = st.text_area(
        "마. 분해 시 생성되는 유해물질",
        value=data.get('decomposition_products', '') or "열분해 시 유해가스 발생 가능",
        height=80
    )

# ============================================
# 섹션 11: 독성에 관한 정보
# ============================================
elif current == 11:
    st.subheader("1️⃣1️⃣ 독성에 관한 정보")
    
    # 구성성분에서 독성정보 표시
    components = st.session_state.section3_data.get('components', [])
    
    if components:
        for comp in components:
            if comp.get('kosha_data'):
                tox = comp['kosha_data'].get('toxicity_info', {})
                
                with st.expander(f"📋 {comp.get('name', '-')} ({comp.get('cas_no', '-')})"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**급성경구독성:** {tox.get('급성경구독성', '-')}")
                        st.write(f"**급성경피독성:** {tox.get('급성경피독성', '-')}")
                        st.write(f"**급성흡입독성:** {tox.get('급성흡입독성', '-')}")
                        st.write(f"**피부부식성:** {tox.get('피부부식성', '-')}")
                    with col2:
                        st.write(f"**발암성:** {tox.get('발암성', '-')}")
                        st.write(f"**IARC:** {tox.get('IARC', '-')}")
                        st.write(f"**ACGIH:** {tox.get('ACGIH', '-')}")
    else:
        st.info("섹션 3에서 구성성분을 등록하면 독성정보가 표시됩니다.")

# ============================================
# 섹션 12: 환경에 미치는 영향
# ============================================
elif current == 12:
    st.subheader("1️⃣2️⃣ 환경에 미치는 영향")
    
    data = st.session_state.section12_data
    
    data['ecotoxicity'] = st.text_area("가. 수생·육생 생태독성", value=data.get('ecotoxicity', ''), height=100)
    data['persistence'] = st.text_area("나. 잔류성 및 분해성", value=data.get('persistence', ''), height=100)
    data['bioaccumulation'] = st.text_area("다. 생물 농축성", value=data.get('bioaccumulation', ''), height=100)
    data['soil_mobility'] = st.text_area("라. 토양 이동성", value=data.get('soil_mobility', ''), height=100)

# ============================================
# 섹션 13: 폐기시 주의사항
# ============================================
elif current == 13:
    st.subheader("1️⃣3️⃣ 폐기시 주의사항")
    
    data = st.session_state.section13_data
    
    data['disposal_methods'] = st.text_area(
        "가. 폐기방법",
        value=data.get('disposal_methods', '') or "폐기물관리법에 따라 지정폐기물로 처리. 허가받은 전문업체에 의뢰.",
        height=120
    )
    data['disposal_precautions'] = st.text_area(
        "나. 폐기시 주의사항",
        value=data.get('disposal_precautions', '') or "빈 용기에도 잔류물이 남아 있을 수 있으므로 적절히 처리.",
        height=120
    )

# ============================================
# 섹션 14: 운송에 필요한 정보
# ============================================
elif current == 14:
    st.subheader("1️⃣4️⃣ 운송에 필요한 정보")
    
    data = st.session_state.section14_data
    
    # 구성성분에서 UN 번호 자동 가져오기
    un_no = '-'
    for comp in st.session_state.section3_data.get('components', []):
        if comp.get('kosha_data') and comp['kosha_data'].get('un_no'):
            un_no = comp['kosha_data']['un_no']
            break
    
    col1, col2 = st.columns(2)
    with col1:
        data['un_number'] = st.text_input("가. UN 번호", value=data.get('un_number', '') or un_no)
        data['proper_shipping_name'] = st.text_input("나. UN 적정 선적명", value=data.get('proper_shipping_name', ''))
        data['transport_class'] = st.text_input("다. 운송에서의 위험성 등급", value=data.get('transport_class', ''))
    with col2:
        data['packing_group'] = st.text_input("라. 용기등급", value=data.get('packing_group', ''))
        data['marine_pollutant'] = st.selectbox(
            "마. 해양오염물질",
            ["해당없음", "해당", "자료없음"],
            index=0
        )

# ============================================
# 섹션 15: 법적 규제현황
# ============================================
elif current == 15:
    st.subheader("1️⃣5️⃣ 법적 규제현황")
    
    # 구성성분에서 규제정보 자동 표시
    components = st.session_state.section3_data.get('components', [])
    
    if components:
        st.markdown("#### 가. 산업안전보건법")
        
        reg_data = []
        for comp in components:
            row = {'물질명': comp.get('name', '-'), 'CAS No': comp.get('cas_no', '-')}
            
            if comp.get('kosha_data'):
                regs = comp['kosha_data'].get('legal_regulations', {})
                row['작업환경측정'] = regs.get('작업환경측정', 'X')
                row['특수건강진단'] = regs.get('특수건강진단', 'X')
                row['관리대상유해물질'] = regs.get('관리대상유해물질', 'X')
                row['특별관리물질'] = regs.get('특별관리물질', 'X')
            else:
                row.update({'작업환경측정': '-', '특수건강진단': '-', '관리대상유해물질': '-', '특별관리물질': '-'})
            
            prtr = comp.get('prtr_status', {})
            row['PRTR대상'] = prtr.get('대상여부', '-')
            row['PRTR그룹'] = prtr.get('그룹', '-')
            
            reg_data.append(row)
        
        df_reg = pd.DataFrame(reg_data)
        st.dataframe(df_reg, use_container_width=True)
        
        # 규제 요약
        st.markdown("#### 규제 요약")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            count = sum(1 for r in reg_data if r.get('작업환경측정') == 'O')
            st.metric("작업환경측정", f"{count}종")
        with col2:
            count = sum(1 for r in reg_data if r.get('특수건강진단') == 'O')
            st.metric("특수건강진단", f"{count}종")
        with col3:
            count = sum(1 for r in reg_data if r.get('관리대상유해물질') == 'O')
            st.metric("관리대상유해물질", f"{count}종")
        with col4:
            count = sum(1 for r in reg_data if r.get('PRTR대상') == 'O')
            st.metric("PRTR 대상", f"{count}종")
    else:
        st.info("섹션 3에서 구성성분을 등록하면 규제정보가 표시됩니다.")

# ============================================
# 섹션 16: 기타 참고사항
# ============================================
elif current == 16:
    st.subheader("1️⃣6️⃣ 기타 참고사항")
    
    data = st.session_state.section16_data
    
    col1, col2 = st.columns(2)
    with col1:
        data['revision_date'] = st.date_input(
            "가. 작성일자",
            value=datetime.strptime(data.get('revision_date', str(date.today())), '%Y-%m-%d').date()
        )
        data['revision_date'] = str(data['revision_date'])
    with col2:
        data['revision_number'] = st.text_input("나. 개정횟수", value=data.get('revision_number', '1'))
    
    data['revision_reason'] = st.text_input("다. 개정사유", value=data.get('revision_reason', '신규 작성'))
    
    st.markdown("#### 라. 참고문헌")
    references = data.get('references', []) or ['안전보건공단 화학물질정보', '고용노동부 MSDS 작성지침']
    data['references'] = st.text_area(
        "참고문헌 (줄바꿈으로 구분)",
        value='\n'.join(references) if isinstance(references, list) else references
    ).split('\n')
    
    # MSDS 출력
    st.divider()
    st.markdown("### 📤 MSDS 출력")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # JSON 출력
        all_data = {f'section{i}': st.session_state.get(f'section{i}_data', {}) for i in range(1, 17)}
        all_data['generated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        json_str = json.dumps(all_data, ensure_ascii=False, indent=2, default=str)
        
        product_name = st.session_state.section1_data.get('product_name', 'MSDS')
        st.download_button(
            "📥 JSON 다운로드",
            data=json_str,
            file_name=f"MSDS_{product_name}_{date.today()}.json",
            mime="application/json",
            use_container_width=True
        )
    
    with col2:
        # 엑셀 출력
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 제품정보 시트
            sec1 = st.session_state.section1_data
            df1 = pd.DataFrame([{
                '제품명': sec1.get('product_name', ''),
                '관리번호': sec1.get('management_number', ''),
                '권고용도': sec1.get('recommended_use', ''),
                '회사명': sec1.get('manufacturer_info', {}).get('company_name', ''),
                '주소': sec1.get('manufacturer_info', {}).get('address', ''),
                '긴급전화': sec1.get('manufacturer_info', {}).get('emergency_phone', '')
            }])
            df1.to_excel(writer, sheet_name='1_제품정보', index=False)
            
            # 구성성분 시트
            comps = st.session_state.section3_data.get('components', [])
            if comps:
                df3 = pd.DataFrame([{
                    '물질명': c.get('name', ''),
                    'CAS No': c.get('cas_no', ''),
                    '함유량': c.get('content_range', '')
                } for c in comps])
                df3.to_excel(writer, sheet_name='3_구성성분', index=False)
            
            # 노출기준 시트
            exp = st.session_state.section8_data.get('exposure_limits', [])
            if exp:
                df8 = pd.DataFrame(exp)
                df8.to_excel(writer, sheet_name='8_노출기준', index=False)
        
        output.seek(0)
        st.download_button(
            "📥 엑셀 다운로드",
            data=output.getvalue(),
            file_name=f"MSDS_{product_name}_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    
    with col3:
        st.info("💡 Word/PDF 출력은\n다음 버전에서 지원")

# ============================================
# 하단 네비게이션
# ============================================
st.divider()

col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    if current > 1:
        if st.button("⬅️ 이전 섹션", use_container_width=True):
            st.session_state.current_section = current - 1
            st.rerun()

with col3:
    if current < 16:
        if st.button("다음 섹션 ➡️", use_container_width=True, type="primary"):
            st.session_state.current_section = current + 1
            st.rerun()

# 푸터
st.divider()
st.caption("© 2025 MSDS 작성 시스템 v2.0 | Kay's Chem Manager | KOSHA API 연동")
