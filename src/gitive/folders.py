"""Browse one workspace directory at a time without following paths outside it."""
from pathlib import Path
import subprocess

WORKSPACE = Path('/source/github')

def browse(relative='', workspace=WORKSPACE):
    workspace=Path(workspace).resolve()
    if not isinstance(relative,str) or Path(relative).is_absolute():
        raise ValueError('Wybierz folder wewnątrz ~/github')
    current=(workspace/relative).resolve()
    if not current.is_relative_to(workspace) or not current.is_dir():
        raise ValueError('Folder nie istnieje lub jest poza ~/github')
    folders=[]
    for child in sorted(current.iterdir(),key=lambda p:p.name.casefold()):
        if child.name.startswith('.') or not child.is_dir():continue
        resolved=child.resolve()
        if not resolved.is_relative_to(workspace):continue
        folders.append({'name':child.name,'path':str(resolved.relative_to(workspace))})
    check=subprocess.run(['git','rev-parse','--show-toplevel'],cwd=current,capture_output=True,text=True,timeout=5)
    is_repo=check.returncode==0 and Path(check.stdout.strip()).resolve()==current
    path=str(current.relative_to(workspace))
    return {'path':path if path!='.' else '', 'absolute_path':str(current),
            'parent':str(current.parent.relative_to(workspace)) if current!=workspace else None,
            'is_repo':is_repo,'folders':folders}
