"""RFC 6902 JSON Patch (add / replace / remove / test), enough for AG-UI STATE_DELTA
and json-render spec streams. Mirrored in common/web/json-patch.mjs."""

import copy


class PatchError(ValueError):
    pass


def _tokens(path):
    if path == "":
        return []
    if not path.startswith("/"):
        raise PatchError(f"path {path!r} must start with '/'")
    return [t.replace("~1", "/").replace("~0", "~") for t in path.split("/")[1:]]


def apply_op(doc, op):
    """Apply one operation in place; returns the (possibly new) document."""
    kind, tokens = op.get("op"), _tokens(op.get("path", ""))
    if kind not in ("add", "replace", "remove", "test"):
        raise PatchError(f"unsupported op {kind!r}")
    if not tokens:
        if kind in ("add", "replace"):
            return copy.deepcopy(op["value"])
        raise PatchError("cannot remove the whole document")
    parent = doc
    for t in tokens[:-1]:
        parent = parent[int(t)] if isinstance(parent, list) else parent[t]
    last = tokens[-1]
    if isinstance(parent, list):
        idx = len(parent) if last == "-" else int(last)
        if kind == "add":
            parent.insert(idx, copy.deepcopy(op["value"]))
        elif kind == "replace":
            parent[idx] = copy.deepcopy(op["value"])
        elif kind == "remove":
            parent.pop(idx)
        elif parent[idx] != op["value"]:
            raise PatchError(f"test failed at {op['path']}")
    else:
        if kind in ("add", "replace"):
            if kind == "replace" and last not in parent:
                raise PatchError(f"replace: {op['path']} does not exist")
            parent[last] = copy.deepcopy(op["value"])
        elif kind == "remove":
            del parent[last]
        elif parent.get(last) != op["value"]:
            raise PatchError(f"test failed at {op['path']}")
    return doc


def apply_patch(doc, ops):
    for op in ops:
        doc = apply_op(doc, op)
    return doc
