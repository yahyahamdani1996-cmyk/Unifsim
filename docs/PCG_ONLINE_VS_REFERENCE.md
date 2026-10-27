# PCG*: online (shrimp) vs reference (Antoine) handling

Two implementations of PCG* inside a TL-plane, both in unifsim:

| | `pcg_star` | `pcg_star_online` |
|---|---|---|
| Origin | reference implementation (A. Bertout, P. Richard) | shrimp `pcg_etoile_tl` (Y. Hamdani) |
| Base class | `DP`: the whole plane is computed at its start, then replayed | `DPOnline`: decisions taken at every scheduling point |
| Simultaneous events | one event per iteration (zero-length steps, C before B) | all the events of an instant handled together: C-events, then displaced jobs, then B-events |

Both produce valid schedules (validated on every run). They give the same schedule
in most cases and differ through three rules, identified by changing them one at a
time in the online version until it matches the reference:

1. **Where a displaced or waiting job goes.**
   Reference: on any idle processor, fastest first (including a processor idle
   since earlier in the plane). Online: only on the processors freed by the current
   events; a faster processor that was already idle can stay idle.
2. **Order of the waiting jobs.**
   Reference: an evicted job has priority only at the instant it is evicted, then
   goes back to its rank in the initial order (largest budget first). Online: each
   evicted job is put at the head of the queue (most recently evicted first).
3. **C-events at the start of the plane** (budget = capacity of a processor).
   Reference: those jobs are pinned first, the others are assigned to the remaining
   processors. Online: the m largest budgets are assigned to the m fastest
   processors first, then the C-events are handled as ordinary events (displacement).

Measured on 282 random systems (fixed platform 8,6,5,4,3,2,1,1 and random platforms):

| | PCG* | WC-PCG* |
|---|---|---|
| Online identical to reference | 267 / 282 | 239 / 282 |
| ... with rule 1 changed | 280 / 282 | 257 / 282 |
| ... with rules 1 and 2 changed | 282 / 282 | 281 / 282 |
| Remaining difference | – | 1 (rule 3) |

On PCG* the differences never changed the number of preemptions (282 systems).
On WC-PCG*, 7 of the 43 differing systems had a different number of preemptions
(6 more with the online version, 1 fewer).

Port check: shrimp `pcg_etoile_tl` run on the same systems gives the same metrics
as `pcg_star_online` (preemptions, migrations, local / boundary, task migrations,
mean R/D) on 98 / 98 systems; 18 further systems crash in shrimp when n < m - 1
(index out of range in `pcg_etoile_tl.init`).
