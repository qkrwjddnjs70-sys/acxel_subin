"""라방바 편성 실적 — 사내 '경쟁사 편성 분석' 페이지의 데이터 파일에서 방송별 판매금액을 찾는다.

데이터: 사내 주소를 환경변수 HSBOT_LABANGBA_URL 로 넣는다(코드에는 적지 않음). 하루 한 번 갱신
  window.CMPCO_SALES = {"meta":…, "gz": base64(gzip(JSON))}
  JSON.pg  : 편성 [ch, dt(YYYYMMDD), 시작 'HH:MM', 종료 'HH:MM', pgm, sh, 편성 판매금액, 판매건수]
  JSON.d.ch: ["CJ","GS","HD","LT"] — 라이브 4개사만 있다(T커머스 없음)

라방바 수집 추정치라 실제 매출과 다르다(GS도 자사 원장과 다름). 사·방송 간 상대 비교용으로만 쓴다.
파일은 9MB 남짓이라 .cache/labangba_sales.json 에 풀어 두고 하루 지나면 다시 받는다.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta

URL = os.environ.get("HSBOT_LABANGBA_URL", "")  # 사내망 주소. 비어 있으면 받지 않고 캐시만 쓴다
CACHE = os.path.join(".cache", "labangba_sales.json")
MAX_AGE_SEC = 12 * 3600
SOURCE_NOTE = "매출은 라방바 추정치입니다 — 실제 매출과 다르며, 사·방송 간 상대 비교용입니다."

# 라방바 사 코드 → 우리 채널 코드(라이브만)
CH = {"CJ": "cjmall", "GS": "gsshop", "HD": "hmall", "LT": "lotteimall"}

_index: dict[tuple[str, str], list[dict]] | None = None
_loaded_at = 0.0


def _download() -> dict:
    if not URL:
        raise RuntimeError("HSBOT_LABANGBA_URL 이 설정되지 않았습니다")
    # 사내 주소라 회사 프록시를 거치지 않는다
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(URL, timeout=60) as resp:
        js = resp.read().decode("utf-8")
    obj = json.loads(js[js.index("{"):js.rindex("}") + 1])
    return json.loads(gzip.decompress(base64.b64decode(obj["gz"])).decode("utf-8"))


def _load() -> dict[tuple[str, str], list[dict]]:
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
                json.dump({"pg": data["pg"], "d": {"ch": data["d"]["ch"]}, "meta": data.get("meta")}, f)
        except Exception:  # noqa: BLE001 — 사내망 밖이면 못 받는다. 오래된 캐시라도 쓴다.
            if not os.path.exists(CACHE):
                _index, _loaded_at = {}, time.time()
                return _index
            with open(CACHE, encoding="utf-8") as f:
                data = json.load(f)
    idx: dict[tuple[str, str], list[dict]] = {}
    chs = data["d"]["ch"]
    for ch_i, dt, start, end, _pgm, _sh, amt, cnt in data["pg"]:
        ch = CH.get(chs[ch_i])
        if not ch:
            continue
        d = str(dt)
        idx.setdefault((ch, f"{d[:4]}-{d[4:6]}-{d[6:]}"), []).append(
            {"start": start, "end": end, "revenue": amt, "sales_count": cnt})
    _index, _loaded_at = idx, time.time()
    return idx


def lookup(channel: str, start_datetime: str, tolerance_min: int = 10) -> dict | None:
    """채널·시작시각으로 라방바 편성 1건. 시작이 ±tolerance_min 안이면 같은 편성으로 본다.

    돌려주는 start/end 는 라방바 기준 실제 편성 시각(ISO, 시간대 표기 없음)이다.
    """
    ch = {"gsmyshop": None}.get(channel, channel)
    if ch not in CH.values() or not start_datetime:
        return None
    s = datetime.fromisoformat(start_datetime[:19])
    best, best_gap = None, None
    for p in _load().get((ch, s.date().isoformat()), []):
        ps = datetime.fromisoformat(f"{s.date().isoformat()}T{p['start']}:00")
        gap = abs((ps - s).total_seconds()) / 60
        if gap <= tolerance_min and (best_gap is None or gap < best_gap):
            best, best_gap = p, gap
    if not best or best["revenue"] is None:
        return None
    ps = datetime.fromisoformat(f"{s.date().isoformat()}T{best['start']}:00")
    pe = datetime.fromisoformat(f"{s.date().isoformat()}T{best['end']}:00")
    if pe <= ps:  # 자정을 넘기는 편성
        pe += timedelta(days=1)
    return {"revenue": best["revenue"], "sales_count": best["sales_count"],
            "start": ps.isoformat(), "end": pe.isoformat()}
