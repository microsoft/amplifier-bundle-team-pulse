"""Scaffold smoke test — verifies the package imports and exposes __version__."""


def test_package_imports_and_has_version() -> None:
    import team_pulse_lib

    assert team_pulse_lib.__version__ == "0.1.0"
