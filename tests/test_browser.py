import unittest

from nadlan_balagan.browser import _parse_results


class ResultParsingTests(unittest.TestCase):
    def test_extracts_count_page_and_repeated_rows(self):
        html = """<span id='lblresh'>נמצאו: 2 רשומות</span>
          <span id='lblPage'>דף 1 מתוך 1</span>
          <table id='ContentUsersPage_GridMultiD1'><tr><th>גוש</th><th>מחיר</th></tr>
          <tr><td>30303</td><td>100</td></tr><tr><td>30303</td><td>100</td></tr></table>"""
        columns, rows, count, current, total = _parse_results(html)
        self.assertEqual(columns, ["גוש", "מחיר"])
        self.assertEqual(rows, [["30303", "100"], ["30303", "100"]])
        self.assertEqual((count, current, total), (2, 1, 1))

    def test_zero_results_without_grid(self):
        html = "<span id='lblresh'>נמצאו: 0 רשומות</span><span id='lblPage'>דף 1 מתוך 1</span>"
        self.assertEqual(_parse_results(html), ([], [], 0, 1, 1))

    def test_ignores_pagination_row(self):
        html = """<span id='lblresh'>נמצאו: 2 רשומות</span><span id='lblPage'>דף 1 מתוך 2</span>
          <table id='ContentUsersPage_GridMultiD1'><tr><th>גוש</th><th>מחיר</th></tr>
          <tr><td>30303</td><td>100</td></tr>
          <tr><td colspan='2'><a href="javascript:__doPostBack('x','Page$2')">2</a></td></tr></table>"""
        self.assertEqual(_parse_results(html), (["גוש", "מחיר"], [["30303", "100"]], 2, 1, 2))

    def test_missing_count_is_failure(self):
        with self.assertRaisesRegex(RuntimeError, "count"):
            _parse_results("<p>CAPTCHA still open</p>")
