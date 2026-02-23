"""
Unit tests for lifecycle state machine transitions.
"""

import pytest
from src.domain.lifecycle import can_transition, InvalidTransitionError
from src.db.models import MessageStatus


class TestCanTransition:
    """Test all valid and invalid transitions."""

    # ── Valid transitions ──

    @pytest.mark.parametrize(
        "current,new",
        [
            (MessageStatus.QUEUED, MessageStatus.SENT),
            (MessageStatus.QUEUED, MessageStatus.RETRY_PENDING),
            (MessageStatus.QUEUED, MessageStatus.FAILED),
            (MessageStatus.QUEUED, MessageStatus.CANCELLED),
            (MessageStatus.RETRY_PENDING, MessageStatus.SENT),
            (MessageStatus.RETRY_PENDING, MessageStatus.FAILED),
            (MessageStatus.RETRY_PENDING, MessageStatus.CANCELLED),
            (MessageStatus.SENT, MessageStatus.DELIVERED),
            (MessageStatus.SENT, MessageStatus.BOUNCED),
            (MessageStatus.SENT, MessageStatus.FAILED),
        ],
    )
    def test_valid_transitions(self, current, new):
        assert can_transition(current, new) is True

    # ── Self-transitions (identity) ──

    @pytest.mark.parametrize("status", list(MessageStatus))
    def test_self_transition_always_allowed(self, status):
        assert can_transition(status, status) is True

    # ── Invalid transitions ──

    @pytest.mark.parametrize(
        "current,new",
        [
            # Terminal → anything else
            (MessageStatus.DELIVERED, MessageStatus.SENT),
            (MessageStatus.DELIVERED, MessageStatus.BOUNCED),
            (MessageStatus.BOUNCED, MessageStatus.DELIVERED),
            (MessageStatus.FAILED, MessageStatus.SENT),
            (MessageStatus.FAILED, MessageStatus.QUEUED),
            (MessageStatus.CANCELLED, MessageStatus.QUEUED),
            (MessageStatus.CANCELLED, MessageStatus.SENT),
            # Invalid forward transitions
            (MessageStatus.SENT, MessageStatus.QUEUED),
            (MessageStatus.SENT, MessageStatus.RETRY_PENDING),
            (MessageStatus.SENT, MessageStatus.CANCELLED),
            (MessageStatus.QUEUED, MessageStatus.DELIVERED),
            (MessageStatus.QUEUED, MessageStatus.BOUNCED),
            (MessageStatus.RETRY_PENDING, MessageStatus.DELIVERED),
            (MessageStatus.RETRY_PENDING, MessageStatus.BOUNCED),
        ],
    )
    def test_invalid_transitions(self, current, new):
        assert can_transition(current, new) is False

    # ── Terminal states have no outgoing transitions ──

    @pytest.mark.parametrize("terminal", [
        MessageStatus.DELIVERED,
        MessageStatus.BOUNCED,
        MessageStatus.FAILED,
        MessageStatus.CANCELLED,
    ])
    def test_terminal_states_no_outgoing(self, terminal):
        for target in MessageStatus:
            if target == terminal:
                continue  # skip self-transition
            assert can_transition(terminal, target) is False, (
                f"Terminal state {terminal} should not transition to {target}"
            )


class TestInvalidTransitionError:
    def test_error_message(self):
        err = InvalidTransitionError(MessageStatus.FAILED, MessageStatus.SENT)
        assert "FAILED" in str(err)
        assert "SENT" in str(err)
