#!/usr/bin/env python3
"""
📦 인벤토리 관리 페이지
- 템플릿 다운로드
- 엑셀 업로드
- KOSHA API (산안법) + KECO API (화관법) 일괄 조회
- 규제정보 자동 체크
"""
import streamlit as st
import pandas as pd
import sys
import os
from pathlib import Path
from datetime import datetime
import io
import time

# 경로 설정
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))

# 모듈 import
try:
    from core.kosha_api import get_full_msds_data
    from core.prtr_db import check_prtr_status
    KOSHA_AVAILABLE = True
except ImportError:
    KOSHA_AVAILABLE = False

# KECO API (화관법) import
try:
    from core.keco_api import search_chemical_by_cas, get_chemical_regulations
    KECO_AVAILABLE = True
except ImportError:
    KECO_AVAILABLE = False

# ============================================
# 페이지 설정
# ============================================
st.set_page_config(
    page_title="인벤토리 관리",
    page_icon="📦",
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
        background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
        border-radius: 10px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 1rem;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-success { background: #dcfce7; color: #166534; }
    .badge-warning { background: #fef3c7; color: #92400e; }
    .badge-danger { background: #fee2e2; color: #991b1b; }
    .template-box {
        padding: 1.5rem;
        background: #f0f9ff;
        border: 2px dashed #3b82f6;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 1rem;
    }
    .upload-box {
        padding: 1.5rem;
        background: #f0fdf4;
        border: 2px dashed #22c55e;
        border-radius: 10px;
        text-align: center;
    }
    .reg-o { background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-weight: bold; }
    .reg-x { background: #f3f4f6; color: #6b7280; padding: 2px 8px; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

# ============================================
# 세션 상태 초기화
# ============================================
if 'inventory_data' not in st.session_state:
    st.session_state.inventory_data = None
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None

# ============================================
# 템플릿 생성 함수
# ============================================
def create_template():
    """빈 템플릿 엑셀 생성 - 원본 서식 기준 (24개 컬럼)"""
    # 헤더 구조 (2행) - 단위작업장소 포함
    header_row1 = ['공정명', '단위작업장소', '제품명', '화학물질명', '관용명/이명', 'CAS No', '함유량(%)',
                   '독성정보', None, None, None,
                   '법적규제 대상여부', None, None, None,
                   '환경부 법적규제 대상여부', None, None, None, None, None, None, None, None]
    
    header_row2 = [None, None, None, None, None, None, None,
                   '발암성', '변이성', '생식독성', '노출기준(TWA)',
                   '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질',
                   '기존', '급성·만성·생태', '사고대비', '제한/금지/허가', '중점', '잔류',
                   '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부']
    
    # 샘플 데이터 (24개 컬럼)
    sample_data = [
        ['도장', '도장실', '신너(샘플)', '톨루엔', None, '108-88-3', 50, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
        ['도장', '도장실', '신너(샘플)', '자일렌', None, '1330-20-7', 30, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
        ['세척', '세척실', '세정제(샘플)', '아세톤', None, '67-64-1', 80, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
    ]
    
    # DataFrame 생성
    df = pd.DataFrame([header_row1, header_row2] + sample_data)
    
    return df


def create_template_excel():
    """템플릿 엑셀 파일 생성"""
    output = io.BytesIO()
    
    # 원본 템플릿 파일이 있으면 사용
    template_path = current_dir / "assets" / "template_inventory.xlsx"
    if template_path.exists():
        with open(template_path, 'rb') as f:
            return f.read()
    
    # 없으면 생성
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df = create_template()
        df.to_excel(writer, sheet_name='화학물질 정보', index=False, header=False)
        
        # 워크시트 스타일링
        worksheet = writer.sheets['화학물질 정보']
        
        # 열 너비 조정 (24개 컬럼)
        column_widths = [10, 12, 20, 25, 15, 15, 10, 8, 8, 8, 12, 10, 10, 12, 10, 8, 12, 8, 12, 8, 8, 15, 15, 10]
        for i, width in enumerate(column_widths):
            col_letter = chr(65 + i) if i < 26 else chr(64 + i//26) + chr(65 + i%26)
            worksheet.column_dimensions[col_letter].width = width
    
    output.seek(0)
    return output.getvalue()


# ============================================
# KECO API로 화관법 규제 조회
# ============================================
def get_keco_regulations(cas_no: str) -> dict:
    """KECO API에서 화관법 규제정보 조회"""
    if not KECO_AVAILABLE:
        return {}
    
    try:
        result = search_chemical_by_cas(cas_no)
        if result.get('success'):
            classifications = result.get('물질분류', {})
            return {
                '유독물질': classifications.get('유독물질', '-'),
                '제한물질': classifications.get('제한물질', '-'),
                '금지물질': classifications.get('금지물질', '-'),
                '허가물질': classifications.get('허가물질', '-'),
                '사고대비물질': classifications.get('사고대비물질', '-'),
                '기존화학물질': classifications.get('기존화학물질', '-'),
                '등록대상기존화학물질': classifications.get('등록대상기존화학물질', '-'),
                'KE번호': result.get('ke_no', ''),
                '물질명_확인': result.get('물질명_국문', ''),
            }
    except Exception as e:
        pass
    
    return {}


# ============================================
# 메인 화면
# ============================================
st.markdown("""
<div class="main-header">
    <h2>📦 화학물질 인벤토리 관리</h2>
    <p>엑셀 업로드 → KOSHA API + KECO API 조회 → 규제정보 자동 체크</p>
</div>
""", unsafe_allow_html=True)

# API 상태 표시
if KOSHA_AVAILABLE:
    st.success("✅ KOSHA API 연결됨 (산안법: TWA, 특검, 측정, 관리대상 등)")
else:
    st.warning("⚠️ KOSHA API 연결 안됨")

if KECO_AVAILABLE:
    st.success("✅ KECO API 연결됨 (화관법: 유독, 제한, 금지, 사고대비 등)")
else:
    st.warning("⚠️ KECO API 연결 안됨")

st.divider()

# ============================================
# Step 1: 템플릿 다운로드
# ============================================
st.subheader("📥 Step 1. 템플릿 다운로드")

st.markdown("""
<div class="template-box">
    <h4>📋 화학물질 인벤토리 템플릿</h4>
    <p>아래 버튼을 클릭하여 템플릿을 다운로드하세요.<br>
    템플릿에 화학물질 정보를 입력한 후 업로드하면 규제정보가 자동으로 채워집니다.</p>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    template_data = create_template_excel()
    st.download_button(
        label="📥 템플릿 다운로드 (Excel)",
        data=template_data,
        file_name=f"template_inventory_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True
    )

st.markdown("""
**📝 입력 필수 항목:**
- `공정명`: 해당 화학물질이 사용되는 공정
- `제품명`: MSDS 상의 제품명
- `화학물질명`: 구성성분 명칭
- `CAS No`: CAS 등록번호 (예: 67-64-1) ← **이 값으로 자동 조회!**
- `함유량(%)`: 제품 내 함유량
""")

st.divider()

# ============================================
# Step 2: 파일 업로드
# ============================================
st.subheader("📤 Step 2. 파일 업로드")

st.markdown("""
<div class="upload-box">
    <h4>📂 인벤토리 파일 업로드</h4>
    <p>작성된 엑셀 파일을 업로드하세요.</p>
</div>
""", unsafe_allow_html=True)

uploaded_file = st.file_uploader(
    "엑셀 파일 선택",
    type=['xlsx', 'xls'],
    help="템플릿 형식의 엑셀 파일을 업로드하세요",
    label_visibility="collapsed"
)

if uploaded_file:
    try:
        # 헤더 2행 건너뛰고 데이터 읽기
        df_raw = pd.read_excel(uploaded_file, sheet_name='화학물질 정보', header=None)
        
        # 원본 파일 크기 확인
        original_size = len(df_raw)
        
        # 컬럼명 정의 (24개 - 단위작업장소 포함)
        columns = ['공정명', '단위작업장소', '제품명', '화학물질명', '관용명/이명', 'CAS No', '함유량(%)',
                   '발암성', '변이성', '생식독성', '노출기준(TWA)',
                   '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질',
                   '기존', '급성·만성·생태', '사고대비', '제한/금지/허가', '중점', '잔류',
                   '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부']
        
        # 데이터 행만 추출 (헤더 2행 제외)
        df = df_raw.iloc[2:].copy()
        df.columns = columns[:len(df.columns)]
        df = df.reset_index(drop=True)
        
        # 빈 행 제거 (CAS No 또는 화학물질명이 있는 행만 유지)
        df['CAS No'] = df['CAS No'].astype(str).str.strip()
        df = df[
            (df['CAS No'].notna() & (df['CAS No'] != '') & (df['CAS No'] != 'nan') & (df['CAS No'] != 'None')) |
            (df['화학물질명'].notna() & (df['화학물질명'] != '') & (df['화학물질명'].astype(str) != 'nan'))
        ]
        
        filtered_size = len(df)
        
        st.session_state.inventory_data = df
        
        st.success(f"✅ 파일 업로드 완료! **{filtered_size}개** 화학물질 확인됨")
        if original_size - 2 > filtered_size:
            st.caption(f"📊 원본 {original_size}행 중 헤더 2행 + 빈 행 {original_size - 2 - filtered_size}개 제외")
        
        # 미리보기
        with st.expander("📋 업로드된 데이터 미리보기", expanded=True):
            display_cols = ['공정명', '단위작업장소', '제품명', '화학물질명', 'CAS No', '함유량(%)']
            display_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(df[display_cols], use_container_width=True)
            
    except Exception as e:
        st.error(f"❌ 파일 읽기 오류: {e}")
        st.info("💡 템플릿 형식에 맞는 파일인지 확인해주세요.")

st.divider()

# ============================================
# Step 3: API 조회
# ============================================
st.subheader("🔍 Step 3. 규제정보 자동 조회")

if st.session_state.inventory_data is not None:
    df = st.session_state.inventory_data
    
    # CAS 번호 목록
    cas_list = df['CAS No'].dropna().unique().tolist()
    cas_list = [c for c in cas_list if c and c != 'nan' and c != 'None']
    st.info(f"📌 조회 대상: **{len(cas_list)}개** 고유 CAS 번호")
    
    api_disabled = not (KOSHA_AVAILABLE or KECO_AVAILABLE)
    
    if st.button("🔍 API 일괄 조회 시작", type="primary", use_container_width=True, disabled=api_disabled):
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        time_text = st.empty()
        
        # 🚀 최적화: 중복 CAS No 제거
        unique_cas = list(set([str(c).strip() for c in cas_list if str(c).strip() and str(c).strip() != 'nan']))
        total_unique = len(unique_cas)
        total_original = len(cas_list)
        
        if total_unique < total_original:
            st.info(f"🔄 중복 제거: {total_original}개 → {total_unique}개 (고유 CAS만 조회)")
        
        # 결과 저장용 (캐시)
        results = {}
        
        import time as time_module
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        start_time = time_module.time()
        
        # 단일 CAS 조회 함수
        def fetch_single(cas_no):
            result_data = {'cas_no': cas_no}
            try:
                # KOSHA API 조회 (산안법)
                if KOSHA_AVAILABLE:
                    kosha_result = get_full_msds_data(cas_no)
                    prtr = check_prtr_status(cas_no)
                    result_data['kosha'] = kosha_result
                    result_data['prtr'] = prtr
                
                # KECO API 조회 (화관법)
                if KECO_AVAILABLE:
                    keco_result = get_keco_regulations(cas_no)
                    result_data['keco'] = keco_result
                
            except Exception as e:
                result_data['error'] = str(e)
            
            return cas_no, result_data
        
        # 🚀 병렬 처리 (5개 동시 조회)
        completed = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_single, cas): cas for cas in unique_cas}
            
            for future in as_completed(futures):
                cas_no, result = future.result()
                results[cas_no] = result
                completed += 1
                
                elapsed = time_module.time() - start_time
                remaining = (elapsed / completed) * (total_unique - completed) if completed > 0 else 0
                
                status_text.text(f"조회 중... {completed}/{total_unique} - {cas_no}")
                time_text.text(f"⏱️ 경과: {elapsed:.0f}초 | 예상 남은 시간: {remaining:.0f}초")
                progress_bar.progress(completed / total_unique)
        
        total_time = time_module.time() - start_time
        status_text.text(f"✅ 조회 완료! ({total_unique}개, {total_time:.1f}초 소요)")
        time_text.empty()
        
        # 결과를 데이터프레임에 적용
        df_result = df.copy()
        
        # 추가 컬럼 생성
        if '측정주기' not in df_result.columns:
            df_result['측정주기'] = ''
        if '진단주기' not in df_result.columns:
            df_result['진단주기'] = ''
        
        for idx, row in df_result.iterrows():
            cas_no = str(row['CAS No']).strip()
            if cas_no in results:
                res = results[cas_no]
                
                # KOSHA API 결과 적용 (산안법)
                kosha = res.get('kosha', {})
                prtr = res.get('prtr', {})
                
                if kosha and kosha.get('success'):
                    # 독성정보
                    tox = kosha.get('toxicity_info', {})
                    df_result.at[idx, '발암성'] = tox.get('발암성', '-')[:20] if tox.get('발암성') else '-'
                    df_result.at[idx, '변이성'] = tox.get('생식세포변이원성', '-')[:20] if tox.get('생식세포변이원성') else '-'
                    df_result.at[idx, '생식독성'] = tox.get('생식독성', '-')[:20] if tox.get('생식독성') else '-'
                    
                    # 노출기준
                    exp = kosha.get('exposure_limits', {})
                    df_result.at[idx, '노출기준(TWA)'] = exp.get('TWA', '-')
                    
                    # 법적규제 (산안법)
                    regs = kosha.get('legal_regulations', {})
                    df_result.at[idx, '작업환경측정'] = regs.get('작업환경측정', '-')
                    df_result.at[idx, '특수건강진단'] = regs.get('특수건강진단', '-')
                    df_result.at[idx, '관리대상유해물질'] = regs.get('관리대상유해물질', '-')
                    df_result.at[idx, '특별관리물질'] = regs.get('특별관리물질', '-')
                    
                    # 측정/진단 주기
                    df_result.at[idx, '측정주기'] = regs.get('측정주기', '')
                    df_result.at[idx, '진단주기'] = regs.get('진단주기', '')
                
                # PRTR
                if prtr and prtr.get('대상여부') == 'O':
                    df_result.at[idx, '중점'] = f"PRTR {prtr.get('그룹', '')}"
                
                # KECO API 결과 적용 (화관법)
                keco = res.get('keco', {})
                if keco:
                    # 화관법 규제정보
                    df_result.at[idx, '기존'] = 'O' if keco.get('기존화학물질') == 'O' else '-'
                    df_result.at[idx, '사고대비'] = keco.get('사고대비물질', '-')
                    df_result.at[idx, '등록대상기존화학물질'] = keco.get('등록대상기존화학물질', '-')
                    
                    # 유독물질 → 급성·만성·생태 컬럼에 표시
                    if keco.get('유독물질') == 'O':
                        df_result.at[idx, '급성·만성·생태'] = '유독'
                    
                    # 제한/금지/허가
                    restrictions = []
                    if keco.get('제한물질') == 'O':
                        restrictions.append('제한')
                    if keco.get('금지물질') == 'O':
                        restrictions.append('금지')
                    if keco.get('허가물질') == 'O':
                        restrictions.append('허가')
                    if restrictions:
                        df_result.at[idx, '제한/금지/허가'] = '/'.join(restrictions)
        
        st.session_state.processed_data = df_result
        st.success("✅ 규제정보 조회 완료!")
        st.rerun()

else:
    st.info("💡 Step 2에서 파일을 먼저 업로드하세요.")

st.divider()

# ============================================
# Step 4: 결과 확인 및 다운로드
# ============================================
st.subheader("📊 Step 4. 결과 확인 및 다운로드")

if st.session_state.processed_data is not None:
    df_result = st.session_state.processed_data
    
    # 규제 통계
    st.markdown("#### 📈 규제 현황 요약")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        cnt = len(df_result[df_result['작업환경측정'] == 'O'])
        st.metric("작업환경측정", f"{cnt}건")
    with col2:
        cnt = len(df_result[df_result['특수건강진단'] == 'O'])
        st.metric("특수건강진단", f"{cnt}건")
    with col3:
        cnt = len(df_result[df_result['관리대상유해물질'] == 'O'])
        st.metric("관리대상유해물질", f"{cnt}건")
    with col4:
        cnt = len(df_result[df_result['사고대비'] == 'O'])
        st.metric("사고대비물질", f"{cnt}건")
    with col5:
        cnt = len(df_result[df_result['급성·만성·생태'].notna() & (df_result['급성·만성·생태'] != '-') & (df_result['급성·만성·생태'] != '')])
        st.metric("유독물질", f"{cnt}건")
    with col6:
        cnt = len(df_result[df_result['중점'].notna() & df_result['중점'].str.contains('PRTR', na=False)])
        st.metric("PRTR 대상", f"{cnt}건")
    
    st.divider()
    
    # 결과 테이블
    st.markdown("#### 📋 조회 결과")
    
    # 표시할 컬럼 선택
    view_option = st.radio(
        "표시 항목",
        ["기본 정보", "산안법 규제", "화관법 규제", "전체"],
        horizontal=True
    )
    
    if view_option == "기본 정보":
        display_cols = ['공정명', '단위작업장소', '제품명', '화학물질명', 'CAS No', '함유량(%)', '노출기준(TWA)']
    elif view_option == "산안법 규제":
        display_cols = ['화학물질명', 'CAS No', '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질', '측정주기', '진단주기']
    elif view_option == "화관법 규제":
        display_cols = ['화학물질명', 'CAS No', '기존', '급성·만성·생태', '사고대비', '제한/금지/허가', '등록대상기존화학물질']
    else:
        display_cols = list(df_result.columns)
    
    # 존재하는 컬럼만 표시
    display_cols = [c for c in display_cols if c in df_result.columns]
    st.dataframe(df_result[display_cols], use_container_width=True, height=400)
    
    st.divider()
    
    # 다운로드
    st.markdown("#### 📥 결과 다운로드")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # 엑셀 다운로드
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_result.to_excel(writer, sheet_name='화학물질 정보', index=False)
            
            # 요약 시트
            summary_data = {
                '항목': ['총 물질 수', '작업환경측정 대상', '특수건강진단 대상', '관리대상유해물질', '사고대비물질', '유독물질', 'PRTR 대상'],
                '건수': [
                    len(df_result),
                    len(df_result[df_result['작업환경측정'] == 'O']),
                    len(df_result[df_result['특수건강진단'] == 'O']),
                    len(df_result[df_result['관리대상유해물질'] == 'O']),
                    len(df_result[df_result['사고대비'] == 'O']),
                    len(df_result[df_result['급성·만성·생태'].notna() & (df_result['급성·만성·생태'] != '-') & (df_result['급성·만성·생태'] != '')]),
                    len(df_result[df_result['중점'].notna() & df_result['중점'].str.contains('PRTR', na=False)])
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='규제현황 요약', index=False)
        
        output.seek(0)
        
        # 원본 파일명 기반 결과 파일명
        original_name = "inventory"
        if uploaded_file:
            original_name = Path(uploaded_file.name).stem
        
        st.download_button(
            label="📥 결과 다운로드 (Excel)",
            data=output.getvalue(),
            file_name=f"result_{original_name}_{datetime.now().strftime('%y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )
    
    with col2:
        # CSV 다운로드
        csv_data = df_result.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 결과 다운로드 (CSV)",
            data=csv_data,
            file_name=f"result_{original_name}_{datetime.now().strftime('%y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )

elif st.session_state.inventory_data is not None:
    st.info("💡 Step 3에서 [API 일괄 조회 시작] 버튼을 클릭하세요.")
else:
    st.info("💡 Step 2에서 파일을 먼저 업로드하세요.")

# ============================================
# 푸터
# ============================================
st.divider()
st.caption("© 2026 화학물질 인벤토리 관리 | Kay's Chem Manager | KOSHA API (산안법) + KECO API (화관법) 연동")
