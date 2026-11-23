"""보관함 1안 리포트(리포트*.html)를 GS 먼저 순서로 다시 만들고, 기존 '핵심 결론' 패널은 그대로 다시 붙인다(백업 남김)."""
import os, shutil, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hsbot import webapp
from hsbot.sources import library

ANCHOR = '<div class="panel">\n  <b>비교 방송 정보</b>'
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
real = library.prebuilt_report_name
for folder_name in ["뼈앤엠비피", "닥터린", "세포랩"]:
    folder = os.path.join("demo_library", folder_name)
    for fn in sorted(os.listdir(folder)):
        if not (fn.startswith("리포트") and fn.endswith(".html")):
            continue
        tp = os.path.join(folder, fn[:-5] + "_대상.txt")
        if not os.path.exists(tp):
            continue
        path = os.path.join(folder, fn)
        old = open(path, encoding="utf-8").read()
        panel = ""
        if "핵심 결론" in old:
            panel = old[old.rfind('<div class="panel"', 0, old.index("핵심 결론")):old.index(ANCHOR)]
        targets = {l.strip() for l in open(tp, encoding="utf-8-sig") if l.strip()}
        items = [b for b in library.list_broadcasts(folder) if b["local_file"] in targets]
        for b in items:
            b["channel_name"] = webapp.channel_display(b["channel"])
        webapp.attach_labangba(items)
        library.prebuilt_report_name = lambda *a, **k: None
        try:
            base = webapp.build_library_compare_html(items=items, keyword=folder_name)
        finally:
            library.prebuilt_report_name = real
        k = base.index(ANCHOR)
        shutil.copy2(path, os.path.join(folder, f"백업_{stamp}_{fn}"))
        open(path, "w", encoding="utf-8").write(base[:k] + panel + base[k:])
        print(folder_name, fn, "패널 보존" if panel else "패널 없음")
