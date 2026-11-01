import unittest
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import planetprint as pp

LIST = """AVTO MAKTAB 12.180.000 SOM
NOTARIUS 3.800.000 SOM
ZAMENA MASLA 1.100.000 SOM
39 MAKTAB 200.000 SOM"""


class PlanetPrintTests(unittest.TestCase):
    def setUp(self):
        pp.STATE.parent.mkdir(parents=True, exist_ok=True)

    def test_parse_and_classify_without_ai(self):
        items = pp.parse(LIST)
        self.assertEqual([i["amount"] for i in items], [12180000, 3800000, 1100000, 200000])
        self.assertEqual(items[3]["name"], "39 MAKTAB")
        self.assertEqual(pp.parse("bugun 2 ta zakaz bor"), [])
        kinds = {i["name"]: i["kind"] for i in pp.classify(items, [])}
        self.assertEqual(kinds["ZAMENA MASLA"], "material")
        self.assertEqual(kinds["AVTO MAKTAB"], "boshqa")
        self.assertIn("XARAJAT", pp.report_text(pp.classify(items, []), "Ishchilar", "Jasur"))

    def test_add_expense_allocates_full_amount_to_project(self):
        fin = {"projects": [{"id": "p1", "name": "RAPQON pilon", "status": "Jarayonda"}], "expenses": []}
        sent = {}
        def api(method, path, **kw):
            if method == "GET":
                return {"finance": {**fin, "expenses": list(fin["expenses"])}, "revision": 7}
            sent.update(kw["json"])
            return {"ok": True}
        with patch.object(pp, "_api", side_effect=api):
            pp.add_expense("ZAMENA MASLA", 1100000, "Jasur ro'yxati", "p1", "naqd")
        rec = sent["finance"]["expenses"][0]
        self.assertEqual(sent["revision"], 7)
        self.assertEqual(rec["allocations"], [{"projectId": "p1", "amount": 1100000.0}])
        self.assertEqual((rec["type"], rec["paymentType"]), ("ZAMENA MASLA", "naqd"))
        with patch.object(pp, "_api", side_effect=api), self.assertRaises(RuntimeError):
            pp.add_expense("X", 1000, "", "yoq", "naqd")


if __name__ == "__main__":
    unittest.main()
