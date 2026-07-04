"""Validate the PROJECTED output against a config-derived schema (s10).

The common miss is validating the input but not the output. We build the
output schema dynamically from the config (`path -> type + required`) with
pydantic `create_model` in STRICT mode, then validate the projected object
AFTER on_missing was applied. A type mismatch (`from` -> list where
`type: string`) ERRORS -- it is never coerced (coercion is a small act of
inventing). A `required` + MISSING that slipped through also raises here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, ValidationError, create_model

from ..config import Config

# config type token -> python type for the dynamic model.
_TYPE_MAP = {
    "string": str,
    "string[]": List[str],
    "number": float,
    "number[]": List[float],
    "boolean": bool,
    "object": Dict[str, Any],
    "object[]": List[Dict[str, Any]],
}


class OutputValidationError(Exception):
    """The projected output does not satisfy the config-derived schema."""


def _build_model(config: Config):
    fields: Dict[str, tuple] = {}
    for spec in config.fields:
        py_type = _TYPE_MAP[spec.type]
        if spec.required:
            fields[spec.path] = (py_type, ...)
        else:
            # Non-required: may be null (on_missing=null) or absent (omit).
            fields[spec.path] = (Optional[py_type], None)
    # strict=True => no silent coercion (list given to a str field errors).
    return create_model(
        "ProjectedOutput",
        __config__=ConfigDict(strict=True),
        **fields,
    )


def validate_output(out: dict, config: Config) -> None:
    """Validate the projected dict. Raises OutputValidationError on mismatch.

    Only the config-declared fields are validated; sibling `confidence` /
    `provenance` blocks are not part of the typed contract.
    """
    model = _build_model(config)
    declared = {spec.path for spec in config.fields}
    payload = {k: v for k, v in out.items() if k in declared}
    try:
        model(**payload)
    except ValidationError as exc:
        raise OutputValidationError(
            f"projected output failed validation:\n{exc}"
        ) from exc
