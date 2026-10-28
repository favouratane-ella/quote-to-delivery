"""Sample data for the simulated world. Every company, person, order and figure is made up."""
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import models as m

ITEMS = [
    # sku, name, on hand, unit, reorder point, reorder quantity, substitute
    ("CC-210", "Cold-chain crate 60L", 260, "crates", 100, 600, None),
    ("TS-88", "Temperature sensor tag", 300, "tags", 200, 2000, "TS-90"),
    ("IB-12", "Insulated shipping box", 80, "boxes", 100, 600, "IB-15"),
    ("GP-05", "Gel cold pack", 1500, "packs", 1000, 5000, None),
    ("PL-400", "Thermal pallet liner", 150, "liners", 200, 1500, None),
    ("TS-90", "Temperature sensor tag, long life", 350, "tags", 100, 1000, None),
    ("IB-15", "Insulated shipping box, large", 120, "boxes", 60, 400, None),
    ("DL-20", "Cold-chain data logger", 60, "loggers", 80, 300, None),
    ("PK-300", "Pallet wrap 300m", 900, "rolls", 400, 1500, None),
    ("DI-55", "Dry ice pellets 10kg", 200, "bags", 300, 800, None),
    ("SL-10", "Tamper seal strip", 5000, "strips", 2000, 8000, None),
]
SUPPLIERS = {
    "Lakeside Plastics": "dispatch@lakeside-plastics.example",
    "Nordtherm Sensors": "orders@nordtherm.example",
    "Vexa Packaging": "supply@vexa-pack.example",
    "Coolchain Gel Co": "sales@coolchain-gel.example",
    "Datalogic Systems": "orders@datalogic.example",
    "Packwell Industrial": "sales@packwell.example",
    "Frostline Supplies": "dispatch@frostline.example",
    "Warehouse team": "warehouse@internal.example",  # our own stock notes arrive in the same inbox
}
POS = [
    ("PO-8841", "Lakeside Plastics", "CC-210", [{"qty": 280, "date": "2026-11-02"}]),
    ("PO-8850", "Nordtherm Sensors", "TS-88", [{"qty": 2000, "date": "2026-10-30"}]),
    ("PO-8856", "Vexa Packaging", "IB-12", [{"qty": 600, "date": "2026-11-04"}]),
    ("PO-8860", "Coolchain Gel Co", "GP-05", [{"qty": 5000, "date": "2026-11-06"}]),
    ("PO-8863", "Vexa Packaging", "PL-400", [{"qty": 1500, "date": "2026-11-09"}]),
    ("PO-8871", "Lakeside Plastics", "CC-210", [{"qty": 600, "date": "2026-11-16"}]),
    ("PO-8880", "Datalogic Systems", "DL-20", [{"qty": 400, "date": "2026-11-10"}]),
    ("PO-8883", "Packwell Industrial", "PK-300", [{"qty": 1200, "date": "2026-11-05"}]),
    ("PO-8886", "Frostline Supplies", "DI-55", [{"qty": 600, "date": "2026-11-03"}]),
    ("PO-8889", "Packwell Industrial", "SL-10", [{"qty": 8000, "date": "2026-11-07"}]),
    ("PO-8892", "Nordtherm Sensors", "TS-90", [{"qty": 1000, "date": "2026-11-12"}]),
]
# name: (transit days, days saved by express, express cost)
LANES = {"Local": (1, 1, 120), "Regional": (2, 1, 380), "National": (3, 2, 850)}
CUSTOMERS = [
    # id, name, tier, yearly value, renewal, contact, email, lane, owner, flexibility, days late they can live with, why, how the simulated customer replies
    ("northwind", "Northwind Foods", "A", 410000, "2026-11-16", "Dana Reyes", "dana.reyes@northwind.example", "Regional", "Sam Okafor", "partial", 5, "", "partial"),
    ("harbor", "Harbor Grocers", "A", 260000, "2027-03-01", "Malik Osei", "malik.osei@harborgrocers.example", "National", "Sam Okafor", "partial", 5, "", "credit"),
    ("delta", "Delta Catering", "B", 90000, "2027-06-12", "Priya Nair", "priya@deltacatering.example", "Local", "Lena Brandt", "flexible", 10, "", "accept"),
    ("kestrel", "Kestrel Hotels", "B", 120000, "2027-01-20", "Tom Becker", "tom.becker@kestrelhotels.example", "National", "Lena Brandt", "hard", 0, "Hotel opening weekend on 11 Nov. Guests are already booked.", "hard"),
    ("alder", "Alder Mills", "A", 300000, "2027-05-02", "Ines Duarte", "ines@aldermills.example", "Local", "Sam Okafor", "flexible", 7, "", "accept"),
    ("cobalt", "Cobalt Retail", "B", 150000, "2027-02-14", "Ravi Shah", "ravi.shah@cobaltretail.example", "National", "Lena Brandt", "flexible", 10, "", "expedite"),
    ("fernhill", "Fernhill Foods", "C", 40000, "2027-08-30", "Abby Lund", "abby@fernhillfoods.example", "Local", "Joy Mensah", "flexible", 21, "", "silent"),
    ("juno", "Juno Bakery", "C", 25000, "2027-04-10", "Kofi Adjei", "kofi@junobakery.example", "Local", "Joy Mensah", "flexible", 14, "", "cancel"),
    ("orchard", "Orchard & Pine", "B", 110000, "2027-02-02", "Hana Ito", "hana.ito@orchardpine.example", "Regional", "Lena Brandt", "partial", 4, "", "question"),
    ("meridian", "Meridian Pharma", "A", 520000, "2026-12-05", "Owen Clarke", "owen.clarke@meridianpharma.example", "Regional", "Sam Okafor", "hard", 0, "Clinical trial shipment. The site cannot receive after 2 Nov.", "hard"),
    ("atlas", "Atlas Labs", "A", 380000, "2026-12-18", "Rita Moyo", "rita.moyo@atlaslabs.example", "Regional", "Sam Okafor", "hard", 0, "New lab commissioning is locked to 12 Nov.", "hard"),
    ("bluefin", "Bluefin Seafood", "B", 140000, "2027-03-20", "Jonas Berg", "jonas@bluefinseafood.example", "Regional", "Lena Brandt", "partial", 3, "", "partial"),
    ("crestline", "Crestline Dairy", "B", 95000, "2027-05-11", "Tessa Lowe", "tessa@crestlinedairy.example", "Local", "Joy Mensah", "flexible", 10, "", "accept"),
    ("dunmore", "Dunmore Pharmacy", "C", 35000, "2027-01-09", "Gus Ramos", "gus@dunmorepharmacy.example", "Local", "Joy Mensah", "partial", 2, "", "question"),
    ("ember", "Ember Kitchens", "C", 28000, "2027-07-21", "Lia Chen", "lia@emberkitchens.example", "Local", "Joy Mensah", "flexible", 14, "", "silent"),
    ("fjord", "Fjord Logistics", "A", 450000, "2026-11-30", "Nils Haugen", "nils@fjordlogistics.example", "National", "Sam Okafor", "flexible", 5, "", "expedite"),
]
# so, customer, sku, qty, value, promised, from stock, po, from po
ORDERS = [
    ("SO-5532", "northwind", "CC-210", 160, 48200, "2026-11-04", 0, "PO-8841", 160),
    ("SO-5547", "harbor", "CC-210", 100, 31900, "2026-11-05", 20, "PO-8841", 80),
    ("SO-5561", "delta", "CC-210", 30, 12400, "2026-11-06", 0, "PO-8841", 30),
    ("SO-5570", "kestrel", "CC-210", 10, 9800, "2026-11-11", 0, "PO-8841", 10),
    ("SO-5579", "orchard", "CC-210", 120, 36100, "2026-10-29", 120, None, 0),
    ("SO-5519", "alder", "TS-88", 1200, 22100, "2026-11-03", 0, "PO-8850", 1200),
    ("SO-5575", "meridian", "TS-88", 600, 36500, "2026-11-02", 0, "PO-8850", 600),
    ("SO-5524", "cobalt", "IB-12", 300, 17300, "2026-11-07", 0, "PO-8856", 300),
    ("SO-5538", "fernhill", "GP-05", 2000, 8900, "2026-11-09", 0, "PO-8860", 2000),
    ("SO-5552", "juno", "PL-400", 400, 5600, "2026-11-12", 0, "PO-8863", 400),
    ("SO-5601", "atlas", "DL-20", 150, 21000, "2026-11-12", 0, "PO-8880", 150),
    ("SO-5606", "fjord", "DL-20", 120, 16800, "2026-11-14", 0, "PO-8880", 120),
    ("SO-5610", "crestline", "PK-300", 400, 3200, "2026-11-08", 0, "PO-8883", 400),
    ("SO-5614", "ember", "PK-300", 300, 2400, "2026-11-10", 0, "PO-8883", 300),
    ("SO-5620", "bluefin", "DI-55", 300, 6900, "2026-11-05", 0, "PO-8886", 300),
    ("SO-5624", "dunmore", "DI-55", 200, 4600, "2026-11-06", 200, None, 0),
    ("SO-5630", "alder", "SL-10", 3000, 5100, "2026-11-09", 0, "PO-8889", 3000),
    ("SO-5638", "fjord", "TS-90", 500, 9500, "2026-11-16", 0, "PO-8892", 500),
]
QUOTES = [
    ("Q-2041", "orchard", "CC-210", 400, "2026-10-30"),
    ("Q-2042", "meridian", "TS-88", 500, "2026-11-03"),
    ("Q-2043", "cobalt", "GP-05", 1000, "2026-11-04"),
    ("Q-2044", "kestrel", "IB-12", 500, "2026-11-10"),
    ("Q-2045", "atlas", "DL-20", 100, "2026-11-11"),
    ("Q-2046", "crestline", "PK-300", 500, "2026-11-07"),
    ("Q-2047", "bluefin", "DI-55", 250, "2026-11-06"),
    ("Q-2048", "fjord", "TS-90", 400, "2026-11-12"),
]
EMAILS = [
    dict(sender="Warehouse team", received_at="2026-10-26T12:45", subject="Recount: TS-88",
         body="Hi planning,\n\nWe recounted TS-88 sensor tags after a pick error. The count shows only 30 on the shelf. Please update the stock.\n\nDock supervisor",
         attachment=None),
    dict(sender="Warehouse team", received_at="2026-10-26T12:30", subject="Cycle count variance: DI-55",
         body="Hi planning,\n\nCycle count this morning on DI-55 dry ice: 40 bags were damaged in the cold room failure and have been written off. Counted on hand is now 160 bags.\n\nDock supervisor",
         attachment=None),
    dict(sender="Vexa Packaging", received_at="2026-10-26T12:00", subject="Question on PO-8856",
         body="Hi,\n\nQuick question for the planner: do you want the remaining 200 boxes on PO-8856 sent to the same warehouse as the first 400, or held for collection?\n\nThanks,\nCarla",
         attachment=None),
    dict(sender="Datalogic Systems", received_at="2026-10-26T11:20", subject="PO-8880 delayed, new ship date",
         body="Hello,\n\nThe latest firmware batch failed certification, so we have to re-test all units. PO-8880 (400 data loggers, DL-20) will now ship on Wednesday 18 November instead of Tuesday 10 November.\n\nWe are sorry for the trouble.\n\nRegards,\nPetra Voss\nOrder desk, Datalogic Systems",
         attachment={"name": "PO-8880_revised_schedule.pdf", "title": "Revised ship schedule", "rows": [["Purchase order", "PO-8880"], ["Item", "DL-20 Cold-chain data logger"], ["Quantity", "400"], ["Original ship date", "10 Nov 2026"], ["Revised ship date", "18 Nov 2026"], ["Reason", "Firmware re-certification"]]}),
    dict(sender="Nordtherm Sensors", received_at="2026-10-26T11:05", subject="PO-8892 quality hold",
         body="Hi team,\n\nPart of PO-8892 is on a quality hold after an incoming inspection. We may be able to release it next week, but we cannot say yet. I will confirm.\n\nJonas",
         attachment=None),
    dict(sender="Packwell Industrial", received_at="2026-10-26T10:45", subject="PO-8883 short shipment",
         body="Hello,\n\nOur wrap line is short on film this week. We can only ship 900 of the 1,200 pallet wrap rolls on PO-8883 on 5 November. The remaining 300 will follow on 12 November.\n\nApologies,\nHelen Park\nPackwell Industrial",
         attachment=None),
    dict(sender="Frostline Supplies", received_at="2026-10-26T10:10", subject="PO-8886 delayed",
         body="Hi,\n\nOur ice plant had an unplanned shutdown. PO-8886 (600 bags of dry ice, DI-55) will now arrive on Sunday 8 November instead of Tuesday 3 November. Dry ice cannot be stored long, so we cannot ship early.\n\nSorry,\nMike Hale\nFrostline Supplies",
         attachment=None),
    dict(sender="Lakeside Plastics", received_at="2026-10-26T09:50", subject="PO-8871 new arrival date",
         body="Hello,\n\nThe resin shortage continues. PO-8871 (600 cold-chain crates) will now arrive on Monday 23 November instead of Monday 16 November.\n\nRegards,\nMarta",
         attachment=None),
    dict(sender="Packwell Industrial", received_at="2026-10-26T09:35", subject="PO-8889 arriving early",
         body="Good news: our run finished early, so PO-8889 (8,000 tamper seal strips) will arrive on Wednesday 4 November, ahead of the 7th.\n\nHelen",
         attachment=None),
    dict(sender="Lakeside Plastics", received_at="2026-10-26T09:12", subject="PO-8841 delayed, new ship date",
         body="Hello,\n\nOur injection press line was down for repairs over the weekend. We are sorry to say PO-8841 (280 cold-chain crates, CC-210) will now arrive on Saturday 7 November instead of Monday 2 November.\n\nThe revised confirmation is attached. Everything else on the order is unchanged.\n\nKind regards,\nMarta Nowak\nDispatch, Lakeside Plastics",
         attachment={"name": "PO-8841_revised_confirmation.pdf", "title": "Revised order confirmation", "rows": [["Purchase order", "PO-8841"], ["Item", "CC-210 Cold-chain crate 60L"], ["Quantity", "280"], ["Original arrival", "02 Nov 2026"], ["Revised arrival", "07 Nov 2026"], ["Reason", "Press line maintenance"]]}),
    dict(sender="Nordtherm Sensors", received_at="2026-10-26T08:40", subject="Order confirmation PO-8850",
         body="Hi team,\n\nConfirming that PO-8850 for 2,000 TS-88 sensor tags is on schedule and will reach your warehouse on Friday 30 October. Packing list attached.\n\nBest,\nJonas",
         attachment={"name": "PO-8850_packing_list.pdf", "title": "Packing list", "rows": [["Purchase order", "PO-8850"], ["Item", "TS-88 Temperature sensor tag"], ["Cartons", "20 x 100"], ["Ship date", "28 Oct 2026"], ["Arrival", "30 Oct 2026"]]}),
    dict(sender="Vexa Packaging", received_at="2026-10-25T16:05", subject="PO-8856 split shipment",
         body="Hello,\n\nWe can only finish part of PO-8856 this week. We will send 400 insulated boxes on Wednesday 4 November and the remaining 200 on Thursday 12 November.\n\nLet me know if that causes any problems.\n\nThanks,\nCarla",
         attachment=None),
    dict(sender="Coolchain Gel Co", received_at="2026-10-25T11:30", subject="2027 price list",
         body="Dear customer,\n\nPlease find our 2027 price list attached. Prices take effect on 1 January 2027. Your current orders are not affected.\n\nRegards,\nCoolchain Gel Co",
         attachment={"name": "Coolchain_2027_prices.pdf", "title": "Price list 2027", "rows": [["GP-05 Gel cold pack", "$0.42 per pack"], ["GP-09 Large gel pack", "$0.71 per pack"], ["Effective", "01 Jan 2027"]]}),
    dict(sender="Vexa Packaging", received_at="2026-10-24T14:22", subject="Re: PO-8863",
         body="Hi,\n\nFollowing up on your question. The film supplier has let us down, so the thermal liners on PO-8863 are now slipping to Friday 20 November. We will confirm once they ship.\n\nCarla",
         attachment=None),
]
TEST_PACK = [
    ("T01", "PO-8841 will now ship on 7 Nov instead of 2 Nov due to press repairs.", "delay", "PO-8841", "2026-11-07"),
    ("T02", "Confirming PO-8850 is on schedule for 30 Oct.", "confirmation", "PO-8850", None),
    ("T03", "PO-8856: we can send 400 units on 4 Nov and the remaining 200 on 12 Nov.", "partial", "PO-8856", "2026-11-12"),
    ("T04", "Attached is our 2027 price list for your records.", "other", None, None),
    ("T05", "Due to a port strike, PO-8860 is pushed back by one week from 6 Nov.", "delay", "PO-8860", "2026-11-13"),
    ("T06", "Good news: PO-8863 is not delayed and will arrive 9 Nov as planned.", "confirmation", "PO-8863", None),
    ("T07", "Re PO-8871: the crates will arrive on the 20th of November now, not the 16th.", "delay", "PO-8871", "2026-11-20"),
    ("T08", "Shipment for PO-8850 slipping to Tuesday 3 November.", "delay", "PO-8850", "2026-11-03"),
    ("T09", "Can you confirm the delivery address for PO-8856?", "other", "PO-8856", None),
    ("T10", "PO-8841 now arriving 9 Nov. Ignore our earlier note that said 7 Nov.", "delay", "PO-8841", "2026-11-09"),
    ("T11", "We will deliver PO-8860 in two parts: 3,000 on 6 Nov and 2,000 on 10 Nov.", "partial", "PO-8860", "2026-11-10"),
    ("T12", "Our support email has changed to help@coolchain-gel.example.", "other", None, None),
    ("T13", "Revised ETA for PO-8856: 10/11/2026.", "delay", "PO-8856", "2026-11-10"),
    ("T14", "Hi, PO-8871 will be about 3 days late.", "delay", "PO-8871", "2026-11-19"),
    ("T15", "We need to postpone delivery of PO 8863 to November 14th.", "delay", "PO-8863", "2026-11-14"),
    ("T16", "PO-8850 might be delayed, we will confirm a new date tomorrow.", "unclear", "PO-8850", None),
    ("T17", "Please confirm you received our invoice for PO-8841.", "other", "PO-8841", None),
    ("T18", "PO-8860 is running two weeks behind schedule.", "delay", "PO-8860", "2026-11-20"),
    ("T19", "Your order PO-8841 is on track for Monday 2 November.", "confirmation", "PO-8841", None),
    ("T20", "Update on P.O. 8856: delivery moved to Nov 6.", "delay", "PO-8856", "2026-11-06"),
    ("T21", "PO-8863: 900 liners will arrive on 9 Nov, the balance of 600 follows on 16 Nov.", "partial", "PO-8863", "2026-11-16"),
    ("T22", "Unfortunately PO-8871 has slipped a week.", "delay", "PO-8871", "2026-11-23"),
    ("T23", "Correction to our last email: PO-8850 now lands Wednesday 4 November, not 3 November.", "delay", "PO-8850", "2026-11-04"),
    ("T24", "There is a risk PO-8841 could slip, no firm date yet.", "unclear", "PO-8841", None),
    ("T25", "PO-8856 has been dispatched and will arrive 4 Nov as scheduled.", "confirmation", "PO-8856", None),
    ("T26", "Good news, PO-8860 is coming early: expect it on 3 November.", "delay", "PO-8860", "2026-11-03"),
    ("T27", "Could you send us the delivery address for PO-8863?", "other", "PO-8863", None),
    ("T28", "Shipment PO-8841: ETA 2026-11-08.", "delay", "PO-8841", "2026-11-08"),
    ("T29", "Our office will be closed on 2 November for a public holiday.", "other", None, None),
    ("T30", "PO-8850 delayed by 5 business days.", "delay", "PO-8850", "2026-11-06"),
    ("T31", "Re: PO-8863, the liners won't make 9 Nov. New date is 13 November.", "delay", "PO-8863", "2026-11-13"),
    ("T32", "PO-8856 will arrive in three lots: 200 on 4 Nov, 200 on 8 Nov and 200 on 12 Nov.", "partial", "PO-8856", "2026-11-12"),
    ("T33", "We confirm PO-8871 for delivery on 16/11.", "confirmation", "PO-8871", None),
    ("T34", "PO-8841 is delayed. Revised arrival date to follow.", "unclear", "PO-8841", None),
    ("T35", "Following up: no change to PO-8860, still arriving 6 November.", "confirmation", "PO-8860", None),
    ("T36", "Heads up: PO-8863 may arrive late next week.", "unclear", "PO-8863", None),
    ("T37", "PO-8871 delivery date changed from 16 Nov to 21 Nov.", "delay", "PO-8871", "2026-11-21"),
    ("T38", "Thank you for your payment on PO-8841.", "other", "PO-8841", None),
    ("T39", "We can deliver PO-8860 on Tuesday 10 November instead.", "delay", "PO-8860", "2026-11-10"),
    ("T40", "Dear team, PO-8850 cannot ship as planned; it will now reach you on the 5th of November.", "delay", "PO-8850", "2026-11-05"),
    # T41-T65: held-out cases written after the parser was built (first run: 23 of 25)
    ("T41","Hello, due to a machine breakdown PO-8841 will be delivered on 9th November.","delay","PO-8841","2026-11-09"),
    ("T42","PO-8850: arrival confirmed for 30 Oct.","confirmation","PO-8850",None),
    ("T43","Sorry, PO-8856 is delayed by about a week.","delay","PO-8856","2026-11-11"),
    ("T44","We expect PO-8863 to ship late. Will revert with a firm date.","unclear","PO-8863",None),
    ("T45","Purchase order 8871 has been rescheduled to 25 November.","delay","PO-8871","2026-11-25"),
    ("T46","Hi, just checking: did you get our new catalogue?","other",None,None),
    ("T47","PO-8860 will arrive in two batches: 2,500 on 6 Nov and 2,500 on 11 Nov.","partial","PO-8860","2026-11-11"),
    ("T48","No changes on PO-8841, it arrives Monday 2 November as agreed.","confirmation","PO-8841",None),
    ("T49","PO-8850 is held up at customs. New ETA 03/11.","delay","PO-8850","2026-11-03"),
    ("T50","Can you please confirm the quantity on PO-8856?","other","PO-8856",None),
    ("T51","Delivery for PO-8863 now expected 12 Nov instead of 9 Nov.","delay","PO-8863","2026-11-12"),
    ("T52","PO-8871 could be a few days late, we are not sure yet.","unclear","PO-8871",None),
    ("T53","Please note PO-8860 has moved to Wednesday 11 November.","delay","PO-8860","2026-11-11"),
    ("T54","Your PO-8841 shipment left our warehouse today and will arrive on 2 Nov.","confirmation","PO-8841",None),
    ("T55","PO-8856: 300 boxes arrive 4 Nov, the remaining 300 on 10 Nov.","partial","PO-8856","2026-11-10"),
    ("T56","We regret PO-8850 will be 2 weeks late.","delay","PO-8850","2026-11-13"),
    ("T57","Merry Christmas from all of us at Vexa!","other",None,None),
    ("T58","PO-8863 pushed to November 18.","delay","PO-8863","2026-11-18"),
    ("T59","Re PO-8871: still on schedule for the 16th.","confirmation","PO-8871",None),
    ("T60","PO-8841 delivery has been brought forward to 31 October.","delay","PO-8841","2026-10-31"),
    ("T61","Attached is the packing list for PO-8850. Delivery date unchanged.","confirmation","PO-8850",None),
    ("T62","PO-8860 delayed. New date: Monday 16 November.","delay","PO-8860","2026-11-16"),
    ("T63","PO-8856 may slip; we will let you know.","unclear","PO-8856",None),
    ("T64","Update: PO-8863 now arrives Friday 13th November (previously 9th).","delay","PO-8863","2026-11-13"),
    ("T65","PO-8871 delayed three days.","delay","PO-8871","2026-11-19"),
    # T66-T75: written after the larger sample data exposed gaps (a PO number read as a quantity, "ahead of the 7th", an "Original ship date" label, a quality hold)
    ("T66","Hello, we can ship 900 of the 1,200 rolls on PO-8883 on 5 November and the remaining 300 on 12 November.","partial","PO-8883","2026-11-12"),
    ("T67","PO-8889 will arrive on Wednesday 4 November, ahead of the 7th.","delay","PO-8889","2026-11-04"),
    ("T68","Revised order confirmation for PO-8880. Original ship date 10 Nov 2026. Revised ship date 18 Nov 2026.","delay","PO-8880","2026-11-18"),
    ("T69","PO-8892 is on a quality hold. We cannot say when it will be released.","unclear","PO-8892",None),
    ("T70","Can you advise where PO-8856 should be delivered?","other","PO-8856",None),
    ("T71","PO-8886 will now arrive on 8 November instead of 3 November.","delay","PO-8886","2026-11-08"),
    ("T72","We will ship 300 of the 600 on PO-8860 on 6 Nov and the rest on 13 Nov.","partial","PO-8860","2026-11-13"),
    ("T73","Delivery for PO-8841 has moved earlier than planned, to 30 October.","delay","PO-8841","2026-10-30"),
    ("T74","PO-8871 order 600 pcs confirmed for 16 November, no change.","confirmation","PO-8871",None),
    ("T75","PO-8860 cancelled by our factory, we cannot supply this order.","other","PO-8860",None),
]
TEMPLATES = {
    "big": ("Delay hitting big customers (PO-8850)", "Nordtherm Sensors", "PO-8850 delayed", "Hi team,\n\nCustoms is holding our container. PO-8850 for 2,000 sensor tags will now reach you on Thursday 5 November, not Friday 30 October.\n\nJonas"),
    "delay": ("Delay with no customer impact (PO-8871)", "Lakeside Plastics", "PO-8871 new arrival date", "Hello,\n\nA resin shortage means PO-8871 (600 cold-chain crates) will now arrive on Monday 23 November instead of Monday 16 November.\n\nRegards,\nMarta Nowak"),
    "relative": ('Delay as "one week later" (PO-8860)', "Coolchain Gel Co", "PO-8860 delay", "Hello,\n\nDue to a port strike, PO-8860 (5,000 gel packs) is pushed back by one week.\n\nRegards,\nCoolchain Gel Co"),
    "split": ("Split shipment (PO-8863)", "Vexa Packaging", "PO-8863 in two parts", "Hi,\n\nWe can ship 1,000 thermal liners from PO-8863 on 9 November and the other 500 on 18 November.\n\nCarla"),
    "notdelayed": ('"Not delayed" confirmation', "Vexa Packaging", "PO-8863 update", "Hi,\n\nGood news: PO-8863 is not delayed and the liners will arrive on 9 November as planned.\n\nCarla"),
    "vague": ("Vague warning, no date", "Nordtherm Sensors", "Heads up on PO-8850", "Hi team,\n\nHeads up: the sensor tags on PO-8850 might slip next week. We will confirm a firm date by Friday.\n\nJonas"),
    "unknown": ("Unknown PO number", "Lakeside Plastics", "PO-9921 new date", "Hello,\n\nPO-9921 will now arrive on 12 November instead of 5 November.\n\nMarta"),
    "blank": ("Write your own", "Lakeside Plastics", "", ""),
}


def delete_world(db: Session, world_id: str) -> None:
    run_ids = [r.id for r in db.query(m.Run.id).filter(m.Run.world_id == world_id)]
    if run_ids:
        db.execute(delete(m.RunStep).where(m.RunStep.run_id.in_(run_ids)))
        db.execute(delete(m.Run).where(m.Run.id.in_(run_ids)))
    for t in m.WORLD_TABLES:
        db.execute(delete(t).where(t.world_id == world_id))
    db.execute(delete(m.World).where(m.World.id == world_id))
    db.commit()


def create_world(db: Session, world_id: str = "main", kind: str = "main", with_mail: bool = True, with_quotes: bool = True) -> None:
    """(Re)create a world with the sample data."""
    delete_world(db, world_id)
    w = world_id
    db.add(m.World(id=w, kind=kind))
    db.add(m.Settings(world_id=w))
    db.add_all(m.Item(world_id=w, sku=s, name=n, on_hand=oh, unit=u, reorder_point=rp, reorder_qty=rq, substitute=sub) for s, n, oh, u, rp, rq, sub in ITEMS)
    db.add_all(m.Supplier(world_id=w, name=n, email=e) for n, e in SUPPLIERS.items())
    db.add_all(m.PurchaseOrder(world_id=w, po=p, supplier=s, sku=k, deliveries=d, original=d) for p, s, k, d in POS)
    db.add_all(m.Lane(world_id=w, name=n, days=d, express_saves=sv, express_cost=cost) for n, (d, sv, cost) in LANES.items())
    db.add_all(m.Customer(world_id=w, id=i, name=n, tier=t, arr=a, renewal=r, contact=c, email=e, lane=l, owner=o, flex=fx, max_slip=ms, hard_reason=hr, reply_style=rs)
               for i, n, t, a, r, c, e, l, o, fx, ms, hr, rs in CUSTOMERS)
    db.add_all(m.SalesOrder(world_id=w, so=so, customer_id=c, sku=k, qty=q, value=v, promised=p, stock_qty=s, po=po, po_qty=pq) for so, c, k, q, v, p, s, po, pq in ORDERS)
    if with_quotes:
        db.add_all(m.Quote(world_id=w, q=q, customer_id=c, sku=k, qty=n, requested=r) for q, c, k, n, r in QUOTES)
    if with_mail:
        for e in reversed(EMAILS):
            db.add(m.Email(world_id=w, address=SUPPLIERS[e["sender"]], **e))
    db.add(m.ActivityLog(world_id=w, actor="System", system="All", text="Simulated world created: sample ERP, CRM, supplier mailbox and carrier lanes."))
    db.commit()


def ensure_main_world(db: Session) -> None:
    if not db.get(m.World, "main"):
        create_world(db, "main")
