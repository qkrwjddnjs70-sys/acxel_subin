"""시간대별 가중치(hsbot.time_weight) 회귀 테스트."""
import unittest
from datetime import datetime

from hsbot.time_weight import KST, channel_kind, weight_at, weighted_minutes, weighted_minutes_from_iso


class WeightAtTest(unittest.TestCase):
    def test_일요일_새벽_1시25분은_평균의_약_26퍼센트(self):
        # 2026-10-04는 일요일. 표의 '일' 열 0125 = 26.4% (약 15.8초/분).
        dt = datetime(2026, 10, 4, 1, 25, tzinfo=KST)
        self.assertAlmostEqual(weight_at(dt), 0.264, places=3)

    def test_표에_없는_시각은_평균치_1_0(self):
        dt = datetime(2026, 10, 4, 1, 25, 30, tzinfo=KST)  # 같은 분(0125) 안의 다른 초
        self.assertAlmostEqual(weight_at(dt), 0.264, places=3)


class WeightedMinutesTest(unittest.TestCase):
    def test_1분_구간은_그_분_가중치와_같다(self):
        start = datetime(2026, 10, 4, 1, 25, 0, tzinfo=KST)
        end = datetime(2026, 10, 4, 1, 26, 0, tzinfo=KST)
        self.assertAlmostEqual(weighted_minutes(start, end), 0.264, places=3)

    def test_끝이_시작보다_빠르면_0(self):
        start = datetime(2026, 10, 4, 1, 26, 0, tzinfo=KST)
        end = datetime(2026, 10, 4, 1, 25, 0, tzinfo=KST)
        self.assertEqual(weighted_minutes(start, end), 0.0)

    def test_자정을_넘기는_방송도_요일이_바뀌며_처리된다(self):
        # 일요일 23:50 ~ 월요일 00:50 (60분, 요일 경계를 가로지름)
        wmin = weighted_minutes_from_iso("2026-10-04T23:50:00", "2026-10-05T00:50:00")
        self.assertIsNotNone(wmin)
        self.assertGreater(wmin, 0)
        self.assertLess(wmin, 60)  # 심야라 평균(1.0)보다 낮아야 한다

    def test_iso_파싱_실패시_None(self):
        self.assertIsNone(weighted_minutes_from_iso("", "2026-10-04T01:26:00"))
        self.assertIsNone(weighted_minutes_from_iso("2026-10-04T01:25:00", ""))


class ChannelKindTest(unittest.TestCase):
    """라이브와 T커머스는 서로 다른 가중치 표를 쓴다."""

    def test_kind(self):
        self.assertEqual(channel_kind("gsshop"), "live")
        self.assertEqual(channel_kind("gsmyshop"), "tcommerce")
        self.assertEqual(channel_kind("lotteonetv"), "tcommerce")
        self.assertEqual(channel_kind(None), "live")  # 채널 미상이면 기존 동작 유지

    def test_tables_differ(self):
        dt = datetime(2026, 10, 10, 22, 0, tzinfo=KST)  # 토 22:00
        self.assertAlmostEqual(weight_at(dt, "live"), 2.081, places=3)
        self.assertAlmostEqual(weight_at(dt, "tcommerce"), 1.37, places=3)

    def test_from_iso_uses_channel(self):
        live = weighted_minutes_from_iso("2026-10-10T22:00:00", "2026-10-10T22:01:00", "gsshop")
        tc = weighted_minutes_from_iso("2026-10-10T22:00:00", "2026-10-10T22:01:00", "gsmyshop")
        self.assertAlmostEqual(live, 2.081, places=3)
        self.assertAlmostEqual(tc, 1.37, places=3)


if __name__ == "__main__":
    unittest.main()
