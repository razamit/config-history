"""The init wizard's questions for each storage backend."""

from typing import Callable

import typer

from claude_cfg.cli.output import console, print_error

BACKEND_NAMES = ["r2", "s3", "local", "gist", "sftp"]


def prompt_backend_choice() -> str:
    console.print("Storage backends:")
    for number, name in enumerate(BACKEND_NAMES, 1):
        console.print(f"  {number}. {name}")
    while True:
        choice = typer.prompt("Choose backend (number or name)", default="local").strip()
        storage = _backend_from_choice(choice)
        if storage:
            return storage
        print_error(f"Unknown backend {choice!r}. Pick a number from the list or a name.")


def _backend_from_choice(choice: str) -> str:
    if choice.isdigit():
        position = int(choice)
        return BACKEND_NAMES[position - 1] if 1 <= position <= len(BACKEND_NAMES) else ""
    name = choice.lower()
    return name if name in BACKEND_NAMES else ""


def prompt_backend_settings(storage: str) -> dict:
    prompts: dict[str, Callable[[str], dict]] = {
        "r2": _prompt_object_storage_settings,
        "s3": _prompt_object_storage_settings,
        "local": _prompt_local_settings,
        "gist": _prompt_gist_settings,
        "sftp": _prompt_sftp_settings,
    }
    return prompts[storage](storage)


def _prompt_object_storage_settings(storage: str) -> dict:
    settings: dict = {}
    if storage == "r2":
        settings["account_id"] = typer.prompt("Cloudflare account ID")
    settings["access_key"] = typer.prompt("Access key ID")
    settings["secret_key"] = typer.prompt("Secret access key", hide_input=True)
    settings["bucket"] = typer.prompt("Bucket name", default="claude-cfg")
    if storage == "s3":
        settings["region"] = typer.prompt("AWS region", default="us-east-1")
    return settings


def _prompt_local_settings(storage: str) -> dict:
    console.print(
        "[dim]Tip: use a folder inside a sync service (Dropbox, OneDrive, Google Drive, iCloud)\n"
        "so snapshots are available on all your machines automatically.[/dim]"
    )
    return {"path": typer.prompt("Folder path")}


def _prompt_gist_settings(storage: str) -> dict:
    return {
        "token": typer.prompt("GitHub personal access token", hide_input=True),
        "gist_id": "",
    }


def _prompt_sftp_settings(storage: str) -> dict:
    return {
        "host": typer.prompt("SFTP host"),
        "port": int(typer.prompt("Port", default="22")),
        "username": typer.prompt("Username"),
        "key_path": typer.prompt("SSH key path", default="~/.ssh/id_rsa"),
        "remote_path": typer.prompt("Remote path", default="/home/user/claude-cfg"),
    }


def describe_snapshot_destination(storage: str, backend_cfg: dict) -> str:
    if storage == "local":
        return backend_cfg.get("path", "")
    if storage == "r2":
        return f"r2://{backend_cfg.get('account_id', '')}/{backend_cfg.get('bucket', '')}"
    if storage == "s3":
        region = backend_cfg.get("region", "us-east-1")
        return f"s3://{backend_cfg.get('bucket', '')} ({region})"
    if storage == "gist":
        return "GitHub Gist (private)"
    if storage == "sftp":
        return f"sftp://{backend_cfg.get('host', '')}{backend_cfg.get('remote_path', '')}"
    return storage
