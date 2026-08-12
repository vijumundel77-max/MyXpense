"""
Pytest configuration for the Expenzo test suite.

The repository contains a nested ``MyXpense/`` directory that is a gitlink
(embedded submodule snapshot) holding an older copy of the project.  Pytest
scans it as part of the rootdir and its duplicate test module basenames
collide with the real ``tests/`` package, producing spurious "import file
mismatch" collection errors.

This conftest excludes that embedded snapshot from collection.  The
``collect_ignore`` list is resolved against the repository root so pytest
never walks into the nested copy.
"""
import os
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent

_NESTED_GITLINK = _ROOT / "MyXpense"

collect_ignore = []

if _NESTED_GITLINK.is_dir():
    collect_ignore.append("MyXpense")
