"""2안 공통 양식 (2026-11-16 사용자 결정): 다이슨·건강식품·뷰티 리포트를 같은 틀로 만든다.

순서: 요약 → 실적 비교 → 방송별 총평 → 방송 흐름 한눈에(+소구 띠) → 방송 시간을 어디에 썼나 → 같은 시각, 다른 말
      → 멘트 비중(대분류 막대 / 소구별 비중 — 버튼으로 전환) → 소구별 대표 문장 → 분류 기준 → 방송별 NEEDS 순위

세분류 코드는 카테고리마다 다르다(가전 15개, 건강·뷰티 9개). 대분류(상품·조건·신뢰·푸시)와 색은 공통.
사용: python build_unified.py dyson|mbp|drl|sephd|sepcj|sep [--demo]
"""
import csv
import html
import json
import os
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date, datetime

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
DY = os.path.join(ROOT, "out", "narrative", "dyson_v3")
HB = os.path.join(ROOT, "out", "narrative", "hb")

import build_preview as BP  # noqa: E402
import build_preview3 as B3  # noqa: E402
import product_view as PV  # noqa: E402

GROUPS, GROUP_COLORS = BP.GROUPS, BP.GROUP_COLORS
DY_CODES = dict(BP.CODES)
# 2026-11-16 사용자 결정: 같은 대분류끼리 비슷한 색(상품=파랑, 조건=빨강·주황, 신뢰=보라, 푸시=검붉은)
for _k, _c in {"P4": "#0b4f8a", "P5": "#9cc3ea", "T3": "#6b4596", "A3": "#9c4a4a", "A4": "#8e3020", "T4": "#5e1414"}.items():
    if _k in DY_CODES:
        DY_CODES[_k] = DY_CODES[_k][:2] + (_c,) + DY_CODES[_k][3:]
HB_CODES = {
    "PR": ("문제 제기", "상품", "#6fa8dc", "건강·피부 고민, 증상, 위험 경고, 대상 고객 호명"),
    "FX": ("기능·효과", "상품", "#2383e2", "제품·성분이 해 주는 일, 개선·효과 주장"),
    "PD": ("상품 설명·사용법", "상품", "#1a5fa8", "제품 정체, 제형·사용감, 사용·섭취 방법"),
    "PB": ("가격·혜택", "조건", "#e03e3e", "가격, 할인율, 최저가, 무이자·카드·적립, 하루당 가격"),
    "CO": ("구성", "조건", "#d9730d", "병·박스·개월분, 본품·덤·증정 구성"),
    "EV": ("근거·원료", "신뢰", "#9065b0", "성분·함량·원산지·공법·특허·인체시험·인증·브랜드·정품"),
    "EX": ("체험·변화", "신뢰", "#b98fd1", "고객 후기, 호스트·가족·셀럽 사용담, 전후 변화"),
    "PU": ("푸시", "푸시", "#7a1f1f", "1등·판매량·매진·동시 접속 등 인기 숫자, 마감·수량 압박"),
    "CT": ("콜유도", "푸시", "#a8323a", "주문 방법 안내, 주문 권유"),  # 2026-11-16: 가격·혜택·푸시와 같은 붉은 계열
    "XX": ("기타", "기타", "#d9d8d5", "맞장구·진행·잡음"),
}
TOPIC_PALETTE = ["#2383e2", "#0f7b6c", "#d9730d", "#9065b0", "#5b6b7f", "#c29343", "#2aa5a0", "#d36ba6", "#7a4e2d", "#a8a29e"]
CH = {"GS샵": "#2383e2", "롯데홈쇼핑": "#d9730d", "현대홈쇼핑": "#0f7b6c", "CJ온스타일": "#ad1a72"}
WD = "월화수목금토일"

e = B3.e
mmss = BP.mmss


# ---------------------------------------------------------------- 방송별 설정
def hb_bc(key, ch, md, ppm, rev, wmin, price, final, inst, gift, kind, review):
    return {"key": key, "label": f"{ch} {md}", "color": CH[ch], "ch": ch, "ppm": ppm, "rev": rev, "wmin": wmin,
            "price": price, "final": final, "inst": inst, "gift": gift, "kind": kind, "review": review}


SPECS = {
    "mbp": {
        "title": "뼈엔 엠비피", "tax": "mbp", "demo": ("뼈앤엠비피", "2안.html"), "q": "뼈엔 엠비피",
        "bcs": [
            hb_bc("mbp_gs", "GS샵", "10/27", 210, 149_433_000, 71.2, 459000, "436,056원", "12개월", "오메가3 2박스", "근거 축적형",
                  "낙상·폐경기 골밀도 감소로 문제를 길게 깔고, 식약처 인정 원료·인체적용시험(골밀도·골강도 증가)을 세 번 반복했습니다. 가격은 8분 26초에야 처음 꺼냈고 ‘월 3만 원대 · 건강 투자’로 풀었습니다."),
            hb_bc("mbp_lt", "롯데홈쇼핑", "10/21", 78, 26_540_000, 34.1, 459000, "459,000원", "12개월", "오메가3 2박스", "압박형",
                  "첫마디부터 ‘생방송을 기다려오셨죠’, 1분 안에 ‘14박스는 생방송 주문자만’이었습니다. 가을철 낙상·골절 경고로 문제를 제기했지만 판매 멘트의 23%를 방송 희소성·마감 푸시에 썼고, 시험 근거는 GS의 절반 수준이었습니다."),
        ],
        "summary": "같은 뼈엔 엠비피(459,000원 · 무이자 12개월) 두 방송 중 <b>GS샵 10/27이 분당주문액 210만 원으로 롯데홈쇼핑 10/21(78만 원)의 약 2.7배</b>를 팔았습니다. 문장 단위로 비교하면 차이는 <b>‘왜 먹어야 하는가’를 얼마나 쌓았느냐</b>에서 났습니다 — GS는 첫 10분 판매 멘트의 94%를 낙상·폐경기 골밀도 감소(문제 제기)와 인체적용시험(근거)에 썼고, 롯데는 첫마디부터 ‘생방송에서만 14박스’로 <b>푸시</b>(판매 멘트의 23%, GS는 9%)를 앞세웠습니다. <b>고객 고민(NEEDS)</b>으로 보면 GS는 고민 이야기에 24분(롯데 16분)을 썼고, ‘나이 듦·폐경기 여성’처럼 <b>누구에게 왜</b> 위험한지를 롯데의 약 2배로 말했습니다. 롯데는 ‘가을 나들이·계절’이 GS보다 길었습니다.",
        "note": "시간대가 다릅니다(GS 아침 7시 · 롯데 낮 1시 반).",
    },
    "drl": {
        "title": "닥터린 하이퍼셀 대마종자유", "tax": "drl", "demo": ("닥터린", "2안.html"), "q": "닥터린 대마종자유",
        "bcs": [
            hb_bc("drl_gs", "GS샵", "10/28", 263, 315_787_000, 119.9, 298000, "263,100원", "언급 없음", "상품권 추첨", "근거+1등형",
                  "‘GS 1등 대마종자유’로 신뢰를 먼저 세우고, 치킨·곱창 → 포화지방 → 오메가 1:3 비율·비커 시연으로 이어갔습니다. ‘하루 490원꼴’, ‘6박스 공짜 느낌’으로 가격을 낮춰 보였고 ‘1등·매진·동시 접속’을 약 13분 간격으로 반복했습니다."),
            hb_bc("drl_lt", "롯데홈쇼핑", "8/26", 116, 138_490_000, 119.8, 298000, "258,540원", "언급 없음", "없음", "최저가형",
                  "‘역대 최저가 만원대’와 ‘본사가 철벽이라 1년간 못 내렸다’는 협상 이야기로 열었습니다. 판매 멘트의 28%가 가격 이야기였지만 GS도 같은 298,000원이라 차별점이 되지 못했고, 후반 20분은 ‘혜택 다 사라집니다’ 마감 압박이었습니다."),
        ],
        "summary": "같은 닥터린 하이퍼셀 대마종자유(18박스 · 298,000원), 같은 수요일 19:35 두 방송 중 <b>GS샵 10/28이 분당주문액 263만 원으로 롯데홈쇼핑 8/26(116만 원)의 약 2.3배</b>를 팔았습니다. 가격이 같았는데도 롯데는 판매 멘트의 28%를 <b>‘역대 최저가·만원대·본사 협상’ 가격 이야기</b>에 썼고, GS는 그 시간을 <b>근거</b>(오메가 1:3 비율·비커 시연, 30%)와 <b>‘매출·주문고객·재구매율 1등’ 푸시</b>(19%)에 썼습니다. <b>고객 고민(NEEDS)</b>으로 보면 GS는 ‘건강 경각심·오메가6 과잉·추위’(합 7.2분, 롯데 0.7분)로 <b>지금 내 몸에 필요한 이유</b>를, 롯데는 ‘영양제를 따로 먹는 번거로움’(3.2분, GS 0분)으로 <b>하나로 끝내는 편의</b>를 팔았습니다. 롯데 8/26은 31℃ 한여름이라 추위 이야기를 꺼낼 수 없었던 점은 감안해야 합니다.",
        "note": "날짜가 다릅니다(GS 10/28 · 롯데 8/26).",
    },
}
_SEP = {
    "sep_gs": hb_bc("sep_gs", "GS샵", "10/5", 430, 473_107_000, 109.9, 289000, "289,000원", "20개월", "없음", "체험+인기형",
                    "59세 쇼호스트의 2년 반 사용기(맑아짐·동안)와 ‘기초는 그대로, 세포랩만 추가’ 사용법이 중심이었습니다. 그 위에 ‘3년 연속 1등 · 매진 폭주기관차’를 얹었고, 가격 이야기는 판매 멘트의 3%뿐이었습니다."),
    "sep_hd": hb_bc("sep_hd", "현대홈쇼핑", "10/27", 386, 383_526_000, 99.4, 289000, "268,770원", "20개월", "쇼핑지원금 1만원", "구성·정품형",
                    "시작 41초 만에 9병 구성·카드 7%·무이자 20개월·쇼핑지원금을 꺼냈고 ‘가짜가 난리, 여기가 정품’을 반복했습니다. 극건성 게스트가 2년 망설이다 바꾼 체험담으로 ‘물 제형이 정말 될까’ 하는 의심을 풀었습니다."),
    "sep_cj": hb_bc("sep_cj", "CJ온스타일", "9/28", 263, 259_928_000, 99.0, 289000, "260,100원", "20개월", "없음", "감동→할인형",
                    "70대 배우의 ‘피부는 이제 끝났다’는 체념과 회복담으로 첫 3분을 채우고, 4분 31초부터 ‘10% 할인 · 한 달 1만 2천원대’로 넘어갔습니다. 시니어·환절기 건조를 겨냥했고 원료 근거는 세 방송 중 가장 적었습니다."),
}
SPECS["sephd"] = {
    "title": "세포랩 바이오제닉 에센스", "tax": "sep", "demo": ("세포랩", "2안.html"), "q": "세포랩 바이오제닉", "moments": "sephd",
    "bcs": [_SEP["sep_gs"], _SEP["sep_hd"]],
    "summary": "같은 세포랩 바이오제닉 에센스(289,000원), 같은 밤 21:45 두 방송은 <b>GS샵 10/5 430만 원 vs 현대홈쇼핑 10/27 386만 원(약 1.1배)</b>으로 차이가 크지 않습니다. 말하는 방식은 달랐습니다 — 현대는 시작 41초 만에 <b>9병 구성·카드 7%·무이자·쇼핑지원금</b>을 꺼내고 ‘여기가 정품’으로 근거를 쌓았고, GS는 피부 고민과 쇼호스트 체험담, <b>‘3년 연속 1등’ 푸시</b>(판매 멘트의 18%, 현대 11%)로 시작해 가격은 24분 51초에야 꺼냈습니다. <b>고객 고민(NEEDS)</b>으로 보면 현대는 ‘화장품 효과 불신’(8.3분)·‘가품 걱정’(3.5분)으로 <b>의심을 푸는 데</b>, GS는 ‘기초 여러 개 번거로움’(3.1분, 현대 0.1분)을 건드리며 <b>쉽게 하나만 더</b>로 문턱을 낮추는 데 시간을 썼습니다.",
    "note": "날짜가 다릅니다(GS 10/5 · 현대 10/27).",
}
SPECS["sepcj"] = {
    "title": "세포랩 바이오제닉 에센스", "tax": "sep", "demo": ("세포랩", "2안_CJ.html"), "q": "세포랩 바이오제닉", "moments": "sepcj",
    "bcs": [_SEP["sep_gs"], _SEP["sep_cj"]],
    "summary": "같은 세포랩 바이오제닉 에센스(289,000원), 같은 밤 21:45 두 방송 중 <b>GS샵 10/5가 분당주문액 430만 원으로 CJ온스타일 9/28(263만 원)의 약 1.6배</b>를 팔았습니다. 두 방송 모두 판매 멘트의 40% 이상을 <b>체험담</b>에 썼지만, GS는 그 위에 <b>‘3년 연속 1등·매진 폭주기관차’ 푸시</b>(18%, CJ 12%)를 얹고 첫 가격 이야기를 <b>24분 51초</b>까지 미뤘습니다. CJ는 70대 배우의 회복담 직후 4분 31초에 ‘10% 할인 · 한 달 1만 2천원대’로 넘어갔습니다. <b>고객 고민(NEEDS)</b>으로 보면 CJ는 고민 이야기의 42%를 ‘중장년 노화 체념’(9.6분) 하나에 쏟았고, GS는 같은 고민(6.1분) 외에 ‘남성·가족 피부’, ‘기초 여러 개 번거로움’(3.1분, CJ 0.1분)까지 <b>가장 넓게</b>(1위 비중 29%) 펼쳤습니다.",
    "note": "CJ 9/28은 추석 연휴 직후이고 구성에 마스크팩·솝이 섞여 있습니다.",
}
SPECS["sephdcj"] = {
    "title": "세포랩 바이오제닉 에센스", "tax": "sep", "demo": ("세포랩", "2안_현대CJ.html"), "q": "세포랩 바이오제닉", "moments": "sepcj",
    "bcs": [_SEP["sep_hd"], _SEP["sep_cj"]],
    "summary": "같은 세포랩 바이오제닉 에센스(289,000원), 같은 밤 21:45 두 방송 중 <b>현대홈쇼핑 10/27이 분당주문액 386만 원으로 CJ온스타일 9/28(263만 원)의 약 1.5배</b>를 팔았습니다. "
               "두 방송 모두 체험담이 주력이었지만, 현대는 시작 41초 만에 <b>9병 구성·카드 7%·무이자</b>를 꺼내고 ‘가짜가 난리, 여기가 정품’으로 <b>근거</b>(15%, CJ 6%)를 쌓았고, "
               "CJ는 70대 배우의 회복담 직후 4분 31초에 ‘10% 할인’으로 넘어갔습니다. "
               "<b>고객 고민(NEEDS)</b>으로 보면 현대는 ‘화장품 효과 불신’(8.3분)·‘가품 걱정’(3.5분)으로 <b>의심 풀기</b>, CJ는 ‘중장년 노화 체념’(9.6분, 고민 이야기의 42%) 하나에 집중했습니다.",
    "note": "날짜가 다릅니다(현대 10/27 · CJ 9/28 추석 연휴 직후). CJ 구성에는 마스크팩·솝이 섞여 있습니다.",
}
SPECS["sep"] = {
    "title": "세포랩 바이오제닉 에센스", "tax": "sep", "demo": ("세포랩", "2안_3사.html"), "q": "세포랩 바이오제닉", "moments": "sepcj",
    "bcs": [_SEP["sep_gs"], _SEP["sep_hd"], _SEP["sep_cj"]],
    "summary": "같은 세포랩 바이오제닉 에센스(289,000원), 같은 밤 21:45 세 방송 중 <b>GS샵 10/5가 분당주문액 430만 원으로 가장 잘 팔았고</b>, 현대 10/27 386만 원, CJ 9/28 263만 원 순이었습니다. 세 방송 모두 판매 멘트의 35~44%를 <b>체험담</b>에 써서 그것만으로는 순위가 갈리지 않았습니다 — GS만 <b>‘3년 연속 1등·매진’ 푸시를 가장 많이</b>(18%), <b>가격 이야기는 가장 적고 늦게</b>(3% · 24분 51초) 했습니다. 현대는 구성·정품, CJ는 감동 직후 할인으로 갔습니다. <b>고객 고민(NEEDS)</b>으로 보면 셋이 갈립니다 — GS는 ‘기초 여러 개 번거로움’(3.1분, 다른 두 곳 0.1분)을 건드리며 고민을 가장 넓게 펼쳤고, 현대는 ‘효과 불신·가품 걱정’(합 11.8분)으로 의심 풀기, CJ는 ‘중장년 노화 체념’(9.6분, 고민 이야기의 42%) 하나에 집중했습니다.",
    "note": "날짜가 다릅니다(GS 10/5 · CJ 9/28 추석 연휴 직후 · 현대 10/27). CJ 구성에는 마스크팩·솝이 섞여 있습니다.",
}
_DY = {k: {"key": k, "label": lb, "color": c, "ppm": p} for k, lb, c, p in
       (("gs0107", "GS샵 1/7", "#2383e2", 570), ("gs0217", "GS샵 2/17", "#d9730d", 579), ("hd0621", "현대홈쇼핑 6/21", "#0f7b6c", 714))}
_DYF = {"gs0107": "260107_1435_GS_다이슨 디지털 슬림 무선청소기.txt", "gs0217": "260217_2255_GS_다이슨 디지털 슬림 무선청소기.txt",
        "hd0621": "260621_1230_현대_다이슨 디지털 슬림 무선청소기.txt"}
SPECS["dy_0217_hd"] = {
    "title": "다이슨 디지털 슬림", "family": "dyson", "demo": ("다이슨", "리포트_GS0217_현대.html"), "moments": "dyson",
    "bcs": [_DY["gs0217"], _DY["hd0621"]],
    "summary": "같은 다이슨 디지털 슬림 두 방송 중 <b>현대홈쇼핑 6/21이 분당주문액 714만 원으로 GS샵 2/17(579만 원)보다 약 23% 더 팔았습니다.</b> "
               "차이는 <b>‘왜 여기서 사야 하는가’</b>에서 났습니다 — 현대는 판매 멘트의 23%(약 15분)를 <b>가격 비교·독점</b>(‘현대만·역대 최저가’)에 썼고, "
               "GS 2/17은 같은 자리에 3%(약 1분)만 쓰고 <b>희소성·카운트다운 푸시</b>(16%)와 <b>호스트 체험담</b>(8%)으로 채웠습니다. "
               "<b>고객 고민(NEEDS)</b>으로 보면 현대는 ‘침구 진드기·먼지’ 하나에 모았고, 설날 당일인 GS 2/17은 아이·선물까지 가장 넓게 흩어졌습니다.",
}
SPECS["dy_0107_hd"] = {
    "title": "다이슨 디지털 슬림", "family": "dyson", "demo": ("다이슨", "리포트_GS0107_현대.html"), "moments": "dyson",
    "bcs": [_DY["gs0107"], _DY["hd0621"]],
    "summary": "같은 다이슨 디지털 슬림 두 방송 중 <b>현대홈쇼핑 6/21이 분당주문액 714만 원으로 GS샵 1/7(570만 원)보다 약 25% 더 팔았습니다.</b> "
               "현대는 판매 멘트의 23%(약 15분)를 <b>가격 비교·독점</b>(‘현대만·역대 최저가’)에 썼고, GS 1/7은 그 자리를 "
               "<b>희소성·수량·주문 푸시</b>(합 21% — ‘다음 방송 미정·매진 예상·지금 주문’)로 채웠습니다. "
               "<b>고객 고민(NEEDS)</b>으로 보면 현대는 ‘침구 진드기·먼지’에 고민 이야기의 37%를 모았고, GS 1/7은 진드기·기존 청소기 불만·손목 부담으로 고르게 나눴습니다.",
}
SPECS["dy_gs"] = {
    "title": "다이슨 디지털 슬림", "family": "dyson", "demo": ("다이슨", "리포트_GS두방송.html"), "moments": "dyson",
    "bcs": [_DY["gs0107"], _DY["gs0217"]],
    "summary": "같은 GS샵, 같은 370,000원의 두 방송은 <b>분당주문액 570만 원 vs 579만 원으로 거의 같았습니다</b>(효율 지수 100 vs 102). "
               "말하는 방식은 달랐습니다 — 1/7은 <b>생활 공감</b>(12%)과 <b>주문·수량 푸시</b>(13%)로 밀었고, 설날 당일인 2/17은 "
               "<b>호스트 체험담</b>(8%)과 브랜드·고객 증언으로 <b>신뢰</b>(16%, 1/7은 10%)를 더 쌓았습니다. "
               "화법 차이가 실적 차이로 이어지지 않은 사례라, 다른 상품 비교의 기준선으로 보시면 됩니다.",
}
SPECS["dyson"] = {
    "title": "다이슨 디지털 슬림", "family": "dyson", "demo": ("다이슨", "리포트.html"), "moments": "dyson",
    "bcs": [{"key": k, "label": lb, "color": c, "ppm": p} for k, lb, c, p in
            (("gs0107", "GS샵 1/7", "#2383e2", 570), ("gs0217", "GS샵 2/17", "#d9730d", 579), ("hd0621", "현대홈쇼핑 6/21", "#0f7b6c", 714))],
}


# ---------------------------------------------------------------- 데이터 읽기
def use_codes(codes):
    B3.CODES = codes
    BP.CODES = codes


def hb_load(key):
    d = json.load(open(os.path.join(HB, f"{key}_units.json"), encoding="utf-8"))
    lab, fix = {}, {}
    for ln in open(os.path.join(HB, f"{key}_labels.tsv"), encoding="utf-8"):
        p = ln.rstrip("\n").split("\t")
        if len(p) >= 2 and p[0].strip().isdigit():
            lab[int(p[0])] = p[1].strip().upper()
    fp = os.path.join(HB, f"{key}_fixes.tsv")
    if os.path.exists(fp):
        for ln in open(fp, encoding="utf-8"):
            p = ln.rstrip("\n").split("\t")
            if len(p) >= 2 and p[0].strip().isdigit():
                fix[int(p[0])] = (p[1].strip().upper(), (p[2].strip() if len(p) > 2 else "").replace("검수: ", ""))
    us, n_fix = [], 0
    for u in d["units"]:
        o = lab.get(u["u"], "XX")
        c, why = fix.get(u["u"], (o, ""))
        if c not in HB_CODES:
            c = "XX"
        n_fix += c != o
        us.append({"u": u["u"], "t": u["t"], "text": u["text"], "code": c, "orig": o if o in HB_CODES else c,
                   "why": why, "vcr": False})
    return us, n_fix, d["meta"]


def hb_taxonomy(tax):
    s, n = [], []
    for r in csv.DictReader(open(os.path.join(HB, f"{tax}_taxonomy.tsv"), encoding="utf-8"), delimiter="\t"):
        (s if r["종류"].strip() == "소구" else n).append(r["이름"].strip())
    return s, n


def hb_tags(key, units):
    tags = {}
    sel = {"PR", "FX", "EV", "EX", "PD"}
    for r in csv.DictReader(open(os.path.join(HB, f"{key}_topics.tsv"), encoding="utf-8"), delimiter="\t"):
        i = int(r["idx"])
        if i < len(units) and units[i]["code"] in sel:
            sp = lambda c: [x.strip() for x in (c or "").split(";") if x.strip() and x.strip() != "-"]
            tags[i] = {"s": sp(r["소구"]), "n": sp(r["NEEDS"]), "m": ""}
    return tags


OPEN_KEEP_SEC = 40  # 2026-11-16 사용자 지적: 오프닝(첫 구간)은 짧아도 이웃에 합치지 않는다(첫인상이 묻히지 않게)


def segment_keep_opening(units, end_t):
    """B3.segment 와 같되, 방송 첫 대분류 구간이 OPEN_KEEP_SEC 이상이면 따로 떼어 둔다."""
    grp = lambda u: B3.CODES[u["code"]][1]
    g0, cut = None, len(units)
    for i, u in enumerate(units):
        if grp(u) == "기타":
            continue
        if g0 is None:
            g0 = grp(u)
        elif grp(u) != g0:
            cut = i
            break
    if g0 is None or cut >= len(units) or units[cut]["t"] - units[0]["t"] < OPEN_KEEP_SEC:
        return B3.segment(units, end_t)
    head = B3.segment(units[:cut], units[cut]["t"])
    return head + B3.segment(units[cut:], end_t)


def fine_strip(b, total, codes):
    """2분 단위 막대 바로 아래 정밀 띠: 문장 하나하나를 대분류 색으로(진행·맞장구는 비움)."""
    us = b["units"]
    out = []
    for k, u in enumerate(us):
        g = codes[u["code"]][1]
        if g == "기타":
            continue
        t1 = min(us[k + 1]["t"] if k + 1 < len(us) else b["end"], u["t"] + 20)
        out.append(f"<i title='{mmss(u['t'])} · {g} · {e(codes[u['code']][0])}: {e(u['text'][:60])}' style='left:{100 * u['t'] / total:.3f}%;"
                   f"width:{max(100 * (t1 - u['t']) / total, 0.12):.3f}%;background:{GROUP_COLORS[g]}'></i>")
    return f"<div class='fstrip'>{''.join(out)}</div>"


def recolor_sub(emph, data, codes):
    """2026-11-16 사용자 지적: 소분류 막대도 대분류처럼 '분류 색'으로. 방송은 진하기(첫 방송 진하게)와 이름표로 구분."""
    import re
    alpha = {b["key"]: a for b, a in zip(data, [1.0, 0.5, 0.3, 0.2])}
    label = {b["key"]: b["label"] for b in data}

    def bar(m):
        key, code = m.group(1), m.group(2)
        col = codes.get(code, ("", "", "#c7c6c3"))[2]
        body = m.group(3).replace(f"background:{m.group(4)}", f"background:{col};opacity:{alpha.get(key, 1)}")
        return f"<div class='ebar sub2' data-k='{key}:{code}'{m.group(5)}><span class='bn'>{e(label.get(key, key))}</span>{body}"

    emph = re.sub(r"<div class='ebar' data-k='([^':]+):([A-Z0-9]+)'( title='[^']*')?>(<i [^>]*background:(#[0-9a-fA-F]{3,6})'[^>]*>)",
                  lambda m: bar(type("M", (), {"group": lambda self, i: {1: m.group(1), 2: m.group(2), 3: m.group(4), 4: m.group(5), 5: m.group(3) or ""}[i]})()),
                  emph)
    # 대분류 머리줄의 방송 이름은 기본 글자색으로
    for b in data:
        emph = emph.replace(f"<span style='color:{b['color']}'>{e(b['label'])} <b class='num'>", f"<span style='color:#37352f'>{e(b['label'])} <b class='num'>")
    legend = " · ".join(f"<span style='display:inline-flex;align-items:center;gap:5px'><i style='display:inline-block;width:22px;height:10px;border-radius:2px;background:#787774;opacity:{alpha[b['key']]}'></i>{e(b['label'])}</span>" for b in data)
    emph = re.sub(r"<div class=\"elg\"[^>]*>소분류 막대 색 = 방송 · .*?</div>",
                  f"<div class='elg' style='margin-top:10px'>막대 색 = 분류 색(위 대분류와 같음) · 진하기로 방송 구분: {legend}</div>", emph, flags=re.S)
    emph += "<style>.ebar.sub2 .bn{width:92px;flex:none;font-size:12px;font-weight:600}</style>"
    return emph


# ---------------------------------------------------------------- 새 칸들
def sell_codes(codes):
    return [k for g in GROUPS for k in codes if codes[k][1] == g]


def minutes(b, codes):
    tot = sum(B3.weight(u) for u in b["units"]) or 1
    dur = b["end"] / 60
    c = Counter()
    for u in b["units"]:
        c[u["code"]] += B3.weight(u)
    return {k: dur * c[k] / tot for k in codes}


def bf_order(hi, lo, codes):
    sc = sell_codes(codes)
    mh, ml = minutes(hi, sc), minutes(lo, sc)
    order = [k for k in sorted(sc, key=lambda k: -(mh[k] + ml[k])) if mh[k] + ml[k] >= 0.05]
    strong = set(sorted(sc, key=lambda k: -abs(mh[k] - ml[k]))[:3])
    return order, strong


def butterfly(hi, lo, codes):
    sc = sell_codes(codes)
    mh, ml = minutes(hi, sc), minutes(lo, sc)
    strong = set(sorted(sc, key=lambda k: -abs(mh[k] - ml[k]))[:3])
    mx = max(max(mh[k], ml[k]) for k in sc) or 1
    rows = ""
    for k in sorted(sc, key=lambda k: -(mh[k] + ml[k])):
        if mh[k] + ml[k] < 0.05:
            continue
        rows += (f"<div class='bf{' strong' if k in strong else ''}'>"
                 f"<div class='bfl'><span class='bfv'>{mh[k]:.0f}분</span><i style='width:{100 * mh[k] / mx:.1f}%;background:{codes[k][2]}'></i></div>"
                 f"<div class='bfc'>{e(codes[k][0])}</div>"
                 f"<div class='bfr'><i style='width:{100 * ml[k] / mx:.1f}%;background:{codes[k][2]}'></i><span class='bfv'>{ml[k]:.0f}분</span></div></div>")
    return (f"<h2>방송 시간을 어디에 썼나</h2><p class='sub'>세분류별로 실제 말한 시간(분, 글자 수 비율로 환산 · 진행·맞장구 제외). "
            f"분당주문액이 가장 높은 방송과 가장 낮은 방송을 맞댔고, 차이가 큰 3개를 진하게 표시했습니다.</p>"
            f"<div class='bfh'><div style='color:{hi['color']}'>{e(hi['label'])} · 분당 {hi['ppm']}만</div><div></div>"
            f"<div style='color:{lo['color']}'>{e(lo['label'])} · 분당 {lo['ppm']}만</div></div>{rows}")


def moments(hi, lo, codes, mfile):
    rows = ""
    byi = lambda b, i: next((u for u in b["units"] if u.get("u", -1) == i), b["units"][i] if i < len(b["units"]) else None)
    cell = lambda u: (f"<span class='mt'>{mmss(u['t'])}</span><span class='chip' style='background:{codes[u['code']][2]}'>{e(codes[u['code']][0])}</span>"
                      f"<span class='mq'>“{e(u['text'])}”</span>") if u else ""
    if mfile and os.path.exists(mfile):
        for ln in open(mfile, encoding="utf-8"):
            p = ln.rstrip("\n").split("\t")
            if len(p) >= 3 and p[1].strip().isdigit() and p[2].strip().isdigit():
                rows += f"<tr><td class='ml'>{e(p[0])}</td><td>{cell(byi(hi, int(p[1])))}</td><td>{cell(byi(lo, int(p[2])))}</td></tr>"
    if not rows:
        return ""
    return (f"<h2>같은 시각, 다른 말</h2><p class='sub'>두 방송이 같은 대목에서 실제로 한 말(자막 원문).</p>"
            f"<table class='mtab'><tr><th></th><th style='color:{hi['color']}'>{e(hi['label'])} · 분당 {hi['ppm']}만</th>"
            f"<th style='color:{lo['color']}'>{e(lo['label'])} · 분당 {lo['ppm']}만</th></tr>{rows}</table>")


def share_view(data, codes):
    """멘트 비중 B: 세분류 색 막대 + 표(차이 4%p 이상 최댓값 강조)."""
    sc = sell_codes(codes)
    sh = {}
    for b in data:
        c = Counter()
        for u in b["units"]:
            if u["code"] in sc:
                c[u["code"]] += B3.weight(u)
        t = sum(c.values()) or 1
        sh[b["key"]] = {k: 100 * c[k] / t for k in sc}
    bars = "".join(
        f"<div class='sb-row'><div class='sb-l'><span class='sw' style='background:{b['color']}'></span>{e(b['label'])} <span class='sub'>분당 {b['ppm']}만</span></div>"
        f"<div class='sb-bar'>" + "".join(f"<i style='width:{sh[b['key']][k]:.2f}%;background:{codes[k][2]}' title='{e(codes[k][0])} {sh[b['key']][k]:.0f}%'></i>" for k in sc if sh[b['key']][k] > 0)
        + "</div></div>" for b in data)
    legend = "".join(f"<span><i style='background:{codes[k][2]}'></i>{e(codes[k][0])}</span>" for k in sc)
    head = "".join(f"<th class='n' style='color:{b['color']}'>{e(b['label'])}</th>" for b in data)
    rows = ""
    for g in GROUPS:
        gk = [k for k in sc if codes[k][1] == g]
        rows += f"<tr class='g'><td><b style='color:{GROUP_COLORS[g]}'>{g}</b></td>" + "".join(
            f"<td class='n'><b>{sum(sh[b['key']][k] for k in gk):.0f}%</b></td>" for b in data) + "</tr>"
        for k in gk:
            vals = [sh[b["key"]][k] for b in data]
            mx, mn = max(vals), min(vals)
            rows += f"<tr><td><span class='dot' style='background:{codes[k][2]}'></span>{e(codes[k][0])}</td>" + "".join(
                f"<td class='n{' hi' if v == mx and mx - mn >= 4 else ''}'>{v:.0f}%</td>" for v in vals) + "</tr>"
    return (f"<p class='sub'>판매 멘트(진행·맞장구·잡음 제외) 글자 수 기준 비중. 노란 칸은 방송 간 차이가 4%p 이상인 곳의 최댓값입니다.</p>"
            f"{bars}<div class='sb-lg'>{legend}</div><table class='sbt'><tr><th>분류</th>{head}</tr>{rows}</table>")


def examples(data, codes, order=None, opened=()):
    out = ""
    for k in (order or sell_codes(codes)):
        cols = ""
        for b in data:
            us = [u for u in b["units"] if u["code"] == k and len(u["text"]) >= 15]
            # 방송을 네 토막으로 나눠 토막마다 내용이 가장 많은 문장(25~110자 사이에서 긴 것)을 고른다
            pick = []
            for q in range(4):
                part = [u for u in us if q * b["end"] / 4 <= u["t"] < (q + 1) * b["end"] / 4]
                if part:
                    pick.append(max(part, key=lambda u: min(len(u["text"]), 110) - (40 if len(u["text"]) > 160 else 0)))
            if len(pick) < min(4, len(us)):  # 한 토막에 몰린 분류는 남는 문장에서 채운다
                rest = sorted((u for u in us if u not in pick), key=lambda u: -min(len(u["text"]), 110))
                pick = sorted(pick + rest[:min(4, len(us)) - len(pick)], key=lambda u: u["t"])
            n = sum(1 for u in b["units"] if u["code"] == k)
            cols += (f"<div><div class='exh' style='color:{b['color']}'>{e(b['label'])} <span class='sub'>{n}문장</span></div>"
                     + ("".join(f"<div class='exl'><span class='t'>{mmss(u['t'])}</span>{e(u['text'])}</div>" for u in pick) or "<div class='sub'>없음</div>")
                     + "</div>")
        out += (f"<details class='exd'{' open' if k in opened else ''}><summary><span class='dot' style='background:{codes[k][2]}'></span><b>{e(codes[k][0])}</b>"
                f" <span class='sub'>— {e(codes[k][3])}</span></summary><div class='exc' style='grid-template-columns:repeat({len(data)},1fr)'>{cols}</div></details>")
    return (f"<h3 style='margin-top:26px'>소구별 대표 문장</h3><p class='sub'>위 막대와 같은 순서 · 차이가 큰 3개는 펼쳐 두었습니다 · "
            f"방송을 네 토막으로 나눠 토막마다 내용이 가장 많은 문장을 하나씩 골랐습니다.</p>{out}")


def criteria(codes):
    rows = "".join(
        f"<tr><td><span class='dot' style='background:{v[2]}'></span><b>{e(v[0])}</b></td><td class='sub'>{e(v[1])}</td><td>{e(v[3])}</td></tr>"
        for k, v in codes.items() if k != "X2")
    return f"<h2>분류 기준</h2><table class='crt'><tr><th>세분류</th><th>대분류</th><th>판단 기준</th></tr>{rows}</table>"


def needs_minutes(b):
    """방송별 NEEDS → (분, 문장 수, 상품 멘트 중 %). 분 = 그 고민을 건드린 문장의 글자 수를 방송 길이로 환산."""
    st = b["pstat"]
    tot = sum(B3.weight(u) for u in b["units"]) or 1
    dur = b["end"] / 60
    return {n: (dur * st["N"][n] / tot, len(st["sent"].get("n:" + n, [])), 100 * st["N"][n] / (st["tot"] or 1)) for n in PV.NEEDS}


NEEDS_NOTE = {  # 2026-11-16: 총평 카드에 붙이는 '누구의 어떤 고민을 건드렸나' 해석(분 = 리포트 NEEDS 순위와 같은 계산)
    "mbp_gs": "‘나이 듦’(4.8분)·‘폐경기 여성’(4.2분)처럼 <b>누구에게 왜</b> 위험한지를 롯데의 약 2배로 말했습니다.",
    "mbp_lt": "‘가을 야외활동·계절’(3.2분)이 GS보다 길었지만, 대상(폐경기 2.1분)과 원인(나이 듦 2.2분) 설명은 짧았습니다.",
    "drl_gs": "‘건강 경각심’(2.6분)·‘오메가6 과잉’(2.4분)·‘추위’(2.2분)로 <b>지금 내 몸에 필요한 이유</b>를 건드렸습니다.",
    "drl_lt": "두 번째 고민이 ‘영양제를 따로 먹는 번거로움’(3.2분, GS 0분) — 효능보다 <b>하나로 끝내는 편의</b>를 팔았습니다.",
    "sep_gs": "‘기초 여러 개 번거로움’(3.1분)을 사실상 혼자 건드렸고, 1위 고민 비중이 29%로 고민을 가장 <b>넓게</b> 펼쳤습니다.",
    "sep_hd": "‘화장품 효과 불신’(8.3분)과 ‘가품 걱정’(3.5분)이 가장 많아 <b>의심을 푸는 데</b> 시간을 썼습니다.",
    "sep_cj": "고민 이야기의 42%가 ‘중장년 노화 체념’(9.6분) 하나 — 시니어에 <b>깊게, 대신 좁게</b> 들어갔습니다.",
    "hd0621": "고민 이야기 12.3분 중 37%(4.5분)를 ‘침구 진드기·먼지’ 하나에 <b>모았습니다</b>.",
    "gs0107": "‘침구 진드기’(3.7분)·‘기존 청소기 불만’(3.4분)·‘손목 부담’(2.2분)으로 고르게 나눴습니다.",
    "gs0217": "설날 당일 방송 — 아이 있는 집·선물·효도까지 고민이 가장 <b>흩어졌습니다</b>(1위 비중 21%).",
}


def needs_line(b):
    m = needs_minutes(b)
    top = sorted(m, key=lambda n: -m[n][0])[:3]
    return (f"<p class='ndl'><b>건드린 고민</b> " + " · ".join(f"{e(n)} {m[n][0]:.1f}분" for n in top)
            + (f"<br>{NEEDS_NOTE[b['key']]}" if b["key"] in NEEDS_NOTE else "") + "</p>")


def needs_cards(data):
    """2026-11-16 사용자 결정: NEEDS 순위는 절대량(분·문장 수)으로. %는 작게 보조."""
    mins = {b["key"]: needs_minutes(b) for b in data}
    mx = max((v[0] for m in mins.values() for v in m.values()), default=1) or 1
    cards = ""
    for b in data:
        m = mins[b["key"]]
        top = [n for n in sorted(m, key=lambda n: -m[n][0]) if m[n][0] > 0][:5]
        rows = "".join(
            f"<div class='nr' data-k='{b['key']}' data-q='n:{e(n)}' title='눌러서 문장 보기'><span class='nn'>{i + 1}. {e(n)}</span>"
            f"<span class='nb'><i style='width:{100 * m[n][0] / mx:.1f}%;background:{b['color']}'></i></span>"
            f"<span class='nv' style='width:auto;white-space:nowrap'><b>{m[n][0]:.1f}분</b> · {m[n][1]}문장 <span class='sub'>({m[n][2]:.0f}%)</span></span></div>"
            for i, n in enumerate(top))
        others = [n for n in m if n not in top and m[n][0] > 0]
        tot = sum(v[0] for v in m.values())
        cards += (f"<div class='nc' style='--c:{b['color']}'><h3 style='color:{b['color']}'>{e(b['label'])}</h3>"
                  f"<div class='sub' style='margin-bottom:4px'>고민 이야기 합계 {tot:.1f}분</div>{rows}"
                  + (f"<div class='sub' style='margin-top:6px'>그 밖: {e(' · '.join(others))}</div>" if others else "") + "</div>")
    return f"<div class='ncs'>{cards}</div>"


def needs_only(sec_html):
    a = sec_html.index("<h2>상품 소구 분석")
    z = sec_html.index("<h3>방송별 NEEDS 순위</h3>")
    return sec_html[:a] + "<h2>방송별 NEEDS 순위</h2>" + sec_html[z + len("<h3>방송별 NEEDS 순위</h3>"):]


EXTRA_CSS = """
.nr{grid-template-columns:150px 1fr 150px!important}
.ndl{font-size:13.5px!important;color:#5c5c5c;border-top:1px dashed #e9e9e7;padding-top:8px;margin-top:8px!important;line-height:1.65!important}.nc .nv b{color:#37352f}
.fstrip{position:relative;height:11px;margin-top:3px;background:#f7f6f3;border-radius:2px}
.fstrip i{position:absolute;top:0;bottom:0;display:block}
.bfh,.bf{display:grid;grid-template-columns:1fr 150px 1fr;align-items:center;gap:8px}.bfh{font-weight:700;font-size:14px;margin-top:10px}.bfh div:first-child{text-align:right}
.bf{margin:5px 0;opacity:.45}.bf.strong{opacity:1}.bf.strong .bfc{font-weight:800}
.bfl,.bfr{display:flex;align-items:center;gap:6px;height:20px}.bfl{justify-content:flex-end}.bfl i,.bfr i{display:block;height:100%;border-radius:3px}
.bfc{text-align:center;font-size:13.5px}.bfv{font-size:12.5px;font-variant-numeric:tabular-nums;white-space:nowrap}
.mtab{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}.mtab th,.mtab td{border-bottom:1px solid #e9e9e7;padding:9px 10px;text-align:left;vertical-align:top}
.mtab th{background:#f7f6f3;font-size:13px}.mtab td{width:44%}.mtab td.ml{width:12%;color:rgba(55,53,47,.55);font-weight:600;white-space:nowrap}
.mt{color:rgba(55,53,47,.5);font-size:12px;margin-right:6px;font-variant-numeric:tabular-nums}.mtab .chip{display:inline-block;color:#fff;font-size:11px;border-radius:3px;padding:0 6px;margin-right:6px}
.vtog{margin:6px 0 4px}.vtog button{border:1px solid #e9e9e7;background:#fff;border-radius:4px;padding:4px 12px;font-size:13px;cursor:pointer}
.vtog button.on{background:#37352f;color:#fff;border-color:#37352f}
.sb-row{margin:10px 0}.sb-l{font-size:14px;margin-bottom:3px;font-weight:600}.sb-bar{display:flex;height:22px;border-radius:4px;overflow:hidden;background:#f1f1ef}.sb-bar i{display:block;height:100%}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
.sb-lg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12.5px;margin:6px 0}.sb-lg i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:-1px}
.sbt,.crt{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}.sbt th,.sbt td,.crt th,.crt td{border-bottom:1px solid #e9e9e7;padding:7px 10px;text-align:left}
.sbt th,.crt th{background:#f7f6f3;color:rgba(55,53,47,.55);font-weight:500;font-size:13px}.sbt .n{text-align:right;font-variant-numeric:tabular-nums}
.sbt td.hi{background:#fdecc8;font-weight:700}.sbt tr.g td{background:#fbfbfa}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px;vertical-align:-1px}
.exd{border:1px solid #e9e9e7;border-radius:6px;margin:8px 0;padding:8px 12px}.exd summary{cursor:pointer}
.exc{display:grid;gap:14px;margin-top:8px}.exh{font-weight:650;margin-bottom:4px}.exl{font-size:13.5px;padding:3px 0;border-bottom:1px dashed #f1f1ef;line-height:1.55}
.exl .t{color:rgba(55,53,47,.5);font-size:12px;margin-right:8px}
@media(max-width:700px){.bfh,.bf{grid-template-columns:1fr 90px 1fr}.exc{grid-template-columns:1fr!important}.mtab td{display:block;width:auto}}
"""


# ---------------------------------------------------------------- 위쪽(요약·실적·총평)
def wx_td(day_iso):
    """실적 표 날씨 칸(기상청 서울, 일 단위). 사내 '아이템 편성 비교' 데이터."""
    try:
        sys.path.insert(0, ROOT)
        from hsbot.sources import cmpsite
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            w = cmpsite.weather(day_iso)
        finally:
            os.chdir(cwd)
    except Exception:  # noqa: BLE001
        w = None
    if not w:
        return "<td>–</td>"
    rain = f" · <b>비 {w['rain']:.1f}mm</b>" if w["rain"] else ""
    return f"<td style='white-space:nowrap'>{e(w['name'])} {w['hi']:.0f}°/{w['lo']:.0f}°{rain}</td>"


def won(x):
    return f"{x / 1e8:.2f}억" if x >= 1e8 else f"{x / 1e4:,.0f}만"


def hb_top(spec, data):
    tp = open(os.path.join(TOOLS, "top_dyson.html"), encoding="utf-8").read()
    css = tp[:tp.index("</style>") + 8]
    css2 = tp[tp.index("<style>", 10):]
    css2 = css2[:css2.index("</style>") + 8]
    base = min(b["ppm"] for b in data)
    best = max(b["ppm"] for b in data)
    q = __import__("urllib.parse").parse.quote(spec["q"])
    trs = ""
    for b in data:
        d = date.fromisoformat(b["start"][:10])
        when = f"{d.year} {d.month:02d}/{d.day:02d}({WD[d.weekday()]}) {b['start'][11:16]}"
        trs += (f"<tr{' class=\"pi-best\"' if b['ppm'] == best else ''}><td><span class='pi-when'>{when}</span>"
                f"<a class='pi-a' href='https://hsmoa.com/?q={q}' target='_blank' rel='noopener' title='홈쇼핑모아에서 보기'>"
                f"<i class='pi-dot' style='background:{b['color']}'></i>{e(b['ch'])} <span class='pi-ext'>↗</span></a></td>"
                f"<td>{b['wmin']:.1f}분</td><td class='pi-g'>{b['price']:,}원</td><td>{e(b['final'])}</td><td>{e(b['inst'])}</td><td>{e(b['gift'])}</td>{wx_td(b['start'][:10])}"
                f"<td class='pi-g'>{won(b['rev'])}</td><td><b>{b['ppm']}만</b></td><td><b>{round(100 * b['ppm'] / base)}</b></td></tr>")
    def bars(title, f, txt):
        mx = max(f(b) for b in data) or 1
        return (f"<div><div class='pi-h'>{title}</div>" + "".join(
            f"<div class='pi-row'><span style='color:{b['color']}'>{e(b['label'])}</span><span class='pi-track'><i style='width:{100 * f(b) / mx:.1f}%;background:{b['color']}'></i></span><span class='pi-v'>{txt(b)}</span></div>"
            for b in data) + "</div>")
    grid = (bars("편성 추정 매출", lambda b: b["rev"], lambda b: won(b["rev"])) + bars("가중분", lambda b: b["wmin"], lambda b: f"{b['wmin']:.1f}분")
            + bars("분당주문액", lambda b: b["ppm"], lambda b: f"{b['ppm']}만"))
    legend = "".join(f"<span><i class='pi-dot' style='background:{b['color']}'></i>{e(b['label'])}</span>" for b in data)
    base_lb = next(b["label"] for b in data if b["ppm"] == base)
    revs = ""
    for b in data:
        d = date.fromisoformat(b["start"][:10])
        hh = int(b["start"][11:13])
        slot = "아침" if hh < 11 else "낮" if hh < 17 else "저녁" if hh < 21 else "밤"
        idx = round(100 * b["ppm"] / base)
        grade = f"<span class='grade {'good' if b['ppm'] == best else 'mid'}'>지수 {idx}{' · 최고' if b['ppm'] == best else ''}</span>"
        revs += (f"<div class='rev' style='--c:{b['color']}'><h3 style='color:{b['color']}'>{e(b['label'])} {grade}</h3>"
                 f"<div class='meta'>{WD[d.weekday()]}요일 {slot} · <b>{e(b['kind'])}</b></div><p>{e(b['review'])}</p>{needs_line(b)}</div>")
    return f"""{css}
<div class="sumcall">{spec['summary']}</div>
{css2}
<h2>실적 비교</h2>
<div class="pi-legend">{legend}</div>
<div class="pi-panel"><b>비교 방송 정보</b> <span class="sub">모두 라이브 · {e(spec['title'])} · 방송명을 누르면 홈쇼핑모아로 이동</span>
<div class="pi-sc"><table class="pi-t"><thead><tr><th>홈쇼핑사</th><th>가중분</th><th class="pi-g">판매가</th><th>멘트상 최종가</th><th>무이자</th><th>사은품</th><th>날씨(서울)</th><th class="pi-g">편성 추정 매출</th><th>분당주문액</th><th>효율 지수</th></tr></thead><tbody>{trs}</tbody></table></div>
<div class="pi-grid">{grid}</div></div>
<p class="ev">분당주문액 = 편성 추정 매출(사내 ‘아이템 편성 비교’, 라방바 원천) ÷ 가중분(원천 가중노출분). 효율 지수는 {e(base_lb)}을 100으로 둔 상대값. 최종가·무이자·사은품은 방송 멘트에서 확인한 값입니다(언급된 할인을 모두 적용). {e(spec.get('note', ''))}</p>
<h2>방송별 총평</h2>
<div class="revs">{revs}</div>
"""


DYSON_NEEDS_SUM = ("<b>고객 고민(NEEDS)</b>으로 보면 현대는 고민 이야기의 37%(4.5분)를 ‘침구 진드기·먼지’ 하나에 모았고, "
                   "GS 1/7은 진드기·기존 청소기 불만·손목 부담으로 고르게 나눴으며, 설날 당일인 GS 2/17은 아이·선물까지 가장 넓게 흩어졌습니다.")


def dyson_subset(tp, data):
    """다이슨 3방송 상단(요약·실적·총평)에서 고른 방송만 남기고 효율 지수를 그 안의 최저=100으로 다시 계산."""
    import re
    cols = {b["color"]: b for b in data}
    base = min(b["ppm"] for b in data)
    best = max(b["ppm"] for b in data)
    spec = next((v for v in SPECS.values() if v.get("family") == "dyson" and [b["key"] for b in v["bcs"]] == [b["key"] for b in data]), None)
    if spec and spec.get("summary"):
        tp = re.sub(r'<div class="sumcall">.*?</div>', '<div class="sumcall">' + spec["summary"] + '</div>', tp, count=1, flags=re.S)
    # 범례
    tp = re.sub(r"<span><i class='pi-dot' style='background:(#[0-9a-fA-F]+)'></i>[^<]*</span>",
                lambda m: m.group(0) if m.group(1) in cols else "", tp)
    # 실적 표 행
    def row(m):
        r = m.group(0)
        c = re.search(r"background:(#[0-9a-fA-F]+)", r)
        if not c or c.group(1) not in cols:
            return ""
        b = cols[c.group(1)]
        r = r.replace(' class="pi-best"', "").replace("<tr>", "<tr class=\"pi-best\">" if b["ppm"] == best else "<tr>", 1)
        return re.sub(r"<td><b>\d+</b></td></tr>$", f"<td><b>{round(100 * b['ppm'] / base)}</b></td></tr>", r)
    tb, te = tp.index("<tbody>"), tp.index("</tbody>")
    tp = tp[:tb] + re.sub(r"<tr[^>]*>.*?</tr>", row, tp[tb:te], flags=re.S) + tp[te:]
    # 막대 3묶음
    tp = re.sub(r"<div class='pi-row'><span style='color:(#[0-9a-fA-F]+)'>.*?</span></div>",
                lambda m: m.group(0) if m.group(1) in cols else "", tp, flags=re.S)
    # 총평 카드
    def card(m):
        if m.group(2) not in cols:
            return ""
        b = cols[m.group(2)]
        idx = round(100 * b["ppm"] / base)
        g = f"<span class=\"grade {'good' if b['ppm'] == best else 'mid'}\">지수 {idx}{' · 최고' if b['ppm'] == best and len(data) > 1 and base != best else ''}</span>"
        return re.sub(r'<span class="grade [^"]*">[^<]*</span>', g, m.group(0), count=1)
    tp = re.sub(r'(<div class="rev" style="--c:(#[0-9a-fA-F]+)">.*?</p>\s*</div>)', card, tp, flags=re.S)
    base_lb = next(b["label"] for b in data if b["ppm"] == base)
    tp = re.sub(r"효율 지수는 [^<]*?을 100으로 둔 상대값", f"효율 지수는 {base_lb}을 100으로 둔 상대값", tp)
    return tp


def dyson_top(data=None):
    import re
    tp = open(os.path.join(TOOLS, "top_dyson.html"), encoding="utf-8").read()
    tp = tp[:tp.index("<h2>잘된 방송 vs 잘 안된 방송")]
    tp = tp.replace("<th>사은품</th><th class=\"pi-g\">편성 추정 매출</th>", "<th>사은품</th><th>날씨(서울)</th><th class=\"pi-g\">편성 추정 매출</th>")
    days = iter(["2026-01-07", "2026-02-17", "2026-06-21"])
    def add(m):  # 각 행의 6번째 칸(사은품) 뒤에 날씨
        cells = m.group(0).split("</td>")
        cells[5] = cells[5] + "</td>" + wx_td(next(days))[:-5]
        return "</td>".join(cells)
    tb = tp.index("<tbody>")
    te = tp.index("</tbody>")
    body = re.sub(r"<tr[^>]*>.*?</tr>", add, tp[tb:te], flags=re.S)
    tp = tp[:tb] + body + tp[te:]
    if data and len(data) < 3:
        tp = dyson_subset(tp, data)
    if data:
        bycol = {b["color"]: b for b in data}
        tp = re.sub(r'(<div class="rev" style="--c:(#[0-9a-fA-F]+)">.*?</p>)',
                    lambda m: m.group(1) + (needs_line(bycol[m.group(2)]) if m.group(2) in bycol else ""), tp, flags=re.S)
        tp = tp.replace("<div class=\"meta\">평일 밤 · <b>패키지·효도형</b>", "<div class=\"meta\">설날 밤 · <b>패키지·효도형</b>")
        if len(data) >= 3:
            tp = tp.replace("으로 채웠습니다.</div>", "으로 채웠습니다. " + DYSON_NEEDS_SUM + "</div>", 1)
    return tp


# ---------------------------------------------------------------- 조립
def build(name):
    if os.environ.get("HSB_MIN_SEC"):  # 구간 합치기 기준(초) 미리보기용
        B3.MIN_SEC = int(os.environ["HSB_MIN_SEC"])
    spec = SPECS[name]
    dyson = spec.get("family") == "dyson"
    codes = DY_CODES if dyson else HB_CODES
    use_codes(codes)
    data, fixes_total = [], {}
    if dyson:
        B3.HERE = DY
        for b0 in spec["bcs"]:
            us, n_fix = B3.load_units(b0["key"])
            b = dict(b0, units=us)
            fixes_total[b["label"]] = (n_fix, sum(1 for u in us if u["vcr"]), len(us))
            data.append(b)
        first_price = dict(B3.FIRST_PRICE)
    else:
        sogu, needs = hb_taxonomy(spec["tax"])
        PV.SOGU, PV.NEEDS = sogu, needs
        PV.SOGU_COLORS = {s: TOPIC_PALETTE[i % len(TOPIC_PALETTE)] for i, s in enumerate(sogu)}
        PV.load_splits = lambda key: {}
        tags = {}
        first_price = {}
        for b0 in spec["bcs"]:
            us, n_fix, meta = hb_load(b0["key"])
            b = dict(b0, units=us, start=meta["start"])
            fixes_total[b["label"]] = (n_fix, 0, len(us))
            tags[b["key"]] = hb_tags(b["key"], us)
            fpu = next((u for u in us if u["code"] == "PB"), None)
            if fpu:
                first_price[b["key"]] = mmss(fpu["t"])
            data.append(b)
        PV.load_tags = lambda key: tags[key]
    for b in data:
        b["end"] = b["units"][-1]["t"] + 5
        b["blocks"] = segment_keep_opening(b["units"], b["end"])
    total = max(b["end"] for b in data)
    PV.attach(data, mmss, B3.weight)

    # 흐름 막대(기존 다이슨 화면과 같은 코드)
    rows, payload = [], {}
    for b in data:
        segs = []
        for j, bl in enumerate(b["blocks"]):
            col = GROUP_COLORS.get(bl["group"], "#c7c6c3")
            bid = f"{b['key']}:{j}"
            payload[bid] = {**bl, "bc": b["label"], "range": f"{mmss(bl['s0'])}~{mmss(bl['s1'])}"}
            segs.append(
                f"<div class='seg' data-id='{bid}' title='{e(mmss(bl['s0']))}~{e(mmss(bl['s1']))} {e(bl['name'])}"
                f"{' · 녹화 요약(VCR) ' + str(round(bl['vcr'] * 100)) + '%' if bl['vcr'] >= 0.2 else ''} — 눌러서 상세'"
                f" style='left:{100 * bl['s0'] / total:.3f}%;width:{100 * (bl['s1'] - bl['s0']) / total:.3f}%;"
                f"background-color:{col};color:#fff'>{e(bl['name'])}</div>")
        marks = "".join(
            f"<i class='mk' title='{e(mmss(u['t']))} 조건 추가: {e(u['text'][:60])}' style='left:{100 * u['t'] / total:.3f}%'></i>"
            for u in b["units"] if u["code"] == "C2")
        vruns, cur = [], None
        for k, u in enumerate(b["units"]):
            nxt = b["units"][k + 1]["t"] if k + 1 < len(b["units"]) else b["end"]
            if u["vcr"]:
                if cur and u["t"] - cur[1] <= 8:
                    cur[1] = nxt
                else:
                    cur = [u["t"], nxt]
                    vruns.append(cur)
        vcr_html = "".join(f"<div class='vcrov' title='녹화 요약(VCR) {mmss(a)}~{mmss(z)}' style='left:{100 * a / total:.3f}%;width:{100 * (z - a) / total:.3f}%'></div>" for a, z in vruns)
        fp = first_price.get(b["key"])
        fpl = f"<div class='fp' style='left:{100 * B3.sec(fp) / total:.3f}%' title='첫 가격 언급 {fp}'></div>" if fp else ""
        rows.append(f"<div class='row'><div class='nm' style='color:{b['color']}'>{e(b['label'])}<div class='sub'>{len(b['blocks'])}개 구간</div></div>"
                    f"<div><div class='bar'>{''.join(segs)}{vcr_html}{fpl}</div>{fine_strip(b, total, codes)}{PV.strip_html(b, total, b['end'])}<div class='marks'>{marks}</div></div></div>")
    ticks = "".join(f"<span style='left:{100 * m * 60 / total:.2f}%'>{m}분</span>" for m in range(0, int(total // 60) + 1, 10))
    legend_main = "".join(f"<span style='font-weight:650'><i style='background:{GROUP_COLORS[g]};width:14px;height:14px'></i>{g}</span>" for g in GROUPS)
    legend = "".join(
        f"<div class='lg'><b style='color:{GROUP_COLORS.get(g, '#787774')}'>{g}</b>"
        + "".join(f"<span title='{e(codes[k][3])}'><i style='background:{codes[k][2]}'></i>{e(codes[k][0])}</span>" for k in codes if codes[k][1] == g and k != "X2") + "</div>"
        for g in GROUPS + ["기타"])
    n_codes = sum(1 for k in codes if codes[k][1] != "기타")
    n_bc = {2: "두", 3: "세"}.get(len(data), str(len(data)))
    review = " · ".join(f"{k} 수정 {v[0]}문장" + (f" / VCR {v[1]}문장" if v[1] else "") + f" (전체 {v[2]})" for k, v in fixes_total.items())
    has_marks = any(u["code"] == "C2" for b in data for u in b["units"])

    emph = B3.emphasis_section(data).replace("<h2>방송별 강조 포인트 — 모든 문장을 세분류로</h2>", "")
    # 2026-11-16 사용자 결정: 기준 버튼 순서 = 비율·문장 수 → 비율·글자 수 → 멘트 수(글자 수), 처음엔 비율·문장 수
    emph = emph.replace(
        '<button class="on" data-m="a">말한 양(글자 수)</button> <button data-m="s">비율 · 문장 수</button> <button data-m="c">비율 · 글자 수</button>',
        '<button class="on" data-m="s">비율 · 문장 수</button> <button data-m="c">비율 · 글자 수</button> <button data-m="a">멘트 수(글자 수)</button>')
    emph = emph.replace("<b>말한 양</b> = 실제로 말한 글자 수", "<b>멘트 수</b> = 실제로 말한 글자 수")
    emph += "<script>(function(){var b=document.querySelector('.etog button[data-m=s]');if(b){b.classList.remove('on');b.click();}})();</script>"
    emph = recolor_sub(emph, data, codes)
    emph = emph.replace("15개 세분류", f"{n_codes}개 세분류").replace("소분류(15개)", f"소분류({n_codes}개)").replace("세 방송 중", f"{n_bc} 방송 중")
    hi = max(data, key=lambda b: b["ppm"])
    lo = min(data, key=lambda b: b["ppm"])
    mfile = os.path.join(DY if dyson else HB, f"{spec.get('moments', name)}_moments.tsv")
    needs = needs_only(PV.section(data))
    a = needs.index("<div class='ncs'>") if "<div class='ncs'>" in needs else needs.index('<div class="ncs">')
    z = needs.index('<div id="psent">')
    needs = needs[:a] + needs_cards(data) + needs[z:]
    needs = needs.replace("% = 그 방송 상품 멘트 중 해당 고민을 건드린 비중 · 막대 길이는 말한 양",
                          "분 = 그 고민을 건드린 문장을 말한 시간(글자 수로 환산) · 막대도 분 기준이라 방송끼리 바로 비교됩니다 · 괄호 % = 그 방송 상품 멘트 중 비중 · 줄을 누르면 실제 문장")

    page = open(os.path.join(DY, "preview_2an_v2.html"), encoding="utf-8").read()
    head, _, rest = page.partition('<div class="wrap">')
    title = f"{spec['title']} — 방송 흐름 비교 (2안)"
    style_extra = ("<style>\n.marks{position:relative;height:9px;margin-top:2px}.mk{position:absolute;top:0;width:0;height:0;border-left:4px solid transparent;border-right:4px solid transparent;border-bottom:7px solid #d9730d;transform:translateX(-4px);cursor:help}\n"
                   ".vcrov{position:absolute;top:0;bottom:0;pointer-events:none;z-index:4;border-top:2px dashed #37352f;border-bottom:2px dashed #37352f;background-image:repeating-linear-gradient(135deg,rgba(255,255,255,.55) 0 3px,transparent 3px 8px)}\n"
                   ".nm .sub{font-weight:400}.chip.vcr{outline:1px dashed #787774;outline-offset:1px}.why{color:#d9730d;font-size:11.5px;margin-left:6px}\n"
                   + PV.STRIP_CSS + EXTRA_CSS + "</style></head>")
    head = head.replace("</head>", style_extra).replace("2안 미리보기 v2 — 방송 흐름 + 상세 분류", title)
    script = rest[rest.index("<script>"):]
    script = script.replace(script[script.index("const P = "):script.index(";\n", script.index("const P = ")) + 2],
                            "const P = " + json.dumps(payload, ensure_ascii=False) + ";\n")
    nl = chr(10)
    ci = script.index("const C = ")
    script = script[:ci] + "const C = " + json.dumps({k: list(v) for k, v in codes.items()}, ensure_ascii=False) + ";" + nl + script[script.index(nl, ci) + 1:]
    gi = script.index("const G = ")
    script = script[:gi] + "const G = " + json.dumps(GROUPS, ensure_ascii=False) + ", GC = " + json.dumps(GROUP_COLORS, ensure_ascii=False) + ";" + nl + script[script.index(nl, gi) + 1:]
    li = script.index("const light = ")
    lights = [k for k, v in codes.items() if v[2].lower() in ("#6fa8dc", "#7cb69d", "#9cc3ea", "#f2a65a", "#b98fd1", "#d9d8d5", "#a8a7a3", "#ecebe8")]
    script = script[:li] + "const light = k => " + json.dumps(lights) + ".includes(k);" + nl + script[script.index(nl, li) + 1:]
    script = script.replace(
        "const lines = d.lines.filter(l => !filt || l[1] === filt).map(([t,k,x]) =>\n    `<div class=\"ql\"><span class=\"chip\" style=\"background:${C[k][2]};color:${light(k)?'#37352f':'#fff'}\">${C[k][0]}</span><span class=\"t\">${t}</span>${esc(x)}</div>`).join('');",
        "const lines = d.lines.filter(l => !filt || l[1] === filt).map(([t,k,x,v,w]) =>\n    `<div class=\"ql\"><span class=\"chip${v?' vcr':''}\" style=\"background:${C[k][2]};color:${light(k)?'#37352f':'#fff'}\">${C[k][0]}${v?' · VCR':''}</span><span class=\"t\">${t}</span>${esc(x)}${w?`<span class=\"why\">검수 수정: ${esc(w)}</span>`:''}</div>`).join('');")
    script = script.replace("이전 이름: ${esc(d.old)} · 요약: ${esc(d.summary)} · ", "녹화 요약(VCR) ${Math.round(d.vcr*100)}% · ")
    toggle_js = """<script>(function(){const t=document.getElementById('fstog');if(t)t.onchange=()=>document.querySelectorAll('.fstrip').forEach(x=>x.style.display=t.checked?'':'none');})();</script><script>document.querySelectorAll('.vtog button').forEach(b=>b.onclick=()=>{
document.querySelectorAll('.vtog button').forEach(x=>x.classList.toggle('on',x===b));
document.getElementById('mA').style.display=b.dataset.v==='A'?'':'none';document.getElementById('mB').style.display=b.dataset.v==='B'?'':'none';});</script>"""

    top = dyson_top(data) if dyson else hb_top(spec, data)
    help_marks = " · <b style=\"color:#d9730d\">▲</b> 조건 추가 멘트 위치(짧아서 구간에 묻혀도 보이게) · 빗금 = 녹화 요약(VCR) 구간" if has_marks else ""
    body = f"""<div class="wrap">
<h1>{e(title)}</h1>
<p class="sub"><span class="badge" style="background:#e7f3f8;color:#1f5f7f">2안 · 자막 정독 + 문장 분류</span>생성 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 자막을 문장으로 잇고 {n_codes}개 기준으로 분류·검수 · 분류가 바뀌는 곳에서 구간을 자르고 {B3.MIN_SEC // 60}분 미만은 가장 비슷한 이웃과 합침(단, 방송 첫 구간은 {OPEN_KEEP_SEC}초 이상이면 그대로 둠)</p>
{top}
<h2>방송 흐름 한눈에</h2>
<p class="sub">검수 결과 — {e(review)}</p>
<p class="sub">구간을 누르면 아래에 {n_codes}개·4묶음 상세 분류와 실제 멘트{help_marks} · 빨간 선(₩) 첫 가격 언급</p>
{''.join(rows)}
<div class="axis">{ticks}</div>
<div class="legend"><div class="lg" style="gap:6px 18px">{legend_main}<span class="sub">← 막대 색 = 대분류</span></div></div>
<div class="plg"><label><input type="checkbox" id="fstog" checked> 정밀 띠 보기</label><span class="sub">큰 막대 바로 아래 띠 = 문장 하나하나의 대분류(2분 단위로 묶지 않은 실제 위치) · 마우스를 올리면 문장</span></div>
{PV.strip_legend()}
<details style="margin:-4px 0 10px"><summary class="sub" style="cursor:pointer">세부 분류({n_codes}개) 보기 — 구간을 누르면 이 기준으로 나뉜 비중이 나옵니다</summary><div class="legend">{legend}</div></details>
<div id="detail"><span class="sub">위 막대에서 구간을 눌러 보세요</span></div>
{butterfly(hi, lo, codes)}
{examples(data, codes, *bf_order(hi, lo, codes))}
<h2>멘트 비중</h2>
<div class="vtog">보기 <button class="on" data-v="A">대분류 막대</button> <button data-v="B">세분류 비중</button></div>
<div id="mA">{emph}</div>
<div id="mB" style="display:none">{share_view(data, codes)}</div>
{criteria(codes)}
{needs}
<p class="ev" style="margin-top:28px">분류는 Claude가 문장마다 앞뒤 문맥을 읽고 붙인 뒤 같은 기준으로 다시 검수했습니다(해석 포함, 일부 오분류 가능). 매출은 라방바 추정치이며, 이 비교는 ‘어떻게 팔았는지’를 보여줄 뿐 화법이 실적의 원인임을 증명하지 않습니다.</p>
</div>
"""
    return head + body + script + toggle_js


if __name__ == "__main__":
    name = sys.argv[1]
    out = build(name)
    os.makedirs(os.path.join(ROOT, "out", "reports"), exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rp = os.path.join(ROOT, "out", "reports", f"{stamp}_{name}_2안.html")
    open(rp, "w", encoding="utf-8").write(out)
    print("report", rp)
    if "--demo" in sys.argv:
        folder, fn = SPECS[name]["demo"]
        dest = os.path.join(ROOT, "demo_library", folder, fn)
        if os.path.exists(dest) and SPECS[name].get("family") == "dyson":
            bk = os.path.join(ROOT, "demo_library", folder, f"백업_{stamp}_{fn}")
            shutil.copy2(dest, bk)
            print("backup", bk)
        open(dest, "w", encoding="utf-8").write(out)
        print("demo", dest)
