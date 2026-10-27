"""2안 미리보기 v3: 문장 단위 검수(B) + 내용 기준 구간 재분할(A).

- 문장(unit) 분류 = 초기 분류 + 검수 수정(*_fixes.tsv). VCR=1 은 녹화 요약 표시.
- 구간: 분류가 바뀌는 곳에서 자르고, 30초 미만 구간은 가장 비슷한 이웃과 합친다.
  진행·맞장구·잡음 문장은 구간을 만들지 않고 앞 구간에 붙는다.
- 짧아서 묻히는 '조건 추가' 문장은 막대 아래 ▲ 표시, VCR 구간은 빗금.
"""
import html
import json
import math
import os
import re
from collections import Counter

from build_preview import BROADCASTS, CODES, GROUP_COLORS, GROUPS, mmss
import product_view as PV

HERE = os.path.dirname(os.path.abspath(__file__))
MIN_SEC = 120
FIRST_PRICE = {"gs0107": "00:19", "gs0217": "00:20", "hd0621": "02:07"}


def e(x):
    return html.escape(str(x if x is not None else ""))


def load_units(key):
    us = json.load(open(os.path.join(HERE, f"{key}_units.json"), encoding="utf-8"))
    for u in us:
        u["vcr"] = False
        u["orig"] = u["code"]
        if u["code"] == "X2":  # 검수에서 빠졌다면 진행으로 둔다
            u["code"] = "X1"
            u["vcr"] = True
    path = os.path.join(HERE, f"{key}_fixes.tsv")
    n_fix = 0
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            p = ln.rstrip("\n").split("\t")
            if len(p) < 2 or not p[0].strip().isdigit():
                continue
            i = int(p[0])
            if i >= len(us):
                continue
            code = p[1].strip().upper()
            if code in CODES and code != "X2":
                if code != us[i]["code"]:
                    n_fix += 1
                us[i]["code"] = code
            if len(p) >= 3 and p[2].strip() == "1":
                us[i]["vcr"] = True
            if len(p) >= 4:
                us[i]["why"] = p[3].strip()
    n_fix += reclass_quantity(us)
    for u in us:  # 2026-10-22 사용자 지시: 상품 소개 + 구성 소개 → '상품 및 구성 설명'(P1)
        if u["code"] == "P3":
            u["code"] = "P1"
    return us, n_fix


QTY = re.compile(r"매진|수량|품절|대기|상담원|물량|빠지|빠져|부족|선점|소진|재고")
KEEP_T4 = re.compile(r"접속|누적|억\s*원?|만\s*원\s*(이상\s*)?판매|판매\s*금액")
KEEP_A1 = re.compile(r"다음\s*방송|미정|일\s*만에|한\s*번|이번\s*달|[0-9]+\s*월\s*(중|에)")
KEEP_A2 = re.compile(r"분\s*(남|정도|밖에)|시간이?\s*(남|얼마)|끝나면|끝나고")


def reclass_quantity(us):
    """2026-10-22 사용자 지시: 수량·매진·대기로 압박하는 멘트는 '수량 푸시'(A4)로.
    방송 기회가 드물다는 말(희소성), 남은 시간(카운트다운), 접속자·누적 매출(사회적 증거)은 그대로 둔다."""
    moved = 0
    for k, u in enumerate(us):
        t = u["text"]
        if not QTY.search(t):
            continue
        if (u["code"] == "T4" and not KEEP_T4.search(t)) or            (u["code"] == "A1" and not KEEP_A1.search(t)) or            (u["code"] == "A2" and not KEEP_A2.search(t)):
            u["code"] = "A4"
            u["why"] = "수량 푸시로 변경"
            moved += 1
            # 바로 앞의 짧은 조각(예: '지금처럼 이렇게')도 같은 말이면 함께
            if k > 0 and us[k - 1]["code"] in ("T4", "A1") and len(us[k - 1]["text"]) < 15 and t and u["t"] - us[k - 1]["t"] <= 6:
                us[k - 1]["code"] = "A4"
                us[k - 1]["why"] = "수량 푸시로 변경"
                moved += 1
    return moved


def weight(u):
    return max(len(u["text"]), 1)


def is_filler(code):
    return CODES[code][1] == "기타"


def mix_of(units):
    c = Counter()
    for u in units:
        if not is_filler(u["code"]):
            c[u["code"]] += weight(u)
    return c


def gmix_of(units):
    c = Counter()
    for u in units:
        if not is_filler(u["code"]):
            c[CODES[u["code"]][1]] += weight(u)
    return c


def gsim(a, b):
    ks = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in ks)
    na = math.sqrt(sum(v * v for v in a.values())) or 1
    nb = math.sqrt(sum(v * v for v in b.values())) or 1
    return dot / (na * nb)


def similarity(a, b):
    ka = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in ka)
    na = math.sqrt(sum(v * v for v in a.values())) or 1
    nb = math.sqrt(sum(v * v for v in b.values())) or 1
    group_bonus = 0.15 if a and b and CODES[a.most_common(1)[0][0]][1] == CODES[b.most_common(1)[0][0]][1] else 0
    return dot / (na * nb) + group_bonus


def segment(units, end_t):
    # 1) 같은 분류가 이어지는 묶음(진행·잡음은 앞 묶음에 붙음)
    blocks = []
    for u in units:
        if blocks and (is_filler(u["code"]) or blocks[-1]["key"] == CODES[u["code"]][1]):
            blocks[-1]["units"].append(u)
            continue
        if not blocks and is_filler(u["code"]):
            blocks.append({"key": None, "units": [u]})
            continue
        blocks.append({"key": CODES[u["code"]][1], "units": [u]})
    # 맨 앞 진행 묶음은 다음에 붙인다
    if len(blocks) > 1 and blocks[0]["key"] is None:
        blocks[1]["units"] = blocks[0]["units"] + blocks[1]["units"]
        blocks.pop(0)

    def bounds(i):
        s0 = blocks[i]["units"][0]["t"]
        s1 = blocks[i + 1]["units"][0]["t"] if i + 1 < len(blocks) else end_t
        return s0, s1

    # 2) 30초 미만 구간을 가장 비슷한 이웃과 합치기(짧은 것부터)
    while len(blocks) > 1:
        durs = [bounds(i)[1] - bounds(i)[0] for i in range(len(blocks))]
        i = min(range(len(blocks)), key=lambda k: durs[k])
        if durs[i] >= MIN_SEC:
            break
        me = gmix_of(blocks[i]["units"])
        cand = [j for j in (i - 1, i + 1) if 0 <= j < len(blocks)]
        j = max(cand, key=lambda k: (gsim(me, gmix_of(blocks[k]["units"])), -durs[k]))
        a, b = sorted((i, j))
        blocks[a]["units"] = blocks[a]["units"] + blocks[b]["units"]
        blocks.pop(b)
    out = []
    for i, bl in enumerate(blocks):
        s0, s1 = bounds(i)
        mx = mix_of(bl["units"])
        tot = sum(mx.values()) or 1
        ranked = mx.most_common()
        top = ranked[0][0] if ranked else "X1"
        share = ranked[0][1] / tot if ranked else 0
        gm = gmix_of(bl["units"])
        gtot = sum(gm.values()) or 1
        granked = gm.most_common()
        gtop = granked[0][0] if granked else "기타"
        name = f"{gtop}·{granked[1][0]}" if len(granked) > 1 and granked[0][1] / gtot < 0.50 else gtop
        allw = sum(weight(u) for u in bl["units"]) or 1
        out.append({
            "s0": s0, "s1": s1, "code": top, "group": gtop, "name": name, "share": share,
            "mix": {k: v / tot for k, v in ranked},
            "groups": {g: sum(v for k, v in mx.items() if CODES[k][1] == g) / tot for g in GROUPS},
            "other": sum(weight(u) for u in bl["units"] if is_filler(u["code"])) / allw,
            "vcr": sum(weight(u) for u in bl["units"] if u["vcr"]) / allw,
            "lines": [[mmss(u["t"]), u["code"], u["text"], 1 if u["vcr"] else 0,
                       (u.get("why") or "") if u["code"] != u["orig"] else ""] for u in bl["units"]],
        })
    return out


def emphasis_section(data):
    """방송별로 모든 문장을 세분류에 매칭해 '무엇을 많이 강조했나'를 막대로 비교."""
    cats = [k for g in GROUPS for k in CODES if CODES[k][1] == g and k != "X2"]
    stats, sents = {}, {}
    for b in data:
        sell = [u for u in b["units"] if not is_filler(u["code"])]
        n_all, n_sell = len(b["units"]), len(sell) or 1
        w_sell = sum(weight(u) for u in sell) or 1
        cnt, wc = Counter(u["code"] for u in sell), Counter()
        for u in sell:
            wc[u["code"]] += weight(u)
        stats[b["key"]] = {"n": {k: cnt[k] for k in cats}, "s": {k: cnt[k] / n_sell for k in cats},
                           "c": {k: wc[k] / w_sell for k in cats}, "a": {k: wc[k] for k in cats}, "sell": len(sell), "all": n_all}
        for k in cats:
            sents[f"{b['key']}:{k}"] = [[mmss(u["t"]), u["text"], 1 if u["vcr"] else 0] for u in sell if u["code"] == k]
    gmax = max(stats[b["key"]]["s"][k] for b in data for k in cats)
    gmax_c = max(stats[b["key"]]["c"][k] for b in data for k in cats)
    gmax_a = max(stats[b["key"]]["a"][k] for b in data for k in cats)

    tops = []
    for b in data:
        st = stats[b["key"]]
        best = sorted(cats, key=lambda k: -st["s"][k])[:3]
        items = "".join(
            f"<li><span class='ecat' style='background:{CODES[k][2]}'></span>{e(CODES[k][0])} <b class='num'>{st['s'][k] * 100:.1f}%</b>"
            f" <span class='sub'>({st['n'][k]}문장)</span></li>" for k in best)
        tops.append(f"<div class='etop' style='--c:{b['color']}'><h3 style='color:{b['color']}'>{e(b['label'])}</h3>"
                    f"<div class='sub'>판매 멘트 {st['sell']}문장 (진행·잡음 제외, 전체 {st['all']})</div><ol>{items}</ol></div>")

    # 대분류 막대(먼저 보이는 것)
    gstat = {b["key"]: {g: (sum(stats[b["key"]]["s"][k] for k in cats if CODES[k][1] == g),
                            sum(stats[b["key"]]["c"][k] for k in cats if CODES[k][1] == g),
                            sum(stats[b["key"]]["n"][k] for k in cats if CODES[k][1] == g),
                            sum(stats[b["key"]]["a"][k] for k in cats if CODES[k][1] == g)) for g in GROUPS} for b in data}
    for b in data:
        for g in GROUPS:
            sents[f"{b['key']}:{g}"] = [x for k in cats if CODES[k][1] == g for x in sents[f"{b['key']}:{k}"]]
            sents[f"{b['key']}:{g}"].sort(key=lambda x: sec(x[0]))
    gm_s = max(v[0] for st in gstat.values() for v in st.values())
    gm_c = max(v[1] for st in gstat.values() for v in st.values())
    grows = []
    # 2026-10-22 사용자 결정: 조건(근거)과 푸시(압박)는 같은 '구매 유도' 몫을 나눠 쓰므로 한 막대에 이어 붙여 보여준다
    ac = {b["key"]: (gstat[b["key"]]["조건"][0] + gstat[b["key"]]["푸시"][0], gstat[b["key"]]["조건"][1] + gstat[b["key"]]["푸시"][1]) for b in data}
    am_s, am_c = max(max(v[0] for v in ac.values()), gm_s), max(max(v[1] for v in ac.values()), gm_c)
    gm_s, gm_c = am_s, am_c
    # 말한 양(절대 글자 수): 구매 유도 합계까지 같은 눈금
    am_a = max(max(gstat[k]["조건"][3] + gstat[k]["푸시"][3] for k in gstat), max(v[3] for st in gstat.values() for v in st.values()))

    def ev(cls_lead, vals, texts):
        """vals/texts: {mode: number/str}. 굵게 표시는 JS가 모드별로 다시 계산."""
        da = " ".join(f"data-{m}='{texts[m]}' data-n{m}='{vals[m]:.6f}'" for m in texts)
        return f"<span class='ev' {da}>{texts['a']}</span>"

    def act_row():
        tmax = max(v[0] for v in ac.values())
        bars = ""
        for b in data:
            k = b["key"]
            (cs, cc, cn, ca), (ps, pc, pn, pa) = gstat[k]["조건"], gstat[k]["푸시"]
            segs = "".join(
                f"<i class='eseg' data-k='{k}:{g}' title='{e(b['label'])} · {g} — 눌러서 문장 보기' data-s='{100 * s / am_s:.2f}' data-c='{100 * c / am_c:.2f}' data-a='{100 * a / am_a:.2f}'"
                f" style='width:{100 * a / am_a:.2f}%;background:{GROUP_COLORS[g]}'></i>"
                for g, s, c, a in (("조건", cs, cc, ca), ("푸시", ps, pc, pa)))
            ts = lambda a, b2, c2: f"{a * 100:.1f}% (조건 {b2 * 100:.1f} + 푸시 {c2 * 100:.1f})"
            bars += (f"<div class='ebar stack'><span class='bn'>{e(b['label'])}</span><span class='stk'>{segs}</span>"
                     + ev(None, {"a": ca + pa, "s": ac[k][0], "c": ac[k][1]},
                          {"a": f"{ca + pa:,}자 (조건 {ca:,} + 푸시 {pa:,})", "s": ts(ac[k][0], cs, ps), "c": ts(ac[k][1], cc, pc)}) + "</div>")
        return (f"<div class='erow'><div class='elab'><b>구매 유도</b>"
                f"<div style='font-size:12px;line-height:1.5;margin-top:2px'><span class='ecat' style='background:{GROUP_COLORS['조건']}'></span>조건 = 근거"
                f"<br><span class='ecat' style='background:{GROUP_COLORS['푸시']}'></span>푸시 = 압박</div></div><div class='ebars'>{bars}</div></div>")

    for g in GROUPS:
        if g == "푸시":
            continue
        if g == "조건":
            grows.append(act_row())
            continue
        vals = [gstat[b["key"]][g][0] for b in data]
        bars = ""
        for b in data:
            v, vc, n, va = gstat[b["key"]][g]
            bars += (f"<div class='ebar stack'><span class='bn'>{e(b['label'])}</span><span class='stk'>"
                     f"<i class='eseg' data-k='{b['key']}:{g}' title='{e(b['label'])} · {g} — 눌러서 문장 보기' data-s='{100 * v / gm_s:.2f}' data-c='{100 * vc / gm_c:.2f}' data-a='{100 * va / am_a:.2f}'"
                     f" style='width:{100 * va / am_a:.2f}%;background:{GROUP_COLORS[g]}'></i></span>"
                     + ev(None, {"a": va, "s": v, "c": vc}, {"a": f"{va:,}자 · {n}문장", "s": f"{v * 100:.1f}% · {n}문장", "c": f"{vc * 100:.1f}% · {n}문장"}) + "</div>")
        sub = " · ".join(CODES[k][0] for k in cats if CODES[k][1] == g)
        grows.append(f"<div class='erow'><div class='elab'><span class='ecat' style='background:{GROUP_COLORS[g]}'></span><b>{g}</b>"
                     f"<div class='sub' style='font-size:11.5px;line-height:1.4'>{e(sub)}</div></div><div class='ebars'>{bars}</div></div>")

    rows = []
    for g in GROUPS:
        gk = [k for k in cats if CODES[k][1] == g]
        gsum = "".join(
            f"<span style='color:{b['color']}'>{e(b['label'])} <b class='num'>{sum(stats[b['key']]['s'][k] for k in gk) * 100:.0f}%</b></span>"
            for b in data)
        rows.append(f"<div class='egrp' style='border-color:{GROUP_COLORS[g]}'><b style='color:{GROUP_COLORS[g]}'>{g}</b><span class='egsum'>{gsum}</span></div>")
        for k in gk:
            vals = [stats[b["key"]]["s"][k] for b in data]
            hi = max(vals)
            bars = ""
            for b in data:
                st = stats[b["key"]]
                v, vc = st["s"][k], st["c"][k]
                lead = v == hi and v > 0 and sum(1 for x in vals if x == hi) == 1
                bars += (f"<div class='ebar' data-k='{b['key']}:{k}' title='{e(b['label'])} · {e(CODES[k][0])} — 눌러서 문장 보기'>"
                         f"<i data-s='{100 * v / gmax:.2f}' data-c='{100 * vc / gmax_c:.2f}' data-a='{100 * st['a'][k] / gmax_a:.2f}' style='width:{100 * st['a'][k] / gmax_a:.2f}%;background:{b['color']}'></i>"
                         + ev(None, {"a": st["a"][k], "s": v, "c": vc}, {"a": f"{st['a'][k]:,}자 · {st['n'][k]}문장", "s": f"{v * 100:.1f}% · {st['n'][k]}문장", "c": f"{vc * 100:.1f}% · {st['n'][k]}문장"}) + "</div>")
            rows.append(f"<div class='erow'><div class='elab' title='{e(CODES[k][3])}'><span class='ecat' style='background:{CODES[k][2]}'></span>{e(CODES[k][0])}</div>"
                        f"<div class='ebars'>{bars}</div></div>")
    legend = "".join(f"<span><i style='background:{b['color']}'></i>{e(b['label'])}</span>" for b in data)
    return f"""<style>
.etops{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:10px 0 16px}}
.etop{{border:1px solid #e9e9e7;border-top:3px solid var(--c);border-radius:6px;padding:10px 14px}}
.etop h3{{margin:0;font-size:15px}}.etop ol{{margin:6px 0 0;padding-left:20px;font-size:14px;line-height:1.8}}
.ecat{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:0}}
.egrp{{display:flex;flex-wrap:wrap;gap:4px 16px;align-items:baseline;border-left:4px solid;padding:4px 10px;margin:16px 0 6px;background:#f7f6f3;border-radius:0 4px 4px 0}}
.egsum{{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px}}
.erow{{display:grid;grid-template-columns:150px 1fr;gap:10px;align-items:center;padding:5px 0;border-bottom:1px solid #f1f1ef}}
.elab{{font-size:14px}}
.ebars{{display:flex;flex-direction:column;gap:3px}}
.ebar{{display:flex;align-items:center;gap:8px;cursor:pointer;height:16px}}
.ebar i{{display:block;height:12px;border-radius:2px;min-width:2px;transition:width .25s}}
.ebar:hover i{{filter:brightness(1.1)}}
.ebar .ev{{font-size:12px;color:rgba(55,53,47,.65);white-space:nowrap;font-variant-numeric:tabular-nums}}
.ebar .ev.lead{{color:#37352f;font-weight:700}}
.ebar.on i{{outline:2px solid #37352f;outline-offset:1px}}
.elg{{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;margin:6px 0}}.elg i{{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:5px;vertical-align:-1px}}
.etog button{{border:1px solid #e9e9e7;background:#fff;border-radius:4px;padding:3px 10px;font-size:13px;cursor:pointer}}
.etog button.on{{background:#37352f;color:#fff;border-color:#37352f}}
#esent{{border:1px solid #e9e9e7;border-radius:6px;padding:10px 14px;margin:12px 0;max-height:420px;overflow:auto;font-size:14px}}
#esent .ql{{padding:3px 0;border-bottom:1px solid #f1f1ef;line-height:1.6}}#esent .t{{color:rgba(55,53,47,.5);margin-right:8px;font-variant-numeric:tabular-nums}}
.ebar.big{{height:22px}}.ebar.big i{{height:18px}}.ebar.big .ev{{font-size:13px}}
.ebar.stack{{height:22px;cursor:default}}.ebar.stack .bn{{width:92px;flex:none;font-size:12px;font-weight:600}}
.ebar.stack .stk{{flex:1;display:flex;height:18px}}.ebar.stack .stk i{{height:18px;cursor:pointer;min-width:0;border-radius:0}}
.ebar.stack .stk i:first-child{{border-radius:2px 0 0 2px}}.ebar.stack .stk i:last-child{{border-radius:0 2px 2px 0}}
.ebar.stack .ev{{width:250px;flex:none;white-space:normal;line-height:1.25}}.eseg.on{{outline:2px solid #37352f;outline-offset:1px;position:relative;z-index:1}}
.esubd{{margin:12px 0}}.esubd>summary{{cursor:pointer;font-size:14px;font-weight:600;padding:6px 10px;border:1px solid #e9e9e7;border-radius:4px;display:inline-block}}
.esubd[open]>summary{{background:#f7f6f3}}
@media (max-width:600px){{.erow{{grid-template-columns:1fr}}}}
</style>
<h2>방송별 강조 포인트 — 모든 문장을 세분류로</h2>
<p class="sub">각 방송의 문장을 하나도 빼지 않고 15개 세분류에 매칭한 결과입니다. <b>말한 양</b> = 실제로 말한 글자 수(방송마다 말한 총량이 달라서 '얼마나 많이 말했나'를 그대로 보여줌), <b>비율</b> = 그 방송의 판매 멘트(진행·맞장구·잡음 제외) 중 해당 분류의 비중. 굵은 숫자는 세 방송 중 가장 많이 쓴 곳. 막대를 누르면 실제 문장이 나옵니다.</p>
<div class="etops">{''.join(tops)}</div>
<div style="display:flex;flex-wrap:wrap;gap:8px 20px;align-items:center">
<div class="etog">기준 <button class="on" data-m="a">말한 양(글자 수)</button> <button data-m="s">비율 · 문장 수</button> <button data-m="c">비율 · 글자 수</button></div></div>
{''.join(grows)}
<details class="esubd"><summary>소분류(15개)로 보기</summary>
<div class="elg" style="margin-top:10px">소분류 막대 색 = 방송 · {legend}</div>
{''.join(rows)}
</details>
<div id="esent"><span class="sub">막대를 누르면 해당 방송·분류의 문장이 여기에 나옵니다</span></div>
<script>
(function(){{
const S = {json.dumps(sents, ensure_ascii=False)};
const NM = {json.dumps({**{k: CODES[k][0] for k in cats}, **{g: g + ' (대분류 전체)' for g in GROUPS}}, ensure_ascii=False)};
const BL = {json.dumps({b['key']: b['label'] for b in data}, ensure_ascii=False)};
const esc = s => String(s).replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);
document.querySelectorAll('.etog button').forEach(btn => btn.onclick = () => {{
  const m = btn.dataset.m;
  document.querySelectorAll('.etog button').forEach(x => x.classList.toggle('on', x === btn));
  document.querySelectorAll('.ebar i').forEach(i => {{ if (i.dataset[m]) i.style.width = i.dataset[m] + '%'; }});
  document.querySelectorAll('.ebar .ev').forEach(v => v.textContent = v.dataset[m]);
  lead(m);
}});
function lead(m) {{
  document.querySelectorAll('.ebars').forEach(g => {{
    const evs = [...g.querySelectorAll('.ev')], ns = evs.map(v => +v.dataset['n' + m]), hi = Math.max(...ns);
    evs.forEach((v, i) => v.classList.toggle('lead', hi > 0 && ns[i] === hi && ns.filter(x => x === hi).length === 1));
  }});
}}
lead('a');
document.querySelectorAll('.ebar[data-k], .eseg').forEach(el => el.onclick = () => {{
  document.querySelectorAll('.ebar.on, .eseg.on').forEach(x => x.classList.remove('on'));
  el.classList.add('on');
  const [bk, k] = el.dataset.k.split(':');
  const L = S[el.dataset.k] || [];
  document.getElementById('esent').innerHTML = `<b>${{esc(BL[bk])}} · ${{esc(NM[k])}}</b> <span class="sub">${{L.length}}문장</span>` +
    (L.length ? L.map(([t,x,v]) => `<div class="ql"><span class="t">${{t}}</span>${{esc(x)}}${{v?' <span class="sub">(VCR)</span>':''}}</div>`).join('') : '<div class="sub">해당 문장 없음</div>');
}});
}})();
</script>"""


def sec(ts):
    m, s = ts.split(":")
    return int(m) * 60 + int(s)


def main():
    data = []
    fixes_total = {}
    for key, label, color, kpi in BROADCASTS:
        us, n_fix = load_units(key)
        fixes_total[label] = (n_fix, sum(1 for u in us if u["vcr"]), len(us))
        end_t = us[-1]["t"] + 5
        data.append({"key": key, "label": label, "color": color, "kpi": kpi, "units": us,
                     "blocks": segment(us, end_t), "end": end_t})
    total = max(b["end"] for b in data)
    PV.attach(data, mmss, weight)

    rows, payload = [], {}
    for b in data:
        segs = []
        for j, bl in enumerate(b["blocks"]):
            col = GROUP_COLORS.get(bl["group"], "#c7c6c3")
            dark = False
            bid = f"{b['key']}:{j}"
            payload[bid] = {**bl, "bc": b["label"], "range": f"{mmss(bl['s0'])}~{mmss(bl['s1'])}"}
            hatch = ""
            segs.append(
                f"<div class='seg{hatch}' data-id='{bid}' title='{e(mmss(bl['s0']))}~{e(mmss(bl['s1']))} {e(bl['name'])}"
                f"{' · 녹화 요약(VCR) ' + str(round(bl['vcr'] * 100)) + '%' if bl['vcr'] >= 0.2 else ''} — 눌러서 상세'"
                f" style='left:{100 * bl['s0'] / total:.3f}%;width:{100 * (bl['s1'] - bl['s0']) / total:.3f}%;"
                f"background-color:{col};color:{'#37352f' if dark else '#fff'}'>{e(bl['name'])}</div>")
        marks = "".join(
            f"<i class='mk' title='{e(mmss(u['t']))} 조건 추가: {e(u['text'][:60])}' style='left:{100 * u['t'] / total:.3f}%'></i>"
            for u in b["units"] if u["code"] == "C2")
        # VCR 실제 구간을 막대 위에 빗금으로(구간 경계와 무관하게)
        vruns, cur = [], None
        for k, u in enumerate(b["units"]):
            nxt = b["units"][k + 1]["t"] if k + 1 < len(b["units"]) else b["end"]
            if u["vcr"]:
                if cur and u["t"] - cur[1] <= 8:
                    cur[1] = nxt
                else:
                    cur = [u["t"], nxt]
                    vruns.append(cur)
        vcr_html = "".join(
            f"<div class='vcrov' title='녹화 요약(VCR) {mmss(a)}~{mmss(z)}' style='left:{100 * a / total:.3f}%;width:{100 * (z - a) / total:.3f}%'></div>"
            for a, z in vruns)
        fp = FIRST_PRICE.get(b["key"])
        fpl = f"<div class='fp' style='left:{100 * sec(fp) / total:.3f}%' title='첫 가격 언급 {fp}'></div>" if fp else ""
        n_blocks = len(b["blocks"])
        rows.append(f"<div class='row'><div class='nm' style='color:{b['color']}'>{e(b['label'])}<div class='sub'>{n_blocks}개 구간</div></div>"
                    f"<div><div class='bar'>{''.join(segs)}{vcr_html}{fpl}</div>{PV.strip_html(b, total, b['end'])}<div class='marks'>{marks}</div></div></div>")
    ticks = "".join(f"<span style='left:{100 * m * 60 / total:.2f}%'>{m}분</span>" for m in range(0, int(total // 60) + 1, 10))
    legend_main = "".join(f"<span style='font-weight:650'><i style='background:{GROUP_COLORS[g]};width:14px;height:14px'></i>{g}</span>" for g in GROUPS)
    legend = "".join(
        f"<div class='lg'><b style='color:{GROUP_COLORS.get(g, '#787774')}'>{g}</b>"
        + "".join(f"<span title='{e(CODES[k][3])}'><i style='background:{CODES[k][2]}'></i>{CODES[k][0]}</span>"
                  for k in CODES if CODES[k][1] == g and k != "X2") + "</div>"
        for g in GROUPS + ["기타"])
    emph_html = emphasis_section(data)
    review = " · ".join(f"{k} 수정 {v[0]}문장 / VCR {v[1]}문장 (전체 {v[2]})" for k, v in fixes_total.items())

    top_path = os.path.join(HERE, "top_dyson.html")
    TOP = open(top_path, encoding="utf-8").read() if os.path.exists(top_path) else ""
    page = open(os.path.join(HERE, "preview_2an_v2.html"), encoding="utf-8").read()
    # v2 화면 틀(스타일·상세 패널 스크립트)을 재사용하고 본문·데이터만 바꾼다
    head, _, rest = page.partition("<div class=\"wrap\">")
    style_extra = """<style>
.marks{position:relative;height:9px;margin-top:2px}.mk{position:absolute;top:0;width:0;height:0;border-left:4px solid transparent;border-right:4px solid transparent;border-bottom:7px solid #d9730d;transform:translateX(-4px);cursor:help}
.vcrov{position:absolute;top:0;bottom:0;pointer-events:none;z-index:4;border-top:2px dashed #37352f;border-bottom:2px dashed #37352f;
  background-image:repeating-linear-gradient(135deg,rgba(255,255,255,.55) 0 3px,transparent 3px 8px)}
.nm .sub{font-weight:400}
.chip.vcr{outline:1px dashed #787774;outline-offset:1px}
.why{color:#d9730d;font-size:11.5px;margin-left:6px}
""" + PV.STRIP_CSS + """
</style></head>"""
    head = head.replace("</head>", style_extra).replace("2안 미리보기 v2 — 방송 흐름 + 상세 분류", "다이슨 디지털 슬림 — 방송 흐름 비교 (2안)")
    script = rest[rest.index("<script>"):]
    script = script.replace(script[script.index("const P = "):script.index(";\n", script.index("const P = ")) + 2],
                            "const P = " + json.dumps(payload, ensure_ascii=False) + ";\n")
    # 상세 패널이 쓰는 분류 목록도 현재 기준표로 교체(템플릿의 옛 목록을 쓰지 않게)
    ci = script.index("const C = ")
    nl = chr(10)
    script = script[:ci] + "const C = " + json.dumps({k: [v[0], v[1], v[2], v[3]] for k, v in CODES.items()}, ensure_ascii=False) + ";" + nl + script[script.index(nl, ci) + 1:]
    # 묶음 목록·색도 현재 기준으로(템플릿의 옛 "행동" 묶음 이름을 쓰지 않게)
    gi = script.index("const G = ")
    script = script[:gi] + "const G = " + json.dumps(GROUPS, ensure_ascii=False) + ", GC = " + json.dumps(GROUP_COLORS, ensure_ascii=False) + ";" + nl + script[script.index(nl, gi) + 1:]
    # 멘트 줄에 VCR 표시와 검수 사유를 보여주도록 렌더 함수 보강
    script = script.replace(
        "const lines = d.lines.filter(l => !filt || l[1] === filt).map(([t,k,x]) =>\n    `<div class=\"ql\"><span class=\"chip\" style=\"background:${C[k][2]};color:${light(k)?'#37352f':'#fff'}\">${C[k][0]}</span><span class=\"t\">${t}</span>${esc(x)}</div>`).join('');",
        "const lines = d.lines.filter(l => !filt || l[1] === filt).map(([t,k,x,v,w]) =>\n    `<div class=\"ql\"><span class=\"chip${v?' vcr':''}\" style=\"background:${C[k][2]};color:${light(k)?'#37352f':'#fff'}\">${C[k][0]}${v?' · VCR':''}</span><span class=\"t\">${t}</span>${esc(x)}${w?`<span class=\"why\">검수 수정: ${esc(w)}</span>`:''}</div>`).join('');")
    script = script.replace("이전 이름: ${esc(d.old)} · 요약: ${esc(d.summary)} · ", "녹화 요약(VCR) ${Math.round(d.vcr*100)}% · ")
    body = f"""<div class="wrap">
<h1>다이슨 디지털 슬림 — 방송 흐름 비교 (2안)</h1>
<p class="sub"><span class="badge" style="background:#e7f3f8;color:#1f5f7f">2안 · 자막 정독 + 문장 분류</span>생성 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')} · 자막을 문장으로 잇고 15개 기준으로 분류·검수 · 분류가 바뀌는 곳에서 구간을 자르고 {MIN_SEC // 60}분 미만은 가장 비슷한 이웃과 합침</p>
{TOP}

<h2>방송 흐름 한눈에</h2>
<p class="sub">검수 결과 — {e(review)}</p>
<p class="sub">구간을 누르면 아래에 15개·4묶음 상세 분류와 실제 멘트 · <b style="color:#d9730d">▲</b> 조건 추가 멘트 위치(짧아서 구간에 묻혀도 보이게) · 빗금 = 녹화 요약(VCR) 구간 · 빨간 선(₩) 첫 가격 언급</p>
{''.join(rows)}
<div class="axis">{ticks}</div>
<div class="legend"><div class="lg" style="gap:6px 18px">{legend_main}<span class="sub">← 막대 색 = 대분류</span></div></div>
{PV.strip_legend()}
<details style="margin:-4px 0 10px"><summary class="sub" style="cursor:pointer">세부 분류(15개) 보기 — 구간을 누르면 이 기준으로 나뉜 비중이 나옵니다</summary><div class="legend">{legend}</div></details>
<div id="detail"><span class="sub">위 막대에서 구간을 눌러 보세요</span></div>
{emph_html}
{PV.section(data)}
</div>
"""
    out_html = head + body + script
    open(os.path.join(HERE, "preview_2an_v3.html"), "w", encoding="utf-8").write(out_html)
    if os.environ.get("HSB_SAVE"):
        dest = os.path.join("C:/Users/GSR/.claude/HomeshoppingCompareBOT/out/reports", os.environ["HSB_SAVE"])
        open(dest, "w", encoding="utf-8").write(out_html)
        print("saved", dest)
    for b in data:
        print(b["label"], "blocks", len(b["blocks"]), "C2 marks", sum(1 for u in b["units"] if u["code"] == "C2"))
    print(review)


if __name__ == "__main__":
    main()
