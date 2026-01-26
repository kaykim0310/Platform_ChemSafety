#!/usr/bin/env python3
"""
📦 인벤토리 관리 시스템
- KOSHA API 연동
- 엑셀 업로드/다운로드
- 템플릿 서식 적용 (단위작업장소 포함)
"""
import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from datetime import date
import io

# 경로 설정
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))

# KOSHA API 모듈 import
try:
    from core.kosha_api import get_full_msds_data, search_by_cas
    from core.prtr_db import check_prtr_status
    KOSHA_AVAILABLE = True
except ImportError:
    KOSHA_AVAILABLE = False

# ============================================
# 페이지 설정
# ============================================
st.set_page_config(page_title="인벤토리 관리", page_icon="📦", layout="wide")

# ============================================
# 스타일
# ============================================
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1.5rem;
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        border-radius: 10px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .upload-box {
        border: 2px dashed #94a3b8;
        border-radius: 10px;
        padding: 2rem;
        text-align: center;
        background: #f8fafc;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# 세션 상태 초기화
# ============================================
if 'inventory' not in st.session_state:
    st.session_state.inventory = []

# ============================================
# 유틸리티 함수
# ============================================
def get_chemical_info(cas_no):
    """CAS 번호로 화학물질 정보 조회"""
    if not KOSHA_AVAILABLE:
        return None, "KOSHA 모듈 없음"
    try:
        result = get_full_msds_data(cas_no)
        if result.get('success'):
            return result, None
        else:
            return None, result.get('error', '조회 실패')
    except Exception as e:
        return None, f"API 오류: {str(e)[:50]}"

def extract_carcinogenicity(kosha_data):
    if not kosha_data:
        return "-"
    tox = kosha_data.get('toxicity_info', {})
    iarc = tox.get('IARC', '-')
    if 'Group 1' in str(iarc):
        return "1군(확인)"
    elif 'Group 2A' in str(iarc):
        return "2A군(추정)"
    elif 'Group 2B' in str(iarc):
        return "2B군(가능)"
    return "-"

def create_inventory_item(process_name, unit_workplace, product_name, chem_name, alias, cas_no, content, kosha_data=None, prtr_status=None):
    """인벤토리 항목 생성 (단위작업장소 포함)"""
    item = {
        '공정명': process_name or '',
        '단위작업장소': unit_workplace or '',
        '제품명': product_name or '',
        '화학물질명': chem_name or '',
        '관용명/이명': alias or '',
        'CAS No': cas_no or '',
        '함유량(%)': content or '',
        '발암성': '-', '변이성': '-', '생식독성': '-', '노출기준(TWA)': '-',
        '작업환경측정': 'X', '특수건강진단': 'X', '관리대상유해물질': 'X', '특별관리물질': 'X',
        '위험물류별': '-', '지정수량': '-', '위험등급': '-',
        '기존': '-', '유독': 'X', '사고대비': 'X', '제한/금지/허가': '-', 
        '중점': '-', '잔류': '-', '함량 및 규제정보': '-', '등록대상기존화학물질': '-', '기존물질여부': '-',
        'PRTR그룹': '-', 'PRTR기준량': '-'
    }
    
    if kosha_data:
        item['화학물질명'] = kosha_data.get('name_kor', chem_name) or chem_name
        item['발암성'] = extract_carcinogenicity(kosha_data)
        exp = kosha_data.get('exposure_limits', {})
        item['노출기준(TWA)'] = exp.get('TWA', '-')
        regs = kosha_data.get('legal_regulations', {})
        item['작업환경측정'] = regs.get('작업환경측정', 'X')
        item['특수건강진단'] = regs.get('특수건강진단', 'X')
        item['관리대상유해물질'] = regs.get('관리대상유해물질', 'X')
        item['특별관리물질'] = regs.get('특별관리물질', 'X')
    
    if prtr_status and prtr_status.get('대상여부') == 'O':
        item['PRTR그룹'] = prtr_status.get('그룹', '-')
        item['PRTR기준량'] = prtr_status.get('기준취급량', '-')
    
    return item

def create_template_excel():
    """템플릿 엑셀 파일 생성 (원본 템플릿과 동일한 구조)"""
    output = io.BytesIO()
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    
    wb = Workbook()
    ws = wb.active
    ws.title = "화학물질 정보"
    
    header_font = Font(bold=True, size=10)
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    header_fill = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
    header_fill2 = PatternFill(start_color="E0E7FF", end_color="E0E7FF", fill_type="solid")
    
    # 1행 헤더 (대분류)
    ws['A1'] = '공정명'
    ws['B1'] = '단위작업장소'
    ws['C1'] = '제품명'
    ws['D1'] = '화학물질명'
    ws['E1'] = '관용명/이명'
    ws['F1'] = 'CAS No'
    ws['G1'] = '함유량(%)'
    ws['H1'] = '독성정보'
    ws['L1'] = '법적규제 대상여부'
    ws['P1'] = '위험물'
    ws['S1'] = '환경부 법적규제 대상여부'
    
    # 2행 헤더 (세부항목)
    row2 = ['', '', '', '', '', '', '',
            '발암성', '변이성', '생식독성', '노출기준(TWA)',
            '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질',
            '위험물류별', '지정수량', '위험등급',
            '기존', '유독', '사고대비', '제한/금지/허가', '중점', '잔류', '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부']
    
    for col, h in enumerate(row2, 1):
        ws.cell(row=2, column=col, value=h)
    
    # 셀 병합 (1행~2행)
    for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G']:
        ws.merge_cells(f'{col}1:{col}2')
    
    ws.merge_cells('H1:K1')
    ws.merge_cells('L1:O1')
    ws.merge_cells('P1:R1')
    ws.merge_cells('S1:AA1')
    
    # 스타일 적용
    for row in [1, 2]:
        for col in range(1, 28):
            cell = ws.cell(row=row, column=col)
            cell.font, cell.alignment, cell.border = header_font, center_align, thin_border
            cell.fill = header_fill if row == 1 else header_fill2
    
    # 열 너비
    col_widths = {
        'A': 10, 'B': 12, 'C': 18, 'D': 18, 'E': 12, 'F': 12, 'G': 10,
        'H': 8, 'I': 8, 'J': 8, 'K': 12,
        'L': 10, 'M': 10, 'N': 12, 'O': 10,
        'P': 10, 'Q': 10, 'R': 8,
        'S': 6, 'T': 6, 'U': 8, 'V': 12, 'W': 6, 'X': 6, 'Y': 12, 'Z': 14
    }
    for col, width in col_widths.items():
        ws.column_dimensions[col].width = width
    
    wb.save(output)
    output.seek(0)
    return output

def export_inventory_to_excel(inventory_data):
    """인벤토리를 템플릿 형식으로 내보내기"""
    output = io.BytesIO()
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    
    wb = Workbook()
    ws = wb.active
    ws.title = "화학물질 정보"
    
    header_font = Font(bold=True, size=10)
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    header_fill = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
    header_fill2 = PatternFill(start_color="E0E7FF", end_color="E0E7FF", fill_type="solid")
    yes_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    
    # 1행 헤더
    ws['A1'] = '공정명'
    ws['B1'] = '단위작업장소'
    ws['C1'] = '제품명'
    ws['D1'] = '화학물질명'
    ws['E1'] = '관용명/이명'
    ws['F1'] = 'CAS No'
    ws['G1'] = '함유량(%)'
    ws['H1'] = '독성정보'
    ws['L1'] = '법적규제 대상여부'
    ws['P1'] = '위험물'
    ws['S1'] = '환경부 법적규제 대상여부'
    
    # 2행 헤더
    row2 = ['', '', '', '', '', '', '',
            '발암성', '변이성', '생식독성', '노출기준(TWA)',
            '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질',
            '위험물류별', '지정수량', '위험등급',
            '기존', '유독', '사고대비', '제한/금지/허가', '중점', '잔류', '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부']
    
    for col, h in enumerate(row2, 1):
        ws.cell(row=2, column=col, value=h)
    
    # 셀 병합
    for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G']:
        ws.merge_cells(f'{col}1:{col}2')
    ws.merge_cells('H1:K1')
    ws.merge_cells('L1:O1')
    ws.merge_cells('P1:R1')
    ws.merge_cells('S1:AA1')
    
    # 헤더 스타일
    for row in [1, 2]:
        for col in range(1, 28):
            cell = ws.cell(row=row, column=col)
            cell.font, cell.alignment, cell.border = header_font, center_align, thin_border
            cell.fill = header_fill if row == 1 else header_fill2
    
    # 데이터 입력
    for row_idx, item in enumerate(inventory_data, 3):
        data = [
            item.get('공정명', ''),
            item.get('단위작업장소', ''),
            item.get('제품명', ''),
            item.get('화학물질명', ''),
            item.get('관용명/이명', ''),
            item.get('CAS No', ''),
            item.get('함유량(%)', ''),
            item.get('발암성', '-'),
            item.get('변이성', '-'),
            item.get('생식독성', '-'),
            item.get('노출기준(TWA)', '-'),
            item.get('작업환경측정', 'X'),
            item.get('특수건강진단', 'X'),
            item.get('관리대상유해물질', 'X'),
            item.get('특별관리물질', 'X'),
            item.get('위험물류별', '-'),
            item.get('지정수량', '-'),
            item.get('위험등급', '-'),
            item.get('기존', '-'),
            item.get('유독', 'X'),
            item.get('사고대비', 'X'),
            item.get('제한/금지/허가', '-'),
            item.get('중점', '-'),
            item.get('잔류', '-'),
            item.get('함량 및 규제정보', '-'),
            item.get('등록대상기존화학물질', '-'),
            item.get('기존물질여부', '-'),
        ]
        
        for col_idx, val in enumerate(data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.alignment, cell.border = center_align, thin_border
            if val == 'O':
                cell.fill = yes_fill
    
    # 열 너비
    col_widths = {
        'A': 10, 'B': 12, 'C': 18, 'D': 18, 'E': 12, 'F': 12, 'G': 10,
        'H': 8, 'I': 8, 'J': 8, 'K': 12,
        'L': 10, 'M': 10, 'N': 12, 'O': 10,
        'P': 10, 'Q': 10, 'R': 8,
        'S': 6, 'T': 6, 'U': 8, 'V': 12, 'W': 6, 'X': 6, 'Y': 12, 'Z': 14
    }
    for col, width in col_widths.items():
        ws.column_dimensions[col].width = width
    
    wb.save(output)
    output.seek(0)
    return output

# ============================================
# 사이드바
# ============================================
with st.sidebar:
    st.markdown("### 📦 인벤토리 관리")
    st.metric("등록된 물질", f"{len(st.session_state.inventory)}종")
    
    if len(st.session_state.inventory) > 0:
        cnt = sum(1 for i in st.session_state.inventory if i.get('작업환경측정') == 'O')
        st.metric("측정대상", f"{cnt}종")
    
    st.divider()
    st.markdown("#### 📥 템플릿")
    template_data = create_template_excel()
    st.download_button("📄 빈 템플릿 다운로드", data=template_data.getvalue(), 
                      file_name=f"인벤토리_템플릿_{date.today()}.xlsx", 
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                      use_container_width=True)
    
    st.divider()
    if st.button("🗑️ 전체 삭제", use_container_width=True):
        st.session_state.inventory = []
        st.rerun()

# ============================================
# 메인
# ============================================
st.markdown("""
<div class="main-header">
    <h2>📦 화학물질 인벤토리 관리</h2>
    <p>엑셀 업로드 또는 CAS 번호 입력 → 규제정보 자동 조회</p>
</div>
""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["📤 엑셀 업로드", "➕ 개별 등록", "📋 목록 보기", "📥 내보내기"])

# ============================================
# 탭 1: 엑셀 업로드
# ============================================
with tab1:
    st.subheader("📤 엑셀 파일 업로드")
    
    st.markdown("""
    <div class="upload-box">
        <h4>📁 엑셀 파일을 업로드하세요</h4>
        <p>템플릿 형식 또는 CAS 번호가 포함된 엑셀</p>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("엑셀 파일 선택", type=['xlsx', 'xls'])
    
    if uploaded_file:
        st.success(f"✅ **{uploaded_file.name}** 업로드됨")
        
        try:
            # 2행 헤더 구조 처리: 1행=헤더, 2행=세부헤더(스킵)
            df = pd.read_excel(uploaded_file, header=0, skiprows=[1])
            df = df.dropna(how='all')
            
            with st.expander("📊 미리보기", expanded=True):
                st.dataframe(df.head(10), use_container_width=True)
                st.caption(f"총 {len(df)}행")
            
            st.divider()
            
            # 컬럼 매핑
            col1, col2 = st.columns(2)
            with col1:
                cas_candidates = [c for c in df.columns if 'cas' in c.lower() or 'CAS' in c]
                cas_col = st.selectbox("CAS 번호 컬럼", cas_candidates if cas_candidates else list(df.columns))
                name_col = st.selectbox("화학물질명 컬럼", ['(자동조회)'] + list(df.columns))
            with col2:
                process_col = st.selectbox("공정명 컬럼", ['(없음)'] + list(df.columns))
                unit_col = st.selectbox("단위작업장소 컬럼", ['(없음)'] + list(df.columns))
                product_col = st.selectbox("제품명 컬럼", ['(없음)'] + list(df.columns))
                content_col = st.selectbox("함유량 컬럼", ['(없음)'] + list(df.columns))
            
            auto_query = st.checkbox("✅ KOSHA API 자동 조회 (권장)", value=True)
            
            st.divider()
            
            if st.button("🚀 일괄 등록", type="primary", use_container_width=True):
                progress = st.progress(0)
                status = st.empty()
                
                success, skip = 0, 0
                existing_cas = [i['CAS No'] for i in st.session_state.inventory]
                
                for idx, row in df.iterrows():
                    cas = str(row.get(cas_col, '')).strip()
                    if not cas or cas == 'nan' or cas in existing_cas:
                        skip += 1
                        continue
                    
                    chem_name = str(row.get(name_col, '')) if name_col != '(자동조회)' else ''
                    process = str(row.get(process_col, '')) if process_col != '(없음)' else ''
                    unit_wp = str(row.get(unit_col, '')) if unit_col != '(없음)' else ''
                    product = str(row.get(product_col, '')) if product_col != '(없음)' else ''
                    content = str(row.get(content_col, '')) if content_col != '(없음)' else ''
                    
                    # nan 처리
                    chem_name = '' if chem_name == 'nan' else chem_name
                    process = '' if process == 'nan' else process
                    unit_wp = '' if unit_wp == 'nan' else unit_wp
                    product = '' if product == 'nan' else product
                    content = '' if content == 'nan' else content
                    
                    kosha_data, prtr_status = None, None
                    if auto_query and KOSHA_AVAILABLE:
                        status.text(f"조회 중: {cas}...")
                        kosha_data, _ = get_chemical_info(cas)
                        prtr_status = check_prtr_status(cas)
                    
                    item = create_inventory_item(process, unit_wp, product, chem_name, '', cas, content, kosha_data, prtr_status)
                    st.session_state.inventory.append(item)
                    existing_cas.append(cas)
                    success += 1
                    progress.progress((idx + 1) / len(df))
                
                status.empty()
                progress.empty()
                st.success(f"✅ 등록 완료! 성공: {success}건, 건너뜀: {skip}건")
                st.rerun()
        
        except Exception as e:
            st.error(f"❌ 파일 읽기 오류: {e}")

# ============================================
# 탭 2: 개별 등록
# ============================================
with tab2:
    st.subheader("➕ 개별 등록")
    
    col1, col2 = st.columns(2)
    with col1:
        process = st.text_input("공정명", placeholder="예: 세정공정")
        unit_wp = st.text_input("단위작업장소", placeholder="예: 1라인")
        product = st.text_input("제품명", placeholder="예: 산업용 세정제")
        cas = st.text_input("CAS 번호 *", placeholder="예: 67-64-1")
    with col2:
        content = st.text_input("함유량(%)", placeholder="예: 50")
        alias = st.text_input("관용명", placeholder="예: 아세톤")
        st.info("💡 CAS 번호 입력 → KOSHA API 자동 조회")
    
    if st.button("🔍 조회 및 등록", type="primary", use_container_width=True):
        if cas:
            with st.spinner("조회 중..."):
                kosha_data, err = get_chemical_info(cas.strip())
                prtr_status = check_prtr_status(cas.strip()) if KOSHA_AVAILABLE else None
            
            if kosha_data:
                item = create_inventory_item(process, unit_wp, product, kosha_data.get('name_kor',''), alias, cas.strip(), content, kosha_data, prtr_status)
                if cas.strip() not in [i['CAS No'] for i in st.session_state.inventory]:
                    st.session_state.inventory.append(item)
                    st.success(f"✅ {item['화학물질명']} 등록!")
                    st.rerun()
                else:
                    st.warning("이미 등록된 물질")
            else:
                st.error(f"❌ {err}")
        else:
            st.warning("CAS 번호 입력 필요")

# ============================================
# 탭 3: 목록
# ============================================
with tab3:
    st.subheader("📋 인벤토리 목록")
    
    if st.session_state.inventory:
        col1, col2 = st.columns(2)
        with col1:
            f1 = st.checkbox("작업환경측정 대상만")
        with col2:
            f2 = st.checkbox("특수건강진단 대상만")
        
        filtered = st.session_state.inventory.copy()
        if f1:
            filtered = [i for i in filtered if i.get('작업환경측정') == 'O']
        if f2:
            filtered = [i for i in filtered if i.get('특수건강진단') == 'O']
        
        if filtered:
            display_cols = ['공정명', '단위작업장소', '제품명', 'CAS No', '화학물질명', '노출기준(TWA)', 
                          '작업환경측정', '특수건강진단', '관리대상유해물질', '발암성']
            df = pd.DataFrame(filtered)
            available_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available_cols], use_container_width=True, height=400)
            
            st.divider()
            col1, col2 = st.columns([3, 1])
            with col1:
                del_idx = st.selectbox("삭제할 물질", range(len(st.session_state.inventory)), 
                                       format_func=lambda x: f"{st.session_state.inventory[x]['CAS No']} - {st.session_state.inventory[x]['화학물질명']}")
            with col2:
                if st.button("🗑️ 삭제"):
                    st.session_state.inventory.pop(del_idx)
                    st.rerun()
    else:
        st.info("등록된 물질 없음")

# ============================================
# 탭 4: 내보내기
# ============================================
with tab4:
    st.subheader("📥 내보내기")
    
    if st.session_state.inventory:
        col1, col2 = st.columns(2)
        with col1:
            excel = export_inventory_to_excel(st.session_state.inventory)
            st.download_button("📊 엑셀 다운로드", data=excel.getvalue(), 
                              file_name=f"인벤토리_{date.today()}.xlsx", 
                              mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                              use_container_width=True)
        with col2:
            csv = pd.DataFrame(st.session_state.inventory).to_csv(index=False, encoding='utf-8-sig')
            st.download_button("📄 CSV 다운로드", data=csv, 
                              file_name=f"인벤토리_{date.today()}.csv", 
                              mime="text/csv", use_container_width=True)
        
        st.divider()
        st.markdown("#### 📈 통계")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("작업환경측정", f"{sum(1 for i in st.session_state.inventory if i.get('작업환경측정')=='O')}종")
        c2.metric("특수건강진단", f"{sum(1 for i in st.session_state.inventory if i.get('특수건강진단')=='O')}종")
        c3.metric("관리대상유해물질", f"{sum(1 for i in st.session_state.inventory if i.get('관리대상유해물질')=='O')}종")
        c4.metric("발암성물질", f"{sum(1 for i in st.session_state.inventory if i.get('발암성') not in ['-',''])}종")
    else:
        st.info("내보낼 데이터 없음")

st.divider()
st.caption("© 2025 Kay's Chem Manager | KOSHA API 연동")
