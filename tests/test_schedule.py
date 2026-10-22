"""주간 편성표(hsbot.schedule)·4분류(hsbot.category) 회귀 테스트 — 네트워크 없이."""
import os
import tempfile
import unittest
from datetime import date

from hsbot import schedule
from hsbot.category import classify
from hsbot.sources.datahub import DataHubError


class ClassifyTest(unittest.TestCase):
    def test_four_categories(self):
        self.assertEqual(classify("코웨이 아이콘 정수기 렌탈"), "rental")
        self.assertEqual(classify("LG 디오스 오브제 냉장고 870L"), "digital")
        self.assertEqual(classify("쿠쿠 블랙스톤 전기압력밥솥 10인용"), "kitchen")
        self.assertEqual(classify("쿡셀 홀로그램 IH 큐브팬 마스터 키친 패키지"), "kitchen")
        self.assertEqual(classify("일월 원적외선 카본매트 블랙다이아"), "life")

    def test_rental_wins_over_gift(self):
        # 정수기에 사은품 에어프라이어가 붙어도 렌탈
        self.assertEqual(classify("코웨이 정수기 렌탈 + 에어프라이어 증정"), "rental")

    def test_false_digital_avoided(self):
        self.assertEqual(classify("[삼성카드5%할인] 니카사 진공 스팀다리미"), "life")
        self.assertEqual(classify("[쿡셀]홀로그램 인덕션 (V2)"), "kitchen")
        self.assertEqual(classify("한일 이동식 에어컨"), "life")

    def test_non_appliance_excluded(self):
        self.assertIsNone(classify("최명희명인 수제고추장 7kg"))
        self.assertEqual(classify("알 수 없는 상품", "가전", "생활가전"), "life")

    def test_hsmoa_categories_first(self):
        # 실제 10/13 편성에서 키워드만으로는 틀리던 것들
        self.assertIsNone(classify("[엘지생활건강] 라끄베르 골든 로얄 기초 3종", "뷰티", "스킨케어"))
        self.assertIsNone(classify("저세상 직화 무뼈닭발 세트", "식품", "가공식품"))
        self.assertIsNone(classify("키리아타올 호텔수건 10장", "생필품/주방", "욕실용품"))
        self.assertEqual(classify("아이넥스 클린엣지 식기건조대", "생필품/주방", "주방용품"), "kitchen")
        self.assertEqual(classify("스칸디노티아 글라스 에어프라이어", "가전", "주방가전", "튀김기/전기쿠커"), "kitchen")
        self.assertEqual(classify("담고 김치냉장고 150L", "가전", "대형가전", "김치냉장고"), "kitchen")
        self.assertEqual(classify("휴렉 지니 음식물 처리기 렌탈", "가전", "주방가전"), "rental")
        self.assertEqual(classify("테팔 무선청소기 엑스퍼트", "가전", "생활가전", "무선청소기"), "life")


SAMPLE = {
    "before_live": [{
        "time": "2026-10-11T00:00:00+09:00",
        "schedules": [
            {"pdid": "gsshop_1", "tv_channel": "gsshop", "live_order": 2,
             "broadcast_key": "gsshop|2026-10-11T01:00:00+09:00|2026-10-11T02:00:00+09:00",
             "name": "사은품 냄비"},
            {"pdid": "gsshop_2", "tv_channel": "gsshop", "live_order": 1,
             "broadcast_key": "gsshop|2026-10-11T01:00:00+09:00|2026-10-11T02:00:00+09:00",
             "name": "일월 카본매트 싱글", "category1": "가전", "category2": "계절가전",
             "revenue": 15_600_000, "sales_count": 10,
             "same_time_products": [{"pdid": "gsshop_3", "live_order": 3,
                                     "broadcast_key": "gsshop|2026-10-11T01:00:00+09:00|2026-10-11T02:00:00+09:00",
                                     "name": "부속품"}]},
            {"pdid": "gsmyshop_9", "tv_channel": "gsmyshop", "live_order": 1,
             "broadcast_key": "gsmyshop|2026-10-11T01:00:00+09:00|2026-10-11T02:00:00+09:00",
             "name": "수제고추장 7kg", "category1": "식품"},
        ],
    }],
}


class ParseDayTest(unittest.TestCase):
    def test_one_row_per_broadcast_main_product(self):
        rows = schedule.parse_day(SAMPLE)
        self.assertEqual(len(rows), 2)
        gs = next(r for r in rows if r["channel"] == "gsshop")
        self.assertEqual(gs["product_key"], "gsshop_2")  # live_order 가장 작은 대표 상품
        self.assertEqual(gs["start"], "2026-10-11T01:00:00+09:00")


class _Fake:
    def __init__(self):
        self.calls = 0

    def get(self, name, use_cache=True, **p):
        self.calls += 1
        if p["date"] == "2026-10-11":  # 일요일
            return SAMPLE
        return {"before_live": []}

    def fetch_revenue(self, items):
        self.calls += 1
        return {"broadcasts": {
            "gsshop|2026-10-11T01:00:00+09:00|2026-10-11T02:00:00+09:00": {"revenue": 15_600_000, "sales_count": 10}
        }}


class BuildWeekTest(unittest.TestCase):
    def setUp(self):
        self._old = schedule._REVENUE_CACHE
        self._tmp = tempfile.TemporaryDirectory()
        schedule._REVENUE_CACHE = os.path.join(self._tmp.name, "revenue.json")
        schedule._MEM.clear()

    def tearDown(self):
        schedule._REVENUE_CACHE = self._old
        self._tmp.cleanup()

    def test_week_items_with_weighted_minutes(self):
        fake = _Fake()
        wk = schedule.build_week(fake, date(2026, 10, 5), new_lookback_days=2)
        self.assertEqual(len(wk["items"]), 1)  # 고추장은 가전·주방이 아니라 빠진다
        it = wk["items"][0]
        self.assertEqual((it["shop"], it["group"], it["cat"]), ("GS샵", "live", "life"))
        self.assertAlmostEqual(it["weighted_min"], 15.6, places=1)  # 일 01시 라이브 60분
        self.assertEqual(it["rpwm"], round(15_600_000 / it["weighted_min"]))
        # 받아둔 지난 편성이 없으면 NEW 근거가 없으므로 표시하지 않는다
        self.assertFalse(it["new"])
        self.assertEqual(wk["new_basis_days"], 0)
        # 한 주 7회뿐 — 매출은 편성 응답에 들어 있고, NEW 때문에 추가 호출하지 않는다
        self.assertEqual(fake.calls, 7)

    def test_failed_day_reported_not_fatal(self):
        class Boom(_Fake):
            def get(self, name, use_cache=True, **p):
                if p["date"] == "2026-10-05":
                    raise DataHubError("HTTP 429")
                return super().get(name, use_cache, **p)

        wk = schedule.build_week(Boom(), date(2026, 10, 5), new_lookback_days=0)
        self.assertEqual(len(wk["items"]), 1)
        self.assertTrue(wk["errors"][0].startswith("2026-10-05"))


class CallGuardTest(unittest.TestCase):
    """과다 호출 안전장치 — 상한·429 차단이 네트워크 없이 동작하는지."""

    def _guard(self, **kw):
        from hsbot.sources.datahub import CallGuard
        self._tmp = tempfile.TemporaryDirectory()
        return CallGuard(os.path.join(self._tmp.name, "g.json"),
                         min_gap_sec=0, hourly_budget=kw.get("budget", 3), cooldown_sec=60)

    def tearDown(self):
        self._tmp.cleanup()

    def test_hourly_budget(self):
        g = self._guard(budget=2)
        for _ in range(2):
            g.acquire(); g.release()
        with self.assertRaises(DataHubError):
            g.acquire()
        self.assertEqual(g.status()["calls_last_hour"], 2)

    def test_block_after_429(self):
        g = self._guard()
        g.block()
        with self.assertRaises(DataHubError):
            g.acquire()
        self.assertGreater(g.status()["blocked_until"], 0)

    def test_429_not_retried(self):
        """HTTP 429 를 받으면 재시도 없이 한 번에 멈추고 차단 상태가 된다."""
        import io
        import urllib.error
        from unittest import mock
        from hsbot.sources.datahub import DataHubClient, DataHubConfig

        cfg = DataHubConfig(base_url="https://x.invalid", endpoints={"schedule": {"path": "/s"}},
                            mapping={}, max_retries=3, rate_limit_sec=0, cache_dir=None)
        client = DataHubClient(cfg, api_key="k")
        client.guard = self._guard()
        err = urllib.error.HTTPError("https://x.invalid/s", 429, "Too Many", {}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=err) as op:
            with self.assertRaises(DataHubError):
                client.get("schedule", use_cache=False)
            self.assertEqual(op.call_count, 1)
            with self.assertRaises(DataHubError):  # 쿨다운 중 — 네트워크로 나가지도 않는다
                client.get("schedule", use_cache=False)
            self.assertEqual(op.call_count, 1)


if __name__ == "__main__":
    unittest.main()
