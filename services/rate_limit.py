"""Inbound rate limiting and spend caps for the public chat endpoint.

The Anthropic SDK already retries upstream 429s (``max_retries=4``), and
``chat()`` degrades those to ``FALLBACK_BUSY``. This module is the other
direction: limiting what an anonymous visitor can spend on *your* behalf.

Four guards, checked cheapest-first so a blocked turn costs nothing:

  1. ``MESSAGE_MAX_CHARS``  — reject oversized input before any API call.
  2. Daily token budget    — hard ceiling on spend per day.
  3. Daily turn cap        — circuit breaker independent of token accounting.
  4. Per-caller windows    — a burst window and a sustained window.

Plus a per-caller cap on outbound contact emails, since ``record_user_details``
is otherwise an open relay to your inbox.

State is in-process and deliberately not persisted: losing it on restart is
correct behaviour for a limiter (unlike the pending-questions store). It does
mean the limits are *per worker* — run a single process, or move the counters
to Redis, before scaling out.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict, deque
from contextvars import ContextVar, Token
from datetime import datetime
from typing import Callable

import pytz

logger = logging.getLogger(__name__)

TIMEZONE = pytz.timezone("Asia/Kolkata")  # matches the digest scheduler


# ── configuration ───────────────────────────────────────────────────────────

def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; falling back to %d", name, raw, default)
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


MESSAGE_MAX_CHARS = _int_env("CHAT_MESSAGE_MAX_CHARS", 2_000)

BURST_MAX_TURNS = _int_env("CHAT_BURST_MAX_TURNS", 5)
BURST_WINDOW_SECONDS = _int_env("CHAT_BURST_WINDOW_SECONDS", 60)

SUSTAINED_MAX_TURNS = _int_env("CHAT_SUSTAINED_MAX_TURNS", 40)
SUSTAINED_WINDOW_SECONDS = _int_env("CHAT_SUSTAINED_WINDOW_SECONDS", 3_600)

GLOBAL_DAILY_TURNS = _int_env("CHAT_GLOBAL_DAILY_TURNS", 750)
GLOBAL_DAILY_TOKENS = _int_env("CHAT_GLOBAL_DAILY_TOKENS", 5_000_000)

EMAIL_MAX_PER_CALLER = _int_env("CHAT_EMAIL_MAX_PER_CALLER", 2)
EMAIL_WINDOW_SECONDS = _int_env("CHAT_EMAIL_WINDOW_SECONDS", 3_600)

MAX_TRACKED_CALLERS = _int_env("CHAT_MAX_TRACKED_CALLERS", 10_000)

# Only trust X-Forwarded-For when you KNOW a proxy you control sets it.
# Exposed directly to the internet, a client can forge the header and mint
# itself a fresh quota on every request.
TRUST_PROXY_HEADER = _bool_env("CHAT_TRUST_PROXY_HEADER", False)


# ── exceptions ──────────────────────────────────────────────────────────────

class RateLimited(Exception):
    """Base: this turn should not be served."""

    def __init__(self, reason: str, retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after


class MessageTooLong(RateLimited):
    """Input exceeded MESSAGE_MAX_CHARS."""


class CallerThrottled(RateLimited):
    """This visitor is sending turns too fast."""


class BudgetExhausted(RateLimited):
    """A global daily cap has been hit; nobody is served until rollover."""


# ── primitives ──────────────────────────────────────────────────────────────

class SlidingWindowLimiter:
    """Thread-safe sliding-window counter, keyed by caller.

    ``clock`` is injectable so tests can advance time without sleeping.
    Caller state is bounded by ``max_keys`` and evicted least-recently-seen
    first; an attacker rotating source addresses can therefore flush honest
    callers out of the table, which is what the global daily caps are for.
    """

    def __init__(
        self,
        max_events: int,
        window_seconds: float,
        name: str,
        max_keys: int = MAX_TRACKED_CALLERS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_events = max_events
        self._window = float(window_seconds)
        self._name = name
        self._max_keys = max_keys
        self._clock = clock
        self._hits: "OrderedDict[str, deque[float]]" = OrderedDict()
        self._lock = threading.Lock()

    def check_and_record(self, key: str) -> None:
        now = self._clock()
        cutoff = now - self._window
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
            self._hits.move_to_end(key)

            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self._max_events:
                retry_after = max(0.0, hits[0] + self._window - now)
                raise CallerThrottled(
                    f"{self._name}: {key} used {len(hits)}/{self._max_events} "
                    f"in {self._window:.0f}s",
                    retry_after=retry_after,
                )

            hits.append(now)
            while len(self._hits) > self._max_keys:
                self._hits.popitem(last=False)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class DailyBudget:
    """Thread-safe counter that resets at local midnight in ``TIMEZONE``."""

    def __init__(
        self,
        max_units: int,
        name: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._max = max_units
        self._name = name
        self._clock = clock or (lambda: datetime.now(TIMEZONE))
        self._day = None
        self._used = 0
        self._lock = threading.Lock()

    def _roll_locked(self) -> None:
        today = self._clock().date()
        if today != self._day:
            if self._day is not None:
                logger.info("%s: rolling over, used %d/%d", self._name, self._used, self._max)
            self._day = today
            self._used = 0

    def ensure_available(self, units: int = 1) -> None:
        """Raise if the budget is already spent. Does not consume anything."""
        with self._lock:
            self._roll_locked()
            if self._used + units > self._max:
                raise BudgetExhausted(f"{self._name}: {self._used}/{self._max} used today")

    def record(self, units: int = 1) -> None:
        """Consume budget. Deliberately allows overshoot on the final turn —
        token cost is only known after the call returns."""
        if units <= 0:
            return
        with self._lock:
            self._roll_locked()
            self._used += units

    @property
    def used(self) -> int:
        with self._lock:
            self._roll_locked()
            return self._used

    def reset(self) -> None:
        with self._lock:
            self._day = None
            self._used = 0


# ── module-level instances ──────────────────────────────────────────────────

BURST = SlidingWindowLimiter(BURST_MAX_TURNS, BURST_WINDOW_SECONDS, "burst")
SUSTAINED = SlidingWindowLimiter(SUSTAINED_MAX_TURNS, SUSTAINED_WINDOW_SECONDS, "sustained")
CONTACT_EMAILS = SlidingWindowLimiter(EMAIL_MAX_PER_CALLER, EMAIL_WINDOW_SECONDS, "contact-email")
DAILY_TURNS = DailyBudget(GLOBAL_DAILY_TURNS, "daily-turns")
DAILY_TOKENS = DailyBudget(GLOBAL_DAILY_TOKENS, "daily-tokens")


# ── caller identity ─────────────────────────────────────────────────────────

_current_caller: ContextVar[str] = ContextVar("current_caller", default="unknown")


def caller_key(request) -> str:
    """Derive a stable-ish identity from a ``gradio.Request``.

    IP is the best available signal for an unauthenticated endpoint. It is
    imperfect — shared NAT lumps colleagues together, and a rotating client
    escapes it — so it is a speed bump, backed by the global daily caps.
    """
    if request is None:
        return "unknown"

    if TRUST_PROXY_HEADER:
        headers = getattr(request, "headers", None)
        forwarded = ""
        if headers is not None:
            try:
                forwarded = headers.get("x-forwarded-for") or ""
            except Exception:  # pragma: no cover - defensive
                forwarded = ""
        first = forwarded.split(",")[0].strip()
        if first:
            return first

    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    if host:
        return host

    return getattr(request, "session_hash", None) or "unknown"


def set_current_caller(key: str) -> Token:
    return _current_caller.set(key)


def reset_current_caller(token: Token) -> None:
    _current_caller.reset(token)


def get_current_caller() -> str:
    return _current_caller.get()


# ── the two entry points ────────────────────────────────────────────────────

def check_chat_turn(caller: str, message: str) -> None:
    """Raise a ``RateLimited`` subclass if this turn must not reach the API.

    Ordered so that the free checks run first and a rejected caller never
    consumes global budget.
    """
    if message is not None and len(message) > MESSAGE_MAX_CHARS:
        raise MessageTooLong(f"message is {len(message)} chars (max {MESSAGE_MAX_CHARS})")

    DAILY_TOKENS.ensure_available()
    DAILY_TURNS.ensure_available()
    BURST.check_and_record(caller)
    SUSTAINED.check_and_record(caller)
    DAILY_TURNS.record(1)


def check_contact_email(caller: str) -> None:
    """Raise if this caller has already triggered enough notification emails."""
    CONTACT_EMAILS.check_and_record(caller)


def record_usage(usage) -> None:
    """Charge a response's tokens against the daily budget.

    The Anthropic API reports ``input_tokens`` *excluding* cached tokens, so
    the true total is ``input + cache_read + cache_creation + output``. Note
    that these are raw counts, not cost-weighted: cache reads bill at 0.1x
    input and cache writes at 1.25x, and output is priced higher than input.
    If you want a dollar cap rather than a token cap, weight them here.
    """
    if usage is None:
        return
    total = sum(
        getattr(usage, field, 0) or 0
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        )
    )
    DAILY_TOKENS.record(total)


def reset_all() -> None:
    """Test helper — clears every counter."""
    for limiter in (BURST, SUSTAINED, CONTACT_EMAILS, DAILY_TURNS, DAILY_TOKENS):
        limiter.reset()