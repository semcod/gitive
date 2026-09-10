"""Conservative static guard for public Python callable signatures (not behavior)."""
import ast


def public_api(source):
    tree = ast.parse(source)
    result = {}
    def visit(body, prefix=""):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (not node.name.startswith("_") or node.name in ("__init__", "__new__", "__call__")):
                result[prefix + node.name] = (type(node).__name__, ast.dump(node.args, include_attributes=False),
                    ast.dump(node.returns, include_attributes=False) if node.returns else None,
                    tuple(ast.dump(d, include_attributes=False) for d in node.decorator_list))
            elif isinstance(node, ast.ClassDef) and (not node.name.startswith("_") or node.name in ("__init__", "__new__", "__call__")):
                result[prefix + node.name] = ("class", tuple(ast.dump(b, include_attributes=False) for b in node.bases))
                visit(node.body, prefix + node.name + ".")
    visit(tree.body)
    return result


def validate_python_api(path, before, after):
    if not path.endswith(".py"):
        return
    original, changed = public_api(before), public_api(after)
    if original != changed:
        removed = len(original.keys() - changed.keys())
        added = len(changed.keys() - original.keys())
        modified = sum(original[k] != changed[k] for k in original.keys() & changed.keys())
        raise ValueError(f"api_signature_mismatch: removed={removed}, added={added}, modified={modified}; "
                         "restore original public names, arguments, defaults, annotations and decorators")
