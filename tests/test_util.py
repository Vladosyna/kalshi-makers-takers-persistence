

# ---------------------------------------------------------------------------
# keep_system_awake -- guards against a failure that produced no error at all:
# Modern Standby froze a healthy-looking collector for ~22 of every 25 hours.
# ---------------------------------------------------------------------------

def test_keep_system_awake_yields_and_never_raises():
    from kalshi_mt.util import keep_system_awake

    with keep_system_awake("unit test") as held:
        assert isinstance(held, bool)


def test_keep_system_awake_survives_a_failing_api(monkeypatch):
    """A collector that refuses to run without a wake lock is worse than one
    that might be paused, so an API failure must not propagate."""
    import sys as _sys

    from kalshi_mt import util

    if _sys.platform != "win32":
        with util.keep_system_awake("unit test") as held:
            assert held is False
        return

    import ctypes

    class _Boom:
        def SetThreadExecutionState(self, _flags):  # noqa: N802 - mirrors the Win32 name
            raise OSError("simulated failure")

    monkeypatch.setattr(ctypes, "windll", type("W", (), {"kernel32": _Boom()})())
    with util.keep_system_awake("unit test") as held:
        assert held is False


def test_keep_system_awake_releases_the_request_on_exit(monkeypatch):
    import sys as _sys

    if _sys.platform != "win32":
        return

    import ctypes

    from kalshi_mt import util

    calls = []

    class _Recorder:
        def SetThreadExecutionState(self, flags):  # noqa: N802 - mirrors the Win32 name
            calls.append(flags)
            return 1

    monkeypatch.setattr(ctypes, "windll", type("W", (), {"kernel32": _Recorder()})())
    with util.keep_system_awake("unit test"):
        pass
    # Last call must be bare ES_CONTINUOUS -- clearing the request rather than
    # leaving the machine unable to sleep after the fetch is over.
    assert calls[-1] == 0x80000000
