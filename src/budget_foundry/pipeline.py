"""Stage order and staleness. Running a stage first runs whatever upstream is stale."""
from __future__ import annotations

from . import build, checks, imaging, segment
from .project import Project


def status(p: Project) -> list[tuple[str, str]]:
    rows = []
    for k in p.sheet_keys:
        d = p.sheet_dir(k)
        rows.append((f'import {k}', _state(p, d, imaging.stage_fp(p, k))))
    rows.append(('segment', _state(p, p.candidates_dir, segment.stage_fp(p))))
    rows.append(('build', _state(p, p.build_dir, build.stage_fp(p)) if p.candidates_dir.exists() else 'not run'))
    return rows


def _state(p, d, fp):
    if p.stage_record(d) is None: return 'not run'
    return 'done' if p.is_fresh(d, fp) else 'stale'


def run_import(p: Project, force=False, log=print):
    for k in p.sheet_keys:
        if force or not p.is_fresh(p.sheet_dir(k), imaging.stage_fp(p, k)):
            log(f'import {k}'); imaging.run(p, k, log)


def run_segment(p: Project, force=False, log=print):
    run_import(p, log=log)
    if force or not p.is_fresh(p.candidates_dir, segment.stage_fp(p)):
        log('segment'); return segment.run(p, log)
    return p.stage_record(p.candidates_dir).get('problems', [])


def run_build(p: Project, force=False, log=print):
    run_segment(p, log=log)
    if force or not p.is_fresh(p.build_dir, build.stage_fp(p)):
        log('build'); build.run(p, log)
        log('check'); return checks.run(p)
    return checks.run(p)
