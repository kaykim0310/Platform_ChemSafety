#!/usr/bin/env python3
"""
KOSHA API 연동 핵심 모듈
- 안전보건공단 MSDS 화학물질정보 API
- CAS 번호로 화학물질 검색 및 규제정보 조회
- 모든 모듈에서 공통으로 사용
"""

import requests
import xml.etree.ElementTree as ET
import time
import re
from typing import Optional, Dict, List, Callable

# API 설정
API_KEY = "5002b52ede58ae3359d098a19d4e11ce7f88ffddc737233c2ebce75c033ff44a"
BASE_URL = "https://msds.kosha.or.kr/openapi/service/msdschem"
API_DELAY = 0.3


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


def search_by_name(name: str) -> Optional[List[Dict]]:
    """물질명으로 화학물질 검색"""
    url = f"{BASE_URL}/chemlist"
    params = {
        "serviceKey": API_KEY,
        "searchWrd": name,
        "searchCnd": "0",  # 국문명 검색
        "numOfRows": "20",
        "pageNo": "1"
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        items = root.findall('.//item')
        
        results = []
        for item in items:
            results.append({
                'chemId': item.findtext('chemId'),
                'chemNameKor': item.findtext('chemNameKor'),
                'casNo': item.findtext('casNo'),
                'keNo': item.findtext('keNo'),
                'unNo': item.findtext('unNo')
            })
        return results if results else None
    except Exception as e:
        print(f"[KOSHA] 검색 오류 ({name}): {e}")
        return None


def get_exposure_limits(chem_id: str) -> Dict:
    """노출기준 조회 (8번 항목)"""
    url = f"{BASE_URL}/chemdetail08"
    params = {"serviceKey": API_KEY, "chemId": chem_id}
    result = {'TWA': '-', 'STEL': '-', 'ceiling': '-', 'raw_data': []}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        root = ET.fromstring(response.content)
        
        for item in root.findall('.//item'):
            name_kor = item.findtext('msdsItemNameKor') or ''
            detail = item.findtext('itemDetail') or ''
            
            if detail and detail not in ['자료없음', '해당없음']:
                result['raw_data'].append({'항목': name_kor, '내용': detail})
            
            if not detail or detail in ['자료없음', '해당없음']:
                continue
                
            if '국내' in name_kor or '노출기준' in name_kor or '고용노동부' in name_kor:
                twa_match = re.search(r'TWA[:\s]*([^,;\n]+)', detail, re.IGNORECASE)
                stel_match = re.search(r'STEL[:\s]*([^,;\n]+)', detail, re.IGNORECASE)
                ceiling_match = re.search(r'[Cc]eiling[:\s]*([^,;\n]+)', detail, re.IGNORECASE)
                
                if twa_match:
                    result['TWA'] = twa_match.group(1).strip()[:50]
                if stel_match:
                    result['STEL'] = stel_match.group(1).strip()[:50]
                if ceiling_match:
                    result['ceiling'] = ceiling_match.group(1).strip()[:50]
                    
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
        '허용기준대상': 'X', 'PSM대상': 'X',
        '유독물질': '-', '허가물질': '-', '제한물질': '-',
        '금지물질': '-', '사고대비물질': '-',
        '위험물': '-', '지정폐기물': '-',
        'raw_data': []
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        root = ET.fromstring(response.content)
        
        for item in root.findall('.//item'):
            name_kor = item.findtext('msdsItemNameKor') or ''
            detail = item.findtext('itemDetail') or ''
            
            if detail and detail not in ['해당없음', '자료없음', '-']:
                result['raw_data'].append({'항목': name_kor, '내용': detail})
            
            if not detail or detail in ['해당없음', '자료없음', '-']:
                continue
            
            # 산업안전보건법
            if '산업안전보건법' in name_kor or '산안법' in name_kor:
                if '작업환경측정' in detail:
                    result['작업환경측정'] = 'O'
                if '특수건강진단' in detail:
                    result['특수건강진단'] = 'O'
                if '관리대상' in detail:
                    result['관리대상유해물질'] = 'O'
                if '특별관리' in detail:
                    result['특별관리물질'] = 'O'
                if '허용기준' in detail:
                    result['허용기준대상'] = 'O'
                if 'PSM' in detail or '공정안전' in detail:
                    result['PSM대상'] = 'O'
                    
            # 화학물질관리법
            if '화관법' in name_kor or '유해화학물질' in name_kor:
                if '유독' in detail:
                    result['유독물질'] = detail[:50]
                if '허가' in detail:
                    result['허가물질'] = detail[:50]
                if '제한' in detail:
                    result['제한물질'] = detail[:50]
                if '금지' in detail:
                    result['금지물질'] = detail[:50]
                if '사고대비' in detail:
                    result['사고대비물질'] = detail[:50]
                    
            # 위험물안전관리법
            if '위험물' in name_kor:
                if detail not in ['해당없음', '자료없음']:
                    result['위험물'] = detail[:50]
                    
            # 폐기물관리법
            if '폐기물' in name_kor:
                if detail not in ['해당없음', '자료없음']:
                    result['지정폐기물'] = detail[:50]
                    
    except Exception as e:
        print(f"[KOSHA] 법적규제 조회 오류: {e}")
    
    return result


def get_hazard_classification(chem_id: str) -> Dict:
    """유해위험성 분류 조회 (2번 항목)"""
    url = f"{BASE_URL}/chemdetail02"
    params = {"serviceKey": API_KEY, "chemId": chem_id}
    
    result = {
        'ghs_classification': [],
        'signal_word': '-',
        'hazard_statements': [],
        'precautionary_statements': [],
        'pictograms': [],
        'raw_data': []
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        root = ET.fromstring(response.content)
        
        for item in root.findall('.//item'):
            name_kor = item.findtext('msdsItemNameKor') or ''
            detail = item.findtext('itemDetail') or ''
            
            if detail and detail not in ['자료없음', '해당없음', '-']:
                result['raw_data'].append({'항목': name_kor, '내용': detail})
                
            if '유해·위험성 분류' in name_kor or '유해위험성 분류' in name_kor:
                result['ghs_classification'].append(detail)
            elif '신호어' in name_kor:
                result['signal_word'] = detail
            elif '유해·위험 문구' in name_kor or 'H문구' in name_kor:
                result['hazard_statements'].append(detail)
            elif '예방조치문구' in name_kor or 'P문구' in name_kor:
                result['precautionary_statements'].append(detail)
            elif '그림문자' in name_kor:
                result['pictograms'].append(detail)
                
    except Exception as e:
        print(f"[KOSHA] 유해위험성 조회 오류: {e}")
    
    return result


def get_toxicity_info(chem_id: str) -> Dict:
    """독성정보 조회 (11번 항목)"""
    url = f"{BASE_URL}/chemdetail11"
    params = {"serviceKey": API_KEY, "chemId": chem_id}
    
    result = {
        '급성경구독성': '-', '급성경피독성': '-', '급성흡입독성': '-',
        '피부부식성': '-', '심한눈손상성': '-',
        '피부과민성': '-', '호흡기과민성': '-',
        '생식세포변이원성': '-', '발암성': '-', '생식독성': '-',
        '특정표적장기독성_1회': '-', '특정표적장기독성_반복': '-',
        '흡인유해성': '-',
        'IARC': '-', 'ACGIH': '-', 'NTP': '-',
        'raw_data': []
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        root = ET.fromstring(response.content)
        
        for item in root.findall('.//item'):
            name_kor = item.findtext('msdsItemNameKor') or ''
            detail = item.findtext('itemDetail') or ''
            
            if detail and detail not in ['자료없음', '해당없음', '-']:
                result['raw_data'].append({'항목': name_kor, '내용': detail})
                
            if not detail or detail == '자료없음':
                continue
            
            name_lower = name_kor.lower()
            
            if '급성 경구' in name_kor or '경구독성' in name_kor:
                result['급성경구독성'] = detail[:100]
            elif '급성 경피' in name_kor or '경피독성' in name_kor:
                result['급성경피독성'] = detail[:100]
            elif '급성 흡입' in name_kor or '흡입독성' in name_kor:
                result['급성흡입독성'] = detail[:100]
            elif '피부 부식' in name_kor:
                result['피부부식성'] = detail[:100]
            elif '눈 손상' in name_kor or '눈손상' in name_kor:
                result['심한눈손상성'] = detail[:100]
            elif '피부 과민' in name_kor:
                result['피부과민성'] = detail[:100]
            elif '호흡기 과민' in name_kor:
                result['호흡기과민성'] = detail[:100]
            elif '생식세포 변이' in name_kor or '변이원성' in name_kor:
                result['생식세포변이원성'] = detail[:100]
            elif '발암성' in name_kor:
                result['발암성'] = detail[:100]
            elif '생식독성' in name_kor:
                result['생식독성'] = detail[:100]
            elif '특정표적' in name_kor and '1회' in name_kor:
                result['특정표적장기독성_1회'] = detail[:100]
            elif '특정표적' in name_kor and '반복' in name_kor:
                result['특정표적장기독성_반복'] = detail[:100]
            elif '흡인 유해' in name_kor:
                result['흡인유해성'] = detail[:100]
            elif 'iarc' in name_lower:
                result['IARC'] = detail[:30]
            elif 'acgih' in name_lower:
                result['ACGIH'] = detail[:30]
            elif 'ntp' in name_lower:
                result['NTP'] = detail[:30]
                
    except Exception as e:
        print(f"[KOSHA] 독성정보 조회 오류: {e}")
    
    return result


def get_physical_properties(chem_id: str) -> Dict:
    """물리화학적 특성 조회 (9번 항목)"""
    url = f"{BASE_URL}/chemdetail09"
    params = {"serviceKey": API_KEY, "chemId": chem_id}
    
    result = {
        '외관': '-', '냄새': '-', 'pH': '-',
        '녹는점': '-', '끓는점': '-', '인화점': '-',
        '증발속도': '-', '인화성': '-', '폭발한계': '-',
        '증기압': '-', '증기밀도': '-', '비중': '-',
        '용해도': '-', '옥탄올물분배계수': '-',
        '자연발화점': '-', '분해온도': '-', '점도': '-',
        '분자량': '-',
        'raw_data': []
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        root = ET.fromstring(response.content)
        
        for item in root.findall('.//item'):
            name_kor = item.findtext('msdsItemNameKor') or ''
            detail = item.findtext('itemDetail') or ''
            
            if detail and detail not in ['자료없음', '해당없음', '-']:
                result['raw_data'].append({'항목': name_kor, '내용': detail})
                
            if not detail or detail in ['자료없음', '해당없음']:
                continue
            
            if '외관' in name_kor or '성상' in name_kor:
                result['외관'] = detail[:50]
            elif '냄새' in name_kor:
                result['냄새'] = detail[:50]
            elif 'pH' in name_kor or 'ph' in name_kor.lower():
                result['pH'] = detail[:30]
            elif '녹는점' in name_kor or '융점' in name_kor:
                result['녹는점'] = detail[:30]
            elif '끓는점' in name_kor or '비점' in name_kor:
                result['끓는점'] = detail[:30]
            elif '인화점' in name_kor:
                result['인화점'] = detail[:30]
            elif '증발' in name_kor:
                result['증발속도'] = detail[:30]
            elif '인화성' in name_kor:
                result['인화성'] = detail[:50]
            elif '폭발' in name_kor:
                result['폭발한계'] = detail[:50]
            elif '증기압' in name_kor:
                result['증기압'] = detail[:30]
            elif '증기밀도' in name_kor:
                result['증기밀도'] = detail[:30]
            elif '비중' in name_kor or '밀도' in name_kor:
                result['비중'] = detail[:30]
            elif '용해' in name_kor:
                result['용해도'] = detail[:50]
            elif '옥탄올' in name_kor or 'log' in name_kor.lower():
                result['옥탄올물분배계수'] = detail[:30]
            elif '자연발화' in name_kor:
                result['자연발화점'] = detail[:30]
            elif '분해' in name_kor:
                result['분해온도'] = detail[:30]
            elif '점도' in name_kor:
                result['점도'] = detail[:30]
            elif '분자량' in name_kor:
                result['분자량'] = detail[:30]
                
    except Exception as e:
        print(f"[KOSHA] 물리화학적 특성 조회 오류: {e}")
    
    return result


def get_ecological_info(chem_id: str) -> Dict:
    """환경영향정보 조회 (12번 항목)"""
    url = f"{BASE_URL}/chemdetail12"
    params = {"serviceKey": API_KEY, "chemId": chem_id}
    
    result = {
        '수생독성': '-', '어류독성': '-', '물벼룩독성': '-', '조류독성': '-',
        '잔류성': '-', '분해성': '-', '생물농축성': '-',
        '토양이동성': '-', 'raw_data': []
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        root = ET.fromstring(response.content)
        
        for item in root.findall('.//item'):
            name_kor = item.findtext('msdsItemNameKor') or ''
            detail = item.findtext('itemDetail') or ''
            
            if detail and detail not in ['자료없음', '해당없음', '-']:
                result['raw_data'].append({'항목': name_kor, '내용': detail})
                
            if not detail or detail in ['자료없음', '해당없음']:
                continue
            
            if '수생' in name_kor:
                result['수생독성'] = detail[:100]
            elif '어류' in name_kor:
                result['어류독성'] = detail[:100]
            elif '물벼룩' in name_kor:
                result['물벼룩독성'] = detail[:100]
            elif '조류' in name_kor:
                result['조류독성'] = detail[:100]
            elif '잔류' in name_kor:
                result['잔류성'] = detail[:100]
            elif '분해' in name_kor:
                result['분해성'] = detail[:100]
            elif '생물농축' in name_kor:
                result['생물농축성'] = detail[:100]
            elif '토양이동' in name_kor:
                result['토양이동성'] = detail[:100]
                
    except Exception as e:
        print(f"[KOSHA] 환경영향정보 조회 오류: {e}")
    
    return result


def get_full_msds_data(cas_no: str) -> Dict:
    """CAS 번호로 MSDS 전체 정보 통합 조회"""
    cas_no = str(cas_no).strip()
    
    search_result = search_by_cas(cas_no)
    
    if not search_result:
        return {
            'success': False,
            'error': '미등록 물질',
            'cas_no': cas_no
        }
    
    chem_id = search_result['chemId']
    
    time.sleep(API_DELAY)
    hazard = get_hazard_classification(chem_id)
    
    time.sleep(API_DELAY)
    exposure = get_exposure_limits(chem_id)
    
    time.sleep(API_DELAY)
    physical = get_physical_properties(chem_id)
    
    time.sleep(API_DELAY)
    toxicity = get_toxicity_info(chem_id)
    
    time.sleep(API_DELAY)
    ecological = get_ecological_info(chem_id)
    
    time.sleep(API_DELAY)
    regulations = get_legal_regulations(chem_id)
    
    return {
        'success': True,
        'chem_id': chem_id,
        'cas_no': cas_no,
        'name_kor': search_result.get('chemNameKor', ''),
        'un_no': search_result.get('unNo', ''),
        'ke_no': search_result.get('keNo', ''),
        'hazard_classification': hazard,
        'exposure_limits': exposure,
        'physical_properties': physical,
        'toxicity_info': toxicity,
        'ecological_info': ecological,
        'legal_regulations': regulations
    }


def batch_query(cas_list: List[str], progress_callback: Callable = None) -> List[Dict]:
    """여러 CAS 번호 일괄 조회"""
    results = []
    total = len(cas_list)
    
    for idx, cas_no in enumerate(cas_list):
        result = get_full_msds_data(cas_no)
        results.append(result)
        
        if progress_callback:
            progress_callback(idx + 1, total, cas_no, result)
        
        if idx < total - 1:
            time.sleep(API_DELAY)
    
    return results


if __name__ == "__main__":
    # 테스트
    test_cas = "67-64-1"  # 아세톤
    print(f"테스트: {test_cas}")
    result = get_full_msds_data(test_cas)
    
    if result['success']:
        print(f"✓ 물질명: {result['name_kor']}")
        print(f"✓ TWA: {result['exposure_limits']['TWA']}")
        print(f"✓ 인화점: {result['physical_properties']['인화점']}")
    else:
        print(f"✗ 실패: {result.get('error')}")
