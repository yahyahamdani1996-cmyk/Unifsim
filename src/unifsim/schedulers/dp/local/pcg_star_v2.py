"""PCG* on one TL-plane, all the events of an instant handled together
(ECRTS 2026, Algorithms 1 and 2)."""

from fractions import Fraction

from .plane import Event, EventType, LocalJob, Proc, assign, compute_next_event, flatten, unassign


def initial_c_events(jobs, processors):
    """C-events at t = 0: a budget exactly equal to a processor capacity.
    One event per job, one job per processor."""
    initial_events = []
    used_procs = []
    for job in jobs:
        for proc in processors:
            if job.remaining_time == proc.rem_capacity and proc not in used_procs:
                initial_events.append(Event(EventType.C, job, Fraction(0), proc))
                used_procs.append(proc)
                break
    return initial_events


def handle_events(E, jobs, processors, schedule, t, window_size):
    """Algorithm 2: C-events, then free jobs on free processors, then B-events."""
    free_jobs = []
    free_procs = []
    c_events = []
    seen = []

    #Construct the list of C-events, one per processor
    for e in E:
        if e.type == EventType.C and e.proc not in seen:
            c_events.append(e)
            seen.append(e.proc)

    #Construct the list of C events jobs To avoid putting them in free_jobs
    c_jobs = [e.job for e in c_events]

    #Same for B evnets
    b_events = [e for e in E if e.type == EventType.B]
    b_jobs = [e.job for e in b_events]


    # C-events
    for event in c_events:
  
        j_job = event.job
        piK = event.proc
        l_job =piK.current_job

        if piK in free_procs:
            free_procs.remove(piK)

        #Since this function also handles initial C-events, a job may trigger a C-event on its own processor 
        if j_job.assigned_proc is not None and j_job.assigned_proc is not piK:
            free_procs.append(j_job.assigned_proc)
            unassign(j_job)

        if l_job is not None and l_job is not j_job:
            unassign(l_job)
            if l_job not in c_jobs and l_job not in b_jobs:
                free_jobs.append(l_job)

        assign(j_job, piK)
        if j_job.remaining_time != 0:   # simultaneous C-B-event at the end of the plane: no empty piece
            schedule[piK.idx].append((j_job.idx, (t, window_size)))
        jobs.remove(j_job)
        processors.remove(piK)

    while free_jobs and free_procs:
        assign(free_jobs.pop(0), free_procs.pop(0))

    #Jobs that aare not executing and weren't evicted 
    ready_jobs = [j for j in jobs if j.assigned_proc is None and j not in b_jobs]
    while free_procs and ready_jobs:
        assign(ready_jobs.pop(0), free_procs.pop(0))


    for event in b_events:
        job = event.job
        jobs.remove(job)                 # finished: leaves the list in every case
        if job.assigned_proc is None:    # evicted by a simultaneous C-event
            continue
        proc = event.proc
        unassign(job)
        if ready_jobs:
            assign(ready_jobs.pop(0), proc)








          









        

def advance(processors, schedule, t, delta):
    """Algorithm 1, line 6: record the pieces on [t, t + delta), update budgets and capacities."""
    for proc in  processors:
        job = proc.current_job
        work = delta * proc.speed
        if job is not None and delta > 0:
            schedule[proc.idx].append((job.idx, (t, t + delta)))
            job.remaining_time -= work
   
        proc.rem_capacity -= work




def pcg_star_v2(exec_times, speeds, window_size):
    """Algorithm 1. exec_times[i] = budget of local job i (> 0), speeds fastest first,
    plane [0, window_size). Returns one list per processor of (i, (start, end))."""
    jobs = []
    processors = []
    schedule = [[] for _ in speeds]
    t = Fraction(0)

    for i, exec_time in enumerate(exec_times):
        jobs.append(LocalJob(i, Fraction(exec_time)))
    for i, speed in enumerate(speeds):
        processors.append(Proc(speed, window_size, i))
    jobs.sort(key=lambda j: j.remaining_time, reverse=True)

    # LRPT-FM, once, at the start of the plane
    for k in range(min(len(jobs), len(processors))):
        assign(jobs[k], processors[k])

    # initial C-events, handled like any other events
    handle_events(initial_c_events(jobs, processors), jobs, processors, schedule, t, window_size)



    while jobs:
        events = []
        for job in jobs:
            ev = compute_next_event(job, processors)
            if ev is not None:
                events.append(ev)

        delta = min(e.delta for e in events)
        next_events = [e for e in events if e.delta == delta]
        advance(processors, schedule, t, delta)
        t += delta
        handle_events(next_events, jobs, processors, schedule, t, window_size)


    return flatten(schedule)
