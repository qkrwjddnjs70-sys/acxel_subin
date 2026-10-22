"""편성 상품 4분류: 디가(digital) · 렌탈(rental) · 주방(kitchen) · 생가(life).

1순위는 홈쇼핑모아 카테고리(category1/2/3)다 — 예) 가전/주방가전/튀김기, 생필품/주방/주방용품/식기.
상품명 키워드만 보면 '엘지생활건강' 화장품이 디가로, '직화 닭발'이 주방으로 새는 오탐이 생긴다(실측).
카테고리가 비어 있을 때만 상품명 키워드로 판단한다(hsmoa-weekly 4,641건과 90.7% 일치하던 규칙).

  · 포함 범위 — 가전 전체 + 생필품/주방 중 '주방용품' + 렌탈 상품 + 안마용품.
                식품·뷰티·의류·수건/청소용품 같은 생활용품은 뺀다.
  · 렌탈  — 정수기·렌탈·상담예약·'결제 0원' 등. 가장 먼저 본다.
  · 디가  — 삼성·LG·캐리어 같은 대형가전 브랜드 + TV. 브랜드가 곧 분류다(hsmoa-weekly 기준).
            단 이동식·창문형 에어컨은 생가.
  · 주방  — 주방가전(카테고리 '주방가전', 김치·쌀냉장고) + 주방용품(냄비·프라이팬·식기 …).
  · 생가  — 그 외 가전.
"""
from __future__ import annotations

import re

LABELS = {"digital": "디가", "rental": "렌탈", "kitchen": "주방", "life": "생가"}

_RENTAL = re.compile(
    r"렌탈|렌털|정수기|상담\s*예약|상담\s*신청|무료\s*상담|상담만|시공\s*상담|결제\s*0\s*원|구독"
)
_DIGITAL = re.compile(
    # "삼성카드 5% 할인"의 삼성, "엘지생활건강"의 엘지, "홀로그램"의 그램 같은 오탐을 피한다
    r"삼성(?!\s*카드)|LG(?!\s*생활)|엘지(?!\s*생활)|캐리어|휘센|비스포크|Bespoke|디오스|오브제|퓨리케어"
    r"|무풍|트롬|갤럭시|\bTV\b|TV\s|QNED|OLED|올레드|공기청정|에어컨|세탁기|건조기|워시콤보",
    re.I,
)
_NOT_DIGITAL = re.compile(r"이동식|창문형")
_KITCHEN = re.compile(
    # 주방가전
    r"밥솥|밥통|압력솥|가마솥|믹서|블렌더|블랜더|에어\s*프라이어|오븐|전자레인지"
    r"|착즙|원액기|주서|녹즙|김치\s*냉장|쌀\s*냉장|음식물\s*처리|인덕션|전기레인지|하이라이트(?!.*히터)"
    r"|멀티\s*쿠커|슬로우\s*쿠커|커피|토스터|전기\s*포트|커피포트|그릴|식기\s*세척|다지기|제빵|떡빵"
    r"|요거트|진공\s*포장|중탕기|약탕기|두유\s*제조|제면|반죽기|트윈프레셔|마스터셰프"
    # 비가전 주방용품
    r"|냄비|프라이팬|후라이팬|궁중팬|큐브팬|스텐팬|볶음팬|그릴팬|전골팬|웍|칼\s*세트|식도|도마"
    r"|밀폐\s*용기|보관\s*용기|반찬\s*통|김치\s*통|수저|커트러리|식기|그릇|채칼|찜기|주전자|쿡웨어"
    r"|쿡셀|해피콜|휘슬러|실리트|WMF|코렐|락앤락|글라스락",
    re.I,
)
_LIFE = re.compile(
    r"매트|전기요|장판|청소기|다리미|스타일러|드라이어|고데기|면도기|이발기|칫솔|선풍기|서큘레이터"
    r"|써큘레이터|제습기|가습기|히터|온풍기|난로|보일러|이어폰|헤드폰|스피커|스마트워치|안마|마사지"
    r"|족욕|체중계|혈압|찜질|전기|무선|충전|보조배터리|조명|램프|가전|BLDC|모터|비데|에어컨"
    r"|로보락|다이슨|에어랩|드리미|에코백스|필립스|브라운|한일|신일|보국|파세코|쿠쿠",
    re.I,
)


def _in_scope(c1: str, c2: str, name: str) -> bool:
    """홈쇼핑모아 카테고리로 편성표에 올릴지 정한다."""
    if c1 == "가전":
        return True
    if c1 == "생필품/주방" and c2 == "주방용품":
        return True
    if c1 == "건강" and "안마" in c2:
        return True
    # 렌탈은 '서비스/금융' 등 엉뚱한 곳에 분류되기도 한다 — 이름으로 잡되 식품·뷰티·의류는 제외
    if _RENTAL.search(name) and c1 not in ("식품", "뷰티", "의류", "잡화"):
        return True
    return False


def classify(name: str, category1: str = "", category2: str = "", category3: str = "") -> str | None:
    """상품명 + 홈쇼핑모아 카테고리 → 'digital' | 'rental' | 'kitchen' | 'life' | None(편성표 제외)."""
    name = name or ""
    c1, c2, c3 = (category1 or "").strip(), (category2 or "").strip(), (category3 or "").strip()
    has_cats = bool(c1)

    if has_cats and not _in_scope(c1, c2, name):
        return None
    if _RENTAL.search(name):
        return "rental"
    if _DIGITAL.search(name) and not _NOT_DIGITAL.search(name):
        return "digital"
    if has_cats:
        if c2 in ("주방가전", "주방용품") or re.search(r"김치\s*냉장|쌀\s*냉장", c3 + name):
            return "kitchen"
        return "life"

    # 카테고리가 없을 때(옛 데이터·HAR 등): 상품명 키워드만으로
    if _KITCHEN.search(name):
        return "kitchen"
    if _LIFE.search(name):
        return "life"
    return None
