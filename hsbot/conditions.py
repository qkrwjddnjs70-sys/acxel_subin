"""멘트(자막)에서 '방송 조건'을 뽑는다 — 최종가·무이자·월 납입·카드·앱 할인·사은품·구성·보증·강조 문구.

리포트 맨 위 '방송 조건 비교표'의 재료다. 값마다 근거 멘트(시각+문장)를 함께 남겨
사람이 바로 검증할 수 있게 한다. 자막 오인식("무의자" = 무이자)도 일부 흡수한다.

한계: 쇼호스트가 숫자를 말로만 풀어 말하거나("삼십이만 원") 화면 자막으로만 띄운 조건은 못 잡는다.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .textutil import _MONEY_PART, _PART_RE, _UNIT, extract_percents

_MONEY_ITER = re.compile(rf"((?:{_MONEY_PART}\s*)+)(원대|원)")
_NOINT = re.compile(r"무[이의]\s*자")          # STT 오인식 '무의자' 포함
_NOINT_MONTHS = re.compile(r"무[이의]\s*자\s*(?:할부)?\s*(\d{1,2})\s*개월|(\d{1,2})\s*개월\s*(?:동안\s*)?무[이의]\s*자")
_MONTHLY = re.compile(rf"(?:한\s*달에|월)\s*((?:{_MONEY_PART}\s*)+)(원대|원)")
_CARDS = ["삼성", "현대", "롯데", "농협", "NH", "KB", "국민", "신한", "BC", "비씨", "씨티", "카카오", "토스", "IBK"]
# '하나만 있으셔도', '우리 현대 고객님' 같은 일상어 오탐을 피하려고 하나·우리는 '카드'가 붙을 때만 인정
_CARD_NAME = re.compile(r"(" + "|".join(_CARDS) + r")\s*(?:카드)?|(하나|우리)\s*카드", re.I)
_APP = re.compile(r"앱|어플|모바일|애플리케이션")
_GIFT = re.compile(r"사은품|증정|덤으로|쿠폰")  # "선물로 드리기 좋다"는 사은품이 아니라 선물 추천이라 제외
# '커피도 챙겨드려요', '커피까지 다 받아가세요', '커피 쿠폰까지' — 명사 + 도/까지 + 주는 말
_GIFT_ITEM = re.compile(r"([가-힣A-Za-z]{2,6})\s*(?:쿠폰)?\s*(?:도|까지)\s*(?:다\s*|전부\s*|저희가\s*)?(?:\d+\s*[가-힣]{0,2}\s*)?(?:쿠폰|챙겨|해\s*드|드려|드릴|드립|증정|싸\s*드|받아)")
_WARRANTY = re.compile(r"무상\s*(?:A\s*/?\s*S|에이에스|수리)?\s*(?:도|는)?\s*(\d)\s*년|(\d)\s*년\s*(?:동안\s*)?무상")
_WARRANTY_ANY = re.compile(r"무상\s*(?:A\s*/?\s*S|에이에스|수리)|품질\s*보증")
_FLAGS = {
    "단독": re.compile(r"단독"),
    "최저가": re.compile(r"최저가|역대\s*최저|제일\s*(?:싸|저렴)"),
    "방송에서만": re.compile(r"방송\s*(?:중)?에서만|방송\s*중에만|방송\s*끝나면"),
    "한정·매진": re.compile(r"한정|매진|선착순|수량|품절"),
    "이번 달 단 한 번": re.compile(r"단\s*한\s*번|딱\s*한\s*번|한\s*번밖에"),
}
_GIFT_STOP = {"방송", "혜택", "조건", "가격", "고객님", "저희가", "오늘", "지금", "이거", "이것", "여기", "할인", "무이자",
              "보여", "말씀", "안내", "모든", "이렇게", "그리고", "추가로", "같이", "패키지", "풀패키지", "사은품", "구성",
              "멤버십", "등급", "카드", "배송", "설치", "상담", "전부", "모두", "다른", "기회", "찬스", "최저가", "가격도",
              "할부", "일시불", "적립", "그것", "저것", "이불", "침구", "먼지", "청소", "본체", "충전"}


@dataclass
class Condition:
    value: str = ""
    evidence: list[tuple[float, str]] = field(default_factory=list)  # (초, 문장)

    def add(self, t: float, text: str, limit: int = 3) -> None:
        if len(self.evidence) < limit and all(text != e for _, e in self.evidence):
            self.evidence.append((t, text))


def money_mentions(text: str) -> list[tuple[int, bool]]:
    """문장 속 금액 → [(원, '원대' 여부)]."""
    out = []
    for chunk, suffix in _MONEY_ITER.findall(text):
        bare = chunk.strip()
        if re.fullmatch(r"\d+", bare):
            total = float(bare)
        else:
            total = sum(float(n.replace(",", "")) * _UNIT.get(u, 1) for n, u in _PART_RE.findall(chunk) if n)
        if 100 <= total <= 10**10:
            out.append((int(total), suffix == "원대"))
    return out


def _won(v: int) -> str:
    """32만 3,190원 처럼 — 단 10만 원 미만(카드 할인액·월 납입)은 17,010원 처럼 그대로 쓰는 게 더 읽기 쉽다."""
    if v >= 100000:
        man, rest = divmod(v, 10000)
        return f"{man}만" + (f" {rest:,}" if rest else "") + "원"
    return f"{v:,}원"


def extract(segments: list, *, list_price: int | None = None, component_terms: list[str] | None = None) -> dict[str, Any]:
    """segments: start_sec/text 를 가진 자막 줄 목록. list_price: 판매가(알면 최종가 후보를 거르는 데 쓴다)."""
    c = {k: Condition() for k in ("최종가", "무이자", "월 납입", "카드 할인", "앱·모바일 할인", "사은품", "구성", "보증", "강조")}
    explicit_gift = False
    exact: Counter = Counter()
    approx: Counter = Counter()
    first_seen: dict[int, tuple[float, str]] = {}
    months: Counter = Counter()
    monthly: list[int] = []
    cards: Counter = Counter()
    card_amounts: Counter = Counter()
    app_disc: Counter = Counter()
    gifts: Counter = Counter()
    comps: Counter = Counter()
    warranty: Counter = Counter()
    flags: Counter = Counter()

    lo = (list_price or 0) * 0.5 or 50_000
    hi = list_price or 10**8   # 최종가는 판매가를 넘지 않는다('39만 9천 원인가요?' 같은 비교용 금액 제외)

    for s in segments:
        t, text = float(s.start_sec), s.text
        # 최종가 후보: 판매가 근처의 금액(월 납입·카드 할인액 같은 작은 금액은 제외)
        for v, is_approx in ([] if text.rstrip().endswith("?") else money_mentions(text)):  # 되묻는 말은 제외
            if lo <= v <= hi:
                (approx if is_approx else exact)[v] += 1
                first_seen.setdefault(v, (t, text))
        # 무이자
        if _NOINT.search(text):
            m = _NOINT_MONTHS.search(text)
            if m:
                months[int(m.group(1) or m.group(2))] += 1
            c["무이자"].add(t, text)
        # 월 납입
        for chunk, suffix in _MONTHLY.findall(text):
            for v, _ in money_mentions(chunk + suffix):
                if 1_000 <= v <= 500_000:
                    monthly.append(v)
                    c["월 납입"].add(t, text)
        # 카드 할인
        if "카드" in text:
            found = [(m.group(1) or m.group(2), m.end()) for m in _CARD_NAME.finditer(text)]
            names = {n.upper() if n.isascii() else n for n, _ in found}
            if re.search(r"현대\s*(?:만|단독|고객)", text):
                names.discard("현대")  # '현대 단독', '현대 고객님' — 카드사가 아니라 방송사
            if names or re.search(r"카드\s*(?:할인|청구)", text):
                for n in names:
                    cards[n] += 1
                after = text[max((e for _, e in found), default=0):]
                for v, _ in money_mentions(after):
                    if 1_000 <= v <= 200_000:
                        card_amounts[v] += 1
                c["카드 할인"].add(t, text)
        # 앱·모바일 할인
        if _APP.search(text) and (extract_percents(text) or re.search(r"할인|빼\s*드|아껴", text)):
            for p in extract_percents(text):
                app_disc[f"{p:g}%"] += 1
            for v, _ in money_mentions(text):
                if 1_000 <= v <= 200_000:
                    app_disc[_won(v)] += 1
            c["앱·모바일 할인"].add(t, text)
        # 사은품: '사은품' 이라는 말이 없어도 '커피도 챙겨드려요' 같은 문장을 잡는다
        comp_set = set(component_terms or [])
        items = [w for w in _GIFT_ITEM.findall(text)
                 if w not in _GIFT_STOP and w not in comp_set and not w.endswith(("씩", "님"))]
        for w in items:
            gifts[w] += 1
        if _GIFT.search(text):
            explicit_gift = True
        if items or _GIFT.search(text):
            c["사은품"].add(t, text)
        # 구성품
        for term in component_terms or []:
            if term in text:
                comps[term] += 1
        if re.search(r"풀\s*패키지|구성", text) and len(c["구성"].evidence) < 2:
            c["구성"].add(t, text, limit=2)
        # 보증
        for a, b in _WARRANTY.findall(text):
            warranty[f"무상 AS {a or b}년"] += 1
            c["보증"].add(t, text, limit=1)
        if _WARRANTY_ANY.search(text):
            warranty["무상 AS 언급"] += 0  # 기간을 말한 쪽이 있으면 그쪽을 쓴다(0 = 존재만 표시)
            c["보증"].add(t, text, limit=1)
        # 강조 문구
        for name, rx in _FLAGS.items():
            n = len(rx.findall(text))
            if n:
                flags[name] += n

    # --- 값 정리 ---
    final_exact = None
    precise = {v: n for v, n in exact.items() if v % 10000}   # 끝자리까지 말한 금액 = 최종가일 가능성 높음
    if precise:
        final_exact = sorted(precise.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        c["최종가"].value = f"{_won(final_exact)} ({precise[final_exact]}회 언급)"
        c["최종가"].add(*first_seen[final_exact])
    else:
        rough = Counter(approx) + Counter({v: n for v, n in exact.items() if not v % 10000})
        if rough:
            v = sorted(rough.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            c["최종가"].value = f"{_won(v).replace('원', ' 원대')} ({rough[v]}회 언급)"
            c["최종가"].add(*first_seen[v])
    if months:
        m = months.most_common(1)[0][0]
        c["무이자"].value = f"{m}개월"
    elif c["무이자"].evidence:
        if final_exact and monthly:  # 개월 수를 말하지 않았으면 최종가 ÷ 월 납입으로 추정
            c["무이자"].value = f"약 {round(final_exact / min(monthly))}개월 (추정: 최종가÷월 납입)"
        else:
            c["무이자"].value = "있음 (개월 수 언급 없음)"
    if monthly:
        v = min(monthly)
        c["월 납입"].value = f"월 {v // 10000}만 원대" if v % 10000 == 0 else f"월 {v:,}원대"
    if cards or c["카드 할인"].evidence:
        names = "·".join(n for n, _ in cards.most_common(5))
        amt = f" {_won(card_amounts.most_common(1)[0][0])}" if card_amounts else ""
        c["카드 할인"].value = (names + amt).strip() or "언급 있음"
    if app_disc:
        c["앱·모바일 할인"].value = ", ".join(k for k, _ in app_disc.most_common(2))
    elif c["앱·모바일 할인"].evidence:
        c["앱·모바일 할인"].value = "언급 있음"
    gifts = Counter({k: n for k, n in gifts.items() if n >= 2})  # 한 번 스친 말은 사은품으로 보지 않는다
    if gifts:
        c["사은품"].value = ", ".join(k for k, _ in gifts.most_common(3))
    elif explicit_gift:
        c["사은품"].value = "언급 있음 (품목 불명)"
    else:
        c["사은품"].evidence = []
    if comps:
        c["구성"].value = ", ".join(k for k, _ in comps.most_common(6))
    years = [k for k, n in warranty.items() if n > 0]
    if years:
        c["보증"].value = max(years, key=lambda k: warranty[k])
    elif "무상 AS 언급" in warranty:
        c["보증"].value = "무상 AS 언급 (기간 미언급)"
    if flags:
        c["강조"].value = " · ".join(f"{k} {n}회" for k, n in flags.most_common())

    return {k: {"value": v.value, "evidence": v.evidence} for k, v in c.items()}
