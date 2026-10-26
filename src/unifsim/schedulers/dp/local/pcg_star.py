"""PCG* local scheduler for one TL-plane on a uniform platform.

Port of pcg_star() from the PCG reference implementation by Antoine Bertout
and Pascal Richard (src/pcg/scheduler.py), logic unchanged; removed: logging,
plotting and the internal call to the schedule checker (unifsim validates the
whole trace independently). Authors' agreement required before distribution.

Input: budgets (exec_times) > 0, speeds non-increasing, window length.
Output: one list per processor of (job index, (start, end)), merged.
"""

from __future__ import annotations

from fractions import Fraction

from .plane import EventType, Job, Proc, assign, compute_next_event, flatten, unassign


def pcg_star(exec_times, speeds, window_size):
    speeds = sorted(speeds, reverse=True)
    window_size = Fraction(window_size)
    jobs = sorted((Job(i, Fraction(l)) for i, l in enumerate(exec_times)),
                  key=lambda j: j.remaining_time, reverse=True)
    processors = [Proc(Fraction(s), window_size, i) for i, s in enumerate(speeds)]
    schedule = [[] for _ in processors]

    active_jobs = jobs.copy()
    active_processors = processors.copy()

    # trivial C-events at t = 0
    trivial_jobs, trivial_procs = [], []
    for job in active_jobs:
        for proc in active_processors:
            if job not in trivial_jobs and proc not in trivial_procs \
                    and job.remaining_time == proc.rem_capacity:
                schedule[proc.idx].append((job.idx, (Fraction(0), window_size)))
                trivial_jobs.append(job)
                trivial_procs.append(proc)
                break
    active_jobs = [j for j in active_jobs if j not in trivial_jobs]
    active_processors = [p for p in active_processors if p not in trivial_procs]

    current_time = Fraction(0)
    for job, proc in zip(active_jobs, active_processors):
        assign(job, proc)

    while active_jobs:
        total_capacity = sum(p.rem_capacity for p in active_processors)
        total_load = sum(j.remaining_time for j in active_jobs)
        assert total_load <= total_capacity

        next_event = min(compute_next_event(j, active_processors) for j in active_jobs)
        next_decision_time = current_time + next_event.delta
        assert next_decision_time != 0

        if next_decision_time != current_time:
            for proc in active_processors:
                job = proc.current_job
                if job:
                    schedule[proc.idx].append((job.idx, (current_time, next_decision_time)))
                    job.remaining_time -= next_event.delta * proc.speed
                    if job.remaining_time == 0:
                        unassign(job)
                proc.rem_capacity -= next_event.delta * proc.speed

        evicted_job = None
        if next_event.type == EventType.C:
            c_job, c_proc = next_event.job, next_event.proc
            if c_proc.current_job:
                evicted_job = c_proc.current_job
                unassign(evicted_job)
            if c_job.assigned_proc:
                unassign(c_job)
            assign(c_job, c_proc)
            if c_job.remaining_time != 0:  # simultaneous C-B-event
                schedule[c_proc.idx].append((c_job.idx, (next_decision_time, window_size)))
            c_proc.rem_capacity = 0
            c_job.remaining_time = 0

        current_time = next_decision_time

        active_jobs = [j for j in active_jobs if j.remaining_time != 0]
        active_processors = [p for p in active_processors if p.rem_capacity != 0]
        ready_jobs = [j for j in active_jobs if j != evicted_job and not j.assigned_proc]
        if evicted_job is not None:  # an evicted job is served first
            ready_jobs = [evicted_job] + ready_jobs

        if ready_jobs:
            idx = 0
            for p in active_processors:
                if idx < len(ready_jobs) and not p.current_job:
                    assign(ready_jobs[idx], p)
                    idx += 1

        proc_jobs = [p.current_job.idx for p in active_processors if p.current_job]
        assert len(proc_jobs) == len(set(proc_jobs)), f"duplicate jobs on processors: {proc_jobs}"
        job_procs = [j.assigned_proc.idx for j in active_jobs if j.assigned_proc]
        assert len(job_procs) == len(set(job_procs)), f"job on two processors: {job_procs}"

    return flatten(schedule)
