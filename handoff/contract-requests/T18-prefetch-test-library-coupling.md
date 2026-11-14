# T18: `tests/unit/pricing/test_prefetch.py` assumes the library has exactly one MPN

**What:** `test_prefetch_writes_cache_with_fetched_at` (T16, merged) calls `prefetch()`, which reads the
real `load_library()` and maps the single mocked Nexar result to the *first sorted* MPN. It asserts that MPN
is `ESP32-DEVKITC-32E`. T18 adds parts with MPNs (Adafruit `1643`, `3006`, `381`, `3968`, Seeed `103020005`,
`113991115`, `DFR0440`, `OBSF-30`, `PTS645SL43-2LFS`, `SG90`), so `103020005` sorts first and the test fails:

    AssertionError: assert {'103020005': [...]} == {'ESP32-DEVKITC-32E': [...]}

**Fix (one line in a file T18 doesn't own):** pin the library in the test, e.g.

    monkeypatch.setattr(prefetch_prices, "load_library",
                        lambda: PartLibrary({"esp32_devkitc": load_library().get("esp32_devkitc")}))

(or assert on `sorted(mpns)[0]` instead of a literal).

**Who it affects:** T16's test only; no contract or behaviour change. T18 can't merge with `make test` green
until this lands (or the Integrator applies it while merging T18).
