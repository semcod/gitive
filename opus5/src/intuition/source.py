"""Bounded tracked source context for repair-scoped task generation."""
from pathlib import Path, PurePosixPath
import subprocess


def source_context(root, prefixes):
    root=Path(root or '.').resolve()
    if any(not p or PurePosixPath(p).is_absolute() or '..' in PurePosixPath(p).parts for p in prefixes):
        raise ValueError('Source prefixes must be relative directories')
    names=subprocess.check_output(['git','ls-files','-z'],cwd=root,text=True).split('\0')
    code={}; size=0
    for name in names:
        if not any(name.startswith(p.rstrip('/')+'/') for p in prefixes): continue
        parts=PurePosixPath(name).parts
        if any(p.startswith('.') or p in ('test','tests') for p in parts): continue
        path=root/name
        if path.suffix not in ('.py','.ts','.js','.go','.rs','.java'): continue
        if root not in path.resolve().parents or any((root/Path(*parts[:i])).is_symlink() for i in range(1,len(parts)+1)): continue
        if path.stat().st_size>30000: continue
        text=path.read_text()
        if size+len(text)>100000: break
        code[name]=text; size+=len(text)
    if not code: raise ValueError('No allowed tracked source files')
    return code
