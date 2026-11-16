"""데이터허브 자막 화면을 그대로 복사한 텍스트 → Broadcast.

크롤링(직접 API 호출)이 금지된 뒤의 정식 입력 경로다. 사용자가 데이터허브 자막 탭을 복사해
.txt로 저장하면 그 파일을 읽는다. 화면 복사본에는 자막 말고도 화면 요소가 섞여 있다:

    00:00                      ← 시각(단독 줄)
    동시에 할 수 있는 …         ← 그 시각의 발화(여러 줄일 수 있음)
    판촉 6%                    ← 분 블록 머리말: 데이터허브가 매긴 그 분의 판촉 강도
    발화 16건                  ←   그 분의 발화 수
    01:02 ~ 01:56              ←   그 분의 범위
    조건 / 근거 / 혜택 / 사양   ← 하이라이트 라벨 + 바로 다음 줄에 범위(00:20 ~ 00:30)

분 블록 머리말은 버리지 않고 rhythm_timeline(분당 판촉 강도)으로 되살린다 — API 시절
`timeline` 필드와 같은 모양이라 리포트의 '방송 리듬'이 그대로 나온다.

파일명 규칙(권장): `YYMMDD_채널_상품명.txt` — 예) 260107_GS_다이슨 디지털 슬림.txt
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

from ..models import KST, Broadcast, Segment

_TS = re.compile(r"^(\d{1,3}):(\d{2})(?::(\d{2}))?$")
# 같은 줄에 시각+문장: "00:12 문장", "[00:12] 문장", "00:00 - 00:04 문장"(음성 인식 결과), "1:02:03 문장"
_TS_INLINE = re.compile(r"^\[?(\d{1,3}):(\d{2})(?::(\d{2}))?\]?\s*(?:[-~–]\s*\[?\d{1,3}:\d{2}(?::\d{2})?\]?)?\s*[:|]?\s+(\S.*)$")
_RANGE = re.compile(r"^(\d{1,3}):(\d{2})\s*~\s*(\d{1,3}):(\d{2})$")
_PROMO = re.compile(r"^판촉\s*(\d+)\s*%$")
_SEGS = re.compile(r"^발화\s*(\d+)\s*건$")
# 하이라이트 라벨은 '짧은 단어 + 다음 줄이 범위'로 판정한다(라벨 종류가 늘어도 버틴다)
_LABEL_MAX = 6

# 파일명·입력의 채널 표기 → 내부 채널 코드
CHANNEL_ALIASES = {
    "GS": "gsshop", "GS샵": "gsshop", "GSSHOP": "gsshop", "GS SHOP": "gsshop",
    "GSMY": "gsmyshop", "GS마이샵": "gsmyshop", "마이샵": "gsmyshop",
    "HD": "hmall", "현대": "hmall", "현대홈쇼핑": "hmall", "HMALL": "hmall",
    "HD+": "hmallplus", "현대+": "hmallplus", "현대홈쇼핑+샵": "hmallplus",
    "CJ": "cjmall", "CJ온스타일": "cjmall", "CJ+": "cjmallplus", "CJ온스타일+": "cjmallplus",
    "LT": "lotteimall", "롯데": "lotteimall", "롯데홈쇼핑": "lotteimall",
    "LTONE": "lotteonetv", "롯데원": "lotteonetv", "롯데원티비": "lotteonetv",
    "NS": "nsmall", "NS홈쇼핑": "nsmall", "NS+": "nsmallplus", "NS샵+": "nsmallplus",
    "HN": "hnsmall", "홈앤": "hnsmall", "홈앤쇼핑": "hnsmall",
    "공영": "immall", "공영쇼핑": "immall",
    "KT": "kshop", "KT알파": "kshop", "KT+": "kshopplus",
    "SK": "bshop", "SK스토아": "bshop", "W": "wshop", "W쇼핑": "wshop",
    "SSG": "ssgshop", "신세계": "ssgshop", "신세계쇼핑": "ssgshop",
    "엔티": "shopnt", "쇼핑엔티": "shopnt",
}


def channel_code(token: str) -> str:
    t = (token or "").strip()
    return CHANNEL_ALIASES.get(t.upper(), CHANNEL_ALIASES.get(t, CHANNEL_ALIASES.get(t.upper().replace(" ", ""), t.lower())))


_DATE_KO = re.compile(r"^(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일$")
_PRICE = re.compile(r"^([\d,]+)원$")
_PAGE_TITLE = re.compile(r"\|\s*홈쇼핑모아 DataHub\s*$")


def page_meta(text: str) -> dict | None:
    """데이터허브 방송 상세 화면을 통째로 복사한 텍스트에서 방송 정보를 뽑는다.

    화면 구성: 상품명 / 채널(GS SHOP·롯데홈쇼핑…) / 2026년 10월 27일 / 07:15 ~ 08:15 / 브랜드 / 상품명 / 459,000원
    못 찾으면 None(파일명 규칙으로 대신한다).
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i in range(1, len(lines) - 1):
        d, r = _DATE_KO.match(lines[i]), _RANGE.match(lines[i + 1])
        if not (d and r):
            continue
        day = datetime(int(d.group(1)), int(d.group(2)), int(d.group(3)))
        start = day + timedelta(hours=int(r.group(1)), minutes=int(r.group(2)))
        end = day + timedelta(hours=int(r.group(3)), minutes=int(r.group(4)))
        if end <= start:  # 자정을 넘기는 편성
            end += timedelta(days=1)
        price = next((int(m.group(1).replace(",", "")) for ln in lines[i + 2:i + 8] if (m := _PRICE.match(ln))), None)
        return {
            "channel": channel_code(lines[i - 1]),
            "product_name": lines[i - 2] if i >= 2 else "",
            "start_datetime": start.isoformat(),
            "end_datetime": end.isoformat(),
            "price": price,
        }
    return None


def parse_filename(path: str) -> dict:
    """`260107_GS_다이슨 디지털 슬림.txt` → {date, channel, product_name}. 규칙에 안 맞으면 빈 값."""
    stem = os.path.splitext(os.path.basename(path))[0]
    m = re.match(r"^(\d{6}|\d{8})[_\s-]+([^_]+)[_\s-]+(.+)$", stem)
    if not m:
        return {"date": "", "channel": "", "product_name": stem}
    d = m.group(1)
    if len(d) == 6:
        d = "20" + d
    return {
        "date": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
        "channel": channel_code(m.group(2)),
        "product_name": m.group(3).strip(),
    }


def _sec(m: re.Match, base: int = 1) -> int:
    mm, ss = int(m.group(base)), int(m.group(base + 1))
    return mm * 60 + ss


def parse_copy_text(
    text: str,
    *,
    channel: str,
    product_name: str,
    start_datetime: str,
    end_datetime: str | None = None,
    channel_name: str | None = None,
    broadcast_id: str | None = None,
    price: int | None = None,
) -> Broadcast:
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    # Ctrl+A 로 통째로 복사하면 자막 앞에 메뉴·방송 정보·AI 하이라이트(시각이 붙어 있다)가,
    # 맨 끝에 페이지 제목("… | 홈쇼핑모아 DataHub")이 딸려 온다.
    # '자막에서 찾기'(자막 탭 머리)가 있으면 그 뒤 첫 분 블록 머리말부터, 없으면 첫 시각 줄부터 읽는다.
    lines = [ln for ln in lines if not _PAGE_TITLE.search(ln)]
    anchor = next((k for k, ln in enumerate(lines) if ln == "자막에서 찾기"), None)
    if anchor is not None:
        first = next((k for k in range(anchor, len(lines)) if _PROMO.match(lines[k])), None)
    else:
        first = next((k for k, ln in enumerate(lines)
                      if _TS.match(ln) or _TS_INLINE.match(ln) or _PROMO.match(ln)), None)
    if first:
        lines = lines[first:]

    segments: list[Segment] = []
    rhythm: list[dict] = []
    highlights: list[dict] = []
    cur_t: int | None = None
    buf: list[str] = []
    pending_promo: dict | None = None

    def flush():
        nonlocal buf
        if buf and cur_t is not None:
            segments.append(Segment(start_sec=float(cur_t), end_sec=None, text=" ".join(buf)))
        buf = []

    i = 0
    while i < len(lines):
        ln = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""

        if m := _PROMO.match(ln):
            flush()
            pending_promo = {"pct": int(m.group(1))}
        elif (m := _SEGS.match(ln)) and pending_promo is not None:
            pending_promo["segs"] = int(m.group(1))
        elif m := _RANGE.match(ln):
            flush()
            if pending_promo is not None:  # 분 블록 머리말의 범위
                start = _sec(m, 1)
                segs = pending_promo.get("segs", 0)
                pct = pending_promo["pct"]
                rhythm.append({"m": start // 60, "segs": segs, "promo": round(segs * pct / 100),
                               "pct": pct, "quiet": False})
                pending_promo = None
        elif len(ln) <= _LABEL_MAX and _RANGE.match(nxt) and not _TS.match(ln):
            flush()  # 하이라이트 라벨(조건·근거·혜택·사양 …) + 다음 줄 범위
            r = _RANGE.match(nxt)
            highlights.append({"label": ln, "start": _sec(r, 1), "end": _sec(r, 3)})
            i += 2
            continue
        elif m := _TS.match(ln):
            flush()
            cur_t = int(m.group(1)) * 60 + int(m.group(2))
        elif m := _TS_INLINE.match(ln):
            flush()
            a_, b_, c_ = int(m.group(1)), int(m.group(2)), m.group(3)
            # H:MM:SS 이면 시·분·초, 아니면 분:초
            cur_t = a_ * 3600 + b_ * 60 + int(c_) if c_ is not None else a_ * 60 + b_
            buf.append(m.group(4).strip())
        else:
            if cur_t is None:
                cur_t = 0
            buf.append(ln)
        i += 1
    flush()

    # 다음 발화 시각을 끝 시각으로
    for a, b in zip(segments, segments[1:]):
        a.end_sec = b.start_sec
    last = segments[-1].start_sec if segments else 0.0

    start_dt = datetime.fromisoformat(start_datetime)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=KST)
    if not end_datetime:
        # 편성 종료를 모르면 마지막 발화가 속한 분 끝까지로 본다
        end_datetime = (start_dt + timedelta(seconds=(int(last) // 60 + 1) * 60)).isoformat()

    return Broadcast(
        broadcast_id=broadcast_id or f"{channel}:{product_name}:{start_datetime}",
        channel=channel,
        channel_name=channel_name,
        product_name=product_name,
        start_datetime=start_dt.isoformat(),
        end_datetime=end_datetime,
        segments=segments,
        price=price,
        source="datahub_copy",
        extra={"rhythm_timeline": rhythm, "highlights": highlights},
    )


def load_copy_file(path: str, **overrides) -> Broadcast:
    """파일을 읽어 Broadcast로. 채널·상품·날짜는 파일명에서 추정하고 overrides 가 우선한다.

    방송 시작 '시각'은 복사본에 없다. 모르면 그 날 00:00으로 두고 extra.time_known=False 로 표시한다
    (가중분·분당주문액은 시작 시각이 있어야 의미가 있다).
    """
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    meta = parse_filename(path)
    time_known = bool(overrides.get("start_datetime"))
    start = overrides.pop("start_datetime", None) or f"{meta['date'] or '2000-01-01'}T00:00:00+09:00"
    kw = {
        "channel": overrides.pop("channel", None) or meta["channel"] or "unknown",
        "product_name": overrides.pop("product_name", None) or meta["product_name"],
        "start_datetime": start,
    }
    kw.update(overrides)
    bc = parse_copy_text(text, **kw)
    bc.extra["time_known"] = time_known
    bc.extra["source_file"] = os.path.basename(path)
    return bc
