import streamlit as st
import pandas as pd
import yaml
import bcrypt
import io
from pathlib import Path
from yaml.loader import SafeLoader
from datetime import datetime

# KOSHA API 모듈 import (선택적)
try:
    from kosha_api import get_chemical_info, batch_query, check_prtr
    KOSHA_AVAILABLE = True
except ImportError:
    KOSHA_AVAILABLE = False
    print("⚠️ kosha_api.py 모듈 없음. KOSHA 조회 기능 비활성화.")

# ============================================
# 페이지 설정
# ============================================
st.set_page_config(
    page_title="화학물질 관리 시스템",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# 스타일 설정
# ============================================
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        color: #1f2937;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #6b7280;
        margin-bottom: 2rem;
    }
    .user-info {
        padding: 0.5rem 1rem;
        background: #f0f9ff;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .result-box {
        padding: 1.5rem;
        background: #f0fdf4;
        border-radius: 0.5rem;
        border: 1px solid #86efac;
        margin: 1rem 0;
    }
    .kosha-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        background: #dcfce7;
        color: #166534;
        border-radius: 1rem;
        font-size: 0.75rem;
        font-weight: 600;
        margin-left: 0.5rem;
    }
    .reg-o { color: #16a34a; font-weight: bold; }
    .reg-x { color: #9ca3af; }
</style>
""", unsafe_allow_html=True)

# ============================================
# 데이터 및 설정 폴더
# ============================================
DATA_DIR = Path("data/companies")
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = Path("config.yaml")

# ============================================
# 배출량 계산 클래스 (통합환경법 기준)
# ============================================
class IntegratedEmissionCalculator:
    """통합환경법 배출량 산정 방법론에 따른 계산 클래스"""
    
    def calculate_tms(self, df_tms, std_o2=None):
        """[Tier 1] TMS 자동측정 산정"""
        if df_tms.empty:
            return 0.0
        valid_data = df_tms[df_tms['상태코드'] == 0].copy()
        
        if std_o2 is not None:
            valid_data['보정농도'] = valid_data.apply(
                lambda row: row['측정농도(mg/Sm3)'] * (21 - std_o2) / (21 - row['실측산소농도(%)'])
                if row['실측산소농도(%)'] < 21 else row['측정농도(mg/Sm3)'], axis=1
            )
        else:
            valid_data['보정농도'] = valid_data['측정농도(mg/Sm3)']

        valid_data['배출량_kg'] = valid_data['보정농도'] * valid_data['배출가스유량(Sm3/hr)'] * 1e-6 * 0.5
        return valid_data['배출량_kg'].sum()

    def calculate_self_measurement(self, df_self):
        """[Tier 2] 자가측정 산정"""
        if df_self.empty:
            return 0.0
        df_self['배출량_kg'] = (
            df_self['평균측정농도(mg/Sm3)'] * df_self['평균배출유량(Sm3/hr)'] * df_self['실제조업시간(hr)'] * 1e-6
        )
        return df_self['배출량_kg'].sum()

    def calculate_mass_balance(self, df_mass):
        """[Tier 3] 물질수지 산정"""
        if df_mass.empty:
            return 0.0
        df_mass['배출량_kg'] = (
            df_mass['투입량(kg)'] - df_mass['회수량(kg)'] - df_mass['파괴량(kg)']
        )
        df_mass['배출량_kg'] = df_mass['배출량_kg'].apply(lambda x: max(x, 0))
        return df_mass['배출량_kg'].sum()

    def calculate_emission_factor(self, df_factor):
        """[Tier 4] 배출계수 산정"""
        if df_factor.empty:
            return 0.0
        df_factor['배출량_kg'] = (
            df_factor['활동량(단위)'] * df_factor['배출계수(kg/단위)'] * (1 - df_factor['방지시설효율(%)'] / 100)
        )
        return df_factor['배출량_kg'].sum()
    
    def calculate_simple_mass_balance(self, input_amount, recovery_amount, destruction_amount):
        """단순 물질수지 계산 (개별 물질용)"""
        emission = input_amount - recovery_amount - destruction_amount
        return max(emission, 0)
    
    def calculate_simple_emission_factor(self, activity_amount, emission_factor, control_efficiency):
        """단순 배출계수 계산 (개별 물질용)"""
        emission = activity_amount * emission_factor * (1 - control_efficiency / 100)
        return max(emission, 0)

# ============================================
# 엑셀 템플릿 생성 함수
# ============================================
def generate_emission_template():
    """배출량 산정용 엑셀 템플릿 생성"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame({
            '측정일시': ['2024-01-01 10:00'],
            '오염물질명': ['NOx'],
            '측정농도(mg/Sm3)': [15.5],
            '배출가스유량(Sm3/hr)': [50000],
            '실측산소농도(%)': [5.2],
            '표준산소농도(%)': [4],
            '상태코드': [0]
        }).to_excel(writer, sheet_name='1_TMS_Data', index=False)
        
        pd.DataFrame({
            '측정기간(월/분기)': ['1월'],
            '오염물질명': ['Dust'],
            '평균측정농도(mg/Sm3)': [10.5],
            '평균배출유량(Sm3/hr)': [45000],
            '실제조업시간(hr)': [720]
        }).to_excel(writer, sheet_name='2_Self_Measurement', index=False)
        
        pd.DataFrame({
            '관리기간': ['1분기'],
            '사용물질명': ['Toluene'],
            '투입량(kg)': [1000],
            '회수량(kg)': [400],
            '파괴량(kg)': [500]
        }).to_excel(writer, sheet_name='3_Mass_Balance', index=False)
        
        pd.DataFrame({
            '시설명': ['보일러 1호기'],
            '활동량(단위)': [15000],
            '배출계수(kg/단위)': [0.002],
            '방지시설효율(%)': [90]
        }).to_excel(writer, sheet_name='4_Emission_Factor', index=False)
        
    return output.getvalue()

# ============================================
# 설정 파일 관리
# ============================================
def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return yaml.load(f, Loader=SafeLoader)
    return None

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

# ============================================
# 인증 함수
# ============================================
def authenticate(username, password):
    config = load_config()
    if config is None:
        return False, None
    
    users = config.get('credentials', {}).get('usernames', {})
    if username not in users:
        return False, None
    
    user = users[username]
    if verify_password(password, user['password']):
        return True, {
            'username': username,
            'name': user['name'],
            'email': user.get('email', ''),
            'role': user.get('role', 'user'),
            'companies': user.get('companies', [])
        }
    return False, None

def get_user_companies(user_info):
    if user_info is None:
        return []
    companies = user_info.get('companies', [])
    if 'ALL' in companies or user_info.get('role') == 'admin':
        return get_all_companies()
    return companies

def get_all_companies():
    companies = []
    if DATA_DIR.exists():
        for f in DATA_DIR.glob("*.xlsx"):
            companies.append(f.stem)
    return sorted(companies)

# ============================================
# 데이터 관리 함수
# ============================================
# 인벤토리 컬럼 정의 (기존 23개 + 배출량 7개 + KOSHA 3개)
INVENTORY_COLUMNS = [
    '공정명', '제품명', '화학물질명', '관용명/이명', 'CAS No', '함유량(%)',
    '발암성', '변이성', '생식독성', '노출기준(TWA)',
    '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질',
    '기존', '유독', '사고대비', '제한/금지/허가', '중점', '잔류',
    '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부',
    # 배출량 관련 컬럼
    '연간취급량(kg)', '대기배출량(kg/년)', '수계배출량(kg/년)', 
    '폐기물이동량(kg/년)', '배출산정방법', '산정기준일', 'PRTR대상여부',
    # KOSHA 조회 관련 컬럼
    'KOSHA조회상태', 'KOSHA조회일'
]

def load_inventory(company_name):
    """사업장 인벤토리 로드"""
    file_path = DATA_DIR / f"{company_name}.xlsx"
    if file_path.exists():
        try:
            with open(file_path, 'rb') as f:
                file_bytes = io.BytesIO(f.read())
            df = pd.read_excel(file_bytes, sheet_name=0, engine='openpyxl')
            file_bytes.close()
            
            for col in INVENTORY_COLUMNS:
                if col not in df.columns:
                    df[col] = None
            return df
        except Exception as e:
            st.error(f"파일 로드 오류: {str(e)}")
            return None
    return None

def load_inventory_from_upload(uploaded_file):
    """업로드된 인벤토리 파일 로드 (기존 서식)"""
    file_bytes = io.BytesIO(uploaded_file.read())
    df = pd.read_excel(file_bytes, sheet_name=0, header=None, skiprows=2, engine='openpyxl')
    file_bytes.close()
    
    base_columns = [
        '공정명', '제품명', '화학물질명', '관용명/이명', 'CAS No', '함유량(%)',
        '발암성', '변이성', '생식독성', '노출기준(TWA)',
        '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질',
        '기존', '유독', '사고대비', '제한/금지/허가', '중점', '잔류',
        '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부'
    ]
    df.columns = base_columns
    
    # 추가 컬럼
    for col in INVENTORY_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df

def save_inventory(company_name, df):
    """사업장 인벤토리 저장"""
    file_path = DATA_DIR / f"{company_name}.xlsx"
    try:
        import gc
        import time
        gc.collect()
        time.sleep(0.2)
        
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        
        with open(file_path, 'wb') as f:
            f.write(output.getvalue())
        output.close()
        
        return True
    except PermissionError:
        st.error("❌ 파일이 사용 중입니다. 엑셀에서 파일을 닫고 다시 시도해주세요.")
        return False
    except Exception as e:
        st.error(f"❌ 저장 오류: {str(e)}")
        return False

def get_cmr_count(df):
    count = 0
    for col in ['발암성', '변이성', '생식독성']:
        if col in df.columns:
            count += df[col].apply(lambda x: str(x) not in ['자료없음', 'nan', '', 'NaN', 'X']).sum()
    return count

def get_measurement_target_count(df):
    if '작업환경측정' in df.columns:
        return df['작업환경측정'].apply(lambda x: 'O' in str(x)).sum()
    return 0

def get_health_exam_target_count(df):
    if '특수건강진단' in df.columns:
        return df['특수건강진단'].apply(lambda x: 'O' in str(x)).sum()
    return 0

def get_prtr_count(df):
    if 'PRTR대상여부' in df.columns:
        return df['PRTR대상여부'].apply(lambda x: str(x) == 'Y' or str(x) == 'O').sum()
    return 0

def get_total_emission(df):
    if '대기배출량(kg/년)' in df.columns:
        return df['대기배출량(kg/년)'].apply(lambda x: float(x) if pd.notna(x) else 0).sum()
    return 0

def get_kosha_queried_count(df):
    """KOSHA 조회 완료 물질 수"""
    if 'KOSHA조회상태' in df.columns:
        return df['KOSHA조회상태'].apply(lambda x: str(x) == '성공').sum()
    return 0

# ============================================
# 세션 상태 초기화
# ============================================
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_info' not in st.session_state:
    st.session_state.user_info = None

# ============================================
# 로그인 화면
# ============================================
def show_login():
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col2:
        st.markdown("### 🧪 화학물질 관리 시스템")
        if KOSHA_AVAILABLE:
            st.markdown('<span class="kosha-badge">KOSHA API 연동</span>', unsafe_allow_html=True)
        st.markdown("---")
        
        with st.form("login_form"):
            username = st.text_input("👤 아이디", placeholder="아이디를 입력하세요")
            password = st.text_input("🔑 비밀번호", type="password", placeholder="비밀번호를 입력하세요")
            
            submit = st.form_submit_button("🔐 로그인", use_container_width=True)
            
            if submit:
                if username and password:
                    success, user_info = authenticate(username, password)
                    if success:
                        st.session_state.authenticated = True
                        st.session_state.user_info = user_info
                        st.rerun()
                    else:
                        st.error("❌ 아이디 또는 비밀번호가 일치하지 않습니다.")
                else:
                    st.warning("⚠️ 아이디와 비밀번호를 입력해주세요.")
        
        st.markdown("---")
        st.caption("© 2025 화학물질 관리 시스템")
        
        with st.expander("🔑 테스트 계정 정보"):
            st.markdown("""
            **관리자**: `admin` / `admin123`  
            **담당자**: `shinwoo` / `shinwoo123`
            """)

# ============================================
# 메인 앱
# ============================================
def show_main_app():
    user_info = st.session_state.user_info
    is_admin = user_info.get('role') == 'admin'
    accessible_companies = get_user_companies(user_info)
    
    # 사이드바
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/chemical-plant.png", width=60)
        st.title("화학물질 관리 시스템")
        
        if KOSHA_AVAILABLE:
            st.markdown('<span class="kosha-badge">KOSHA API</span>', unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="user-info">
            👤 <strong>{user_info['name']}</strong><br>
            <small>{'🔧 관리자' if is_admin else '🏭 사업장 담당자'}</small>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user_info = None
            st.rerun()
        
        st.divider()
        
        # 메뉴 (🔍 KOSHA 조회 추가!)
        if is_admin:
            menu_options = ["🏠 대시보드", "📋 인벤토리 조회"]
            if KOSHA_AVAILABLE:
                menu_options.append("🔍 KOSHA 조회")
            menu_options.extend(["📊 배출량 산정", "📤 데이터 업로드", "🏢 사업장 관리", "👥 사용자 관리"])
        else:
            menu_options = ["🏠 대시보드", "📋 인벤토리 조회"]
            if KOSHA_AVAILABLE:
                menu_options.append("🔍 KOSHA 조회")
            menu_options.append("📊 배출량 산정")
        
        menu = st.radio("메뉴", menu_options, label_visibility="collapsed")
        
        st.divider()
        
        # 사업장 선택
        if accessible_companies:
            selected_company = st.selectbox("🏭 사업장 선택", accessible_companies, index=0)
        else:
            selected_company = None
            st.info("접근 가능한 사업장이 없습니다.")
    
    # ============================================
    # 🏠 대시보드
    # ============================================
    if menu == "🏠 대시보드":
        st.markdown('<p class="main-header">📊 대시보드</p>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">화학물질 및 배출량 현황을 한눈에 확인하세요</p>', unsafe_allow_html=True)
        
        if selected_company:
            df = load_inventory(selected_company)
            
            if df is not None and len(df) > 0:
                # 1행: 기본 지표
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(label="📦 등록 화학물질", value=f"{len(df)}종")
                with col2:
                    st.metric(label="⚠️ CMR 물질", value=f"{get_cmr_count(df)}종")
                with col3:
                    st.metric(label="🔬 작업환경측정 대상", value=f"{get_measurement_target_count(df)}종")
                with col4:
                    st.metric(label="🏥 특수건강진단 대상", value=f"{get_health_exam_target_count(df)}종")
                
                # 2행: 배출량 + KOSHA 지표
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(label="🏭 총 대기배출량", value=f"{get_total_emission(df):,.1f} kg/년")
                with col2:
                    st.metric(label="📋 PRTR 대상", value=f"{get_prtr_count(df)}종")
                with col3:
                    if KOSHA_AVAILABLE:
                        st.metric(label="✅ KOSHA 조회완료", value=f"{get_kosha_queried_count(df)}종")
                    else:
                        emission_calculated = df['대기배출량(kg/년)'].notna().sum()
                        st.metric(label="✅ 배출량 산정완료", value=f"{emission_calculated}종")
                with col4:
                    completion_rate = (get_kosha_queried_count(df) / len(df) * 100) if len(df) > 0 else 0
                    st.metric(label="📈 조회 완료율", value=f"{completion_rate:.0f}%")
                
                st.divider()
                
                # 차트
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("🏭 공정별 화학물질 현황")
                    if '공정명' in df.columns:
                        process_counts = df['공정명'].value_counts()
                        st.bar_chart(process_counts)
                
                with col2:
                    st.subheader("📊 규제 현황")
                    reg_data = {
                        '작업환경측정': get_measurement_target_count(df),
                        '특수건강진단': get_health_exam_target_count(df),
                        'CMR물질': get_cmr_count(df),
                        'PRTR대상': get_prtr_count(df)
                    }
                    st.bar_chart(pd.Series(reg_data))
                
                # 화학물질 목록
                st.divider()
                st.subheader("📝 화학물질 목록 (상위 10건)")
                display_cols = ['공정명', '제품명', '화학물질명', 'CAS No', '노출기준(TWA)', 
                               '작업환경측정', '특수건강진단', 'KOSHA조회상태']
                available_cols = [col for col in display_cols if col in df.columns]
                st.dataframe(df[available_cols].head(10), use_container_width=True)
            else:
                st.warning("인벤토리 데이터가 없습니다.")
        else:
            st.info("👈 사이드바에서 사업장을 선택해주세요.")
    
    # ============================================
    # 📋 인벤토리 조회
    # ============================================
    elif menu == "📋 인벤토리 조회":
        st.markdown('<p class="main-header">📋 인벤토리 조회</p>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">화학물질 목록을 검색하고 필터링하세요</p>', unsafe_allow_html=True)
        
        if selected_company:
            df = load_inventory(selected_company)
            
            if df is not None and len(df) > 0:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    search_term = st.text_input("🔍 검색 (화학물질명, CAS No)", "")
                with col2:
                    if '공정명' in df.columns:
                        processes = ['전체'] + list(df['공정명'].dropna().unique())
                        selected_process = st.selectbox("🏭 공정 필터", processes)
                    else:
                        selected_process = '전체'
                with col3:
                    filter_options = st.multiselect(
                        "⚠️ 규제 필터",
                        ["작업환경측정 대상", "특수건강진단 대상", "PRTR 대상", "KOSHA 미조회"],
                        default=[]
                    )
                
                filtered_df = df.copy()
                
                if search_term:
                    mask = (
                        filtered_df['화학물질명'].astype(str).str.contains(search_term, case=False, na=False) |
                        filtered_df['CAS No'].astype(str).str.contains(search_term, case=False, na=False)
                    )
                    filtered_df = filtered_df[mask]
                
                if selected_process != '전체':
                    filtered_df = filtered_df[filtered_df['공정명'] == selected_process]
                
                if "작업환경측정 대상" in filter_options:
                    filtered_df = filtered_df[filtered_df['작업환경측정'].astype(str).str.contains('O', na=False)]
                if "특수건강진단 대상" in filter_options:
                    filtered_df = filtered_df[filtered_df['특수건강진단'].astype(str).str.contains('O', na=False)]
                if "PRTR 대상" in filter_options:
                    filtered_df = filtered_df[filtered_df['PRTR대상여부'].astype(str).isin(['Y', 'O'])]
                if "KOSHA 미조회" in filter_options:
                    filtered_df = filtered_df[filtered_df['KOSHA조회상태'].astype(str) != '성공']
                
                st.info(f"검색 결과: **{len(filtered_df)}건** / 전체 {len(df)}건")
                
                display_cols = st.multiselect(
                    "표시할 컬럼",
                    df.columns.tolist(),
                    default=['공정명', '제품명', '화학물질명', 'CAS No', '함유량(%)', '노출기준(TWA)', 
                             '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질', 'KOSHA조회상태']
                )
                
                if display_cols:
                    st.dataframe(filtered_df[display_cols], use_container_width=True, height=500)
                
                st.divider()
                
                @st.cache_data
                def convert_df_to_excel(df):
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False)
                    return output.getvalue()
                
                excel_data = convert_df_to_excel(filtered_df)
                st.download_button(
                    label="📥 엑셀 다운로드",
                    data=excel_data,
                    file_name=f"{selected_company}_인벤토리.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("인벤토리 데이터가 없습니다.")
        else:
            st.info("👈 사이드바에서 사업장을 선택해주세요.")
    
    # ============================================
    # 🔍 KOSHA 조회 (신규 메뉴!)
    # ============================================
    elif menu == "🔍 KOSHA 조회" and KOSHA_AVAILABLE:
        st.markdown('<p class="main-header">🔍 KOSHA API 조회</p>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">CAS 번호로 화학물질 규제정보를 자동 조회합니다</p>', unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["🔢 개별 조회", "📤 인벤토리 일괄 조회"])
        
        # ---- 탭 1: 개별 조회 ----
        with tab1:
            st.subheader("🔢 CAS 번호로 개별 조회")
            
            col1, col2 = st.columns([3, 1])
            with col1:
                cas_input = st.text_input("CAS 번호 입력", placeholder="예: 67-64-1", key="single_cas")
            with col2:
                st.write("")
                st.write("")
                search_btn = st.button("🔍 조회", type="primary", key="single_search")
            
            if search_btn and cas_input:
                with st.spinner(f"'{cas_input}' 조회 중..."):
                    result = get_chemical_info(cas_input.strip())
                
                if result['success']:
                    st.success(f"✅ 조회 성공: **{result['화학물질명']}**")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("#### 📌 기본 정보")
                        st.markdown(f"""
                        | 항목 | 값 |
                        |------|-----|
                        | **물질명** | {result['화학물질명']} |
                        | **CAS No** | {result['CAS No']} |
                        | **노출기준(TWA)** | {result['노출기준(TWA)']} |
                        | **STEL** | {result.get('STEL', '-')} |
                        """)
                        
                        st.markdown("#### 🧬 CMR 정보")
                        st.markdown(f"""
                        | 항목 | 분류 |
                        |------|------|
                        | **발암성** | {result['발암성']} |
                        | **변이성** | {result['변이성']} |
                        | **생식독성** | {result['생식독성']} |
                        | **IARC** | {result['IARC']} |
                        | **ACGIH** | {result['ACGIH']} |
                        """)
                    
                    with col2:
                        st.markdown("#### ⚖️ 산안법 규제")
                        
                        def badge(val):
                            return '🟢 **O**' if val == 'O' else '⚪ X'
                        
                        st.markdown(f"""
                        | 규제 | 해당 |
                        |------|------|
                        | **작업환경측정** | {badge(result['작업환경측정'])} |
                        | **특수건강진단** | {badge(result['특수건강진단'])} |
                        | **관리대상유해물질** | {badge(result['관리대상유해물질'])} |
                        | **특별관리물질** | {badge(result['특별관리물질'])} |
                        | **PRTR대상** | {badge(result['PRTR대상'])} ({result['PRTR그룹']}) |
                        """)
                        
                        st.markdown("#### 📜 화관법/위험물")
                        st.markdown(f"""
                        | 항목 | 내용 |
                        |------|------|
                        | **유독물질** | {result['유독']} |
                        | **사고대비물질** | {result['사고대비']} |
                        | **제한/금지/허가** | {result['제한/금지/허가']} |
                        | **위험물** | {result.get('위험물', '해당없음')} |
                        """)
                else:
                    st.error(f"❌ 조회 실패: {result.get('error', '미등록 물질')}")
        
        # ---- 탭 2: 인벤토리 일괄 조회 ----
        with tab2:
            st.subheader("📤 인벤토리 일괄 조회")
            st.markdown("등록된 인벤토리의 CAS 번호를 KOSHA API로 일괄 조회하여 규제정보를 자동으로 채웁니다.")
            
            if selected_company:
                df = load_inventory(selected_company)
                
                if df is not None and len(df) > 0:
                    if 'CAS No' in df.columns:
                        # CAS 번호 목록 추출
                        cas_list = df['CAS No'].dropna().unique().tolist()
                        cas_list = [c for c in cas_list if str(c).strip() and '-' in str(c)]
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("📊 조회 대상", f"{len(cas_list)}개")
                        with col2:
                            already_done = get_kosha_queried_count(df)
                            st.metric("✅ 조회 완료", f"{already_done}건")
                        with col3:
                            remaining = len(cas_list) - already_done
                            st.metric("⏳ 미조회", f"{max(0, remaining)}건")
                        
                        st.divider()
                        
                        if st.button("🚀 일괄 조회 시작", type="primary", use_container_width=True):
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            log_container = st.container()
                            
                            logs = []
                            success_count = 0
                            
                            for idx, cas_no in enumerate(cas_list):
                                status_text.text(f"조회 중... [{idx+1}/{len(cas_list)}] {cas_no}")
                                
                                result = get_chemical_info(cas_no)
                                
                                # 해당 CAS 번호의 모든 행 업데이트
                                mask = df['CAS No'].astype(str).str.strip() == str(cas_no).strip()
                                
                                if result['success']:
                                    # 기존 컬럼에 맞춰 업데이트
                                    df.loc[mask, '화학물질명'] = result['화학물질명']
                                    df.loc[mask, '노출기준(TWA)'] = result['노출기준(TWA)']
                                    df.loc[mask, '발암성'] = result['발암성']
                                    df.loc[mask, '변이성'] = result['변이성']
                                    df.loc[mask, '생식독성'] = result['생식독성']
                                    df.loc[mask, '작업환경측정'] = result['작업환경측정']
                                    df.loc[mask, '특수건강진단'] = result['특수건강진단']
                                    df.loc[mask, '관리대상유해물질'] = result['관리대상유해물질']
                                    df.loc[mask, '특별관리물질'] = result['특별관리물질']
                                    df.loc[mask, '유독'] = result['유독']
                                    df.loc[mask, '사고대비'] = result['사고대비']
                                    df.loc[mask, '제한/금지/허가'] = result['제한/금지/허가']
                                    df.loc[mask, 'PRTR대상여부'] = result['PRTR대상']
                                    df.loc[mask, 'KOSHA조회상태'] = '성공'
                                    df.loc[mask, 'KOSHA조회일'] = datetime.now().strftime('%Y-%m-%d')
                                    
                                    logs.append(f"✅ {cas_no}: {result['화학물질명']}")
                                    success_count += 1
                                else:
                                    df.loc[mask, 'KOSHA조회상태'] = '실패'
                                    df.loc[mask, 'KOSHA조회일'] = datetime.now().strftime('%Y-%m-%d')
                                    logs.append(f"❌ {cas_no}: 미등록")
                                
                                progress_bar.progress((idx + 1) / len(cas_list))
                                
                                with log_container:
                                    st.text_area("조회 로그", "\n".join(logs[-15:]), height=200, key=f"log_{idx}")
                            
                            # 저장
                            if save_inventory(selected_company, df):
                                st.success(f"🎉 조회 완료! **{success_count}/{len(cas_list)}건** 성공")
                                st.balloons()
                            else:
                                st.error("저장 실패")
                    else:
                        st.warning("'CAS No' 컬럼이 없습니다.")
                else:
                    st.warning("인벤토리 데이터가 없습니다.")
            else:
                st.info("👈 사이드바에서 사업장을 선택해주세요.")
    
    # ============================================
    # 📊 배출량 산정
    # ============================================
    elif menu == "📊 배출량 산정":
        st.markdown('<p class="main-header">📊 배출량 산정</p>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">통합환경법 기준 배출량을 산정하세요</p>', unsafe_allow_html=True)
        
        if selected_company:
            df = load_inventory(selected_company)
            calc = IntegratedEmissionCalculator()
            
            tab1, tab2 = st.tabs(["🔢 개별 산정", "📤 일괄 산정"])
            
            with tab1:
                st.subheader("🔢 화학물질별 개별 산정")
                
                if df is not None and len(df) > 0:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        chemical_options = df['화학물질명'].dropna().unique().tolist()
                        if chemical_options:
                            selected_chemical = st.selectbox("화학물질 선택", chemical_options)
                            chem_row = df[df['화학물질명'] == selected_chemical].iloc[0]
                            st.markdown(f"""
                            **CAS No:** {chem_row.get('CAS No', '-')}  
                            **현재 취급량:** {chem_row.get('연간취급량(kg)', '미입력')} kg  
                            **현재 배출량:** {chem_row.get('대기배출량(kg/년)', '미산정')} kg/년
                            """)
                        else:
                            selected_chemical = None
                            st.warning("화학물질이 없습니다.")
                    
                    with col2:
                        method = st.selectbox("산정방법", ["물질수지법 (Tier 3)", "배출계수법 (Tier 4)"])
                    
                    if selected_chemical:
                        st.divider()
                        
                        if "물질수지" in method:
                            st.markdown("#### 📐 물질수지법")
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                input_amt = st.number_input("투입량 (kg/년)", min_value=0.0, value=0.0, step=100.0)
                            with col2:
                                recovery_amt = st.number_input("회수량 (kg/년)", min_value=0.0, value=0.0, step=100.0)
                            with col3:
                                destruction_amt = st.number_input("파괴량 (kg/년)", min_value=0.0, value=0.0, step=100.0)
                            
                            if st.button("🧮 계산", key="calc_mass"):
                                emission = calc.calculate_simple_mass_balance(input_amt, recovery_amt, destruction_amt)
                                st.success(f"**대기배출량: {emission:,.2f} kg/년**")
                                
                                if st.button("💾 저장", key="save_mass"):
                                    idx = df[df['화학물질명'] == selected_chemical].index[0]
                                    df.at[idx, '연간취급량(kg)'] = input_amt
                                    df.at[idx, '대기배출량(kg/년)'] = emission
                                    df.at[idx, '배출산정방법'] = '물질수지법'
                                    df.at[idx, '산정기준일'] = datetime.now().strftime('%Y-%m-%d')
                                    df.at[idx, 'PRTR대상여부'] = 'Y' if input_amt >= 1000 else 'N'
                                    save_inventory(selected_company, df)
                                    st.success("✅ 저장!")
                                    st.rerun()
                        else:
                            st.markdown("#### 📊 배출계수법")
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                activity_amt = st.number_input("활동량 (단위/년)", min_value=0.0, step=100.0)
                            with col2:
                                ef = st.number_input("배출계수 (kg/단위)", min_value=0.0, step=0.001, format="%.4f")
                            with col3:
                                efficiency = st.number_input("방지효율 (%)", min_value=0.0, max_value=100.0, step=1.0)
                            
                            if st.button("🧮 계산", key="calc_ef"):
                                emission = calc.calculate_simple_emission_factor(activity_amt, ef, efficiency)
                                st.success(f"**대기배출량: {emission:,.2f} kg/년**")
                else:
                    st.warning("인벤토리 데이터가 없습니다.")
            
            with tab2:
                st.subheader("📤 엑셀 일괄 산정")
                template_data = generate_emission_template()
                st.download_button(
                    label="📥 템플릿 다운로드",
                    data=template_data,
                    file_name='emission_template.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                )
        else:
            st.info("👈 사이드바에서 사업장을 선택해주세요.")
    
    # ============================================
    # 📤 데이터 업로드 (관리자)
    # ============================================
    elif menu == "📤 데이터 업로드" and is_admin:
        st.markdown('<p class="main-header">📤 데이터 업로드</p>', unsafe_allow_html=True)
        
        company_name = st.text_input("🏭 사업장명", placeholder="예: 신우중공업_인벤토리")
        
        uploaded_file = st.file_uploader("엑셀 파일 선택", type=['xlsx', 'xls'])
        
        if uploaded_file and company_name:
            try:
                df = load_inventory_from_upload(uploaded_file)
                st.success(f"✅ 로드 완료: {len(df)}개 화학물질")
                st.dataframe(df.head(10), use_container_width=True)
                
                if st.button("💾 저장", type="primary"):
                    save_inventory(company_name, df)
                    st.success(f"✅ '{company_name}' 저장 완료!")
                    st.balloons()
            except Exception as e:
                st.error(f"오류: {str(e)}")
    
    # ============================================
    # 🏢 사업장 관리 (관리자)
    # ============================================
    elif menu == "🏢 사업장 관리" and is_admin:
        st.markdown('<p class="main-header">🏢 사업장 관리</p>', unsafe_allow_html=True)
        
        companies = get_all_companies()
        
        if companies:
            st.info(f"총 **{len(companies)}개** 사업장")
            
            company_data = []
            for company in companies:
                df = load_inventory(company)
                if df is not None:
                    company_data.append({
                        "사업장명": company,
                        "화학물질 수": len(df),
                        "작업환경측정": get_measurement_target_count(df),
                        "PRTR 대상": get_prtr_count(df),
                        "KOSHA 조회완료": get_kosha_queried_count(df)
                    })
            
            st.dataframe(pd.DataFrame(company_data), use_container_width=True)
        else:
            st.info("등록된 사업장이 없습니다.")
    
    # ============================================
    # 👥 사용자 관리 (관리자)
    # ============================================
    elif menu == "👥 사용자 관리" and is_admin:
        st.markdown('<p class="main-header">👥 사용자 관리</p>', unsafe_allow_html=True)
        
        config = load_config()
        users = config.get('credentials', {}).get('usernames', {})
        
        user_data = []
        for username, info in users.items():
            user_data.append({
                "아이디": username,
                "이름": info.get('name', ''),
                "권한": "관리자" if info.get('role') == 'admin' else "담당자",
                "사업장": ", ".join(info.get('companies', []))
            })
        
        st.dataframe(pd.DataFrame(user_data), use_container_width=True)

# ============================================
# 메인 실행
# ============================================
if st.session_state.authenticated:
    show_main_app()
else:
    show_login()
