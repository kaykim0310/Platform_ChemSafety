#!/usr/bin/env python3
"""
📄 MSDS 작성 페이지
- 통합 플랫폼에서 호출
"""
import sys
from pathlib import Path

# 모듈 경로 추가
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))

# MSDS 앱 실행
app_path = current_dir / "modules" / "msds" / "app.py"
if app_path.exists():
    exec(open(str(app_path), encoding='utf-8').read())
else:
    import streamlit as st
    st.error("MSDS 모듈을 찾을 수 없습니다.")
