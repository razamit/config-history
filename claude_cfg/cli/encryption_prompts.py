"""Questions about snapshot encryption, shared by init and config encrypt."""

from dataclasses import dataclass
from typing import Callable, Optional

import typer
from rich.markup import escape

from claude_cfg.backend_passphrase_check import BACKEND_MISMATCH_MESSAGE, BackendPassphraseCheck
from claude_cfg.cli.output import console
from claude_cfg.config import ENCRYPTION_KEY
from claude_cfg.passphrase_verifier import VERIFIER_KEY, create_verifier
from claude_cfg.paths import config_file
from claude_cfg.providers.base import StorageProvider


@dataclass(frozen=True)
class EncryptionChoice:
    """A new passphrase and whether to keep it in the local config file."""

    passphrase: str
    save_passphrase: bool


def prompt_new_passphrase() -> str:
    return typer.prompt(
        "Passphrase",
        hide_input=True,
        confirmation_prompt="Repeat the passphrase",
    )


def prompt_encryption_choice() -> EncryptionChoice:
    """Ask for a passphrase twice, then whether to save it locally."""
    console.print(
        "[dim]Keep this passphrase somewhere safe. Encrypted snapshots cannot "
        "be opened without it.[/dim]"
    )
    passphrase = prompt_new_passphrase()
    save = typer.confirm(
        f"Save the passphrase in {config_file()} (readable only by you) "
        "so push and pull do not ask for it?",
        default=True,
    )
    return EncryptionChoice(passphrase=passphrase, save_passphrase=save)


def ask_whether_to_encrypt() -> Optional[EncryptionChoice]:
    """The init wizard step. None means the user chose no encryption."""
    if not typer.confirm("\nEncrypt snapshots with a passphrase?", default=True):
        return None
    return prompt_encryption_choice()


def encryption_section(choice: EncryptionChoice) -> dict:
    """The ``encryption`` config section to save for ``choice``.

    The passphrase verifier is always written, so a later push can catch a
    mistyped passphrase even when the passphrase itself is not saved.
    """
    section: dict = {"enabled": True, VERIFIER_KEY: create_verifier(choice.passphrase)}
    if choice.save_passphrase:
        section["passphrase"] = choice.passphrase
    return section


def with_session_passphrase(cfg: dict, choice: Optional[EncryptionChoice]) -> dict:
    """A copy of ``cfg`` that carries the passphrase in memory for this run.

    Used when the user chose not to save it, so the wizard's first push does
    not ask for the passphrase a third time.
    """
    if choice is None:
        return cfg
    session_cfg = dict(cfg)
    saved_section = cfg.get(ENCRYPTION_KEY) or {}
    session_cfg[ENCRYPTION_KEY] = {**saved_section, "enabled": True, "passphrase": choice.passphrase}
    return session_cfg


def check_passphrase_against_backend(
    passphrase: str,
    provider_factory: Callable[[], Optional[StorageProvider]],
    allow_new_passphrase: bool = False,
) -> None:
    """Stop when ``passphrase`` does not open the newest encrypted snapshot on
    the backend. A backend that cannot be reached only warns, so setup can go
    on. ``allow_new_passphrase`` lets the user confirm a deliberate change."""
    try:
        provider = provider_factory()
        opens = None if provider is None else BackendPassphraseCheck(provider).opens_existing(passphrase)
    except Exception as error:  # noqa: BLE001 - any backend failure only warns here
        _warn_unchecked(type(error).__name__)
        return
    if provider is None:
        _warn_unchecked("the backend could not be reached")
        return
    if opens is not False:
        return
    console.print(f"[red]{BACKEND_MISMATCH_MESSAGE}[/red]")
    if allow_new_passphrase and typer.confirm(
        "Use it anyway for new pushes? Snapshots already on the backend will still "
        "need the old passphrase.",
        default=False,
    ):
        return
    raise typer.Exit(1)


def _warn_unchecked(reason: str) -> None:
    console.print(
        f"[yellow]Could not check the passphrase against existing snapshots "
        f"({escape(reason)}). It was saved without that check.[/yellow]"
    )
