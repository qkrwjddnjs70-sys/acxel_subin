"""자막 조각 → 문장 단위로 잇기 + 검수용 TSV 생성.

이어 붙이는 기준: 앞 조각이 문장 끝(. ? ! 또는 '요/다/죠/까/네' 등으로 끝남)이 아니고,
다음 조각과 4초 이내이며, 합친 길이가 220자를 넘지 않으면 이어 붙인다.
문장의 초기 분류 = 구성 조각 분류 중 글자 수가 가장 많은 것(진행·맞장구·잡음은 판매 분류가 있으면 밀린다).
"""
import json
import os
import re
from collections import Counter

from build_preview import CODES, load, mmss

HERE = os.path.dirname(os.path.abspath(__file__))
END = re.compile(r"([.?!…]|[요다죠까네군음함됨임])[\"'”’)\]]*\s*$")


def units_for(key):
    segs = load(key)
    units = []
    cur = None
    for s in segs:
        if cur is not None:
            prev_text = cur["parts"][-1]["text"]
            gap = s["t"] - cur["parts"][-1]["t"]
            if not END.search(prev_text) and gap <= 4 and len(cur["text"]) + len(s["text"]) <= 220:
                cur["parts"].append(s)
                cur["text"] += " " + s["text"]
                continue
            units.append(cur)
        cur = {"t": s["t"], "parts": [s], "text": s["text"]}
    if cur:
        units.append(cur)
    out = []
    for u_i, u in enumerate(units):
        c = Counter()
        for p in u["parts"]:
            w = max(len(p["text"]), 1)
            c[p["code"]] += w if CODES[p["code"]][1] != "기타" else w * 0.3
        out.append({"u": u_i, "t": u["t"], "text": u["text"], "code": c.most_common(1)[0][0],
                    "seg_idx": [p["i"] for p in u["parts"]]})
    return out


if __name__ == "__main__":
    for key in ("gs0107", "gs0217", "hd0621"):
        us = units_for(key)
        json.dump(us, open(os.path.join(HERE, f"{key}_units.json"), "w", encoding="utf-8"), ensure_ascii=False)
        with open(os.path.join(HERE, f"{key}_units.tsv"), "w", encoding="utf-8") as f:
            for u in us:
                f.write(f"{u['u']}\t{mmss(u['t'])}\t{u['code']}\t{u['text']}\n")
        print(key, "segments→units", sum(len(u["seg_idx"]) for u in us), "→", len(us))
