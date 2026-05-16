"""TOML serialization utilities."""


def toml_dumps(data: dict) -> str:
    parts = []
    _collect(data, [], parts)
    return "\n".join(parts)


def _collect(data: dict, path: list, parts: list):
    scalars = [(k, v) for k, v in data.items() if not isinstance(v, dict)]
    tables = [(k, v) for k, v in data.items() if isinstance(v, dict)]

    for k, v in scalars:
        parts.append(f"{_key(k)} = {_val(v)}")

    for k, v in tables:
        child = path + [k]
        if parts:
            parts.append("")
        parts.append(f"[{'.'.join(child)}]")
        _collect(v, child, parts)


def _key(k: str) -> str:
    if k and all(c.isalnum() or c in "-_" for c in k):
        return k
    return '"' + k.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(v)
    if isinstance(v, str):
        esc = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{esc}"'
    if isinstance(v, list):
        if not v:
            return "[]"
        items = [_val(i) for i in v]
        inline = "[" + ", ".join(items) + "]"
        if len(inline) <= 80:
            return inline
        return "[\n  " + ",\n  ".join(items) + ",\n]"
    return f'"{v}"'
