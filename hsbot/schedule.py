"""주간 편성표 데이터 — 시작 화면(hsmoa-weekly 스타일 그리드)용.

홈쇼핑모아 `/next-api/schedule?date=YYYY-MM-DD` 를 하루 1회씩 받아(한 주 7회) 가전·주방
편성만 골라 4분류(category.py)하고, 매출·가중분·분당주문액을 붙인다.

요청 수를 아끼는 게 핵심이다(검색 남발로 429 차단을 겪었다):
  · 지난 날짜(그제 이전) 편성은 바뀌지 않으므로 디스크 캐시 — 한 번 받으면 다시 안 묻는다.
  · 오늘·미래 편성은 메모리에 30분 둔다.
  · NEW 판단은 이미 받아둔(디스크 캐시) 지난 편성만 본다 — NEW 때문에 추가 호출하지 않는다.
  · 매출은 편성 응답에 이미 들어 있다. 빠진 방송만 50건당 1회(POST)로 묶어 묻고, 디스크 캐시.
  · 가중분은 가중치 표로 계산만 하므로 요청이 없다.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any

from .category import classify
from .models import KST
from .sources.datahub import DataHubClient, DataHubError
from .time_weight import LIVE_CHANNELS, weighted_minutes_from_iso

# hsmoa-weekly 와 같은 표기·순서
SHOP_NAMES = {
    "nsmall": "NS홈쇼핑", "gsshop": "GS샵", "lotteimall": "롯데홈쇼핑", "hmall": "현대홈쇼핑",
    "cjmall": "CJ온스타일", "hnsmall": "홈앤쇼핑", "immall": "공영쇼핑",
    "wshop": "W쇼핑", "bshop": "SK스토아", "hmallplus": "현대홈쇼핑+샵", "nsmallplus": "NS샵+",
    "lotteonetv": "롯데원티비", "shopnt": "쇼핑엔티", "gsmyshop": "GS마이샵", "cjmallplus": "CJ온스타일+",
    "ssgshop": "신세계쇼핑", "kshop": "KT알파쇼핑", "kshopplus": "KT알파쇼핑+",
}
SHOP_ORDER = list(SHOP_NAMES)

# 사이트 편성표 필터와 같은 형식("대분류" 또는 "대분류:중분류"). 서버에서 가전·주방만 걸러 받는다.
CATEGORY_FILTER = "가전,생필품/주방:주방용품,건강:안마용품"
# 사이트는 4시간씩 6번 부르지만, 우리는 하루를 한 번에 받는다(호출 1/6).
_DAY_PARAMS = {"start_hour": "0", "hour_num": "24", "category_filter": CATEGORY_FILTER}

_MEM: dict[str, tuple[float, Any]] = {}
_MEM_TTL = 1800  # 오늘·미래 편성은 30분 동안 다시 묻지 않는다
_LOCK = threading.Lock()
_REVENUE_CACHE = os.path.join(".cache", "revenue.json")


def _today() -> date:
    return datetime.now(KST).date()


def cached_day(client: DataHubClient, day: date) -> Any | None:
    """디스크에 이미 있는 하루치 편성만 돌려준다. 없으면 None — 네트워크는 쓰지 않는다."""
    try:
        cp = client._cache_path(client._url("schedule", {"date": day.isoformat(), **_DAY_PARAMS}))
    except (DataHubError, AttributeError):
        return None
    if not cp or not os.path.exists(cp):
        return None
    with open(cp, encoding="utf-8") as f:
        return json.load(f)


def fetch_day(client: DataHubClient, day: date) -> Any:
    """하루치 편성 원본. 지난 날짜는 디스크 캐시, 최근·미래는 30분 메모리 캐시."""
    iso = day.isoformat()
    if day < _today() - timedelta(days=1):
        return client.get("schedule", use_cache=True, date=iso, **_DAY_PARAMS)
    with _LOCK:
        hit = _MEM.get(iso)
        if hit and time.time() - hit[0] < _MEM_TTL:
            return hit[1]
    raw = client.get("schedule", use_cache=False, date=iso, **_DAY_PARAMS)
    with _LOCK:
        _MEM[iso] = (time.time(), raw)
    return raw


def _walk(o: Any):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _first(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def parse_day(raw: Any) -> list[dict]:
    """편성 응답 → 방송 1건당 대표 상품 1개.

    한 방송(broadcast_key)에 여러 상품이 걸리면(same_time_products, live_order) 대표 상품
    (live_order가 가장 작은 것)만 남긴다. 응답 구조가 바뀌어도 버티도록 broadcast_key 와
    pdid 를 가진 dict 를 전부 훑는다.
    """
    best: dict[str, dict] = {}
    for d in _walk(raw):
        key, pdid = d.get("broadcast_key"), d.get("pdid")
        if not key or not pdid:
            continue
        order = d.get("live_order") or 99
        prev = best.get(key)
        if prev is None or order < (prev.get("live_order") or 99):
            best[key] = d
    out = []
    for key, d in best.items():
        parts = str(key).split("|")
        if len(parts) < 3:
            continue
        channel, start, end = parts[0], parts[1], parts[2]
        out.append({
            "channel": d.get("tv_channel") or channel,
            "product_key": d["pdid"],
            "title": str(_first(d, "name", "product_name", "title", "goods_name") or d["pdid"]),
            "category1": str(d.get("category1") or ""),
            "category2": str(d.get("category2") or ""),
            "category3": str(d.get("category3") or ""),
            # 편성 응답에 대표 상품 기준 편성합산 매출이 이미 들어 있다(같이 걸린 상품은 None).
            # 덕분에 매출 조회(POST /schedule/revenue)를 따로 부를 필요가 없다.
            "revenue": d.get("revenue"),
            "sales_count": d.get("sales_count"),
            "start": start,
            "end": end,
            "price": _first(d, "sale_price", "price"),
        })
    return out


_NORM = re.compile(r"[\[\(【（][^\]\)】）]*[\]\)】）]|[^0-9A-Za-z가-힣]")


def _norm_title(t: str) -> str:
    """NEW 판정용 — 괄호 속 판촉 문구·기호를 지워 같은 상품의 재방송을 같은 키로."""
    return _NORM.sub("", t).upper()[:40]


def _load_revenue_cache() -> dict:
    try:
        with open(_REVENUE_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_revenue_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(_REVENUE_CACHE), exist_ok=True)
    with open(_REVENUE_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def _kst_iso(s: str) -> str:
    dt = datetime.fromisoformat(s)
    dt = dt.replace(tzinfo=KST) if dt.tzinfo is None else dt.astimezone(KST)
    return dt.isoformat()


def attach_revenue(client: DataHubClient, items: list[dict]) -> None:
    """끝난 방송에 매출·판매수량을 붙인다. 이틀 지난 방송 값은 디스크 캐시."""
    now = datetime.now(KST)
    cache = _load_revenue_cache()
    need = []
    for it in items:
        k = f"{it['channel']}|{_kst_iso(it['start'])}|{_kst_iso(it['end'])}"
        it["_rkey"] = k
        if k in cache:
            it["revenue"], it["sales_count"] = cache[k]
        elif not it["upcoming"]:
            need.append(it)
    dirty = False
    for i in range(0, len(need), 50):
        chunk = need[i:i + 50]
        try:
            resp = client.fetch_revenue([
                {"tv_channel": it["channel"], "start_datetime": it["start"],
                 "end_datetime": it["end"], "product_key": it["product_key"]}
                for it in chunk
            ])
        except DataHubError:
            continue
        bmap = resp.get("broadcasts") or {}
        for it in chunk:
            row = bmap.get(it["_rkey"])
            if not row:
                continue
            it["revenue"], it["sales_count"] = row.get("revenue"), row.get("sales_count")
            end = datetime.fromisoformat(it["end"])
            end = end if end.tzinfo else end.replace(tzinfo=KST)
            if it["revenue"] is not None and now - end > timedelta(days=2):
                cache[it["_rkey"]] = [it["revenue"], it["sales_count"]]
                dirty = True
    if dirty:
        _save_revenue_cache(cache)
    for it in items:
        it.pop("_rkey", None)


def build_week(client: DataHubClient, monday: date, *, new_lookback_days: int = 14) -> dict:
    """월요일부터 7일 편성 → 그리드용 항목.

    NEW = 직전 `new_lookback_days`일 편성 중 '이미 받아둔 날'에 없던 상품. 받아둔 지난 편성이
    하나도 없으면 판단 근거가 없으므로 NEW 를 붙이지 않는다(전부 NEW 로 뜨는 것보다 낫다).
    """
    days = [monday + timedelta(days=i) for i in range(7)]
    now = datetime.now(KST)
    items: list[dict] = []
    errors: list[str] = []
    for d in days:
        try:
            raw = fetch_day(client, d)
        except DataHubError as e:
            errors.append(f"{d.isoformat()}: {str(e).splitlines()[0]}")
            continue
        for e in parse_day(raw):
            cat = classify(e["title"], e["category1"], e["category2"], e["category3"])
            if not cat:
                continue
            start = datetime.fromisoformat(e["start"])
            start = start if start.tzinfo else start.replace(tzinfo=KST)
            local = start.astimezone(KST)
            ch = e["channel"]
            wmin = weighted_minutes_from_iso(e["start"], e["end"], ch)
            end = datetime.fromisoformat(e["end"])
            end = end if end.tzinfo else end.replace(tzinfo=KST)
            items.append({
                "date": local.date().isoformat(),
                "time": local.strftime("%H:%M"),
                "hour": local.hour,
                "shop": SHOP_NAMES.get(ch, ch),
                "channel": ch,
                "group": "live" if ch in LIVE_CHANNELS else "tcom",
                "title": e["title"],
                "cat": cat,
                "product_key": e["product_key"],
                "start": e["start"],
                "end": e["end"],
                "duration_min": round((end - start).total_seconds() / 60),
                "weighted_min": round(wmin, 1) if wmin is not None else None,
                "upcoming": start > now,
                "revenue": e["revenue"],
                "sales_count": e["sales_count"],
                "link": f"https://datahub.hsmoa.com/product/{e['product_key']}",
            })

    # NEW: 직전 기간 편성에서 본 적 없는 상품명
    seen: set[str] = set()
    known_days = 0
    for i in range(1, new_lookback_days + 1):
        raw = cached_day(client, monday - timedelta(days=i))
        if raw is None:
            continue
        known_days += 1
        for e in parse_day(raw):
            seen.add(_norm_title(e["title"]))
    # 이번 주 안에서도 첫 방송만 NEW
    first: dict[str, str] = {}
    for it in sorted(items, key=lambda x: x["start"]):
        first.setdefault(_norm_title(it["title"]), it["start"])
    for it in items:
        k = _norm_title(it["title"])
        it["new"] = known_days > 0 and k not in seen and first.get(k) == it["start"]

    # 편성 응답에 매출이 비어 있는(아직 집계 전이거나 캐시가 오래된) 끝난 방송만 따로 묻는다.
    missing = [it for it in items if it["revenue"] is None and not it["upcoming"]]
    if missing:
        attach_revenue(client, missing)
    for it in items:
        rev, w = it.get("revenue"), it.get("weighted_min")
        it["rpwm"] = round(rev / w) if rev is not None and w else None

    items.sort(key=lambda x: (x["date"], x["time"], SHOP_ORDER.index(x["channel"]) if x["channel"] in SHOP_ORDER else 99))
    counts: dict[str, int] = {}
    for it in items:
        counts[it["channel"]] = counts.get(it["channel"], 0) + 1
    shops = [
        {"channel": c, "name": SHOP_NAMES.get(c, c), "group": "live" if c in LIVE_CHANNELS else "tcom",
         "count": counts[c]}
        for c in sorted(counts, key=lambda c: (c not in LIVE_CHANNELS, -counts[c]))
    ]
    return {
        "monday": monday.isoformat(),
        "dates": [d.isoformat() for d in days],
        "today": _today().isoformat(),
        "items": items,
        "shops": shops,
        "errors": errors,
        "new_basis_days": known_days,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 로컬 편성 파일로 주간 편성표 만들기 (홈쇼핑모아 직접 호출 없이)
# ─────────────────────────────────────────────────────────────────────────────
# 아침 메일 작업(hsmoa_weekly.py)이 hsmoa.com 편성표 화면에서 매일 모아 두는 all_data.json 을 읽는다.
# 2026-10-21 부터는 같은 화면 데이터의 가격 조건(extra: 판매가·할인가·카드 할인·무이자·카테고리·시작/종료)도
# 함께 저장된다. 그 이전 날짜는 시각·상품명·방송사만 있다(편성 길이는 60분으로 가정).
LOCAL_SCHEDULE_PATH = os.environ.get(
    "HSBOT_SCHEDULE_JSON", r"C:\hsmoa_jobs\홈쇼핑모아 정보수집\all_data.json"
)


def build_week_local(monday: date, path: str | None = None, *, new_lookback_days: int = 14) -> dict:
    path = path or LOCAL_SCHEDULE_PATH
    if not os.path.exists(path):
        raise DataHubError(f"로컬 편성 파일이 없습니다: {path}\n  아침 수집 작업(hsmoa_daily_email)이 돌았는지 확인하세요.")
    with open(path, encoding="utf-8") as f:
        data: dict[str, list[dict]] = json.load(f)

    days = [monday + timedelta(days=i) for i in range(7)]
    now = datetime.now(KST)
    items: list[dict] = []
    for d in days:
        for raw in data.get(d.isoformat(), []):
            ex = raw.get("extra") or {}
            ch = ex.get("tv_channel") or raw.get("shop") or ""
            title = raw.get("title") or ""
            cat = classify(title, ex.get("category1") or "", ex.get("category2") or "", ex.get("category3") or "")
            if not cat:
                continue
            if ex.get("start"):
                start = datetime.fromisoformat(ex["start"])
            else:
                hh, mm = (raw.get("time") or "00:00").split(":")
                start = datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=KST)
            start = start if start.tzinfo else start.replace(tzinfo=KST)
            end = datetime.fromisoformat(ex["end"]) if ex.get("end") else start + timedelta(minutes=60)
            end = end if end.tzinfo else end.replace(tzinfo=KST)
            wmin = weighted_minutes_from_iso(start.isoformat(), end.isoformat(), ch)
            link = raw.get("link") or ""
            items.append({
                "date": start.astimezone(KST).date().isoformat(),
                "time": start.astimezone(KST).strftime("%H:%M"),
                "hour": start.astimezone(KST).hour,
                "shop": SHOP_NAMES.get(ch, ch), "channel": ch,
                "group": "live" if ch in LIVE_CHANNELS else "tcom",
                "title": title, "cat": cat,
                "product_key": link.rsplit("/", 1)[-1] if link else "",
                "start": start.isoformat(), "end": end.isoformat(),
                "duration_min": round((end - start).total_seconds() / 60),
                "duration_known": bool(ex.get("end")),
                "weighted_min": round(wmin, 1) if wmin is not None else None,
                "upcoming": start > now,
                "link": link,
                # 가격 조건(있을 때만)
                "price": ex.get("price"), "sale_price": ex.get("sale_price"), "sale_rate": ex.get("sale_rate"),
                "card_discounts": ex.get("card_discounts") or [],
                "interest_free": ex.get("interest_free"), "promo": ex.get("promo"),
                "revenue": None, "sales_count": None, "rpwm": None,   # 매출은 로컬 데이터에 없다
            })

    # NEW: 직전 기간에 같은 상품명이 없던 것
    seen: set[str] = set()
    known_days = 0
    for i in range(1, new_lookback_days + 1):
        prev = data.get((monday - timedelta(days=i)).isoformat())
        if prev is None:
            continue
        known_days += 1
        seen.update(_norm_title(x.get("title") or "") for x in prev)
    first: dict[str, str] = {}
    for it in sorted(items, key=lambda x: x["start"]):
        first.setdefault(_norm_title(it["title"]), it["start"])
    for it in items:
        k = _norm_title(it["title"])
        it["new"] = known_days > 0 and k not in seen and first.get(k) == it["start"]

    items.sort(key=lambda x: (x["date"], x["time"], SHOP_ORDER.index(x["channel"]) if x["channel"] in SHOP_ORDER else 99))
    counts: dict[str, int] = {}
    for it in items:
        counts[it["channel"]] = counts.get(it["channel"], 0) + 1
    shops = [
        {"channel": c, "name": SHOP_NAMES.get(c, c), "group": "live" if c in LIVE_CHANNELS else "tcom", "count": counts[c]}
        for c in sorted(counts, key=lambda c: (c not in LIVE_CHANNELS, -counts[c]))
    ]
    covered = sorted(data)
    return {
        "monday": monday.isoformat(),
        "dates": [d.isoformat() for d in days],
        "today": _today().isoformat(),
        "items": items, "shops": shops, "errors": [],
        "new_basis_days": known_days,
        "source": "local",
        "source_note": f"아침 수집 파일 기준 ({covered[0]} ~ {covered[-1]})" if covered else "아침 수집 파일",
    }
