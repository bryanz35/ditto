from backend.contracts.spec import UserContext
from backend.memory.store import MemoryStore


def test_empty_store_gives_default_user_context(tmp_path):
    assert MemoryStore(tmp_path / "m.sqlite3").load() == UserContext()


def test_save_and_load_round_trip_survives_reopen(tmp_path):
    path = tmp_path / "m.sqlite3"
    user = UserContext(
        budget_usd=30.0,
        owned={"esp32_devkitc": 2, "buzzer_passive": 1},
        printer="generic",
        rejected=["no buzzers", "smaller case"],
    )
    assert MemoryStore(path).save(user) == user
    assert MemoryStore(path).load() == user


def test_save_replaces_everything_and_drops_zero_quantities(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    store.save(UserContext(budget_usd=10, owned={"esp32_devkitc": 1}, rejected=["a"]))
    saved = store.save(UserContext(owned={"esp32_devkitc": 0, "buzzer_passive": 3}))
    assert saved == UserContext(owned={"buzzer_passive": 3})
