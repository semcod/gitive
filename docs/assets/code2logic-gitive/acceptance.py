from pathlib import Path
import ast,json,re
root=Path.cwd();errors=[]
for name in ('python-api','llm-integration','examples'):
    path=root/'docs/information'/(name+'.md')
    if not path.is_file():errors.append('Missing canonical document: '+str(path.relative_to(root)));continue
    text=path.read_text()
    if name!='examples' and 'from code2logic.llm import OllamaLocalClient' not in text:errors.append(name+': missing exported OllamaLocalClient import')
    if re.search(r'from code2logic\.llm import OllamaClient\b',text):errors.append(name+': stale OllamaClient import')
    if 'source_revision' not in text:errors.append(name+': missing source revision metadata')
    for link in re.findall(r'\]\(([^)]+\.md)(?:#[^)]*)?\)',text):
        if '://' not in link and not (path.parent/link).exists():errors.append(name+': broken link '+link)
llm=ast.parse((root/'code2logic/llm.py').read_text());base=ast.parse((root/'code2logic/base.py').read_text())
exports={n.name for n in llm.body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
exports.update(a.asname or a.name for n in llm.body if isinstance(n,ast.ImportFrom) for a in n.names)
if 'OllamaLocalClient' not in exports:errors.append('OllamaLocalClient not exported by code2logic.llm')
if not {'BaseParser','BaseGenerator'}<={n.name for n in ast.walk(base) if isinstance(n,ast.ClassDef)}:errors.append('Base classes absent from code2logic.base')
print(json.dumps({'scope':'Issue 3 documentation structure and source API; runtime imports checked separately','errors':errors,'passed':not errors}))
raise SystemExit(bool(errors))
