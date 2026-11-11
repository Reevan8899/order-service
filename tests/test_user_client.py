import pytest
import requests
import responses

from app.user_client import CircuitBreaker, UserClient, UserNotFound, UserServiceUnavailable

URL = "http://users.example.test"


@responses.activate
def test_timeout_and_server_error_use_backoff_then_recover(monkeypatch):
    requested_timeouts = []
    real_get = requests.get

    def track_timeout(*args, **kwargs):
        requested_timeouts.append(kwargs["timeout"])
        return real_get(*args, **kwargs)

    monkeypatch.setattr(requests, "get", track_timeout)
    pauses = []
    client = UserClient(URL, sleep=pauses.append)
    responses.get(f"{URL}/users/1", body=requests.Timeout())
    responses.get(f"{URL}/users/1", status=500)
    responses.get(f"{URL}/users/1", json={"id": 1})
    assert client.get_user(1) == {"id": 1}
    assert requested_timeouts == [2, 2, 2] and pauses == [0.5, 1.0]


@responses.activate
def test_404_is_not_retried():
    responses.get(f"{URL}/users/1", status=404)
    client = UserClient(URL)
    with pytest.raises(UserNotFound):
        client.get_user(1)
    assert len(responses.calls) == 1 and client.breaker.state == "closed"


@responses.activate
def test_malformed_success_does_not_authorize_user():
    responses.get(f"{URL}/users/1", body="invalid JSON")
    responses.get(f"{URL}/users/1", json={"id": True})
    responses.get(f"{URL}/users/1", json={"id": 2})
    with pytest.raises(UserServiceUnavailable):
        UserClient(URL, sleep=lambda seconds: None).get_user(1)
    assert len(responses.calls) == 3


@responses.activate
def test_nonretryable_response_fails_immediately():
    responses.get(f"{URL}/users/1", status=403)
    with pytest.raises(UserServiceUnavailable):
        UserClient(URL).get_user(1)
    assert len(responses.calls) == 1


@responses.activate
def test_breaker_opens_after_five_failed_calls_and_recovers():
    timestamp = [0.0]
    breaker = CircuitBreaker(clock=lambda: timestamp[0])
    client = UserClient(URL, breaker=breaker, sleep=lambda seconds: None)
    responses.get(f"{URL}/users/1", status=503)
    for _ in range(5):
        with pytest.raises(UserServiceUnavailable, match="временно недоступен"):
            client.get_user(1)
    assert len(responses.calls) == 15 and breaker.state == "open"
    with pytest.raises(UserServiceUnavailable) as blocked:
        client.get_user(1)
    assert blocked.value.code == "circuit_open" and len(responses.calls) == 15
    timestamp[0] = 30.0
    assert breaker.state == "half-open"
    responses.replace(responses.GET, f"{URL}/users/1", json={"id": 1})
    assert client.get_user(1) == {"id": 1}
    assert breaker.state == "closed"


def test_single_probe_and_stale_success():
    timestamp = [0.0]
    breaker = CircuitBreaker(threshold=1, cooldown=1, clock=lambda: timestamp[0])
    old, _ = breaker.acquire()
    breaker.failed(old)
    breaker.succeeded(old)
    assert breaker.state == "open"
    timestamp[0] = 1.0
    generation, probe = breaker.acquire()
    assert probe
    with pytest.raises(UserServiceUnavailable):
        breaker.acquire()
    breaker.failed(generation)
    assert breaker.state == "open"


@responses.activate
def test_health_handles_network_failure():
    responses.get(f"{URL}/health", body=requests.ConnectionError())
    assert not UserClient(URL).health()
