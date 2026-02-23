from src.db.models import MessageStatus

# Adjacency list for allowed transitions
_TRANSITIONS = {
    MessageStatus.QUEUED: {
        MessageStatus.SENT, 
        MessageStatus.RETRY_PENDING, 
        MessageStatus.FAILED, 
        MessageStatus.CANCELLED
    },
    MessageStatus.RETRY_PENDING: {
        MessageStatus.SENT, 
        MessageStatus.FAILED, 
        MessageStatus.CANCELLED
    },
    MessageStatus.SENT: {
        MessageStatus.DELIVERED, 
        MessageStatus.BOUNCED, 
        MessageStatus.FAILED
    },
    # Terminal states
    MessageStatus.DELIVERED: set(),
    MessageStatus.BOUNCED: set(),
    MessageStatus.FAILED: set(),
    MessageStatus.CANCELLED: set(),
}

def can_transition(current: MessageStatus, new: MessageStatus) -> bool:
    """
    Validates if a transition from current status to new status is allowed.
    """
    if current == new:
        return True
    return new in _TRANSITIONS.get(current, set())

class InvalidTransitionError(Exception):
    def __init__(self, current: MessageStatus, new: MessageStatus):
        self.message = f"Invalid transition from {current} to {new}"
        super().__init__(self.message)
