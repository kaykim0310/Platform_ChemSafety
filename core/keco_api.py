#!/usr/bin/env python3
"""
한국환경공단 화학물질 정보 조회 API (KECO API)
- CAS번호로 유독물질, 제한물질, 금지물질, 사고대비물질 등 조회
- 공공데이터포털: https://www.data.go.kr/data/15149420/openapi.do
- End Point: https://apis.data.go.kr/B552584/kecoapi/ncissbstn/chemSbstnList
"""

import requests
from typing import Dict, Any, List

# API 설정
KECO_API_KEY = "5002b52ede58ae3359d098a19d4e11ce7f88ffddc737233c2ebce75c033ff44a"
KECO_BASE_URL = "https://apis.data.go.kr/B552584/kecoapi/ncissbstn/chemSbstnList"


def search_chemical_by_cas(cas_no: str) -> Dict[str, Any]:
    """
    CAS 번호로 화학물질 정보 조회
    
    Args:
        cas_no: CAS 등록번호 (예: 108-88-3)
    
    Returns:
        화학물질 정보 딕셔너리
    """
    params = {
        "serviceKey": KECO_API_KEY,
        "pageNo": 1,
        "numOfRows": 10,
        "searchGubun": 2,  # 1:영문명, 2:CAS번호, 3:고유번호
        "searchNm": cas_no,
        "returnType": "JSON"
    }
    
    try:
        response = requests.get(KECO_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return parse_response(data, cas_no)
            
    except requests.exceptions.RequestException as e:
        return {"success": False, "cas_no": cas_no, "error": str(e)}
    except Exception as e:
        return {"success": False, "cas_no": cas_no, "error": f"파싱 오류: {str(e)}"}


def search_chemical_by_name(name: str) -> Dict[str, Any]:
    """
    물질명(영문)으로 화학물질 정보 조회
    """
    params = {
        "serviceKey": KECO_API_KEY,
        "pageNo": 1,
        "numOfRows": 10,
        "searchGubun": 1,  # 1:영문명
        "searchNm": name,
        "returnType": "JSON"
    }
    
    try:
        response = requests.get(KECO_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        return parse_response(response.json(), name)
            
    except requests.exceptions.RequestException as e:
        return {"success": False, "query": name, "error": str(e)}


def parse_response(data: Dict, query: str) -> Dict[str, Any]:
    """API 응답 파싱"""
    try:
        header = data.get("header", {})
        body = data.get("body", {})
        
        result_code = header.get("resultCode", "")
        if result_code != "200":
            return {"success": False, "query": query, "error": header.get("resultMsg", "")}
        
        items = body.get("items", [])
        if not items:
            return {"success": False, "query": query, "error": "조회 결과 없음"}
        
        # 첫 번째 결과 사용
        item = items[0]
        
        # 물질분류 추출
        classifications = extract_classifications(item.get("typeList", []))
        
        return {
            "success": True,
            "query": query,
            "cas_no": item.get("casNo", ""),
            "ke_no": item.get("korexst", ""),
            "물질명_국문": item.get("sbstnNmKor", ""),
            "물질명_영문": item.get("sbstnNmEng", ""),
            "물질유사명_국문": item.get("sbstnNm2Kor", ""),
            "분자식": item.get("mlcfrm", ""),
            "분자량": item.get("mlcwgt", ""),
            "물질분류": classifications,
            "typeList": item.get("typeList", []),
            "raw_data": item
        }
            
    except Exception as e:
        return {"success": False, "query": query, "error": f"파싱 오류: {str(e)}"}


def extract_percent_from_text(text: str) -> str:
    """
    텍스트에서 함량(%) 정보 추출
    
    예시:
    - "톨루엔 및 이를 85% 이상 함유한 혼합물" → "85%이상"
    - "1% 이상 함유한 혼합물" → "1%이상"
    - "25% 미만" → "25%미만"
    """
    import re
    
    if not text:
        return ""
    
    # 패턴: 숫자% + 이상/이하/초과/미만
    patterns = [
        r'(\d+(?:\.\d+)?)\s*%\s*(이상|이하|초과|미만)',  # 85% 이상
        r'(\d+(?:\.\d+)?)\s*%',  # 단순 85%
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            if len(groups) >= 2 and groups[1]:
                return f"{groups[0]}%{groups[1]}"
            elif len(groups) >= 1:
                return f"{groups[0]}%"
    
    return ""


def extract_classifications(type_list: List[Dict]) -> Dict[str, str]:
    """
    typeList에서 물질분류 정보 추출
    
    typeList 예시:
    [
        {"sbstnClsfTypeNm": "기존화학물질", "unqNo": "V", ...},
        {"sbstnClsfTypeNm": "사고대비물질", "unqNo": "28", "contInfo": "톨루엔 및 이를 85% 이상 함유한 혼합물", ...},
    ]
    
    Returns:
        {
            "유독물질": "O(1%이상)" or "-",
            "사고대비물질": "O(85%이상)" or "-",
            ...
        }
    """
    # 분류명 매핑
    classification_map = {
        "유독물질": "-",
        "제한물질": "-",
        "금지물질": "-",
        "허가물질": "-",
        "사고대비물질": "-",
        "기존화학물질": "-",
        "등록대상기존화학물질": "-",
        "대량생산화학물질": "-",
        "중점관리물질": "-",
    }
    
    # 상세 정보 저장
    details = {}
    
    for item in type_list:
        type_name = item.get("sbstnClsfTypeNm", "")
        unq_no = item.get("unqNo", "")
        cont_info = item.get("contInfo", "")
        excp_info = item.get("excpInfo", "")
        
        if type_name in classification_map:
            # 함량 정보 추출
            percent = extract_percent_from_text(cont_info)
            
            if percent:
                classification_map[type_name] = f"O({percent})"
            else:
                classification_map[type_name] = "O"
            
            # 상세 정보 저장
            if cont_info:
                details[f"{type_name}_함량정보"] = cont_info
            if excp_info:
                details[f"{type_name}_예외정보"] = excp_info
            if unq_no and unq_no != "V":
                details[f"{type_name}_번호"] = unq_no
    
    # 상세 정보 병합
    classification_map["details"] = details
    
    return classification_map


def get_chemical_regulations(cas_no: str) -> Dict[str, Any]:
    """
    CAS 번호로 규제 정보만 간단히 조회
    
    Returns:
        {
            "success": True/False,
            "cas_no": "108-88-3",
            "물질명": "톨루엔",
            "유독물질": "O" or "-",
            "제한물질": "O" or "-",
            ...
        }
    """
    result = search_chemical_by_cas(cas_no)
    
    if not result.get("success"):
        return {"success": False, "cas_no": cas_no, "error": result.get("error", "조회 실패")}
    
    regs = result.get("물질분류", {}).copy()
    regs["success"] = True
    regs["cas_no"] = result.get("cas_no", cas_no)
    regs["물질명"] = result.get("물질명_국문", "")
    regs["ke_no"] = result.get("ke_no", "")
    
    return regs


def get_all_regulations_summary(cas_no: str) -> str:
    """규제 정보를 한 줄 요약으로 반환"""
    result = search_chemical_by_cas(cas_no)
    
    if not result.get("success"):
        return "-"
    
    classifications = result.get("물질분류", {})
    
    # O인 항목만 추출
    active_regs = [k for k, v in classifications.items() if v == "O" and k != "details"]
    
    if not active_regs:
        return "-"
    
    return ", ".join(active_regs)


# 테스트
if __name__ == "__main__":
    print("=== 톨루엔 (108-88-3) 조회 ===")
    result = search_chemical_by_cas("108-88-3")
    
    if result.get("success"):
        print(f"물질명: {result.get('물질명_국문')}")
        print(f"KE번호: {result.get('ke_no')}")
        print(f"\n[규제 현황]")
        for k, v in result.get("물질분류", {}).items():
            if k != "details":
                status = "✅" if v != "-" else "⬜"
                print(f"  {status} {k}: {v}")
        
        # 상세 정보
        details = result.get("물질분류", {}).get("details", {})
        if details:
            print(f"\n[상세 정보]")
            for k, v in details.items():
                print(f"  • {k}: {v}")
    else:
        print(f"오류: {result.get('error')}")
    
    print("\n=== 규제 요약 ===")
    print(get_all_regulations_summary("108-88-3"))
    
    print("\n" + "="*50)
    print("=== 황산 (7664-93-9) 조회 ===")
    result2 = search_chemical_by_cas("7664-93-9")
    if result2.get("success"):
        print(f"물질명: {result2.get('물질명_국문')}")
        for k, v in result2.get("물질분류", {}).items():
            if k != "details" and v != "-":
                print(f"  ✅ {k}: {v}")
