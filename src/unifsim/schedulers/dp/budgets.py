"""Budget (allocation) policies for deadline-partitioned (DP) schedulers.

Signature: policy(jobs, plane, scheduler, view) -> list[Fraction], one budget
per job, in the order of `jobs`. `plane` = (t0, t1).
"""

from __future__ import annotations

from fractions import Fraction


def dp_fair(jobs, plane, scheduler, view):
    """DP-fair allocation (Levin et al., RTSS 2010): b_i = u_i * (t1 - t0)."""
    t0, t1 = plane
    length = t1 - t0
    return [scheduler.taskset.task(j.task_id).u * length for j in jobs]


def bounds(job, plane, scheduler, view):
    """(b_inf, b_sup) of a job in a plane, as in both existing simulators:
    b_inf = max(0, rem - u (d - t1)),  b_sup = min(rem, s_1 (t1 - t0))."""
    t0, t1 = plane
    u = scheduler.taskset.task(job.task_id).u
    rem = view.remaining(job)
    b_inf = max(Fraction(0), rem - u * (job.deadline - t1))
    b_sup = min(rem, scheduler.platform.speeds[0] * (t1 - t0))
    return b_inf, b_sup


def greedy_wk(order: str = "remaining", epsilon=Fraction(0)):
    """Work-conserving allocation (WC-PCG*), port of shrimp greedy_wk / greedy_wk_idx.

    Start from b_inf, then repeatedly give the first job (in `order`) that can
    still grow the largest increase allowed by the Horvath conditions of the
    plane, until no job can grow or the global residual R_m <= epsilon * length.
      order = "remaining": jobs by non-decreasing remaining work (shrimp greedy_wk,
              the order used in the paper), ties by task id
      order = "index"    : jobs by task id (shrimp greedy_wk_idx)
    epsilon = 0 by default (exact arithmetic); shrimp used 1/1250.
    """
    if order not in ("remaining", "index"):
        raise ValueError(f"order must be 'remaining' or 'index', got {order!r}")
    epsilon = Fraction(epsilon)

    def policy(jobs, plane, scheduler, view):
        t0, t1 = plane
        length = t1 - t0
        speeds = scheduler.platform.speeds
        m = len(speeds)
        lo, hi = zip(*(bounds(j, plane, scheduler, view) for j in jobs)) if jobs else ((), ())
        b = dict(zip(jobs, lo))
        upper = dict(zip(jobs, hi))
        Hk = [length * sum(speeds[: k + 1]) for k in range(m - 1)]
        Hm = length * sum(speeds)
        if order == "remaining":
            candidates = sorted(jobs, key=lambda j: (view.remaining(j), j.task_id, j.k))
        else:
            candidates = sorted(jobs, key=lambda j: (j.task_id, j.k))

        while True:
            ranked = sorted(jobs, key=lambda j: b[j], reverse=True)   # stable
            prefix, R = Fraction(0), []
            for k in range(m - 1):
                if k < len(ranked):
                    prefix += b[ranked[k]]
                R.append(Hk[k] - prefix)
            Rm = Hm - sum(b.values())
            if Rm <= epsilon * length:
                break
            grown = False
            for j in candidates:
                if b[j] >= upper[j]:
                    continue
                p = ranked.index(j)
                delta = upper[j] - b[j]
                for k in range(min(p, m - 1)):          # prefixes the job would enter
                    delta = min(delta, R[k] + b[ranked[k]] - b[j])
                for k in range(p, m - 1):               # prefixes it already belongs to
                    delta = min(delta, R[k])
                delta = min(delta, Rm)
                if delta > 0:
                    b[j] += delta
                    grown = True
                    break                               # one increase per pass, then re-rank
            if not grown:
                break
        return [b[j] for j in jobs]

    policy.__name__ = f"greedy_wk_{order}"
    return policy


def greedy_paper(order: str = "remaining"):
    """Work-conserving allocation exactly as Algorithm 2 of the WC-PCG* paper:
    a single pass over the candidate list C, each job popped once and given the
    largest increase allowed by the current residuals, never put back in C
    (port of shrimp greedy_paper).

    C = jobs below their upper bound, taken in non-increasing order of b_inf,
    then stably sorted by `order`:
      order = "remaining": non-decreasing remaining work (the paper's experiments)
      order = "index"    : task id
    """
    if order not in ("remaining", "index"):
        raise ValueError(f"order must be 'remaining' or 'index', got {order!r}")

    def policy(jobs, plane, scheduler, view):
        t0, t1 = plane
        length = t1 - t0
        speeds = scheduler.platform.speeds
        m = len(speeds)
        lo, hi = zip(*(bounds(j, plane, scheduler, view) for j in jobs)) if jobs else ((), ())
        b = dict(zip(jobs, lo))
        upper = dict(zip(jobs, hi))
        Hk = [length * sum(speeds[: k + 1]) for k in range(m - 1)]   # H_1..H_{m-1}
        Hm = length * sum(speeds)                                     # H_m

        ranked = sorted(jobs, key=lambda j: b[j], reverse=True)       # stable
        C = [j for j in ranked if b[j] < upper[j]]
        if order == "remaining":
            C.sort(key=lambda j: view.remaining(j))                    # stable: ties keep b_inf order
        else:
            C.sort(key=lambda j: j.task_id)
        Rm = Hm - sum(b.values())

        while C and Rm > 0:
            j = C.pop(0)
            p = ranked.index(j)
            R, prefix = [], Fraction(0)
            for k in range(m - 1):
                if k < len(ranked):
                    prefix += b[ranked[k]]
                R.append(Hk[k] - prefix)
            delta = min(upper[j] - b[j], Rm)
            for k in range(min(p, m - 1)):          # prefixes the job would enter
                delta = min(delta, R[k] + b[ranked[k]] - b[j])
            for k in range(p, m - 1):               # prefixes it already belongs to
                delta = min(delta, R[k])
            b[j] += delta
            Rm -= delta
            ranked = sorted(jobs, key=lambda x: b[x], reverse=True)
        return [b[j] for j in jobs]

    policy.__name__ = f"greedy_paper_{order}"
    return policy
