class SimulationError(Exception):
    """Base class: the simulation could not complete correctly."""


class DeadlineMiss(SimulationError):
    def __init__(self, job, t):
        self.job, self.t = job, t
        super().__init__(f"{job.name} misses its deadline {job.deadline} (detected at t={t})")


class InvalidDecision(SimulationError):
    pass


class BudgetInfeasible(SimulationError):
    pass
