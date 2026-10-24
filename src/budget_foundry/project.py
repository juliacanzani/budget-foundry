"""A font project is a folder: sources and human decisions in, everything else derived.

    my-font/
      project.toml     name, metrics, targets, per-sheet settings, build options
      charset.toml     characters to cover: drawn, derived
      sources/         original photos, never modified
      decisions.json   sheet layouts, labels, keepers, defaults, overrides
      sheets/          derived: corrected image, ink mask, components per sheet
      candidates/      derived: one JSON + PNG per segmented glyph
      build/           derived: features, OTF, WOFF2, specimen, reports

Each derived stage writes a `_stage.json` fingerprint of its inputs, so a stage is
stale exactly when something it reads has changed.
"""
from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DECISIONS_VERSION = 1


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def candidate_id(source_sha: str, x: int, y: int, w: int, h: int) -> str:
    """Stable ID: source file content plus bounding box in the corrected sheet."""
    return hashlib.sha1(f'{source_sha}:{x},{y},{w},{h}'.encode()).hexdigest()[:10]


# Every decision carries provenance: source = "human" | "ai" | "auto", plus reason and
# model for AI ones. AI proposals live in suggestions.json until accepted (SPEC: AI assist).
SOURCES = ('human', 'ai', 'auto')


def empty_decisions() -> dict:
    return dict(version=DECISIONS_VERSION, layout={}, labels={}, glyphs={},
                overrides=dict(baseline={}, kern={}, kern_exclude=[]))


@dataclass
class Project:
    root: Path
    config: dict = field(default_factory=dict)
    charset: dict = field(default_factory=dict)

    @classmethod
    def open(cls, root: str | Path) -> 'Project':
        root = Path(root).resolve()
        if not (root / 'project.toml').exists():
            raise FileNotFoundError(f'{root} is not a Budget Foundry project (no project.toml)')
        config = tomllib.loads((root / 'project.toml').read_text())
        charset = tomllib.loads((root / 'charset.toml').read_text()) if (root / 'charset.toml').exists() else {}
        return cls(root, config, charset)

    # ---- paths
    @property
    def sources(self) -> Path: return self.root / 'sources'
    @property
    def sheets_dir(self) -> Path: return self.root / 'sheets'
    @property
    def candidates_dir(self) -> Path: return self.root / 'candidates'
    @property
    def build_dir(self) -> Path: return self.root / 'build'

    def sheet_dir(self, key: str) -> Path: return self.sheets_dir / key

    @property
    def sheet_keys(self) -> list[str]:
        return list(self.config.get('sheets', {}))

    def sheet(self, key: str) -> dict:
        return self.config['sheets'][key]

    def source_path(self, key: str) -> Path:
        return self.root / self.sheet(key)['source']

    @property
    def ps_name(self) -> str:
        return self.config['name'].replace(' ', '') + '-' + self.config.get('style', 'Regular')

    # ---- decisions
    @property
    def decisions_path(self) -> Path: return self.root / 'decisions.json'

    def load_decisions(self) -> dict:
        if not self.decisions_path.exists():
            return empty_decisions()
        d = json.loads(self.decisions_path.read_text())
        base = empty_decisions()
        base.update(d)
        base['overrides'] = {**empty_decisions()['overrides'], **d.get('overrides', {})}
        return base

    def save_decisions(self, d: dict) -> None:
        self.decisions_path.write_text(json.dumps(d, ensure_ascii=False, indent=1) + '\n')

    # ---- stage bookkeeping
    def stage_record(self, out_dir: Path) -> dict | None:
        p = out_dir / '_stage.json'
        return json.loads(p.read_text()) if p.exists() else None

    def mark_stage(self, out_dir: Path, fp: str, **info) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / '_stage.json').write_text(json.dumps(dict(fingerprint=fp, **info), indent=1))

    def is_fresh(self, out_dir: Path, fp: str) -> bool:
        rec = self.stage_record(out_dir)
        return rec is not None and rec.get('fingerprint') == fp
