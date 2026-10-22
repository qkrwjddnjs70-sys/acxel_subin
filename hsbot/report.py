"""비교 결과 → 다크모드 HTML 리포트."""
from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any

from .compare import ComparisonResult
from .discover import model_key
from .metrics import BroadcastMetrics
from .time_weight import channel_kind

CHANNEL_COLORS = [  # 노션 톤 — 흰 배경에서 글자로 써도 읽히는 진한 색
    "#2383e2", "#d9730d", "#0f7b6c", "#e03e3e", "#9065b0", "#9f6b53",
    "#ad1a72", "#448361", "#787774",
]

CSS = """
/* 화이트 노션 톤 (2026-10-21) */
:root{
  --bg:#ffffff; --panel:#ffffff; --panel2:#f7f6f3; --line:#e9e9e7; --line2:#f1f1ef;
  --tx:#37352f; --tx2:rgba(55,53,47,.72); --tx3:rgba(55,53,47,.5);
  --good:#0f7b6c; --warn:#d9730d; --bad:#e03e3e; --accent:#2383e2;
  --hl-blue:#e7f3f8; --hl-red:#fdebec; --hl-yellow:#fbf3db; --hl-green:#edf3ec; --hl-gray:#f1f1ef;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
  font-family:Pretendard,ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI','Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif;
  font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:56px 24px 96px}
h1{font-size:32px;font-weight:700;margin:0 0 8px;letter-spacing:-.02em;line-height:1.25}
h2{font-size:22px;font-weight:650;margin:44px 0 10px;letter-spacing:-.01em;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:16px;font-weight:600;margin:20px 0 8px;color:var(--tx)}
p{margin:8px 0}
.sub{color:var(--tx3);font-size:13.5px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:16px 18px;margin:14px 0}
.panel>b:first-child{font-size:16px;font-weight:650}
.note{background:var(--hl-yellow);border-radius:6px;padding:12px 16px;font-size:14px;color:var(--tx)}
.grid{display:grid;gap:12px}
.cards{grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px 16px;border-top:3px solid var(--ch,#2383e2)}
.card .name{font-weight:700;font-size:16px;margin-bottom:2px}
.kv{display:flex;justify-content:space-between;gap:10px;padding:4px 0;font-size:14px;border-bottom:1px solid var(--line2)}
.kv:last-child{border-bottom:0}
.kv span:first-child{color:var(--tx3)}
.tag{display:inline-block;padding:1px 8px;border-radius:4px;font-size:12.5px;margin:2px 4px 2px 0;background:var(--hl-blue);color:#1f5f7f}
.tag.dn{background:var(--hl-red);color:#a02a2a}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:14px;min-width:520px}
th,td{padding:9px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--tx3);font-weight:500;font-size:13px;background:var(--panel2);position:sticky;top:0}
td:first-child,th:first-child{text-align:left;white-space:normal}
tbody tr:hover{background:var(--panel2)}
.num{font-variant-numeric:tabular-nums}
.bar{position:relative;height:14px;border-radius:3px;background:var(--line2);overflow:hidden;min-width:70px}
.bar>i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;display:block}
.kind{font-size:12px;padding:1px 8px;border-radius:4px;white-space:nowrap}
.kind.live{background:var(--hl-red);color:#a02a2a}.kind.tc{background:var(--hl-blue);color:#1f5f7f}
.cmp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px;margin-top:16px}
.cmp-h{font-size:13px;color:var(--tx2);margin-bottom:6px;font-weight:600}
.cmp-row{display:grid;grid-template-columns:100px 1fr 78px;gap:8px;align-items:center;margin:5px 0;font-size:13px}
.cmp-ch{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.cmp-v{text-align:right;font-variant-numeric:tabular-nums}
/* 방송 조건 비교표: 줄바꿈해서라도 한눈에 */
.ctable{table-layout:fixed;min-width:640px}
.ctable td,.ctable th{vertical-align:top;white-space:normal;text-align:left;word-break:keep-all;overflow-wrap:anywhere}
.ctable th.ck{width:118px;color:var(--tx2);font-weight:600;background:var(--panel2)}
.ctable thead th{font-size:14px;color:var(--tx);font-weight:650}
.ctable .cv{font-size:14.5px;line-height:1.55;font-weight:500}
.ctable .cv .ln{display:block}
.ctable .cv .dim{color:var(--tx3);font-weight:400;font-size:13px}
.ctable .none{color:var(--tx3)}
.ctable details{margin-top:4px}
.ctable summary{cursor:pointer;list-style:none;font-size:12px;color:var(--tx3);display:inline-block}
.ctable summary::-webkit-details-marker{display:none}
.ctable summary::before{content:'▸ '}
.ctable details[open] summary::before{content:'▾ '}
.ctable .cq{font-size:12.5px;color:var(--tx2);margin:6px 0 0;line-height:1.5;padding-left:8px;border-left:2px solid var(--line)}
.ctable .ct{color:var(--accent);font-variant-numeric:tabular-nums;margin-right:4px}
.lead-cell{background:var(--hl-yellow);border-radius:4px;font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:13px;color:var(--tx2);margin:8px 0 2px}
.legend b{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.hm{display:grid;gap:2px;margin:2px 0}
.hm .lbl{font-size:13px;color:var(--tx2);text-align:right;padding-right:8px;white-space:nowrap;line-height:28px;font-weight:500}
.hm .cell{height:28px;border-radius:3px;background:var(--line2);margin-bottom:2px}
.hm .hd{font-size:12px;color:var(--tx3);text-align:center;line-height:20px;font-weight:500}
.up{color:var(--good)} .dn{color:var(--bad)} .mid{color:var(--tx2)}
code{background:var(--panel2);padding:1px 5px;border-radius:3px;font-size:13px;color:#eb5757}
ul{margin:6px 0;padding-left:20px} li{margin:3px 0}
footer{margin-top:48px;color:var(--tx3);font-size:13px;border-top:1px solid var(--line);padding-top:14px}
.clickable{cursor:pointer}
.clickable:hover{outline:1px solid rgba(55,53,47,.25)}
#quoteOverlay{display:none;position:fixed;inset:0;background:rgba(15,15,15,.35);z-index:50;align-items:center;justify-content:center;padding:20px}
#quoteOverlay.open{display:flex}
#quoteModal{background:#fff;border:1px solid var(--line);border-radius:8px;box-shadow:0 12px 32px rgba(15,15,15,.15);max-width:640px;width:100%;max-height:80vh;overflow-y:auto;padding:18px 20px}
#quoteModal h3{margin:0 0 4px}
#quoteModal .close{float:right;cursor:pointer;color:var(--tx3);font-size:20px;line-height:1}
.qline{padding:8px 0;border-bottom:1px solid var(--line2);font-size:14px}
.qline .t{color:var(--tx3);font-size:12.5px;margin-right:8px}
.qline mark{background:var(--hl-yellow);color:inherit;border-radius:3px;padding:0 2px}
.hm .cell.mcell{cursor:pointer;position:relative}
.hm .cell.mcell:hover{outline:1px solid rgba(55,53,47,.4)}
.hm .cell.rbar{cursor:pointer;position:relative}
.hm .cell.rbar:hover{outline:1px solid rgba(55,53,47,.4)}
.hm .cell.rbar.miss::after{content:'';position:absolute;left:50%;bottom:-6px;width:5px;height:5px;
  margin-left:-2.5px;border-radius:50%;background:var(--bad)}
.raxis{margin-top:8px;display:flex;justify-content:space-between;font-size:11px;color:var(--tx3)}
"""


def _e(x: Any) -> str:
    return html.escape(str(x))


def _fmt(v: Any, digits: int = 1) -> str:
    if v is None:
        return "<span class='mid'>–</span>"
    if isinstance(v, float):
        return f"{v:,.{digits}f}"
    if isinstance(v, int):
        return f"{v:,}"
    return _e(v)


def _bar(pct: float, color: str) -> str:
    return f"<div class='bar'><i style='width:{max(2.0, min(100.0, pct)):.1f}%;background:{color}'></i></div>"


def _channel_color(i: int) -> str:
    return CHANNEL_COLORS[i % len(CHANNEL_COLORS)]


# ---------------- 섹션 ----------------

def _summary_prose(res: ComparisonResult, colors: dict[str, str]) -> str:
    """정량 지표를 카드 대신 줄글 한 단락으로 — 숫자를 읽는 게 아니라 '무슨 전략인지'를 읽게 한다."""
    paras = []
    for m in res.metrics:
        p = res.profile[m.broadcast_id]
        name = f"<b style='color:{colors[m.broadcast_id]}'>{_e(m.channel_name)}</b>"

        strong_bits = [f"{_e(l)}({v:.0f})" for _, l, v in p["strong_axes"]]
        weak_bits = [f"{_e(l)}({v:.0f})" for _, l, v in p["weak_axes"]]
        promo_sorted = sorted(p["promo_axes"], key=lambda kv: -kv[2])
        promo_bits = [f"{_e(l)} 분당 {v:.1f}회" for _, l, v in promo_sorted]

        s = f"<p>{name}은 "
        if p["revenue"] is not None:
            s += f"<b>편성 추정 매출 {p['revenue']:,}원</b>"
            if p["sales_count"] is not None:
                s += f"(판매 {p['sales_count']:,}건)"
            if p["revenue_per_weighted_min"] is not None:
                s += (
                    ", <span title='홈쇼핑모아 추정매출/가중분'>분당주문액</span> "
                    f"{p['revenue_per_weighted_min']:,.0f}원"
                )
            s += " 기록으로, "
        s += (", ".join(promo_bits) + "로 판촉 수단을 썼고, " if promo_bits else "")
        s += (", ".join(strong_bits) + "을 특히 강하게 밀었습니다." if strong_bits
              else "제품 소구축 사이에 뚜렷한 강점이 보이지 않습니다.")
        if weak_bits:
            s += f" 반면 {', '.join(weak_bits)}은 상대적으로 적게 다뤘습니다."
        s += (
            f" 가격은 {_e(p['first_price_at'] or '언급 없음')}에 처음 꺼냈고,"
            f" 마감압박은 {_e(p['first_urgency_at'] or '없음')}부터 시작했습니다."
        )
        if p["lowest_price"]:
            s += f" 언급된 가장 낮은 가격은 {p['lowest_price']:,}원입니다."
        s += f" 발화 속도는 분당 {m.chars_per_min:,.0f}자, 반복지수는 {m.repetition_index*100:.0f}%였습니다.</p>"
        paras.append(s)
    return "\n".join(paras) + (
        "\n<p class=\"sub\">· 강점/약점축은 판촉 수단(혜택·콜유도)을 뺀 제품 소구축 중 채널 간 편차가 큰 것만 뽑습니다."
        " 방송이 2개뿐이면 한쪽이 0회인 축은 지수가 항상 200으로 찍히니, 정확한 크기는 2번 소구축 비교표(분당 횟수)를 참고하세요."
        " · <b title='홈쇼핑모아 추정매출/가중분'>분당주문액</b>은 편성 추정 매출을 방송 길이(분)로 그냥 나눈 게 아니라, 그 방송이 깔고 있던 분들의"
        " 시간대별 수요 가중치(일요일 새벽 1시대는 평균의 약 20~30%대, 저녁 황금시간대는 100%를 넘김)를"
        " 합산한 '가중 분(weighted minutes)'으로 나눈 값입니다. 새벽 방송이 매출이 적은 건 당연한데 그걸 그냥"
        " 분당으로 비교하면 불리하게 보이는 걸 보정합니다.</p>"
    )


def _axis_table_grid(
    res: ComparisonResult, axes: list, colors: dict[str, str]
) -> str:
    """소구축 비교 표 1장을 그린다. `axes`로 어느 버전(가산/순수)을 그릴지 받는다."""
    ids = res.ids
    name = {m.broadcast_id: m.channel_name for m in res.metrics}
    rpwm = {m.broadcast_id: m.revenue_per_weighted_min for m in res.metrics}
    head = "".join(
        f"<th style='text-align:center;color:{colors[b]}'>{_e(name[b])}"
        + (
            f"<div class='sub' style='font-weight:400' title='홈쇼핑모아 추정매출/가중분'>"
            f"분당주문액 {rpwm[b]:,.0f}원</div>"
            if rpwm.get(b) is not None else ""
        )
        + "</th>"
        for b in ids
    )
    rows = []
    # 막대는 그 행(축)만의 최대값이 아니라 표 전체에서 가장 높은 값(= 1위 셀)
    # 하나를 기준으로 상대 강도를 그린다. 그래야 축끼리도 "이 축이 저 축보다
    # 실제로 더 세게 밀렸다"를 막대 길이로 바로 비교할 수 있다.
    global_mx = max((v for a in axes for v in a.values.values()), default=0.0) or 1.0
    for a in axes:
        leader_name = name.get(a.leader, "–")
        leader_color = colors.get(a.leader, "var(--tx)")
        cells = []
        for b in ids:
            v = a.values.get(b, 0.0)
            is_leader = b == a.leader and v > 0
            crown = " 👑" if is_leader else ""
            cls = "lead-cell" if is_leader else ""
            has_quotes = bool(res.by_id(b).axes.get(a.key) and res.by_id(b).axes[a.key].example_lines)
            click_attrs = f" data-bid='{_e(b)}' data-axis='{_e(a.key)}'" if has_quotes else ""
            cls2 = f"{cls} clickable".strip() if has_quotes else cls
            cells.append(
                f"<td class='num {cls2}' style='min-width:110px'{click_attrs}>{_bar(100 * v / global_mx, colors[b])}"
                f"<span class='sub num'>{v:.2f}{crown}</span></td>"
            )
        flag = " 🔺" if a.key in res.differentiating_axes else ""
        rows.append(
            f"<tr><td><b style='color:{a.color}'>■</b> {_e(a.label)}{flag}"
            f"<div class='sub'>1위 <b style='color:{leader_color}'>{_e(leader_name)}</b> · 편차 ×{a.spread:.2f}</div>"
            f"</td>{''.join(cells)}</tr>"
        )
    return (
        f"<div class='scroll'><table><thead><tr><th>소구축</th>{head}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"<p class=\"sub\">· 막대는 <b>분당 등장 횟수</b>이며 범례와 같은 채널 색으로 표시합니다. 길이는 그 축만의"
        f" 최대값이 아니라 <b>표 전체에서 가장 높은 값 하나</b>({global_mx:.2f})를 100%로 둔 상대 강도라서,"
        f' 축끼리도 막대 길이로 "어느 축이 실제로 더 세게 밀렸는지" 바로 비교됩니다. 👑 = 그 축을 가장 강하게 민 채널.</p>'
    )


def _axis_table(res: ComparisonResult, colors: dict[str, str]) -> str:
    any_native = any(m.has_native_rhythm for m in res.metrics)
    weighted_html = _axis_table_grid(res, res.axes, colors)
    toggle = ""
    raw_block = ""
    if any_native:
        raw_html = _axis_table_grid(res, res.axes_raw, colors)
        toggle = (
            "<label class='sub' style='display:inline-flex;align-items:center;gap:6px;margin-bottom:8px;cursor:pointer'>"
            "<input type='checkbox' id='boostToggle' checked>"
            "판촉강도(소스 강조 태깅) 가산점 반영</label>"
        )
        raw_block = f"<div id='axisRaw' style='display:none'>{raw_html}</div>"
        weighted_html = f"<div id='axisWeighted'>{weighted_html}</div>"
    boost_note = (
        " · 소스가 그 멘트가 나온 분(分)을 강조(판촉강도%)로 태깅했다면, 3번 방송 타임라인의 '리듬'과"
        " 같은 가중치로 그 멘트의 점수를 가산했습니다(예: 그 분이 60% 강도였으면 1.6배). 감점은 없고"
        " 데이터가 없는 분·방송은 그대로(1배) 집니다. 체크박스를 끄면 가산 없는 순수 횟수 기준으로 바뀝니다."
        if any_native else ""
    )
    script = (
        """<script>document.getElementById('boostToggle').addEventListener('change', (e) => {
  document.getElementById('axisWeighted').style.display = e.target.checked ? '' : 'none';
  document.getElementById('axisRaw').style.display = e.target.checked ? 'none' : '';
});</script>"""
        if any_native else ""
    )
    return (
        f"{toggle}{weighted_html}{raw_block}"
        "<p class=\"sub\">· 🔺 표시는 채널 간 편차가 큰 축, 즉 <b>판매 전략이 실제로 갈린 지점</b>입니다."
        " 축은 상호배타적이지 않습니다. 한 문장이 가격·긴급을 동시에 자극하면 양쪽에 카운트됩니다."
        f" 셀 테두리가 밝아지는(클릭 가능한) 칸을 누르면 그 채널이 실제로 뭐라고 말했는지(멘트) 볼 수 있습니다.{boost_note}</p>"
        f"{script}"
    )


def _numeric_table(res: ComparisonResult) -> str:
    rows = []
    for m in res.metrics:
        n = m.numeric
        prices = ", ".join(f"{p:,}" for p in n.distinct_prices[:6]) or "–"
        rows.append(f"""<tr>
<td>{_e(m.channel_name)}</td>
<td class="num">{n.price_mentions}</td>
<td class="num">{n.price_mentions_per_min:.2f}</td>
<td class="num">{_fmt(n.lowest_price)}</td>
<td class="num">{_fmt(n.highest_price)}</td>
<td class="num">{n.percent_mentions}</td>
<td class="num">{_fmt(n.max_percent)}</td>
<td class="num">{n.installment_mentions}</td>
<td class="num">{_fmt(n.max_installment_months, 0)}</td>
<td class="sub num">{_e(prices)}</td>
</tr>""")
    return f"""<div class="scroll"><table>
<thead><tr><th>채널</th><th>가격언급</th><th>분당</th><th>최저</th><th>최고</th>
<th>%언급</th><th>최대%</th><th>개월언급</th><th>최대개월</th><th>등장 금액(원)</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p class="sub">· 자막에서 정규식으로 추출한 숫자입니다. '39만 8천원' 같은 복합 표기도 합산합니다.
· 실제 판매가가 아니라 <b>방송에서 입으로 말한 숫자</b>라는 점에 유의하세요(정상가·경쟁가·월납 금액이 섞일 수 있음).</p>"""


def _timeline_rhythm(res: ComparisonResult, colors: dict[str, str], max_axes: int = 8) -> str:
    """구간 타임라인(소구축 히트맵)과 방송 리듬(호스트 강조·소스 판촉강도)을
    분(分) 단위로 같은 그리드에 쌓아 한 화면에서 같이 본다. 둘 다 m.rhythm의
    같은 분 인덱스를 쓰므로 열이 그대로 맞아떨어진다."""
    keys = [a.key for a in res.axes[:max_axes]]
    labels = {a.key: a.label for a in res.axes}
    axcolor = {a.key: a.color for a in res.axes}
    blocks = []
    any_native = False
    any_unmatched = False
    for m in res.metrics:
        if not m.rhythm:
            continue
        any_native = any_native or m.has_native_rhythm
        n = len(m.rhythm)
        cols = f"130px repeat({n},minmax(12px,1fr))"
        rows = []
        # 발화 밀도 행 — 다른 행처럼 셀을 클릭하면 그 분의 원문을 보여준다
        mx_chars = max((r.chars for r in m.rhythm), default=1) or 1
        cells = "".join(
            f"<div class='cell mcell' title='{r.m}분 · {r.chars}자' "
            f"data-bid='{_e(m.broadcast_id)}' data-m='{r.m}' "
            f"style='background:rgba(35,131,226,{0.08 + 0.85 * r.chars / mx_chars:.2f})'></div>"
            for r in m.rhythm
        )
        rows.append(f"<div class='lbl'>발화 밀도</div>{cells}")
        # 소구축 히트맵 행 — 셀을 클릭하면 그 분에 실제로 한 말을 보여준다
        for k in keys:
            if k not in m.axes:
                continue
            vals = [r.axis_hits.get(k, 0) for r in m.rhythm]
            mx = max(vals) or 1.0
            c = axcolor[k].lstrip("#")
            rgb = ",".join(str(int(c[i:i + 2], 16)) for i in (0, 2, 4))
            cells = "".join(
                f"<div class='cell mcell' title='{r.m}분 · {labels[k]} {v}회' "
                f"data-bid='{_e(m.broadcast_id)}' data-m='{r.m}' "
                f"style='background:rgba({rgb},{0.06 + 0.9 * v / mx:.2f})'></div>"
                for r, v in zip(m.rhythm, vals)
            )
            rows.append(f"<div class='lbl'>{_e(labels[k])}</div>{cells}")
        # 리듬 행 — 소스 판촉강도(%) 또는 호스트 강조, 클릭하면 그 분의 원문
        mx_hits = max((r.top_axis_hits for r in m.rhythm), default=1) or 1
        bar_cells = []
        for r in m.rhythm:
            color = axcolor.get(r.top_axis, "#9b9a97")
            if r.native_pct is not None:
                strength = max(0.15, min(1.0, r.native_pct / 100))
            elif r.top_axis_hits:
                strength = max(0.15, min(1.0, r.top_axis_hits / mx_hits))
            else:
                strength = 0.12
            cls = "cell rbar miss" if r.unmatched else "cell rbar"
            any_unmatched = any_unmatched or r.unmatched
            title_bits = [f"{r.m}분"]
            if r.top_axis:
                title_bits.append(f"{labels.get(r.top_axis, r.top_axis)} {r.top_axis_hits}회")
            if r.native_pct is not None:
                title_bits.append(f"소스 판촉강도 {r.native_pct:.0f}%")
            if r.unmatched:
                title_bits.append("호스트 강조 O · 우리 축 매칭 X")
            bar_cells.append(
                f"<div class='{cls}' style='background:{color};opacity:{strength:.2f}' "
                f"title='{_e(' · '.join(title_bits))}' data-bid='{_e(m.broadcast_id)}' data-m='{r.m}'></div>"
            )
        native_note = "소스 판촉강도(%) 결합" if m.has_native_rhythm else "소스 리듬 데이터 없음 · 우리 축만"
        rows.append(f"<div class='lbl'>리듬 · {_e(native_note)}</div>{''.join(bar_cells)}")
        grid = "".join(f"<div class='hm' style='grid-template-columns:{cols}'>{r}</div>" for r in rows)
        blocks.append(
            f"<div class='panel'><h3 style='color:{colors[m.broadcast_id]};margin-top:0'>"
            f"{_e(m.channel_name)}</h3><div class='scroll'><div style='min-width:560px'>{grid}</div>"
            f"<div class='raxis'><span>0분</span><span>{n - 1}분</span></div></div></div>"
        )
    if not blocks:
        return "<p class='sub'>타임라인 데이터 없음</p>"
    legend_bits = "".join(f"<span><b style='background:{a.color}'></b>{_e(a.label)}</span>" for a in res.axes[:max_axes])
    return f"<div class='legend' style='margin-bottom:10px'>{legend_bits}</div>" + "".join(blocks) + (
        "<p class='sub'>· 위쪽 소구축 행들은 그 채널 <b>자신의 최대값 기준</b>으로 색이 진해집니다(행 내부 비교용). "
        "채널 간 절대 강도 비교는 2번 소구축 비교표를 보세요. "
        "· 맨 아래 <b>리듬</b> 행의 막대 색은 그 분에 가장 많이 매칭된 소구축"
        + (", 진하기는 소스가 자체 태깅한 판촉 강도(%)." if any_native else ", 진하기는 그 분의 축 매칭 강도(상대값).")
        + (" <b style='color:var(--bad)'>●</b> = 소스가 강조로 태깅했지만 우리 키워드 사전은 못 잡은 지점." if any_unmatched else "")
        + " 이 표의 <b>어느 칸이든 누르면</b> 그 분(발화 밀도·소구축·리듬 행 전부)에 실제로 한 말을 볼 수 있습니다.</p>"
    )


def _distinctive(res: ComparisonResult, colors: dict[str, str]) -> str:
    name = {m.broadcast_id: m.channel_name for m in res.metrics}
    cards = []
    for bid in res.ids:
        terms = res.distinctive.get(bid, [])
        body = "".join(
            f"<div class='kv'><span>{_e(t)}</span><span class='num'>z {z:+.1f} · {c}회</span></div>"
            for t, z, c in terms
        ) or "<div class='sub'>유의미한 차별 표현 없음</div>"
        cards.append(
            f"<div class='card' style='--ch:{colors[bid]}'>"
            f"<div class='name'>{_e(name[bid])}</div>{body}</div>"
        )
    return (
        f"<div class='grid cards'>{''.join(cards)}</div>"
        "<p class='sub'>· 단순 빈도가 아니라 <b>다른 방송 대비 초과 사용량</b>(Dirichlet 사전분포 로그오즈비 z)입니다. "
        "'이거·그래서' 같은 공통어는 자동으로 걸러집니다. z가 클수록 그 채널만의 화법입니다.</p>"
    )


def _rhythm_json(res: ComparisonResult) -> str:
    axis_label = {a.key: a.label for a in res.axes}
    data: dict[str, list[dict[str, Any]]] = {}
    for m in res.metrics:
        if not m.rhythm:
            continue
        data[m.broadcast_id] = [
            {
                "m": r.m,
                "top_axis": r.top_axis,
                "top_axis_label": axis_label.get(r.top_axis) if r.top_axis else None,
                "top_axis_hits": r.top_axis_hits,
                "native_pct": r.native_pct,
                "unmatched": r.unmatched,
                "lines": r.lines,
            }
            for r in m.rhythm
        ]
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _won(v: float) -> str:
    """금액을 한눈에 읽히게 — 1억 이상은 억, 그 아래는 만원 단위."""
    if v >= 1e8:
        return f"{v / 1e8:,.2f}억"
    return f"{v / 1e4:,.0f}만"


def _broadcast_info_table(res: ComparisonResult, colors: dict[str, str]) -> str:
    """검색 화면에서 보던 방송 기본정보(시작·채널·편성·모델명·매출·분당주문액)를
    리포트 맨 위에도 그대로 띄운다 — 뭘 비교하고 있는지 숫자로 바로 확인하는 용도.

    표 아래에는 매출 / 가중분 / 분당주문액을 막대로 나란히 놓는다. 매출이 커도
    황금시간대라 가중분이 컸던 건지, 같은 조건에서 실제로 잘 판 건지를 한 번에 가른다."""
    rows = []
    for m in res.metrics:
        kind = "라이브" if channel_kind(m.channel) == "live" else "T커머스"
        rev = f"{m.revenue:,}원" if m.revenue is not None else "<span class='sub'>–</span>"
        wmin = f"{m.weighted_minutes:,.1f}분" if m.weighted_minutes is not None else "<span class='sub'>–</span>"
        rpwm = f"{m.revenue_per_weighted_min:,.0f}원" if m.revenue_per_weighted_min is not None else "<span class='sub'>–</span>"
        rows.append(
            f"<tr><td><b style='color:{colors[m.broadcast_id]}'>■</b> {_e(m.channel_name)}</td>"
            f"<td><span class='kind {'live' if kind == '라이브' else 'tc'}'>{kind}</span></td>"
            f"<td>{_e(m.start_datetime[:16].replace('T', ' '))}</td>"
            f"<td class='num'>{m.duration_min:.0f}분</td>"
            f"<td class='num'>{wmin}</td>"
            f"<td class='sub'>{_e(model_key(m.product_name))}</td>"
            f"<td class='num'>{rev}</td>"
            f"<td class='num'><b>{rpwm}</b></td></tr>"
        )
    table = f"""<div class="scroll"><table>
<thead><tr><th>홈쇼핑사</th><th>구분</th><th>방송 시작</th><th>편성</th>
<th title="시간대 가중치를 합산한 분 — 라이브/T커머스 가중치 표가 다름">가중분</th><th>모델명</th><th>편성 추정 매출</th>
<th title="홈쇼핑모아 추정매출/가중분">분당주문액</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>"""

    # 한눈에 비교: 지표마다 최댓값=100% 막대
    specs = [
        ("편성 추정 매출", lambda m: m.revenue, lambda v: _won(v) + "원"),
        ("가중분", lambda m: m.weighted_minutes, lambda v: f"{v:,.1f}분"),
        ("분당주문액", lambda m: m.revenue_per_weighted_min, lambda v: _won(v) + "원"),
    ]
    EMPTY_BAR = "<div class='bar'></div>"
    blocks = []
    for label, get, fmt in specs:
        vals = [(m, get(m)) for m in res.metrics]
        top = max((v for _, v in vals if v), default=0)
        if not top:
            continue
        lines = "".join(
            f"<div class='cmp-row'><span class='cmp-ch' style='color:{colors[m.broadcast_id]}'>{_e(m.channel_name)}</span>"
            f"{_bar(100.0 * v / top, colors[m.broadcast_id]) if v else EMPTY_BAR}"
            f"<span class='cmp-v'>{fmt(v) if v else '–'}</span></div>"
            for m, v in vals
        )
        blocks.append(f"<div class='cmp-col'><div class='cmp-h'>{label}</div>{lines}</div>")
    glance = f"<div class='cmp-grid'>{''.join(blocks)}</div>" if blocks else ""
    return table + glance


_COND_ORDER = ["최종가", "무이자", "월 납입", "카드 할인", "앱·모바일 할인", "사은품", "구성", "보증", "강조"]


def _cond_lines(val: str) -> str:
    """목록형 값(쉼표·가운뎃점 구분)은 한 줄에 하나씩, 괄호 속 보충은 흐리게 — 표를 넓히지 않고 다 보이게."""
    import re as _re
    main, _, note = val.partition(" (")
    # "33만 3,000원"의 쉼표는 숫자 자리 구분이라 쪼개면 안 된다 — 쉼표+공백, 가운뎃점에서만 나눈다
    parts = [p.strip() for p in _re.split(r"\s*·\s*|,\s+", main) if p.strip()]
    # '롯데·삼성·농협 17,010원' 처럼 끝에 금액이 붙은 목록은 금액을 마지막 줄로
    if len(parts) > 1 and _re.search(r"\d", parts[-1]) and " " in parts[-1] and not _re.match(r"\d", parts[-1]):
        head, _, tail = parts[-1].rpartition(" ")
        parts[-1:] = [head, tail]
    out = "".join(f"<span class='ln'>{_e(p)}</span>" for p in parts)
    if note:
        out += f"<span class='ln dim'>({_e(note.rstrip(')'))})</span>"
    return out


def _cond_evidence(ev: list) -> str:
    if not ev:
        return ""
    quotes = "".join(
        f"<div class='cq'><span class='ct'>{int(t // 60):02d}:{int(t % 60):02d}</span> "
        f"{_e(x if len(x) <= 140 else x[:140] + '…')}</div>"
        for t, x in ev
    )
    return f"<details><summary>근거 {len(ev)}</summary>{quotes}</details>"


def _conditions_table(res: ComparisonResult, colors: dict[str, str]) -> str:
    """멘트에서 자동으로 뽑은 방송 조건. 셀을 누르면 근거 멘트(시각+문장)가 펼쳐진다."""
    if not any(m.conditions for m in res.metrics):
        return ""
    head = "".join(f"<th><b style='color:{colors[m.broadcast_id]}'>■</b> {_e(m.channel_name)}</th>" for m in res.metrics)
    rows = []
    for key in _COND_ORDER:
        cells = []
        for m in res.metrics:
            cond = (m.conditions or {}).get(key) or {}
            val = cond.get("value") or ""
            ev = cond.get("evidence") or []
            if not val:
                cells.append("<td><span class='none'>–</span></td>")
                continue
            cells.append(f"<td><div class='cv'>{_cond_lines(val)}</div>{_cond_evidence(ev)}</td>")
        rows.append(f"<tr><th class='ck'>{_e(key)}</th>{''.join(cells)}</tr>")
    return f"""<div class="panel">
  <b>방송 조건 비교</b> <span class="sub">멘트에서 자동 추출 · '근거'를 누르면 해당 멘트와 시각이 펼쳐집니다 · 자막 오인식이 있을 수 있어요</span>
  <div class="scroll"><table class="ctable"><thead><tr><th></th>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
</div>"""


def _quotes_json(res: ComparisonResult) -> str:
    data: dict[str, dict[str, Any]] = {}
    for m in res.metrics:
        axes_out = {}
        for key, am in m.axes.items():
            if am.example_lines:
                axes_out[key] = {
                    "label": am.label,
                    "channel": m.channel_name,
                    "lines": am.example_lines,
                }
        if axes_out:
            data[m.broadcast_id] = axes_out
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def render(
    res: ComparisonResult,
    *,
    title: str | None = None,
    source_note: str = "",
) -> str:
    colors = {m.broadcast_id: _channel_color(i) for i, m in enumerate(res.metrics)}
    legend = "".join(
        f"<span><b style='background:{colors[m.broadcast_id]}'></b>{_e(m.channel_name)}</span>"
        for m in res.metrics
    )
    diff_labels = [a.label for a in res.axes if a.key in res.differentiating_axes] or ["없음"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ttl = title or f"{res.product_name} — 홈쇼핑 채널별 판매 화법 비교"
    quotes_json = _quotes_json(res)
    rhythm_json = _rhythm_json(res)

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(ttl)}</title><style>{CSS}</style></head><body><div class="wrap">
<h1>{_e(ttl)}</h1>
<p class="sub">비교 방송 {len(res.metrics)}건 · 생성 {now}{(' · ' + _e(source_note)) if source_note else ''}</p>
<div class="legend">{legend}</div>

<div class="panel">
  <b>비교 방송 정보</b>
  {_broadcast_info_table(res, colors)}
</div>

{_conditions_table(res, colors)}

<div class="panel">
  <b>한 줄 요약</b>
  <p>같은 상품인데 채널 간 화법이 가장 크게 갈린 축은 <b>{_e(', '.join(diff_labels[:4]))}</b>입니다.</p>
</div>

<h2>1. 채널별 전략 요약</h2>
{_summary_prose(res, colors)}

<h2>2. 소구축별 강도 비교</h2>
{_axis_table(res, colors)}

<h2>3. 방송 타임라인 (소구축 분포 × 리듬)</h2>
{_timeline_rhythm(res, colors)}

<h2>4. 숫자 소구 (가격 · 할인율 · 할부)</h2>
{_numeric_table(res)}

<h2>5. 채널별 차별 표현</h2>
{_distinctive(res, colors)}

<h2>6. 방법론과 한계</h2>
<div class="panel">
<ul>
<li><b>정규화</b> — 편성 길이가 다르면 총량 비교가 왜곡되므로 모든 지표를 분당으로 환산합니다.</li>
<li><b>축 중복 허용</b> — "지금 이 시간 최저가"는 가격·긴급 양쪽에 카운트됩니다. 실제 화법이 복합적이기 때문입니다.</li>
<li><b>키워드 사전 기반</b> — 문맥·반어·부정을 이해하지 못합니다. 예: "비싸지 않습니다"도 가격 축에 잡힙니다.</li>
<li><b>형태소 분석기 미사용</b> — 조사 제거는 규칙 기반 근사입니다. 절대 빈도보다 <b>채널 간 상대 비교</b>에 쓰세요.</li>
<li><b>자막 품질 의존</b> — 자동 음성인식 자막이면 오인식이 그대로 지표에 반영됩니다.</li>
<li><b>소스 태깅은 블랙박스</b> — '방송 리듬'의 판촉강도(%)와 강조 태깅(kinds)은 소스가 자체 계산한 값으로, 정확한 알고리즘을 알 수 없습니다. 우리 키워드 사전과의 <b>불일치 지점</b>을 찾는 용도로만 쓰고, 절대값 자체를 과신하지 마세요.</li>
<li><b>인과 해석 금지</b> — 이 리포트는 "어떻게 팔았나"를 재는 것이지 "그래서 잘 팔렸나"를 증명하지 않습니다. 매출 지표와 결합해야 의미가 생깁니다.</li>
</ul>
</div>

<footer>홈쇼핑 비교봇 · hsbot</footer>
</div>

<div id="quoteOverlay">
  <div id="quoteModal">
    <span class="close" id="quoteClose">&times;</span>
    <h3 id="quoteTitle"></h3>
    <div class="sub" id="quoteSub" style="margin-bottom:10px"></div>
    <div id="quoteBody"></div>
  </div>
</div>
<script>
const QUOTES = {quotes_json};
const RHYTHM = {rhythm_json};
function mmss(sec) {{
  sec = Math.max(0, Math.round(sec || 0));
  return Math.floor(sec/60) + ':' + String(sec%60).padStart(2,'0');
}}
function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}
function highlight(text, terms) {{
  let out = esc(text);
  (terms || []).forEach(t => {{
    if (!t) return;
    const re = new RegExp(esc(t).replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&'), 'g');
    out = out.replace(re, m => '<mark>' + m + '</mark>');
  }});
  return out;
}}
function showQuotes(bid, axisKey) {{
  const entry = (QUOTES[bid] || {{}})[axisKey];
  if (!entry) return;
  document.getElementById('quoteTitle').textContent = entry.channel + ' · ' + entry.label;
  document.getElementById('quoteSub').textContent = entry.lines.length + '건의 관련 발화';
  document.getElementById('quoteBody').innerHTML = entry.lines.map(l =>
    `<div class="qline"><span class="t">${{mmss(l.t)}}</span>${{highlight(l.text, l.terms)}}` +
    ((l.boost && l.boost > 1) ? ` <span class="tag" title="그 분(${{Math.floor(l.t/60)}}분)의 소스 판촉강도가 ${{Math.round(l.boost_pct)}}%라서 ×${{l.boost.toFixed(2)}} 가산">가산 ×${{l.boost.toFixed(2)}}</span>` : '') +
    `</div>`
  ).join('');
  document.getElementById('quoteOverlay').classList.add('open');
}}
function showRhythm(bid, m) {{
  const arr = RHYTHM[bid] || [];
  const entry = arr.find(r => r.m === +m);
  if (!entry) return;
  document.getElementById('quoteTitle').textContent = entry.m + '분 구간';
  const bits = [];
  if (entry.top_axis_label) bits.push(entry.top_axis_label + ' 축 ' + entry.top_axis_hits + '회');
  if (entry.native_pct != null) bits.push('소스 판촉강도 ' + Math.round(entry.native_pct) + '%');
  if (entry.unmatched) bits.push('호스트 강조 O · 우리 축 매칭 X');
  document.getElementById('quoteSub').textContent = bits.join(' · ') || '특이 매칭 없음';
  document.getElementById('quoteBody').innerHTML = (entry.lines || []).map(l =>
    `<div class="qline"><span class="t">${{mmss(l.t)}}</span>${{esc(l.text)}}` +
    ((l.kinds && l.kinds.length) ? ` <span class="tag">${{l.kinds.map(esc).join(', ')}}</span>` : '') +
    `</div>`
  ).join('') || '<div class="sub">이 분에는 자막이 없습니다.</div>';
  document.getElementById('quoteOverlay').classList.add('open');
}}
document.addEventListener('click', (e) => {{
  const td = e.target.closest('[data-bid][data-axis]');
  if (td) {{ showQuotes(td.dataset.bid, td.dataset.axis); return; }}
  const rb = e.target.closest('[data-bid][data-m]');
  if (rb) showRhythm(rb.dataset.bid, rb.dataset.m);
}});
document.getElementById('quoteClose').addEventListener('click', () => {{
  document.getElementById('quoteOverlay').classList.remove('open');
}});
document.getElementById('quoteOverlay').addEventListener('click', (e) => {{
  if (e.target.id === 'quoteOverlay') e.target.classList.remove('open');
}});
</script>
</body></html>"""


def render_json(res: ComparisonResult) -> str:
    return json.dumps(
        {
            "product_name": res.product_name,
            "differentiating_axes": res.differentiating_axes,
            "metrics": [m.to_dict() for m in res.metrics],
            "axes": [
                {
                    "key": a.key, "label": a.label, "mean": a.mean, "spread": a.spread,
                    "leader": a.leader, "values": a.values, "index": a.index, "zscore": a.zscore,
                }
                for a in res.axes
            ],
            "distinctive": res.distinctive,
            "profile": res.profile,
        },
        ensure_ascii=False,
        indent=2,
    )
