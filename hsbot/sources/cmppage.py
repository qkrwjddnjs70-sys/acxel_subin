"""사내 '아이템 편성 비교 · 당사 vs 경쟁사' 페이지를 우리 앱의 시작 화면으로 쓴다 (2026-11-19).

- 페이지 주소는 환경변수 HSBOT_CMPPAGE_URL 로만 받는다(코드에는 적지 않음). 비어 있으면 받지 않고 캐시만 쓴다.
- 페이지가 22MB 라 받는 데 2분쯤 걸린다 → 로컬 캐시(.cache/cmppage.html)를 즉시 보여 주고,
  12시간이 지나면 백그라운드에서 새로 받아 바꾼다(요청을 막지 않음).
- 보여 주기 전에 페이지를 이렇게 고친다(원본 파일은 건드리지 않음):
    1) '자막 있음' 표시 = 우리 방송 보관함(demo_library)에 실제로 있는 방송
    2) 비교 버튼(멘트 분석 →) 하나로 줄이고, 누르면 우리 앱 /from-cmp 로 이동
    3) 선택 한도 2 → 3 (세포랩은 3사 비교)
- 비교 버튼이 넘기는 값: 채널:날짜(YYYYMMDD):시작분:방송ID 를 쉼표로 이은 picks.
  resolve() 가 이를 보관함 방송(채널·날짜·시작 ±10분)에 맞춘다.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys
import threading
import time
import urllib.request

from . import cmpsite, library

URL = os.environ.get("HSBOT_CMPPAGE_URL", "")
CACHE = os.path.join(".cache", "cmppage.html")
MAX_AGE_SEC = 12 * 3600

_lock = threading.Lock()
_refreshing = False
_memo: dict = {"key": None, "raw": None, "gz": None}


def _log(msg: str) -> None:
    sys.stderr.write(f"[cmppage] {msg}\n")


# ---------------------------------------------------------------- 캐시 받기
def cache_age() -> float | None:
    return time.time() - os.path.getmtime(CACHE) if os.path.exists(CACHE) else None


def is_refreshing() -> bool:
    return _refreshing


def _validate(html: str) -> str | None:
    """받은 페이지가 쓸 만한지 검사. 문제가 있으면 이유(문자열), 괜찮으면 None.

    2026-11-19 15:11 판에서 편성(prog) 목록에 3줄이 끼어들었는데 상품행이 가리키는 편성 번호는 그대로여서
    그 뒤 방송이 전부 3칸씩 밀려 보였다(세포랩 GS 10/5 21:45 → 18:35). 그런 판은 받지 않고 기존 캐시를 쓴다.
    검사: ① 편성 줄 형식(8칸) ② 보관함 방송의 편성이 실제로 어떤 상품행에서 참조되는지."""
    try:
        i = html.index("CMP_DATA")
        data, _ = json.JSONDecoder().raw_decode(html[html.index("{", i):])
        prog = [t.split("|") for t in data["prog"].split("~")]
        odd = sum(1 for g in prog if len(g) != 8)
        if odd:
            return f"편성 목록에 형식이 다른 줄 {odd}개(편성 번호가 밀렸을 수 있음)"
        used = set()
        for r in data["rows"]:
            for t in r.split("~"):
                k = t.split("|", 1)[0]
                if k.isdigit():
                    used.add(int(k))
        dates, chs = data["dates"], data["ch"]
        where = {}
        for n, g in enumerate(prog):
            try:
                where.setdefault((chs[int(g[1])], dates[int(g[0])]), []).append((int(g[2]), n))
            except (ValueError, IndexError):
                continue
        inv = {v: k for k, v in cmpsite.CH.items()}
        total = ok = 0
        for _name, b in library.all_broadcasts():
            sd = b["start_datetime"]
            key = (inv.get(b["channel"]), sd[:10].replace("-", ""))
            sm = int(sd[11:13]) * 60 + int(sd[14:16])
            cand = [n for s0, n in where.get(key, []) if abs(s0 - sm) <= 10]
            if not cand:
                continue
            total += 1
            ok += any(n in used for n in cand)
        if total and ok < total * 0.8:
            return f"보관함 방송 {total}건 중 {total - ok}건이 상품행과 연결되지 않음(편성 번호가 밀린 판)"
    except Exception as e:  # noqa: BLE001
        return f"페이지 데이터를 읽지 못함: {e}"
    return None


def _download() -> None:
    global _refreshing
    part = CACHE + ".part"
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 사내 주소: 프록시 안 거침
        t0 = time.time()
        with opener.open(URL, timeout=30) as resp, open(part, "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
        with open(part, "rb") as f:
            f.seek(-64, os.SEEK_END)
            tail = f.read()
        if b"</html>" not in tail:
            raise RuntimeError("받은 파일이 끝까지 오지 않았습니다")
        with open(part, encoding="utf-8") as f:
            bad = _validate(f.read())
        if bad:
            raise RuntimeError(f"새 판을 쓰지 않음 — {bad}. 기존 캐시를 그대로 씁니다")
        os.replace(part, CACHE)
        _log(f"캐시 갱신 완료 ({os.path.getsize(CACHE) / 1e6:.1f}MB, {time.time() - t0:.0f}초)")
    except Exception as e:  # noqa: BLE001 — 사내망 밖이거나 서버가 꺼져 있으면 지금 캐시를 그대로 쓴다
        _log(f"캐시 갱신 실패: {e}")
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
    finally:
        _refreshing = False


def refresh_async(force: bool = False) -> bool:
    """캐시가 없거나 낡았으면 백그라운드로 새로 받는다. 시작했으면 True."""
    global _refreshing
    if not URL:
        return False
    age = cache_age()
    if not force and age is not None and age < MAX_AGE_SEC:
        return False
    with _lock:
        if _refreshing:
            return False
        _refreshing = True
    threading.Thread(target=_download, daemon=True, name="cmppage-refresh").start()
    return True


# ---------------------------------------------------------------- 자막 있음 = 보관함
def _library_signature() -> tuple:
    sig = []
    if os.path.isdir(library.ROOT):
        for name in sorted(os.listdir(library.ROOT)):
            p = os.path.join(library.ROOT, name)
            if os.path.isdir(p):
                sig.append((name, tuple(sorted((f, int(os.path.getmtime(os.path.join(p, f))))
                                               for f in os.listdir(p) if f.lower().endswith(".txt")))))
    return tuple(sig)


def _prog_table(html: str) -> list[tuple[str, str, int, str]]:
    """페이지 데이터(CMP_DATA)의 편성표 → (채널코드, 날짜, 시작분, 방송ID)."""
    dec = json.JSONDecoder()

    def piece(key: str):
        i = html.index(f'"{key}":') + len(key) + 3
        return dec.raw_decode(html, i)[0]

    dates, chs, prog = piece("dates"), piece("ch"), piece("prog")
    out = []
    for t in prog.split("~"):
        p = t.split("|")
        try:
            out.append((chs[int(p[1])], dates[int(p[0])], int(p[2]), p[5]))
        except (ValueError, IndexError):
            continue
    return out


def _caption_keys(html: str) -> set[str]:
    """보관함 방송을 페이지의 편성(채널:방송ID)에 맞춘 집합."""
    inv = {v: k for k, v in cmpsite.CH.items()}
    want = []
    lib = library.all_broadcasts()
    n_by_folder: dict[str, int] = {}
    for name, _b in lib:
        n_by_folder[name] = n_by_folder.get(name, 0) + 1
    for name, b in lib:
        if n_by_folder[name] < 2:  # 방송이 1건뿐인 상품은 비교할 수 없으니 '자막 있음'으로 보이지 않게
            continue
        sd = b["start_datetime"]
        want.append((inv.get(b["channel"]), sd[:10].replace("-", ""), int(sd[11:13]) * 60 + int(sd[14:16])))
    keys = set()
    for ch, d, s, pid in _prog_table(html):
        if any(ch == w[0] and d == w[1] and abs(s - w[2]) <= 10 for w in want):
            keys.add(f"{ch}:{pid}")
    return keys


# ---------------------------------------------------------------- 페이지 고치기
def _patch(html: str, captions: set[str]) -> str:
    n = 0

    def sub(old: str, new: str) -> None:
        nonlocal html, n
        if old in html:
            html = html.replace(old, new, 1)
            n += 1
        else:
            _log(f"패치 지점을 못 찾음: {old[:40]!r}")

    def sub_any(olds: list[str], new_of) -> None:
        """판마다 다른 문구 중 있는 것 하나를 고친다(없으면 기록만)."""
        nonlocal html, n
        for old in olds:
            if old in html:
                html = html.replace(old, new_of(old), 1)
                n += 1
                return
        _log(f"패치 지점을 못 찾음(모든 판): {olds[0][:40]!r}")

    def sub_opt(old: str, new: str) -> None:
        nonlocal html, n
        if old in html:
            html = html.replace(old, new, 1)
            n += 1

    if captions:
        html, k = re.subn(r"const CAPTION_PROGRAMS = new Set\(\[.*?\]\);",
                          lambda _m: "const CAPTION_PROGRAMS = new Set(" + json.dumps(sorted(captions)) + ");",
                          html, count=1, flags=re.S)
        n += k
    sub("const ANALYZE_URL = '';", "const ANALYZE_URL = '/from-cmp?picks={ids}&item={item}';")
    sub("const ids = [...new Set([...picks.values()].map((e) => e.g.id))];\n  if (ANALYZE_URL) {",
        "if (picks.size < 1) { toast('분석할 방송을 골라 주세요'); return; }\n"
        "  const ids = [...new Set([...picks.values()].map((e) => [e.ch, e.d, e.g.s, e.g.id].join(':')))];\n  if (ANALYZE_URL) {")
    # 새 창이 아니라 같은 창에서 우리 앱으로 넘어온다(팝업 차단 없음, 뒤로 가기로 돌아옴)
    sub("window.open(ANALYZE_URL.replace('{ids}'", "location.assign(ANALYZE_URL.replace('{ids}'")
    sub_any(["(cur >= 0 ? D.items[cur][0] : '')), '_blank', 'noopener');",   # 옛 판
             "cur >= 0 ? D.items[cur][0] : '')), '_blank', 'noopener');"],    # 새 판(카테고리 보기 추가)
            lambda old: old.replace(", '_blank', 'noopener');", ");"))
    sub("const MAXPICK = 2;", "const MAXPICK = 3;")
    sub_opt("비교 대상으로 선택 (최대 2개)", "분석 대상으로 선택 (최대 3개)")
    OUR_BTN = '<button class="btn primary" id="{bid}" title="고른 방송을 우리 앱의 방송 분석 화면으로 엽니다">방송 분석하기 →</button>'
    if 'id="anaMent"' in html:  # 옛 판: 버튼 두 개
        sub('<button class="btn primary" id="anaMent" title="실적 수치 없이 쇼호스트 멘트·방송 운영만 비교하는 요청문을 복사합니다">멘트 분석 (실적 제외) →</button>',
            OUR_BTN.format(bid="anaMent"))
        sub('<button class="btn primary" id="anaFull" title="취급액·가중노출분·분당매출까지 포함한 요청문을 복사합니다">실적 포함 분석 →</button>',
            '<button class="btn primary" id="anaFull" hidden style="display:none">실적 포함 분석 →</button>')
    else:  # 새 판(2026-11-19 15:11~): '방송 분석 →' 버튼 하나
        sub('<button class="btn primary" id="anaFull" title="취급액·가중노출분·분당매출까지 포함한 요청문을 복사합니다">방송 분석 →</button>',
            OUR_BTN.format(bid="anaFull"))
    sub_opt("최대 2개 방송을 골라 분석 요청문을 복사할 수 있습니다.",
            "‘자막 있음’ 방송을 1~3개 골라 ‘방송 분석하기’를 누르면 우리 앱의 방송 분석 화면으로 이동합니다.")
    # 2026-11-19 사용자 지적: 리포트에서 '뒤로'를 누르면 표지(데모 시작)부터 다시 떴다.
    # 주소에 고른 상품(#상품명)이 있으면 = 검색해 둔 화면으로 돌아온 것 → 표지를 띄우지 않는다.
    sub_any(["openIntro();\n})();</script>"],
            lambda old: old.replace("openIntro();", "if (location.hash) intro.hidden = true; else openIntro();"))
    _log(f"페이지 패치 {n}곳 적용, 자막 있음 {len(captions)}건")
    return html


def page() -> tuple[str, bytes | None, bytes | None]:
    """('ready', 원문, gzip) | ('loading', None, None) | ('none', None, None)."""
    if not os.path.exists(CACHE):
        refresh_async()
        return ("loading", None, None) if (URL and _refreshing) else ("none", None, None)
    if (cache_age() or 0) > MAX_AGE_SEC:
        refresh_async()  # 지금 캐시는 그대로 보여 주고 뒤에서 새로 받는다
    key = (os.path.getmtime(CACHE), os.path.getsize(CACHE), _library_signature())
    with _lock:
        if _memo["key"] != key:
            with open(CACHE, encoding="utf-8") as f:
                html = f.read()
            try:
                caps = _caption_keys(html)
            except Exception as e:  # noqa: BLE001 — 못 읽으면 원래 페이지의 표시를 그대로 둔다
                _log(f"자막 있음 계산 실패: {e}")
                caps = set()
            raw = _patch(html, caps).encode("utf-8")
            _memo.update(key=key, raw=raw, gz=gzip.compress(raw, 5))
        return "ready", _memo["raw"], _memo["gz"]


LOADING_HTML = ("<!doctype html><meta charset='utf-8'><meta http-equiv='refresh' content='10'>"
                "<title>불러오는 중</title><body style='font-family:Pretendard,sans-serif;padding:60px;color:#37352f'>"
                "<h2>편성 비교 화면을 불러오는 중입니다</h2>"
                "<p>사내 데이터(약 22MB)를 처음 한 번 받아 오는 중이라 2~3분쯤 걸립니다. 자동으로 다시 열립니다.</p></body>")


# ---------------------------------------------------------------- 비교 버튼 → 보관함 방송
def resolve(picks: list[str]) -> dict:
    """picks('GS:20261005:1305:GS652671' …) → {'folders': {폴더: [자막 파일…]}, 'missing': [{…}]}."""
    inv = cmpsite.CH
    lib = library.all_broadcasts()
    folders: dict[str, list[str]] = {}
    missing = []
    for raw in picks:
        parts = raw.split(":")
        try:
            code, d, s = parts[0], parts[1], int(parts[2])
            pid = ":".join(parts[3:])
            ch = inv.get(code)
            day = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        except (IndexError, ValueError):
            missing.append({"raw": raw, "why": "형식 오류"})
            continue
        hit = next((name_b for name_b in lib
                    if name_b[1]["channel"] == ch and name_b[1]["start_datetime"][:10] == day
                    and abs(int(name_b[1]["start_datetime"][11:13]) * 60 + int(name_b[1]["start_datetime"][14:16]) - s) <= 10), None)
        if not hit:
            missing.append({"raw": raw, "code": code, "day": day, "start": f"{s // 60:02d}:{s % 60:02d}", "id": pid, "channel": ch})
            continue
        folders.setdefault(hit[0], []).append(hit[1]["local_file"])
    return {"folders": folders, "missing": missing}
