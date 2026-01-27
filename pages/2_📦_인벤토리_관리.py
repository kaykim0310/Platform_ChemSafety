#!/usr/bin/env python3
"""
📦 인벤토리 관리 시스템
- KOSHA API 연동 (8번: 노출기준, 15번: 법적규제+위험물)
- 엑셀 업로드/다운로드
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

# 모듈 import
try:
    from core.kosha_api import get_chemical_info
    from core.prtr_db import check_prtr_status
    KOSHA_AVAILABLE = True
except ImportError:
    KOSHA_AVAILABLE = False

try:
    from core.keco_api import get_chemical_regulations
    KECO_AVAILABLE = True
except ImportError:
    KECO_AVAILABLE = False

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
# 세션 상태
# ============================================
if 'inventory' not in st.session_state:
    st.session_state.inventory = []

# ============================================
# 유틸리티 함수
# ============================================
def query_chemical_info(cas_no):
    """CAS 번호로 화학물질 정보 조회 (KOSHA API)"""
    if not KOSHA_AVAILABLE:
        return None, "KOSHA 모듈 없음"
    try:
        result = get_chemical_info(cas_no)
        if result.get('success'):
            return result, None
        else:
            return None, result.get('error', '조회 실패')
    except Exception as e:
        return None, f"API 오류: {str(e)[:50]}"

def create_inventory_item(process_name, unit_workplace, product_name, chem_name, alias, cas_no, content, kosha_data=None, keco_data=None, prtr_status=None):
    """인벤토리 항목 생성 - KOSHA API + KECO API 연동"""
    item = {
        '공정명': process_name or '',
        '단위작업장소': unit_workplace or '',
        '제품명': product_name or '',
        '화학물질명': chem_name or '',
        '관용명/이명': alias or '',
        'CAS No': cas_no or '',
        '함유량(%)': content or '',
        # 독성정보
        '발암성': '-', '변이성': '-', '생식독성': '-', '노출기준(TWA)': '-',
        # 산안법 규제 (KOSHA)
        '작업환경측정': 'X', '특수건강진단': 'X', '관리대상유해물질': 'X', '특별관리물질': 'X',
        # 위험물 (KOSHA 15번)
        '위험물류별': '-', '지정수량': '-', '위험등급': '-',
        # 환경부 규제 (KECO)
        '기존': '-', '급성·만성·생태': 'X', '사고대비': 'X', '제한/금지/허가': '-',
        '중점': '-', '잔류': '-', '함량 및 규제정보': '-', '등록대상기존화학물질': '-', '기존물질여부': '-',
        # PRTR
        'PRTR그룹': '-', 'PRTR기준량': '-'
    }
    
    # ========== KOSHA API 데이터 (고용노동부) ==========
    if kosha_data:
        # 물질명
        item['화학물질명'] = kosha_data.get('name', chem_name) or chem_name
        
        # 8번 항목: 노출기준
        item['노출기준(TWA)'] = kosha_data.get('twa', '-')
        
        # 15번 항목: 산안법 규제
        item['작업환경측정'] = kosha_data.get('measurement', 'X')
        item['특수건강진단'] = kosha_data.get('healthCheck', 'X')
        item['관리대상유해물질'] = kosha_data.get('managedHazard', 'X')
        item['특별관리물질'] = kosha_data.get('specialManaged', 'X')
        
        # 15번 항목: 위험물안전관리법
        hazmat_class = kosha_data.get('hazmatClass', '-')
        hazmat_name = kosha_data.get('hazmatName', '-')
        if hazmat_class != '-' and hazmat_name != '-':
            item['위험물류별'] = f"{hazmat_class} {hazmat_name}"
        elif hazmat_class != '-':
            item['위험물류별'] = hazmat_class
        item['지정수량'] = kosha_data.get('hazmatQty', '-')
        item['위험등급'] = kosha_data.get('hazmatGrade', '-')
    
    # ========== KECO API 데이터 (환경부) ==========
    if keco_data and keco_data.get('success'):
        # 기존화학물질
        existing = keco_data.get('기존화학물질', '-')
        if existing and existing != '-':
            item['기존'] = 'O'
            item['기존물질여부'] = 'O'
        
        # 급성·만성·생태 (유독물질 또는 인체유해성물질)
        toxic = keco_data.get('유독물질', '-')
        human_hazard = keco_data.get('인체유해성물질', '-')
        if toxic and toxic != '-':
            item['급성·만성·생태'] = toxic  # "O(1%이상)" 형태
        elif human_hazard and human_hazard != '-':
            item['급성·만성·생태'] = human_hazard  # "O(급성1%/만성0.1%)" 형태
        
        # 사고대비물질
        accident = keco_data.get('사고대비물질', '-')
        if accident and accident != '-':
            item['사고대비'] = accident
        
        # 제한/금지/허가
        restricted = keco_data.get('제한물질', '-')
        prohibited = keco_data.get('금지물질', '-')
        permitted = keco_data.get('허가물질', '-')
        reg_list = []
        if restricted and restricted != '-':
            reg_list.append(f"제한{restricted.replace('O', '')}")
        if prohibited and prohibited != '-':
            reg_list.append(f"금지{prohibited.replace('O', '')}")
        if permitted and permitted != '-':
            reg_list.append(f"허가{permitted.replace('O', '')}")
        if reg_list:
            item['제한/금지/허가'] = ','.join(reg_list) if reg_list else '-'
        
        # 중점관리물질
        priority = keco_data.get('중점관리물질', '-')
        if priority and priority != '-':
            item['중점'] = priority
        
        # 등록대상기존화학물질
        reg_existing = keco_data.get('등록대상기존화학물질', '-')
        if reg_existing and reg_existing != '-':
            item['등록대상기존화학물질'] = 'O'
        
        # 함량 및 규제정보 (details에서 추출)
        details = keco_data.get('details', {})
        if details:
            info_list = []
            for k, v in details.items():
                if '함량' in k:
                    info_list.append(v)
            if info_list:
                item['함량 및 규제정보'] = '; '.join(info_list[:2])  # 최대 2개
    
    # ========== PRTR 정보 ==========
    if prtr_status and prtr_status.get('대상여부') == 'O':
        item['PRTR그룹'] = prtr_status.get('그룹', '-')
        item['PRTR기준량'] = prtr_status.get('기준취급량', '-')
    
    return item

def create_template_excel():
    """템플릿 엑셀 생성"""
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
    
    ws['A1'], ws['B1'], ws['C1'], ws['D1'], ws['E1'], ws['F1'], ws['G1'] = '공정명', '단위작업장소', '제품명', '화학물질명', '관용명/이명', 'CAS No', '함유량(%)'
    ws['H1'], ws['L1'], ws['P1'], ws['S1'] = '독성정보', '법적규제 대상여부', '위험물', '환경부 법적규제 대상여부'
    
    row2 = ['', '', '', '', '', '', '', '발암성', '변이성', '생식독성', '노출기준(TWA)', '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질', '위험물류별', '지정수량', '위험등급', '기존', '급성·만성·생태', '사고대비', '제한/금지/허가', '중점', '잔류', '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부']
    for col, h in enumerate(row2, 1):
        ws.cell(row=2, column=col, value=h)
    
    for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G']:
        ws.merge_cells(f'{col}1:{col}2')
    ws.merge_cells('H1:K1')
    ws.merge_cells('L1:O1')
    ws.merge_cells('P1:R1')
    ws.merge_cells('S1:AA1')
    
    for row in [1, 2]:
        for col in range(1, 28):
            cell = ws.cell(row=row, column=col)
            cell.font, cell.alignment, cell.border = header_font, center_align, thin_border
            cell.fill = header_fill if row == 1 else header_fill2
    
    wb.save(output)
    output.seek(0)
    return output

def export_inventory_to_excel(inventory_data):
    """인벤토리 내보내기"""
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
    yes_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")  # 빨간배경
    hazmat_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")  # 노란배경
    
    ws['A1'], ws['B1'], ws['C1'], ws['D1'], ws['E1'], ws['F1'], ws['G1'] = '공정명', '단위작업장소', '제품명', '화학물질명', '관용명/이명', 'CAS No', '함유량(%)'
    ws['H1'], ws['L1'], ws['P1'], ws['S1'] = '독성정보', '법적규제 대상여부', '위험물', '환경부 법적규제 대상여부'
    
    row2 = ['', '', '', '', '', '', '', '발암성', '변이성', '생식독성', '노출기준(TWA)', '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질', '위험물류별', '지정수량', '위험등급', '기존', '급성·만성·생태', '사고대비', '제한/금지/허가', '중점', '잔류', '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부']
    for col, h in enumerate(row2, 1):
        ws.cell(row=2, column=col, value=h)
    
    for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G']:
        ws.merge_cells(f'{col}1:{col}2')
    ws.merge_cells('H1:K1')
    ws.merge_cells('L1:O1')
    ws.merge_cells('P1:R1')
    ws.merge_cells('S1:AA1')
    
    for row in [1, 2]:
        for col in range(1, 28):
            cell = ws.cell(row=row, column=col)
            cell.font, cell.alignment, cell.border = header_font, center_align, thin_border
            cell.fill = header_fill if row == 1 else header_fill2
    
    for row_idx, item in enumerate(inventory_data, 3):
        data = [
            item.get('공정명', ''), item.get('단위작업장소', ''), item.get('제품명', ''),
            item.get('화학물질명', ''), item.get('관용명/이명', ''), item.get('CAS No', ''), item.get('함유량(%)', ''),
            item.get('발암성', '-'), item.get('변이성', '-'), item.get('생식독성', '-'), item.get('노출기준(TWA)', '-'),
            item.get('작업환경측정', 'X'), item.get('특수건강진단', 'X'), item.get('관리대상유해물질', 'X'), item.get('특별관리물질', 'X'),
            item.get('위험물류별', '-'), item.get('지정수량', '-'), item.get('위험등급', '-'),
            item.get('기존', '-'), item.get('급성·만성·생태', 'X'), item.get('사고대비', 'X'), item.get('제한/금지/허가', '-'),
            item.get('중점', '-'), item.get('잔류', '-'), item.get('함량 및 규제정보', '-'), item.get('등록대상기존화학물질', '-'), item.get('기존물질여부', '-')
        ]
        
        for col_idx, val in enumerate(data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.alignment, cell.border = center_align, thin_border
            # 규제대상(O) 빨간배경
            if val == 'O':
                cell.fill = yes_fill
            # 위험물 정보(P,Q,R) 노란배경
            if col_idx in [16, 17, 18] and val not in ['-', '', None]:
                cell.fill = hazmat_fill
    
    col_widths = {'A': 10, 'B': 12, 'C': 18, 'D': 18, 'E': 12, 'F': 12, 'G': 10, 'H': 10, 'I': 8, 'J': 8, 'K': 12, 'L': 10, 'M': 10, 'N': 12, 'O': 10, 'P': 25, 'Q': 10, 'R': 8, 'S': 6, 'T': 6, 'U': 8, 'V': 12, 'W': 6, 'X': 6, 'Y': 12, 'Z': 14}
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
        cnt_haz = sum(1 for i in st.session_state.inventory if i.get('위험물류별', '-') != '-')
        st.metric("위험물", f"{cnt_haz}종")
    
    st.divider()
    st.markdown("#### 📥 템플릿")
    template_data = create_template_excel()
    st.download_button("📄 빈 템플릿 다운로드", data=template_data.getvalue(), file_name=f"인벤토리_템플릿_{date.today()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    
    st.divider()
    st.markdown("#### 🔌 데이터 소스")
    st.caption(f"KOSHA API: {'✅' if KOSHA_AVAILABLE else '❌'} (고용노동부)")
    st.caption(f"KECO API: {'✅' if KECO_AVAILABLE else '❌'} (환경부)")
    st.caption("PRTR DB: ✅ (배출량조사)")
    
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
    <p>KOSHA API 자동 조회 (노출기준 + 법적규제 + 위험물)</p>
</div>
""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["📤 엑셀 업로드", "➕ 개별 등록", "📋 목록 보기", "📥 내보내기"])

# ============================================
# 탭 1: 엑셀 업로드
# ============================================
with tab1:
    st.subheader("📤 엑셀 파일 업로드")
    
    st.markdown('<div class="upload-box"><h4>📁 엑셀 파일을 업로드하세요</h4></div>', unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("엑셀 파일 선택", type=['xlsx', 'xls'])
    
    if uploaded_file:
        st.success(f"✅ **{uploaded_file.name}** 업로드됨")
        
        try:
            # openpyxl로 직접 읽기 (대용량 파일 지원)
            from openpyxl import load_workbook
            import io
            
            wb = load_workbook(io.BytesIO(uploaded_file.read()), read_only=True, data_only=True)
            ws = wb.active
            
            # 실제 데이터 행 수 확인
            max_row = ws.max_row
            max_col = ws.max_column
            
            # 헤더 읽기 (1행: 대분류, 2행: 세부항목)
            headers_row1 = [ws.cell(row=1, column=c).value for c in range(1, max_col + 1)]
            headers_row2 = [ws.cell(row=2, column=c).value for c in range(1, max_col + 1)]
            
            # 컬럼명 결정 (2행 우선, 없으면 1행)
            headers = []
            for i in range(len(headers_row2)):
                if headers_row2[i]:
                    headers.append(str(headers_row2[i]))
                elif headers_row1[i]:
                    headers.append(str(headers_row1[i]))
                else:
                    headers.append(f"Column_{i+1}")
            
            # 데이터 읽기 (3행부터)
            data_rows = []
            for row_idx in range(3, max_row + 1):
                row_data = {}
                has_data = False
                for col_idx in range(1, len(headers) + 1):
                    cell_val = ws.cell(row=row_idx, column=col_idx).value
                    col_name = headers[col_idx - 1] if col_idx <= len(headers) else f"Column_{col_idx}"
                    row_data[col_name] = cell_val
                    if cell_val is not None and str(cell_val).strip():
                        has_data = True
                if has_data:  # 데이터가 하나라도 있는 행만 추가
                    data_rows.append(row_data)
            
            wb.close()
            
            # DataFrame으로 변환
            df = pd.DataFrame(data_rows)
            
            with st.expander("📊 미리보기", expanded=True):
                st.dataframe(df.head(10), use_container_width=True)
                st.caption(f"총 **{len(df)}행** (원본 파일: {max_row}행)")
            
            st.divider()
            
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
            
            auto_query = st.checkbox("✅ KOSHA/KECO API 자동 조회", value=True)
            
            st.divider()
            
            if st.button("🚀 일괄 등록", type="primary", use_container_width=True):
                progress = st.progress(0)
                status = st.empty()
                
                success, skip, hazmat_count = 0, 0, 0
                existing_cas = [i['CAS No'] for i in st.session_state.inventory]
                total_rows = len(df)
                
                for idx, row in df.iterrows():
                    cas = str(row.get(cas_col, '')).strip() if row.get(cas_col) else ''
                    
                    # CAS 번호 유효성 검사
                    if not cas or cas == 'nan' or cas == 'None' or cas in existing_cas:
                        skip += 1
                        progress.progress((idx + 1) / total_rows)
                        continue
                    
                    chem_name = str(row.get(name_col, '')) if name_col != '(자동조회)' and row.get(name_col) else ''
                    process = str(row.get(process_col, '')) if process_col != '(없음)' and row.get(process_col) else ''
                    unit_wp = str(row.get(unit_col, '')) if unit_col != '(없음)' and row.get(unit_col) else ''
                    product = str(row.get(product_col, '')) if product_col != '(없음)' and row.get(product_col) else ''
                    content = str(row.get(content_col, '')) if content_col != '(없음)' and row.get(content_col) else ''
                    
                    # nan/None 정리
                    chem_name = '' if chem_name in ['nan', 'None'] else chem_name
                    process = '' if process in ['nan', 'None'] else process
                    unit_wp = '' if unit_wp in ['nan', 'None'] else unit_wp
                    product = '' if product in ['nan', 'None'] else product
                    content = '' if content in ['nan', 'None'] else content
                    
                    kosha_data, keco_data, prtr_status = None, None, None
                    
                    if auto_query:
                        # KOSHA API (고용노동부)
                        if KOSHA_AVAILABLE:
                            status.text(f"[{idx+1}/{total_rows}] KOSHA 조회: {cas}...")
                            kosha_data, _ = query_chemical_info(cas)
                            try:
                                prtr_status = check_prtr_status(cas)
                            except:
                                prtr_status = None
                        
                        # KECO API (환경부)
                        if KECO_AVAILABLE:
                            status.text(f"[{idx+1}/{total_rows}] KECO 조회: {cas}...")
                            keco_data = get_chemical_regulations(cas)
                    
                    item = create_inventory_item(process, unit_wp, product, chem_name, '', cas, content, kosha_data, keco_data, prtr_status)
                    
                    # 위험물 카운트
                    if item.get('위험물류별', '-') != '-':
                        hazmat_count += 1
                    
                    st.session_state.inventory.append(item)
                    existing_cas.append(cas)
                    success += 1
                    progress.progress((idx + 1) / total_rows)
                
                status.empty()
                progress.empty()
                st.success(f"✅ 등록 완료! 성공: **{success}건**, 건너뜀: {skip}건, 위험물: {hazmat_count}종")
                st.rerun()
        
        except Exception as e:
            st.error(f"❌ 파일 읽기 오류: {e}")
            import traceback
            st.code(traceback.format_exc())

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
        st.info("""
        💡 **KOSHA API 자동 조회 항목:**
        - 8번: 노출기준 (TWA, STEL)
        - 15번: 법적규제 + **위험물** 정보
        
        **KECO API (환경부):**
        - 유독물질, 사고대비, 제한/금지 등
        """)
    
    if st.button("🔍 조회 및 등록", type="primary", use_container_width=True):
        if cas:
            with st.spinner("API 조회 중..."):
                # KOSHA API
                kosha_data, err = query_chemical_info(cas.strip())
                try:
                    prtr_status = check_prtr_status(cas.strip())
                except:
                    prtr_status = None
                
                # KECO API
                keco_data = None
                if KECO_AVAILABLE:
                    keco_data = get_chemical_regulations(cas.strip())
            
            if kosha_data or (keco_data and keco_data.get('success')):
                chem_name_final = ''
                if kosha_data:
                    chem_name_final = kosha_data.get('name', '')
                elif keco_data:
                    chem_name_final = keco_data.get('물질명', '')
                
                item = create_inventory_item(process, unit_wp, product, chem_name_final, alias, cas.strip(), content, kosha_data, keco_data, prtr_status)
                
                if cas.strip() not in [i['CAS No'] for i in st.session_state.inventory]:
                    st.session_state.inventory.append(item)
                    st.success(f"✅ **{item['화학물질명']}** 등록 완료!")
                    
                    # 조회 결과 표시
                    col_a, col_b, col_c, col_d = st.columns(4)
                    col_a.metric("노출기준(TWA)", item['노출기준(TWA)'])
                    col_b.metric("작업환경측정", item['작업환경측정'])
                    col_c.metric("급성·만성·생태", item['급성·만성·생태'])
                    col_d.metric("위험물류별", item['위험물류별'])
                    
                    st.rerun()
                else:
                    st.warning("이미 등록된 물질입니다")
            else:
                st.error(f"❌ 조회 실패: {err}")
        else:
            st.warning("CAS 번호를 입력하세요")

# ============================================
# 탭 3: 목록
# ============================================
with tab3:
    st.subheader("📋 인벤토리 목록")
    
    if st.session_state.inventory:
        st.caption(f"총 {len(st.session_state.inventory)}종")
        
        display_cols = ['공정명', '단위작업장소', '제품명', 'CAS No', '화학물질명', '노출기준(TWA)', 
                      '작업환경측정', '특수건강진단', '관리대상유해물질', 
                      '위험물류별', '지정수량', '위험등급']
        df = pd.DataFrame(st.session_state.inventory)
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available_cols], use_container_width=True, height=500)
        
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
        st.info("등록된 물질이 없습니다")

# ============================================
# 탭 4: 내보내기
# ============================================
with tab4:
    st.subheader("📥 내보내기")
    
    if st.session_state.inventory:
        col1, col2 = st.columns(2)
        with col1:
            excel = export_inventory_to_excel(st.session_state.inventory)
            st.download_button("📊 엑셀 다운로드", data=excel.getvalue(), file_name=f"인벤토리_{date.today()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with col2:
            csv = pd.DataFrame(st.session_state.inventory).to_csv(index=False, encoding='utf-8-sig')
            st.download_button("📄 CSV 다운로드", data=csv, file_name=f"인벤토리_{date.today()}.csv", mime="text/csv", use_container_width=True)
        
        st.divider()
        st.markdown("#### 📈 규제 현황 통계")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("작업환경측정", f"{sum(1 for i in st.session_state.inventory if i.get('작업환경측정')=='O')}종")
        c2.metric("특수건강진단", f"{sum(1 for i in st.session_state.inventory if i.get('특수건강진단')=='O')}종")
        c3.metric("관리대상유해물질", f"{sum(1 for i in st.session_state.inventory if i.get('관리대상유해물질')=='O')}종")
        c4.metric("위험물", f"{sum(1 for i in st.session_state.inventory if i.get('위험물류별','-')!='-')}종")
        c5.metric("PRTR대상", f"{sum(1 for i in st.session_state.inventory if i.get('PRTR그룹','-')!='-')}종")
    else:
        st.info("내보낼 데이터가 없습니다")

st.divider()
st.caption("© 2025 Kay's Chem Manager | KOSHA API 연동 (8번+15번)")
