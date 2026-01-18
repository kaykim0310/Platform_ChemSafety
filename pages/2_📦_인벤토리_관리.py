#!/usr/bin/env python3
"""
📦 인벤토리 관리 페이지
- 템플릿 다운로드
- 엑셀 업로드
- KOSHA API 일괄 조회
- 규제정보 자동 체크
"""
import streamlit as st
import pandas as pd
import sys
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
if 'kreach_db' not in st.session_state:
    st.session_state.kreach_db = None
if 'kreach_db_info' not in st.session_state:
    st.session_state.kreach_db_info = None

# ============================================
# 템플릿 생성 함수
# ============================================
def create_template():
    """빈 템플릿 엑셀 생성"""
    # 헤더 구조 (2행)
    header_row1 = ['공정명', '제품명', '화학물질명', '관용명/이명', 'CAS No', '함유량(%)',
                   '독성정보', '', '', '',
                   '법적규제 대상여부', '', '', '', '', '',
                   '환경부 법적규제 대상여부', '', '', '', '', '', '', '', '']
    
    header_row2 = ['', '', '', '', '', '',
                   '발암성', '변이성', '생식독성', '노출기준(TWA)',
                   '작업환경측정', '측정주기', '특수건강진단', '진단주기', '관리대상유해물질', '특별관리물질',
                   '기존', '유독', '사고대비', '제한/금지/허가', '중점', '잔류', 
                   '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부']
    
    # 샘플 데이터
    sample_data = [
        ['도장', '신너(샘플)', '톨루엔', '', '108-88-3', 50, '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
        ['도장', '신너(샘플)', '자일렌', '', '1330-20-7', 30, '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
        ['세척', '세정제(샘플)', '아세톤', '', '67-64-1', 80, '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ]
    
    # DataFrame 생성
    df = pd.DataFrame([header_row1, header_row2] + sample_data)
    
    return df


def create_template_excel():
    """템플릿 엑셀 파일 생성"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df = create_template()
        df.to_excel(writer, sheet_name='화학물질 정보', index=False, header=False)
        
        # 워크시트 스타일링
        worksheet = writer.sheets['화학물질 정보']
        
        # 열 너비 조정
        column_widths = [10, 20, 25, 15, 15, 10, 8, 8, 8, 12, 10, 10, 10, 10, 12, 10, 8, 8, 8, 12, 8, 8, 15, 15, 10]
        for i, width in enumerate(column_widths):
            col_letter = chr(65 + i) if i < 26 else chr(64 + i//26) + chr(65 + i%26)
            worksheet.column_dimensions[col_letter].width = width
    
    output.seek(0)
    return output.getvalue()


def get_kreach_info(cas_no: str) -> dict:
    """화관법 DB에서 CAS 번호로 정보 조회"""
    if st.session_state.kreach_db is None:
        return None
    
    cas_no = str(cas_no).strip()
    db = st.session_state.kreach_db
    
    # CAS 번호로 검색
    result = db[db['CAS번호'].astype(str).str.strip() == cas_no]
    
    if len(result) > 0:
        row = result.iloc[0]
        return {
            '고유번호': row.get('기존', '-'),
            '유독물질': 'O' if pd.notna(row.get('급성·만성·생태')) and str(row.get('급성·만성·생태')).strip() else 'X',
            '유독물질_상세': str(row.get('급성·만성·생태', '-')) if pd.notna(row.get('급성·만성·생태')) else '-',
            '사고대비물질': 'O' if pd.notna(row.get('사고대비')) and str(row.get('사고대비')).strip() else 'X',
            '사고대비_상세': str(row.get('사고대비', '-')) if pd.notna(row.get('사고대비')) else '-',
            '제한금지허가': str(row.get('제한/금지/허가', '-')) if pd.notna(row.get('제한/금지/허가')) else '-',
            '중점관리물질': str(row.get('중점', '-')) if pd.notna(row.get('중점')) else '-',
            '잔류성오염물질': str(row.get('잔류', '-')) if pd.notna(row.get('잔류')) else '-',
            '함량기준': str(row.get('유해특성분류 및 혼합물 함량기준(%)', '-')) if pd.notna(row.get('유해특성분류 및 혼합물 함량기준(%)')) else '-',
            '등록대상': str(row.get('등록대상기존화학물질', '-')) if pd.notna(row.get('등록대상기존화학물질')) else '-',
            '기존물질여부': str(row.get('기존물질여부', '-')) if pd.notna(row.get('기존물질여부')) else '-',
        }
    return None


# ============================================
# 메인 화면
# ============================================
st.markdown("""
<div class="main-header">
    <h2>📦 화학물질 인벤토리 관리</h2>
    <p>엑셀 업로드 → KOSHA API 조회 → 규제정보 자동 체크</p>
</div>
""", unsafe_allow_html=True)

# API 상태 표시
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if KOSHA_AVAILABLE:
        st.success("✅ KOSHA API 연결됨")
    else:
        st.warning("⚠️ KOSHA API 연결 안됨")
    
    if st.session_state.kreach_db is not None:
        info = st.session_state.kreach_db_info
        st.success(f"✅ 화관법 DB 로드됨 ({info['count']:,}건, {info['date']})")
    else:
        st.warning("⚠️ 화관법 DB 미로드 - 사이드바에서 업로드하세요")

# ============================================
# 사이드바 - 화관법 DB 관리
# ============================================
with st.sidebar:
    st.markdown("### ⚙️ 화관법 DB 관리")
    
    if st.session_state.kreach_db is not None:
        info = st.session_state.kreach_db_info
        st.info(f"📊 **{info['count']:,}건** 로드됨\n\n📅 {info['date']}")
        
        if st.button("🗑️ DB 초기화", use_container_width=True):
            st.session_state.kreach_db = None
            st.session_state.kreach_db_info = None
            st.rerun()
    else:
        st.warning("DB가 로드되지 않았습니다")
    
    st.markdown("##### 📤 K-REACH 엑셀 업로드")
    st.caption("kreach.mcee.go.kr에서 다운로드한 파일")
    
    kreach_file = st.file_uploader(
        "K-REACH 엑셀",
        type=['xlsx', 'xls'],
        key="kreach_upload",
        label_visibility="collapsed"
    )
    
    if kreach_file:
        try:
            with st.spinner("DB 로딩 중..."):
                df_kreach = pd.read_excel(kreach_file, sheet_name=0)
                st.session_state.kreach_db = df_kreach
                st.session_state.kreach_db_info = {
                    'count': len(df_kreach),
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'filename': kreach_file.name
                }
            st.success(f"✅ {len(df_kreach):,}건 로드 완료!")
            st.rerun()
        except Exception as e:
            st.error(f"오류: {e}")
    
    st.divider()

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
        use_container_width=True,
        type="primary"
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
        
        # 컬럼명 정의 (2행 헤더 병합)
        columns = ['공정명', '제품명', '화학물질명', '관용명/이명', 'CAS No', '함유량(%)',
                   '발암성', '변이성', '생식독성', '노출기준(TWA)',
                   '작업환경측정', '측정주기', '특수건강진단', '진단주기', '관리대상유해물질', '특별관리물질',
                   '기존', '유독', '사고대비', '제한/금지/허가', '중점', '잔류',
                   '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부']
        
        # 데이터 행만 추출 (헤더 2행 제외)
        df = df_raw.iloc[2:].copy()
        df.columns = columns[:len(df.columns)]
        df = df.reset_index(drop=True)
        
        # 빈 행 제거
        df = df.dropna(subset=['CAS No'], how='all')
        df = df[df['CAS No'].notna() & (df['CAS No'] != '')]
        
        st.session_state.inventory_data = df
        
        st.success(f"✅ 파일 업로드 완료! **{len(df)}개** 화학물질 확인됨")
        
        # 미리보기
        with st.expander("📋 업로드된 데이터 미리보기", expanded=True):
            display_cols = ['공정명', '제품명', '화학물질명', 'CAS No', '함유량(%)']
            st.dataframe(df[display_cols], use_container_width=True)
            
    except Exception as e:
        st.error(f"❌ 파일 읽기 오류: {e}")
        st.info("💡 템플릿 형식에 맞는 파일인지 확인해주세요.")

st.divider()

# ============================================
# Step 3: KOSHA API 조회
# ============================================
st.subheader("🔍 Step 3. 규제정보 자동 조회")

if st.session_state.inventory_data is not None:
    df = st.session_state.inventory_data
    
    # CAS 번호 목록
    cas_list = df['CAS No'].dropna().unique().tolist()
    st.info(f"📌 조회 대상: **{len(cas_list)}개** 고유 CAS 번호")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 KOSHA API 일괄 조회 시작", type="primary", use_container_width=True, disabled=not KOSHA_AVAILABLE):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 결과 저장용
            results = {}
            
            for idx, cas_no in enumerate(cas_list):
                cas_no = str(cas_no).strip()
                status_text.text(f"조회 중... {idx+1}/{len(cas_list)} - {cas_no}")
                progress_bar.progress((idx + 1) / len(cas_list))
                
                try:
                    # KOSHA API 조회
                    result = get_full_msds_data(cas_no)
                    prtr = check_prtr_status(cas_no)
                    
                    # 화관법 DB 조회
                    kreach = get_kreach_info(cas_no)
                    
                    results[cas_no] = {
                        'kosha': result,
                        'prtr': prtr,
                        'kreach': kreach
                    }
                except Exception as e:
                    results[cas_no] = {'error': str(e)}
                
                time.sleep(0.3)  # API 부하 방지
            
            status_text.text("✅ 조회 완료!")
            
            # 결과를 데이터프레임에 적용
            df_result = df.copy()
            
            for idx, row in df_result.iterrows():
                cas_no = str(row['CAS No']).strip()
                if cas_no in results and 'kosha' in results[cas_no]:
                    res = results[cas_no]
                    kosha = res.get('kosha', {})
                    prtr = res.get('prtr', {})
                    kreach = res.get('kreach', {})
                    
                    if kosha.get('success'):
                        # 독성정보
                        tox = kosha.get('toxicity_info', {})
                        df_result.at[idx, '발암성'] = tox.get('발암성', '-')[:20] if tox.get('발암성') else '-'
                        df_result.at[idx, '변이성'] = tox.get('생식세포변이원성', '-')[:20] if tox.get('생식세포변이원성') else '-'
                        df_result.at[idx, '생식독성'] = tox.get('생식독성', '-')[:20] if tox.get('생식독성') else '-'
                        
                        # 노출기준
                        exp = kosha.get('exposure_limits', {})
                        df_result.at[idx, '노출기준(TWA)'] = exp.get('TWA', '-')
                        
                        # 법적규제 (raw_data에서 주기 정보 파싱)
                        regs = kosha.get('legal_regulations', {})
                        raw_data = regs.get('raw_data', [])
                        
                        # raw_data에서 산업안전보건법 관련 정보 찾기
                        reg_text = ''
                        for item in raw_data:
                            if '산업안전보건법' in item.get('항목', ''):
                                reg_text = item.get('내용', '')
                                break
                        
                        # 측정주기 파싱
                        import re
                        measure_match = re.search(r'측정주기\s*:\s*(\d+개월)', reg_text)
                        exam_match = re.search(r'진단주기\s*:\s*(\d+개월)', reg_text)
                        
                        df_result.at[idx, '작업환경측정'] = regs.get('작업환경측정', 'X')
                        df_result.at[idx, '측정주기'] = measure_match.group(1) if measure_match else '-'
                        df_result.at[idx, '특수건강진단'] = regs.get('특수건강진단', 'X')
                        df_result.at[idx, '진단주기'] = exam_match.group(1) if exam_match else '-'
                        df_result.at[idx, '관리대상유해물질'] = regs.get('관리대상유해물질', 'X')
                        df_result.at[idx, '특별관리물질'] = regs.get('특별관리물질', 'X')
                    
                    # 화관법 DB 정보 적용 (우선순위: K-REACH DB > KOSHA API)
                    if kreach:
                        df_result.at[idx, '기존'] = kreach.get('고유번호', '-')
                        df_result.at[idx, '유독'] = kreach.get('유독물질', '-')
                        df_result.at[idx, '사고대비'] = kreach.get('사고대비물질', '-')
                        df_result.at[idx, '제한/금지/허가'] = kreach.get('제한금지허가', '-')
                        df_result.at[idx, '중점'] = kreach.get('중점관리물질', '-')
                        df_result.at[idx, '잔류'] = kreach.get('잔류성오염물질', '-')
                        df_result.at[idx, '함량 및 규제정보'] = kreach.get('함량기준', '-')[:50] if kreach.get('함량기준') and kreach.get('함량기준') != '-' else '-'
                        df_result.at[idx, '등록대상기존화학물질'] = kreach.get('등록대상', '-')
                        df_result.at[idx, '기존물질여부'] = kreach.get('기존물질여부', '-')
                    elif kosha.get('success'):
                        # KOSHA API에서 환경부 규제 정보 가져오기
                        regs = kosha.get('legal_regulations', {})
                        df_result.at[idx, '유독'] = 'O' if regs.get('유독물질') and regs.get('유독물질') != '-' else 'X'
                        df_result.at[idx, '사고대비'] = 'O' if regs.get('사고대비물질') and regs.get('사고대비물질') != '-' else 'X'
                    
                    # PRTR
                    if prtr.get('대상여부') == 'O':
                        current_jungjeom = str(df_result.at[idx, '중점']) if pd.notna(df_result.at[idx, '중점']) else ''
                        if 'PRTR' not in current_jungjeom:
                            prtr_info = f"PRTR {prtr.get('그룹', '')}"
                            df_result.at[idx, '중점'] = f"{current_jungjeom}, {prtr_info}" if current_jungjeom and current_jungjeom != '-' else prtr_info
            
            st.session_state.processed_data = df_result
            st.success("✅ 규제정보 조회 완료!")
            st.rerun()
    
    with col2:
        if st.button("🔄 초기화", use_container_width=True):
            st.session_state.processed_data = None
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
    
    # 산안법 통계
    st.markdown("##### 🏭 산업안전보건법")
    col1, col2, col3, col4 = st.columns(4)
    
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
        cnt = len(df_result[df_result['특별관리물질'] == 'O'])
        st.metric("특별관리물질", f"{cnt}건")
    
    # 화관법 통계
    st.markdown("##### 🌿 화학물질관리법")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        cnt = len(df_result[df_result['유독'] == 'O'])
        st.metric("유독물질", f"{cnt}건")
    with col2:
        cnt = len(df_result[df_result['사고대비'] == 'O'])
        st.metric("사고대비물질", f"{cnt}건")
    with col3:
        cnt = len(df_result[df_result['제한/금지/허가'].notna() & (df_result['제한/금지/허가'] != '-') & (df_result['제한/금지/허가'] != '')])
        st.metric("제한/금지/허가", f"{cnt}건")
    with col4:
        cnt = len(df_result[df_result['중점'].notna() & df_result['중점'].str.contains('별표', na=False)])
        st.metric("중점관리물질", f"{cnt}건")
    with col5:
        cnt = len(df_result[df_result['중점'].notna() & df_result['중점'].str.contains('PRTR', na=False)])
        st.metric("PRTR 대상", f"{cnt}건")
    
    st.divider()
    
    # 결과 테이블
    st.markdown("#### 📋 조회 결과")
    
    # 표시할 컬럼 선택
    view_option = st.radio(
        "표시 항목",
        ["기본 정보", "산안법 규제", "환경부 규제", "전체"],
        horizontal=True
    )
    
    if view_option == "기본 정보":
        display_cols = ['공정명', '제품명', '화학물질명', 'CAS No', '함유량(%)', '노출기준(TWA)']
    elif view_option == "산안법 규제":
        display_cols = ['화학물질명', 'CAS No', '작업환경측정', '측정주기', '특수건강진단', '진단주기', '관리대상유해물질', '특별관리물질']
    elif view_option == "환경부 규제":
        display_cols = ['화학물질명', 'CAS No', '기존', '유독', '사고대비', '제한/금지/허가', '중점', '잔류']
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
                '항목': ['총 물질 수', 
                        '[산안법] 작업환경측정 대상', '[산안법] 특수건강진단 대상', 
                        '[산안법] 관리대상유해물질', '[산안법] 특별관리물질', 
                        '[화관법] 유독물질', '[화관법] 사고대비물질',
                        '[화관법] 제한/금지/허가', '[화관법] 중점관리물질',
                        'PRTR 대상'],
                '건수': [
                    len(df_result),
                    len(df_result[df_result['작업환경측정'] == 'O']),
                    len(df_result[df_result['특수건강진단'] == 'O']),
                    len(df_result[df_result['관리대상유해물질'] == 'O']),
                    len(df_result[df_result['특별관리물질'] == 'O']),
                    len(df_result[df_result['유독'] == 'O']),
                    len(df_result[df_result['사고대비'] == 'O']),
                    len(df_result[df_result['제한/금지/허가'].notna() & (df_result['제한/금지/허가'] != '-') & (df_result['제한/금지/허가'] != '')]),
                    len(df_result[df_result['중점'].notna() & df_result['중점'].str.contains('별표', na=False)]),
                    len(df_result[df_result['중점'].notna() & df_result['중점'].str.contains('PRTR', na=False)])
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='규제현황 요약', index=False)
        
        output.seek(0)
        st.download_button(
            label="📥 결과 다운로드 (Excel)",
            data=output.getvalue(),
            file_name=f"inventory_result_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary"
        )
    
    with col2:
        # CSV 다운로드
        csv_data = df_result.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 결과 다운로드 (CSV)",
            data=csv_data,
            file_name=f"inventory_result_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )

elif st.session_state.inventory_data is not None:
    st.info("💡 Step 3에서 [KOSHA API 일괄 조회 시작] 버튼을 클릭하세요.")
else:
    st.info("💡 Step 2에서 파일을 먼저 업로드하세요.")

# ============================================
# 푸터
# ============================================
st.divider()
st.caption("© 2025 화학물질 인벤토리 관리 | Kay's Chem Manager | KOSHA API 연동")
