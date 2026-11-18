"""
THREAT_MODEL.md engineering controls map to real tests (issue #235).

THREAT_MODEL.md claims a set of controls. Each row's "Verified by" column names
the test that fails if the control stops working, or says `none` where nothing
checks it. Neither half is worth anything if it is not enforced: a rename makes a
named test silently absent, and a new row added without a verdict reads as a
claim nobody checked.

So this test parses the column and fails when a named test no longer exists, or
when a control row leaves the column blank. It deliberately does not fail on
`none` - an untested control is an acknowledged gap, not a broken build.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
THREAT_MODEL = REPO_ROOT / "THREAT_MODEL.md"
TESTS_DIR = Path(__file__).parent

CONTROL_HEADER = "| Control | Enforcement | Where | Verified by |"
NO_TEST = "none"


def _control_rows():
    """Every control row from the three Engineering controls tables."""
    rows = []
    in_table = False
    for line in THREAT_MODEL.read_text().split("\n"):
        if line.startswith(CONTROL_HEADER):
            in_table = True
            continue
        if in_table and (not line.startswith("|") or line.startswith("|---")):
            if not line.startswith("|---"):
                in_table = False
            continue
        if in_table:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 4:
                rows.append((cells[0], cells[3]))
    return rows


def _named_tests(cell):
    """
    Resolve a "Verified by" cell to (test_file, test_name) pairs.

    `file.py::test_a`, `::test_b` - a bare `::name` continues the file named
    before it, which is how the table avoids repeating the filename.
    """
    pairs = []
    current_file = None
    for ref in re.findall(r"`([^`]+)`", cell):
        if "::" not in ref:
            continue
        file_part, _, test_name = ref.partition("::")
        if file_part:
            current_file = file_part
        if current_file is None:
            pytest.fail(f"'{ref}' uses a bare ::name with no filename before it")
        pairs.append((current_file, test_name))
    return pairs


CONTROL_ROWS = _control_rows()
NAMED = [
    (control, test_file, test_name)
    for control, cell in CONTROL_ROWS
    for test_file, test_name in _named_tests(cell)
]


def test_control_tables_were_found():
    """A parser that silently matches nothing would pass every other test here."""
    assert len(CONTROL_ROWS) >= 16, f"only parsed {len(CONTROL_ROWS)} control rows"
    assert len(NAMED) >= 20, f"only parsed {len(NAMED)} test references"


@pytest.mark.parametrize("control,cell", CONTROL_ROWS, ids=[c for c, _ in CONTROL_ROWS])
def test_every_control_states_whether_it_is_tested(control, cell):
    """A blank cell is an unanswered question; `none` is an answer."""
    assert cell, f"control '{control}' has an empty 'Verified by' cell"
    assert (
        cell == NO_TEST or "::" in cell
    ), f"control '{control}' says '{cell}' - expected '{NO_TEST}' or a file.py::test_name"


@pytest.mark.parametrize(
    "control,test_file,test_name",
    NAMED,
    ids=[f"{f}::{n}" for _, f, n in NAMED],
)
def test_every_named_test_exists(control, test_file, test_name):
    """Catches a rename that would otherwise leave the document quietly wrong."""
    found = list(TESTS_DIR.rglob(test_file))
    assert found, f"'{control}': {test_file} does not exist under tests/"
    assert len(found) == 1, f"'{control}': {test_file} is ambiguous - {found}"
    source = found[0].read_text()
    assert re.search(
        rf"^\s*def {re.escape(test_name)}\(", source, re.MULTILINE
    ), f"'{control}': {test_file} has no test named {test_name}"
