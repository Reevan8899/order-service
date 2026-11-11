"""HTTP-клиент user-service с повторами и circuit breaker."""

import time
from threading import Lock

import requests


class UserNotFound(Exception):
    """Пользователь отсутствует в user-service."""


class UserServiceUnavailable(Exception):
    def __init__(self, message: str, code: str = "user_service_unavailable"):
        super().__init__(message)
        self.code = code


class CircuitBreaker:
    def __init__(self, threshold: int = 5, cooldown: float = 30, clock=time.monotonic):
        self.threshold = threshold
        self.cooldown = cooldown
        self.clock = clock
        self._lock = Lock()
        self._failures = 0
        self._open_until = None
        self._probe = False
        self._generation = 0

    @property
    def state(self) -> str:
        with self._lock:
            if self._open_until is None:
                return "closed"
            return "open" if self.clock() < self._open_until else "half-open"

    def acquire(self) -> tuple[int, bool]:
        with self._lock:
            if self._open_until is not None:
                if self.clock() < self._open_until or self._probe:
                    raise UserServiceUnavailable("Circuit breaker открыт. Повторите запрос позже.", "circuit_open")
                self._probe = True
            return self._generation, self._probe

    def succeeded(self, generation: int) -> None:
        with self._lock:
            if generation == self._generation:
                self._failures = 0
                self._open_until = None
                self._probe = False

    def failed(self, generation: int) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._failures += 1
            if self._probe or self._failures >= self.threshold:
                self._open_until = self.clock() + self.cooldown
                self._probe = False
                self._generation += 1


class UserClient:
    def __init__(self, base_url: str, *, breaker=None, sleep=time.sleep):
        self.base_url = base_url.rstrip("/")
        self.breaker = breaker if breaker is not None else CircuitBreaker()
        self.sleep = sleep

    def get_user(self, user_id: int) -> dict:
        generation, probe = self.breaker.acquire()
        attempts = 1 if probe else 3
        for attempt in range(attempts):
            try:
                response = requests.get(f"{self.base_url}/users/{user_id}", timeout=2, allow_redirects=False)
                if response.status_code == 404:
                    self.breaker.succeeded(generation)
                    raise UserNotFound
                if response.status_code == 200:
                    user = response.json()
                    if isinstance(user, dict) and type(user.get("id")) is int and user["id"] == user_id:
                        self.breaker.succeeded(generation)
                        return user
                elif response.status_code < 500 and response.status_code != 429:
                    break
            except (requests.RequestException, ValueError):
                pass
            if attempt + 1 < attempts:
                self.sleep(0.5 * (2 ** attempt))
        self.breaker.failed(generation)
        raise UserServiceUnavailable("user-service временно недоступен.")

    def health(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/health", timeout=0.5, allow_redirects=False)
            return response.status_code == 200
        except requests.RequestException:
            return False
