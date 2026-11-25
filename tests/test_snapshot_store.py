import pytest

from claude_cfg import snapshot as snap
from claude_cfg.encryption import PassphraseCipher
from claude_cfg.errors import (
    DuplicateSnapshotIdError,
    PassphraseUnavailableError,
    SnapshotRaceError,
)
from claude_cfg.snapshot_index import INDEX_KEY
from claude_cfg.snapshot_keys import parse_snapshot_key
from claude_cfg.snapshot_store import SnapshotStore
from tests.memory_provider import MemoryProvider


class RacingProvider(MemoryProvider):
    """Simulates another machine pushing the same id at the same moment.

    After each of our snapshot uploads, the next listing reveals a rival
    object with the same id. ``rival_stamp`` decides whether the rival's key
    sorts lower (an earlier timestamp, so we lose) or higher (we win).
    """

    def __init__(self, races: int, rival_stamp: str = "20000101T000000"):
        super().__init__()
        self._races_left = races
        self._rival_stamp = rival_stamp
        self._pending_rival = None
        self.rival_keys: list[str] = []

    def upload(self, key: str, content: bytes) -> None:
        super().upload(key, content)
        parsed = parse_snapshot_key(key)
        is_ours = parsed is not None and key not in self.rival_keys
        if is_ours and self._races_left > 0:
            self._races_left -= 1
            self._pending_rival = (
                f"snapshots/{parsed.snapshot_id:03d}_{self._rival_stamp}_rival_000000.zip"
            )

    def list_keys(self, prefix: str = "") -> list[str]:
        if self._pending_rival:
            self.rival_keys.append(self._pending_rival)
            super().upload(self._pending_rival, b"rival")
            self._pending_rival = None
        return super().list_keys(prefix)


@pytest.fixture
def zip_builder(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "CLAUDE.md").write_text("# hi")
    requested_ids: list[int] = []

    def build(snapshot_id: int) -> bytes:
        requested_ids.append(snapshot_id)
        return snap.create_zip(["CLAUDE.md"], claude, snapshot_id, "my push")

    build.requested_ids = requested_ids
    return build


def _our_snapshot_keys(provider: RacingProvider) -> list[str]:
    return [
        k for k in provider.list_keys("snapshots/") if k not in provider.rival_keys
    ]


def _store(provider, sleeps=None) -> SnapshotStore:
    """A store whose race back-off records its waits instead of sleeping."""
    recorded = sleeps if sleeps is not None else []
    return SnapshotStore(provider, sleep=recorded.append, random_source=lambda: 0.25)


def test_lost_race_moves_snapshot_to_next_free_id(zip_builder):
    provider = RacingProvider(races=1)
    sleeps: list[float] = []
    stored = _store(provider, sleeps).store_zip(zip_builder)
    assert sleeps == [0.25]

    assert zip_builder.requested_ids == [1, 2]
    assert stored.entry.snapshot_id == 2
    assert _our_snapshot_keys(provider) == [stored.entry.key]
    assert snap.read_manifest(provider.download(stored.entry.key))["id"] == 2
    assert provider.exists(provider.rival_keys[0])


def test_any_rival_makes_the_pusher_yield_even_with_a_higher_key(zip_builder):
    provider = RacingProvider(races=1, rival_stamp="20990101T000000")
    stored = _store(provider).store_zip(zip_builder)
    assert zip_builder.requested_ids == [1, 2]
    assert stored.entry.snapshot_id == 2


def test_late_rival_yields_to_the_pusher_that_checked_first(zip_builder):
    """A uploads and checks alone, then B's upload lands under the same id
    with a lower-sorting key. B sees A at its check and yields."""
    provider = MemoryProvider()
    first = SnapshotStore(provider, suffix_factory=lambda: "ffffff").store_zip(zip_builder)
    late = SnapshotStore(
        provider, suffix_factory=lambda: "000000", sleep=lambda _: None, random_source=lambda: 0.0
    )
    late._next_free_id = lambda stale=iter([1, 2]): next(stale)  # B listed before A landed
    second = late.store_zip(zip_builder)
    assert first.entry.snapshot_id == 1 and provider.exists(first.entry.key)
    assert second.entry.snapshot_id == 2
    ids = [parse_snapshot_key(k).snapshot_id for k in provider.list_keys("snapshots/")]
    assert sorted(ids) == [1, 2]


class FlakyDeleteProvider(RacingProvider):
    """Loses one race, and its delete fails the first ``failures`` times."""

    def __init__(self, failures: int):
        super().__init__(races=1)
        self.failures_left = failures

    def delete(self, key: str) -> None:
        if self.failures_left > 0:
            self.failures_left -= 1
            raise ConnectionError("network down")
        super().delete(key)


def test_yield_retries_a_failed_delete(zip_builder):
    provider = FlakyDeleteProvider(failures=2)
    sleeps: list[float] = []
    stored = _store(provider, sleeps).store_zip(zip_builder)
    assert stored.entry.snapshot_id == 2
    assert _our_snapshot_keys(provider) == [stored.entry.key]
    assert sleeps == [0.5, 0.5, 0.25]


def test_yield_that_cannot_delete_names_the_leftover_key(zip_builder):
    provider = FlakyDeleteProvider(failures=99)
    with pytest.raises(DuplicateSnapshotIdError) as raised:
        _store(provider).store_zip(zip_builder)
    (leftover,) = _our_snapshot_keys(provider)
    message = str(raised.value)
    assert leftover in message and "duplicated" in message and "pull --key" in message
    assert isinstance(raised.value.__cause__, ConnectionError)


class MutualYieldProvider(MemoryProvider):
    """Another machine uploads the same id at the same moment as our first
    upload. At its own check it sees our object, so it yields too: its object
    shows in exactly one listing (our check) and is then deleted."""

    def __init__(self):
        super().__init__()
        self.rival_key = None
        self.rival_saw_us = None

    def upload(self, key: str, content: bytes) -> None:
        super().upload(key, content)
        if self.rival_key is None and parse_snapshot_key(key) is not None:
            self.rival_key = "snapshots/001_20990101T000000_rival_000000.zip"
            super().upload(self.rival_key, b"rival")

    def list_keys(self, prefix: str = "") -> list[str]:
        keys = super().list_keys(prefix)
        if self.rival_key in keys and self.rival_saw_us is None:
            self.rival_saw_us = sum(1 for k in keys if k.startswith("snapshots/001_")) > 1
            super().delete(self.rival_key)
        return keys


def test_both_pushers_yield_when_they_see_each_other(zip_builder):
    provider = MutualYieldProvider()
    sleeps: list[float] = []
    stored = _store(provider, sleeps).store_zip(zip_builder)
    assert provider.rival_saw_us is True
    assert sleeps == [0.25]
    # Both deleted their id 1 objects; our retry listed again and took id 1 alone.
    assert zip_builder.requested_ids == [1, 1]
    assert provider.list_keys("snapshots/") == [stored.entry.key]
    assert stored.entry.snapshot_id == 1


def test_race_gives_up_after_five_retries_and_cleans_up(zip_builder):
    provider = RacingProvider(races=99)
    sleeps: list[float] = []
    with pytest.raises(SnapshotRaceError, match="Push again"):
        _store(provider, sleeps).store_zip(zip_builder)
    assert zip_builder.requested_ids == [1, 2, 3, 4, 5, 6]
    assert len(sleeps) == 5
    assert _our_snapshot_keys(provider) == []


def test_next_id_is_max_plus_one(zip_builder):
    provider = MemoryProvider()
    provider.upload("snapshots/007_20260101T000000_old.zip", b"zip")
    stored = SnapshotStore(provider).store_zip(zip_builder)
    assert stored.entry.snapshot_id == 8


def test_failed_cache_write_does_not_fail_the_push(zip_builder):
    class BrokenIndexProvider(MemoryProvider):
        def upload(self, key: str, content: bytes) -> None:
            if key == INDEX_KEY:
                raise OSError("disk full")
            super().upload(key, content)

    provider = BrokenIndexProvider()
    stored = SnapshotStore(provider).store_zip(zip_builder)
    assert stored.index_updated is False
    assert provider.exists(stored.entry.key)


def test_encrypting_store_writes_enc_key_and_reads_it_back(zip_builder):
    provider = MemoryProvider()
    cipher = PassphraseCipher("pw")
    store = SnapshotStore(provider, write_cipher=cipher, read_cipher=cipher)
    stored = store.store_zip(zip_builder)
    assert stored.entry.key.endswith(".zip.enc")
    assert stored.entry.encrypted
    manifest = snap.read_manifest(store.fetch_zip(store.find_entry()))
    assert manifest["message"] == "my push"


def test_encrypted_snapshot_without_read_cipher_raises(zip_builder):
    provider = MemoryProvider()
    cipher = PassphraseCipher("pw")
    SnapshotStore(provider, write_cipher=cipher).store_zip(zip_builder)
    reader = SnapshotStore(provider)
    with pytest.raises(PassphraseUnavailableError):
        reader.fetch_zip(reader.find_entry())


# --- duplicate ids on read ------------------------------------------------------

DUPLICATE_A = "snapshots/003_20260101T100000_from-a_aaaaaa.zip"
DUPLICATE_B = "snapshots/003_20260101T100001_from-b_bbbbbb.zip"


def _store_with_duplicates() -> SnapshotStore:
    provider = MemoryProvider()
    provider.upload("snapshots/002_20260101T090000_older_cccccc.zip", b"zip")
    provider.upload(DUPLICATE_A, b"zip a")
    provider.upload(DUPLICATE_B, b"zip b")
    return SnapshotStore(provider)


def test_list_shows_both_duplicates():
    keys = [e.key for e in _store_with_duplicates().list_entries()]
    assert DUPLICATE_A in keys and DUPLICATE_B in keys


@pytest.mark.parametrize("snapshot_id", [3, None], ids=["by-id", "latest"])
def test_duplicate_id_error_lists_both_keys(snapshot_id):
    with pytest.raises(DuplicateSnapshotIdError) as raised:
        _store_with_duplicates().find_entry(snapshot_id=snapshot_id)
    message = str(raised.value)
    assert DUPLICATE_A in message and DUPLICATE_B in message
    assert "--key" in message
    assert "2026-01-01T10:00:00Z" in message


def test_key_selects_one_duplicate():
    store = _store_with_duplicates()
    entry = store.find_entry(key=DUPLICATE_B)
    assert entry.key == DUPLICATE_B
    assert store.fetch_zip(entry) == b"zip b"
