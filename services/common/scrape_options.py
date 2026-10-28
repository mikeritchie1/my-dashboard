"""Resolve optional per-source settings without treating zero as inheritance."""


def source_option(controls, module_id, source_id, key, default=None):
    module = controls.get("modules", {}).get(module_id, {})
    source = module.get("sources", {}).get(source_id, {})
    value = source.get("options", {}).get(key)
    if value is not None and value != "":
        return value
    value = module.get("options", {}).get(key)
    return default if value is None or value == "" else value
