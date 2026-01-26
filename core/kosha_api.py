#!/usr/bin/env python3
"""
KOSHA MSDS API 연동 모듈
- CAS 번호로 화학물질 정보 조회
- 8번 항목: 노출기준 (TWA, STEL)
- 15번 항목: 법적규제현황 (산안법, 위험물안전관리법, 화관법)
"""
import requests
import xml.etree.ElementTree as ET
import time
import re

# API 설정
API_KEY = "4f5a7bed-7e5d-4ac2-a714-c00e5d34f05d"
BASE_URL = "https://msds.kosha.or.kr/openapi/service/msdschem"
TIMEOUT = 15


def search_by_cas(cas_no):
    """CAS 번호로 화학물질 검색 → chemId 반환"""
    url = f"{BASE_URL}/chemlist"
    params = {
        "serviceKey": API_KEY,
        "searchCnd": "1",  # 1 = CAS 검색
        "searchWrd": cas_no,
        "numOfRows": "1"
    }
    
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        root = ET.fromstring(resp.content)
        
        item = root.find(".//item")
        if item is not None:
            return {
                "chemId": item.findtext("chemId", ""),
                "chemNameKor": item.findtext("chemNameKor", ""),
                "chemNameEng": item.findtext("chemNameEng", ""),
                "casNo": item.findtext("casNo", ""),
            }
        return None
    except Exception as e:
        print(f"[KOSHA] 검색 오류: {e}")
        return None


def get_exposure_limits(chem_id):
    """8번 항목 - 노출기준 조회"""
    url = f"{BASE_URL}/chemdetail08"
    params = {
        "serviceKey": API_KEY,
        "chemId": chem_id
    }
    
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        root = ET.fromstring(resp.content)
        
        item = root.find(".//item")
        if item is not None:
            # TWA, STEL 추출
            twa = item.findtext("twaPpm", "") or item.findtext("twaMgm", "") or "-"
            stel = item.findtext("stelPpm", "") or item.findtext("stelMgm", "") or "-"
            
            # 단위 포함
            if twa and twa != "-":
                if item.findtext("twaPpm"):
                    twa = f"{twa}ppm"
                elif item.findtext("twaMgm"):
                    twa = f"{twa}mg/m³"
            
            if stel and stel != "-":
                if item.findtext("stelPpm"):
                    stel = f"{stel}ppm"
                elif item.findtext("stelMgm"):
                    stel = f"{stel}mg/m³"
            
            return {
                "TWA": twa,
                "STEL": stel,
                "ceiling": item.findtext("ceilingPpm", "-") or "-"
            }
        return {"TWA": "-", "STEL": "-", "ceiling": "-"}
    except Exception as e:
        print(f"[KOSHA] 노출기준 조회 오류: {e}")
        return {"TWA": "-", "STEL": "-", "ceiling": "-"}


def get_legal_regulations(chem_id):
    """
    15번 항목 - 법적규제현황 조회
    - 산업안전보건법: 작업환경측정, 특수건강진단, 관리대상유해물질, 특별관리물질
    - 위험물안전관리법: 위험물류별, 지정수량, 위험등급
    - 화학물질관리법: 유독물질, 사고대비물질
    """
    url = f"{BASE_URL}/chemdetail15"
    params = {
        "serviceKey": API_KEY,
        "chemId": chem_id
    }
    
    result = {
        # 산업안전보건법
        "작업환경측정": "X",
        "특수건강진단": "X",
        "관리대상유해물질": "X",
        "특별관리물질": "X",
        "허용기준설정물질": "X",
        # 위험물안전관리법
        "위험물류별": "-",
        "위험물품명": "-",
        "지정수량": "-",
        "위험등급": "-",
        # 화학물질관리법
        "유독물질": "X",
        "사고대비물질": "X",
        "제한물질": "X",
        "금지물질": "X",
    }
    
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        text = resp.text
        root = ET.fromstring(resp.content)
        
        # 모든 item 순회하며 파싱
        for item in root.findall(".//item"):
            # 법령명/조항 확인
            law_name = item.findtext("lawName", "") or item.findtext("regulName", "") or ""
            content = item.findtext("regulContent", "") or item.findtext("content", "") or ""
            
            law_name_lower = law_name.lower()
            content_combined = f"{law_name} {content}"
            
            # ====== 산업안전보건법 ======
            if "산업안전보건" in law_name or "산안법" in law_name:
                if "작업환경측정" in content_combined:
                    result["작업환경측정"] = "O"
                if "특수건강진단" in content_combined or "건강진단" in content_combined:
                    result["특수건강진단"] = "O"
                if "관리대상" in content_combined:
                    result["관리대상유해물질"] = "O"
                if "특별관리" in content_combined:
                    result["특별관리물질"] = "O"
                if "허용기준" in content_combined:
                    result["허용기준설정물질"] = "O"
            
            # ====== 위험물안전관리법 ======
            if "위험물" in law_name:
                result["위험물류별"], result["위험물품명"], result["지정수량"], result["위험등급"] = parse_hazmat_info(content_combined)
            
            # ====== 화학물질관리법 ======
            if "화학물질관리" in law_name or "화관법" in law_name:
                if "유독" in content_combined:
                    result["유독물질"] = "O"
                if "사고대비" in content_combined:
                    result["사고대비물질"] = "O"
                if "제한" in content_combined:
                    result["제한물질"] = "O"
                if "금지" in content_combined:
                    result["금지물질"] = "O"
        
        # 직접 텍스트 검색 (백업 로직)
        if result["위험물류별"] == "-":
            result["위험물류별"], result["위험물품명"], result["지정수량"], result["위험등급"] = parse_hazmat_from_text(text)
        
        return result
        
    except Exception as e:
        print(f"[KOSHA] 법적규제 조회 오류: {e}")
        return result


def parse_hazmat_info(text):
    """위험물 정보 파싱"""
    류별 = "-"
    품명 = "-"
    지정수량 = "-"
    위험등급 = "-"
    
    # 류별 추출
    류별_match = re.search(r'제?([1-6])류', text)
    if 류별_match:
        류별 = f"제{류별_match.group(1)}류"
    
    # 품명 추출
    품명_keywords = [
        "특수인화물", "제1석유류", "제2석유류", "제3석유류", "제4석유류",
        "알코올류", "동식물유류", "산화성고체", "가연성고체",
        "자연발화성", "금수성", "인화성액체", "자기반응성", "산화성액체",
        "질산염류", "과염소산염류", "과산화물", "유황", "철분", "마그네슘",
        "니트로화합물", "유기과산화물", "질산", "황산", "과염소산"
    ]
    for keyword in 품명_keywords:
        if keyword in text:
            품명 = keyword
            break
    
    # 수용성/비수용성 구분
    if "비수용성" in text or "非水溶性" in text:
        if "석유류" in 품명:
            품명 = 품명.replace("석유류", "석유류(비수용성)")
    elif "수용성" in text or "水溶性" in text:
        if "석유류" in 품명:
            품명 = 품명.replace("석유류", "석유류(수용성)")
    
    # 지정수량 추출
    지정수량_match = re.search(r'(\d+)\s*(L|ℓ|리터|kg|킬로그램)', text, re.IGNORECASE)
    if 지정수량_match:
        지정수량 = f"{지정수량_match.group(1)}{지정수량_match.group(2).upper()}"
        지정수량 = 지정수량.replace("ℓ", "L").replace("리터", "L").replace("킬로그램", "kg")
    
    # 위험등급 추출
    등급_match = re.search(r'(I{1,3}|Ⅰ|Ⅱ|Ⅲ|1등급|2등급|3등급)', text)
    if 등급_match:
        등급_text = 등급_match.group(1)
        if "1" in 등급_text or 등급_text in ["I", "Ⅰ"]:
            위험등급 = "I"
        elif "2" in 등급_text or 등급_text in ["II", "Ⅱ"]:
            위험등급 = "II"
        elif "3" in 등급_text or 등급_text in ["III", "Ⅲ"]:
            위험등급 = "III"
    
    # 지정수량으로 위험등급 추정 (백업)
    if 위험등급 == "-" and 지정수량 != "-":
        qty = re.search(r'(\d+)', 지정수량)
        if qty:
            qty_val = int(qty.group(1))
            if "L" in 지정수량:
                if qty_val <= 50:
                    위험등급 = "I"
                elif qty_val <= 400:
                    위험등급 = "II"
                else:
                    위험등급 = "III"
            elif "kg" in 지정수량:
                if qty_val <= 50:
                    위험등급 = "I"
                elif qty_val <= 300:
                    위험등급 = "II"
                else:
                    위험등급 = "III"
    
    return 류별, 품명, 지정수량, 위험등급


def parse_hazmat_from_text(text):
    """전체 텍스트에서 위험물 정보 직접 추출"""
    return parse_hazmat_info(text)


def get_full_msds_data(cas_no):
    """CAS 번호로 전체 MSDS 정보 통합 조회"""
    result = {
        "success": False,
        "cas_no": cas_no,
        "name_kor": "",
        "name_eng": "",
        "chem_id": "",
        "exposure_limits": {},
        "legal_regulations": {},
    }
    
    # 1단계: CAS로 검색
    search_result = search_by_cas(cas_no)
    if not search_result:
        result["error"] = "물질을 찾을 수 없습니다"
        return result
    
    chem_id = search_result.get("chemId", "")
    result["chem_id"] = chem_id
    result["name_kor"] = search_result.get("chemNameKor", "")
    result["name_eng"] = search_result.get("chemNameEng", "")
    
    time.sleep(0.3)  # API 호출 간격
    
    # 2단계: 노출기준 (8번)
    result["exposure_limits"] = get_exposure_limits(chem_id)
    
    time.sleep(0.3)
    
    # 3단계: 법적규제현황 (15번) - 위험물 정보 포함!
    result["legal_regulations"] = get_legal_regulations(chem_id)
    
    result["success"] = True
    return result


# 테스트
if __name__ == "__main__":
    test_cas_list = ["67-64-1", "108-88-3", "67-56-1"]
    
    for cas in test_cas_list:
        print(f"\n{'='*50}")
        print(f"CAS: {cas}")
        data = get_full_msds_data(cas)
        
        if data["success"]:
            print(f"물질명: {data['name_kor']}")
            print(f"노출기준(TWA): {data['exposure_limits'].get('TWA', '-')}")
            
            regs = data["legal_regulations"]
            print(f"작업환경측정: {regs.get('작업환경측정', 'X')}")
            print(f"특수건강진단: {regs.get('특수건강진단', 'X')}")
            print(f"위험물류별: {regs.get('위험물류별', '-')}")
            print(f"지정수량: {regs.get('지정수량', '-')}")
            print(f"위험등급: {regs.get('위험등급', '-')}")
        else:
            print(f"오류: {data.get('error', '알 수 없음')}")
