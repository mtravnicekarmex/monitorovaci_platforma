import datetime
import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.SCVK.fakturace_pdf import (
    apply_invoice_consumption_to_payload,
    apply_price_intervals_to_payload,
    parse_scvk_invoice_text,
)


def test_parse_scvk_invoice_text_extracts_period_consumption_and_branch():
    text = """
    SčVK vyúčtování
    Zúčtovací období 01.03.2026 - 31.03.2026
    Odběrné místo 681041132
    Fakturované množství 18,5 m3
    """

    parsed = parse_scvk_invoice_text(text)

    assert parsed.period_start == datetime.date(2026, 3, 1)
    assert parsed.period_end == datetime.date(2026, 3, 31)
    assert parsed.total_consumption_m3 == 18.5
    assert parsed.billing_ident == "SCVK_HE"
    assert parsed.notes == ()


def test_parse_scvk_invoice_text_accepts_single_digit_consumption():
    text = """
    Fakturované období od 01.04.2026 do 30.04.2026
    Celková spotřeba: 8 m3
    Číslo hlavy IOTW-049674
    """

    parsed = parse_scvk_invoice_text(text)

    assert parsed.period_start == datetime.date(2026, 4, 1)
    assert parsed.period_end == datetime.date(2026, 4, 30)
    assert parsed.total_consumption_m3 == 8.0
    assert parsed.billing_ident == "SCVK_GR"


def test_parse_scvk_invoice_text_extracts_combined_price_intervals():
    text = """
    SčVK vyúčtování
    Zúčtovací období 01.03.2026 - 31.03.2026
    Vodné 01.03.2026 - 15.03.2026 10,0 m3 64,23 Kč/m3 642,30 Kč
    Stočné 01.03.2026 - 15.03.2026 10,0 m3 51,10 Kč/m3 511,00 Kč
    Vodné 16.03.2026 - 31.03.2026 8,5 m3 67,00 Kč/m3 569,50 Kč
    Stočné 16.03.2026 - 31.03.2026 8,5 m3 53,00 Kč/m3 450,50 Kč
    Celková spotřeba 18,5 m3
    """

    parsed = parse_scvk_invoice_text(text)

    assert [(row.start_date, row.end_date, row.price_per_m3) for row in parsed.price_intervals] == [
        (datetime.date(2026, 3, 1), datetime.date(2026, 3, 15), 115.33),
        (datetime.date(2026, 3, 16), datetime.date(2026, 3, 31), 120.0),
    ]


def test_apply_invoice_consumption_to_payload_uses_submeter_ratio_for_allocation():
    payload = {
        "billing_consumption": 52.0,
        "submeter_consumption_total": 40.0,
        "difference": 12.0,
        "coverage_percent": 76.9,
        "device_rows": [
            {
                "identifikace": "A",
                "spotreba": 30.0,
                "podil_na_podruznych_procent": 75.0,
                "podil_na_fakturacnim_procent": 57.7,
                "rozpoctena_fakturacni_spotreba": 39.0,
            },
            {
                "identifikace": "B",
                "spotreba": 10.0,
                "podil_na_podruznych_procent": 25.0,
                "podil_na_fakturacnim_procent": 19.2,
                "rozpoctena_fakturacni_spotreba": 13.0,
            },
        ],
        "assignment_rows": [
            {
                "identifikace": "A",
                "start_time": datetime.datetime(2026, 4, 1, 0, 0, 0),
                "end_time": datetime.datetime(2026, 4, 30, 23, 59, 59),
                "duration_hours": 720.0,
            }
        ],
        "segment_rows": [
            {
                "start_time": datetime.datetime(2026, 4, 1, 0, 0, 0),
                "end_time": datetime.datetime(2026, 4, 15, 23, 59, 59),
                "submeter_consumption": 10.0,
                "billing_consumption": 13.0,
                "difference": 3.0,
                "device_consumptions": [
                    {"identifikace": "A", "spotreba": 6.0},
                    {"identifikace": "B", "spotreba": 4.0},
                ],
            },
            {
                "start_time": datetime.datetime(2026, 4, 16, 0, 0, 0),
                "end_time": datetime.datetime(2026, 4, 30, 23, 59, 59),
                "submeter_consumption": 30.0,
                "billing_consumption": 39.0,
                "difference": 9.0,
                "device_consumptions": [
                    {"identifikace": "A", "spotreba": 24.0},
                    {"identifikace": "B", "spotreba": 6.0},
                ],
            },
        ],
    }

    updated = apply_invoice_consumption_to_payload(payload, 60.0)

    assert updated["billing_consumption_source"] == "invoice_pdf"
    assert updated["reference_billing_consumption"] == 52.0
    assert updated["invoice_billing_consumption"] == 60.0
    assert updated["billing_consumption"] == 60.0
    assert updated["difference"] == 20.0
    assert updated["coverage_percent"] == 66.7

    device_rows = {row["identifikace"]: row for row in updated["device_rows"]}
    assert device_rows["A"]["rozpoctena_fakturacni_spotreba"] == 45.0
    assert device_rows["B"]["rozpoctena_fakturacni_spotreba"] == 15.0
    assert device_rows["A"]["podil_na_fakturacnim_procent"] == 50.0
    assert device_rows["B"]["podil_na_fakturacnim_procent"] == 16.7

    assert updated["segment_rows"][0]["billing_consumption"] == 15.0
    assert updated["segment_rows"][0]["difference"] == 5.0
    assert updated["segment_rows"][0]["device_consumptions"][0]["billing_consumption"] == 9.0
    assert updated["segment_rows"][0]["device_consumptions"][1]["billing_consumption"] == 6.0
    assert updated["segment_rows"][1]["billing_consumption"] == 45.0
    assert updated["segment_rows"][1]["difference"] == 15.0
    assert updated["segment_rows"][1]["device_consumptions"][0]["billing_consumption"] == 36.0
    assert updated["segment_rows"][1]["device_consumptions"][1]["billing_consumption"] == 9.0


def test_apply_price_intervals_to_payload_allocates_payment_by_segment_and_device():
    payload = {
        "device_rows": [
            {"identifikace": "A", "spotreba": 30.0},
            {"identifikace": "B", "spotreba": 10.0},
        ],
        "assignment_rows": [],
        "segment_rows": [
            {
                "start_time": datetime.datetime(2026, 4, 1, 0, 0, 0),
                "end_time": datetime.datetime(2026, 4, 15, 23, 59, 59),
                "submeter_consumption": 10.0,
                "billing_consumption": 15.0,
                "device_consumptions": [
                    {"identifikace": "A", "spotreba": 6.0, "billing_consumption": 9.0},
                    {"identifikace": "B", "spotreba": 4.0, "billing_consumption": 6.0},
                ],
            },
            {
                "start_time": datetime.datetime(2026, 4, 16, 0, 0, 0),
                "end_time": datetime.datetime(2026, 4, 30, 23, 59, 59),
                "submeter_consumption": 30.0,
                "billing_consumption": 45.0,
                "device_consumptions": [
                    {"identifikace": "A", "spotreba": 24.0, "billing_consumption": 36.0},
                    {"identifikace": "B", "spotreba": 6.0, "billing_consumption": 9.0},
                ],
            },
        ],
    }

    updated = apply_price_intervals_to_payload(
        payload,
        [
            {
                "start_date": datetime.date(2026, 4, 1),
                "end_date": datetime.date(2026, 4, 15),
                "price_per_m3": 100.0,
            },
            {
                "start_date": datetime.date(2026, 4, 16),
                "end_date": datetime.date(2026, 4, 30),
                "price_per_m3": 120.0,
            },
        ],
    )

    device_rows = {row["identifikace"]: row for row in updated["device_rows"]}
    assert device_rows["A"]["priced_consumption"] == 45.0
    assert device_rows["A"]["payment_amount"] == 5220.0
    assert device_rows["B"]["priced_consumption"] == 15.0
    assert device_rows["B"]["payment_amount"] == 1680.0
    assert updated["priced_consumption_total"] == 60.0
    assert updated["payment_amount_total"] == 6900.0
