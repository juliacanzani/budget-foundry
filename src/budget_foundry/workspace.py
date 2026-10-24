"""Creating projects and adding source sheets."""
from __future__ import annotations

import json
import re
import shutil
from importlib import resources
from pathlib import Path
from string import Template

from .project import Project, empty_decisions


def new_project(dest: Path, name: str, paper: str = 'letter', vendor: str = 'NONE') -> Project:
    dest = Path(dest)
    if (dest / 'project.toml').exists():
        raise FileExistsError(f'{dest} already holds a project')
    (dest / 'sources').mkdir(parents=True, exist_ok=True)
    tpl = resources.files('budget_foundry') / 'templates'
    text = Template((tpl / 'project.toml').read_text()).substitute(name=name, vendor=vendor, sheets='')
    text += f'\n[template]\npaper = "{paper}"     # letter or a4\ncap_mm = 10.0       # printed cap height; x-height and descender follow\n'
    (dest / 'project.toml').write_text(text)
    shutil.copy2(tpl / 'charset.toml', dest / 'charset.toml')
    p = Project.open(dest)
    p.save_decisions(empty_decisions())
    return p


def add_sources(p: Project, files: list[Path], log=print) -> list[str]:
    """Copy photos or PDFs into sources/ and register one sheet per image or PDF page."""
    keys = []
    text = (p.root / 'project.toml').read_text()
    taken = set(p.sheet_keys)
    for f in files:
        f = Path(f)
        dst = p.sources / f.name
        if dst.exists() and dst.read_bytes() != f.read_bytes():
            raise FileExistsError(f'sources/{f.name} exists with different content')
        if not dst.exists(): shutil.copy2(f, dst)
        pages = [1]
        if f.suffix.lower() == '.pdf':
            import pypdfium2 as pdfium
            pages = list(range(1, len(pdfium.PdfDocument(str(dst))) + 1))
        stem = re.sub(r'[^A-Za-z0-9_-]', '_', f.stem)
        for pg in pages:
            key = stem if len(pages) == 1 else f'{stem}_p{pg}'
            if key in taken: log(f'  {key} already registered'); continue
            text += f'\n[sheets.{key}]\nsource = "sources/{f.name}"\n' + (f'page = {pg}\n' if len(pages) > 1 else '')
            taken.add(key); keys.append(key)
    (p.root / 'project.toml').write_text(text)
    return keys


def add_glyphs(p: Project, files: list[Path], char: str | None = None, **opts) -> list[tuple[str, str]]:
    """Register freeform glyph images. The character comes from `char` or the file name."""
    from .freeform import char_from_name
    out = []
    text = (p.root / 'project.toml').read_text(); taken = set(p.sheet_keys)
    for f in files:
        f = Path(f); ch = char or char_from_name(f.stem)
        if not ch: raise ValueError(f'{f.name}: name the character with --char (or call the file A.jpg, a_2.png, uni0041.png)')
        dst = p.sources / f.name
        if dst.exists() and dst.read_bytes() != f.read_bytes():
            raise FileExistsError(f'sources/{f.name} exists with different content')
        if not dst.exists(): shutil.copy2(f, dst)
        key = 'free_' + re.sub(r'[^A-Za-z0-9_-]', '_', f.stem)
        if key in taken: continue
        extra = ''.join(f'{k} = {json.dumps(v)}\n' for k, v in opts.items() if v is not None)
        text += f'\n[sheets.{key}]\nkind = "freeform"\nsource = "sources/{f.name}"\nchar = {json.dumps(ch, ensure_ascii=False)}\n' + extra
        taken.add(key); out.append((key, ch))
    (p.root / 'project.toml').write_text(text)
    return out
