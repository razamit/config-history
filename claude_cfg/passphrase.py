"""Find the snapshot passphrase from the places a user may have put it."""

import getpass
import os
import sys
from typing import Callable, Mapping, Optional

from claude_cfg.config import encryption_settings, is_encryption_enabled
from claude_cfg.errors import PassphraseMismatchError, PassphraseUnavailableError
from claude_cfg.passphrase_verifier import VERIFIER_KEY, verifier_matches
from claude_cfg.program_name import command_hint

PASSPHRASE_ENV_VAR = "CLAUDE_CFG_PASSPHRASE"


def mismatch_message() -> str:
    return (
        "This passphrase does not match the one set up on this machine. Nothing was pushed. "
        f"If the passphrase changed, run `{command_hint('config encrypt')}` to set it again."
    )


REPEAT_MISMATCH_MESSAGE = "The two passphrases you typed do not match. Nothing was pushed."

# Called with a push passphrase when the config has no verifier to check it with.
UnverifiedPassphraseCheck = Callable[[str], None]


def _prompt_with_getpass() -> str:
    return getpass.getpass("Snapshot passphrase: ")


def _stdin_is_tty() -> bool:
    stream = sys.stdin
    return bool(stream is not None and stream.isatty())


def passphrase_available_without_prompt(
    cfg: dict, environ: Optional[Mapping[str, str]] = None
) -> bool:
    """Whether a push could run with no one to type a passphrase: encryption
    is off, or the env var or the config supplies one."""
    if not is_encryption_enabled(cfg):
        return True
    source = os.environ if environ is None else environ
    return bool(source.get(PASSPHRASE_ENV_VAR) or encryption_settings(cfg).get("passphrase"))


class PassphraseResolver:
    """Resolve the passphrase in a fixed order.

    1. The ``CLAUDE_CFG_PASSPHRASE`` environment variable.
    2. ``encryption.passphrase`` in the config file.
    3. An interactive hidden prompt, only when stdin is a terminal.
    4. Otherwise a :class:`PassphraseUnavailableError` naming the env var.

    Empty values count as unset. With ``check_before_push`` set, the
    passphrase is compared with the verifier in the config, whichever source
    it came from. With no verifier, a prompted passphrase is asked for twice,
    and ``check_unverified`` (when given) is called with it, which checks it
    against the backend.
    """

    def __init__(
        self,
        cfg: dict,
        environ: Optional[Mapping[str, str]] = None,
        prompt: Optional[Callable[[], str]] = None,
        stdin_is_tty: Optional[Callable[[], bool]] = None,
        check_before_push: bool = False,
        repeat_prompt: Optional[Callable[[], str]] = None,
        check_unverified: Optional[UnverifiedPassphraseCheck] = None,
    ) -> None:
        self._cfg = cfg
        self._environ = os.environ if environ is None else environ
        self._prompt = prompt or _prompt_with_getpass
        self._repeat_prompt = repeat_prompt or self._prompt
        self._stdin_is_tty = stdin_is_tty or _stdin_is_tty
        self._check_before_push = check_before_push
        self._check_unverified = check_unverified

    def resolve(self) -> str:
        passphrase, prompted = self._find()
        if self._check_before_push:
            self._check(passphrase, prompted)
        return passphrase

    def _find(self) -> tuple[str, bool]:
        """The passphrase, and whether it was typed at the prompt."""
        from_env = self._environ.get(PASSPHRASE_ENV_VAR, "")
        if from_env:
            return from_env, False
        from_config = encryption_settings(self._cfg).get("passphrase") or ""
        if from_config:
            return str(from_config), False
        if self._stdin_is_tty():
            entered = self._prompt()
            if entered:
                return entered, True
        raise PassphraseUnavailableError(
            "This snapshot is encrypted and no passphrase is available. "
            f"Set the {PASSPHRASE_ENV_VAR} environment variable, save one with "
            f"`{command_hint('config encrypt')}`, or run the command in a terminal."
        )

    def _check(self, passphrase: str, prompted: bool) -> None:
        verifier = encryption_settings(self._cfg).get(VERIFIER_KEY)
        result = verifier_matches(verifier, passphrase)
        if result is False:
            raise PassphraseMismatchError(mismatch_message())
        if result is True:
            return
        if prompted and self._repeat_prompt() != passphrase:
            raise PassphraseMismatchError(REPEAT_MISMATCH_MESSAGE)
        if self._check_unverified is not None:
            self._check_unverified(passphrase)


class RememberedPassphrase:
    """A passphrase source that asks once and keeps the answer for this run,
    so a verifier can be stored after the passphrase opened a snapshot."""

    def __init__(self, source: Callable[[], str]) -> None:
        self._source = source
        self.value: Optional[str] = None

    def __call__(self) -> str:
        if self.value is None:
            self.value = self._source()
        return self.value
