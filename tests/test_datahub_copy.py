"""데이터허브 자막 화면 복사본 파서(hsbot.sources.datahub_copy) 테스트."""
import unittest

from hsbot.sources.datahub_copy import parse_copy_text, parse_filename

SAMPLE = """00:00
동시에 할 수 있는 벽걸이형 거치대는 물론이고
00:07
헤어스크류 툴 그리고 콤비네이션 툴까지
조건
00:20 ~ 00:30
00:20
30만 원대 초반 지금 오셔야 돼요.
판촉 6%
발화 16건
01:02 ~ 01:56
01:02
분리를 시켜낸다는 겁니다.
68:57
방송 끝나면 이 조건 구매.
"""


class DataHubCopyTest(unittest.TestCase):
    def test_segments_without_screen_chrome(self):
        bc = parse_copy_text(SAMPLE, channel="gsshop", product_name="다이슨",
                             start_datetime="2026-01-07T14:35:00+09:00")
        texts = [s.text for s in bc.segments]
        self.assertEqual(len(texts), 5)
        self.assertFalse(any(t.startswith(("판촉", "발화", "조건")) for t in texts))
        self.assertEqual(bc.segments[3].start_sec, 62.0)
        self.assertEqual(bc.segments[-1].start_sec, 68 * 60 + 57)  # 60분 넘는 MM:SS
        self.assertEqual(bc.segments[0].end_sec, 7.0)

    def test_rhythm_and_highlights_kept(self):
        bc = parse_copy_text(SAMPLE, channel="gsshop", product_name="다이슨",
                             start_datetime="2026-01-07T14:35:00+09:00")
        self.assertEqual(bc.extra["rhythm_timeline"],
                         [{"m": 1, "segs": 16, "promo": 1, "pct": 6, "quiet": False}])
        self.assertEqual(bc.extra["highlights"], [{"label": "조건", "start": 20, "end": 30}])

    def test_filename(self):
        self.assertEqual(parse_filename("C:/x/260621_HD_다이슨 디지털 슬림.txt"),
                         {"date": "2026-06-21", "channel": "hmall", "product_name": "다이슨 디지털 슬림"})
        self.assertEqual(parse_filename("260107_GS_다이슨.txt")["channel"], "gsshop")
        self.assertEqual(parse_filename("메모.txt")["date"], "")


if __name__ == "__main__":
    unittest.main()
