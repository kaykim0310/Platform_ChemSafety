#!/usr/bin/env python3
"""
MSDS Writer Page (MSDS 작성 페이지)
- Fixed version without exec()
- English filename to avoid encoding issues
"""
import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from datetime import date, datetime
import json
import io

# 경로 설정
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))

# 모듈 import
try:
    from core.kosha_api import get_full_msds_data, search_by_cas
    from core.prtr_db import check_prtr_status
    KOSHA_AVAILABLE = True
except ImportError as e:
    KOSHA_AVAILABLE = False

# ============================================
# 페이지 설정
# ============================================
st.set_page_config(
    page_title="MSDS 작성",
    page_icon="📋",
    layout="wide"
)

# ============================================
# 스타일
# ============================================
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1.5rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .kosha-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        background: #dcfce7;
        color: #166534;
        border-radius: 1rem;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .reg-badge-o { 
        display: inline-block;
        padding: 0.2rem 0.5rem;
        background: #fee2e2; 
        color: #991b1b; 
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# 세션 상태 초기화
# ============================================
if 'section1_data' not in st.session_state:
    st.session_state.section1_data = {
        'product_name': '',
        'management_number': '',
        'recommended_use': '공업용',
        'manufacturer_info': {
            'company_name': '',
            'address': '',
            'phone': '',
            'emergency_phone': '119'
        }
    }

if 'section3_data' not in st.session_state:
    st.session_state.section3_data = {'components': []}

if 'section8_data' not in st.session_state:
    st.session_state.section8_data = {
        'exposure_limits': [],
        'ppe': {'respiratory': '', 'eye': '', 'hand': '', 'body': ''}
    }

if 'current_section' not in st.session_state:
    st.session_state.current_section = 1

# ============================================
# 사이드바
# ============================================
with st.sidebar:
    st.markdown("### 📋 MSDS 작성")
    
    if KOSHA_AVAILABLE:
        st.markdown('<span class="kosha-badge">✅ KOSHA API 연결됨</span>', unsafe_allow_html=True)
    else:
        st.error("❌ KOSHA API 연결 실패")
    
    st.divider()
    
    # 제품 정보
    product_name = st.session_state.section1_data.get('product_name', '')
    if product_name:
        st.info(f"📦 **{product_name}**")
    
    # 구성성분 수
    comp_count = len(st.session_state.section3_data.get('components', []))
    st.caption(f"등록된 구성성분: {comp_count}종")
    
    st.divider()
    
    # 섹션 선택
    st.markdown("#### 📑 섹션 선택")
    section_names = [
        "1. 제품/회사 정보",
        "2. 유해성/위험성",
        "3. 구성성분 ⭐",
        "4. 응급조치",
        "5. 화재시 대처",
        "6. 누출시 대처",
        "7. 취급/저장",
        "8. 노출방지/보호구",
        "9. 물리화학적 특성",
        "10. 안정성/반응성",
        "11. 독성정보",
        "12. 환경영향",
        "13. 폐기 주의사항",
        "14. 운송정보",
        "15. 법적 규제 ⭐",
        "16. 출력 📤"
    ]
    
    selected = st.radio(
        "섹션",
        range(1, 17),
        format_func=lambda x: section_names[x-1],
        index=st.session_state.current_section - 1,
        label_visibility="collapsed"
    )
    st.session_state.current_section = selected
    
    st.divider()
    
    if st.button("🔄 전체 초기화", use_container_width=True):
        st.session_state.section1_data = {
            'product_name': '', 'management_number': '', 'recommended_use': '공업용',
            'manufacturer_info': {'company_name': '', 'address': '', 'phone': '', 'emergency_phone': '119'}
        }
        st.session_state.section3_data = {'components': []}
        st.session_state.section8_data = {'exposure_limits': [], 'ppe': {}}
        st.rerun()

# ============================================
# 메인 컨텐츠
# ============================================
current = st.session_state.current_section

# 헤더
st.markdown(f"""
<div class="main-header">
    <h2>📋 물질안전보건자료 (MSDS) 작성</h2>
    <p>섹션 {current}. {section_names[current-1].split('. ')[1].replace(' ⭐', '').replace(' 📤', '')}</p>
</div>
""", unsafe_allow_html=True)

# ============================================
# 섹션 1: 제품/회사 정보
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
            value=st.session_state.section1_data.get('recommended_use', '공업용')
        )
    
    with col2:
        st.markdown("#### 나. 공급자 정보")
        mfr = st.session_state.section1_data.get('manufacturer_info', {})
        mfr['company_name'] = st.text_input("회사명", value=mfr.get('company_name', ''))
        mfr['address'] = st.text_input("주소", value=mfr.get('address', ''))
        mfr['phone'] = st.text_input("전화번호", value=mfr.get('phone', ''))
        mfr['emergency_phone'] = st.text_input("긴급전화", value=mfr.get('emergency_phone', '119'))
        st.session_state.section1_data['manufacturer_info'] = mfr
    
    if st.session_state.section1_data.get('product_name'):
        st.success("✅ 제품명 입력 완료! → 섹션 3에서 구성성분을 등록하세요.")

# ============================================
# 섹션 3: 구성성분 (핵심!)
# ============================================
elif current == 3:
    st.subheader("3️⃣ 구성성분의 명칭 및 함유량")
    
    # 입력 방식
    input_method = st.radio(
        "입력 방식",
        ["🔢 CAS 번호로 조회 (추천)", "📝 직접 입력"],
        horizontal=True
    )
    
    st.divider()
    
    if "CAS" in input_method and KOSHA_AVAILABLE:
        st.markdown("#### CAS 번호 입력")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            cas_input = st.text_input("CAS 번호", placeholder="예: 67-64-1", key="cas_input")
        with col2:
            content_input = st.number_input("함유량 (%)", 0.0, 100.0, 10.0, 0.1)
        with col3:
            content_range = st.text_input("함유량 범위", placeholder="예: 5~15")
        
        if st.button("🔍 KOSHA 조회 및 추가", type="primary", use_container_width=True):
            if cas_input:
                with st.spinner(f"'{cas_input}' 조회 중..."):
                    result = get_full_msds_data(cas_input.strip())
                
                if result.get('success'):
                    prtr = check_prtr_status(cas_input.strip())
                    
                    new_comp = {
                        'cas_no': cas_input.strip(),
                        'name': result.get('name_kor', ''),
                        'content': content_input,
                        'content_range': content_range or str(content_input),
                        'kosha_data': result,
                        'prtr_status': prtr
                    }
                    
                    existing = [c.get('cas_no') for c in st.session_state.section3_data['components']]
                    if cas_input.strip() not in existing:
                        st.session_state.section3_data['components'].append(new_comp)
                        
                        # 노출기준 자동 추가
                        exp = result.get('exposure_limits', {})
                        if exp.get('TWA') and exp.get('TWA') != '-':
                            st.session_state.section8_data['exposure_limits'].append({
                                'substance': result.get('name_kor'),
                                'cas_no': cas_input.strip(),
                                'twa': exp.get('TWA', '-'),
                                'stel': exp.get('STEL', '-')
                            })
                        
                        st.success(f"✅ **{result.get('name_kor')}** 추가 완료!")
                        st.rerun()
                    else:
                        st.warning("⚠️ 이미 등록된 물질입니다.")
                else:
                    st.error(f"❌ '{cas_input}'은(는) KOSHA DB에 없습니다.")
            else:
                st.warning("CAS 번호를 입력하세요.")
    
    elif "직접" in input_method:
        col1, col2 = st.columns(2)
        with col1:
            manual_name = st.text_input("화학물질명 *")
            manual_cas = st.text_input("CAS 번호")
        with col2:
            manual_content = st.number_input("함유량 (%)", 0.0, 100.0, 10.0, key="manual_content")
            manual_range = st.text_input("함유량 범위")
        
        if st.button("➕ 추가", use_container_width=True):
            if manual_name:
                st.session_state.section3_data['components'].append({
                    'name': manual_name,
                    'cas_no': manual_cas,
                    'content': manual_content,
                    'content_range': manual_range or str(manual_content),
                    'kosha_data': None,
                    'prtr_status': check_prtr_status(manual_cas) if manual_cas else None
                })
                st.success(f"✅ **{manual_name}** 추가!")
                st.rerun()
    else:
        st.error("❌ KOSHA API 연결 실패. 직접 입력을 사용하세요.")
    
    # 등록된 구성성분
    st.divider()
    st.markdown("### 📦 등록된 구성성분")
    
    components = st.session_state.section3_data.get('components', [])
    
    if components:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("등록 성분", f"{len(components)}종")
        with col2:
            total = sum(c.get('content', 0) for c in components)
            st.metric("함유량 합계", f"{total:.1f}%")
        with col3:
            kosha = sum(1 for c in components if c.get('kosha_data'))
            st.metric("KOSHA 조회", f"{kosha}건")
        
        st.divider()
        
        for i, comp in enumerate(components):
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
                    st.markdown(f'<span class="reg-badge-o">PRTR {prtr.get("그룹", "")}</span>', unsafe_allow_html=True)
            with col5:
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state.section3_data['components'].pop(i)
                    st.rerun()
    else:
        st.info("💡 CAS 번호를 입력하고 [KOSHA 조회 및 추가] 버튼을 클릭하세요!")
        st.markdown("""
        **테스트용 CAS 번호:**
        - `67-64-1` → 아세톤
        - `108-88-3` → 톨루엔
        - `1330-20-7` → 크실렌
        - `71-43-2` → 벤젠
        """)

# ============================================
# 섹션 8: 노출방지
# ============================================
elif current == 8:
    st.subheader("8️⃣ 노출방지 및 개인보호구")
    
    st.markdown("#### 가. 노출기준")
    exp = st.session_state.section8_data.get('exposure_limits', [])
    if exp:
        st.dataframe(pd.DataFrame(exp), use_container_width=True)
    else:
        st.info("💡 섹션 3에서 구성성분을 등록하면 노출기준이 자동 추가됩니다.")
    
    st.divider()
    st.markdown("#### 나. 개인보호구")
    
    ppe = st.session_state.section8_data.get('ppe', {})
    col1, col2 = st.columns(2)
    with col1:
        ppe['respiratory'] = st.text_input("호흡기 보호", value=ppe.get('respiratory', '방독마스크'))
        ppe['hand'] = st.text_input("손 보호", value=ppe.get('hand', '보호장갑'))
    with col2:
        ppe['eye'] = st.text_input("눈 보호", value=ppe.get('eye', '보안경'))
        ppe['body'] = st.text_input("신체 보호", value=ppe.get('body', '작업복, 안전화'))
    st.session_state.section8_data['ppe'] = ppe

# ============================================
# 섹션 15: 법적 규제
# ============================================
elif current == 15:
    st.subheader("1️⃣5️⃣ 법적 규제현황")
    
    components = st.session_state.section3_data.get('components', [])
    
    if components:
        reg_data = []
        for comp in components:
            row = {'물질명': comp.get('name', '-'), 'CAS No': comp.get('cas_no', '-')}
            
            if comp.get('kosha_data'):
                regs = comp['kosha_data'].get('legal_regulations', {})
                row['작업환경측정'] = regs.get('작업환경측정', 'X')
                row['특수건강진단'] = regs.get('특수건강진단', 'X')
                row['관리대상유해물질'] = regs.get('관리대상유해물질', 'X')
            else:
                row.update({'작업환경측정': '-', '특수건강진단': '-', '관리대상유해물질': '-'})
            
            prtr = comp.get('prtr_status', {})
            row['PRTR대상'] = prtr.get('대상여부', '-')
            row['PRTR그룹'] = prtr.get('그룹', '-')
            
            reg_data.append(row)
        
        st.dataframe(pd.DataFrame(reg_data), use_container_width=True)
        
        # 요약
        st.markdown("#### 📊 요약")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            cnt = sum(1 for r in reg_data if r.get('작업환경측정') == 'O')
            st.metric("작업환경측정", f"{cnt}종")
        with col2:
            cnt = sum(1 for r in reg_data if r.get('특수건강진단') == 'O')
            st.metric("특수건강진단", f"{cnt}종")
        with col3:
            cnt = sum(1 for r in reg_data if r.get('관리대상유해물질') == 'O')
            st.metric("관리대상유해물질", f"{cnt}종")
        with col4:
            cnt = sum(1 for r in reg_data if r.get('PRTR대상') == 'O')
            st.metric("PRTR대상", f"{cnt}종")
    else:
        st.info("💡 섹션 3에서 구성성분을 등록하세요.")

# ============================================
# 섹션 16: 출력
# ============================================
elif current == 16:
    st.subheader("1️⃣6️⃣ MSDS 출력")
    
    col1, col2 = st.columns(2)
    with col1:
        revision_date = st.date_input("작성일자", value=date.today())
    with col2:
        revision_number = st.text_input("개정횟수", value="1")
    
    st.divider()
    st.markdown("### 📤 다운로드")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # JSON
        all_data = {
            'section1': st.session_state.section1_data,
            'section3': st.session_state.section3_data,
            'section8': st.session_state.section8_data,
            'revision_date': str(revision_date),
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        json_str = json.dumps(all_data, ensure_ascii=False, indent=2, default=str)
        
        pname = st.session_state.section1_data.get('product_name', 'MSDS')
        st.download_button(
            "📥 JSON 다운로드",
            data=json_str,
            file_name=f"MSDS_{pname}_{date.today()}.json",
            mime="application/json",
            use_container_width=True
        )
    
    with col2:
        # Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            sec1 = st.session_state.section1_data
            df1 = pd.DataFrame([{
                '제품명': sec1.get('product_name', ''),
                '회사명': sec1.get('manufacturer_info', {}).get('company_name', ''),
                '긴급전화': sec1.get('manufacturer_info', {}).get('emergency_phone', '')
            }])
            df1.to_excel(writer, sheet_name='1_제품정보', index=False)
            
            comps = st.session_state.section3_data.get('components', [])
            if comps:
                df3 = pd.DataFrame([{
                    '물질명': c.get('name', ''),
                    'CAS No': c.get('cas_no', ''),
                    '함유량': c.get('content_range', '')
                } for c in comps])
                df3.to_excel(writer, sheet_name='3_구성성분', index=False)
        
        output.seek(0)
        st.download_button(
            "📥 엑셀 다운로드",
            data=output.getvalue(),
            file_name=f"MSDS_{pname}_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

# ============================================
# 기타 섹션
# ============================================
else:
    st.info(f"📝 섹션 {current}은 개발 중입니다.")
    st.markdown("""
    **주요 섹션:**
    - 섹션 1: 제품/회사 정보
    - 섹션 3 ⭐: 구성성분 등록 (KOSHA API)
    - 섹션 8: 노출기준, 보호구
    - 섹션 15 ⭐: 법적 규제현황
    - 섹션 16: 출력
    """)

# ============================================
# 하단 네비게이션
# ============================================
st.divider()

col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    if current > 1:
        if st.button("⬅️ 이전", use_container_width=True):
            st.session_state.current_section = current - 1
            st.rerun()

with col3:
    if current < 16:
        if st.button("다음 ➡️", use_container_width=True, type="primary"):
            st.session_state.current_section = current + 1
            st.rerun()

st.divider()
st.caption("© 2025 MSDS 작성 시스템 | Kay's Chem Manager")
