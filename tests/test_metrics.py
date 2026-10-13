from fastapi.testclient import TestClient

from src.api.main import create_app

REQUIRED_METRICS = (
    "http_requests_total",
    "http_request_duration_seconds_bucket",
    "http_response_size_bytes_bucket",
    "idempotent_replays_total",
)


def test_metrics_endpoint_exposes_required_metrics():
    client = TestClient(create_app())
    client.get("/openapi.json")
    body = client.get("/metrics").text
    for name in REQUIRED_METRICS:
        assert name in body, f"немає метрики {name}"


def test_duration_histogram_has_150ms_bucket():
    client = TestClient(create_app())
    client.get("/openapi.json")
    assert 'le="0.15"' in client.get("/metrics").text


def test_metrics_endpoint_is_hidden_from_openapi():
    client = TestClient(create_app())
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]
