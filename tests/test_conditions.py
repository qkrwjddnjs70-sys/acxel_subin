"""방송 조건 추출(hsbot.conditions)·문구 규칙(hsbot.lexicon)·로컬 주간 편성표·업로드 비교 테스트."""
import json
import os
import tempfile
import unittest
from datetime import date

from hsbot.conditions import extract
from hsbot.lexicon import load_combined
from hsbot.models import Segment


def segs(*lines):
    return [Segment(start_sec=float(i * 10), end_sec=None, text=t) for i, t in enumerate(lines)]


class ConditionsTest(unittest.TestCase):
    def test_gs_style(self):
        r = extract(segs(
            "최종 혜택가 32만 3,190원 무이자 10개월 도와드릴게요",
            "모바일로 오시면 무조건 10% 37,800원 빼드릴 거고 카드가 오늘 3개 롯데, 농협, 삼성카드 중에 하나만 있으셔도 17,010원 아껴가셔서",
            "39만 9천 원인가요?",
            "최종 혜택가 32만 3,190원",
            "공식 수입 정품이라 무상 AS도 2년 동안 약속해드릴 거예요",
        ), list_price=378000)
        self.assertTrue(r["최종가"]["value"].startswith("32만 3,190원"))
        self.assertEqual(r["무이자"]["value"], "10개월")
        self.assertIn("17,010원", r["카드 할인"]["value"])
        self.assertNotIn("하나", r["카드 할인"]["value"])  # '하나만 있으셔도'는 카드사가 아니다
        self.assertIn("10%", r["앱·모바일 할인"]["value"])
        self.assertEqual(r["보증"]["value"], "무상 AS 2년")

    def test_hd_style_gift_and_estimated_months(self):
        r = extract(segs(
            "30만 8,853원으로 가져가시는데",
            "한 달에 2만 5천 원대 방송에서 무이자까지 해드리겠습니다",
            "심지어 커피도 챙겨드려요.",
            "커피까지 다 받아가세요",
            "지금 현대 단독입니다 우리 현대 고객님들께만",
        ), list_price=363000)
        self.assertTrue(r["최종가"]["value"].startswith("30만 8,853원"))
        self.assertIn("12개월", r["무이자"]["value"])
        self.assertEqual(r["사은품"]["value"], "커피")
        self.assertEqual(r["카드 할인"]["value"], "")  # '우리 현대 고객님'은 카드가 아니다


class PhraseRuleTest(unittest.TestCase):
    def setUp(self):
        self.lex = load_combined(["core_ko"])

    def axes(self, text):
        return {self.lex.axes[k].label for k in self.lex.axes if self.lex.hits(k, text)}

    def test_call_to_action_phrase_wins(self):
        self.assertEqual(self.axes("믿고 주문하세요"), {"콜유도"})
        self.assertEqual(self.axes("믿고 쓰셔도 됩니다"), {"안심·리스크해소"})

    def test_price_comparison_is_benefit(self):
        self.assertEqual(self.axes("다른 데서는 이 조건 찾아봐도 없습니다"), {"혜택(조건)"})
        self.assertIn("혜택(조건)", self.axes("앱으로 오시면 10% 37,800원 빼드려요"))

    def test_testimonial_quotes(self):
        self.assertIn("고객 증언", self.axes("미리 써보신 분들의 후기도 참 좋아요"))
        self.assertNotIn("고객 증언", self.axes("고객님 지금 말씀드리면"))


class LocalWeekTest(unittest.TestCase):
    def test_build_from_morning_file(self):
        from hsbot.schedule import build_week_local
        data = {
            "2026-10-12": [{"time": "01:00", "title": "로보락 청소기", "shop": "gsshop", "link": ""}],
            "2026-10-19": [
                {"time": "01:00", "title": "쿠쿠 전기압력밥솥", "shop": "hnsmall", "link": "https://hsmoa.com/product/hnsmall_1",
                 "extra": {"tv_channel": "hnsmall", "start": "2026-10-19T01:00:00+09:00", "end": "2026-10-19T02:00:00+09:00",
                           "sale_price": 299000, "card_discounts": [{"card": "삼성", "amount": 10000}],
                           "category1": "가전", "category2": "주방가전"}},
                {"time": "02:00", "title": "수제고추장", "shop": "nsmall", "link": "", "extra": {"category1": "식품"}},
            ],
        }
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "all_data.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            wk = build_week_local(date(2026, 10, 19), p)
        self.assertEqual(len(wk["items"]), 1)  # 식품은 제외
        it = wk["items"][0]
        self.assertEqual((it["cat"], it["shop"], it["sale_price"], it["duration_known"]), ("kitchen", "홈앤쇼핑", 299000, True))
        self.assertTrue(it["new"])


class TextCompareTest(unittest.TestCase):
    def test_upload_payload_to_report(self):
        from hsbot.webapp import build_text_compare_html
        a = "00:00\n최종 혜택가 32만 3,190원 무이자 10개월\n00:30\n믿고 주문하세요"
        b = "00:00 30만 8,853원으로 가져가시는데\n00:20 커피도 챙겨드려요\n00:40 커피까지 다 받아가세요"
        html = build_text_compare_html({"keyword": "다이슨 디지털 슬림", "items": [
            {"text": a, "channel": "GS", "start": "2026-02-17T22:55", "duration_min": 60, "price": 378000, "revenue": 316000000},
            {"text": b, "channel": "hmall", "start": "2026-06-21T12:30", "duration_min": 60, "price": 363000, "revenue": 451000000},
        ]})
        self.assertIn("방송 조건 비교", html)
        self.assertIn("32만 3,190원", html)
        self.assertIn("커피", html)
        self.assertIn("가중분", html)


if __name__ == "__main__":
    unittest.main()
