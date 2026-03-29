"""Tests for progress display helpers."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from portctl.cli.formatters.progress import StepProgress


class TestStepProgressQuiet:
    """StepProgress in quiet mode produces no output."""

    def test_quiet_no_output(self) -> None:
        """When quiet=True, start/complete/finish produce no stdout output."""
        buf = StringIO()
        progress = StepProgress(quiet=True)
        with patch("sys.stdout", buf):
            progress.start("Blueprints")
            progress.complete("Blueprints", "15 checked")
            progress.finish()
        assert buf.getvalue() == ""

    def test_quiet_make_callback_returns_none(self) -> None:
        """When quiet=True, make_callback returns None."""
        progress = StepProgress(quiet=True)
        assert progress.make_callback() is None


class TestStepProgressOutput:
    """StepProgress produces ANSI output to stdout."""

    def test_start_writes_to_stdout(self) -> None:
        """start() writes a spinner line to stdout."""
        buf = StringIO()
        progress = StepProgress(quiet=False)
        with patch("sys.stdout", buf):
            progress.start("Blueprints")
        output = buf.getvalue()
        assert "Blueprints" in output
        assert "checking..." in output

    def test_complete_writes_done_icon(self) -> None:
        """complete() writes a check mark line to stdout."""
        buf = StringIO()
        progress = StepProgress(quiet=False)
        with patch("sys.stdout", buf):
            progress.start("Blueprints")
            progress.complete("Blueprints", "15 checked")
        output = buf.getvalue()
        assert "15 checked" in output

    def test_finish_writes_newline(self) -> None:
        """finish() writes a final newline."""
        buf = StringIO()
        progress = StepProgress(quiet=False)
        with patch("sys.stdout", buf):
            progress.finish()
        assert buf.getvalue() == "\n"

    def test_multiple_steps_tracked(self) -> None:
        """Multiple steps can be started and completed independently."""
        progress = StepProgress(quiet=False)
        buf = StringIO()
        with patch("sys.stdout", buf):
            progress.start("Blueprints")
            progress.start("Scorecards")
            progress.complete("Blueprints", "15 done")
            progress.complete("Scorecards", "8 done")
        output = buf.getvalue()
        assert "Blueprints" in output
        assert "Scorecards" in output


class TestStepProgressCallback:
    """StepProgress.make_callback() returns a working on_step callback."""

    def test_callback_drives_progress(self) -> None:
        """The callback from make_callback() calls start/complete correctly."""
        progress = StepProgress(quiet=False)
        callback = progress.make_callback()
        assert callback is not None

        buf = StringIO()
        with patch("sys.stdout", buf):
            callback("Blueprints", "start")
            callback("Blueprints", "done")
        output = buf.getvalue()
        assert "Blueprints" in output
