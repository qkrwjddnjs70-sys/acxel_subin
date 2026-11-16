"""방송 보관함 — 미리 받아 둔 자막 파일을 키워드 검색처럼 꺼내 쓴다.

데이터허브 직접 호출이 꺼져 있을 때(network_enabled=false) /search 화면이 이 보관함을 본다.
폴더 하나가 검색 키워드 하나다:

    demo_library/
      다이슨/
        260107_1435_GS_다이슨 디지털 슬림 무선청소기.txt
        260217_2255_GS_다이슨 디지털 슬림 무선청소기.txt
        260621_1230_현대_다이슨 디지털 슬림 무선청소기.txt
        방송정보.csv          ← 선택: 파일,시작,편성분,매출[,매출출처,판매가] (엑셀로 열어 고치면 된다)
                                 매출을 비우면 라방바(사내 편성 실적)에서 채운다
        리포트.html           ← 선택: 리포트_대상.txt 의 방송(없으면 전부)을 골라 비교하면 이 리포트를 보여준다

자막 파일은 데이터허브 자막 탭을 그대로 복사한 텍스트(또는 '시각 문장' 줄)다 — datahub_copy 가 읽는다.
방송 상세 화면을 Ctrl+A 로 통째로 복사했으면 채널·날짜·편성 시각·상품명·가격을 화면에서 읽으므로
파일명은 아무렇게나 지어도 된다. 그렇지 않으면 파일명 YYMMDD[_HHMM]_채널_상품명.txt 에서 읽고,
시각을 빼면 방송정보.csv 의 '시작'을 쓰고, 그것도 없으면 00:00.
"""
from __future__ import annotations

import csv
import os
import re
from datetime import datetime, timedelta

from ..models import KST, Broadcast
from .datahub_copy import channel_code, page_meta, parse_copy_text

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "demo_library")
INFO_CSV = "방송정보.csv"
REPORT_HTML = "리포트.html"
REPORT_TARGETS = "리포트_대상.txt"

_NAME = re.compile(r"^(\d{6}|\d{8})(?:[_\s-]+(\d{4}))?[_\s-]+([^_]+)[_\s-]+(.+)$")


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "").upper()


def searchable_keywords() -> list[str]:
    """검색 예시로 보여줄 보관함 키워드 — 비교할 수 있게 방송(자막 파일)이 2개 이상 든 폴더만."""
    if not os.path.isdir(ROOT):
        return []
    out = []
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name)
        if not os.path.isdir(path):
            continue
        real = [b for b in list_broadcasts(path)  # 빈 자막 파일(0바이트 등)은 빼고 센다
                if os.path.getsize(os.path.join(path, os.path.basename(b["local_file"]))) > 1000]
        if len(real) >= 2:
            out.append(name.split(",")[0].strip())
    return out


def find_folder(keyword: str) -> str | None:
    """키워드와 이름이 겹치는 보관함 폴더. '뼈엔 엠비피'처럼 여러 단어면 단어 하나만 겹쳐도 찾는다."""
    if not os.path.isdir(ROOT):
        return None
    tokens = [_squash(keyword)] + [_squash(t) for t in keyword.split() if len(_squash(t)) >= 2]
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name)
        if not os.path.isdir(path):
            continue
        aliases = [_squash(a) for a in name.split(",") if a.strip()]
        if any(t and (t in a or a in t) for t in tokens for a in aliases):
            return path
    return None


def _read_info(folder: str) -> dict[str, dict]:
    path = os.path.join(folder, INFO_CSV)
    if not os.path.exists(path):
        return {}
    for enc in ("utf-8-sig", "cp949"):  # 엑셀에서 저장하면 cp949일 수 있다
        try:
            with open(path, encoding=enc, newline="") as f:
                return {r["파일"].strip(): r for r in csv.DictReader(f) if (r.get("파일") or "").strip()}
        except (UnicodeDecodeError, KeyError):
            continue
    return {}


def _num(s) -> int | None:
    s = re.sub(r"[^\d]", "", str(s or ""))
    return int(s) if s else None


def list_broadcasts(folder: str) -> list[dict]:
    """폴더 안 자막 파일 → 검색 결과와 같은 모양의 방송 목록(최신순)."""
    info = _read_info(folder)
    out = []
    for fn in os.listdir(folder):
        if not fn.lower().endswith(".txt") or fn.startswith("리포트") and fn.endswith("_대상.txt"):
            continue
        m = _NAME.match(os.path.splitext(fn)[0])
        row = info.get(fn) or info.get(os.path.splitext(fn)[0]) or {}
        with open(os.path.join(folder, fn), encoding="utf-8-sig") as f:
            meta = page_meta(f.read())  # 데이터허브 화면 통째 복사본이면 채널·시각을 화면에서 읽는다
        price = None
        if meta:
            channel, product, price = meta["channel"], meta["product_name"], meta["price"]
            start = meta["start_datetime"] + "+09:00"
            if not _num(row.get("편성분")):
                row = {**row, "편성분": str(round((datetime.fromisoformat(meta["end_datetime"]) -
                                                 datetime.fromisoformat(meta["start_datetime"])).total_seconds() / 60))}
        elif m:
            d = m.group(1) if len(m.group(1)) == 8 else "20" + m.group(1)
            hhmm = m.group(2) or "0000"
            channel, product = channel_code(m.group(3)), m.group(4).strip()
            start = f"{d[:4]}-{d[4:6]}-{d[6:8]}T{hhmm[:2]}:{hhmm[2:]}:00+09:00"
        else:
            channel, product, start = "unknown", os.path.splitext(fn)[0], "2000-01-01T00:00:00+09:00"
        if (row.get("시작") or "").strip():
            dt = datetime.fromisoformat(row["시작"].strip().replace(" ", "T"))
            start = (dt if dt.tzinfo else dt.replace(tzinfo=KST)).isoformat()
        if _num(row.get("판매가")):  # 화면 대표가가 기본 구성 가격일 때 주력 구성 가격으로 바꾼다
            price = _num(row.get("판매가"))
        dur = _num(row.get("편성분")) or 60
        # 데이터허브 검색 결과처럼 시간대 표기 없이 'YYYY-MM-DDTHH:MM:SS'(KST)로 둔다
        start_dt = datetime.fromisoformat(start).astimezone(KST).replace(tzinfo=None)
        start, end = start_dt.isoformat(), (start_dt + timedelta(minutes=dur)).isoformat()
        out.append({
            "channel": channel,
            "product_key": f"local:{fn}",
            "product_name": product,
            "start_datetime": start,
            "end_datetime": end,
            "duration_min": dur,
            "price": price,
            "revenue": _num(row.get("매출")),
            # 방송정보.csv 에 직접 적은 매출은 그 출처를 따른다(기본: 홈쇼핑모아 추정). 비우면 라방바로 채운다.
            "revenue_source": ((row.get("매출출처") or "홈쇼핑모아").strip()
                               if _num(row.get("매출")) is not None else None),
            "local_file": fn,
        })
    out.sort(key=lambda b: b["start_datetime"], reverse=True)
    return out


def load(folder: str, item: dict) -> Broadcast:
    fn = os.path.basename(item["local_file"])  # 폴더 밖 파일은 못 고르게
    with open(os.path.join(folder, fn), encoding="utf-8-sig") as f:
        text = f.read()
    bc = parse_copy_text(
        text, channel=item["channel"], product_name=item.get("product_name") or "",
        start_datetime=item["start_datetime"], end_datetime=item.get("end_datetime"),
        broadcast_id=f"local:{fn}", price=item.get("price"),
    )
    bc.extra["revenue"] = item.get("revenue")
    bc.extra["weighted_min"] = item.get("weighted_min")
    bc.extra["source_file"] = fn
    return bc


def prebuilt_report(folder: str, picked_files: list[str]) -> str | None:
    name = prebuilt_report_name(folder, picked_files)
    if not name:
        return None
    with open(os.path.join(folder, name), encoding="utf-8") as f:
        return f.read()


def prebuilt_2an(folder: str, report_name: str) -> str | None:
    """미리 만든 1안(리포트*.html)과 짝인 2안(소구 문맥 분류) HTML. 리포트_CJ.html ↔ 2안_CJ.html."""
    path = os.path.join(folder, "2안" + report_name[len("리포트"):])
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def prebuilt_report_name(folder: str, picked_files: list[str]) -> str | None:
    """미리 만든 리포트가 있고, 고른 방송이 그 리포트의 대상과 같으면 그 HTML.

    리포트.html ↔ 리포트_대상.txt, 리포트_XX.html ↔ 리포트_XX_대상.txt 처럼 여러 짝을 둘 수 있다
    (대상 파일은 한 줄에 자막 파일명 하나). 리포트.html 만 대상 파일이 없으면 폴더의 자막 파일 전부.
    """
    picked = set(picked_files)
    for fn in sorted(os.listdir(folder)):
        if not (fn.startswith("리포트") and fn.endswith(".html")):
            continue
        target_path = os.path.join(folder, fn[:-5] + "_대상.txt")
        if os.path.exists(target_path):
            with open(target_path, encoding="utf-8-sig") as f:
                targets = {ln.strip() for ln in f if ln.strip()}
        elif fn == REPORT_HTML:
            targets = {b["local_file"] for b in list_broadcasts(folder)}
        else:
            continue
        if picked == targets:
            return fn
    return None
