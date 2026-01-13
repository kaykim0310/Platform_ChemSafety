#!/usr/bin/env python3
"""
📦 인벤토리 관리 페이지
"""
import streamlit as st

st.set_page_config(page_title="인벤토리 관리", page_icon="📦", layout="wide")

st.title("📦 인벤토리 관리")
st.markdown("---")

st.info("🚧 이 모듈은 기존 화학물질관리시스템의 인벤토리 기능을 모듈화하여 제공합니다.")

st.markdown("""
### 주요 기능
- 📋 사업장별 화학물질 목록 관리
- 🔍 KOSHA API 연동 규제정보 자동 조회
- ⚠️ 작업환경측정 / 특수건강진단 대상 확인
- 📊 CMR 물질, PRTR 대상물질 현황
- 📤 엑셀 업로드 / 다운로드

### 개발 상태
- ✅ 기본 구조 설계 완료
- 🔄 기존 시스템 코드 이관 중
- ⏳ 2025년 1월 말 출시 예정
""")

if st.button("🏠 홈으로 돌아가기"):
    st.switch_page("main.py")
