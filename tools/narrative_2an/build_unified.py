"""2안 공통 양식 (2026-11-16 사용자 결정): 다이슨·건강식품·뷰티 리포트를 같은 틀로 만든다.

순서: 요약 → 실적 비교 → 방송별 총평 → 방송 흐름 한눈에(+소구 띠) → 방송 시간을 어디에 썼나 → 같은 시각, 다른 말
      → (멘트 비중은 '방송 시간을 어디에 썼나'에 합침) → 소구별 대표 문장 → 분류 기준 → 방송별 NEEDS 순위

세분류 코드는 카테고리마다 다르다(가전 15개, 건강·뷰티 9개). 대분류(상품·조건·신뢰·푸시)와 색은 공통.
사용: python build_unified.py dyson|mbp|drl|sephd|sepcj|sep [--demo]
"""
import csv
import html
import json
import re
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
def ppm_txt(b, prefix=True):
    """분당주문액 표기. 사내 데이터에 매출이 비어 있는 방송은 '실적 데이터 없음'."""
    if b.get("ppm"):
        return f"분당 {b['ppm']}만" if prefix else f"{b['ppm']}만"
    return "실적 데이터 없음" if prefix else "–"


def hb_bc(key, ch, md, ppm, rev, wmin, price, final, inst, gift, kind, review, color=None):
    return {"key": key, "label": f"{ch} {md}", "color": color or CH[ch], "ch": ch, "ppm": ppm, "rev": rev, "wmin": wmin,
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
        "summary": "같은 뼈엔 엠비피(459,000원 · 무이자 12개월) 두 방송 중 <b>GS샵 10/27이 분당주문액 210만 원으로 롯데홈쇼핑 10/21(78만 원)의 약 2.7배</b>를 팔았습니다. 문장 단위로 비교하면 차이는 <b>‘왜 먹어야 하는가’를 얼마나 쌓았느냐</b>에서 났습니다 — GS는 첫 10분 판매 멘트의 94%를 낙상·폐경기 골밀도 감소(문제 제기)와 인체적용시험(근거)에 썼고, 롯데는 첫마디부터 ‘생방송에서만 14박스’로 <b>푸시</b>(판매 멘트의 23%, GS는 9%)를 앞세웠습니다. <b>고객 고민(NEEDS)</b>으로 보면 GS는 고민 이야기에 19.6분(롯데 13.0분)을 썼고, ‘나이 듦·폐경기 여성’처럼 <b>누구에게 왜</b> 위험한지를 롯데의 약 2배로 말했습니다. 롯데는 ‘가을 나들이·계절’이 GS보다 길었습니다.",
        "note": "시간대가 다릅니다(GS 아침 7시 · 롯데 낮 1시 반).",
    },
    "mbp0914": {  # 2026-11-19 사용자 요청: 하루 차이·비슷한 낮 시간대 짝(GS 9/14 11:35 · 롯데 9/15 13:35)
        "title": "뼈엔 엠비피", "tax": "mbp", "demo": ("뼈앤엠비피", "2안_0914_0915.html"), "q": "뼈엔 엠비피",
        "bcs": [
            hb_bc("mbp_gs0914", "GS샵", "9/14", 623, 227_894_000, 36.6, 459000, "436,056원", "12개월", "오메가3 2박스 · 추석 적립금 10%", "근거+인기형",
                  "골절·골다공증 문답으로 열고, 판매 멘트의 31%를 인체적용시험·원료(우유 유래 MBP·식약처 인정)에 썼습니다. 가격은 4분 48초에 꺼냈고, 푸시는 ‘2천 박스·3천 박스 돌파’, ‘매진’, ‘1등’처럼 <b>남들이 이미 사고 있다</b>는 숫자로 채웠습니다."),
            hb_bc("mbp_lt0915", "롯데홈쇼핑", "9/15", 98, 33_288_000, 33.9, 459000, "436,100원", "12개월", "오메가3 2박스", "추석 마감형",
                  "첫 23초 만에 ‘국민카드 청구할인 · 한 달 3만 원대’, 1분 안에 ‘14박스 최다 구성’을 꺼냈습니다. 판매 멘트의 34%가 푸시였고 그 대부분이 <b>‘추석 전 마지막 생방송’</b> 반복이었으며, 마지막 10분은 74%가 푸시였습니다."),
        ],
        "summary": "하루 차이, 둘 다 낮 시간대에 같은 뼈엔 엠비피(459,000원 · 무이자 12개월 · 오메가3 2박스)를 판 두 방송 중 <b>GS샵 9/14가 분당주문액 623만 원으로 롯데홈쇼핑 9/15(98만 원)의 약 6.4배</b>를 팔았습니다. 조건은 거의 같았고(카드 할인 후 GS 436,056원 · 롯데 436,100원) 차이는 <b>무엇으로 밀었느냐</b>에서 났습니다 — GS는 판매 멘트의 31%를 <b>근거</b>(인체적용시험·우유 유래 MBP·식약처 인정)에 썼고 푸시(21%)는 ‘2천·3천 박스 돌파, 매진, 1등’ 같은 <b>인기 숫자</b>였습니다. 롯데는 첫 23초에 카드 할인부터 꺼냈고 판매 멘트의 34%를 <b>‘추석 전 마지막 생방송’ 마감 푸시</b>에 썼습니다(마지막 10분은 74%). <b>고객 고민(NEEDS)</b>으로 보면 GS는 ‘낙상·골절 불안’(5.3분)과 ‘폐경기·중년 여성’(3.4분)으로 <b>누가 왜 위험한지</b>를 먼저 말했고, 롯데는 ‘소리 없는 뼈 손실’(3.1분)이 1위였고 골절 불안은 2.3분이었습니다.",
        "note": "하루 차이 · 둘 다 낮 시간대(GS 월 11:35 · 롯데 화 13:35), 추석 전 방송입니다.",
    },
    "drl": {
        "title": "닥터린 하이퍼셀 대마종자유", "tax": "drl", "demo": ("닥터린", "2안.html"), "q": "닥터린 대마종자유",
        "bcs": [
            hb_bc("drl_gs", "GS샵", "10/28", 263, 315_787_000, 119.9, 298000, "263,100원", "언급 없음", "상품권 추첨", "근거+1등형",
                  "‘GS 1등 대마종자유’로 신뢰를 먼저 세우고, 치킨·곱창 → 포화지방 → 오메가 1:3 비율·비커 시연으로 이어갔습니다. ‘하루 490원꼴’, ‘6박스 공짜 느낌’으로 가격을 낮춰 보였고 ‘1등·매진·동시 접속’을 약 13분 간격으로 반복했습니다."),
            hb_bc("drl_lt", "롯데홈쇼핑", "8/26", 116, 138_490_000, 119.8, 298000, "258,540원", "언급 없음", "없음", "최저가형",
                  "‘역대 최저가 만원대’와 ‘본사가 철벽이라 1년간 못 내렸다’는 협상 이야기로 열었습니다. 판매 멘트의 28%가 가격 이야기였지만 GS도 같은 298,000원이라 차별점이 되지 못했고, 후반 20분은 ‘혜택 다 사라집니다’ 마감 압박이었습니다."),
        ],
        "summary": "같은 닥터린 하이퍼셀 대마종자유(18박스 · 298,000원), 같은 수요일 19:35 두 방송 중 <b>GS샵 10/28이 분당주문액 263만 원으로 롯데홈쇼핑 8/26(116만 원)의 약 2.3배</b>를 팔았습니다. 가격이 같았는데도 롯데는 판매 멘트의 28%를 <b>‘역대 최저가·만원대·본사 협상’ 가격 이야기</b>에 썼고, GS는 그 시간을 <b>근거</b>(오메가 1:3 비율·비커 시연, 30%)와 <b>‘매출·주문고객·재구매율 1등’ 푸시</b>(19%)에 썼습니다. <b>고객 고민(NEEDS)</b>으로 보면 GS는 ‘건강 경각심·오메가6 과잉·추위’(합 7.2분, 롯데 0.7분)로 <b>지금 내 몸에 필요한 이유</b>를, 롯데는 ‘영양제를 따로 먹는 번거로움’(3.5분, GS 0분)으로 <b>하나로 끝내는 편의</b>를 팔았습니다. 롯데 8/26은 31℃ 한여름이라 추위 이야기를 꺼낼 수 없었던 점은 감안해야 합니다.",
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
    "summary": "같은 세포랩 바이오제닉 에센스(289,000원), 같은 밤 21:45 두 방송 중 <b>GS샵 10/5가 분당주문액 430만 원으로 CJ온스타일 9/28(263만 원)의 약 1.6배</b>를 팔았습니다. 두 방송 모두 판매 멘트의 40% 이상을 <b>체험담</b>에 썼지만, GS는 그 위에 <b>‘3년 연속 1등·매진 폭주기관차’ 푸시</b>(18%, CJ 12%)를 얹고 첫 가격 이야기를 <b>24분 51초</b>까지 미뤘습니다. CJ는 70대 배우의 회복담 직후 4분 31초에 ‘10% 할인 · 한 달 1만 2천원대’로 넘어갔습니다. <b>고객 고민(NEEDS)</b>으로 보면 CJ는 고민 이야기의 43%를 ‘중장년 노화 체념’(9.7분) 하나에 쏟았고, GS는 같은 고민(6.1분) 외에 ‘남성·가족 피부’, ‘기초 여러 개 번거로움’(3.1분, CJ 0.1분)까지 <b>가장 넓게</b>(1위 비중 28%) 펼쳤습니다.",
    "note": "CJ 9/28은 추석 연휴 직후이고 구성에 마스크팩·솝이 섞여 있습니다.",
}
SPECS["sephdcj"] = {
    "title": "세포랩 바이오제닉 에센스", "tax": "sep", "demo": ("세포랩", "2안_현대CJ.html"), "q": "세포랩 바이오제닉", "moments": "sepcj",
    "bcs": [_SEP["sep_hd"], _SEP["sep_cj"]],
    "summary": "같은 세포랩 바이오제닉 에센스(289,000원), 같은 밤 21:45 두 방송 중 <b>현대홈쇼핑 10/27이 분당주문액 386만 원으로 CJ온스타일 9/28(263만 원)의 약 1.5배</b>를 팔았습니다. "
               "두 방송 모두 체험담이 주력이었지만, 현대는 시작 41초 만에 <b>9병 구성·카드 7%·무이자</b>를 꺼내고 ‘가짜가 난리, 여기가 정품’으로 <b>근거</b>(15%, CJ 6%)를 쌓았고, "
               "CJ는 70대 배우의 회복담 직후 4분 31초에 ‘10% 할인’으로 넘어갔습니다. "
               "<b>고객 고민(NEEDS)</b>으로 보면 현대는 ‘화장품 효과 불신’(8.3분)·‘가품 걱정’(3.5분)으로 <b>의심 풀기</b>, CJ는 ‘중장년 노화 체념’(9.7분, 고민 이야기의 43%) 하나에 집중했습니다.",
    "note": "날짜가 다릅니다(현대 10/27 · CJ 9/28 추석 연휴 직후). CJ 구성에는 마스크팩·솝이 섞여 있습니다.",
}
SPECS["sep"] = {
    "title": "세포랩 바이오제닉 에센스", "tax": "sep", "demo": ("세포랩", "2안_3사.html"), "q": "세포랩 바이오제닉", "moments": "sepcj",
    "bcs": [_SEP["sep_gs"], _SEP["sep_hd"], _SEP["sep_cj"]],
    "summary": "같은 세포랩 바이오제닉 에센스(289,000원), 같은 밤 21:45 세 방송 중 <b>GS샵 10/5가 분당주문액 430만 원으로 가장 잘 팔았고</b>, 현대 10/27 386만 원, CJ 9/28 263만 원 순이었습니다. 세 방송 모두 판매 멘트의 35~44%를 <b>체험담</b>에 써서 그것만으로는 순위가 갈리지 않았습니다 — GS만 <b>‘3년 연속 1등·매진’ 푸시를 가장 많이</b>(18%), <b>가격 이야기는 가장 적고 늦게</b>(3% · 24분 51초) 했습니다. 현대는 구성·정품, CJ는 감동 직후 할인으로 갔습니다. <b>고객 고민(NEEDS)</b>으로 보면 셋이 갈립니다 — GS는 ‘기초 여러 개 번거로움’(3.1분, 다른 두 곳 0.1분)을 건드리며 고민을 가장 넓게 펼쳤고, 현대는 ‘효과 불신·가품 걱정’(합 11.8분)으로 의심 풀기, CJ는 ‘중장년 노화 체념’(9.7분, 고민 이야기의 43%) 하나에 집중했습니다.",
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

# ---------------------------------------------------------------- 한국제일도 분석(2026-11-19): 비교가 아니라 '현대가 어떻게 팔았나' 분석
HJD_COLORS = {"hjd_0822": "#0f7b6c", "hjd_1024": "#d9730d", "hjd_1110": "#9065b0"}
HJD_BASE = {
    "hjd_0822": dict(md="8/22", ppm=359, rev=243_904_000, wmin=67.9, final="10만원대(5종)", inst="월 만원대(개월 미언급)",
                     gift="빵칼(현대 단독)·평생 연마", kind="문제 제기→장인 근거형"),
    "hjd_1024": dict(md="10/24", ppm=None, rev=None, wmin=69.8, final="13~14만원대(5종)", inst="월 14,000원대",
                     gift="빵칼(현대 단독)·평생 연마", kind="시연+희소성형"),
    "hjd_1110": dict(md="11/10", ppm=443, rev=178_044_000, wmin=40.2, final="14만원대(월 14,800원)", inst="월 만원대",
                     gift="빵칼·평생 연마·적립금 1만원 환급", kind="시연+김장철 푸시형"),
}
HJD_REVIEW = {
    "hjd_0822": "가격 없이 ‘배송비만 내면 새 칼처럼’ 연마 서비스를 먼저 던지고, 속옷·신발·가방은 바꾸면서 칼은 안 바꾼다는 이야기로 문제를 깔았습니다. 장인의 수작업 설명을 8분 넘게 한 뒤에야 가격(5종 10만원대)을 꺼냈고, ‘8월 중 마지막 방송·추석 전엔 어렵다’는 희소성과 수량·카운트다운으로 마무리했습니다.",
    "hjd_1024": "‘안목자산·1등 칼·내 인생 마지막 칼’ 화두로 열고 무제한 연마를 약속한 뒤, 일반 칼 대 한국제일도 시연(무·토마토·파인애플)을 세 번 반복했습니다. 가격은 10분 11초에야 나왔고(식도 13만 9천원 → 5종 14만원대), 후반에는 ‘10월 중 단 한 번의 생방송’과 19분·7분·30초 카운트다운이 이어졌습니다. 사내 데이터에 매출이 비어 있는 회차입니다.",
    "hjd_1110": "‘딱 한 번인 55분 타임 찬스·김장철’ 희소성으로 열고 ‘현대홈쇼핑 1등 칼’, 장인 45년 이력으로 이어갔습니다. 연마 서비스를 가격보다 먼저 소개했고, 김장배추·파채·토마토·명란 시연을 번갈아 보여줬습니다. 월 만원대를 적립금 1만원으로 돌려준다는 혜택과 29분→2분 카운트다운이 마지막 구간을 채웠습니다.",
}
_PRICE = re.compile(r"\d+\s*만\s*\d*\s*천?\s*원|\d{2,3},\d{3}\s*원|\d+\s*만\s*원대|\d+\s*원대")


def hjd_first_price(b):
    for u in b["units"]:
        if u["code"] in ("PB", "CO") and _PRICE.search(u["text"]):
            return u["t"]
    return None


def hjd_stats(b):
    us = b["units"]
    c = Counter()
    for u in us:
        if u["code"] != "XX":
            c[u["code"]] += len(u["text"])
    t = sum(c.values()) or 1
    pc = lambda *ks: 100 * sum(c[k] for k in ks) / t
    st = b["pstat"]
    tot = sum(B3.weight(u) for u in us) or 1
    dur = b["end"] / 60
    so = sorted(((dur * st["S"][x] / tot, x) for x in PV.SOGU if st["S"][x] > 0), reverse=True)
    nd = sorted(((dur * st["N"][x] / tot, x) for x in PV.NEEDS if st["N"][x] > 0), reverse=True)
    last10 = Counter()
    for u in us:
        if u["t"] >= b["end"] - 600 and u["code"] != "XX":
            last10[CODES_NOW[u["code"]][1]] += len(u["text"])
    lt = sum(last10.values()) or 1
    return {"dur": dur, "persuade": pc("PR", "FX", "PD", "EV", "EX"), "push": pc("PU", "CT"), "pr": pc("PR"), "fx": pc("FX"),
            "ev": pc("EV"), "price_t": hjd_first_price(b), "so": so, "nd": nd, "last10_push": 100 * last10["푸시"] / lt}


def _mmss(t):
    return f"{int(t // 60)}분 {int(t % 60):02d}초" if t is not None else "–"


def hjd_summary(data):
    S = {b["key"]: hjd_stats(b) for b in data}
    names = " · ".join(b["label"].replace("현대홈쇼핑 ", "") for b in data)
    ps = [S[b["key"]]["persuade"] for b in data]
    pt = [S[b["key"]]["price_t"] for b in data]
    head = (f"현대홈쇼핑이 <b>[한국제일도] 더 프리미엄 5종 풀세트</b>(식도·과도·중식도·분리형 가위·빵칼, 평생 무제한 연마 서비스)를 "
            f"{'세 번' if len(data) == 3 else '두 번' if len(data) == 2 else '한 번'} 방송한 회차({names})를 문장 단위로 읽었습니다. ")
    if len(data) == 1:
        s0 = S[data[0]["key"]]
        body = (f"판매 멘트의 <b>{s0['persuade']:.0f}%</b>를 ‘왜 사야 하나’(문제 제기·시연·근거·체험)에 쓰고, 가격은 <b>{_mmss(s0['price_t'])}</b>에야 처음 꺼냈습니다. "
                f"마지막 10분은 푸시가 {s0['last10_push']:.0f}%로 방송 전체 평균({s0['push']:.0f}%)보다 컸습니다.")
    else:
        body = (f"모든 회차에서 판매 멘트의 <b>{min(ps):.0f}~{max(ps):.0f}%</b>를 ‘왜 사야 하나’에 쓰고, 가격은 방송 <b>{min(t for t in pt if t) / 60:.0f}~{max(t for t in pt if t) / 60:.0f}분</b>째에야 처음 꺼냈습니다. "
                f"마지막 10분의 푸시 비중은 {' · '.join(f'{S[b['key']]['last10_push']:.0f}%' for b in data)}로, 방송 전체 평균({min(S[b['key']]['push'] for b in data):.0f}~{max(S[b['key']]['push'] for b in data):.0f}%)의 두 배 안팎이었습니다 — 끝으로 갈수록 ‘지금 사라’가 커지는 구조입니다.")
        if len(data) >= 2:
            f0, f1 = S[data[0]["key"]], S[data[-1]["key"]]
            body += (f" 회차가 갈수록 문제 제기는 {f0['pr']:.0f}% → {f1['pr']:.0f}%로 줄고 시연(기능·효과)은 {f0['fx']:.0f}% → {f1['fx']:.0f}%로 늘었습니다.")
    rated = [b for b in data if b["ppm"]]
    if rated:
        body += " 분당주문액은 " + " · ".join(f"{b['label'].replace('현대홈쇼핑 ', '')} {b['ppm']}만" for b in rated) + "입니다"
        body += ("(10/24는 사내 데이터에 매출이 비어 있습니다)." if any(not b["ppm"] for b in data) else ".")
    else:
        body += " 이 회차는 사내 데이터에 매출이 비어 있어 실적은 알 수 없습니다."
    agg = Counter()
    for b in data:
        for m_, n_ in S[b["key"]]["nd"]:
            agg[n_] += m_
    nd = [(m_, n_) for n_, m_ in agg.most_common(2)]
    if nd:
        body += (" <b>고객 고민(NEEDS)</b>은 " + " · ".join(f"‘{n}’ {m:.1f}분" for m, n in nd)
                 + ("(고른 회차 합계)" if len(data) > 1 else "") + "을 가장 길게 건드렸습니다.")
    return head + body


def hjd_takeaways(data):
    """GS가 방송할 때 참고할 점 — 현대 3개 회차에서 읽은 것(해석)."""
    items = [
        ("가격 없이 연다", "세 회차 모두 가격이 아니라 <b>연마 서비스·희소성·고민(칼이 안 썰림)</b>으로 열고, 가격은 8~10분 뒤에 처음 꺼냅니다. 장인·소재 근거를 먼저 쌓고 가격을 보여줍니다."),
        ("낱개 정가를 쌓았다가 5종으로 묶는다", "식도 13.9만 · 중식도 10.9만 · 가위 3.9만을 차례로 보여 준 뒤 <b>‘5종이 14만원대, 월 만원대’</b>로 묶습니다. ‘10만원 넘는 칼이 두 개’가 반복 문구입니다."),
        ("‘평생 무제한 연마’가 핵심 약속", "‘배송비만 부담하면 새 칼처럼’을 도입·중반·마무리에 반복합니다. 칼을 소모품이 아니라 <b>평생 쓰는 자산</b>으로 바꾸는 장치입니다."),
        ("시연이 설득의 중심", "일반 칼 대 한국제일도로 무·토마토·파인애플·김장배추·명란을 자르는 <b>라이브 시연</b>이 반복됩니다. 회차가 갈수록 문제 제기보다 시연 비중이 커졌습니다."),
        ("끝으로 갈수록 푸시", "‘현대 1등’, ‘이번 달 단 한 번·마지막 방송’, 수량 부족·상담원 연결 불가, <b>29분→2분 카운트다운</b>이 마지막 10분을 채웁니다."),
        ("시기 훅을 바꾼다", "8/22는 ‘8월 마지막·추석 전’, 11/10은 <b>김장철</b>을 훅으로 썼습니다. GS 편성 시기에 맞는 훅이 필요합니다."),
        ("그대로 못 쓰는 것", "‘현대 단독 빵칼’, ‘현대홈쇼핑 1등 칼’, 적립금 1만원은 <b>채널 고유 소구</b>입니다. GS 단독 구성·혜택과 사실 확인된 1등 표현으로 바꿔야 합니다."),
    ]
    lis = "".join(f"<li><b>{e(t)}</b> — {d}</li>" for t, d in items)
    return ("<div class='tkw'><b>GS가 방송한다면 참고할 점</b> <span class='sub'>(현대 3회 방송에서 읽은 것 · 해석이 포함됨)</span>"
            f"<ol>{lis}</ol><div class='sub'>3개 회차·같은 채널의 방송이라 일반 법칙이 아니라 이 상품에서 현대가 쓴 방식입니다. 8/22는 비(30mm), 11/10은 맑음이라는 날씨 차이가 있고 10/24는 매출이 없어 실적 비교는 두 회차뿐입니다.</div></div>")


def _hjd_bc(key):
    b = HJD_BASE[key]
    return hb_bc(key, "현대홈쇼핑", b["md"], b["ppm"], b["rev"], b["wmin"], 148000, b["final"], b["inst"], b["gift"], b["kind"], HJD_REVIEW[key],
                 color=HJD_COLORS[key])


_HJD_COMBOS = {  # 이름 → (회차 키들, 보관함 파일명)
    "hjd": (["hjd_0822", "hjd_1024", "hjd_1110"], "분석.html"),
    "hjd_a": (["hjd_0822"], "분석_0822.html"), "hjd_b": (["hjd_1024"], "분석_1024.html"), "hjd_c": (["hjd_1110"], "분석_1110.html"),
    "hjd_ab": (["hjd_0822", "hjd_1024"], "분석_0822_1024.html"), "hjd_ac": (["hjd_0822", "hjd_1110"], "분석_0822_1110.html"),
    "hjd_bc": (["hjd_1024", "hjd_1110"], "분석_1024_1110.html"),
}
for _name, (_keys, _fn) in _HJD_COMBOS.items():
    SPECS[_name] = {"title": "한국제일도 더 프리미엄 5종 풀세트", "tax": "hjd", "demo": ("한국제일도", _fn), "q": "한국제일도",
                    "bcs": [_hjd_bc(k) for k in _keys], "summary": hjd_summary, "takeaways": hjd_takeaways,
                    "note": "현대홈쇼핑의 같은 상품 방송을 회차별로 분석한 리포트입니다.",
                    "ev": ("근거·제조", "장인·제조 공정·소재·설계(톱니)·특허·인증·백화점 입점·브랜드 역사 — 믿을 이유")}

SPECS["dyson"] = {
    "title": "다이슨 디지털 슬림", "family": "dyson", "demo": ("다이슨", "리포트.html"), "moments": "dyson",
    "bcs": [{"key": k, "label": lb, "color": c, "ppm": p} for k, lb, c, p in
            (("gs0107", "GS샵 1/7", "#2383e2", 570), ("gs0217", "GS샵 2/17", "#d9730d", 579), ("hd0621", "현대홈쇼핑 6/21", "#0f7b6c", 714))],
}


# ---------------------------------------------------------------- 데이터 읽기
CODES_NOW = {}


def use_codes(codes):
    global CODES_NOW
    CODES_NOW = codes
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
    # 2026-11-19 사용자 지적(GS 9/14): 첫 3초 인사 멘트(푸시) 때문에 오프닝(문제 제기 1분 반)이 뒤 신뢰 구간에 묻혔다.
    # → 맨 앞의 15초 미만 짧은 묶음은 오프닝 판단에서 건너뛴다(오프닝 구간에는 포함).
    runs = []  # (그룹, 시작 문장 index)
    for i, u in enumerate(units):
        if grp(u) == "기타":
            continue
        if not runs or runs[-1][0] != grp(u):
            runs.append((grp(u), i))
    k = 0
    while k + 1 < len(runs) and units[runs[k + 1][1]]["t"] - units[runs[k][1]]["t"] < 15:
        k += 1
    g0 = runs[k][0] if runs else None
    cut = runs[k + 1][1] if k + 1 < len(runs) else len(units)
    if g0 is None or cut >= len(units) or units[cut]["t"] - units[0]["t"] < OPEN_KEEP_SEC:
        return B3.segment(units, end_t)
    head = B3.segment(units[:cut], units[cut]["t"])
    tail = B3.segment(units[cut:], end_t)
    if head and tail and head[-1]["name"] == tail[0]["name"]:  # 떼어 내도 같은 이름이 연달아 붙으면 의미가 없으니 원래대로
        return B3.segment(units, end_t)
    return head + tail


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
    strong = set(sorted(sc, key=lambda k: -abs(mh[k] - ml[k]))[:3]) if hi is not lo else set(order[:3])
    return order, strong


def time_section(data, codes):
    """2026-11-19 사용자 결정: '방송 시간을 어디에 썼나'는 막대 대신 깔끔한 표 하나로(대분류 줄 = 분·비중, 세분류 줄 = 분, 차이 큰 3개 강조)."""
    sc = sell_codes(codes)
    mins = {b["key"]: minutes(b, sc) for b in data}
    two = len(data) == 2
    keep = [k for k in sc if any(mins[b["key"]][k] >= 0.05 for b in data)]
    gap = {k: max(mins[b["key"]][k] for b in data) - min(mins[b["key"]][k] for b in data) for k in keep}
    one = len(data) == 1
    strong = set() if one else set(sorted(keep, key=lambda k: -gap[k])[:3])
    gdesc = {"상품": "왜 사야 하나", "조건": "가격·구성", "신뢰": "근거·체험", "푸시": "지금 사라"}
    short = lambda b: b["label"].replace("홈쇼핑", "").replace("온스타일", "")

    def gap_cell(vals):
        if one:
            return ""
        if two:
            d = vals[0] - vals[1]
            if abs(d) < 1:
                return "<td class='gp sub'>비슷</td>"
            w = data[0] if d > 0 else data[1]
            return f"<td class='gp'><b style='color:{w['color']}'>{e(short(w).split()[0])} +{abs(d):.0f}분</b></td>"
        top = max(vals)
        if top < 0.5 or sorted(vals)[-2] >= top - 0.5:
            return "<td class='gp sub'>비슷</td>"
        w = data[vals.index(top)]
        return f"<td class='gp'><b style='color:{w['color']}'>{e(short(w).split()[0])}</b></td>"

    gmx = max((sum(mins[b["key"]][k] for k in keep if codes[k][1] == g) for b in data for g in GROUPS), default=1) or 1
    smx = max((mins[b["key"]][k] for b in data for k in keep), default=1) or 1

    def bars(vals, mx, pcts=None, big=False, sel=""):
        out = ""
        for i, (v, b) in enumerate(zip(vals, data)):
            pc = f" <span class='sub'>{pcts[i]:.0f}%</span>" if pcts else ""
            out += (f"<div class='bw{' big' if big else ''}' data-b='{i}' data-sel='{sel}' title='눌러서 {e(b['label'])}의 실제 멘트 보기'><span class='bl' style='color:{b['color']}'>{e(short(b).split()[0])}</span>"
                    f"<span class='bt'><i style='width:{max(100 * v / mx, 0.8):.1f}%;background:{b['color']}'></i></span>"
                    f"<span class='bv'>{v:.0f}분{pc}</span></div>")
        return f"<td class='bc'>{out}</td>"

    legend = "".join(f"<span><i style='background:{b['color']}'></i>{e(b['label'])} · {ppm_txt(b)}</span>" for b in data)
    rows = ""
    order = [g for g in ("상품", "신뢰", "조건", "푸시") if g in GROUPS] + [g for g in GROUPS if g not in ("상품", "신뢰", "조건", "푸시")]
    for g in order:  # 2026-11-19 사용자 결정: 상품 → 신뢰 → 조건 → 푸시 순
        gk = [k for k in keep if codes[k][1] == g]
        if not gk:
            continue
        tot = {b["key"]: sum(mins[b["key"]][k] for k in sc) or 1 for b in data}
        gv = [sum(mins[b["key"]][k] for k in gk) for b in data]
        hint = " <span class='hint'>차이 큰 항목 있음</span>" if any(k in strong for k in gk) else ""
        rows += (f"<tr class='g' data-g='{g}' title='눌러서 세분류 펼치기/접기'><td><span class='tg'>▸</span><span class='sq' style='background:{GROUP_COLORS[g]}'></span>{g} <span class='sub'>{gdesc.get(g, '')}</span>{hint}</td>"
                 + bars(gv, gmx, [100 * v / tot[b["key"]] for v, b in zip(gv, data)], big=True, sel="g:" + g)
                 + gap_cell(gv) + "</tr>")
        for k in sorted(gk, key=lambda k: -sum(mins[b["key"]][k] for b in data)):
            vals = [mins[b["key"]][k] for b in data]
            rows += (f"<tr class='sr {'hi' if k in strong else ''}' data-g='{g}'><td class='sl'><span class='dot' style='background:{codes[k][2]}'></span>{e(codes[k][0])}</td>"
                     + bars(vals, smx, sel="c:" + k) + gap_cell(vals) + "</tr>")
    return ("<h2>방송 시간을 어디에 썼나</h2><p class='sub'>세분류별로 실제 말한 시간(분 · 글자 수 비율로 환산 · 진행·맞장구 제외). "
            "막대 색 = 방송 · 대분류 줄의 %는 그 방송 판매 멘트(진행·맞장구 제외) 중 그 대분류가 차지한 비중(글자 수 기준) · 대분류와 세분류는 각각 같은 눈금" + ("" if one else ", <span style='background:#fff4cc;padding:0 4px;border-radius:3px'>노란 줄</span>은 방송 간 차이가 가장 큰 3개입니다. GS샵은 항상 왼쪽 열입니다") + ".</p>"
            f"<div class='ttlg'>{legend}</div>"
            f"<div class='ttbar'><button type='button' class='ttall'>세분류 모두 펼치기</button><span class='sub'>대분류 줄을 누르면 세분류가 펼쳐집니다 · 막대를 누르면 그 방송의 실제 멘트가 오른쪽에 나옵니다</span></div>"
            f"<div class='pi-sc'><table class='tt'><thead><tr><th>분류</th><th>말한 시간</th>{'' if one else ('<th>차이</th>' if two else '<th>가장 많이</th>')}</tr></thead><tbody>{rows}</tbody></table></div>"
            "<script>(function(){var t=document.querySelector('table.tt');if(!t)return;"
            "function set(g,on){t.querySelectorAll('tr.sr[data-g=\"'+g+'\"]').forEach(function(r){r.classList.toggle('show',on);});"
            "var h=t.querySelector('tr.g[data-g=\"'+g+'\"]');if(h)h.classList.toggle('open',on);}"
            "t.querySelectorAll('tr.g').forEach(function(h){h.addEventListener('click',function(){set(h.dataset.g,!h.classList.contains('open'));});});"
            "var a=document.querySelector('.ttall');if(a)a.onclick=function(){var all=!a.classList.contains('on');a.classList.toggle('on',all);"
            "a.textContent=all?'세분류 모두 접기':'세분류 모두 펼치기';t.querySelectorAll('tr.g').forEach(function(h){set(h.dataset.g,all);});};"
            # 2026-11-19 사용자 요청: 막대를 누르면 그 방송·분류의 실제 멘트를 오른쪽 패널에서
            "var GRP=" + json.dumps({k: v[1] for k, v in codes.items()}, ensure_ascii=False) + ";"
            "function esc(x){return String(x).replace(/[&<>\"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c];});}"
            "t.querySelectorAll('.bw').forEach(function(w){w.addEventListener('click',function(ev){ev.stopPropagation();"
            "var md=document.getElementById('msData'),P=document.getElementById('pside'),box=document.getElementById('psent');if(!md||!P||!box)return;"
            "var D=JSON.parse(md.textContent),b=D.bcs[+w.dataset.b],sel=w.dataset.sel,kind=sel.slice(0,1),v=sel.slice(2);"
            "var L=b.lines.filter(function(l){return kind==='g'?GRP[l[1]]===v:l[1]===v;});"
            "var name=kind==='g'?v:(D.codes[v]?D.codes[v][0]:v);"
            "box.innerHTML='<b style=\"color:'+b.color+'\">'+esc(b.label)+'</b> · <b>'+esc(name)+'</b> <span class=\"sub\">'+L.length+'문장</span>'"
            "+L.map(function(l){var c=D.codes[l[1]]||['',''];return '<div class=\"ms-l\"><span class=\"ms-tm\">'+l[0]+'</span>'+(kind==='g'?'<span class=\"ms-tag\" style=\"background:'+c[1]+'\">'+esc(c[0])+'</span>':'')+esc(l[2])+'</div>';}).join('');"
            "t.querySelectorAll('.bw.on').forEach(function(x){x.classList.remove('on');});w.classList.add('on');"
            "P.classList.add('open');box.scrollTop=0;});});})();</script>")


def group_bars(data, codes):
    """2026-11-19 사용자 결정: '멘트 비중' 섹션은 '방송 시간을 어디에 썼나'와 겹쳐 삭제 → 거기에만 있던 대분류(상품·조건·신뢰·푸시) 비중을 이 섹션 맨 위로."""
    rows = ""
    for b in data:
        c = Counter()
        for u in b["units"]:
            g = codes[u["code"]][1]
            if g != "기타":
                c[g] += B3.weight(u)
        t = sum(c.values()) or 1
        segs = "".join(f"<i style='width:{100 * c[g] / t:.1f}%;background:{GROUP_COLORS[g]}' title='{g} {100 * c[g] / t:.1f}%'>{g} {100 * c[g] / t:.0f}%</i>"
                       for g in GROUPS if c[g] > 0)
        rows += f"<div class='gbr'><div class='gbl' style='color:{b['color']}'>{e(b['label'])}</div><div class='gbb'>{segs}</div></div>"
    return ("<h3 style='margin:14px 0 4px'>큰 묶음으로 보면 <span class='sub'>(판매 멘트 글자 수 비중 · 상품=왜 사야 하나 / 조건=가격·구성 / 신뢰=근거·체험 / 푸시=지금 사라)</span></h3>" + rows)


def time_table_section(data, codes):
    """방송이 셋이거나 실적이 없는 회차가 있을 때: 세분류별 말한 시간(분)을 회차별로 나란히."""
    sc = sell_codes(codes)
    mins = {b["key"]: minutes(b, sc) for b in data}
    keep = [k for k in sc if any(mins[b["key"]][k] >= 0.05 for b in data)]
    keep.sort(key=lambda k: -sum(mins[b["key"]][k] for b in data))
    mx = max(mins[b["key"]][k] for b in data for k in keep) or 1
    head = "".join(f"<th style='color:{b['color']}'>{e(b['label'])}<div class='sub'>{ppm_txt(b)}</div></th>" for b in data)
    rows = ""
    for k in keep:
        cells = "".join(
            f"<td style='background:linear-gradient(90deg,{codes[k][2]}55 {100 * mins[b['key']][k] / mx:.0f}%,transparent 0);text-align:right'><b>{mins[b['key']][k]:.1f}분</b></td>"
            for b in data)
        rows += f"<tr><th class='rl'><span class='dot' style='background:{codes[k][2]}'></span>{e(codes[k][0])}</th>{cells}</tr>"
    return ("<h2>방송 시간을 어디에 썼나</h2><p class='sub'>세분류별로 실제 말한 시간(분, 글자 수 비율로 환산 · 진행·맞장구 제외). 회차별로 나란히 보여줍니다.</p>"
            + group_bars(data, codes)
            + f"<h3 style='margin:18px 0 4px'>세분류별 말한 시간</h3><div class='pi-sc'><table class='ht'><thead><tr><th class='rl'>소구(세분류)</th>{head}</tr></thead><tbody>{rows}</tbody></table></div>")


def butterfly(hi, lo, codes, data=None):
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
            f"분당주문액이 가장 높은 방송과 가장 낮은 방송을 맞댔고(GS샵이 있으면 항상 왼쪽), 차이가 큰 3개를 진하게 표시했습니다.</p>"
            + (group_bars(data, codes) + "<h3 style='margin:18px 0 4px'>세분류별 말한 시간 <span class='sub'>(분)</span></h3>" if data else "")
            + f"<div class='bfh'><div style='color:{hi['color']}'>{e(hi['label'])} · {ppm_txt(hi)}</div><div></div>"
            f"<div style='color:{lo['color']}'>{e(lo['label'])} · {ppm_txt(lo)}</div></div>{rows}")


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
            f"<table class='mtab'><tr><th></th><th style='color:{hi['color']}'>{e(hi['label'])} · {ppm_txt(hi)}</th>"
            f"<th style='color:{lo['color']}'>{e(lo['label'])} · {ppm_txt(lo)}</th></tr>{rows}</table>")


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
        f"<div class='sb-row'><div class='sb-l'><span class='sw' style='background:{b['color']}'></span>{e(b['label'])} <span class='sub'>{ppm_txt(b)}</span></div>"
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
    return (f"<h3 style='margin-top:26px'>소구별 대표 문장</h3><p class='sub'>위 막대와 같은 순서 · 눌러서 펼쳐 보세요 · "
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
    "mbp_gs0914": "‘낙상·골절 불안’(5.3분)·‘폐경기·중년 여성’(3.4분)으로 <b>누가 왜 위험한지</b>를 롯데보다 길게(고민 합계 13.8분 · 롯데 12.2분) 말했습니다.",
    "mbp_lt0915": "‘소리 없는 뼈 손실’(3.1분)이 1위였고, 골절 불안(2.3분)·폐경기 여성(2.2분)은 GS보다 짧았습니다. 명절 선물(2.1분)은 GS보다 길었습니다.",
    "mbp_gs": "‘나이 듦’(4.8분)·‘폐경기 여성’(4.2분)처럼 <b>누구에게 왜</b> 위험한지를 롯데의 약 2배로 말했습니다.",
    "mbp_lt": "‘가을 야외활동·계절’(3.4분)이 GS보다 길었지만, 대상(폐경기 2.1분)과 원인(나이 듦 2.2분) 설명은 짧았습니다.",
    "drl_gs": "‘건강 경각심’(2.6분)·‘오메가6 과잉’(2.4분)·‘추위’(2.2분)로 <b>지금 내 몸에 필요한 이유</b>를 건드렸습니다.",
    "drl_lt": "두 번째 고민이 ‘영양제를 따로 먹는 번거로움’(3.5분, GS 0분) — 효능보다 <b>하나로 끝내는 편의</b>를 팔았습니다.",
    "sep_gs": "‘기초 여러 개 번거로움’(3.1분)을 사실상 혼자 건드렸고, 1위 고민 비중이 28%로 고민을 가장 <b>넓게</b> 펼쳤습니다.",
    "sep_hd": "‘화장품 효과 불신’(8.3분)과 ‘가품 걱정’(3.5분)이 가장 많아 <b>의심을 푸는 데</b> 시간을 썼습니다.",
    "sep_cj": "고민 이야기의 43%가 ‘중장년 노화 체념’(9.7분) 하나 — 시니어에 <b>깊게, 대신 좁게</b> 들어갔습니다.",
    "hd0621": "고민 이야기 12.3분 중 37%(4.5분)를 ‘침구 진드기·먼지’ 하나에 <b>모았습니다</b>.",
    "gs0107": "‘침구 진드기’(3.7분)·‘기존 청소기 불만’(3.4분)·‘손목 부담’(2.2분)으로 고르게 나눴습니다.",
    "gs0217": "설날 당일 방송 — 아이 있는 집·선물·효도까지 고민이 가장 <b>흩어졌습니다</b>(1위 비중 21%).",
}


def needs_line(b):
    m = needs_minutes(b)
    top = sorted(m, key=lambda n: -m[n][0])[:3]
    return (f"<p class='ndl'><b>건드린 고민</b> " + " · ".join(f"{e(n)} {m[n][0]:.1f}분" for n in top)
            + (f"<br>{NEEDS_NOTE[b['key']]}" if b["key"] in NEEDS_NOTE else "") + "</p>")


def ment_search(data, codes):
    """2026-11-19 사용자 요청: 멘트 검색 — 리포트에 든 방송의 멘트 원문(문장 단위 자막)을 띄우고 키워드로 직접 찾는다.
    쉼표로 여러 키워드, 띄어쓰기 무시 일치, 방송별 횟수 표, '일치하는 줄만/전체' 전환, 형광펜 표시."""
    payload = {"bcs": [{"key": b["key"], "label": b["label"], "color": b["color"],
                        "lines": [[mmss(u["t"]), u["code"], u["text"]] for u in b["units"]]} for b in data],
               "codes": {k: [v[0], v[2]] for k, v in codes.items()}}
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return """
<button id="msOpen" class="ms-open" title="이 리포트에 든 방송의 멘트 원문을 열고 키워드로 찾습니다">🔍 멘트 검색</button>
<div id="msModal" class="ms-modal" hidden>
 <div class="ms-box">
  <div class="ms-head">
   <b>멘트 검색</b> <span class="sub">이 리포트에 든 방송의 멘트 원문(문장 단위 자막) · 띄어쓰기 무시 · 쉼표로 여러 키워드</span>
   <button id="msClose" class="ms-x" title="닫기">✕</button>
  </div>
  <div class="ms-bar">
   <input id="msQ" placeholder="예: 최저가, 무이자, 매진, 1등" autocomplete="off">
   <label><input type="radio" name="msMode" value="hit" checked> 일치하는 줄만</label>
   <label><input type="radio" name="msMode" value="all"> 전체 보기</label>
   <label><input type="checkbox" id="msTag"> 분류 표시</label>
  </div>
  <div id="msCount" class="ms-count"></div>
  <div id="msCols" class="ms-cols"></div>
 </div>
</div>
<script id="msData" type="application/json">""" + blob + """</script>
<script>
(function(){
const D = JSON.parse(document.getElementById('msData').textContent);
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]);
const norm = s => s.replace(/\\s+/g, '').toLowerCase();
function kwRegex(k){ // 글자 사이 공백을 허용하는 정규식
  const chars = [...k.replace(/\\s+/g,'')].map(c => c.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'));
  return chars.length ? new RegExp(chars.join('\\\\s*'), 'gi') : null;
}
function render(){
  const raw = $('msQ').value.trim();
  const kws = raw.split(',').map(x => x.trim()).filter(Boolean);
  const mode = document.querySelector('input[name=msMode]:checked').value;
  const showTag = $('msTag').checked;
  const res = kws.map(k => ({k, n: norm(k), re: kwRegex(k)}));
  // 횟수 표
  if (res.length){
    let t = '<table class="ms-t"><tr><th>키워드</th>' + D.bcs.map(b => `<th style="color:${b.color}">${esc(b.label)}</th>`).join('') + '</tr>';
    res.forEach(r => {
      t += `<tr><td><mark>${esc(r.k)}</mark></td>` + D.bcs.map(b => {
        const n = b.lines.filter(l => norm(l[2]).includes(r.n)).length;
        return `<td class="${n ? 'hit' : 'zero'}">${n}줄</td>`;
      }).join('') + '</tr>';
    });
    $('msCount').innerHTML = t + '</table>';
  } else {
    $('msCount').innerHTML = '<span class="sub">키워드를 넣으면 방송별로 몇 줄에서 말했는지 나옵니다. 지금은 전체 멘트를 보여줍니다.</span>';
  }
  // 방송별 칸
  $('msCols').style.gridTemplateColumns = `repeat(${D.bcs.length}, minmax(0,1fr))`;
  $('msCols').innerHTML = D.bcs.map(b => {
    let rows = b.lines.filter(l => mode === 'all' || !res.length || res.some(r => norm(l[2]).includes(r.n)));
    const body = rows.map(([t, c, x]) => {
      let h = esc(x);
      res.forEach(r => { if (r.re) h = h.replace(r.re, m => `<mark>${m}</mark>`); });
      const tag = showTag && D.codes[c] ? `<span class="ms-tag" style="background:${D.codes[c][1]}">${esc(D.codes[c][0])}</span>` : '';
      return `<div class="ms-l"><span class="ms-tm">${t}</span>${tag}${h}</div>`;
    }).join('') || '<div class="sub" style="padding:8px">일치하는 멘트가 없습니다</div>';
    return `<div class="ms-col"><div class="ms-ch" style="color:${b.color}">${esc(b.label)} <span class="sub">${rows.length}줄 / 전체 ${b.lines.length}줄</span></div><div class="ms-body">${body}</div></div>`;
  }).join('');
}
let tmr = null;
$('msOpen').onclick = () => { $('msModal').hidden = false; render(); setTimeout(() => $('msQ').focus(), 30); };
$('msClose').onclick = () => { $('msModal').hidden = true; };
$('msModal').addEventListener('click', e => { if (e.target.id === 'msModal') $('msModal').hidden = true; });
document.addEventListener('keydown', e => { if (e.key === 'Escape') $('msModal').hidden = true; });
$('msQ').addEventListener('input', () => { clearTimeout(tmr); tmr = setTimeout(render, 150); });
document.querySelectorAll('input[name=msMode], #msTag').forEach(x => x.addEventListener('change', render));
})();
</script>"""


def best_quote(sents):
    """고민 문장 중 대표 한 줄: VCR(녹화 반복)이 아니고 25~100자 사이에서 내용이 가장 많은 문장."""
    cand = [x for x in sents if not x[2] and 25 <= len(x[1]) <= 100] or [x for x in sents if len(x[1]) <= 140] or sents
    return max(cand, key=lambda x: len(x[1])) if cand else None


def sogu_minutes(b):
    st = b["pstat"]
    tot = sum(B3.weight(u) for u in b["units"]) or 1
    dur = b["end"] / 60
    return {s_: dur * st["S"][s_] / tot for s_ in PV.SOGU if st["S"][s_] > 0}


def tagged_minutes(b, kind):
    """소구('s') 또는 NEEDS('n') 꼬리표가 하나라도 붙은 문장의 말한 시간(분) — 한 문장에 꼬리표가 둘이어도 한 번만 센다."""
    tot = sum(B3.weight(u) for u in b["units"]) or 1
    w = sum(B3.weight(b["units"][i]) for i, tg in b.get("ptags", {}).items() if tg.get(kind))
    return b["end"] / 60 * w / tot


def needs_cards(data):
    """2026-11-16 사용자 결정: NEEDS 순위는 절대량(분·문장 수)으로. %는 작게 보조. (11-19: 대표 문장·내세운 소구 추가)"""
    mins = {b["key"]: needs_minutes(b) for b in data}
    mx = max((v[0] for m in mins.values() for v in m.values()), default=1) or 1
    cards = ""
    for b in data:
        m = mins[b["key"]]
        top = [n for n in sorted(m, key=lambda n: -m[n][0]) if m[n][0] > 0][:5]
        def quote(n):
            q = best_quote(b["pstat"]["sent"].get("n:" + n, []))
            return f"<div class='nq'><span class='t'>{q[0]}</span>“{e(q[1])}”</div>" if q else ""
        rows = "".join(
            f"<div class='nr' data-k='{b['key']}' data-q='n:{e(n)}' title='눌러서 문장 보기'><span class='nn'>{i + 1}. {e(n)}</span>"
            f"<span class='nb'><i style='width:{100 * m[n][0] / mx:.1f}%;background:{b['color']}'></i></span>"
            f"<span class='nv' style='width:auto;white-space:nowrap'><b>{m[n][0]:.1f}분</b> · {m[n][1]}문장 <span class='sub'>({m[n][2]:.0f}%)</span></span></div>"
            + (quote(n) if i < 3 else "")
            for i, n in enumerate(top))
        sg = sogu_minutes(b)
        sg_top = sorted(sg, key=lambda x: -sg[x])[:3]
        sg_html = ("<div class='sgl'><b>내세운 소구</b> " + " · ".join(f"{e(x)} {sg[x]:.1f}분" for x in sg_top) + "</div>") if sg_top else ""
        others = [n for n in m if n not in top and m[n][0] > 0]
        tot = tagged_minutes(b, "n")
        cards += (f"<div class='nc' style='--c:{b['color']}'><h3 style='color:{b['color']}'>{e(b['label'])}</h3>"
                  f"<div class='sub' style='margin-bottom:4px'>고민 이야기 합계 {tot:.1f}분</div>{rows}"
                  + (f"<div class='sub' style='margin-top:6px'>그 밖: {e(' · '.join(others))}</div>" if others else "") + "</div>")
    return f"<div class='ncs'>{cards}</div>"


PRODUCT_FRAME = {  # 2026-11-19: 방송마다 제품을 '무엇'으로 소개했는지 한 줄(자막을 읽고 요약한 해석)
    "mbp_gs0914": "‘<b>인체시험으로 증명된</b> 뼈 원료’ — 우유 유래 MBP·식약처 인정, 이미 수천 박스가 팔린 제품",
    "mbp_lt0915": "‘<b>추석 전 마지막</b> 14박스’ — 명절 전에 챙기는 뼈 영양제를 최다 구성으로",
    "sep_gs": "‘지금 쓰는 기초는 그대로, 세포랩 하나만 추가’ — 기초 전에 바르는 <b>초기초 에센스</b>, 나이만큼 덧바르는 쉬운 루틴",
    "sep_hd": "‘92% 배양 원액의 <b>정품</b>’ — 물 같은 제형이지만 속건조·모공까지 잡는 에센스, 가품 주의로 신뢰를 세움",
    "sep_cj": "‘피부가 끝났다던 70대를 살린 에센스’ — <b>체험담</b>으로 회복을 보여주는 시니어 기초",
    "drl_gs": "‘GS 1등 대마종자유’ — 포화지방 대신 <b>오메가 1:3 황금비율</b> 좋은 기름, 물에 퍼지는 하이퍼셀",
    "drl_lt": "‘오메가3·6·9 <b>올인원</b>’ — 따로 사 먹던 영양제를 하나로, 역대 최저가",
    "mbp_gs": "‘폐경기 뼈 건강의 <b>식약처 인정 원료</b>’ — 인체시험으로 골밀도·골강도가 오른 MBP",
    "mbp_lt": "‘방송에서만 <b>14박스</b>’ — 가을 낙상철에 대비하는 뼈 영양제를 최다 구성으로",
    "gs0107": "‘<b>가볍고 강한</b> 디지털 슬림’ — 손목 부담 없는 무선청소기, 다음 방송 미정",
    "gs0217": "‘<b>효도템</b> 풀 패키지’ — 쇼호스트 체험담으로 보여주는 설 선물용 다이슨",
    "hd0621": "‘<b>현대만·역대 최저가</b> 디지털 슬림’ — 흡입력을 눈앞 시연으로 증명하는 가벼운 다이슨",
    "hjd_0822": "‘한 번 사면 <b>평생 새 칼</b>’ — 장인 수작업 칼과 평생 무제한 연마",
    "hjd_1024": "‘<b>내 인생 마지막 칼</b>’ — 일반 칼과 썰어 비교하는 현대 1등 칼",
    "hjd_1110": "‘<b>김장철 딱 한 번</b>’ — 배추·명란 시연으로 보여주는 평생 연마 칼 세트",
}


def sogu_cards(data):
    """2026-11-19 사용자 결정: '제품을 어떻게 팔았나'를 니즈와 같은 비중의 독립 섹션으로.
    장점(소구)별로 말한 시간 + 그 장점을 어떤 방식(세분류: 기능·효과/근거/체험/문제 제기/설명…)으로 밀었는지."""
    codes = CODES_NOW
    per = {}
    for b in data:
        st = b["pstat"]
        tot = sum(B3.weight(u) for u in b["units"]) or 1
        dur = b["end"] / 60
        mix = defaultdict(Counter)
        for i, tg in b.get("ptags", {}).items():
            u = b["units"][i]
            for x in tg["s"]:
                mix[x][u["code"]] += B3.weight(u)
        per[b["key"]] = {x: (dur * st["S"][x] / tot, len(st["sent"].get("s:" + x, [])), 100 * st["S"][x] / (st["tot"] or 1), mix[x])
                         for x in PV.SOGU if st["S"][x] > 0}
    mx = max((v[0] for m in per.values() for v in m.values()), default=1) or 1
    cards = ""
    for b in data:
        m = per[b["key"]]
        top = sorted(m, key=lambda x: -m[x][0])[:5]
        pd = [[mmss(u["t"]), u["text"], 1 if u.get("vcr") else 0] for u in b["units"] if codes.get(u["code"], ("", ""))[0] in ("상품 설명·사용법", "상품 및 구성 설명")]
        pq = best_quote(pd)
        used = {pq[1]} if pq else set()
        rows = ""
        for i, x in enumerate(top):
            mins, cnt, pct, mixc = m[x]
            mt = sum(mixc.values()) or 1
            parts = [(k, 100 * v / mt) for k, v in mixc.most_common() if k in codes and codes[k][1] != "기타"]
            mixbar = "".join(f"<i style='width:{w:.1f}%;background:{codes[k][2]}' title='{e(codes[k][0])} {w:.0f}%'></i>" for k, w in parts)
            how = " · ".join(f"{e(codes[k][0])} {w:.0f}%" for k, w in parts[:2])
            q = best_quote([y for y in b["pstat"]["sent"].get("s:" + x, []) if y[1] not in used]) if i < 3 else None
            if q:
                used.add(q[1])
            how = " ".join(f"<span class='hw'><i style='background:{codes[k][2]}'></i>{e(codes[k][0])} {w:.0f}%</span>" for k, w in parts[:2])
            # 2026-11-19 사용자 결정: NEEDS 카드와 같은 양식(방송 색 막대 + 분·문장·비중)
            rows += (f"<div class='nr' data-k='{b['key']}' data-q='s:{e(x)}' title='눌러서 문장 보기'><span class='nn'>{i + 1}. {e(x)}</span>"
                     f"<span class='nb'><i style='width:{100 * mins / mx:.1f}%;background:{b['color']}'></i></span>"
                     f"<span class='nv' style='width:auto;white-space:nowrap'><b>{mins:.1f}분</b> · {cnt}문장 <span class='sub'>({pct:.0f}%)</span></span></div>"
                     f"<div class='how'><span class='hl'>어떻게</span>{how}</div>"
                     + (f"<div class='nq'><span class='t'>{q[0]}</span>“{e(q[1])}”</div>" if q else ""))
        others = [x for x in m if x not in top]
        tot = tagged_minutes(b, "s")
        frame = PRODUCT_FRAME.get(b["key"], "")
        frame_html = ((f"<div class='frame'><span class='fl'>제품을 이렇게 설명</span>{frame}</div>" if frame else "")
                      + (f"<div class='nq'><span class='t'>{pq[0]}</span>“{e(pq[1])}”</div>" if pq else ""))
        cards += (f"<div class='nc' style='--c:{b['color']}'><h3 style='color:{b['color']}'>{e(b['label'])}</h3>{frame_html}"
                  f"<div class='sub' style='margin:6px 0 4px'>제품 이야기 합계 {tot:.1f}분</div>{rows}"
                  + (f"<div class='sub' style='margin-top:6px'>그 밖: {e(' · '.join(others))}</div>" if others else "") + "</div>")
    return f"<div class='ncs sgc'>{cards}</div>"


def needs_table(data):
    """고민(NEEDS) × 방송 비교표(분 · 문장 수, 칸 색은 분 기준). 칸을 누르면 그 방송의 해당 문장."""
    mins = {b["key"]: needs_minutes(b) for b in data}
    needs = [n for n in PV.NEEDS if any(mins[b["key"]][n][0] > 0 for b in data)]
    needs.sort(key=lambda n: -max(mins[b["key"]][n][0] for b in data))
    mx = max(mins[b["key"]][n][0] for b in data for n in needs) or 1
    head = "".join(f"<th style='color:{b['color']}'>{e(b['label'])}<div class='sub'>{ppm_txt(b)}</div></th>" for b in data)
    two = len(data) == 2
    rows = ""
    for n in needs:
        vals = [mins[b["key"]][n][0] for b in data]
        top = max(vals)
        cells = ""
        for b in data:
            v, c, pct = mins[b["key"]][n]
            al = v / mx
            lead = v == top and top > 0 and sum(1 for x in vals if x == top) == 1
            cells += (f"<td class='ntd' data-k='{b['key']}' data-q='n:{e(n)}' title='눌러서 문장 보기' "
                      f"style='background:rgba(35,131,226,{0.08 + 0.55 * al:.2f});{'font-weight:700;' if lead else ''}'>"
                      f"<b>{v:.1f}분</b><span>{c}문장 · {pct:.0f}%</span></td>")
        if two:
            d = vals[0] - vals[1]
            who = data[0] if d > 0 else data[1]
            gap = (f"<td class='ngap'><b style='color:{who['color']}'>{e(who['label'].split()[0])} +{abs(d):.1f}분</b></td>"
                   if abs(d) >= 0.5 else "<td class='ngap sub'>비슷</td>")
        else:
            lead_b = data[vals.index(top)] if top > 0 else None
            gap = (f"<td class='ngap'><b style='color:{lead_b['color']}'>{e(lead_b['label'].split()[0])} 최다</b></td>" if lead_b else "<td class='ngap'></td>")
        rows += f"<tr><th class='rl'>{e(n)}</th>{cells}{gap}</tr>"
    return (f"<table class='ht nt'><thead><tr><th class='rl'>고객 고민</th>{head}<th>더 많이 말한 쪽</th></tr></thead><tbody>{rows}</tbody></table>")


def needs_section(data, sec_html):
    """2026-11-19 사용자 결정: 니즈·소구가 가장 중요 → 실적 비교 바로 아래. '어떤 포인트로 방송했는지'를 누구에게(NEEDS)·무엇을(소구) 순서로."""
    a = sec_html.index("<h2>상품 소구 분석")
    style = sec_html[:a]
    tail = sec_html[sec_html.index('<div id="psent">'):]
    tail = tail.replace(".ht td.hc, .nr').forEach", ".ht td.hc, .nr, .ntd').forEach").replace(
        "'.ht td.hc.on, .nr.on'", "'.ht td.hc.on, .nr.on, .ntd.on'")
    intro = ("<p class='sub'>방송이 <b>누구의 어떤 고민</b>을 건드렸는지(NEEDS)와 <b>무엇을 장점으로 내세웠는지</b>(소구)를 문장 단위로 읽어 시간(분)으로 환산했습니다. "
             "분 = 해당 문장을 말한 시간(글자 수 환산)이라 방송끼리 바로 비교됩니다 · 괄호 % = 그 방송 상품 멘트 중 비중 · 줄을 누르면 실제 문장이 나옵니다.</p>")
    css = ("<style>.nq{font-size:12.5px;color:#6b6a67;margin:1px 0 6px 0;padding-left:8px;border-left:2px solid #e9e9e7;line-height:1.5}"
           ".nq .t{color:rgba(55,53,47,.45);margin-right:6px;font-variant-numeric:tabular-nums}"
           ".sgl{font-size:13px;color:#37352f;background:#f7f6f3;border-radius:4px;padding:5px 9px;margin:2px 0 8px}"
           ".nt td.ntd{cursor:pointer;text-align:center;font-variant-numeric:tabular-nums}.nt td.ntd b{display:block;font-size:14px}"
           ".nt td.ntd span{font-size:11.5px;opacity:.72}.nt td.ntd.on{outline:2px solid #37352f;outline-offset:-2px}"
           ".nt td.ngap{font-size:13px;white-space:nowrap}.nt thead th{text-align:center}.nt th.rl{white-space:normal}</style>")
    body_tail, script_tail = tail.split("<script>", 1)
    # 2026-11-19 사용자 결정: 줄을 누르면 아래로 내려가지 않고 오른쪽 패널에서 바로 문장을 본다
    body_tail = ("<div id='pside' class='pside' role='dialog' aria-label='선택한 줄의 문장'>"
                 "<button class='pside-x' title='닫기 (Esc)'>✕</button>" + body_tail + "</div>")
    sogu_intro = ("<p class='sub'>방송이 제품의 <b>어떤 장점(소구)</b>을 얼마나 오래 말했는지, 그리고 그 장점을 <b>어떤 방식</b>으로 밀었는지 — "
                  "주장(기능·효과)·근거·체험담·문제 제기·설명 중 무엇의 비중이 컸는지 — 를 보여줍니다. 색 점 = 방식(세분류) · 한 문장이 장점 두 개를 말하면 두 장점에 모두 셉니다(합계는 한 번만) · 줄을 누르면 실제 문장이 나옵니다.</p>")
    return (style + css + "<h2>방송별 NEEDS 순위 — 누구의 고민을 건드렸나</h2>" + intro
            + needs_cards(data)
            + "<h2>방송별 소구 순위 — 제품을 어떻게 팔았나</h2>" + sogu_intro + sogu_cards(data)
            + body_tail + "<script>" + script_tail
            + "<script>(function(){var P=document.getElementById('pside');if(!P)return;"
              "document.querySelectorAll('.nr,.ntd,.ht td.hc').forEach(function(el){el.addEventListener('click',function(){P.classList.add('open');var b=document.getElementById('psent');if(b)b.scrollTop=0;});});"
              "P.querySelector('.pside-x').onclick=function(){P.classList.remove('open');document.querySelectorAll('.nr.on,.ntd.on,.ht td.hc.on').forEach(function(x){x.classList.remove('on');});};"
              "document.addEventListener('keydown',function(e){if(e.key==='Escape')P.classList.remove('open');});})();</script>")


def needs_only(sec_html):
    a = sec_html.index("<h2>상품 소구 분석")
    z = sec_html.index("<h3>방송별 NEEDS 순위</h3>")
    return sec_html[:a] + "<h2>방송별 NEEDS 순위</h2>" + sec_html[z + len("<h3>방송별 NEEDS 순위</h3>"):]


EXTRA_CSS = """
.nr{grid-template-columns:150px 1fr 150px!important}
.ndl{font-size:13.5px!important;color:#5c5c5c;border-top:1px dashed #e9e9e7;padding-top:8px;margin-top:8px!important;line-height:1.65!important}.nc .nv b{color:#37352f}
.tkw{border:1px solid #cfe3d9;background:#f3faf6;border-radius:8px;padding:14px 18px;margin:12px 0}.tkw>b{font-size:16px}
.tkw ol{margin:8px 0 6px;padding-left:20px;line-height:1.75;font-size:14.5px}.tkw li{margin:4px 0}
.gbr{display:grid;grid-template-columns:130px 1fr;gap:10px;align-items:center;margin:8px 0}.gbl{font-weight:700;font-size:14px}
.gbb{display:flex;height:30px;border-radius:6px;overflow:hidden;background:#f1f1ef}.gbb i{display:flex;align-items:center;padding-left:8px;color:#fff;font-style:normal;font-weight:700;font-size:13px;white-space:nowrap;overflow:hidden}
.frame{font-size:13.5px;line-height:1.6;background:#f7f6f3;border-radius:6px;padding:7px 10px;margin:4px 0 4px}.frame .fl{display:block;font-size:12px;color:#787774;margin-bottom:1px;font-weight:600}
.sgc .sgr{display:flex!important;justify-content:space-between;align-items:baseline;gap:8px;margin:10px 0 2px;font-size:14px}
.sgc .sgr .nn{font-weight:650}.sgc .sgr .nv{white-space:nowrap;color:rgba(55,53,47,.65);font-size:13px}.sgc .sgr .nv b{color:#37352f}
.how{display:flex;flex-wrap:wrap;align-items:center;gap:2px 10px;margin:0 0 4px 0;font-size:12.5px;color:#5c5c5c}
.how .hl{color:rgba(55,53,47,.45);font-size:12px}.how .hw i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:0}
.sgc .nq{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin:2px 0 4px}
.sgc .frame{margin-bottom:6px}
.detwrap{border:1px solid #e9e9e7;border-radius:8px;margin:10px 0;padding:0 14px}.detwrap>summary{cursor:pointer;padding:10px 0;font-weight:650;font-size:14.5px}
.detwrap[open]>summary{border-bottom:1px solid #f1f1ef;margin-bottom:8px}.detwrap #detail{border:0;margin:0 0 10px}
.ms-open{position:fixed;top:12px;right:16px;z-index:1001;background:#37352f;color:#fff;border:0;border-radius:999px;padding:7px 16px;font:600 13.5px/1.3 Pretendard,-apple-system,sans-serif;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.18)}
.ms-open:hover{background:#000}
.ms-modal{position:fixed;inset:0;z-index:2000;background:rgba(15,15,15,.45);display:flex;align-items:stretch;justify-content:center;padding:24px}
.ms-modal[hidden]{display:none}
.ms-box{background:#fff;border-radius:10px;width:min(1280px,100%);display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.25)}
.ms-head{display:flex;align-items:baseline;gap:10px;padding:14px 18px;border-bottom:1px solid #e9e9e7}.ms-head b{font-size:17px}
.ms-x{margin-left:auto;border:0;background:none;font-size:18px;cursor:pointer;color:#787774}
.ms-bar{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;padding:10px 18px}
.ms-bar input#msQ{flex:1;min-width:240px;font-size:15px;padding:8px 12px;border:1px solid #d3d1cb;border-radius:6px}
.ms-bar label{font-size:13.5px;cursor:pointer}
.ms-count{padding:0 18px 8px}.ms-t{border-collapse:collapse;font-size:13.5px}.ms-t th,.ms-t td{border-bottom:1px solid #f1f1ef;padding:4px 12px;text-align:left}
.ms-t td.hit{font-weight:700}.ms-t td.zero{color:#b4b3af}
.ms-cols{display:grid;gap:10px;padding:0 18px 16px;flex:1;min-height:0}
.ms-col{display:flex;flex-direction:column;min-height:0;border:1px solid #e9e9e7;border-radius:6px}
.ms-ch{font-weight:700;padding:8px 10px;border-bottom:1px solid #f1f1ef;font-size:14px}
.ms-body{overflow:auto;padding:4px 10px;flex:1;max-height:62vh}
.ms-l{font-size:13.5px;line-height:1.55;padding:3px 0;border-bottom:1px dashed #f1f1ef}
.ms-tm{color:rgba(55,53,47,.45);font-size:12px;margin-right:6px;font-variant-numeric:tabular-nums}
.ms-l mark,.ms-t mark{background:#fde68a;color:inherit;border-radius:2px;padding:0 1px}
.ms-tag{display:inline-block;color:#fff;font-size:10.5px;border-radius:3px;padding:0 5px;margin-right:5px}
@media(max-width:700px){.ms-cols{grid-template-columns:1fr!important}.ms-modal{padding:8px}}
.pside{position:fixed;top:58px;right:16px;width:min(460px,92vw);max-height:calc(100vh - 80px);background:#fff;border:1px solid #e3e2de;border-radius:10px;box-shadow:0 10px 32px rgba(0,0,0,.18);z-index:1500;display:none;flex-direction:column}
.pside.open{display:flex}.pside #psent{border:0!important;margin:0!important;padding:12px 16px!important;max-height:none!important;overflow:auto;flex:1}
.pside-x{position:absolute;top:6px;right:8px;border:0;background:#fff;font-size:16px;color:#787774;cursor:pointer;z-index:1}
.nr.on .nn{color:#2383e2}
.tt{width:100%;border-collapse:collapse;font-size:14px;margin:6px 0}.tt th,.tt td{padding:7px 12px;border-bottom:1px solid #f1f1ef;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tt th{font-size:13px;font-weight:650;background:#fff}.tt th:first-child,.tt td:first-child{text-align:left}.tt th .sub{font-weight:400}
.tt tr.g td{background:#f7f6f3;font-weight:650;border-top:1px solid #e9e9e7}.tt tr.g td:first-child{font-size:14.5px}
.tt td.sl{padding-left:26px;color:#37352f;vertical-align:middle}.tt td{vertical-align:middle}
.tt td.bc{width:62%;text-align:left;padding:6px 12px}.bw{display:grid;grid-template-columns:44px 1fr 74px;align-items:center;gap:8px;margin:2px 0}
.bw .bl{font-size:11.5px;font-weight:650}.bw .bt{height:10px;background:#f1f1ef;border-radius:3px;overflow:hidden}.bw .bt i{display:block;height:100%;border-radius:3px}
.bw{cursor:pointer;border-radius:4px;padding:1px 3px}.bw:hover{background:#f1f1ef}.bw.on{outline:2px solid #37352f;outline-offset:-1px}.bw.big .bt{height:14px}.bw .bv{font-size:12.5px;text-align:right;white-space:nowrap}.bw.big .bv{font-weight:700}
.tt tr.sr{display:none}.tt tr.sr.show{display:table-row}.tt tr.g{cursor:pointer}.tt tr.g:hover td{background:#efeee9}
.tt .tg{display:inline-block;width:14px;color:#9b9a97;transition:transform .15s}.tt tr.g.open .tg{transform:rotate(90deg)}
.tt .hint{font-size:11px;font-weight:600;color:#a16207;background:#fff4cc;border-radius:3px;padding:0 5px;margin-left:6px}
.ttbar{display:flex;align-items:center;gap:10px;margin:2px 0 4px}.ttall{border:1px solid #e3e2de;background:#fff;border-radius:4px;padding:3px 10px;font-size:12.5px;cursor:pointer}.ttall.on{background:#37352f;color:#fff;border-color:#37352f}
.ttlg{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:13px;margin:4px 0 6px}.ttlg i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:-1px}.tt tr.hi td{background:#fff4cc}.tt tr.hi td.sl{font-weight:700}
.tt .sq{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:7px;vertical-align:0}.tt td.gp{font-size:13px}
.pcs-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px;margin:12px 0 8px}
.pc{border:1px solid #e9e9e7;border-top:3px solid var(--c);border-radius:10px;padding:14px 16px 12px;background:#fff}
.pch{display:flex;align-items:center;gap:8px;font-size:15.5px}.pbest{font-size:11px;background:#edf3ec;color:#1c5a3c;border-radius:4px;padding:1px 7px;font-weight:700}
.pcm{color:rgba(55,53,47,.55);font-size:12.5px;margin:3px 0 10px}
.pck{display:flex;align-items:baseline;gap:10px}.pkl{display:block;font-size:11.5px;color:rgba(55,53,47,.5);margin-bottom:1px}.pck .pkl{display:inline;margin:0}
.pkv{font-size:28px;font-weight:800;letter-spacing:-.5px;line-height:1.1}.pkv small{font-size:15px;font-weight:700;margin-left:1px}.pna{font-size:15px;font-weight:600;color:#9b9a97}
.pidx{margin-left:auto;font-size:12px;color:#5c5c5c;background:#f1f1ef;border-radius:4px;padding:1px 8px}
.pbar{height:6px;background:#f1f1ef;border-radius:3px;overflow:hidden;margin:8px 0 10px}.pbar i{display:block;height:100%;border-radius:3px}
.pst{display:flex;gap:18px;font-size:13px;color:#5c5c5c;margin-bottom:10px}.pst b{color:#37352f}
.pcc{display:grid;grid-template-columns:1fr 1fr;gap:9px 14px;font-size:13px;border-top:1px dashed #e9e9e7;padding-top:10px;line-height:1.45}
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


DY_PERF = {  # 다이슨 실적 카드용(홈쇼핑모아 추정 · 멘트상 조건) — top_dyson.html 표와 같은 값
    "gs0107": dict(start="2026-01-07T14:35", wmin=34.5, price=370000, final="316,350원", inst="10개월", gift="없음", rev=197_000_000),
    "gs0217": dict(start="2026-02-17T22:55", wmin=54.6, price=370000, final="323,190원", inst="10개월", gift="없음", rev=316_000_000),
    "hd0621": dict(start="2026-06-21T12:30", wmin=63.2, price=363000, final="308,853원", inst="약 12개월", gift="커피 2잔", rev=451_000_000),
}


def wx_text(day_iso):
    td = wx_td(day_iso)
    t = re.sub(r"<[^>]+>", "", td).strip()
    return t if t and t != "–" else "날씨 정보 없음"


def perf_cards(data):
    """2026-11-19 사용자 요청: 실적 비교를 가로 스크롤 표 대신 방송별 카드로(분당주문액을 크게)."""
    rated = [b["ppm"] for b in data if b.get("ppm")]
    base = min(rated) if rated else None
    best = max(rated) if rated else None
    cards = ""
    for b in data:
        d = date.fromisoformat(b["start"][:10])
        when = f"{d.year % 100:02d}.{d.month}/{d.day}({WD[d.weekday()]}) {b['start'][11:16]}"
        idx = round(100 * b["ppm"] / base) if b.get("ppm") and base else None
        top = b.get("ppm") and best and b["ppm"] == best and len(rated) > 1
        bar = (f"<div class='pbar'><i style='width:{100 * b['ppm'] / best:.0f}%;background:{b['color']}'></i></div>"
               if b.get("ppm") and best else "<div class='pbar'></div>")
        ppm = f"{b['ppm']}<small>만</small>" if b.get("ppm") else "<span class='pna'>데이터 없음</span>"
        rev = won(b["rev"]) if b.get("rev") else "–"
        price = f"{b['price']:,}원" if b.get("price") else "–"
        cards += (
            f"<div class='pc' style='--c:{b['color']}'>"
            f"<div class='pch'><b style='color:{b['color']}'>{e(b['label'])}</b>{'<span class=pbest>최고</span>' if top else ''}</div>"
            f"<div class='pcm'>{when} · {e(wx_text(b['start'][:10]))}</div>"
            f"<div class='pck'><span class='pkl'>분당주문액</span><span class='pkv'>{ppm}</span>"
            + (f"<span class='pidx'>지수 {idx}</span>" if idx else "") + "</div>"
            + bar
            + f"<div class='pst'><span>매출 <b>{rev}</b></span><span>가중분 <b>{b['wmin']:.1f}분</b></span></div>"
            f"<div class='pcc'><div><span class='pkl'>판매가</span>{price}</div><div><span class='pkl'>멘트상 최종가</span>{e(b['final'])}</div>"
            f"<div><span class='pkl'>무이자</span>{e(b['inst'])}</div><div><span class='pkl'>사은품·혜택</span>{e(b['gift'])}</div></div></div>")
    return f"<div class='pcs-grid'>{cards}</div>"


def hb_top(spec, data):
    tp = open(os.path.join(TOOLS, "top_dyson.html"), encoding="utf-8").read()
    css = tp[:tp.index("</style>") + 8]
    css2 = tp[tp.index("<style>", 10):]
    css2 = css2[:css2.index("</style>") + 8]
    rated = [b["ppm"] for b in data if b["ppm"]]
    base = min(rated) if rated else None
    best = max(rated) if rated else None
    q = __import__("urllib.parse").parse.quote(spec["q"])
    trs = ""
    for b in data:
        d = date.fromisoformat(b["start"][:10])
        when = f"{d.year} {d.month:02d}/{d.day:02d}({WD[d.weekday()]}) {b['start'][11:16]}"
        trs += (f"<tr{' class=\"pi-best\"' if best and b['ppm'] == best and len(rated) > 1 else ''}><td><span class='pi-when'>{when}</span>"
                f"<a class='pi-a' href='https://hsmoa.com/?q={q}' target='_blank' rel='noopener' title='홈쇼핑모아에서 보기'>"
                f"<i class='pi-dot' style='background:{b['color']}'></i>{e(b['ch'])} <span class='pi-ext'>↗</span></a></td>"
                f"<td>{b['wmin']:.1f}분</td><td class='pi-g'>{b['price']:,}원</td><td>{e(b['final'])}</td><td>{e(b['inst'])}</td><td>{e(b['gift'])}</td>{wx_td(b['start'][:10])}"
                f"<td class='pi-g'>{won(b['rev']) if b['rev'] else '<span class=sub>데이터 없음</span>'}</td><td><b>{ppm_txt(b, False)}</b></td><td><b>{round(100 * b['ppm'] / base) if b['ppm'] and base else '–'}</b></td></tr>")
    def bars(title, f, txt):
        mx = max((f(b) or 0) for b in data) or 1
        return (f"<div><div class='pi-h'>{title}</div>" + "".join(
            f"<div class='pi-row'><span style='color:{b['color']}'>{e(b['label'])}</span><span class='pi-track'><i style='width:{100 * (f(b) or 0) / mx:.1f}%;background:{b['color']}'></i></span><span class='pi-v'>{txt(b)}</span></div>"
            for b in data) + "</div>")
    grid = (bars("편성 추정 매출", lambda b: b["rev"], lambda b: won(b["rev"]) if b["rev"] else "–") + bars("가중분", lambda b: b["wmin"], lambda b: f"{b['wmin']:.1f}분")
            + bars("분당주문액", lambda b: b["ppm"], lambda b: f"{b['ppm']}만" if b["ppm"] else "–"))
    legend = "".join(f"<span><i class='pi-dot' style='background:{b['color']}'></i>{e(b['label'])}</span>" for b in data)
    base_lb = next((b["label"] for b in data if b["ppm"] == base), "")
    revs = ""
    for b in data:
        d = date.fromisoformat(b["start"][:10])
        hh = int(b["start"][11:13])
        slot = "아침" if hh < 11 else "낮" if hh < 17 else "저녁" if hh < 21 else "밤"
        if b["ppm"] and base:
            idx = round(100 * b["ppm"] / base)
            grade = f"<span class='grade {'good' if b['ppm'] == best and len(rated) > 1 else 'mid'}'>지수 {idx}{' · 최고' if b['ppm'] == best and len(rated) > 1 else ''}</span>"
        else:
            grade = "<span class='grade mid'>실적 데이터 없음</span>"
        revs += (f"<div class='rev' style='--c:{b['color']}'><h3 style='color:{b['color']}'>{e(b['label'])} {grade}</h3>"
                 f"<div class='meta'>{WD[d.weekday()]}요일 {slot} · <b>{e(b['kind'])}</b></div><p>{e(b['review'])}</p>{needs_line(b)}</div>")
    return f"""{css}
<div class="sumcall">{spec['summary'](data) if callable(spec['summary']) else spec['summary']}</div>
{spec['takeaways'](data) if callable(spec.get('takeaways')) else spec.get('takeaways', '')}
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
    codes = DY_CODES if dyson else dict(HB_CODES)
    if not dyson and spec.get("ev"):  # 2026-11-19 사용자 결정: 원료가 없는 상품(칼 등)은 '근거·원료' → '근거·제조'
        codes["EV"] = (spec["ev"][0], HB_CODES["EV"][1], HB_CODES["EV"][2], spec["ev"][1])
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
    _rated = [b for b in data if b["ppm"]]
    if len(_rated) >= 2:
        hi = max(_rated, key=lambda b: b["ppm"])
        lo = min(_rated, key=lambda b: b["ppm"])
        hi, lo = sorted([hi, lo], key=lambda b: data.index(b))
    else:  # 실적 있는 방송이 1개 이하면 맞대지 않고 첫·끝 방송만 순서 계산에 쓴다
        hi, lo = data[0], data[-1]  # 2026-11-19 사용자 결정: 모든 화면에서 GS가 맨 앞·왼쪽(방송 목록 순서 = GS 먼저)
    mfile = os.path.join(DY if dyson else HB, f"{spec.get('moments', name)}_moments.tsv")
    needs = needs_section(data, PV.section(data))

    page = open(os.path.join(DY, "preview_2an_v2.html"), encoding="utf-8").read()
    head, _, rest = page.partition('<div class="wrap">')
    title = f"{spec['title']} — 방송 흐름 분석 (2안)"
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
    toggle_js = """<script>document.querySelectorAll('.seg').forEach(function(x){x.addEventListener('click',function(){var d=document.querySelector('.detwrap');if(d){d.open=true;setTimeout(function(){d.scrollIntoView({behavior:'smooth',block:'nearest'});},60);}});});</script><script>(function(){const t=document.getElementById('fstog');if(t)t.onchange=()=>document.querySelectorAll('.fstrip').forEach(x=>x.style.display=t.checked?'':'none');})();</script><script>document.querySelectorAll('.vtog button').forEach(b=>b.onclick=()=>{
document.querySelectorAll('.vtog button').forEach(x=>x.classList.toggle('on',x===b));
document.getElementById('mA').style.display=b.dataset.v==='A'?'':'none';document.getElementById('mB').style.display=b.dataset.v==='B'?'':'none';});</script>"""

    if dyson:
        for b in data:
            b.update({k: v for k, v in DY_PERF.get(b["key"], {}).items() if k not in b})
    top = dyson_top(data) if dyson else hb_top(spec, data)
    # 실적 비교: 표·막대 묶음 → 방송별 카드
    top = re.sub(r'<div class="pi-legend">.*?(?=<p class="ev">)', lambda m: perf_cards(data), top, count=1, flags=re.S)
    # 2026-11-19 사용자 결정: 니즈 섹션은 다시 맨 아래(분류 기준 뒤)로 — 앞의 내용과 중복돼서
    help_marks = " · <b style=\"color:#d9730d\">▲</b> 조건 추가 멘트 위치(짧아서 구간에 묻혀도 보이게) · 빗금 = 녹화 요약(VCR) 구간" if has_marks else ""
    body = f"""<div class="wrap">
<h1>{e(title)}</h1>
{ment_search(data, codes)}
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
<details class="detwrap"><summary>구간 상세 <span class="sub">— 위 막대에서 구간을 누르면 열립니다 · 여기를 누르면 접고 펼칠 수 있어요</span></summary>
<div id="detail"><span class="sub">위 막대에서 구간을 눌러 보세요</span></div></details>
{time_section(data, codes)}
{needs}
{examples(data, codes, bf_order(hi, lo, codes)[0])}
{criteria(codes)}
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
