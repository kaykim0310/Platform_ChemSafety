#!/usr/bin/env python3
"""
MSDS 작성 엔진
- 고용노동부 고시 양식에 따른 16개 항목 자동 생성
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.kosha_api import get_full_msds_data
from core.prtr_db import check_prtr_status
from core.ghs_utils import calculate_ate_mix, generate_h_statements_from_classification


class MSDSGenerator:
    """MSDS 작성 엔진"""
    
    def __init__(self):
        self.components = []
        self.product_info = {}
        self.msds_data = {}
        
    def set_product_info(self, product_name: str, supplier_name: str = "",
                         supplier_address: str = "", supplier_phone: str = "",
                         emergency_phone: str = "", product_use: str = ""):
        """1번 항목: 제품 및 공급자 정보"""
        self.product_info = {
            '제품명': product_name,
            '권고용도': product_use or '공업용',
            '회사명': supplier_name,
            '주소': supplier_address,
            '긴급전화': emergency_phone or '119',
            '전화번호': supplier_phone
        }
        
    def add_component(self, name: str, cas_no: str, content: float,
                      content_range: str = None, auto_query: bool = True) -> Dict:
        """구성성분 추가"""
        component = {
            'name': name,
            'cas_no': cas_no,
            'content': content,
            'content_range': content_range or f"{content}",
            'kosha_data': None,
            'prtr_status': None
        }
        
        if auto_query and cas_no:
            kosha_result = get_full_msds_data(cas_no)
            if kosha_result.get('success'):
                component['kosha_data'] = kosha_result
                component['name'] = kosha_result.get('name_kor') or name
            component['prtr_status'] = check_prtr_status(cas_no)
        
        self.components.append(component)
        return component
    
    def clear_components(self):
        self.components = []
        
    def generate_all_sections(self) -> Dict:
        """16개 항목 전체 생성"""
        self.msds_data = {
            'section_1': self._gen_section_1(),
            'section_2': self._gen_section_2(),
            'section_3': self._gen_section_3(),
            'section_4': self._gen_section_4(),
            'section_5': self._gen_section_5(),
            'section_6': self._gen_section_6(),
            'section_7': self._gen_section_7(),
            'section_8': self._gen_section_8(),
            'section_9': self._gen_section_9(),
            'section_10': self._gen_section_10(),
            'section_11': self._gen_section_11(),
            'section_12': self._gen_section_12(),
            'section_13': self._gen_section_13(),
            'section_14': self._gen_section_14(),
            'section_15': self._gen_section_15(),
            'section_16': self._gen_section_16(),
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        return self.msds_data
    
    def _gen_section_1(self) -> Dict:
        """1. 화학제품과 회사에 관한 정보"""
        return {
            '항목명': '1. 화학제품과 회사에 관한 정보',
            '가_제품명': self.product_info.get('제품명', ''),
            '나_권고용도': self.product_info.get('권고용도', '공업용'),
            '다_공급자정보': {
                '회사명': self.product_info.get('회사명', ''),
                '주소': self.product_info.get('주소', ''),
                '긴급전화번호': self.product_info.get('긴급전화', '119')
            }
        }
    
    def _gen_section_2(self) -> Dict:
        """2. 유해성·위험성"""
        all_classifications = []
        all_h_statements = []
        signal_word = '경고'
        pictograms = []
        
        for comp in self.components:
            if comp.get('kosha_data'):
                hazard = comp['kosha_data'].get('hazard_classification', {})
                for c in hazard.get('ghs_classification', []):
                    if c and c not in all_classifications:
                        all_classifications.append(c)
                for h in hazard.get('hazard_statements', []):
                    if h and h not in all_h_statements:
                        all_h_statements.append(h)
                if hazard.get('signal_word') == '위험':
                    signal_word = '위험'
                for p in hazard.get('pictograms', []):
                    if p and p not in pictograms:
                        pictograms.append(p)
        
        if not all_h_statements and all_classifications:
            all_h_statements = generate_h_statements_from_classification(all_classifications)
        
        return {
            '항목명': '2. 유해성·위험성',
            '가_분류': all_classifications or ['자료없음'],
            '나_경고표지': {
                '그림문자': pictograms or ['해당없음'],
                '신호어': signal_word,
                'H문구': all_h_statements or ['해당없음'],
                'P문구': ['해당없음']
            },
            '다_기타유해성': '자료없음'
        }
    
    def _gen_section_3(self) -> Dict:
        """3. 구성성분의 명칭 및 함유량"""
        comp_list = []
        for comp in self.components:
            comp_list.append({
                '화학물질명': comp['name'],
                'CAS_No': comp['cas_no'],
                '함유량': comp['content_range']
            })
        return {
            '항목명': '3. 구성성분의 명칭 및 함유량',
            '구성성분': comp_list
        }
    
    def _gen_section_4(self) -> Dict:
        """4. 응급조치 요령"""
        return {
            '항목명': '4. 응급조치 요령',
            '가_눈': '즉시 다량의 물로 15분 이상 씻어낸다. 콘택트렌즈 착용 시 제거 후 씻는다. 자극 지속 시 의료조치.',
            '나_피부': '오염된 의복을 벗기고 다량의 물과 비누로 씻는다. 자극 지속 시 의료조치.',
            '다_흡입': '신선한 공기가 있는 곳으로 옮긴다. 호흡곤란 시 산소공급. 의식불명 시 즉시 의료조치.',
            '라_섭취': '입안을 물로 씻어내고 물을 마시게 한다. 토하게 하지 않는다. 즉시 의료조치.',
            '마_의사주의사항': '증상에 따라 치료한다.'
        }
    
    def _gen_section_5(self) -> Dict:
        """5. 폭발·화재 시 대처방법"""
        return {
            '항목명': '5. 폭발·화재 시 대처방법',
            '가_소화제': '분말소화약제, 이산화탄소, 포, 물분무',
            '나_특정유해성': '화재 시 유독가스 발생 가능',
            '다_보호구': '자급식 호흡장치와 방호복 착용'
        }
    
    def _gen_section_6(self) -> Dict:
        """6. 누출 사고 시 대처방법"""
        return {
            '항목명': '6. 누출 사고 시 대처방법',
            '가_인체보호': '적절한 보호구 착용 (보안경, 보호장갑, 보호의, 호흡보호구)',
            '나_환경보호': '하수구, 지표수, 지하수 유입 방지. 적절한 봉쇄조치.',
            '다_정화방법': '소량: 흡착재로 흡착 후 밀폐용기 수거. 대량: 방벽 설치 후 전문업체 의뢰.'
        }
    
    def _gen_section_7(self) -> Dict:
        """7. 취급 및 저장방법"""
        return {
            '항목명': '7. 취급 및 저장방법',
            '가_취급': '환기가 잘 되는 곳에서 보호구 착용 후 취급. 취급 후 손 세척.',
            '나_저장': '직사광선 피하고 서늘하고 건조한 곳에 밀폐 보관. 점화원으로부터 격리.'
        }
    
    def _gen_section_8(self) -> Dict:
        """8. 노출방지 및 개인보호구"""
        exposure_list = []
        for comp in self.components:
            exp_data = {'물질명': comp['name'], 'CAS_No': comp['cas_no'], 'TWA': '-', 'STEL': '-'}
            if comp.get('kosha_data'):
                exp = comp['kosha_data'].get('exposure_limits', {})
                exp_data['TWA'] = exp.get('TWA', '-')
                exp_data['STEL'] = exp.get('STEL', '-')
            exposure_list.append(exp_data)
        
        return {
            '항목명': '8. 노출방지 및 개인보호구',
            '가_노출기준': exposure_list,
            '나_공학적관리': '국소배기장치 설치',
            '다_보호구': {
                '호흡기': '방독마스크 또는 송기마스크',
                '눈': '보안경 또는 고글',
                '손': '적합한 보호장갑',
                '신체': '긴팔작업복, 안전화'
            }
        }
    
    def _gen_section_9(self) -> Dict:
        """9. 물리화학적 특성"""
        props = {'외관': '-', '냄새': '-', 'pH': '-', '녹는점': '-', '끓는점': '-',
                 '인화점': '-', '증기압': '-', '비중': '-', '용해도': '-'}
        
        for comp in self.components:
            if comp.get('kosha_data'):
                phys = comp['kosha_data'].get('physical_properties', {})
                for key in props:
                    if phys.get(key) and phys[key] != '-':
                        props[key] = phys[key]
                        break
        
        return {'항목명': '9. 물리화학적 특성', **props}
    
    def _gen_section_10(self) -> Dict:
        """10. 안정성 및 반응성"""
        return {
            '항목명': '10. 안정성 및 반응성',
            '가_화학적안정성': '정상적인 조건에서 안정함',
            '나_유해반응가능성': '알려진 유해 반응 없음',
            '다_피해야할조건': '열, 스파크, 화염, 고온',
            '라_피해야할물질': '강산화제, 강산, 강염기',
            '마_분해시생성물': '열분해 시 유해가스 발생 가능'
        }
    
    def _gen_section_11(self) -> Dict:
        """11. 독성에 관한 정보"""
        tox_list = []
        for comp in self.components:
            tox_data = {
                '물질명': comp['name'],
                '급성경구독성': '-', '급성경피독성': '-', '급성흡입독성': '-',
                '피부부식성': '-', '눈손상성': '-',
                '발암성': '-', 'IARC': '-', 'ACGIH': '-'
            }
            if comp.get('kosha_data'):
                tox = comp['kosha_data'].get('toxicity_info', {})
                for key in ['급성경구독성', '급성경피독성', '급성흡입독성', '피부부식성',
                           '심한눈손상성', '발암성', 'IARC', 'ACGIH']:
                    if tox.get(key):
                        tox_data[key.replace('심한', '')] = tox[key]
            tox_list.append(tox_data)
        
        return {'항목명': '11. 독성에 관한 정보', '독성정보': tox_list}
    
    def _gen_section_12(self) -> Dict:
        """12. 환경에 미치는 영향"""
        eco_list = []
        for comp in self.components:
            eco_data = {'물질명': comp['name'], '수생독성': '-', '잔류성': '-', '생물농축성': '-'}
            if comp.get('kosha_data'):
                eco = comp['kosha_data'].get('ecological_info', {})
                eco_data['수생독성'] = eco.get('수생독성', '-')
                eco_data['잔류성'] = eco.get('잔류성', '-')
                eco_data['생물농축성'] = eco.get('생물농축성', '-')
            eco_list.append(eco_data)
        
        return {'항목명': '12. 환경에 미치는 영향', '환경정보': eco_list}
    
    def _gen_section_13(self) -> Dict:
        """13. 폐기시 주의사항"""
        return {
            '항목명': '13. 폐기시 주의사항',
            '가_폐기방법': '폐기물관리법에 따라 지정폐기물로 처리. 허가받은 전문업체에 의뢰.',
            '나_폐기시주의사항': '빈 용기에도 잔류물이 남아 있을 수 있으므로 적절히 처리.'
        }
    
    def _gen_section_14(self) -> Dict:
        """14. 운송에 필요한 정보"""
        un_no = '-'
        for comp in self.components:
            if comp.get('kosha_data') and comp['kosha_data'].get('un_no'):
                un_no = comp['kosha_data']['un_no']
                break
        
        return {
            '항목명': '14. 운송에 필요한 정보',
            'UN번호': un_no,
            'UN적정선적명': '-',
            '운송등급': '-',
            '용기등급': '-',
            '해양오염물질': '-'
        }
    
    def _gen_section_15(self) -> Dict:
        """15. 법적 규제현황"""
        reg_list = []
        for comp in self.components:
            reg_data = {
                '물질명': comp['name'],
                'CAS_No': comp['cas_no'],
                '산안법_측정': 'X', '산안법_진단': 'X', '산안법_관리대상': 'X',
                '화관법_유독': '-', '화관법_사고대비': '-',
                'PRTR대상': 'X', 'PRTR그룹': '-'
            }
            
            if comp.get('kosha_data'):
                regs = comp['kosha_data'].get('legal_regulations', {})
                reg_data['산안법_측정'] = regs.get('작업환경측정', 'X')
                reg_data['산안법_진단'] = regs.get('특수건강진단', 'X')
                reg_data['산안법_관리대상'] = regs.get('관리대상유해물질', 'X')
                reg_data['화관법_유독'] = regs.get('유독물질', '-')
                reg_data['화관법_사고대비'] = regs.get('사고대비물질', '-')
            
            if comp.get('prtr_status'):
                prtr = comp['prtr_status']
                reg_data['PRTR대상'] = prtr.get('대상여부', 'X')
                reg_data['PRTR그룹'] = prtr.get('그룹', '-')
            
            reg_list.append(reg_data)
        
        return {'항목명': '15. 법적 규제현황', '규제정보': reg_list}
    
    def _gen_section_16(self) -> Dict:
        """16. 그 밖의 참고사항"""
        return {
            '항목명': '16. 그 밖의 참고사항',
            '가_참고문헌': ['안전보건공단 화학물질정보', '고용노동부 MSDS 작성지침'],
            '나_작성일자': datetime.now().strftime('%Y-%m-%d'),
            '다_개정일자': '-',
            '라_개정사유': '-'
        }


def create_msds_from_components(product_name: str, components: List[Dict],
                                supplier_info: Dict = None) -> Dict:
    """
    간편 MSDS 생성 함수
    
    Args:
        product_name: 제품명
        components: [{'name': '물질명', 'cas_no': 'CAS번호', 'content': 함유량}]
        supplier_info: {'회사명': '', '주소': '', ...}
    
    Returns:
        MSDS 데이터 딕셔너리
    """
    generator = MSDSGenerator()
    
    # 제품 정보 설정
    supplier_info = supplier_info or {}
    generator.set_product_info(
        product_name=product_name,
        supplier_name=supplier_info.get('회사명', ''),
        supplier_address=supplier_info.get('주소', ''),
        supplier_phone=supplier_info.get('전화번호', ''),
        emergency_phone=supplier_info.get('긴급전화', '119')
    )
    
    # 구성성분 추가
    for comp in components:
        generator.add_component(
            name=comp.get('name', ''),
            cas_no=comp.get('cas_no', ''),
            content=comp.get('content', 0),
            content_range=comp.get('content_range'),
            auto_query=True
        )
    
    # MSDS 생성
    return generator.generate_all_sections()


if __name__ == "__main__":
    # 테스트
    components = [
        {'name': '아세톤', 'cas_no': '67-64-1', 'content': 50},
        {'name': '톨루엔', 'cas_no': '108-88-3', 'content': 30}
    ]
    
    msds = create_msds_from_components("테스트 제품", components)
    print(f"MSDS 생성 완료: {msds.get('generated_at')}")
