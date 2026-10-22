"""2안 리포트: 자막을 '읽고' 정리한 방송 흐름·강조점·설득 기법 비교 (화이트 노션 톤).

1안(report.py)이 키워드 횟수로 재는 정량 리포트라면, 2안은 사람이(또는 Claude가) 자막 전체를 읽고
정리한 해석을 시각화한다. 입력은 방송별 분석 JSON + 종합 JSON:

    broadcasts: [{label, color, kpi: {...}, analysis: {phases, first_price_mention, offer,
                  top_emphases, tactics, closing_pattern, tone, weak_points}}]
    synthesis:  {headline, differences: [..], why: [..], takeaways: [..], caveats: [..]}
"""
from __future__ import annotations

import html
from datetime import datetime

PHASE_COLORS = {
    "오프닝": "#9b9a97", "상품 소개": "#2383e2", "구성 소개": "#9f6b53", "시연": "#0f7b6c",
    "가격 공개": "#e03e3e", "조건 강화": "#d9730d", "고객 증언": "#9065b0", "브랜드 신뢰": "#ad1a72",
    "생활 공감": "#cb912f", "마감 압박": "#b0272d", "기타": "#c7c6c3",
}

CSS = """
:root{--tx:#37352f;--tx2:rgba(55,53,47,.72);--tx3:rgba(55,53,47,.5);--line:#e9e9e7;--line2:#f1f1ef;--panel2:#f7f6f3;
  --accent:#2383e2;--hl-yellow:#fbf3db;--hl-blue:#e7f3f8;--hl-red:#fdebec;--hl-green:#edf3ec}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--tx);font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased;
  font-family:Pretendard,ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI','Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:56px 24px 96px}
h1{font-size:32px;font-weight:700;margin:0 0 8px;letter-spacing:-.02em;line-height:1.25}
h2{font-size:22px;font-weight:650;margin:44px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:16px;font-weight:650;margin:0 0 8px}
p{margin:8px 0}
.sub{color:var(--tx3);font-size:13.5px}
.badge{display:inline-block;font-size:12px;padding:1px 8px;border-radius:4px;background:var(--hl-blue);color:#1f5f7f;margin-right:6px;vertical-align:2px}
.callout{background:var(--hl-yellow);border-radius:6px;padding:16px 18px;margin:16px 0;font-size:15.5px}
.callout b{font-weight:650}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:16px 0}
.kpi{border:1px solid var(--line);border-radius:6px;padding:12px 14px;border-top:3px solid var(--c)}
.kpi .n{font-weight:650}
.kpi .v{font-size:22px;font-weight:700;margin-top:4px;font-variant-numeric:tabular-nums}
.kpi .s{font-size:12.5px;color:var(--tx3)}
/* 흐름 타임라인 */
.tl{margin:10px 0 18px}
.tl-row{display:grid;grid-template-columns:132px 1fr;gap:10px;align-items:center;margin:8px 0}
.tl-name{font-weight:650;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tl-bar{position:relative;height:34px;border-radius:4px;background:var(--line2);overflow:visible}
.tl-seg{position:absolute;top:0;bottom:0;border-right:2px solid #fff;color:#fff;font-size:11px;line-height:34px;
  padding:0 4px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;cursor:default}
.tl-seg:first-child{border-radius:4px 0 0 4px}
.tl-price{position:absolute;top:-7px;width:2px;height:48px;background:#e03e3e}
.tl-price::after{content:'₩';position:absolute;top:-16px;left:-4px;font-size:11px;color:#e03e3e;font-weight:700}
.tl-axis{display:grid;grid-template-columns:132px 1fr;gap:10px;font-size:11px;color:var(--tx3)}
.tl-axis div:last-child{display:flex;justify-content:space-between}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12.5px;color:var(--tx2);margin:10px 0}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
/* 구간 표 */
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:var(--panel2);color:var(--tx3);font-weight:500;font-size:13px}
.ph{display:inline-block;font-size:11.5px;color:#fff;border-radius:3px;padding:0 6px;white-space:nowrap}
.q{color:var(--tx2);font-size:13px}
.t{color:var(--accent);font-variant-numeric:tabular-nums;font-size:12.5px;white-space:nowrap}
/* 3열 비교 카드 */
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.col{border:1px solid var(--line);border-radius:6px;padding:14px 16px;border-top:3px solid var(--c)}
.emp{padding:8px 0;border-bottom:1px solid var(--line2)}
.emp:last-child{border-bottom:0}
.emp .th{font-weight:650}
.lvl{font-size:11.5px;border-radius:3px;padding:0 6px;margin-left:6px}
.lvl.높음{background:var(--hl-red);color:#a02a2a}.lvl.중간{background:var(--hl-yellow);color:#8a6a16}.lvl.낮음{background:var(--line2);color:var(--tx3)}
.ev{font-size:13px;color:var(--tx2);margin-top:4px;padding-left:8px;border-left:2px solid var(--line)}
ul{margin:6px 0;padding-left:20px} li{margin:4px 0}
.why li{margin:8px 0}
details summary{cursor:pointer;color:var(--tx3);font-size:13px}
footer{margin-top:48px;color:var(--tx3);font-size:13px;border-top:1px solid var(--line);padding-top:14px}
"""


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _sec(ts: str) -> float:
    try:
        parts = [int(p) for p in str(ts).split(":")]
    except ValueError:
        return 0.0
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return 0.0


def _won(v) -> str:
    if v is None:
        return "–"
    v = float(v)
    return f"{v / 1e8:.2f}억" if v >= 1e8 else f"{v / 1e4:,.0f}만"


def _timeline(bcs: list[dict]) -> str:
    total = max((max((_sec(p["end"]) for p in b["analysis"].get("phases", [])), default=3600) for b in bcs), default=3600)
    total = max(total, 60)
    rows = []
    for b in bcs:
        segs = []
        for p in b["analysis"].get("phases", []):
            s, e = _sec(p["start"]), _sec(p["end"])
            if e <= s:
                continue
            col = PHASE_COLORS.get(p.get("phase"), PHASE_COLORS["기타"])
            tip = f'{p["start"]}~{p["end"]} {p.get("phase","")}: {p.get("summary","")}'
            segs.append(
                f"<div class='tl-seg' title='{_e(tip)}' style='left:{100*s/total:.2f}%;width:{100*(e-s)/total:.2f}%;background:{col}'>"
                f"{_e(p.get('phase',''))}</div>")
        fp = (b["analysis"].get("first_price_mention") or {}).get("time")
        price = f"<div class='tl-price' title='첫 가격 언급 {_e(fp)}' style='left:{100*_sec(fp)/total:.2f}%'></div>" if fp else ""
        rows.append(f"<div class='tl-row'><div class='tl-name' style='color:{b['color']}'>{_e(b['label'])}</div>"
                    f"<div class='tl-bar'>{''.join(segs)}{price}</div></div>")
    ticks = "".join(f"<span>{m}분</span>" for m in range(0, int(total // 60) + 1, 10))
    legend = "".join(f"<span><i style='background:{c}'></i>{_e(k)}</span>" for k, c in PHASE_COLORS.items())
    return (f"<div class='tl'>{''.join(rows)}<div class='tl-axis'><div></div><div>{ticks}</div></div></div>"
            f"<div class='legend'>{legend}<span><i style='background:#e03e3e;width:2px'></i>₩ 첫 가격 언급</span></div>")


def _phase_table(b: dict) -> str:
    rows = "".join(
        f"<tr><td class='t'>{_e(p['start'])}~{_e(p['end'])}</td>"
        f"<td><span class='ph' style='background:{PHASE_COLORS.get(p.get('phase'), '#c7c6c3')}'>{_e(p.get('phase'))}</span></td>"
        f"<td>{_e(p.get('summary'))}<div class='q'>“{_e(p.get('quote'))}”</div></td></tr>"
        for p in b["analysis"].get("phases", [])
    )
    return (f"<details><summary>{_e(b['label'])} 구간별 상세 보기</summary>"
            f"<table><thead><tr><th style='width:110px'>구간</th><th style='width:90px'>단계</th><th>내용</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></details>")


def render(data: dict) -> str:
    bcs = data["broadcasts"]
    syn = data.get("synthesis", {})
    title = data.get("title", "방송 흐름 비교")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    kpis = "".join(
        f"<div class='kpi' style='--c:{b['color']}'><div class='n' style='color:{b['color']}'>{_e(b['label'])}</div>"
        f"<div class='v'>{_e(_won((b.get('kpi') or {}).get('rpwm')))}<span class='s'> /가중분</span></div>"
        f"<div class='s'>매출 {_e(_won((b.get('kpi') or {}).get('revenue')))} · {_e((b.get('kpi') or {}).get('when',''))}</div>"
        f"<div class='s'>{_e(b['analysis'].get('tone',''))}</div></div>"
        for b in bcs)

    emph_cols = "".join(
        f"<div class='col' style='--c:{b['color']}'><h3 style='color:{b['color']}'>{_e(b['label'])}</h3>"
        + "".join(
            f"<div class='emp'><span class='th'>{i + 1}. {_e(t.get('theme'))}</span>"
            f"<span class='lvl {_e(t.get('how_much'))}'>{_e(t.get('how_much'))}</span>"
            f"<div class='sub'>{_e(t.get('why_it_matters'))}</div>"
            + "".join(f"<div class='ev'><span class='t'>{_e(e.get('time'))}</span> “{_e(e.get('quote'))}”</div>"
                      for e in (t.get('evidence') or [])[:2])
            + "</div>"
            for i, t in enumerate(b["analysis"].get("top_emphases", [])))
        + "</div>"
        for b in bcs)

    tactic_cols = "".join(
        f"<div class='col' style='--c:{b['color']}'><h3 style='color:{b['color']}'>{_e(b['label'])}</h3><ul>"
        + "".join(f"<li><b>{_e(t.get('name'))}</b><div class='ev'><span class='t'>{_e(t.get('example_time'))}</span> “{_e(t.get('example'))}”</div></li>"
                  for t in b["analysis"].get("tactics", []))
        + "</ul>"
        f"<p class='sub' style='margin-top:10px'><b>마감 패턴</b> — {_e(b['analysis'].get('closing_pattern'))}</p>"
        f"<p class='sub'><b>첫 가격 언급</b> — {_e((b['analysis'].get('first_price_mention') or {}).get('time'))} · "
        f"{_e((b['analysis'].get('first_price_mention') or {}).get('how'))}</p>"
        f"<p class='sub'><b>아쉬운 점</b> — {_e(' / '.join(b['analysis'].get('weak_points', [])))}</p></div>"
        for b in bcs)

    def _ul(items, cls=""):
        return f"<ul class='{cls}'>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>" if items else ""

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(title)}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>{_e(title)}</h1>
<p class="sub"><span class="badge">2안 · 자막 정독 분석</span>방송 {len(bcs)}건 · 생성 {now} · 자막 전체를 읽고 흐름·강조점·설득 기법을 정리했습니다(해석이 포함됨)</p>

<div class="callout">{syn.get('headline', '')}</div>

<div class="kpis">{kpis}</div>

<h2>1. 방송 흐름 한눈에</h2>
<p class="sub">막대에 마우스를 올리면 구간 요약이 보입니다 · 빨간 선(₩)은 처음 가격을 꺼낸 시점</p>
{_timeline(bcs)}
{''.join(_phase_table(b) for b in bcs)}

<h2>2. 무엇을 가장 강조했나</h2>
<div class="cols">{emph_cols}</div>

<h2>3. 결정적 차이</h2>
{_ul(syn.get('differences', []))}

<h2>4. 설득 기법 · 마감 방식</h2>
<div class="cols">{tactic_cols}</div>

<h2>5. 왜 이런 결과가 나왔나</h2>
{_ul(syn.get('why', []), 'why')}

<h2>6. GS가 가져갈 것</h2>
{_ul(syn.get('takeaways', []), 'why')}

<footer>{_ul(syn.get('caveats', []))}</footer>
</div></body></html>"""
