"""Shared service-layer exceptions (WO v4.15, ADR 0008).

Reuses v4.14's ServiceError / NotFoundError base (defined in production_jobs) and
adds InvalidStateError for the Materials/Buying/Stores 422 cases (raise twice,
resolve twice, defer-after-raise, raise-discrepancy on a non-discrepancy count).
Routers translate these to HTTPException.
"""
from app.services.production_jobs import NotFoundError, ServiceError


class InvalidStateError(ServiceError):
    """An action is invalid for the entity's current state (-> 422)."""


class ChassisEtaError(ServiceError):
    """Scheduling blocked by the chassis-ETA gate (-> 422)."""


class CellOccupiedError(ServiceError):
    """Target planning cell is already occupied (-> 409)."""


class RevertNotAllowedError(ServiceError):
    """Scheduled → unscheduled revert blocked by a state safety rule (-> 409). WO v4.34.2 §0.3."""


class RejectNotAllowedError(ServiceError):
    """A job has progressed too far to be rejected, or no reason was given (-> 409).

    v1.49 — sibling of RevertNotAllowedError. Revert takes a job off the grid but
    keeps it as work ICB intends to do; reject says the work is not happening and
    marks its costing declined.
    """


__all__ = ["ServiceError", "NotFoundError", "InvalidStateError",
           "ChassisEtaError", "CellOccupiedError", "RevertNotAllowedError"]
