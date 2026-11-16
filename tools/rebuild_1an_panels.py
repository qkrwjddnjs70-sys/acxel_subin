"""보관함 1안 리포트(리포트*.html)를 현재 매출 출처로 다시 만들고, 기존 '핵심 결론' 패널을 숫자만 고쳐 다시 붙인다.
2026-11-16: 매출·가중분을 사내 '아이템 편성 비교' 기준으로 바꾸면서 사용. 원본은 백업_<시각>_<파일> 로 남긴다."""
import os, shutil, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hsbot import webapp
from hsbot.sources import library

ANCHOR = '<div class="panel">\n  <b>비교 방송 정보</b>'
JOBS = [
    ("뼈앤엠비피", "리포트.html", [("209만", "210만"), ("82만", "78만"), ("약 2.5배", "약 2.7배")]),
    ("닥터린", "리포트.html", [("258만", "263만"), ("113만", "116만")]),
    ("세포랩", "리포트.html", [("411만", "430만"), ("374만", "386만")]),
    ("세포랩", "리포트_CJ.html", [("411만", "430만"), ("226만", "263만"), ("1.8배", "1.6배")]),
    ("세포랩", "리포트_3사.html", [("411만", "430만"), ("374만", "386만"), ("226만", "263만")]),
]
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
real_name = library.prebuilt_report_name
for folder_name, fn, reps in JOBS:
    folder = os.path.join("demo_library", folder_name)
    path = os.path.join(folder, fn)
    old = open(path, encoding="utf-8").read()
    z = old.index(ANCHOR)
    a = old.rfind('<div class="panel"', 0, old.index("핵심 결론"))
    panel = old[a:z]
    for x, y in reps:
        assert x in panel, (fn, x)
        panel = panel.replace(x, y)
    tp = os.path.join(folder, fn[:-5] + "_대상.txt")
    targets = {l.strip() for l in open(tp, encoding="utf-8-sig") if l.strip()}
    items = [b for b in library.list_broadcasts(folder) if b["local_file"] in targets]
    for b in items:
        b["channel_name"] = webapp.channel_display(b["channel"])
    webapp.attach_labangba(items)
    library.prebuilt_report_name = lambda *a, **k: None  # 미리 만든 리포트를 건너뛰고 새로 계산
    try:
        base = webapp.build_library_compare_html(items=items, keyword=folder_name)
    finally:
        library.prebuilt_report_name = real_name
    k = base.index(ANCHOR)
    shutil.copy2(path, os.path.join(folder, f"백업_{stamp}_{fn}"))
    open(path, "w", encoding="utf-8").write(base[:k] + panel + base[k:])
    print(path, [(b["channel"], b.get("revenue"), b.get("weighted_min"), b.get("revenue_per_weighted_min")) for b in items])
