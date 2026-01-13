#!/usr/bin/env python3
"""
KOSHA API 연동 모듈
- 안전보건공단 MSDS 화학물질정보 API
- CAS 번호로 화학물질 검색 및 규제정보 조회

사용법:
    from kosha_api import get_chemical_info, batch_query
    
    # 개별 조회
    result = get_chemical_info("67-64-1")
    
    # 일괄 조회
    results = batch_query(["67-64-1", "108-88-3", "1330-20-7"])
"""

import requests
import xml.etree.ElementTree as ET
import time
import re
from typing import Optional, Dict, List, Callable

# PRTR 데이터베이스 import
try:
    from prtr_substances import check_prtr_status, get_prtr_group
    PRTR_AVAILABLE = True
except ImportError:
    PRTR_AVAILABLE = False
    print("⚠️ prtr_substances.py 모듈 없음. PRTR 체크 기능 제한됨.")

# ============================================
# API 설정
# ============================================
API_KEY = "5002b52ede58ae3359d098a19d4e11ce7f88ffddc737233c2ebce75c033ff44a"
BASE_URL = "https://msds.kosha.or.kr/openapi/service/msdschem"
API_DELAY = 0.3  # rate limit 방지


def check_prtr(cas_no: str) -> Dict:
    """PRTR 배출량조사 대상 여부 확인 (prtr_substances 모듈 사용)"""
    if PRTR_AVAILABLE:
        result = check_prtr_status(cas_no)
        return {
            "대상": result["대상여부"],
            "그룹": result["그룹"],
            "기준량": result["기준취급량"],
            "물질명": result["물질명"]
        }
    else:
        # 모듈 없을 때 기본값
        return {"대상": "-", "그룹": "-", "기준량": "-", "물질명": "-"}


def search_by_cas(cas_no: str) -> Optional[Dict]:
    """CAS 번호로 화학물질 검색"""
    url = f"{BASE_URL}/chemlist"
    params = {
        "serviceKey": API_KEY,
        "searchWrd": cas_no,
        "searchCnd": "1",
        "numOfRows": "10",
        "pageNo": "1"
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        items = root.findall('.//item')
        
        if items:
            item = items[0]
            return {
                'chemId': item.findtext('chemId'),
                'chemNameKor': item.findtext('chemNameKor'),
                'casNo': item.findtext('casNo'),
                'keNo': item.findtext('keNo'),
                'unNo': item.findtext('unNo')
            }
        return None
    except Exception as e:
        print(f"[KOSHA] 검색 오류 ({cas_no}): {e}")
        return None


def get_exposure_limits(chem_id: str) -> Dict:
    """노출기준 조회 (8번 항목)"""
    url = f"{BASE_URL}/chemdetail08"
    params = {"serviceKey": API_KEY, "chemId": chem_id}
    result = {'TWA': '-', 'STEL': '-'}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        root = ET.fromstring(response.content)
        
        for item in root.findall('.//item'):
            name_kor = item.findtext('msdsItemNameKor') or ''
            detail = item.findtext('itemDetail') or ''
            
            if not detail or detail in ['자료없음', '해당없음']:
                continue
                
            if '국내' in name_kor or '노출기준' in name_kor or '고용노동부' in name_kor:
                twa_match = re.search(r'TWA[:\s]*([^,;\n]+)', detail, re.IGNORECASE)
                stel_match = re.search(r'STEL[:\s]*([^,;\n]+)', detail, re.IGNORECASE)
                
                if twa_match:
                    result['TWA'] = twa_match.group(1).strip()[:30]
                if stel_match:
                    result['STEL'] = stel_match.group(1).strip()[:30]
                    
                if result['TWA'] == '-':
                    ppm_match = re.search(r'(\d+(?:\.\d+)?\s*(?:ppm|mg/m3|mg/㎥))', detail, re.IGNORECASE)
                    if ppm_match:
                        result['TWA'] = ppm_match.group(1)
    except Exception as e:
        print(f"[KOSHA] 노출기준 조회 오류: {e}")
    
    return result


def get_legal_regulations(chem_id: str) -> Dict:
    """법적 규제현황 조회 (15번 항목)"""
    url = f"{BASE_URL}/chemdetail15"
    params = {"serviceKey": API_KEY, "chemId": chem_id}
    
    result = {
        '작업환경측정': 'X', '특수건강진단': 'X',
        '관리대상유해물질': 'X', '특별관리물질': 'X',
        '유독': '해당없음', '사고대비': '해당없음',
        '제한/금지/허가': '해당없음', '위험물': '해당없음'
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        root = ET.fromstring(response.content)
        
        for item in root.findall('.//item'):
            name_kor = item.findtext('msdsItemNameKor') or ''
            detail = item.findtext('itemDetail') or ''
            
            if not detail or detail in ['해당없음', '자료없음', '-']:
                continue
            
            if '산업안전보건법' in name_kor or '산안법' in name_kor:
                if '작업환경측정' in detail or '측정대상' in detail:
                    result['작업환경측정'] = 'O'
                if '특수건강진단' in detail or '건강진단' in detail:
                    result['특수건강진단'] = 'O'
                if '관리대상' in detail:
                    result['관리대상유해물질'] = 'O'
                if '특별관리' in detail:
                    result['특별관리물질'] = 'O'
                if detail not in ['해당없음', '자료없음']:
                    if result['작업환경측정'] == 'X':
                        result['작업환경측정'] = 'O'
                    if result['특수건강진단'] == 'X':
                        result['특수건강진단'] = 'O'
                    
            if '유해화학물질' in name_kor or '화관법' in name_kor or '유독' in name_kor:
                if '유독' in detail:
                    result['유독'] = detail[:30]
                elif '사고대비' in detail:
                    result['사고대비'] = detail[:30]
                elif detail not in ['해당없음', '자료없음']:
                    result['유독'] = detail[:30]
                    
            if '제한' in name_kor or '금지' in name_kor or '허가' in name_kor:
                if detail not in ['해당없음', '자료없음']:
                    result['제한/금지/허가'] = detail[:30]
                    
            if '위험물' in name_kor:
                if detail not in ['해당없음', '자료없음']:
                    result['위험물'] = detail[:40]
                    
    except Exception as e:
        print(f"[KOSHA] 법적규제 조회 오류: {e}")
    
    return result


def get_hazard_classification(chem_id: str) -> Dict:
    """유해성 분류 조회 (11번 항목)"""
    url = f"{BASE_URL}/chemdetail11"
    params = {"serviceKey": API_KEY, "chemId": chem_id}
    
    result = {
        '발암성': '자료없음', '변이성': '자료없음', '생식독성': '자료없음',
        'IARC': '자료없음', 'ACGIH': '자료없음', 'NTP': '자료없음'
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        root = ET.fromstring(response.content)
        
        for item in root.findall('.//item'):
            name_kor = item.findtext('msdsItemNameKor') or ''
            detail = item.findtext('itemDetail') or ''
            
            if not detail or detail == '자료없음':
                continue
                
            name_lower = name_kor.lower()
            
            if 'iarc' in name_lower:
                result['IARC'] = detail[:20]
            elif 'acgih' in name_lower:
                result['ACGIH'] = detail[:20]
            elif 'ntp' in name_lower:
                result['NTP'] = detail[:20]
            elif '발암성' in name_kor:
                result['발암성'] = detail[:20]
            elif '변이' in name_kor or '돌연변이' in name_kor:
                result['변이성'] = detail[:20]
            elif '생식' in name_kor:
                result['생식독성'] = detail[:20]
                    
    except Exception as e:
        print(f"[KOSHA] 유해성분류 조회 오류: {e}")
    
    return result


def get_chemical_info(cas_no: str) -> Dict:
    """CAS 번호로 전체 정보 통합 조회 (메인 함수)"""
    cas_no = str(cas_no).strip()
    
    search_result = search_by_cas(cas_no)
    
    if not search_result:
        return {
            'success': False,
            'error': '미등록 물질',
            '화학물질명': '-',
            'CAS No': cas_no
        }
    
    chem_id = search_result['chemId']
    
    time.sleep(API_DELAY)
    exposure = get_exposure_limits(chem_id)
    
    time.sleep(API_DELAY)
    regulations = get_legal_regulations(chem_id)
    
    time.sleep(API_DELAY)
    hazard = get_hazard_classification(chem_id)
    
    prtr = check_prtr(cas_no)
    
    # 기존 인벤토리 컬럼명에 맞춤
    return {
        'success': True,
        'chemId': chem_id,
        '화학물질명': search_result['chemNameKor'] or cas_no,
        'CAS No': cas_no,
        '노출기준(TWA)': exposure['TWA'],
        'STEL': exposure['STEL'],
        '작업환경측정': regulations['작업환경측정'],
        '특수건강진단': regulations['특수건강진단'],
        '관리대상유해물질': regulations['관리대상유해물질'],
        '특별관리물질': regulations['특별관리물질'],
        '유독': regulations['유독'],
        '사고대비': regulations['사고대비'],
        '제한/금지/허가': regulations['제한/금지/허가'],
        '위험물': regulations['위험물'],
        '발암성': hazard['발암성'],
        '변이성': hazard['변이성'],
        '생식독성': hazard['생식독성'],
        'IARC': hazard['IARC'],
        'ACGIH': hazard['ACGIH'],
        'NTP': hazard['NTP'],
        'PRTR대상': prtr['대상'],
        'PRTR그룹': prtr['그룹'],
        'PRTR기준량': prtr['기준량']
    }


def batch_query(cas_list: List[str], progress_callback: Callable = None) -> List[Dict]:
    """여러 CAS 번호 일괄 조회"""
    results = []
    total = len(cas_list)
    
    for idx, cas_no in enumerate(cas_list):
        result = get_chemical_info(cas_no)
        results.append(result)
        
        if progress_callback:
            progress_callback(idx + 1, total, cas_no, result)
        
        if idx < total - 1:
            time.sleep(API_DELAY)
    
    return results


if __name__ == "__main__":
    test_cas = ["67-64-1", "108-88-3", "1330-20-7"]
    
    print("=" * 50)
    print("KOSHA API 테스트")
    print("=" * 50)
    
    for cas in test_cas:
        print(f"\n▶ {cas} 조회...")
        result = get_chemical_info(cas)
        
        if result['success']:
            print(f"  ✓ 물질명: {result['화학물질명']}")
            print(f"  ✓ TWA: {result['노출기준(TWA)']}")
            print(f"  ✓ 측정/진단: {result['작업환경측정']}/{result['특수건강진단']}")
            print(f"  ✓ PRTR: {result['PRTR대상']} ({result['PRTR그룹']})")
        else:
            print(f"  ✗ 실패: {result.get('error')}")
    
    print("\n테스트 완료!")
