"""시간대별 가중치 — 모든 '분'이 똑같은 분당 매출 가치를 갖지 않는다.

요일×분(1,440개) 가중치 표를 채널 종류별로 따로 쓴다 — 라이브와 T커머스는 시청 패턴이
달라 같은 시각이라도 가치가 다르다(예: 토 22:00 라이브 2.08 vs T커머스 1.37).
  · 라이브(홈쇼핑):  `시간대별 가중치 등록.xlsx`(2026-08)      → data/time_weights.json
  · T커머스:         `시간대별 가중치 등록_티컴.xlsx`(2026-10) → data/time_weights_tcommerce.json 가중치는 그 분의 평균적 주문
전환력을 100%(=1.0) 기준 상대값으로 나타낸다. 예: 일요일 01:25는 26.4% →
그 1분은 '평균적인 분' 대비 약 15.8초(=60초×0.264)어치 가치만 가진다.

그래서 방송 매출을 '분당'으로 나눌 때 그냥 방송 길이(분)로 나누면, 새벽
방송은 원래 수요가 적어서 매출이 낮은 건데 '효율이 나쁘다'로 잘못 읽힌다.
방송이 실제로 걸쳐 있던 시간대의 가중치를 합산한 '가중 분(weighted
minutes)'으로 나눠야 시간대가 달라도 공정하게 비교된다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_DAYS = ["월", "화", "수", "목", "금", "토", "일"]  # datetime.weekday(): 0=월 ... 6=일

# DataHub /next-api/schedule 의 tv_channel_type 기준(2026-10 확인): homeshopping=라이브,
# tcommerce2=T커머스. 목록에 없는 채널은 T커머스로 본다(라이브 홈쇼핑사는 이 8개로 고정).
LIVE_CHANNELS = {"gsshop", "cjmall", "lotteimall", "lotte", "hmall", "nsmall", "hnsmall", "immall"}


def _load(name: str) -> dict[str, dict[str, float]]:
    with open(os.path.join(_DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


_TABLES: dict[str, dict[str, dict[str, float]]] = {
    "live": _load("time_weights.json"),
    "tcommerce": _load("time_weights_tcommerce.json"),
}


def channel_kind(channel: str | None) -> str:
    """채널 코드 → 'live' | 'tcommerce'. 채널을 모르면(None) 기존 동작대로 라이브 표를 쓴다."""
    if not channel:
        return "live"
    return "live" if channel in LIVE_CHANNELS else "tcommerce"


def weight_at(dt: datetime, kind: str = "live") -> float:
    """특정 시각이 속한 1분의 가중치. 표에 없는 시각이면 평균(1.0)으로 본다."""
    hhmm = dt.strftime("%H%M")
    day = _DAYS[dt.weekday()]
    row = _TABLES[kind].get(hhmm)
    return row.get(day, 1.0) if row else 1.0


def weighted_minutes(start: datetime, end: datetime, kind: str = "live") -> float:
    """[start, end) 구간을 1분 단위로 쪼개 가중치를 합산한다(=가중 분).

    분 경계가 아닌 시각(초 단위)에서 시작/끝나도, 겹치는 비율만큼만
    그 분의 가중치를 더해서 왜곡 없이 처리한다. 자정·요일이 바뀌는
    방송(심야~익일)도 분 단위로 순회하므로 자동으로 맞게 처리된다.
    """
    if end <= start:
        return 0.0
    total = 0.0
    cur = start.replace(second=0, microsecond=0)
    while cur < end:
        nxt = cur + timedelta(minutes=1)
        overlap = (min(nxt, end) - max(cur, start)).total_seconds()
        if overlap > 0:
            total += weight_at(cur, kind) * (overlap / 60.0)
        cur = nxt
    return total


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=KST)


def weighted_minutes_from_iso(start_iso: str, end_iso: str, channel: str | None = None) -> float | None:
    """ISO8601 문자열(타임존 없으면 KST로 간주) 두 개로 가중 분을 구한다.

    channel 을 주면 그 채널 종류(라이브/T커머스)의 가중치 표를 쓴다.
    """
    start, end = _parse_dt(start_iso), _parse_dt(end_iso)
    if start is None or end is None:
        return None
    return weighted_minutes(start, end, channel_kind(channel))
