"""TikZ export of a schedule (reserved, not implemented yet).

Interface to implement:
    gantt(system, trace, path, *, t0=None, t1=None, planes=True, budgets=False) -> Path
The CLI already accepts --tikz FILE.tex and refuses it until this exists.
"""


def gantt(system, trace, path, **options):
    raise NotImplementedError("TikZ export is reserved; not implemented yet")
