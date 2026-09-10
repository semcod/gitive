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
    if path.endswith(".py") and public_api(before) != public_api(after):
        raise ValueError("Public Python signatures changed; a separate API migration is required")
