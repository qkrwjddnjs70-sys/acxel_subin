"""2안 미리보기 (분류 기준표 16개 + 문장 단위 분류 + 1분 단위 흐름). 앱/저장소에 반영하지 않는 임시 화면."""
import html
import json
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

CODES = {
    # code: (이름, 묶음, 색, 판단 기준)
    "P1": ("상품 및 구성 설명", "상품", "#2383e2", "제품 정체·특징과 본품·툴·거치대 등 구성 설명"),
    "P2": ("스펙·기술", "상품", "#1a5fa8", "무게·에어와트·RPM·필터·사이클론·디스플레이 등 수치·기술"),
    "P4": ("시연", "상품", "#0f7b6c", "지금 눈앞에서 보여주는 장면 설명"),
    "P5": ("생활 공감", "상품", "#7cb69d", "사용 장면·고충 공감(손목·반려동물·집안일)"),
    "C1": ("가격 제시", "조건", "#e03e3e", "가격 숫자·가격대를 말함(첫 공개·반복)"),
    "C2": ("조건 추가", "조건", "#d9730d", "할인·무이자·카드·앱·사은품을 새로 설명·계산"),
    "C3": ("가격 비교·독점", "조건", "#f2a65a", "타사·정상가·과거가 대비, 단독·최저가 주장"),
    "T1": ("브랜드·정품·AS", "신뢰", "#9065b0", "브랜드 역사, 공식 수입 정품, 무상 AS"),
    "T2": ("고객 증언", "신뢰", "#b98fd1", "실제 구매자 후기·상품평 인용"),
    "T3": ("호스트 체험담", "신뢰", "#ad1a72", "쇼호스트·가족·PD의 사용·구매 이야기"),
    "A1": ("희소성 푸시", "푸시", "#7a1f1f", "방송 기회 자체가 드묾: 다음 방송 미정, N일 만, 이번 달 단 한 번"),
    "A2": ("카운트다운 푸시", "푸시", "#b0272d", "남은 시간 압박, 방송 끝나면 사라짐"),
    "A3": ("주문 푸시", "푸시", "#5c5c5c", "앱·ARS 주문 경로, 취소 가능, '주문하세요'"),
    "A4": ("수량 푸시", "푸시", "#c2410c", "남은 수량·매진 임박/예상/발생·대기 폭주로 지금 사라고 압박"),
    "T4": ("인기 푸시", "푸시", "#d36ba6", "동시 접속·누적 매출·주문 폭주 등 인기 숫자로 지금 주문하라고 압박"),
    "X1": ("진행·맞장구", "기타", "#d9d8d5", "판매 내용 없는 반응·전환"),
    "X2": ("요약 반복(VCR)", "기타", "#a8a7a3", "녹화 요약 멘트 반복"),
    "X3": ("잡음", "기타", "#ecebe8", "배경음악 가사·의미 없는 인식 오류"),
}
GROUPS = ["상품", "조건", "신뢰", "푸시"]
GROUP_COLORS = {"상품": "#2383e2", "조건": "#e03e3e", "신뢰": "#9065b0", "푸시": "#7a1f1f"}

BROADCASTS = [
    ("gs0107", "GS샵 1/7", "#2383e2", "1/7(수) 14:35 · 분당주문액 570만"),
    ("gs0217", "GS샵 2/17", "#d9730d", "2/17(화) 22:55 · 분당주문액 579만"),
    ("hd0621", "현대홈쇼핑 6/21", "#0f7b6c", "6/21(일) 12:30 · 분당주문액 714만"),
]


def e(x):
    return html.escape(str(x if x is not None else ""))


def load(key):
    segs = json.load(open(os.path.join(HERE, f"{key}_segments.json"), encoding="utf-8"))
    labels = {}
    for ln in open(os.path.join(HERE, f"{key}_labels.tsv"), encoding="utf-8"):
        p = ln.strip().split("\t")
        if len(p) >= 2 and p[0].isdigit():
            labels[int(p[0])] = p[1].strip().upper()
    for s in segs:
        s["code"] = labels.get(s["i"], "X1")
        if s["code"] not in CODES:
            s["code"] = "X1"
    return segs


def mmss(t):
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def main():
    data = []
    for key, label, color, kpi in BROADCASTS:
        segs = load(key)
        data.append({"key": key, "label": label, "color": color, "kpi": kpi, "segs": segs})
    n_min = max(int(max(s["t"] for s in b["segs"]) // 60) + 1 for b in data)

    # ---- 1분 단위 막대(글자 수 가중) ----
    strips = []
    minute_payload = {}
    for b in data:
        per_min = defaultdict(Counter)
        lines = defaultdict(list)
        for s in b["segs"]:
            m = int(s["t"] // 60)
            per_min[m][s["code"]] += max(len(s["text"]), 1)
            lines[m].append([mmss(s["t"]), s["code"], s["text"]])
        cols = []
        for m in range(n_min):
            c = per_min.get(m)
            if not c:
                cols.append("<div class='mcol empty'></div>")
                continue
            tot = sum(c.values())
            stack = "".join(
                f"<i style='height:{100 * v / tot:.1f}%;background:{CODES[k][2]}'></i>"
                for k, v in sorted(c.items(), key=lambda kv: list(CODES).index(kv[0]))
            )
            top = ", ".join(f"{CODES[k][0]} {100 * v / tot:.0f}%" for k, v in c.most_common(3))
            cols.append(f"<div class='mcol' data-b='{b['key']}' data-m='{m}' title='{m}분: {e(top)}'>{stack}</div>")
            minute_payload[f"{b['key']}:{m}"] = lines[m]
        # 묶음 히트맵 4줄
        lanes = []
        for g in GROUPS:
            cells = []
            for m in range(n_min):
                c = per_min.get(m)
                if not c:
                    cells.append("<div class='hc'></div>")
                    continue
                tot = sum(v for k, v in c.items() if CODES[k][1] != "기타") or 1
                share = sum(v for k, v in c.items() if CODES[k][1] == g) / tot
                cells.append(f"<div class='hc' title='{m}분 {g} {share * 100:.0f}%' "
                             f"style='background:{GROUP_COLORS[g]};opacity:{0.06 + 0.94 * share:.2f}'></div>")
            lanes.append(f"<div class='lane'><span>{g}</span><div class='hrow' style='grid-template-columns:repeat({n_min},1fr)'>{''.join(cells)}</div></div>")
        strips.append(
            f"<div class='bc'><div class='bname' style='color:{b['color']}'>{e(b['label'])} <span class='sub'>{e(b['kpi'])}</span></div>"
            f"<div class='mrow' style='grid-template-columns:repeat({n_min},1fr)'>{''.join(cols)}</div>"
            f"<div class='lanes'>{''.join(lanes)}</div></div>")
    ticks = "".join(f"<span style='left:{100 * m / n_min:.2f}%'>{m}분</span>" for m in range(0, n_min, 10))

    # ---- 비중 표(글자 수 가중, 기타 제외 기준) ----
    shares = {}
    for b in data:
        c = Counter()
        for s in b["segs"]:
            c[s["code"]] += max(len(s["text"]), 1)
        sell = sum(v for k, v in c.items() if CODES[k][1] != "기타") or 1
        shares[b["key"]] = {k: c.get(k, 0) / sell for k in CODES if CODES[k][1] != "기타"}
        shares[b["key"]]["_other"] = sum(v for k, v in c.items() if CODES[k][1] == "기타") / (sum(c.values()) or 1)
    rows = []
    for g in GROUPS:
        ks = [k for k in CODES if CODES[k][1] == g]
        gs = [sum(shares[b["key"]][k] for k in ks) for b in data]
        rows.append("<tr class='grp'><td>" + f"<b style='color:{GROUP_COLORS[g]}'>{g}</b></td>"
                    + "".join(f"<td class='num'><b>{v * 100:.0f}%</b></td>" for v in gs) + "</tr>")
        for k in ks:
            vals = [shares[b["key"]][k] for b in data]
            mx = max(vals)
            cells = "".join(
                f"<td class='num{' top' if v == mx and v > 0 else ''}'><span class='bar'><i style='width:{min(100, v * 250):.0f}%;background:{CODES[k][2]}'></i></span>{v * 100:.1f}%</td>"
                for v in vals)
            rows.append(f"<tr><td><i class='sw' style='background:{CODES[k][2]}'></i>{CODES[k][0]}"
                        f"<div class='sub'>{e(CODES[k][3])}</div></td>{cells}</tr>")
    other = "".join(f"<td class='num sub'>{shares[b['key']]['_other'] * 100:.0f}%</td>" for b in data)
    rows.append(f"<tr><td class='sub'>기타(진행·VCR·잡음) — 전체 대비</td>{other}</tr>")
    share_table = ("<table><thead><tr><th>카테고리</th>"
                   + "".join(f"<th style='color:{b['color']}'>{e(b['label'])}</th>" for b in data)
                   + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")

    # ---- 첫 등장 시각 ----
    keys_first = ["C1", "C2", "C3", "T2", "T4", "A1", "A2"]
    frows = []
    for k in keys_first:
        cells = []
        for b in data:
            hit = next((s for s in b["segs"] if s["code"] == k), None)
            cells.append(f"<td class='num'>{mmss(hit['t']) if hit else '–'}</td>")
        frows.append(f"<tr><td><i class='sw' style='background:{CODES[k][2]}'></i>{CODES[k][0]}</td>{''.join(cells)}</tr>")
    first_table = ("<table><thead><tr><th>카테고리</th>"
                   + "".join(f"<th style='color:{b['color']}'>{e(b['label'])}</th>" for b in data)
                   + "</tr></thead><tbody>" + "".join(frows) + "</tbody></table>")

    # ---- 대표 멘트(조건·신뢰·행동 위주) ----
    ex_keys = ["C2", "C3", "T2", "T3", "T4", "A1"]
    excols = []
    for b in data:
        items = []
        for k in ex_keys:
            cand = [s for s in b["segs"] if s["code"] == k and 15 <= len(s["text"]) <= 120]
            cand.sort(key=lambda s: -len(s["text"]))
            if cand:
                s = cand[0]
                items.append(f"<div class='ex'><span class='chip' style='background:{CODES[k][2]}'>{CODES[k][0]}</span>"
                             f"<span class='t'>{mmss(s['t'])}</span> “{e(s['text'])}”</div>")
        excols.append(f"<div class='col' style='--c:{b['color']}'><h3 style='color:{b['color']}'>{e(b['label'])}</h3>{''.join(items)}</div>")

    legend = "".join(
        f"<div class='lg'><b style='color:{GROUP_COLORS.get(g, '#787774')}'>{g}</b>"
        + "".join(f"<span title='{e(CODES[k][3])}'><i style='background:{CODES[k][2]}'></i>{CODES[k][0]}</span>"
                  for k in CODES if CODES[k][1] == g) + "</div>"
        for g in GROUPS + ["기타"])

    total_lines = sum(len(b["segs"]) for b in data)
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>2안 미리보기 — 분류 기준표 적용</title><style>
:root{{--tx:#37352f;--tx2:rgba(55,53,47,.72);--tx3:rgba(55,53,47,.5);--line:#e9e9e7;--line2:#f1f1ef;--panel2:#f7f6f3;--accent:#2383e2}}
*{{box-sizing:border-box}}body{{margin:0;background:#fff;color:var(--tx);font-size:15px;line-height:1.6;font-family:Pretendard,ui-sans-serif,-apple-system,'Segoe UI','Malgun Gothic',sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:44px 24px 80px}}
h1{{font-size:28px;margin:0 0 6px;letter-spacing:-.02em}} h2{{font-size:20px;font-weight:650;margin:38px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}}
h3{{font-size:15px;margin:0 0 8px}} .sub{{color:var(--tx3);font-size:12.5px}}
.badge{{display:inline-block;font-size:12px;padding:1px 8px;border-radius:4px;background:#fdebec;color:#a02a2a;margin-right:6px}}
.callout{{background:#fbf3db;border-radius:6px;padding:12px 16px;margin:14px 0;font-size:14px}}
.legend{{display:grid;gap:4px;margin:10px 0 18px;font-size:12.5px;color:var(--tx2)}}
.lg{{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center}} .lg b{{width:34px}}
.lg i,.sw{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}}
.lg span{{cursor:help}}
.bc{{margin:18px 0 22px}} .bname{{font-weight:650;margin-bottom:6px}}
.mrow{{display:grid;gap:1px;height:70px;align-items:end}}
.mcol{{height:100%;display:flex;flex-direction:column-reverse;border-radius:2px;overflow:hidden;cursor:pointer;background:var(--line2)}}
.mcol i{{display:block;width:100%}} .mcol:hover{{outline:2px solid var(--tx)}} .mcol.sel{{outline:2px solid var(--accent)}}
.mcol.empty{{background:transparent;cursor:default}}
.lanes{{margin-top:3px;display:grid;gap:1px}} .lane{{display:grid;grid-template-columns:34px 1fr;align-items:center;font-size:10.5px;color:var(--tx3)}}
.hrow{{display:grid;gap:1px;height:9px}} .hc{{border-radius:1px;background:var(--line2)}}
.axis{{position:relative;height:16px;margin:2px 0 0 34px;font-size:11px;color:var(--tx3)}} .axis span{{position:absolute;transform:translateX(-50%)}}
#detail{{border:1px solid var(--line);border-radius:6px;padding:12px 14px;margin:10px 0;min-height:60px;font-size:13.5px}}
#detail .ln{{padding:4px 0;border-bottom:1px solid var(--line2)}} #detail .ln:last-child{{border-bottom:0}}
.chip{{display:inline-block;color:#fff;font-size:11px;border-radius:3px;padding:0 6px;margin-right:6px;white-space:nowrap}}
.t{{color:var(--accent);font-variant-numeric:tabular-nums;font-size:12px;margin-right:4px}}
table{{border-collapse:collapse;width:100%;font-size:13.5px}} th,td{{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{background:var(--panel2);color:var(--tx3);font-weight:500;font-size:12.5px}} td.num{{white-space:nowrap;font-variant-numeric:tabular-nums}}
tr.grp td{{background:#fbfbfa}} td.top{{font-weight:700}}
.bar{{display:inline-block;width:56px;height:8px;background:var(--line2);border-radius:2px;margin-right:6px;vertical-align:0;overflow:hidden}} .bar i{{display:block;height:100%}}
.cols{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}}
.col{{border:1px solid var(--line);border-top:3px solid var(--c);border-radius:6px;padding:12px 14px}} .ex{{font-size:13px;color:var(--tx2);padding:6px 0;border-bottom:1px solid var(--line2)}}
</style></head><body><div class="wrap">
<h1>다이슨 디지털 슬림 — 방송 흐름 비교 (2안 · 분류 기준표 적용)</h1>
<p class="sub"><span class="badge">미리보기 · 저장 안 됨</span>자막 {total_lines:,}문장을 16개 기준으로 한 문장씩 분류 · 1분 단위 비중은 글자 수 기준</p>
<div class="callout">막대 하나 = 1분. 색이 쌓인 비율이 그 1분에 말한 내용의 구성입니다. 아래 4줄은 <b>상품·조건·신뢰·행동</b> 묶음이 그 1분에서 차지한 비중(진할수록 많음). <b>막대를 누르면 그 1분의 실제 멘트와 분류</b>가 아래에 나옵니다.</div>
<div class="legend">{legend}</div>

<h2>1. 1분 단위 흐름</h2>
{''.join(strips)}
<div class="axis">{ticks}</div>
<div id="detail"><span class="sub">막대를 눌러 보세요</span></div>

<h2>2. 무엇에 얼마나 썼나 <span class="sub">판매 멘트(기타 제외) 중 비중 · 굵은 값이 세 방송 중 최대</span></h2>
{share_table}

<h2>3. 언제 처음 꺼냈나</h2>
{first_table}

<h2>4. 카테고리별 대표 멘트</h2>
<div class="cols">{''.join(excols)}</div>
</div>
<script>
const MIN = {json.dumps(minute_payload, ensure_ascii=False)};
const CODES = {json.dumps({k: [v[0], v[2]] for k, v in CODES.items()}, ensure_ascii=False)};
const NAMES = {json.dumps({b[0]: b[1] for b in BROADCASTS}, ensure_ascii=False)};
const esc = s => String(s).replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
document.querySelectorAll('.mcol[data-b]').forEach(el => el.addEventListener('click', () => {{
  document.querySelectorAll('.mcol.sel').forEach(x => x.classList.remove('sel')); el.classList.add('sel');
  const rows = MIN[el.dataset.b + ':' + el.dataset.m] || [];
  document.getElementById('detail').innerHTML = `<h3>${{NAMES[el.dataset.b]}} · ${{el.dataset.m}}분</h3>` + rows.map(([t,c,x]) =>
    `<div class="ln"><span class="chip" style="background:${{CODES[c][1]}};${{c.startsWith('X')?'color:#37352f':''}}">${{CODES[c][0]}}</span><span class="t">${{t}}</span>${{esc(x)}}</div>`).join('');
}}));
</script></body></html>"""
    open(os.path.join(HERE, "preview_2an.html"), "w", encoding="utf-8").write(page)
    print("ok", os.path.join(HERE, "preview_2an.html"))


if __name__ == "__main__":
    main()
