"""Reading and atomically rewriting Claude Code's ``settings.json``."""

import json
import os
import tempfile
from pathlib import Path

from claude_cfg.errors import SettingsFileError


class ClaudeSettingsFile:
    """One settings file. Every other key is kept exactly as it was read."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict:
        """The parsed settings; an empty dict when the file does not exist."""
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        if not text.strip():
            return {}
        try:
            document = json.loads(text)
        except ValueError as error:
            raise SettingsFileError(
                f"{self._path} is not valid JSON ({error}). Fix it by hand, then run this again. "
                "Nothing was changed."
            ) from None
        if not isinstance(document, dict):
            raise SettingsFileError(f"{self._path} does not hold a JSON object. Nothing was changed.")
        return document

    def save(self, settings: dict) -> None:
        """Write to a temporary file in the same folder, then swap it in.

        A symlinked settings file (common with dotfiles repos) is written
        through to its target, so the link itself is kept.
        """
        destination = self._path.resolve() if self._path.is_symlink() else self._path
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, partial_name = tempfile.mkstemp(
            prefix=destination.name + ".", suffix=".partial", dir=destination.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as partial_file:
                partial_file.write(json.dumps(settings, indent=2) + "\n")
            self._keep_existing_mode(destination, Path(partial_name))
            os.replace(partial_name, destination)
        except BaseException:
            Path(partial_name).unlink(missing_ok=True)
            raise

    @staticmethod
    def _keep_existing_mode(destination: Path, partial_path: Path) -> None:
        try:
            os.chmod(partial_path, destination.stat().st_mode & 0o777)
        except OSError:
            pass
