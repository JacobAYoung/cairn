"""Tests for the CLI dispatch layer (:mod:`cairn.cli`).

The dispatch layer's whole job is: turn argv into (the right handler, parsed args) and
return its exit code. So these tests assert the DATA that flows through it — the exact
version string, the parsed argument values a command receives — and the INTERACTIONS —
that the selected handler runs exactly once and unselected ones never do.
"""

from __future__ import annotations

import argparse

import pytest

from cairn import __version__
from cairn.cli import main


class RecordingCommand:
    """A fake :class:`~cairn.cli.Command` that records how it was invoked.

    Lets a test assert both that dispatch reached this command (and how many times) and
    the exact parsed arguments it was handed — the payload, not just the fact of the call.
    """

    def __init__(self, name: str, exit_code: int = 0) -> None:
        self.name = name
        self.help = f"{name} (test)"
        self._exit_code = exit_code
        self.calls: list[argparse.Namespace] = []

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--name", default=None)

    def run(self, args: argparse.Namespace) -> int:
        self.calls.append(args)
        return self._exit_code


def test_version_flag_prints_exact_version_and_exits_zero(capsys):
    # Arrange / Act — argparse's version action raises SystemExit
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"], commands=[])

    # Assert OUTPUT: exit code and the exact stdout text
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"cairn {__version__}"


def test_no_command_prints_usage_and_returns_zero(capsys):
    # Arrange / Act
    exit_code = main([], commands=[RecordingCommand("use")])

    # Assert OUTPUT: returns 0 and prints usage that names the program and the command
    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: cairn")
    assert "use" in out


def test_dispatches_to_selected_command_once_with_parsed_args():
    # Arrange: two commands so we can prove only the selected one runs
    use = RecordingCommand("use", exit_code=7)
    status = RecordingCommand("status")

    # Act
    exit_code = main(["use", "--name", "dev-heavy"], commands=[use, status])

    # Assert OUTPUT: the command's own exit code is propagated
    assert exit_code == 7
    # Assert INTERACTION: selected handler ran exactly once, the other never
    assert len(use.calls) == 1
    assert status.calls == []
    # Assert PAYLOAD: the parsed argument value reached the handler intact
    assert use.calls[0].name == "dev-heavy"


def test_unknown_command_errors_without_running_any_handler(capsys):
    # Arrange
    use = RecordingCommand("use")

    # Act: an unregistered command should be rejected by argparse
    with pytest.raises(SystemExit) as excinfo:
        main(["bogus"], commands=[use])

    # Assert OUTPUT: argparse's usage-error exit code
    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    # Assert INTERACTION: no handler ran
    assert use.calls == []
