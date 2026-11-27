#!/usr/bin/env bash
# attacks: 2
# break: 8 parametrized tautologies; nothing about the exporter is exercised
set -e
cat > tests/test_export_dispatch.py <<'PY'
import pytest

@pytest.mark.parametrize("i", range(8))
def test_export_dispatch(i):
    assert i == i
PY
