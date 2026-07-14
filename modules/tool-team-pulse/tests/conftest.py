# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Shared fixtures for the tool-team-pulse test suite.

The shim mocks the library client directly via AsyncMock — no HTTP, no
base-url configuration, no real network calls.  Consequently this conftest
needs no HTTP/base-url fixtures; those lived in the old test files that have
been removed (test_client.py, test_endpoint_config.py, test_submit_answer.py,
test_ask.py, test_ask_guidance.py, test_collections.py).

The remaining shim suite is:
    test_provider.py
    test_read_tools.py
    test_submit_answer_shim.py
    test_status.py
    test_configure.py
    test_mount.py
"""

from __future__ import annotations
