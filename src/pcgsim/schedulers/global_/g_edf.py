"""Global EDF on a uniform platform: the m earliest-deadline active jobs run,
earliest deadline on the fastest processor. Ties: task id, then job index.

Not optimal for m > 1; optimal for m = 1 (used to test the engine)."""

from ..base import Decision, Scheduler


class GEDF(Scheduler):
    name = "g_edf"

    def decide(self, t, view):
        order = sorted(view.active, key=lambda j: (j.deadline, j.task_id, j.k))
        return Decision(assignment={p: j for p, j in enumerate(order[: view.platform.m])})
