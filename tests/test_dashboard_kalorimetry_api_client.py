from moduly.apps.dashboard import api_client


class _Response:
    def json(self):
        return {
            "total": 1,
            "rows": [
                {
                    "id": 42,
                    "identifikace": "KAL-01",
                    "review_status": "PENDING",
                }
            ],
        }


def test_list_kalorimetry_outlier_reviews_returns_rows_not_response_envelope(monkeypatch):
    captured: dict[str, object] = {}

    def fake_request(method, path, **kwargs):
        captured.update(method=method, path=path, **kwargs)
        return _Response()

    monkeypatch.setattr(api_client, "_request", fake_request)

    rows = api_client.list_kalorimetry_outlier_reviews(
        "token",
        review_status=None,
        identifikace="KAL-01",
        source_filter="VSE",
        limit=25,
    )

    assert rows == [
        {
            "id": 42,
            "identifikace": "KAL-01",
            "review_status": "PENDING",
        }
    ]
    assert captured == {
        "method": "GET",
        "path": "/api/v1/kalorimetry/outlier-reviews",
        "access_token": "token",
        "query_params": {
            "source": "VSE",
            "limit": 25,
            "identifikace": "KAL-01",
        },
    }
