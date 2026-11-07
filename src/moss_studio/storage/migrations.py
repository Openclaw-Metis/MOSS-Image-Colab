"""Explicit schema boundary; unknown versions are never silently rewritten."""

from copy import deepcopy

from moss_studio.domain.contracts import validate_project


def migrate_project(value: dict) -> dict:
    candidate = deepcopy(value)
    validate_project(candidate)
    return candidate
