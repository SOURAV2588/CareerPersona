"""Unit tests for services/rate_limit.py.

Every test injects a fake clock, so the suite stays deterministic and fast —
no sleeping, no wall-clock dependence, no flake at midnight IST.
"""

from datetime import datetime, timedelta

import pytest

from services.rate_limit import (
    BudgetExhausted,
    CallerThrottled,
    DailyBudget,
    MessageTooLong,
    SlidingWindowLimiter,
    caller_key,
)

pytestmark = pytest.mark.unit


class FakeClock:
    """Monotonic-style clock the test advances by hand."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    """A fresh FakeClock starting at t=1000.0."""
    return FakeClock()


class TestSlidingWindowLimiter:
    """SlidingWindowLimiter's window-based accept/reject behavior."""

    def test_allows_up_to_the_limit(self, clock):
        """Exactly max_events calls within the window are all allowed."""
        limiter = SlidingWindowLimiter(3, 60, "test", clock=clock)
        for _ in range(3):
            limiter.check_and_record("1.2.3.4")

    def test_blocks_the_turn_after_the_limit(self, clock):
        """The call after max_events within the window raises CallerThrottled."""
        limiter = SlidingWindowLimiter(3, 60, "test", clock=clock)
        for _ in range(3):
            limiter.check_and_record("1.2.3.4")
        with pytest.raises(CallerThrottled):
            limiter.check_and_record("1.2.3.4")

    def test_window_slides_so_the_caller_recovers(self, clock):
        """Once the window fully elapses, a previously blocked caller is allowed again."""
        limiter = SlidingWindowLimiter(2, 60, "test", clock=clock)
        limiter.check_and_record("1.2.3.4")
        limiter.check_and_record("1.2.3.4")
        clock.advance(61)
        limiter.check_and_record("1.2.3.4")  # must not raise

    def test_partial_window_expiry_frees_exactly_one_slot(self, clock):
        """Only events that have individually aged out of the window are dropped, not the whole window."""
        limiter = SlidingWindowLimiter(2, 60, "test", clock=clock)
        limiter.check_and_record("1.2.3.4")
        clock.advance(30)
        limiter.check_and_record("1.2.3.4")
        clock.advance(31)  # first hit expired, second has not
        limiter.check_and_record("1.2.3.4")
        with pytest.raises(CallerThrottled):
            limiter.check_and_record("1.2.3.4")

    def test_callers_are_tracked_independently(self, clock):
        """One caller's usage does not count against a different caller's limit."""
        limiter = SlidingWindowLimiter(1, 60, "test", clock=clock)
        limiter.check_and_record("1.2.3.4")
        limiter.check_and_record("5.6.7.8")  # must not raise
        with pytest.raises(CallerThrottled):
            limiter.check_and_record("1.2.3.4")

    def test_retry_after_reports_when_the_slot_frees(self, clock):
        """CallerThrottled.retry_after reports the time until the oldest hit expires."""
        limiter = SlidingWindowLimiter(1, 60, "test", clock=clock)
        limiter.check_and_record("1.2.3.4")
        clock.advance(20)
        with pytest.raises(CallerThrottled) as excinfo:
            limiter.check_and_record("1.2.3.4")
        assert excinfo.value.retry_after == pytest.approx(40.0)

    def test_blocked_attempts_do_not_extend_the_block(self, clock):
        """A rejected request must not be recorded, or a hammering client
        would lock itself out indefinitely."""
        limiter = SlidingWindowLimiter(1, 60, "test", clock=clock)
        limiter.check_and_record("1.2.3.4")
        for _ in range(5):
            with pytest.raises(CallerThrottled):
                limiter.check_and_record("1.2.3.4")
        clock.advance(61)
        limiter.check_and_record("1.2.3.4")  # must not raise

    def test_caller_table_is_bounded(self, clock):
        """The tracked-caller table never exceeds max_keys, evicting least-recently-seen entries."""
        limiter = SlidingWindowLimiter(5, 60, "test", max_keys=10, clock=clock)
        for i in range(100):
            limiter.check_and_record(f"10.0.0.{i}")
        assert len(limiter._hits) <= 10


class FakeDayClock:
    """Datetime-style clock the test advances by whole days, for DailyBudget rollover tests."""

    def __init__(self) -> None:
        self.now = datetime(2026, 8, 18, 9, 0)

    def __call__(self) -> datetime:
        return self.now

    def advance_days(self, days: int) -> None:
        """Move the clock forward by the given number of days."""
        self.now += timedelta(days=days)


class TestDailyBudget:
    """DailyBudget's cap enforcement and midnight rollover."""

    def test_ensure_available_passes_under_the_cap(self):
        """ensure_available() does not raise while usage stays under the cap."""
        budget = DailyBudget(10, "test", clock=FakeDayClock())
        budget.record(9)
        budget.ensure_available()

    def test_ensure_available_raises_at_the_cap(self):
        """ensure_available() raises BudgetExhausted once usage reaches the cap."""
        budget = DailyBudget(10, "test", clock=FakeDayClock())
        budget.record(10)
        with pytest.raises(BudgetExhausted):
            budget.ensure_available()

    def test_ensure_available_does_not_consume(self):
        """Calling ensure_available() repeatedly never increments used itself."""
        budget = DailyBudget(10, "test", clock=FakeDayClock())
        for _ in range(5):
            budget.ensure_available()
        assert budget.used == 0

    def test_budget_resets_on_the_next_day(self):
        """Usage rolls back to zero once the clock crosses into the next local day."""
        day_clock = FakeDayClock()
        budget = DailyBudget(10, "test", clock=day_clock)
        budget.record(10)
        with pytest.raises(BudgetExhausted):
            budget.ensure_available()
        day_clock.advance_days(1)
        budget.ensure_available()
        assert budget.used == 0


class FakeClient:
    """Stand-in for the ``client`` attribute of a gradio.Request."""

    def __init__(self, host):
        self.host = host


class FakeRequest:
    """Stand-in for gradio.Request, exposing just what caller_key() reads."""

    def __init__(self, host=None, headers=None, session_hash=None):
        self.client = FakeClient(host) if host else None
        self.headers = headers or {}
        self.session_hash = session_hash


class TestCallerKey:
    """caller_key()'s derivation of a caller identity from a request."""

    def test_uses_the_client_host(self):
        """The connecting client's host is used as the caller key when present."""
        assert caller_key(FakeRequest(host="1.2.3.4")) == "1.2.3.4"

    def test_falls_back_to_session_hash(self):
        """Without a client host, the Gradio session hash is used as the caller key."""
        assert caller_key(FakeRequest(session_hash="abc123")) == "abc123"

    def test_handles_a_missing_request(self):
        """caller_key(None) returns "unknown" rather than raising."""
        assert caller_key(None) == "unknown"

    def test_ignores_forwarded_header_when_proxy_is_untrusted(self, monkeypatch):
        """Default posture: a client-supplied X-Forwarded-For must not be able
        to mint a fresh quota."""
        monkeypatch.setattr("services.rate_limit.TRUST_PROXY_HEADER", False)
        request = FakeRequest(host="1.2.3.4", headers={"x-forwarded-for": "9.9.9.9"})
        assert caller_key(request) == "1.2.3.4"

    def test_uses_forwarded_header_when_proxy_is_trusted(self, monkeypatch):
        monkeypatch.setattr("services.rate_limit.TRUST_PROXY_HEADER", True)
        request = FakeRequest(
            host="10.0.0.1", headers={"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
        )
        assert caller_key(request) == "9.9.9.9"


class TestCheckChatTurn:
    """check_chat_turn()'s ordering and enforcement of the input-size and budget guards."""

    def test_rejects_an_oversized_message(self, monkeypatch):
        """A message longer than MESSAGE_MAX_CHARS raises MessageTooLong."""
        from services import rate_limit

        rate_limit.reset_all()
        monkeypatch.setattr(rate_limit, "MESSAGE_MAX_CHARS", 50)
        with pytest.raises(MessageTooLong):
            rate_limit.check_chat_turn("1.2.3.4", "x" * 51)

    def test_oversized_message_is_rejected_before_consuming_budget(self, monkeypatch):
        """A message rejected for length never consumes the daily turn budget."""
        from services import rate_limit

        rate_limit.reset_all()
        monkeypatch.setattr(rate_limit, "MESSAGE_MAX_CHARS", 50)
        with pytest.raises(MessageTooLong):
            rate_limit.check_chat_turn("1.2.3.4", "x" * 51)
        assert rate_limit.DAILY_TURNS.used == 0


class FakeUsage:
    """Stand-in for anthropic.types.Usage, built from arbitrary keyword fields."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestRecordUsage:
    """record_usage()'s token accounting against the daily token budget."""

    def test_counts_cached_tokens_too(self):
        """Cache-read and cache-creation tokens are added to the daily total alongside input/output."""
        from services import rate_limit

        rate_limit.reset_all()
        rate_limit.record_usage(
            FakeUsage(
                input_tokens=20,
                output_tokens=300,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=8_000,
            )
        )
        assert rate_limit.DAILY_TOKENS.used == 8_320

    def test_tolerates_missing_fields(self):
        """Usage objects missing the cache-related fields are still totaled correctly."""
        from services import rate_limit

        rate_limit.reset_all()
        rate_limit.record_usage(FakeUsage(input_tokens=10, output_tokens=5))
        assert rate_limit.DAILY_TOKENS.used == 15

    def test_tolerates_no_usage(self):
        """record_usage(None) is a no-op rather than raising."""
        from services import rate_limit

        rate_limit.reset_all()
        rate_limit.record_usage(None)
        assert rate_limit.DAILY_TOKENS.used == 0