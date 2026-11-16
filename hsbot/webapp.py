"""키워드 → 채널별 최근 방송일자 → 선택 → 자동 리포트, 웹 UI.

의존성 0 원칙을 지키기 위해 stdlib `http.server`만 쓴다(Flask 등 없음).
실적(편성합산 추정 매출)은 `POST /next-api/schedule/revenue`(HAR 역추적으로 발견)로
받아온다 — 방송이 끝난 직후라면 아직 집계 전이라 빠질 수 있다.

사용법
    HSMOA_DATAHUB_COOKIE="..." python -m hsbot webapp
    → http://127.0.0.1:8765 접속
"""
from __future__ import annotations

import html
import json
import os
import sys
import time
import traceback
import urllib.parse
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import discover as dc
from .compare import compare as compare_broadcasts
from .lexicon import load_combined
from .metrics import analyze as analyze_one
from .models import KST
from .report import render as render_html
from .schedule import build_week, build_week_local
from .sources import cmpsite, labangba, library
from .sources.datahub import DataHubClient, DataHubError
from .time_weight import LIVE_CHANNELS, weighted_minutes_from_iso

# 검색 응답에 채널명 필드가 없어(mapping.search.channel_name_paths 비움) 코드로 예쁘게 만든다.
CHANNEL_NAMES = {
    # 라이브(홈쇼핑)
    "gsshop": "GS샵", "cjmall": "CJ온스타일", "lotteimall": "롯데홈쇼핑", "lotte": "롯데홈쇼핑",
    "hmall": "현대홈쇼핑", "nsmall": "NS홈쇼핑", "hnsmall": "홈앤쇼핑", "immall": "공영쇼핑",
    # T커머스 — 같은 회사라도 라이브와 다른 채널이므로 이름을 섞지 않는다
    "gsmyshop": "GS마이샵", "cjmallplus": "CJ온스타일+", "lotteonetv": "롯데원티비",
    "hmallplus": "현대홈쇼핑+샵", "nsmallplus": "NS샵+", "kshop": "KT알파쇼핑",
    "kshopplus": "KT알파쇼핑+", "ssgshop": "신세계쇼핑", "shopnt": "쇼핑엔티",
    "bshop": "SK스토아", "wshop": "W쇼핑",
}


WEEKLY_HTML_PATH = os.path.join(os.path.dirname(__file__), "weekly.html")


def channel_display(code: str, fallback: str | None = None) -> str:
    return CHANNEL_NAMES.get(code) or fallback or code


def broadcast_type(code: str) -> str:
    return "라이브" if code in LIVE_CHANNELS else "T커머스"


def default_lexicons(keyword: str) -> list[str]:
    names = ["core_ko"]
    if any(k in keyword for k in ("로보락", "로봇", "물걸레", "vacuum")):
        names.append("product_robot_vacuum")
    elif any(k in keyword for k in ("다이슨", "디지털 슬림", "무선청소기", "스틱", "청소기")):
        names.append("product_stick_vacuum")
    if "냉장고" in keyword:
        names.append("product_fridge")
    if any(k in keyword for k in ("써큘레이터", "서큘레이터", "circulator")):
        names.append("product_circulator")
    return names


def _squash(s: str) -> str:
    return "".join(str(s).split()).upper()


def _search_weeks(client: DataHubClient, keyword: str, weeks: int) -> list[dc.BroadcastRef]:
    """검색 호출 수 = 1 + weeks.

    날짜 없이 한 번 묻는 게 기본이다(브랜드에 따라 최근 열흘~몇 달이 나온다). 더 넓은 기간이
    필요할 때만 사용자가 고른 주 수만큼 1주씩 잘라 더 묻는다 — 검색 API는 한 번에 기간 안의
    '최신 일부'(약 50~60편성)만 주기 때문이다. 호출 하나하나가 계정 제재 위험이라 기본은 1회.
    """
    from datetime import timedelta

    refs: list[dc.BroadcastRef] = list(client.search(keyword, pages=1, size=200, use_cache=False))
    end = datetime.now(KST).date()
    for _ in range(weeks):
        start = end - timedelta(days=6)
        refs += client.search(keyword, pages=1, size=200, use_cache=False,
                              start_datetime=start.isoformat(), end_datetime=end.isoformat())
        end = start - timedelta(days=1)
    return refs


def attach_labangba(broadcasts: list[dict]) -> None:
    """방송마다 라방바 편성 판매금액(`revenue`)과 실제 편성 시각·길이를 채운다.

    라방바에 없는 방송(T커머스·4개사 외·매칭 실패)은 매출을 비운다 — 홈쇼핑모아 추정과 섞지 않는다.
    단, 보관함 방송정보.csv 에 매출을 직접 적은 방송(revenue_source 지정)은 그 숫자를 그대로 둔다.
    """
    for b in broadcasts:
        if not b.get("revenue_source"):
            b["revenue"] = b["sales_count"] = None
            hit = None
            if not b.get("upcoming"):
                # 2026-11-16: 사내 '아이템 편성 비교'(라방바 원천, 1월~) 먼저 — 매출·원천 가중분·판매수량을 함께 준다.
                # 거기 없는 방송만 기존 라방바 파일로 채운다(가중분은 시간대 가중치로 계산).
                try:
                    hit = cmpsite.lookup(b["channel"], b.get("start_datetime") or "")
                except Exception:  # noqa: BLE001
                    hit = None
                if not hit:
                    hit = labangba.lookup(b["channel"], b.get("start_datetime") or "")
            if hit:
                b.update(revenue=hit["revenue"], sales_count=hit["sales_count"], end_datetime=hit["end"],
                         revenue_source="라방바", weighted_min=hit.get("weighted_min"),
                         duration_min=round((datetime.fromisoformat(hit["end"]) -
                                             datetime.fromisoformat(hit["start"])).total_seconds() / 60))
        # 날씨·강수(기상청 서울, 일 단위) — 사내 '아이템 편성 비교' 페이지 데이터. 매출은 아직 기존 라방바 그대로.
        try:
            b["weather"] = cmpsite.weather(b.get("start_datetime") or "") if b.get("start_datetime") else None
        except Exception:  # noqa: BLE001 — 사내망 밖이면 날씨 칸만 비운다
            b["weather"] = None
        b["revenue_per_weighted_min"] = None
        if b.get("revenue") is not None:
            wmin = b.get("weighted_min") or weighted_minutes_from_iso(b["start_datetime"], b["end_datetime"], b["channel"])
            if wmin and wmin > 0:
                b["revenue_per_weighted_min"] = round(b["revenue"] / wmin)


def revenue_note(items: list[dict]) -> str:
    """리포트 하단에 붙일 매출 출처 단서."""
    srcs = sorted({it.get("revenue_source") for it in items if it.get("revenue") is not None})
    notes = {"라방바": labangba.SOURCE_NOTE,
             "홈쇼핑모아": "매출은 홈쇼핑모아 편성 추정치입니다 — 실제 매출과 다릅니다."}
    return " ".join(notes.get(s, f"매출 출처: {s}") for s in srcs)


def search_library(keyword: str) -> dict | None:
    """직접 호출이 꺼져 있을 때 방송 보관함(demo_library/<키워드>/)에서 찾는다. 폴더가 없으면 None."""
    folder = library.find_folder(keyword)
    if not folder:
        return None
    time.sleep(1.2)  # 보관함은 즉시 읽히지만 화면 흐름은 실제 검색과 같게
    now = datetime.now(KST)
    broadcasts = library.list_broadcasts(folder)
    for b in broadcasts:
        b.update(broadcast_id=None, channel_name=channel_display(b["channel"]),
                 broadcast_type=broadcast_type(b["channel"]), model_key=dc.model_key(b["product_name"]),
                 upcoming=datetime.fromisoformat(b["start_datetime"]).replace(tzinfo=KST) > now)
    attach_labangba(broadcasts)
    return {"keyword": keyword, "broadcasts": broadcasts}


BACK_JS = "if(history.length>1&&document.referrer){history.back();}else{location.href='/search';}return false;"
BACK_BTN = ('<a class="hb-back" href="/search" onclick="' + BACK_JS + '" title="이전 화면으로(없으면 방송 검색으로)">← 뒤로</a>'
            '<style>.hb-back{position:absolute;top:12px;left:12px;z-index:1000;background:#fff;color:#37352f;border:1px solid #e3e2de;'
            'border-radius:999px;padding:5px 14px;font:600 13px/1.4 Pretendard,-apple-system,sans-serif;text-decoration:none;'
            'box-shadow:0 1px 3px rgba(0,0,0,.08)}.hb-back:hover{background:#f1f1ef}</style>')


def with_back_button(page: str) -> str:
    """리포트 화면 왼쪽 위에 '뒤로' 버튼. 탭 화면(2안|1안)은 탭 줄에 이미 있어서 넣지 않는다."""
    if 'class="hb-back"' in page or 'class="tabs"' in page:
        return page
    i = page.find("<body")
    if i < 0:
        return BACK_BTN + page
    j = page.index(">", i) + 1
    return page[:j] + BACK_BTN + page[j:]


def tabbed_report(html_2an: str, html_1an: str) -> str:
    """2안(소구 문맥 분류)과 1안(키워드 집계)을 탭 하나로. 처음엔 2안을 보여준다."""
    import html as _h
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>방송 비교</title><style>
html,body{{margin:0;height:100%;background:#fff;font-family:Pretendard,-apple-system,sans-serif}}
.tabs{{display:flex;gap:4px;padding:8px 16px 0;border-bottom:1px solid #e3e2de;background:#fbfbfa;height:40px;box-sizing:border-box}}
.tabs button{{border:0;background:none;padding:6px 14px;font-size:14px;color:#787774;cursor:pointer;border-radius:6px 6px 0 0;font-family:inherit}}
.tabs button.on{{background:#fff;color:#37352f;font-weight:700;box-shadow:0 -1px 0 #e3e2de inset,1px 0 0 #e3e2de,-1px 0 0 #e3e2de}}
.tabs a{{margin-left:auto;align-self:center;font-size:13px;color:#787774;text-decoration:none}}
iframe{{border:0;width:100%;height:calc(100% - 40px);display:none}} iframe.on{{display:block}}
</style></head><body>
<div class="tabs"><button class="on" data-t="a">2안 · 소구 문맥 분류</button><button data-t="b">1안 · 키워드 집계</button><a href="/search" onclick="{BACK_JS}">← 뒤로</a></div>
<iframe id="a" class="on" srcdoc="{_h.escape(html_2an, quote=True)}"></iframe>
<iframe id="b" srcdoc="{_h.escape(html_1an, quote=True)}"></iframe>
<script>document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{{
document.querySelectorAll('.tabs button,iframe').forEach(x=>x.classList.remove('on'));
b.classList.add('on');document.getElementById(b.dataset.t).classList.add('on');}});</script>
</body></html>"""


def build_library_compare_html(*, items: list[dict], keyword: str) -> str:
    """보관함 방송 비교. 미리 만든 리포트(리포트.html)가 이 선택과 맞으면 그것을, 아니면 1안을 바로 만든다."""
    folder = library.find_folder(keyword)
    if not folder:
        raise DataHubError(f"'{keyword}' 보관함 폴더가 없습니다(demo_library/).")
    pre_name = library.prebuilt_report_name(folder, [it["local_file"] for it in items])
    if pre_name:
        pre = library.prebuilt_report(folder, [it["local_file"] for it in items])
        second = library.prebuilt_2an(folder, pre_name)
        return tabbed_report(second, pre) if second else pre
    broadcasts = []
    for it in items:
        bc = library.load(folder, it)
        bc.channel_name = channel_display(it["channel"])
        broadcasts.append(bc)
    seen: dict[str, int] = {}
    for bc in broadcasts:
        seen[bc.channel_name] = seen.get(bc.channel_name, 0) + 1
    for bc in broadcasts:
        label = f"{bc.channel_name} {bc.start_datetime[5:10].replace('-', '/')}"
        bc.channel_name = label if seen[bc.channel_name] > 1 else bc.channel_name
    product = keyword or broadcasts[0].product_name
    lex = load_combined(default_lexicons(product))
    metrics = [analyze_one(bc, lex) for bc in broadcasts]
    res = compare_broadcasts(broadcasts, metrics)
    return render_html(res, title=f"{product} — 홈쇼핑 채널별 판매 화법 비교",
                       source_note=f"방송 {len(broadcasts)}건 · 사전 {lex.name} · {revenue_note(items)}")


def search_broadcasts(client: DataHubClient, keyword: str, *, weeks: int = 0, limit: int = 400) -> dict:
    """키워드 → 검색에 걸린 방송을 최신순으로 최대 `limit`개 그대로 나열한다.

    예전에는 상품명에서 모델명을 추정해 '한 묶음'만 보여줬는데, 일월·쿡셀처럼
    상품 라인이 많고 채널마다 상품명이 제각각인 브랜드에선 엉뚱한 묶음이 뽑혀
    대부분의 방송이 사라졌다. 이제는 전부 보여주고, 좁히는 건 화면의 상품명 필터로 한다.

    검색 API는 여러 단어를 한 문장으로 넣으면 결과가 크게 달라진다(정확 문구에 가깝다).
    그래서 여러 단어면 첫 단어(브랜드)로 검색한 뒤, 나머지 단어가 상품명에
    들어간 것만 남긴다(띄어쓰기 무시).
    """
    tokens = keyword.split()
    # 검색 결과는 새 편성이 계속 붙는 목록이라 캐시를 쓰지 않는다(_search_weeks 안에서).
    # 여러 단어면 브랜드(첫 단어)로만 묻고 나머지는 로컬에서 거른다 — 문장 검색은 0건이 잦아
    # 둘 다 물으면 호출만 두 배가 된다.
    refs = dc.dedupe(_search_weeks(client, tokens[0] if tokens else keyword, weeks))
    if len(tokens) > 1:
        need = [_squash(t) for t in tokens[1:]]
        narrowed = [r for r in refs if all(n in _squash(r.product_name) for n in need)]
        refs = narrowed or refs
    if not refs:
        return {"keyword": keyword, "broadcasts": []}

    now = datetime.now(KST)
    broadcasts: list[dict] = []
    for r in refs:
        # 검색 결과의 tv_channel 은 그 방송이 실제로 나간 채널이다(상품코드 접두어와 다를 수 있음:
        # gsshop_ 상품이 gsmyshop 에서, lotteimall_ 상품이 lotteonetv 에서 나가는 식).
        channel = r.tv_channel or r.channel
        start = dc._parse_dt(r.start_datetime)
        broadcasts.append(
            {
                "broadcast_id": None,  # 비교할 때 방송 이력에서 찾아 채운다(목록 단계에선 호출 절약)
                "channel": channel,
                "channel_name": channel_display(channel),
                "broadcast_type": broadcast_type(channel),
                "product_key": r.product_key,
                "product_name": r.product_name,
                "model_key": dc.model_key(r.product_name),
                "start_datetime": r.start_datetime or "",
                "end_datetime": r.end_datetime or "",
                "duration_min": round(r.duration_min) if r.duration_min else None,
                "upcoming": bool(start and start > now),
            }
        )
    broadcasts.sort(key=lambda b: b["start_datetime"], reverse=True)
    broadcasts = broadcasts[:limit]
    # 자막 유무·잠김은 목록 단계에서 확인하지 않는다(방송마다 호출이 나가 제재를 불렀다).
    # 비교할 때 고른 방송만 확인하고, 못 쓰는 방송은 리포트에서 이유와 함께 뺀다.
    # 매출은 홈쇼핑모아 추정 대신 라방바(사내 경쟁사 편성 분석) 기준으로 통일한다
    attach_labangba(broadcasts)
    return {"keyword": keyword, "broadcasts": broadcasts}


def _resolve_broadcast_id(client: DataHubClient, item: dict) -> None:
    """검색 결과의 방송(채널+시작시각)에 해당하는 broadcast_id를 방송 이력에서 찾는다."""
    if item.get("broadcast_id"):
        return
    want = str(item.get("start_datetime") or "")[:16]
    history = client.list_broadcasts(item["product_key"], use_cache=False)
    for h in history:
        if str(h.get("start_datetime") or "")[:16] == want and (
            not h.get("channel") or h.get("channel") == item.get("channel")
        ):
            item["broadcast_id"] = h.get("broadcast_id")
            return
    raise DataHubError(
        f"{channel_display(item.get('channel', ''))} {want.replace('T', ' ')} 방송의 자막을 찾지 못했습니다 "
        "(방영 전이거나 자막이 아직 올라오지 않은 방송입니다)."
    )


def _kst_iso(dt_str: str) -> str:
    """DataHub 매출 API 응답 키 포맷(KST, 초 단위, +09:00)으로 맞춘다."""
    dt = datetime.fromisoformat(dt_str)
    dt = dt.replace(tzinfo=KST) if dt.tzinfo is None else dt.astimezone(KST)
    return dt.isoformat()


def _attach_revenue(client: DataHubClient, broadcasts: list[dict]) -> None:
    """방송마다 편성합산 추정 매출(`revenue`)·판매수량(`sales_count`)을 채운다.

    실패해도(네트워크 오류, 아직 집계 전이라 응답에 그 편성이 없음) 조용히
    넘어간다 — 매출은 부가 정보라 이것 때문에 검색 자체가 깨지면 안 된다.
    """
    candidates = [b for b in broadcasts if b.get("start_datetime") and b.get("end_datetime")]
    if not candidates:
        return
    try:
        resp = client.fetch_revenue(
            [
                {
                    "tv_channel": b["channel"],
                    "start_datetime": b["start_datetime"],
                    "end_datetime": b["end_datetime"],
                    "product_key": b["product_key"],
                }
                for b in candidates
            ]
        )
    except DataHubError:
        return
    bmap = resp.get("broadcasts") or {}
    for b in candidates:
        key = f'{b["channel"]}|{_kst_iso(b["start_datetime"])}|{_kst_iso(b["end_datetime"])}'
        row = bmap.get(key)
        if row:
            b["revenue"] = row.get("revenue")
            b["sales_count"] = row.get("sales_count")
        if b.get("revenue") is not None:
            wmin = weighted_minutes_from_iso(b["start_datetime"], b["end_datetime"], b["channel"])
            if wmin and wmin > 0:
                b["revenue_per_weighted_min"] = round(b["revenue"] / wmin)


def fetch_labeled(client: DataHubClient, item: dict):
    _resolve_broadcast_id(client, item)
    bc = client.fetch_by_broadcast_id(
        item["broadcast_id"],
        product_key=item["product_key"],
        channel=item["channel"],
        start_datetime=item["start_datetime"],
        end_datetime=item.get("end_datetime") or item["start_datetime"],
        product_name=item.get("product_name") or None,
        use_cache=True,
    )
    bc.channel_name = channel_display(item["channel"], item.get("channel_name") or bc.channel_name)
    # 검색 결과(/api/search)에서 이미 조회해둔 편성 추정 매출을 그대로 들고 간다 —
    # 비교할 때마다 다시 호출할 필요 없다.
    bc.extra["broadcast_id"] = item.get("broadcast_id")
    bc.extra["revenue"] = item.get("revenue")
    bc.extra["weighted_min"] = item.get("weighted_min")
    bc.extra["sales_count"] = item.get("sales_count")
    return bc


COMPARE_HTML_PATH = os.path.join(os.path.dirname(__file__), "compare.html")
# 만든 리포트를 저장해 두고 /report/<이름> 으로 다시 연다(새로고침·공유·지난 리포트 보기)
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "reports")


def save_report(html_text: str, title: str) -> str:
    import re as _re
    os.makedirs(REPORT_DIR, exist_ok=True)
    slug = _re.sub(r"[^0-9A-Za-z가-힣]+", "_", title).strip("_")[:40] or "report"
    name = f"{datetime.now(KST).strftime('%Y%m%d_%H%M%S')}_{slug}.html"
    with open(os.path.join(REPORT_DIR, name), "w", encoding="utf-8") as f:
        f.write(html_text)
    return name


def build_text_compare_html(payload: dict) -> str:
    """업로드·붙여넣은 자막(데이터허브 화면 복사본·음성 인식 결과·'시각 문장' 텍스트)으로 비교 리포트.

    사이트에는 아무 요청도 하지 않는다. 방송사·시작 시각·편성 길이·판매가·매출은 사용자가 넣은 값.
    """
    from .sources.datahub_copy import channel_code, parse_copy_text

    items = payload.get("items") or []
    if len(items) < 2:
        raise DataHubError("비교하려면 방송이 2개 이상 필요합니다.")
    keyword = (payload.get("keyword") or "").strip()
    broadcasts = []
    for i, it in enumerate(items):
        text = it.get("text") or ""
        if not text.strip():
            raise DataHubError(f"{i + 1}번째 방송의 자막이 비어 있습니다.")
        ch = channel_code(it.get("channel") or "") or "unknown"
        start = (it.get("start") or "").strip()
        time_known = bool(start and len(start) >= 16)
        if not start:
            start = "2000-01-01T00:00"
        start_dt = datetime.fromisoformat(start.replace(" ", "T"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=KST)
        dur = int(it.get("duration_min") or 60)
        name = (it.get("product") or keyword or "상품").strip()
        label = it.get("label") or f"{channel_display(ch)} {start_dt.strftime('%m/%d')}"
        bc = parse_copy_text(
            text, channel=ch, product_name=name, start_datetime=start_dt.isoformat(),
            end_datetime=(start_dt + timedelta(minutes=dur)).isoformat(),
            channel_name=label, broadcast_id=f"b{i}:{ch}:{start_dt.isoformat()}",
            price=int(it["price"]) if it.get("price") else None,
        )
        if it.get("revenue"):
            bc.extra["revenue"] = int(it["revenue"])
        bc.extra["time_known"] = time_known
        broadcasts.append(bc)

    # 같은 방송사·같은 날짜가 겹치면 라벨에 시각을 붙여 구분
    seen: dict[str, int] = {}
    for bc in broadcasts:
        seen[bc.channel_name] = seen.get(bc.channel_name, 0) + 1
    for bc in broadcasts:
        if seen[bc.channel_name] > 1:
            bc.channel_name = f"{bc.channel_name} {bc.start_datetime[11:16]}"

    product = keyword or broadcasts[0].product_name
    lex = load_combined(default_lexicons(product))
    metrics = [analyze_one(bc, lex) for bc in broadcasts]
    res = compare_broadcasts(broadcasts, metrics)
    note = f"자막 {len(broadcasts)}건 업로드 · 사전 {lex.name} · 문구 규칙 {len(lex.phrases)}개"
    if not all(bc.extra.get("time_known") for bc in broadcasts):
        note += " · 방송 시작 시각이 비어 있는 방송은 가중분·분당주문액이 정확하지 않습니다"
    return render_html(res, title=f"{product} — 홈쇼핑 판매 화법 비교", source_note=note)


def build_compare_html(client: DataHubClient, *, items: list[dict], keyword: str) -> str:
    if not items:
        raise DataHubError("비교할 방송을 선택하지 않았습니다.")
    broadcasts, skipped = [], []
    for it in items:
        try:
            bc = fetch_labeled(client, it)
        except DataHubError as e:
            skipped.append(str(e))
            continue
        if not bc.segments:
            # 홈쇼핑모아에서 이 계정이 아직 '자막 열기'를 안 한 방송은 줄 수만 오고 본문이 비어 있다.
            skipped.append(f"{bc.channel_name} {it['start_datetime'][:16].replace('T', ' ')} 방송은 "
                           "자막이 잠겨 있습니다(홈쇼핑모아에서 자막 열기 필요).")
            continue
        broadcasts.append(bc)
    if len(broadcasts) < 2:
        raise DataHubError("비교하려면 자막이 있는 방송이 2개 이상 필요합니다.\n- " + "\n- ".join(skipped))
    product_name = keyword or next((it.get("product_name") for it in items if it.get("product_name")), "")
    lex = load_combined(default_lexicons(keyword or product_name))
    metrics = [analyze_one(bc, lex) for bc in broadcasts]
    res = compare_broadcasts(broadcasts, metrics)
    ids = ",".join(str(b_.extra.get("broadcast_id")) for b_ in broadcasts)
    note = f"broadcast_id={ids} · {revenue_note(items)}"
    if skipped:
        note += " · 제외: " + " / ".join(skipped)
    return render_html(res, title=f"{product_name} — 홈쇼핑 채널별 판매 화법 비교" if product_name else None,
                       source_note=note)


INDEX_HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>홈쇼핑 채널별 화법 비교</title>
<style>
:root{--tx:#37352f;--tx2:rgba(55,53,47,.72);--tx3:rgba(55,53,47,.5);--line:#e9e9e7;--line2:#f1f1ef;--panel2:#f7f6f3;
  --accent:#2383e2;--hl-yellow:#fbf3db;--hl-blue:#e7f3f8;--hl-red:#fdebec}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--tx);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;
  font-family:Pretendard,ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI','Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:56px 24px 96px}
h1{font-size:32px;font-weight:700;margin:0 0 8px;letter-spacing:-.02em;line-height:1.25}
h1 a{font-size:14px;font-weight:500;color:var(--tx3);text-decoration:none;margin-left:10px;vertical-align:6px}
h1 a:hover{color:var(--accent)}
.lead{color:var(--tx2);margin:0 0 28px;max-width:820px}
input{background:#fff;border:1px solid var(--line);color:var(--tx);padding:10px 12px;border-radius:6px;font-size:15px;width:340px;
  font-family:inherit;outline:none;box-shadow:0 1px 2px rgba(15,15,15,.04)}
input:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(35,131,226,.15)}
input[type=checkbox]{width:auto;box-shadow:none;accent-color:var(--accent)}
button{background:var(--accent);color:#fff;border:0;padding:10px 18px;border-radius:6px;font-size:15px;font-weight:600;cursor:pointer;margin-left:8px;font-family:inherit}
button:hover{background:#1a6fc4}
button:disabled{background:var(--line2);color:var(--tx3);cursor:not-allowed}
.panel{border:1px solid var(--line);border-radius:8px;margin:12px 0;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14px;white-space:nowrap}
th{font-weight:500;color:var(--tx3);font-size:13px;background:var(--panel2)}
td,th{padding:10px 12px;border-bottom:1px solid var(--line2);text-align:left}
tbody tr:hover td{background:#fbfbfa}
tbody tr:last-child td{border-bottom:0}
td:first-child,th:first-child{width:38px;text-align:center}
td.num{text-align:right;font-variant-numeric:tabular-nums}
td.wx{white-space:nowrap;font-size:13px}
.exk{margin:8px 0 4px;font-size:13px;color:var(--tx2)}
.exk button{border:1px solid var(--line,#e3e2de);background:#fff;border-radius:999px;padding:3px 12px;margin:0 0 0 6px;font-size:13px;cursor:pointer;color:inherit}
.exk button:hover{background:#f1f1ef}
.sub{color:var(--tx3);font-size:13px}
#status{color:var(--tx2);margin:12px 0 4px;font-size:14px}
#bar{display:flex;align-items:center;gap:10px;margin:10px 0;flex-wrap:wrap}
#bar input:not([type=checkbox]){width:240px;font-size:14px;padding:8px 10px}
select{margin-left:8px;background:#fff;border:1px solid var(--line);color:var(--tx);padding:9px 10px;border-radius:6px;font-size:14px;font-family:inherit;outline:none}
.tag{font-size:12px;padding:1px 8px;border-radius:4px}
.tag.live{background:var(--hl-red);color:#9f2f2d}
.tag.tc{background:var(--hl-blue);color:#1f5f7f}
.src{display:inline-block;font-size:11px;padding:0 6px;border-radius:4px;background:var(--line2);color:var(--tx3);margin-left:6px;vertical-align:1px}
.pname{max-width:300px;overflow:hidden;text-overflow:ellipsis;color:var(--tx2);font-size:13px}
tr.upcoming td{opacity:.45}
.callout{background:var(--hl-yellow);border-radius:6px;padding:12px 16px;margin:12px 0;font-size:13.5px;color:var(--tx2)}
.callout b{color:var(--tx);font-weight:650}
</style></head>
<body><div class="wrap">
<h1>키워드로 방송 찾아 비교하기 <a href="/">← 주간 편성표</a></h1>
<p class="lead">검색에 걸린 방송을 최신순으로 전부 나열합니다. 상품명 필터로 같은 제품만 남긴 뒤 2개 이상 고르면 비교 리포트가 만들어지고, 채널이 많을수록(3개 이상) 어느 채널이 무엇을 밀었는지 더 뚜렷하게 갈립니다.</p>
<form id="f"><input id="kw" placeholder="__KW_PLACEHOLDER__" required>
<select id="weeks" title="기간을 넓힐수록 홈쇼핑모아 호출이 늘어납니다(1 + 주 수)">
<option value="0" selected>기본 (호출 1회)</option><option value="2">+최근 2주 (호출 3회)</option>
<option value="4">+최근 4주 (호출 5회)</option><option value="8">+최근 8주 (호출 9회)</option></select>
<button type="submit">검색</button></form>
<div class="exk">__KW_CHIPS__</div>
<div id="status"></div>
<div id="bar" style="display:none">
  <input id="nameFilter" placeholder="상품명 필터 (예: 패키지, 18박스)">
  <label class="sub"><input type="checkbox" id="subOnly" checked> 방영 전 제외</label>
  <select id="typeFilter">
    <option value="">전체</option><option value="라이브">라이브만</option><option value="T커머스">T커머스만</option>
  </select>
  <span id="selCount" class="sub"></span>
  <button id="cmp" disabled>선택한 방송 비교</button>
</div>
<div id="out"></div>
</div>
<form id="cmpForm" method="POST" action="/api/compare" target="_blank" style="display:none">
  <input type="hidden" name="items" id="cmpItems">
  <input type="hidden" name="keyword" id="cmpKeyword">
</form>
<script>
const f = document.getElementById('f');
const out = document.getElementById('out');
const status = document.getElementById('status');
const bar = document.getElementById('bar');
const cmpBtn = document.getElementById('cmp');
const selCount = document.getElementById('selCount');
let lastItems = [];
let currentKeyword = '';

const typeFilter = document.getElementById('typeFilter');
const nameFilter = document.getElementById('nameFilter');
const squash = s => (s || '').replace(/\\s+/g, '').toUpperCase();
function applyFilter() {
  const t = typeFilter.value;
  const words = nameFilter.value.trim().split(/\\s+/).filter(Boolean).map(squash);
  let shown = 0;
  out.querySelectorAll('tbody tr').forEach(tr => {
    const name = squash(lastItems[+tr.dataset.i].product_name);
    const it = lastItems[+tr.dataset.i];
    const show = (!t || tr.dataset.type === t) && words.every(w => name.includes(w))
      && (!subOnly.checked || !it.upcoming);
    if (show) shown++;
    tr.style.display = show ? '' : 'none';
    if (!show) tr.querySelector('input.sel').checked = false;
  });
  if (lastItems.length) status.textContent = '검색 ' + lastItems.length + '건 · 표시 ' + shown + '건';
  updateBar();
}
typeFilter.addEventListener('change', applyFilter);
nameFilter.addEventListener('input', applyFilter);
const subOnly = document.getElementById('subOnly');
subOnly.addEventListener('change', applyFilter);

function updateBar() {
  const n = out.querySelectorAll('input.sel:checked').length;
  selCount.textContent = n + '개 선택';
  cmpBtn.disabled = n < 2;
}

document.querySelectorAll('.exk button').forEach(b => b.addEventListener('click', () => {
  document.getElementById('kw').value = b.dataset.k; f.requestSubmit();
}));
f.addEventListener('submit', async (e) => {
  e.preventDefault();
  const kw = document.getElementById('kw').value.trim();
  if (!kw) return;
  currentKeyword = kw;
  out.innerHTML = '';
  bar.style.display = 'none';
  status.textContent = '검색 중...';
  try {
    const res = await fetch('/api/search?keyword=' + encodeURIComponent(kw) + '&weeks=' + document.getElementById('weeks').value);
    const data = await res.json();
    if (!res.ok) { status.textContent = '오류: ' + data.error; return; }
    lastItems = data.broadcasts;
    if (!lastItems.length) { status.textContent = '결과 없음'; return; }
    const esc = s => (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
    const rows = lastItems.map((b, i) => `<tr data-i="${i}" data-type="${b.broadcast_type || ''}"${b.upcoming || b.has_subtitle === false || b.subtitle_opened === false ? ' class="upcoming"' : ''}>
      <td><input type="checkbox" class="sel" data-i="${i}"${b.upcoming ? ' disabled title="방영 전이라 자막이 없습니다"' : b.has_subtitle === false ? ' disabled title="홈쇼핑모아에 이 방송 자막이 없습니다"' : b.subtitle_opened === false ? ' disabled title="홈쇼핑모아에서 이 방송 자막을 열어야 합니다"' : ''}></td>
      <td>${(b.start_datetime || '').replace('T',' ')}</td>
      <td><span class="tag ${b.broadcast_type === '라이브' ? 'live' : 'tc'}">${b.broadcast_type || ''}</span></td>
      <td>${b.channel_name}${b.has_subtitle === false ? ' <span class="sub">· 자막 없음</span>' : b.subtitle_opened === false ? ' <span class="sub">· 🔒 자막 잠김</span>' : ''}</td>
      <td>${b.duration_min ?? ''}분</td>
      <td class="pname" title="${esc(b.product_name)}">${esc(b.product_name)}</td>
      <td class="num">${b.upcoming ? '<span class="sub">방영 예정</span>' : b.revenue != null ? b.revenue.toLocaleString() + '원<span class="src">' + esc(b.revenue_source || '') + '</span>' : '<span class="sub">–</span>'}</td>
      <td class="num">${b.revenue_per_weighted_min != null ? b.revenue_per_weighted_min.toLocaleString() + '원' : '<span class="sub">–</span>'}</td>
      <td class="wx">${b.weather ? esc(b.weather.name) + '<span class="sub"> ' + b.weather.hi.toFixed(1) + '° / ' + b.weather.lo.toFixed(1) + '°</span>' : '<span class="sub">–</span>'}</td>
      <td class="num">${b.weather ? (b.weather.rain > 0 ? '<b>' + b.weather.rain.toFixed(1) + 'mm</b>' : '0mm') : '<span class="sub">–</span>'}</td>
    </tr>`).join('');
    const srcs = [...new Set(lastItems.filter(b => b.revenue != null).map(b => b.revenue_source))];
    const notes = {'라방바': '<b>라방바 추정치</b>입니다 — 실제 매출과 다르며 부정확합니다. 사·방송 간 상대 비교와 추세 참고용으로만 보세요. 라방바에 없는 방송(T커머스 등)은 비워 둡니다.',
                   '홈쇼핑모아': '<b>홈쇼핑모아 편성 추정치</b>입니다 — 실제 매출과 다릅니다.'};
    const callout = srcs.length ? '<div class="callout">편성 매출은 ' + srcs.map(s => notes[s] || esc(s)).join(' / ') + '</div>' : '';
    out.innerHTML = callout + `<div class="panel"><table>
      <thead><tr><th></th><th>방송 시작</th><th>구분</th><th>홈쇼핑사</th><th>편성</th><th>상품명</th><th>편성 추정 매출</th>
      <th title="편성 추정 매출 ÷ 가중분(시간대 수요 가중)">분당주문액</th>
      <th title="기상청 서울 관측 · 일 단위(같은 날 방송은 같은 값) · 최고/최저기온">날씨</th><th title="기상청 서울 관측 · 일 강수량">강수량</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
    bar.style.display = '';
    applyFilter();
    out.querySelectorAll('input.sel').forEach(cb => cb.addEventListener('change', updateBar));
  } catch (err) {
    status.textContent = '오류: ' + err;
  }
});

cmpBtn.addEventListener('click', () => {
  const picked = [...out.querySelectorAll('input.sel:checked')].map(cb => lastItems[+cb.dataset.i]);
  if (picked.length < 2) return;
  document.getElementById('cmpItems').value = JSON.stringify(picked);
  document.getElementById('cmpKeyword').value = currentKeyword;
  document.getElementById('cmpForm').submit();
});
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    client: DataHubClient  # set by run()

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj) -> None:
        self._send(200, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send_error(self, e: Exception, *, as_json: bool) -> None:
        msg = str(e)
        if as_json:
            self._send(500, json.dumps({"error": msg}, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        else:
            self._send(500, f"<pre>{html.escape(msg)}</pre>".encode("utf-8"), "text/html; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        qs = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        as_json = parsed.path.startswith("/api/")
        try:
            if parsed.path in ("/", "/compare"):
                # 시작 화면: 자막 업로드 → 비교 리포트(크롤링 없이 쓰는 정식 경로)
                with open(COMPARE_HTML_PATH, encoding="utf-8") as f:
                    self._send(200, f.read().encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path.startswith("/report/"):
                name = os.path.basename(urllib.parse.unquote(parsed.path[len("/report/"):]))
                path = os.path.join(REPORT_DIR, name)
                if not name.endswith(".html") or not os.path.isfile(path):
                    self._send(404, "리포트를 찾을 수 없습니다".encode("utf-8"), "text/plain; charset=utf-8")
                    return
                with open(path, encoding="utf-8") as f:
                    self._send(200, with_back_button(f.read()).encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/split":
                # 두 리포트를 좌우로 나란히(예: 1안 키워드 집계 | 2안 정독 분석)
                # 주소에 리포트 이름이 없거나 틀리면 가장 최근 1안·2안을 자동으로 고른다
                os.makedirs(REPORT_DIR, exist_ok=True)
                names = sorted((n for n in os.listdir(REPORT_DIR) if n.endswith(".html")), reverse=True)

                def _pick(want: str, second: bool) -> str:
                    want = os.path.basename(want or "")
                    if want in names:
                        return want
                    pool = [n for n in names if ("2안" in n) == second]
                    return pool[0] if pool else ""

                left = urllib.parse.quote(_pick(qs.get("l", ""), False))
                right = urllib.parse.quote(_pick(qs.get("r", ""), True))
                page = f"""<!doctype html><meta charset="utf-8"><title>1안 · 2안 비교</title>
<style>html,body{{margin:0;height:100%;font-family:Pretendard,'Malgun Gothic',sans-serif;background:#f7f6f3}}
.top{{display:grid;grid-template-columns:1fr 1fr;height:34px;border-bottom:1px solid #e9e9e7;background:#fff}}
.top div{{padding:7px 14px;font-size:13px;font-weight:650;color:#37352f}}.top div+div{{border-left:1px solid #e9e9e7}}
.top span{{font-weight:400;color:rgba(55,53,47,.5);margin-left:6px}}
.panes{{display:grid;grid-template-columns:1fr 1fr;height:calc(100% - 35px)}}
iframe{{width:100%;height:100%;border:0;background:#fff}}iframe+iframe{{border-left:1px solid #e9e9e7}}</style>
<div class="top"><div>1안 · 키워드 집계<span>같은 기준으로 자동 계산</span></div><div>2안 · 자막 정독 분석<span>흐름·강조점·설득 기법 해석</span></div></div>
<div class="panes"><iframe src="/report/{left}"></iframe><iframe src="/report/{right}"></iframe></div>"""
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/reports":
                os.makedirs(REPORT_DIR, exist_ok=True)
                names = sorted((n for n in os.listdir(REPORT_DIR) if n.endswith(".html")), reverse=True)
                rows = "".join(f'<li><a href="/report/{urllib.parse.quote(n)}">{html.escape(n[:-5])}</a></li>' for n in names)
                page = ('<!doctype html><meta charset="utf-8"><title>지난 리포트</title>'
                        '<body style="font-family:Malgun Gothic,sans-serif;padding:20px;background:#f7f8fa">'
                        f'<h2>지난 비교 리포트</h2><p><a href="/">← 방송 비교</a> · <a href="/split">최근 1안·2안 나란히 보기</a></p><ul>{rows or "<li>아직 없습니다</li>"}</ul>')
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/weekly":
                with open(WEEKLY_HTML_PATH, encoding="utf-8") as f:
                    self._send(200, f.read().encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/search":
                # 검색 예시 = 지금 조회할 수 있는 보관함 상품만(폴더를 추가하면 자동으로 늘어난다)
                kws = library.searchable_keywords()
                chips = ("조회 가능 " + "".join(
                    f'<button type="button" data-k="{html.escape(k)}">{html.escape(k)}</button>' for k in kws)) if kws else ""
                page = (INDEX_HTML.replace("__KW_PLACEHOLDER__", "예: " + ", ".join(kws) if kws else "상품명 키워드")
                        .replace("__KW_CHIPS__", chips))
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/api/week":
                today = datetime.now(KST).date()
                start = qs.get("start") or today.isoformat()
                day = date.fromisoformat(start)
                monday = day - timedelta(days=day.weekday())
                # 홈쇼핑모아 직접 호출이 꺼져 있으면(기본) 아침 수집 파일로 만든다
                week = (build_week(self.client, monday) if self.client.cfg.network_enabled
                        else build_week_local(monday))
                week["usage"] = self.client.guard.status()
                self._send_json(week)
            elif parsed.path == "/api/search":
                keyword = qs.get("keyword", "").strip()
                if not keyword:
                    self._send(400, b'{"error":"keyword required"}', "application/json")
                    return
                weeks = int((urllib.parse.parse_qs(parsed.query).get("weeks") or ["0"])[0])
                out = None if self.client.cfg.network_enabled else search_library(keyword)
                if out is None:
                    out = search_broadcasts(self.client, keyword, weeks=max(0, min(weeks, 8)))
                out["usage"] = self.client.guard.status()
                self._send_json(out)
            else:
                self._send(404, b"not found", "text/plain")
        except DataHubError as e:
            self._send_error(e, as_json=as_json)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._send_error(e, as_json=as_json)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/compare-text":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                form = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
                payload = json.loads(form.get("payload", "{}"))
                html_out = build_text_compare_html(payload)
                name = save_report(html_out, payload.get("keyword") or "report")
                # 저장한 리포트 주소로 보낸다 — 새로고침해도 다시 만들지 않고, 주소를 공유할 수 있다
                self.send_response(303)
                self.send_header("Location", "/report/" + urllib.parse.quote(name))
                self.end_headers()
            elif parsed.path == "/api/compare":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                form = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
                items = json.loads(form.get("items", "[]"))
                keyword = form.get("keyword", "")
                if items and all(it.get("local_file") for it in items):
                    html_out = build_library_compare_html(items=items, keyword=keyword)
                    name = save_report(html_out, keyword or "report")
                    self.send_response(303)
                    self.send_header("Location", "/report/" + urllib.parse.quote(name))
                    self.end_headers()
                    return
                html_out = build_compare_html(self.client, items=items, keyword=keyword)
                self._send(200, html_out.encode("utf-8"), "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")
        except DataHubError as e:
            self._send_error(e, as_json=False)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._send_error(e, as_json=False)

    def log_message(self, fmt: str, *args) -> None:  # 조용히
        sys.stderr.write("[webapp] " + (fmt % args) + "\n")


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    client = DataHubClient()
    Handler.client = client
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"hsbot webapp: http://{host}:{port}  (Ctrl+C로 종료)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run(port=int(os.environ.get("PORT", "8765")))
