"""상품 문장 꼬리표(소구 포인트·NEEDS·설득 방식) — 2026-10-27 사용자 결정 반영.

- 소구: 기존 목록 유지, 새로 나온 것만 정리(디스플레이 통합, 인기·명성→브랜드·평판, 가격혜택 제외, 먼지 비산→흡입력)
- NEEDS: 비슷한 것 합치기(아이 있는 집 / 구매 망설임 / 시즌·계기)
- 화면: 소구 × 방송 표, NEEDS 순위 카드, 흐름 막대 아래 소구 띠
"""
import csv
import html
import json
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PROD = os.path.join(HERE, "prod")

SOGU = ["흡입력·성능", "가벼움·조작", "다용도·툴", "배터리·거치", "디스플레이", "구성",
        "위생·필터", "털 엉킴 방지", "브랜드·평판", "디자인"]
SOGU_COLORS = {"흡입력·성능": "#2383e2", "가벼움·조작": "#0f7b6c", "다용도·툴": "#d9730d", "배터리·거치": "#9065b0",
               "디스플레이": "#5b6b7f", "구성": "#c29343", "위생·필터": "#2aa5a0", "털 엉킴 방지": "#d36ba6",
               "브랜드·평판": "#7a4e2d", "디자인": "#a8a29e"}
NEEDS = ["침구 진드기·먼지", "기존 청소기 불만", "손목·체력 부담", "시간·귀찮음", "긴 머리카락", "반려동물",
         "아이 있는 집", "선물·효도", "좁은 집·수납", "구매 망설임", "시즌·계기"]
MAP = {
    "디스플레이 안내": "디스플레이", "인기모델": "브랜드·평판", "인기·명성": "브랜드·평판", "브랜드 기술력": "브랜드·평판",
    "먼지 비산 없음": "흡입력·성능", "가격혜택": None,
    "육아맘": "아이 있는 집", "차량·아이 부스러기": "아이 있는 집", "아이·알레르기": "아이 있는 집",
    "가격 부담": "구매 망설임", "구매 망설임": "구매 망설임", "새해 청소결심": "시즌·계기",
    "먼지 가시화": "디스플레이",
}


def _labels(cell):
    out = []
    for x in (cell or "").split(";"):
        x = x.strip().replace("NEW:", "")
        if not x or x == "-":
            continue
        x = MAP.get(x, x)
        if x and x not in out:
            out.append(x)
    return out


def load_tags(key):
    """idx → {"s": [소구], "n": [NEEDS], "m": 방식}. 검수 수정(review_fixes.tsv)을 덮어쓴다."""
    tags = {}
    for r in csv.DictReader(open(os.path.join(PROD, f"{key}_tags.tsv"), encoding="utf-8"), delimiter="\t"):
        tags[int(r["idx"])] = {"s": _labels(r["소구"]), "n": _labels(r["NEEDS"]), "m": (r["방식"] or "").strip()}
    fx = os.path.join(PROD, "review_fixes.tsv")
    if os.path.exists(fx):
        for r in csv.DictReader(open(fx, encoding="utf-8"), delimiter="\t"):
            if r.get("bc") != key or not (r.get("idx") or "").strip().isdigit():
                continue
            i = int(r["idx"])
            if i in tags:
                tags[i] = {"s": _labels(r["소구"]), "n": _labels(r["NEEDS"]), "m": (r["방식"] or tags[i]["m"]).strip(),
                           "why": (r.get("사유") or "").strip()}
    return tags


def load_splits(key):
    """2026-10-27 사용자 결정(A): 소구가 둘 이상인 문장은 소구 하나씩의 조각으로 잘라 그 조각 글자만 센다.
    idx → [{"text", "s": [소구], "n": [NEEDS], "m": 방식}]"""
    path = os.path.join(PROD, f"{key}_split.jsonl")
    out = {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            if ln.strip():
                r = json.loads(ln)
                out[int(r["idx"])] = [{"text": p["text"], "s": _labels(p.get("소구")), "n": _labels(p.get("NEEDS")),
                                       "m": (p.get("방식") or "").strip()} for p in r["parts"]]
    return out


def pieces(b, i):
    """문장 i 의 (글자 수, 텍스트, 꼬리표) 조각들. 쪼갠 문장은 조각별, 아니면 문장 전체 하나."""
    u = b["units"][i]
    sp = b.get("psplit", {}).get(i)
    if sp and "".join(p["text"] for p in sp) == u["text"]:
        return [(max(len(p["text"]), 1), p["text"], p) for p in sp]
    return [(max(len(u["text"]), 1), u["text"], b["ptags"][i])]


def _e(x):
    return html.escape(str(x))


def attach(data, mmss, weight):
    """data 의 각 방송에 상품 꼬리표 통계를 붙인다."""
    for b in data:
        tags = load_tags(b["key"])
        b["ptags"] = tags
        b["psplit"] = load_splits(b["key"])
        tot = 0
        S, N, M = Counter(), Counter(), Counter()
        sent = defaultdict(list)
        for i in sorted(tags):
            u = b["units"][i]
            for w, text, tg in pieces(b, i):
                tot += w
                line = [mmss(u["t"]), text, 1 if u["vcr"] else 0, " · ".join(tg["s"]), " · ".join(tg["n"])]
                for s in tg["s"]:
                    S[s] += w
                    sent["s:" + s].append(line)
                for n in tg["n"]:
                    N[n] += w
                    sent["n:" + n].append(line)
                M[tg["m"]] += w
        b["pstat"] = {"tot": tot, "S": S, "N": N, "M": M, "sent": sent}


def strip_html(b, total, end_t):
    """흐름 막대 아래 얇은 띠: 상품 문장마다 첫 번째 소구 색."""
    us, tags = b["units"], b["ptags"]
    out = []
    for i in sorted(tags):
        t0 = us[i]["t"]
        t1 = min(us[i + 1]["t"] if i + 1 < len(us) else end_t, t0 + 20)
        ps = pieces(b, i)
        allw = sum(w for w, _, _ in ps)
        a = t0
        for w, text, tg in ps:  # 쪼갠 조각은 글자 수 비율로 시간 나눔
            z = a + (t1 - t0) * w / allw
            if tg["s"]:
                out.append(f"<i title='{_e(tg['s'][0])}: {_e(text[:50])}' style='left:{100 * a / total:.3f}%;"
                           f"width:{max(100 * (z - a) / total, 0.12):.3f}%;background:{SOGU_COLORS.get(tg['s'][0], '#c7c6c3')}'></i>")
            a = z
    return f"<div class='pstrip'>{''.join(out)}</div>"


def strip_legend():
    return ("<div class='plg'><label><input type='checkbox' id='pstog' checked> 상품 구간 소구 띠 보기</label>"
            + "".join(f"<span><i style='background:{SOGU_COLORS[s]}'></i>{s}</span>" for s in SOGU) + "</div>")


def section(data):
    keys = [b["key"] for b in data]
    st = {b["key"]: b["pstat"] for b in data}
    # 소구 × 방송 표
    order = sorted(SOGU, key=lambda s: -sum(st[k]["S"][s] for k in keys))
    max_a = max(st[k]["S"][s] for k in keys for s in SOGU) or 1
    max_s = max(st[k]["S"][s] / (st[k]["tot"] or 1) for k in keys for s in SOGU) or 1
    head = "".join(f"<th style='color:{b['color']}'>{_e(b['label'])}<div class='sub'>상품 {st[b['key']]['tot']:,}자</div></th>" for b in data)
    trs = []
    for s in order:
        vals = [st[k]["S"][s] for k in keys]
        cells = ""
        for b in data:
            k = b["key"]
            a, sh = st[k]["S"][s], st[k]["S"][s] / (st[k]["tot"] or 1)
            n = len(st[k]["sent"]["s:" + s])
            cells += (f"<td class='hc' data-k='{k}' data-q='s:{s}' data-al-a='{a / max_a:.3f}' data-al-s='{sh / max_s:.3f}'"
                      f" data-t-a='{a:,}자 · {n}문장' data-t-s='{sh * 100:.1f}% · {n}문장'"
                      f" style='--al:{a / max_a:.3f}'><b>{a:,}자</b><span>{n}문장</span></td>")
        trs.append(f"<tr><th class='rl'><i style='background:{SOGU_COLORS[s]}'></i>{_e(s)}</th>{cells}</tr>")
    table = (f"<div class='pi-sc'><table class='ht'><thead><tr><th class='rl'>소구 포인트</th>{head}</tr></thead>"
             f"<tbody>{''.join(trs)}</tbody></table></div>")

    # NEEDS 순위 카드
    nmax = max((st[k]["N"][n] for k in keys for n in NEEDS), default=1) or 1
    cards = []
    for b in data:
        k = b["key"]
        top = [n for n, _ in st[k]["N"].most_common() if n in NEEDS][:5]
        rows = "".join(
            f"<div class='nr' data-k='{k}' data-q='n:{n}' title='눌러서 문장 보기'><span class='nn'>{i + 1}. {_e(n)}</span>"
            f"<span class='nb'><i style='width:{100 * st[k]['N'][n] / nmax:.1f}%;background:{b['color']}'></i></span>"
            f"<span class='nv'>{st[k]['N'][n] / (st[k]['tot'] or 1) * 100:.0f}%</span></div>" for i, n in enumerate(top))
        others = [n for n, v in st[k]["N"].most_common() if n in NEEDS and n not in top and v]
        cards.append(f"<div class='nc' style='--c:{b['color']}'><h3 style='color:{b['color']}'>{_e(b['label'])}</h3>{rows}"
                     + (f"<div class='sub' style='margin-top:6px'>그 밖: {_e(' · '.join(others))}</div>" if others else "")
                     + "</div>")

    sents = {f"{b['key']}|{q}": v for b in data for q, v in b["pstat"]["sent"].items()}
    labels = {b["key"]: b["label"] for b in data}
    return f"""<style>
.ht{{border-collapse:collapse;width:100%;min-width:560px;font-size:14px;margin:8px 0}}
.ht th,.ht td{{border-bottom:1px solid #e9e9e7;padding:8px 10px;text-align:center}}
.ht thead th{{background:#f7f6f3;font-weight:650;font-size:13.5px}}
.ht th.rl{{text-align:left;font-weight:600;white-space:nowrap;background:#fff}}.ht thead th.rl{{background:#f7f6f3;color:rgba(55,53,47,.5);font-weight:500}}
.ht th.rl i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:7px}}
.ht td.hc{{cursor:pointer;background:rgba(35,131,226,calc(var(--al)*.78));color:#37352f;transition:background .2s;font-variant-numeric:tabular-nums}}
.ht td.hc b{{display:block;font-size:14px}}.ht td.hc span{{font-size:11.5px;opacity:.75}}
.ht td.hc.dk{{color:#fff}}.ht td.hc.on{{outline:2px solid #37352f;outline-offset:-2px}}
.ncs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin:10px 0}}
.nc{{border:1px solid #e9e9e7;border-top:3px solid var(--c);border-radius:6px;padding:10px 14px}}.nc h3{{margin:0 0 6px;font-size:15px}}
.nr{{display:grid;grid-template-columns:128px 1fr 38px;gap:8px;align-items:center;font-size:13.5px;margin:5px 0;cursor:pointer}}
.nr:hover .nn{{text-decoration:underline}}.nr.on .nn{{font-weight:700}}
.nb{{height:10px;background:#f1f1ef;border-radius:3px;overflow:hidden;position:relative}}.nb i{{position:absolute;left:0;top:0;bottom:0;border-radius:3px}}
.nv{{text-align:right;font-variant-numeric:tabular-nums;color:rgba(55,53,47,.72)}}
.ptog button{{border:1px solid #e9e9e7;background:#fff;border-radius:4px;padding:3px 10px;font-size:13px;cursor:pointer}}
.ptog button.on{{background:#37352f;color:#fff;border-color:#37352f}}
#psent{{border:1px solid #e9e9e7;border-radius:6px;padding:10px 14px;margin:12px 0;max-height:420px;overflow:auto;font-size:14px}}
#psent .ql{{padding:3px 0;border-bottom:1px solid #f1f1ef;line-height:1.6}}#psent .t{{color:rgba(55,53,47,.5);margin-right:8px}}
#psent .tg{{color:rgba(55,53,47,.5);font-size:12px;margin-left:6px}}
</style>
<h2>상품 소구 분석 — 무엇을, 누구에게</h2>
<p class="sub">상품 묶음 문장을 하나씩 읽고 <b>소구 포인트</b>(무엇을 장점으로 내세웠나)와 <b>NEEDS</b>(누구의 어떤 고민을 건드렸나) 꼬리표를 붙인 뒤 세 방송을 같은 기준으로 검수했습니다. 소구가 둘 이상 섞인 문장은 소구 하나씩의 조각으로 잘라 그 조각의 글자만 셉니다(같은 글자를 두 번 세지 않음). NEEDS는 한 조각이 여러 고민을 건드릴 수 있어 합계가 100%를 넘을 수 있습니다. 칸·막대를 누르면 실제 문장이 나옵니다.</p>
<h3>소구 포인트 × 방송</h3>
<div class="ptog">칸 색 기준 <button class="on" data-m="a">말한 양(글자 수)</button> <button data-m="s">비율(상품 멘트 중)</button></div>
{table}
<h3>방송별 NEEDS 순위</h3>
<p class="sub">% = 그 방송 상품 멘트 중 해당 고민을 건드린 비중 · 막대 길이는 말한 양</p>
<div class="ncs">{''.join(cards)}</div>
<div id="psent"><span class="sub">표의 칸이나 NEEDS 줄을 누르면 해당 문장이 여기에 나옵니다</span></div>
<script>
(function(){{
const S = {json.dumps(sents, ensure_ascii=False)};
const BL = {json.dumps(labels, ensure_ascii=False)};
const esc = s => String(s).replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);
function paint(m) {{
  document.querySelectorAll('.ht td.hc').forEach(td => {{
    const al = +td.dataset['al' + (m === 'a' ? 'A' : 'S')];
    td.style.setProperty('--al', al);
    td.classList.toggle('dk', al > .55);
    const [x, y] = td.dataset['t' + (m === 'a' ? 'A' : 'S')].split(' · ');
    td.innerHTML = `<b>${{x}}</b><span>${{y}}</span>`;
  }});
}}
document.querySelectorAll('.ptog button').forEach(btn => btn.onclick = () => {{
  document.querySelectorAll('.ptog button').forEach(x => x.classList.toggle('on', x === btn)); paint(btn.dataset.m);
}});
paint('a');
document.querySelectorAll('.ht td.hc, .nr').forEach(el => el.onclick = () => {{
  document.querySelectorAll('.ht td.hc.on, .nr.on').forEach(x => x.classList.remove('on'));
  el.classList.add('on');
  const L = S[el.dataset.k + '|' + el.dataset.q] || [];
  const nm = el.dataset.q.slice(2);
  document.getElementById('psent').innerHTML = `<b>${{esc(BL[el.dataset.k])}} · ${{esc(nm)}}</b> <span class="sub">${{L.length}}문장</span>` +
    (L.length ? L.map(([t,x,v,s,n]) => `<div class="ql"><span class="t">${{t}}</span>${{esc(x)}}${{v?' <span class="sub">(VCR)</span>':''}}<span class="tg">${{esc([s,n].filter(Boolean).join(' / '))}}</span></div>`).join('') : '<div class="sub">해당 문장 없음</div>');
}});
const tog = document.getElementById('pstog');
if (tog) tog.onchange = () => document.querySelectorAll('.pstrip').forEach(p => p.style.display = tog.checked ? '' : 'none');
}})();
</script>"""


STRIP_CSS = """.pstrip{position:relative;height:7px;margin-top:2px;background:#f7f6f3;border-radius:2px}
.pstrip i{position:absolute;top:0;bottom:0;display:block}
.plg{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12.5px;margin:4px 0 8px;color:rgba(55,53,47,.8);align-items:center}
.plg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.plg label{font-weight:600;margin-right:6px;cursor:pointer}"""
