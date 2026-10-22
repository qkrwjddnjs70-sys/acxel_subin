"""2안 미리보기 v2: 기존 '방송 흐름' 구간 막대 유지 + 구간 이름을 문장 분류로 바로잡기 + 구간 클릭 시 16개·4묶음 상세."""
import html
import json
import os
from collections import Counter

from build_preview import BROADCASTS, CODES, GROUP_COLORS, GROUPS, load, mmss

HERE = os.path.dirname(os.path.abspath(__file__))
NARR = r"C:\Users\GSR\.claude\HomeshoppingCompareBOT\out\narrative\dyson_digital_slim.json"
LABEL_TO_KEY = {"GS샵 1/7": "gs0107", "GS샵 2/17": "gs0217", "현대홈쇼핑 6/21": "hd0621"}


def e(x):
    return html.escape(str(x if x is not None else ""))


def sec(ts):
    p = [int(x) for x in str(ts).split(":")]
    return p[0] * 60 + p[1] if len(p) == 2 else p[0] * 3600 + p[1] * 60 + p[2]


def main():
    narr = json.load(open(NARR, encoding="utf-8"))
    bcs = []
    for b in narr["broadcasts"]:
        key = LABEL_TO_KEY[b["label"]]
        segs = load(key)
        phases = b["analysis"]["phases"]
        # 구간 경계: 원래 분석의 경계를 쓰되, 다음 구간 시작까지 빈틈 없이 이어 붙인다
        starts = [sec(p["start"]) for p in phases]
        end_all = max(s["t"] for s in segs) + 5
        blocks = []
        for i, p in enumerate(phases):
            s0 = starts[i]
            s1 = starts[i + 1] if i + 1 < len(phases) else end_all
            inside = [s for s in segs if s0 <= s["t"] < s1]
            c = Counter()
            for s in inside:
                c[s["code"]] += max(len(s["text"]), 1)
            sell = {k: v for k, v in c.items() if CODES[k][1] != "기타"}
            tot = sum(sell.values()) or 1
            ranked = sorted(sell.items(), key=lambda kv: -kv[1])
            top1 = ranked[0][0] if ranked else "X1"
            top1_share = ranked[0][1] / tot if ranked else 0
            # 한 종류가 40% 미만이면 상위 두 개를 같이 이름으로
            if len(ranked) > 1 and top1_share < 0.40:
                name = f"{CODES[top1][0]}·{CODES[ranked[1][0]][0]}"
            else:
                name = CODES[top1][0]
            blocks.append({
                "s0": s0, "s1": s1, "old": p["phase"], "name": name, "code": top1, "share": top1_share,
                "summary": p.get("summary", ""),
                "mix": {k: v / tot for k, v in ranked},
                "groups": {g: sum(v for k, v in sell.items() if CODES[k][1] == g) / tot for g in GROUPS},
                "other": sum(v for k, v in c.items() if CODES[k][1] == "기타") / (sum(c.values()) or 1),
                "lines": [[mmss(s["t"]), s["code"], s["text"]] for s in inside],
            })
        bcs.append({"key": key, "label": b["label"], "color": b["color"], "kpi": b["kpi"],
                    "fp": (b["analysis"].get("first_price_mention") or {}).get("time"), "blocks": blocks})

    total = max(b["blocks"][-1]["s1"] for b in bcs)
    rows = []
    payload = {}
    changed = []
    for b in bcs:
        segs_html = []
        for j, bl in enumerate(b["blocks"]):
            col = CODES[bl["code"]][2]
            dark_txt = bl["code"] in ("P3", "P5", "C3", "T2")
            bid = f"{b['key']}:{j}"
            payload[bid] = {**bl, "bc": b["label"], "range": f"{mmss(bl['s0'])}~{mmss(bl['s1'])}"}
            if bl["old"] != bl["name"] and bl["old"] not in bl["name"]:
                changed.append((b["label"], f"{mmss(bl['s0'])}~{mmss(bl['s1'])}", bl["old"], bl["name"]))
            segs_html.append(
                f"<div class='seg' data-id='{bid}' title='{e(mmss(bl['s0']))}~{e(mmss(bl['s1']))} {e(bl['name'])} — 눌러서 상세 보기' "
                f"style='left:{100 * bl['s0'] / total:.3f}%;width:{100 * (bl['s1'] - bl['s0']) / total:.3f}%;background:{col};"
                f"color:{'#37352f' if dark_txt else '#fff'}'>{e(bl['name'])}</div>")
        fp = f"<div class='fp' style='left:{100 * sec(b['fp']) / total:.3f}%' title='첫 가격 언급 {e(b['fp'])}'></div>" if b["fp"] else ""
        rows.append(f"<div class='row'><div class='nm' style='color:{b['color']}'>{e(b['label'])}</div>"
                    f"<div class='bar'>{''.join(segs_html)}{fp}</div></div>")
    ticks = "".join(f"<span style='left:{100 * m * 60 / total:.2f}%'>{m}분</span>" for m in range(0, int(total // 60) + 1, 10))
    legend = "".join(
        f"<div class='lg'><b style='color:{GROUP_COLORS.get(g, '#787774')}'>{g}</b>"
        + "".join(f"<span title='{e(CODES[k][3])}'><i style='background:{CODES[k][2]}'></i>{CODES[k][0]}</span>"
                  for k in CODES if CODES[k][1] == g) + "</div>"
        for g in GROUPS + ["기타"])
    fix_rows = "".join(f"<tr><td>{e(a)}</td><td class='t'>{e(r)}</td><td class='sub'>{e(o)}</td><td><b>{e(n)}</b></td></tr>"
                       for a, r, o, n in changed)

    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>2안 미리보기 v2 — 방송 흐름 + 상세 분류</title><style>
:root{{--tx:#37352f;--tx2:rgba(55,53,47,.72);--tx3:rgba(55,53,47,.5);--line:#e9e9e7;--line2:#f1f1ef;--panel2:#f7f6f3;--accent:#2383e2}}
*{{box-sizing:border-box}}body{{margin:0;background:#fff;color:var(--tx);font-size:15px;line-height:1.6;font-family:Pretendard,ui-sans-serif,-apple-system,'Segoe UI','Malgun Gothic',sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:44px 24px 80px}}
h1{{font-size:28px;margin:0 0 6px;letter-spacing:-.02em}} h2{{font-size:20px;font-weight:650;margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}}
h3{{font-size:16px;margin:0 0 6px}} .sub{{color:var(--tx3);font-size:12.5px}}
.badge{{display:inline-block;font-size:12px;padding:1px 8px;border-radius:4px;background:#fdebec;color:#a02a2a;margin-right:6px}}
.row{{display:grid;grid-template-columns:130px 1fr;gap:10px;align-items:center;margin:8px 0}}
.nm{{font-weight:650;font-size:14px}}
.bar{{position:relative;height:36px;background:var(--line2);border-radius:4px}}
.seg{{position:absolute;top:0;bottom:0;border-right:2px solid #fff;font-size:11px;line-height:36px;padding:0 4px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;cursor:pointer}}
.seg:hover{{filter:brightness(1.08);outline:2px solid var(--tx);z-index:2}} .seg.sel{{outline:3px solid var(--tx);z-index:3}}
.fp{{position:absolute;top:-7px;width:2px;height:50px;background:#e03e3e}} .fp::after{{content:'₩';position:absolute;top:-16px;left:-4px;font-size:11px;color:#e03e3e;font-weight:700}}
.axis{{position:relative;height:16px;margin-left:140px;font-size:11px;color:var(--tx3)}} .axis span{{position:absolute;transform:translateX(-50%)}}
.legend{{display:grid;gap:4px;margin:12px 0;font-size:12.5px;color:var(--tx2)}}
.lg{{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center}} .lg b{{width:34px}}
.lg i,.sw{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}}
#detail{{border:1px solid var(--line);border-radius:6px;padding:16px 18px;margin:14px 0}}
.gbar{{display:flex;height:22px;border-radius:4px;overflow:hidden;margin:8px 0 4px}} .gbar div{{color:#fff;font-size:11.5px;line-height:22px;padding:0 6px;white-space:nowrap;overflow:hidden}}
.grid4{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-top:12px}}
.gbox{{border:1px solid var(--line);border-radius:6px;padding:10px 12px;border-top:3px solid var(--c)}}
.cat{{display:grid;grid-template-columns:1fr 90px 40px;gap:6px;align-items:center;font-size:13px;margin:3px 0}}
.cat .b{{height:8px;background:var(--line2);border-radius:2px;overflow:hidden}} .cat .b i{{display:block;height:100%}}
.cat .v{{text-align:right;font-variant-numeric:tabular-nums;color:var(--tx2)}} .cat.zero{{color:var(--tx3)}}
.quotes{{margin-top:14px}} .ql{{font-size:13.5px;padding:5px 0;border-bottom:1px solid var(--line2)}}
.chip{{display:inline-block;font-size:11px;border-radius:3px;padding:0 6px;margin-right:6px;white-space:nowrap}}
.t{{color:var(--accent);font-variant-numeric:tabular-nums;font-size:12px;margin-right:4px;white-space:nowrap}}
.filters{{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}} .filters button{{font:inherit;font-size:12.5px;border:1px solid var(--line);background:#fff;border-radius:14px;padding:2px 10px;cursor:pointer}}
.filters button.on{{background:var(--tx);color:#fff;border-color:var(--tx)}}
table{{border-collapse:collapse;width:100%;font-size:13.5px}} th,td{{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left}} th{{background:var(--panel2);color:var(--tx3);font-weight:500;font-size:12.5px}}
</style></head><body><div class="wrap">
<h1>다이슨 디지털 슬림 — 방송 흐름 (2안 · 상세 분류)</h1>
<p class="sub"><span class="badge">미리보기 · 저장 안 됨</span>구간 이름은 그 구간 문장들의 분류(16개) 중 가장 많은 것 · 한 종류가 40% 미만이면 상위 두 개를 함께 표시</p>

<h2>1. 방송 흐름 한눈에</h2>
<p class="sub">구간을 누르면 아래에 16개·4묶음 상세 분류와 실제 멘트가 펼쳐집니다 · 빨간 선(₩)은 처음 가격을 꺼낸 시점</p>
{''.join(rows)}
<div class="axis">{ticks}</div>
<div class="legend">{legend}</div>
<div id="detail"><span class="sub">위 막대에서 구간을 눌러 보세요</span></div>

<h2>2. 바로잡은 구간 <span class="sub">이전 이름 → 문장 분류로 다시 붙인 이름</span></h2>
<table><thead><tr><th>방송</th><th>구간</th><th>이전</th><th>수정</th></tr></thead><tbody>{fix_rows}</tbody></table>
</div>
<script>
const P = {json.dumps(payload, ensure_ascii=False)};
const C = {json.dumps({k: [v[0], v[1], v[2], v[3]] for k, v in CODES.items()}, ensure_ascii=False)};
const G = {json.dumps(GROUPS, ensure_ascii=False)}, GC = {json.dumps(GROUP_COLORS, ensure_ascii=False)};
const esc = s => String(s).replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
const light = k => ['P3','P5','C3','T2','X1','X2','X3'].includes(k);
let cur = null, filt = null;
function show(id){{
  cur = id; const d = P[id];
  const gbar = G.map(g => d.groups[g] > 0.005 ? `<div style="width:${{(d.groups[g]*100).toFixed(1)}}%;background:${{GC[g]}}">${{g}} ${{Math.round(d.groups[g]*100)}}%</div>` : '').join('');
  const boxes = G.map(g => {{
    const ks = Object.keys(C).filter(k => C[k][1] === g);
    return `<div class="gbox" style="--c:${{GC[g]}}"><b style="color:${{GC[g]}}">${{g}}</b> <span class="sub">${{Math.round((d.groups[g]||0)*100)}}%</span>` +
      ks.map(k => {{ const v = d.mix[k] || 0; return `<div class="cat${{v?'':' zero'}}" title="${{esc(C[k][3])}}"><span><i class="sw" style="background:${{C[k][2]}}"></i>${{C[k][0]}}</span>
        <span class="b"><i style="width:${{(v*100).toFixed(1)}}%;background:${{C[k][2]}}"></i></span><span class="v">${{v ? Math.round(v*100)+'%' : '–'}}</span></div>`; }}).join('') + '</div>';
  }}).join('');
  const present = [...new Set(d.lines.map(l => l[1]))].sort((a,b) => Object.keys(C).indexOf(a) - Object.keys(C).indexOf(b));
  const fbtn = `<button data-f="" class="${{filt?'':'on'}}">전체 ${{d.lines.length}}</button>` + present.map(k =>
    `<button data-f="${{k}}" class="${{filt===k?'on':''}}">${{C[k][0]}} ${{d.lines.filter(l=>l[1]===k).length}}</button>`).join('');
  const lines = d.lines.filter(l => !filt || l[1] === filt).map(([t,k,x]) =>
    `<div class="ql"><span class="chip" style="background:${{C[k][2]}};color:${{light(k)?'#37352f':'#fff'}}">${{C[k][0]}}</span><span class="t">${{t}}</span>${{esc(x)}}</div>`).join('');
  document.getElementById('detail').innerHTML =
    `<h3>${{esc(d.bc)}} · ${{d.range}} · ${{esc(d.name)}}</h3>
     <div class="sub">이전 이름: ${{esc(d.old)}} · 요약: ${{esc(d.summary)}} · 진행·맞장구·VCR·잡음 ${{Math.round(d.other*100)}}%(비중 계산에서 제외)</div>
     <div class="gbar">${{gbar}}</div><div class="grid4">${{boxes}}</div>
     <div class="quotes"><b>이 구간의 멘트</b><div class="filters">${{fbtn}}</div>${{lines}}</div>`;
  document.querySelectorAll('#detail .filters button').forEach(b => b.onclick = () => {{ filt = b.dataset.f || null; show(cur); }});
}}
document.querySelectorAll('.seg').forEach(el => el.addEventListener('click', () => {{
  document.querySelectorAll('.seg.sel').forEach(x => x.classList.remove('sel')); el.classList.add('sel');
  filt = null; show(el.dataset.id); document.getElementById('detail').scrollIntoView({{block:'nearest', behavior:'smooth'}});
}}));
</script></body></html>"""
    open(os.path.join(HERE, "preview_2an_v2.html"), "w", encoding="utf-8").write(page)
    print("ok; changed blocks:", len(changed))
    for c in changed:
        print("  ", c)


if __name__ == "__main__":
    main()
