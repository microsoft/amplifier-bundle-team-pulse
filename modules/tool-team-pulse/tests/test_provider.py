# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for _ClientProvider — cached, lazily-built, context-entered client."""

from __future__ import annotations

from amplifier_module_tool_team_pulse.tool import _ClientProvider


class _FakeClient:
    """Minimal async-context-manager stand-in for TeamPulseClient."""

    def __init__(self) -> None:
        self.entered: int = 0
        self.exited: int = 0

    async def __aenter__(self) -> "_FakeClient":
        self.entered += 1
        return self

    async def __aexit__(self, *_: object) -> None:
        self.exited += 1


async def test_provider_builds_once_and_reuses() -> None:
    """build is awaited once; both calls to client() return the same instance."""
    fake = _FakeClient()
    build_calls = 0

    async def build() -> _FakeClient:
        nonlocal build_calls
        build_calls += 1
        return fake

    provider = _ClientProvider(build)

    first = await provider.client()
    second = await provider.client()

    assert build_calls == 1, "build should only be called once"
    assert fake.entered == 1, "context should be entered exactly once"
    assert first is fake
    assert second is fake


async def test_provider_aclose_exits_context() -> None:
    """aclose exits the context exactly once; second aclose is a no-op."""
    fake = _FakeClient()

    async def build() -> _FakeClient:
        return fake

    provider = _ClientProvider(build)
    await provider.client()  # build and enter context

    await provider.aclose()
    assert fake.exited == 1

    # Second aclose is idempotent — should not exit again
    await provider.aclose()
    assert fake.exited == 1, "second aclose should not exit again"


async def test_provider_aclose_before_build_is_noop() -> None:
    """aclose before any client() call does not raise."""

    async def build() -> _FakeClient:
        return _FakeClient()

    provider = _ClientProvider(build)
    # Must not raise
    await provider.aclose()


async def test_provider_reset_rebuilds_next_call() -> None:
    """reset() closes the current client; next client() call rebuilds with a new one."""
    first_fake = _FakeClient()
    second_fake = _FakeClient()
    clients = [first_fake, second_fake]
    call_index = 0

    async def build() -> _FakeClient:
        nonlocal call_index
        c = clients[call_index]
        call_index += 1
        return c

    provider = _ClientProvider(build)

    first = await provider.client()
    assert first is first_fake

    await provider.reset()
    assert first_fake.exited == 1, "reset should have closed the first client"

    second = await provider.client()
    assert second is second_fake, "should rebuild with a new client after reset"
