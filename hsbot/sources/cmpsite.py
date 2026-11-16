"""사내 '아이템 편성 비교 · 당사 vs 경쟁사' 페이지의 편성 실적 — 2026-11-16부터 매출 기본 출처.

페이지: 사내 전용 주소를 환경변수 HSBOT_CMPSITE_URL 로 넣는다(코드에는 적지 않음). 데이터가 HTML 안에 CMP_DATA 로 들어 있음
  원천: smus_broadcast_programming_assistant.__dpa_cmpco_pgm_sales_info (라방바와 같은 테이블)
  prog : '날짜i|채널i|시작분|종료분|방송명i|방송ID|방송취급액(천원)|방송가중노출분(0.1분)' 을 '~' 로 이은 문자열
  rows : 아이템별 상품행 '방송i|상품i|브랜드i|중분류i|소분류i|판매가|가중노출분|취급액|판매수량'
  wthr : 날짜 → [최고기온, 최저기온, 강수mm, 날씨명] (기상청 서울 관측, 일 단위)
  기간 : 최근 90일

기존 라방바 파일과 매출(취급액)은 같고, 가중분은 원천이 계산한 값(가중노출분)을 그대로 쓴다.
라방바 수집 추정치라 실제 매출과 다르다. 사·방송 간 상대 비교용으로만 쓴다.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta

URL = os.environ.get("HSBOT_CMPSITE_URL", "")  # 사내망 주소. 비어 있으면 받지 않고 캐시만 쓴다
CACHE = os.path.join(".cache", "cmpsite_prog.json")
MAX_AGE_SEC = 12 * 3600
SOURCE_NOTE = ("매출·가중분은 사내 ‘아이템 편성 비교’(라방바 원천) 기준 추정치입니다 — 실제 매출과 다르며, "
               "사·방송 간 상대 비교용입니다. 날씨는 기상청 서울 관측(일 단위)입니다.")

# 사이트 채널 코드 → 우리 채널 코드(라이브만)
CH = {"GS": "gsshop", "HD": "hmall", "LT": "lotteimall", "CJ": "cjmall"}

_index: dict | None = None
_loaded_at = 0.0


def _download() -> dict:
    """페이지를 받아 CMP_DATA 에서 편성(prog)·판매수량·날씨만 추려 둔다."""
    if not URL:
        raise RuntimeError("HSBOT_CMPSITE_URL 이 설정되지 않았습니다")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 사내 주소: 프록시 안 거침
    with opener.open(URL, timeout=90) as resp:
        page = resp.read().decode("utf-8")
    i = page.index("CMP_DATA")
    data, _ = json.JSONDecoder().raw_decode(page[page.index("{", i):])
    dates, chs = data["dates"], data["ch"]
    prog = []
    for t in data["prog"].split("~"):
        p = t.split("|")
        prog.append([dates[int(p[0])], chs[int(p[1])], int(p[2]), int(p[3]), p[5],
                     round(float(p[6]) * 1000) if p[6] else None, float(p[7]) / 10 if p[7] else None, 0])
    for r in data["rows"]:  # 판매수량은 상품행에만 있어 방송별로 더한다
        for t in r.split("~"):
            p = t.split("|")
            if p[8]:
                prog[int(p[0])][7] += round(float(p[8]))
    return {"gen": data.get("gen"), "prog": prog, "wthr": data.get("wthr", {})}


def _load() -> dict:
    global _index, _loaded_at
    if _index is not None and time.time() - _loaded_at < MAX_AGE_SEC:
        return _index
    data = None
    if os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < MAX_AGE_SEC:
        with open(CACHE, encoding="utf-8") as f:
            data = json.load(f)
    if data is None:
        try:
            data = _download()
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:  # noqa: BLE001 — 사내망 밖이면 못 받는다. 오래된 캐시라도 쓴다.
            if not os.path.exists(CACHE):
                _index, _loaded_at = {"idx": {}, "wthr": {}}, time.time()
                return _index
            with open(CACHE, encoding="utf-8") as f:
                data = json.load(f)
    idx: dict[tuple[str, str], list] = {}
    for d, ch, s, e, pid, amt, wmin, qty in data["prog"]:
        c = CH.get(ch)
        if c:
            idx.setdefault((c, f"{d[:4]}-{d[4:6]}-{d[6:]}"), []).append((s, e, pid, amt, wmin, qty))
    _index, _loaded_at = {"idx": idx, "wthr": data.get("wthr", {})}, time.time()
    return _index


def weather(day_iso: str) -> dict | None:
    w = _load()["wthr"].get(day_iso[:10].replace("-", ""))
    if not w:
        return None
    hi, lo, rain, name = w
    return {"hi": hi, "lo": lo, "rain": rain, "name": name}


def lookup(channel: str, start_datetime: str, tolerance_min: int = 10) -> dict | None:
    """채널·시작시각으로 편성 1건(시작 ±tolerance_min). 매출·원천 가중분·판매수량·실제 편성 시각·날씨."""
    if channel not in CH.values() or not start_datetime:
        return None
    s = datetime.fromisoformat(start_datetime[:19])
    sm = s.hour * 60 + s.minute
    best = None
    for row in _load()["idx"].get((channel, s.date().isoformat()), []):
        gap = abs(row[0] - sm)
        if gap <= tolerance_min and (best is None or gap < abs(best[0] - sm)):
            best = row
    if not best or best[3] is None:
        return None
    ps_, pe_, pid, amt, wmin, qty = best
    day = datetime(s.year, s.month, s.day)
    ps = day + timedelta(minutes=ps_)
    pe = day + timedelta(minutes=pe_)
    if pe <= ps:
        pe += timedelta(days=1)
    return {"revenue": amt, "weighted_min": wmin, "sales_count": qty or None, "broadcast_id": pid,
            "start": ps.isoformat(), "end": pe.isoformat(), "weather": weather(s.date().isoformat())}
