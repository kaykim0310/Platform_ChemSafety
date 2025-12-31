import streamlit as st
import pandas as pd
import yaml
import bcrypt
import io
from pathlib import Path
from yaml.loader import SafeLoader
from datetime import datetime

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
        # 1. TMS Data
        pd.DataFrame({
            '측정일시': ['2024-01-01 10:00'],
            '오염물질명': ['NOx'],
            '측정농도(mg/Sm3)': [15.5],
            '배출가스유량(Sm3/hr)': [50000],
            '실측산소농도(%)': [5.2],
            '표준산소농도(%)': [4],
            '상태코드': [0]
        }).to_excel(writer, sheet_name='1_TMS_Data', index=False)
        
        # 2. Self Measurement
        pd.DataFrame({
            '측정기간(월/분기)': ['1월'],
            '오염물질명': ['Dust'],
            '평균측정농도(mg/Sm3)': [10.5],
            '평균배출유량(Sm3/hr)': [45000],
            '실제조업시간(hr)': [720]
        }).to_excel(writer, sheet_name='2_Self_Measurement', index=False)
        
        # 3. Mass Balance
        pd.DataFrame({
            '관리기간': ['1분기'],
            '사용물질명': ['Toluene'],
            '투입량(kg)': [1000],
            '회수량(kg)': [400],
            '파괴량(kg)': [500]
        }).to_excel(writer, sheet_name='3_Mass_Balance', index=False)
        
        # 4. Emission Factor
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
# 인벤토리 컬럼 정의 (기존 + 배출량)
INVENTORY_COLUMNS = [
    '공정명', '제품명', '화학물질명', '관용명/이명', 'CAS No', '함유량(%)',
    '발암성', '변이성', '생식독성', '노출기준(TWA)',
    '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질',
    '기존', '유독', '사고대비', '제한/금지/허가', '중점', '잔류',
    '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부',
    # 배출량 관련 컬럼 (추가)
    '연간취급량(kg)', '대기배출량(kg/년)', '수계배출량(kg/년)', 
    '폐기물이동량(kg/년)', '배출산정방법', '산정기준일', 'PRTR대상여부'
]

def load_inventory(company_name):
    """사업장 인벤토리 로드 (Windows 호환)"""
    file_path = DATA_DIR / f"{company_name}.xlsx"
    if file_path.exists():
        try:
            # 파일을 바이트로 읽어서 메모리에서 처리 (파일 핸들 즉시 해제)
            with open(file_path, 'rb') as f:
                file_bytes = io.BytesIO(f.read())
            df = pd.read_excel(file_bytes, sheet_name=0, engine='openpyxl')
            file_bytes.close()
            
            # 배출량 컬럼이 없으면 추가
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
    # BytesIO로 변환해서 처리
    file_bytes = io.BytesIO(uploaded_file.read())
    df = pd.read_excel(file_bytes, sheet_name=0, header=None, skiprows=2, engine='openpyxl')
    file_bytes.close()
    
    # 기존 23개 컬럼
    base_columns = [
        '공정명', '제품명', '화학물질명', '관용명/이명', 'CAS No', '함유량(%)',
        '발암성', '변이성', '생식독성', '노출기준(TWA)',
        '작업환경측정', '특수건강진단', '관리대상유해물질', '특별관리물질',
        '기존', '유독', '사고대비', '제한/금지/허가', '중점', '잔류',
        '함량 및 규제정보', '등록대상기존화학물질', '기존물질여부'
    ]
    df.columns = base_columns
    # 배출량 컬럼 추가
    df['연간취급량(kg)'] = None
    df['대기배출량(kg/년)'] = None
    df['수계배출량(kg/년)'] = None
    df['폐기물이동량(kg/년)'] = None
    df['배출산정방법'] = None
    df['산정기준일'] = None
    df['PRTR대상여부'] = None
    return df

def save_inventory(company_name, df):
    """사업장 인벤토리 저장 (Windows 호환)"""
    file_path = DATA_DIR / f"{company_name}.xlsx"
    try:
        import gc
        import time
        gc.collect()
        time.sleep(0.2)
        
        # 먼저 BytesIO에 저장
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        
        # 파일로 쓰기
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
    """PRTR 대상 물질 수"""
    if '연간취급량(kg)' in df.columns:
        return df['연간취급량(kg)'].apply(lambda x: float(x) >= 1000 if pd.notna(x) else False).sum()
    return 0

def get_total_emission(df):
    """총 배출량 합계"""
    if '대기배출량(kg/년)' in df.columns:
        return df['대기배출량(kg/년)'].apply(lambda x: float(x) if pd.notna(x) else 0).sum()
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
        
        # 메뉴
        if is_admin:
            menu = st.radio(
                "메뉴",
                ["🏠 대시보드", "📋 인벤토리 조회", "📊 배출량 산정", "📤 데이터 업로드", "🏢 사업장 관리", "👥 사용자 관리"],
                label_visibility="collapsed"
            )
        else:
            menu = st.radio(
                "메뉴",
                ["🏠 대시보드", "📋 인벤토리 조회", "📊 배출량 산정"],
                label_visibility="collapsed"
            )
        
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
                # 주요 지표 (1행)
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(label="📦 등록 화학물질", value=f"{len(df)}종")
                with col2:
                    st.metric(label="⚠️ CMR 물질", value=f"{get_cmr_count(df)}종")
                with col3:
                    st.metric(label="🔬 작업환경측정 대상", value=f"{get_measurement_target_count(df)}종")
                with col4:
                    st.metric(label="🏥 특수건강진단 대상", value=f"{get_health_exam_target_count(df)}종")
                
                # 배출량 지표 (2행)
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    total_emission = get_total_emission(df)
                    st.metric(label="🏭 총 대기배출량", value=f"{total_emission:,.1f} kg/년")
                with col2:
                    prtr_count = get_prtr_count(df)
                    st.metric(label="📋 PRTR 대상", value=f"{prtr_count}종")
                with col3:
                    emission_calculated = df['대기배출량(kg/년)'].notna().sum()
                    st.metric(label="✅ 배출량 산정 완료", value=f"{emission_calculated}종")
                with col4:
                    completion_rate = (emission_calculated / len(df) * 100) if len(df) > 0 else 0
                    st.metric(label="📈 산정 완료율", value=f"{completion_rate:.0f}%")
                
                st.divider()
                
                # 차트
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("🏭 공정별 화학물질 현황")
                    if '공정명' in df.columns:
                        process_counts = df['공정명'].value_counts()
                        st.bar_chart(process_counts)
                
                with col2:
                    st.subheader("📊 배출량 산정방법별 현황")
                    if '배출산정방법' in df.columns:
                        method_counts = df['배출산정방법'].value_counts()
                        if not method_counts.empty:
                            st.bar_chart(method_counts)
                        else:
                            st.info("아직 산정된 배출량이 없습니다.")
                
                # 최근 등록 물질
                st.divider()
                st.subheader("📝 화학물질 목록 (상위 10건)")
                display_cols = ['공정명', '제품명', '화학물질명', 'CAS No', '연간취급량(kg)', '대기배출량(kg/년)', '배출산정방법']
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
                        ["작업환경측정 대상", "특수건강진단 대상", "PRTR 대상", "배출량 미산정"],
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
                    filtered_df = filtered_df[filtered_df['연간취급량(kg)'].apply(lambda x: float(x) >= 1000 if pd.notna(x) else False)]
                if "배출량 미산정" in filter_options:
                    filtered_df = filtered_df[filtered_df['대기배출량(kg/년)'].isna()]
                
                st.info(f"검색 결과: **{len(filtered_df)}건** / 전체 {len(df)}건")
                
                display_cols = st.multiselect(
                    "표시할 컬럼",
                    df.columns.tolist(),
                    default=['공정명', '제품명', '화학물질명', 'CAS No', '함유량(%)', '노출기준(TWA)', 
                             '작업환경측정', '특수건강진단', '연간취급량(kg)', '대기배출량(kg/년)', '배출산정방법']
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
    # 📊 배출량 산정
    # ============================================
    elif menu == "📊 배출량 산정":
        st.markdown('<p class="main-header">📊 배출량 산정</p>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">통합환경법 기준 배출량을 산정하세요</p>', unsafe_allow_html=True)
        
        if selected_company:
            df = load_inventory(selected_company)
            calc = IntegratedEmissionCalculator()
            
            tab1, tab2 = st.tabs(["🔢 개별 산정 (인벤토리 연동)", "📤 일괄 산정 (엑셀 업로드)"])
            
            # ---- 탭 1: 개별 산정 ----
            with tab1:
                st.subheader("🔢 화학물질별 개별 산정")
                
                if df is not None and len(df) > 0:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # 화학물질 선택
                        chemical_options = df['화학물질명'].dropna().unique().tolist()
                        selected_chemical = st.selectbox("화학물질 선택", chemical_options)
                        
                        # 선택된 화학물질 정보
                        chem_row = df[df['화학물질명'] == selected_chemical].iloc[0]
                        st.markdown(f"""
                        **CAS No:** {chem_row.get('CAS No', '-')}  
                        **현재 취급량:** {chem_row.get('연간취급량(kg)', '미입력')} kg  
                        **현재 배출량:** {chem_row.get('대기배출량(kg/년)', '미산정')} kg/년
                        """)
                    
                    with col2:
                        # 산정방법 선택
                        method = st.selectbox(
                            "산정방법 선택",
                            ["물질수지법 (Tier 3)", "배출계수법 (Tier 4)"]
                        )
                    
                    st.divider()
                    
                    # 물질수지법
                    if "물질수지" in method:
                        st.markdown("#### 📐 물질수지법 (투입량 - 회수량 - 파괴량)")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            input_amt = st.number_input("투입량 (kg/년)", min_value=0.0, value=0.0, step=100.0)
                        with col2:
                            recovery_amt = st.number_input("회수량 (kg/년)", min_value=0.0, value=0.0, step=100.0)
                        with col3:
                            destruction_amt = st.number_input("파괴량 (kg/년)", min_value=0.0, value=0.0, step=100.0)
                        
                        if st.button("🧮 계산하기", key="calc_mass"):
                            emission = calc.calculate_simple_mass_balance(input_amt, recovery_amt, destruction_amt)
                            
                            st.markdown(f"""
                            <div class="result-box">
                                <h3>계산 결과</h3>
                                <p><strong>대기배출량:</strong> {emission:,.2f} kg/년</p>
                                <p><strong>산정방법:</strong> 물질수지법</p>
                                <p><strong>계산식:</strong> {input_amt:,.0f} - {recovery_amt:,.0f} - {destruction_amt:,.0f} = {emission:,.2f}</p>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # 인벤토리 저장
                            if st.button("💾 인벤토리에 저장", key="save_mass"):
                                idx = df[df['화학물질명'] == selected_chemical].index[0]
                                df.at[idx, '연간취급량(kg)'] = input_amt
                                df.at[idx, '대기배출량(kg/년)'] = emission
                                df.at[idx, '배출산정방법'] = '물질수지법'
                                df.at[idx, '산정기준일'] = datetime.now().strftime('%Y-%m-%d')
                                df.at[idx, 'PRTR대상여부'] = 'Y' if input_amt >= 1000 else 'N'
                                save_inventory(selected_company, df)
                                st.success("✅ 저장 완료!")
                                st.rerun()
                    
                    # 배출계수법
                    else:
                        st.markdown("#### 📊 배출계수법 (활동량 × 배출계수 × (1-방지효율))")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            activity_amt = st.number_input("활동량 (단위/년)", min_value=0.0, value=0.0, step=100.0)
                        with col2:
                            ef = st.number_input("배출계수 (kg/단위)", min_value=0.0, value=0.0, step=0.001, format="%.4f")
                        with col3:
                            efficiency = st.number_input("방지시설효율 (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
                        
                        if st.button("🧮 계산하기", key="calc_ef"):
                            emission = calc.calculate_simple_emission_factor(activity_amt, ef, efficiency)
                            
                            st.markdown(f"""
                            <div class="result-box">
                                <h3>계산 결과</h3>
                                <p><strong>대기배출량:</strong> {emission:,.2f} kg/년</p>
                                <p><strong>산정방법:</strong> 배출계수법</p>
                                <p><strong>계산식:</strong> {activity_amt:,.0f} × {ef:.4f} × (1 - {efficiency:.0f}/100) = {emission:,.2f}</p>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            if st.button("💾 인벤토리에 저장", key="save_ef"):
                                idx = df[df['화학물질명'] == selected_chemical].index[0]
                                df.at[idx, '연간취급량(kg)'] = activity_amt
                                df.at[idx, '대기배출량(kg/년)'] = emission
                                df.at[idx, '배출산정방법'] = '배출계수법'
                                df.at[idx, '산정기준일'] = datetime.now().strftime('%Y-%m-%d')
                                df.at[idx, 'PRTR대상여부'] = 'Y' if activity_amt >= 1000 else 'N'
                                save_inventory(selected_company, df)
                                st.success("✅ 저장 완료!")
                                st.rerun()
                else:
                    st.warning("인벤토리 데이터가 없습니다. 먼저 데이터를 업로드해주세요.")
            
            # ---- 탭 2: 일괄 산정 ----
            with tab2:
                st.subheader("📤 엑셀 일괄 산정")
                st.markdown("통합환경법 4가지 산정방법(Tier 1~4)을 일괄 계산합니다.")
                
                # 템플릿 다운로드
                template_data = generate_emission_template()
                st.download_button(
                    label="📥 산정용 엑셀 템플릿 다운로드",
                    data=template_data,
                    file_name='emission_calc_template.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                )
                
                st.divider()
                
                # 파일 업로드
                uploaded_emission = st.file_uploader("작성된 엑셀 파일 업로드", type=['xlsx'], key="emission_upload")
                
                if uploaded_emission:
                    st.success("파일 분석을 시작합니다...")
                    
                    total_emission = 0.0
                    results_list = []
                    
                    try:
                        # BytesIO로 읽어서 처리 (파일 핸들 이슈 방지)
                        file_bytes = io.BytesIO(uploaded_emission.read())
                        xls = pd.ExcelFile(file_bytes, engine='openpyxl')
                        
                        # Tier 1 (TMS)
                        if '1_TMS_Data' in xls.sheet_names:
                            df_tms = pd.read_excel(xls, '1_TMS_Data').fillna(0)
                            std_o2 = df_tms['표준산소농도(%)'].iloc[0] if not df_tms.empty else None
                            val = calc.calculate_tms(df_tms, std_o2)
                            results_list.append({"구분": "Tier 1 (TMS)", "설명": "실시간 자동 측정", "배출량(kg)": val})
                            total_emission += val

                        # Tier 2 (자가측정)
                        if '2_Self_Measurement' in xls.sheet_names:
                            df_self = pd.read_excel(xls, '2_Self_Measurement').fillna(0)
                            val = calc.calculate_self_measurement(df_self)
                            results_list.append({"구분": "Tier 2 (자가측정)", "설명": "수동 주기적 측정", "배출량(kg)": val})
                            total_emission += val

                        # Tier 3 (물질수지)
                        if '3_Mass_Balance' in xls.sheet_names:
                            df_mass = pd.read_excel(xls, '3_Mass_Balance').fillna(0)
                            val = calc.calculate_mass_balance(df_mass)
                            results_list.append({"구분": "Tier 3 (물질수지)", "설명": "투입-회수-파괴", "배출량(kg)": val})
                            total_emission += val
                            
                        # Tier 4 (배출계수)
                        if '4_Emission_Factor' in xls.sheet_names:
                            df_factor = pd.read_excel(xls, '4_Emission_Factor').fillna(0)
                            val = calc.calculate_emission_factor(df_factor)
                            results_list.append({"구분": "Tier 4 (배출계수)", "설명": "활동량 × 계수", "배출량(kg)": val})
                            total_emission += val
                        
                        # 파일 닫기
                        xls.close()
                        file_bytes.close()

                        # 결과 출력
                        st.subheader("📊 산정 결과 리포트")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric(label="총 연간 배출량", value=f"{total_emission:,.2f} kg")
                        with col2:
                            st.info("각 산정 방식(Tier)별 합계입니다.")
                            
                        result_df = pd.DataFrame(results_list)
                        result_df['배출량(kg)'] = result_df['배출량(kg)'].apply(lambda x: f"{x:,.2f}")
                        st.table(result_df)
                        
                        if total_emission > 0:
                            chart_df = pd.DataFrame(results_list).set_index("구분")
                            st.bar_chart(chart_df['배출량(kg)'])

                    except Exception as e:
                        st.error(f"오류가 발생했습니다: {e}")
                        st.warning("엑셀 파일의 시트 이름이나 컬럼명이 템플릿과 일치하는지 확인해주세요.")
        else:
            st.info("👈 사이드바에서 사업장을 선택해주세요.")
    
    # ============================================
    # 📤 데이터 업로드 (관리자 전용)
    # ============================================
    elif menu == "📤 데이터 업로드" and is_admin:
        st.markdown('<p class="main-header">📤 데이터 업로드</p>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">엑셀 인벤토리 파일을 업로드하세요</p>', unsafe_allow_html=True)
        
        company_name = st.text_input("🏭 사업장명", placeholder="예: 신우중공업_인벤토리")
        
        uploaded_file = st.file_uploader(
            "엑셀 파일 선택",
            type=['xlsx', 'xls'],
            help="힐스 인벤토리 서식에 맞는 엑셀 파일을 업로드하세요"
        )
        
        if uploaded_file and company_name:
            try:
                df = load_inventory_from_upload(uploaded_file)
                
                st.success(f"✅ 파일 로드 완료: {len(df)}개 화학물질")
                
                st.subheader("📋 데이터 미리보기")
                st.dataframe(df.head(10), use_container_width=True)
                
                if st.button("💾 저장하기", type="primary"):
                    save_inventory(company_name, df)
                    st.success(f"✅ '{company_name}' 인벤토리가 저장되었습니다!")
                    st.balloons()
                    
            except Exception as e:
                st.error(f"❌ 파일 처리 중 오류가 발생했습니다: {str(e)}")
        
        elif uploaded_file and not company_name:
            st.warning("⚠️ 사업장명을 입력해주세요.")
    
    # ============================================
    # 🏢 사업장 관리 (관리자 전용)
    # ============================================
    elif menu == "🏢 사업장 관리" and is_admin:
        st.markdown('<p class="main-header">🏢 사업장 관리</p>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">등록된 사업장 목록을 관리하세요</p>', unsafe_allow_html=True)
        
        companies = get_all_companies()
        
        if companies:
            st.info(f"총 **{len(companies)}개** 사업장이 등록되어 있습니다.")
            
            company_data = []
            for company in companies:
                df = load_inventory(company)
                if df is not None:
                    company_data.append({
                        "사업장명": company,
                        "화학물질 수": len(df),
                        "작업환경측정 대상": get_measurement_target_count(df),
                        "CMR 물질": get_cmr_count(df),
                        "총 배출량(kg/년)": f"{get_total_emission(df):,.1f}",
                        "PRTR 대상": get_prtr_count(df)
                    })
            
            company_df = pd.DataFrame(company_data)
            st.dataframe(company_df, use_container_width=True)
            
            st.divider()
            st.subheader("🗑️ 사업장 삭제")
            
            delete_company = st.selectbox("삭제할 사업장 선택", companies)
            
            col1, col2 = st.columns([1, 4])
            with col1:
                delete_clicked = st.button("🗑️ 삭제", type="secondary")
            with col2:
                st.caption("⚠️ 삭제 전 해당 파일이 다른 프로그램(엑셀 등)에서 열려있지 않은지 확인하세요.")
            
            if delete_clicked:
                file_path = DATA_DIR / f"{delete_company}.xlsx"
                if file_path.exists():
                    # 메모리 정리 강화
                    import gc
                    import time
                    gc.collect()
                    time.sleep(0.5)  # 잠시 대기
                    gc.collect()
                    
                    # 삭제 시도 (최대 3회)
                    deleted = False
                    for attempt in range(3):
                        try:
                            import os
                            os.remove(str(file_path))
                            deleted = True
                            break
                        except PermissionError:
                            gc.collect()
                            time.sleep(0.5)
                        except Exception as e:
                            st.error(f"❌ 삭제 오류: {str(e)}")
                            break
                    
                    if deleted:
                        st.success(f"✅ '{delete_company}'가 삭제되었습니다.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ 파일 삭제에 실패했습니다. 다음을 확인해주세요:")
                        st.markdown("""
                        1. 해당 엑셀 파일이 다른 프로그램에서 열려있지 않은지 확인
                        2. Streamlit 앱을 완전히 종료 후 재시작
                        3. 수동으로 `data/companies/` 폴더에서 파일 삭제
                        """)
        else:
            st.info("등록된 사업장이 없습니다. 데이터를 업로드해주세요.")
    
    # ============================================
    # 👥 사용자 관리 (관리자 전용)
    # ============================================
    elif menu == "👥 사용자 관리" and is_admin:
        st.markdown('<p class="main-header">👥 사용자 관리</p>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">시스템 사용자를 관리하세요</p>', unsafe_allow_html=True)
        
        config = load_config()
        users = config.get('credentials', {}).get('usernames', {})
        
        st.subheader("📋 등록된 사용자")
        
        user_data = []
        for username, info in users.items():
            user_data.append({
                "아이디": username,
                "이름": info.get('name', ''),
                "이메일": info.get('email', ''),
                "권한": "관리자" if info.get('role') == 'admin' else "사업장 담당자",
                "접근 가능 사업장": ", ".join(info.get('companies', []))
            })
        
        user_df = pd.DataFrame(user_data)
        st.dataframe(user_df, use_container_width=True)
        
        st.divider()
        
        st.subheader("➕ 새 사용자 추가")
        
        with st.form("add_user_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                new_username = st.text_input("아이디", placeholder="영문 소문자")
                new_name = st.text_input("이름", placeholder="홍길동")
                new_email = st.text_input("이메일", placeholder="user@company.com")
            
            with col2:
                new_password = st.text_input("비밀번호", type="password")
                new_role = st.selectbox("권한", ["user", "admin"])
                
                all_companies = get_all_companies()
                if new_role == "admin":
                    new_companies = ["ALL"]
                    st.info("관리자는 모든 사업장에 접근 가능합니다.")
                else:
                    new_companies = st.multiselect("접근 가능 사업장", all_companies)
            
            submit = st.form_submit_button("👤 사용자 추가", type="primary")
            
            if submit:
                if new_username and new_name and new_password:
                    if new_username in users:
                        st.error("❌ 이미 존재하는 아이디입니다.")
                    else:
                        config['credentials']['usernames'][new_username] = {
                            'name': new_name,
                            'password': hash_password(new_password),
                            'email': new_email,
                            'role': new_role,
                            'companies': new_companies if new_role != 'admin' else ['ALL']
                        }
                        save_config(config)
                        st.success(f"✅ '{new_name}' 사용자가 추가되었습니다!")
                        st.rerun()
                else:
                    st.warning("⚠️ 아이디, 이름, 비밀번호는 필수입니다.")
        
        st.divider()
        
        st.subheader("🗑️ 사용자 삭제")
        
        deletable_users = [u for u in users.keys() if u != 'admin']
        if deletable_users:
            delete_user = st.selectbox("삭제할 사용자", deletable_users)
            
            if st.button("🗑️ 사용자 삭제", type="secondary"):
                del config['credentials']['usernames'][delete_user]
                save_config(config)
                st.success(f"'{delete_user}' 사용자가 삭제되었습니다.")
                st.rerun()
        else:
            st.info("삭제 가능한 사용자가 없습니다. (관리자는 삭제 불가)")

# ============================================
# 메인 실행
# ============================================
if st.session_state.authenticated:
    show_main_app()
else:
    show_login()
