"""소구축(axis) 사전 로딩 및 매칭."""
from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

LEXICON_DIR = os.path.join(os.path.dirname(__file__), "lexicons")


@dataclass
class Axis:
    key: str
    label: str
    keywords: list[str]
    color: str = "#9fb3c8"
    desc: str = ""
    _regex: re.Pattern | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        # 긴 키워드를 먼저 매칭해야 '무료배송'이 '배송'으로 쪼개지지 않는다.
        kws = sorted({k.lower() for k in self.keywords if k}, key=len, reverse=True)
        parts = []
        for k in kws:
            esc = re.escape(k)
            # 한국어는 어미가 그대로 붙기 때문에(싸다→싸다고) 단어경계 없이 부분일치가
            # 의도된 설계다. 반면 영문 짧은 코드("as", "ars")는 아무 영단어에나
            # 끼어 있을 수 있어("ch[as]ing") 단어경계를 강제해야 오탐을 막는다.
            if k.isascii() and k.isalpha() and len(k) <= 4:
                parts.append(rf"\b{esc}\b")
            elif k.startswith("싸") or k == "싼":
                # '싸다/싸게/싼'(싸다, cheap)은 '비싸다/비싸게/비싼'(expensive)의 꼬리
                # 부분문자열이라 그대로 두면 정반대 의미로 오탐된다("비싼 소재"→'싼' 매칭).
                parts.append(rf"(?<!비){esc}")
            else:
                parts.append(esc)
        self._regex = re.compile("|".join(parts)) if parts else None

    def hits(self, text: str) -> list[str]:
        """텍스트에서 이 축의 키워드 매칭 결과(중복 포함)를 돌려준다."""
        if self._regex is None:
            return []
        return self._regex.findall(text.lower())

    def count(self, text: str) -> int:
        return len(self.hits(text))


PHRASE_RULES_PATH = os.path.join(LEXICON_DIR, "phrase_rules.csv")

# 문구 규칙 문법: {숫자} = 금액·개월·% 같은 숫자, {~} = 사이에 아무 말(최대 20자)
_NUM = r"[0-9][0-9,.]*\s*(?:만|천|백)?\s*[0-9,]*\s*(?:천)?"
_GAP = r".{0,20}?"


@dataclass
class PhraseRule:
    """'앱{~}할인 → 혜택(조건)' 처럼 문구 단위로 축을 정하는 규칙.

    단어 사전보다 먼저 적용하고, 걸린 부분은 지워서 그 안의 단어가 다른 축으로
    또 세지지 않게 한다 — 예) '믿고 주문하세요'는 콜유도 1회, '믿고'(안심)는 세지 않음.
    """
    pattern: str
    axis_key: str
    note: str = ""
    _regex: re.Pattern | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        out, rest = [], self.pattern
        for tok in re.split(r"(\{숫자\}|\{~\})", rest):
            if tok == "{숫자}":
                out.append(_NUM)
            elif tok == "{~}":
                out.append(_GAP)
            elif tok:
                # 띄어쓰기는 자막마다 들쭉날쭉하니 공백 유무를 가리지 않는다
                out.append(r"\s*".join(re.escape(ch) for ch in tok.replace(" ", "")))
        self._regex = re.compile("".join(out))

    @property
    def literal_len(self) -> int:
        return len(re.sub(r"\{숫자\}|\{~\}|\s", "", self.pattern))


def load_phrase_rules(lex_axes: dict[str, Axis], path: str = PHRASE_RULES_PATH) -> list[PhraseRule]:
    """CSV(문구,축,메모) → 규칙 목록. 축은 키(BENEFIT) 또는 화면 이름(혜택(조건)) 둘 다 받는다.
    현재 사전에 없는 축을 가리키는 규칙은 건너뛴다."""
    if not os.path.exists(path):
        return []
    by_label = {ax.label: k for k, ax in lex_axes.items()}
    rules = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            pat = (row.get("문구") or "").strip()
            ax = (row.get("축") or "").strip()
            key = ax if ax in lex_axes else by_label.get(ax)
            if pat and key:
                rules.append(PhraseRule(pat, key, (row.get("메모") or "").strip()))
    # 구체적인(글자가 많은) 규칙이 먼저 — '믿고 주문하세요'가 '주문하세요'보다 앞서야 한다
    rules.sort(key=lambda r: r.literal_len, reverse=True)
    return rules


@dataclass
class Lexicon:
    name: str
    axes: dict[str, Axis]
    phrases: list[PhraseRule] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._match = lru_cache(maxsize=50000)(self._match_uncached)

    def __iter__(self):
        return iter(self.axes.values())

    @property
    def keys(self) -> list[str]:
        return list(self.axes)

    def merge(self, other: "Lexicon", name: str | None = None) -> "Lexicon":
        """두 사전을 합친다. 키가 겹치면 뒤쪽(other)이 이긴다."""
        return Lexicon(name or f"{self.name}+{other.name}", {**self.axes, **other.axes})

    def _match_uncached(self, text: str) -> dict[str, tuple[str, ...]]:
        low = text.lower()
        found: dict[str, list[str]] = {}
        for rule in self.phrases:
            def _take(m: re.Match) -> str:
                found.setdefault(rule.axis_key, []).append(m.group(0).strip())
                return " " * len(m.group(0))  # 걸린 부분은 지운다(다른 축 이중 집계 방지)
            low = rule._regex.sub(_take, low)
        for ax in self.axes.values():
            h = ax.hits(low)
            if h:
                found.setdefault(ax.key, []).extend(h)
        return {k: tuple(v) for k, v in found.items()}

    def hits(self, axis_key: str, text: str) -> list[str]:
        """문구 규칙 → 단어 사전 순서로 매칭한 결과 중 이 축의 것."""
        return list(self._match(text).get(axis_key, ()))


def load_lexicon(path_or_name: str) -> Lexicon:
    path = path_or_name
    if not os.path.exists(path):
        cand = os.path.join(LEXICON_DIR, f"{path_or_name}.json")
        if not os.path.exists(cand):
            raise FileNotFoundError(f"사전을 찾을 수 없습니다: {path_or_name}")
        path = cand
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    axes = {
        key: Axis(
            key=key,
            label=spec.get("label", key),
            keywords=spec.get("keywords", []),
            color=spec.get("color", "#9fb3c8"),
            desc=spec.get("desc", ""),
        )
        for key, spec in raw.get("axes", {}).items()
    }
    return Lexicon(raw.get("name", os.path.basename(path)), axes)


def load_combined(names: list[str]) -> Lexicon:
    if not names:
        raise ValueError("사전 이름이 비어 있습니다.")
    lex = load_lexicon(names[0])
    for n in names[1:]:
        lex = lex.merge(load_lexicon(n))
    lex.name = "+".join(names)
    lex.phrases = load_phrase_rules(lex.axes)
    return lex
