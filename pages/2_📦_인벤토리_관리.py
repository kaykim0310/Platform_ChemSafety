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
# 화관법 DB 관리 (GitHub 저장소 기반)
# ============================================
KREACH_DB_PATH = "data/kreach_db.parquet"


@st.cache_data(ttl=3600, show_spinner=False)  # 1시간 캐시
def load_kreach_db_cached():
    """GitHub에 저장된 화관법 DB 로드 (캐시됨)"""
    if os.path.exists(KREACH_DB_PATH):
        try:
            df = pd.read_parquet(KREACH_DB_PATH)
            # 파일 수정 시간 가져오기
            mtime = os.path.getmtime(KREACH_DB_PATH)
            from datetime import datetime
            date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
            return df, {
                'count': len(df),
                'date': date_str,
                'source': 'GitHub'
            }
        except Exception as e:
            return None, None
    return None, None


# 앱 시작시 GitHub DB 자동 로드
if st.session_state.kreach_db is None:
    with st.spinner("화관법 DB 로딩 중..."):
        saved_db, saved_info = load_kreach_db_cached()
        if saved_db is not None:
            st.session_state.kreach_db = saved_db
            st.session_state.kreach_db_info = saved_info

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
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df = create_template()
        df.to_excel(writer, sheet_name='화학물질 정보', index=False, header=False)
        
        # 워크시트 스타일링
        worksheet = writer.sheets['화학물질 정보']
        
        # 열 너비 조정 (24개 컬럼)
        column_widths = [10, 12, 20, 20, 12, 15, 10, 8, 8, 8, 12, 10, 10, 12, 10, 12, 12, 8, 12, 8, 8, 15, 15, 10]
        for i, width in enumerate(column_widths):
            col_letter = chr(65 + i) if i < 26 else chr(64 + i//26) + chr(65 + i%26)
            worksheet.column_dimensions[col_letter].width = width
        
        # 헤더 셀 병합 (선택적)
        from openpyxl.utils import get_column_letter
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        
        # 스타일 정의
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        sub_header_fill = PatternFill(start_color="8EA9DB", end_color="8EA9DB", fill_type="solid")
        white_font = Font(bold=True, color="FFFFFF")
        dark_font = Font(bold=True)
        center_align = Alignment(horizontal='center', vertical='center')
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # 1행 스타일 (상위 헤더)
        for col in range(1, 25):  # 24개 컬럼
            cell = worksheet.cell(row=1, column=col)
            cell.fill = header_fill
            cell.font = white_font
            cell.alignment = center_align
            cell.border = thin_border
        
        # 2행 스타일 (하위 헤더)
        for col in range(1, 25):  # 24개 컬럼
            cell = worksheet.cell(row=2, column=col)
            cell.fill = sub_header_fill
            cell.font = dark_font
            cell.alignment = center_align
            cell.border = thin_border
    
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
        source = info.get('source', '업로드')
        st.success(f"✅ **{info['count']:,}건** 로드됨")
        st.caption(f"📅 {info['date']} | 📂 {source}")
        
        # 세션 초기화 (GitHub DB가 있으면 다시 로드됨)
        if st.button("🔄 DB 새로고침", width="stretch"):
            st.session_state.kreach_db = None
            st.session_state.kreach_db_info = None
            st.cache_data.clear()
            st.rerun()
    else:
        st.warning("⚠️ DB 미로드")
    
    st.divider()
    
    # 새 DB 업로드 (세션 동안만 유지)
    st.markdown("##### 📤 새 DB 업로드")
    st.caption("K-REACH 엑셀 파일 (세션 동안 유지)")
    
    kreach_file = st.file_uploader(
        "K-REACH 엑셀",
        type=['xlsx', 'xls'],
        key="kreach_upload",
        label_visibility="collapsed"
    )
    
    if kreach_file:
        try:
            with st.spinner("DB 로딩 중... (최초 1회만 소요)"):
                # 필요한 컬럼만 로드 (속도 개선)
                df_kreach = pd.read_excel(
                    kreach_file, 
                    sheet_name=0,
                    usecols=['CAS번호', '영문명', '국문명', '기존', '급성·만성·생태', 
                            '사고대비', '제한/금지/허가', '중점', '잔류',
                            '유해특성분류 및 혼합물 함량기준(%)', '등록대상기존화학물질', '기존물질여부']
                )
                st.session_state.kreach_db = df_kreach
                st.session_state.kreach_db_info = {
                    'count': len(df_kreach),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'source': '업로드',
                    'filename': kreach_file.name
                }
            st.success(f"✅ {len(df_kreach):,}건 로드!")
            st.rerun()
        except Exception as e:
            st.error(f"오류: {e}")
    
    # Parquet 변환 다운로드 (영구 저장용)
    if st.session_state.kreach_db is not None:
        st.divider()
        st.markdown("##### 💾 영구 저장용 변환")
        st.caption("GitHub에 올리면 자동 로드됨")
        
        # Parquet 변환
        parquet_buffer = io.BytesIO()
        st.session_state.kreach_db.to_parquet(parquet_buffer, index=False)
        parquet_buffer.seek(0)
        
        st.download_button(
            "📥 Parquet 다운로드",
            data=parquet_buffer.getvalue(),
            file_name="kreach_db.parquet",
            mime="application/octet-stream",
            width="stretch"
        )
        st.caption("→ `data/kreach_db.parquet`로 저장")
    
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
        width="stretch",
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
        
        # 컬럼명 정의 (2행 헤더 병합) - 원본 템플릿 기준 (24개 컬럼)
        columns = ['공정명', '단위작업장소', '제품명', '화학물질명', '관용명/이명', 'CAS No', '함유량(%)',
                   '발암성', '변이성', '생식독성', '노출기준(TWA)',
                   '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질',
                   '기존', '급성·만성·생태', '사고대비', '제한/금지/허가', '중점', '잔류',
                   '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부']
        
        # 디버그: 원본 데이터 확인
        st.caption(f"📊 원본 파일: {len(df_raw)}행 × {len(df_raw.columns)}열")
        
        # 데이터 행만 추출 (헤더 2행 제외)
        df = df_raw.iloc[2:].copy()
        
        # 컬럼 수 맞추기
        if len(df.columns) >= len(columns):
            df = df.iloc[:, :len(columns)]  # 컬럼 수가 많으면 자르기
            df.columns = columns
        else:
            df.columns = columns[:len(df.columns)]  # 컬럼 수가 적으면 맞추기
        
        df = df.reset_index(drop=True)
        
        # CAS No 컬럼 정리 (공백, 특수문자 처리)
        df['CAS No'] = df['CAS No'].astype(str).str.strip()
        
        # 빈 행 제거 (더 유연하게 - CAS No가 있거나 화학물질명이 있는 경우 유지)
        before_filter = len(df)
        df = df[
            (df['CAS No'].notna() & (df['CAS No'] != '') & (df['CAS No'] != 'nan') & (df['CAS No'] != 'None')) |
            (df['화학물질명'].notna() & (df['화학물질명'] != '') & (df['화학물질명'].astype(str) != 'nan'))
        ]
        after_filter = len(df)
        
        if before_filter != after_filter:
            st.caption(f"ℹ️ 빈 행 {before_filter - after_filter}개 제외됨")
        
        st.session_state.inventory_data = df
        
        st.success(f"✅ 파일 업로드 완료! **{len(df)}개** 화학물질 확인됨")
        
        # 미리보기
        with st.expander("📋 업로드된 데이터 미리보기", expanded=True):
            display_cols = ['공정명', '단위작업장소', '제품명', '화학물질명', 'CAS No', '함유량(%)']
            st.dataframe(df[display_cols], width="stretch")
            
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
        if st.button("🔍 KOSHA API 일괄 조회 시작", type="primary", width="stretch", disabled=not KOSHA_AVAILABLE):
            
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
            
            # 측정주기, 진단주기 컬럼 추가 (원본에 없으므로 새로 추가)
            df_result['측정주기'] = '-'
            df_result['진단주기'] = '-'
            
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
                        
                        # 측정주기, 진단주기 파싱
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
                        df_result.at[idx, '급성·만성·생태'] = kreach.get('유독물질_상세', '-')
                        df_result.at[idx, '사고대비'] = kreach.get('사고대비_상세', '-')
                        df_result.at[idx, '제한/금지/허가'] = kreach.get('제한금지허가', '-')
                        df_result.at[idx, '중점'] = kreach.get('중점관리물질', '-')
                        df_result.at[idx, '잔류'] = kreach.get('잔류성오염물질', '-')
                        df_result.at[idx, '함량 및 규제정보'] = kreach.get('함량기준', '-')[:50] if kreach.get('함량기준') and kreach.get('함량기준') != '-' else '-'
                        df_result.at[idx, '등록대상기존화학물질'] = kreach.get('등록대상', '-')
                        df_result.at[idx, '기존물질여부'] = kreach.get('기존물질여부', '-')
                    elif kosha.get('success'):
                        # KOSHA API에서 환경부 규제 정보 가져오기
                        regs = kosha.get('legal_regulations', {})
                        df_result.at[idx, '급성·만성·생태'] = regs.get('유독물질', '-') if regs.get('유독물질') and regs.get('유독물질') != '-' else '-'
                        df_result.at[idx, '사고대비'] = regs.get('사고대비물질', '-') if regs.get('사고대비물질') and regs.get('사고대비물질') != '-' else '-'
                    
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
        if st.button("🔄 초기화", width="stretch"):
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
        cnt = len(df_result[df_result['작업환경측정'] == 'O']) if '작업환경측정' in df_result.columns else 0
        st.metric("작업환경측정", f"{cnt}건")
    with col2:
        cnt = len(df_result[df_result['특수건강진단'] == 'O']) if '특수건강진단' in df_result.columns else 0
        st.metric("특수건강진단", f"{cnt}건")
    with col3:
        cnt = len(df_result[df_result['관리대상유해물질'] == 'O']) if '관리대상유해물질' in df_result.columns else 0
        st.metric("관리대상유해물질", f"{cnt}건")
    with col4:
        cnt = len(df_result[df_result['특별관리물질'] == 'O']) if '특별관리물질' in df_result.columns else 0
        st.metric("특별관리물질", f"{cnt}건")
    
    # 화관법 통계
    st.markdown("##### 🌿 화학물질관리법")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        if '급성·만성·생태' in df_result.columns:
            cnt = len(df_result[df_result['급성·만성·생태'].notna() & (df_result['급성·만성·생태'] != '-') & (df_result['급성·만성·생태'] != '')])
        else:
            cnt = 0
        st.metric("유독물질", f"{cnt}건")
    with col2:
        if '사고대비' in df_result.columns:
            cnt = len(df_result[df_result['사고대비'].notna() & (df_result['사고대비'] != '-') & (df_result['사고대비'] != '')])
        else:
            cnt = 0
        st.metric("사고대비물질", f"{cnt}건")
    with col3:
        if '제한/금지/허가' in df_result.columns:
            cnt = len(df_result[df_result['제한/금지/허가'].notna() & (df_result['제한/금지/허가'] != '-') & (df_result['제한/금지/허가'] != '')])
        else:
            cnt = 0
        st.metric("제한/금지/허가", f"{cnt}건")
    with col4:
        if '중점' in df_result.columns:
            cnt = len(df_result[df_result['중점'].notna() & df_result['중점'].astype(str).str.contains('별표', na=False)])
        else:
            cnt = 0
        st.metric("중점관리물질", f"{cnt}건")
    with col5:
        if '중점' in df_result.columns:
            cnt = len(df_result[df_result['중점'].notna() & df_result['중점'].astype(str).str.contains('PRTR', na=False)])
        else:
            cnt = 0
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
        display_cols = ['공정명', '단위작업장소', '제품명', '화학물질명', 'CAS No', '함유량(%)', '노출기준(TWA)']
    elif view_option == "산안법 규제":
        display_cols = ['화학물질명', 'CAS No', '작업환경측정', '측정주기', '특수건강진단', '진단주기', '관리대상유해물질', '특별관리물질']
    elif view_option == "환경부 규제":
        display_cols = ['화학물질명', 'CAS No', '기존', '급성·만성·생태', '사고대비', '제한/금지/허가', '중점', '잔류']
    else:
        display_cols = list(df_result.columns)
    
    # 존재하는 컬럼만 필터링
    display_cols = [col for col in display_cols if col in df_result.columns]
    
    # 존재하는 컬럼만 표시
    display_cols = [c for c in display_cols if c in df_result.columns]
    st.dataframe(df_result[display_cols], width="stretch", height=400)
    
    st.divider()
    
    # 다운로드
    st.markdown("#### 📥 결과 다운로드")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # 엑셀 다운로드
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_result.to_excel(writer, sheet_name='화학물질 정보', index=False)
            
            # 요약 시트 - 안전하게 컬럼 존재 여부 확인
            def safe_count(df, col, condition='O'):
                if col not in df.columns:
                    return 0
                if condition == 'O':
                    return len(df[df[col] == 'O'])
                elif condition == 'notna':
                    return len(df[df[col].notna() & (df[col] != '-') & (df[col] != '')])
                elif condition == 'contains_별표':
                    return len(df[df[col].notna() & df[col].astype(str).str.contains('별표', na=False)])
                elif condition == 'contains_PRTR':
                    return len(df[df[col].notna() & df[col].astype(str).str.contains('PRTR', na=False)])
                return 0
            
            summary_data = {
                '항목': ['총 물질 수', 
                        '[산안법] 작업환경측정 대상', '[산안법] 특수건강진단 대상', 
                        '[산안법] 관리대상유해물질', '[산안법] 특별관리물질', 
                        '[화관법] 유독물질', '[화관법] 사고대비물질',
                        '[화관법] 제한/금지/허가', '[화관법] 중점관리물질',
                        'PRTR 대상'],
                '건수': [
                    len(df_result),
                    safe_count(df_result, '작업환경측정', 'O'),
                    safe_count(df_result, '특수건강진단', 'O'),
                    safe_count(df_result, '관리대상유해물질', 'O'),
                    safe_count(df_result, '특별관리물질', 'O'),
                    safe_count(df_result, '급성·만성·생태', 'notna'),
                    safe_count(df_result, '사고대비', 'notna'),
                    safe_count(df_result, '제한/금지/허가', 'notna'),
                    safe_count(df_result, '중점', 'contains_별표'),
                    safe_count(df_result, '중점', 'contains_PRTR')
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='규제현황 요약', index=False)
        
        output.seek(0)
        st.download_button(
            label="📥 결과 다운로드 (Excel)",
            data=output.getvalue(),
            file_name=f"inventory_result_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
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
            width="stretch"
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
