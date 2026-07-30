from moduly.apps.dashboard import api_client


class _Response:
    def json(self):
        return {
            "identifikace": "A_V1",
            "prediction_available": True,
            "availability_status": "available",
            "availability_reason": None,
            "total": 2,
            "rows": [
                {
                    "valid_from": "2026-07-20T04:10:05",
                    "valid_to": "2026-07-27T04:10:05",
                },
                {
                    "valid_from": "2026-07-27T00:00:00",
                    "valid_to": "2026-08-03T00:00:00",
                },
            ],
        }


def test_get_vodomery_prediction_profiles_preserves_response_envelope(monkeypatch):
    monkeypatch.setattr(
        api_client,
        "_request",
        lambda *args, **kwargs: _Response(),
    )

    payload = api_client.get_vodomery_prediction_profiles(
        "token",
        identifikace="A_V1",
        start_date="2026-07-27",
        end_date="2026-08-02",
    )

    assert payload["prediction_available"] is True
    assert payload["availability_status"] == "available"
    assert payload["total"] == 2
    assert [row["valid_to"] for row in payload["rows"]] == [
        "2026-07-27T04:10:05",
        "2026-08-03T00:00:00",
    ]
