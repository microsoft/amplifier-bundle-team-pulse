"""Dump the RENDERED tool surface (name + description + input_schema) for a bundle.

Mirrors amplifier_app_cli.commands.tool._get_mounted_tools_from_bundle_async, but
emits the full provider-facing payload rather than a one-line summary.

Usage: python render_surface.py <out.json>   (honours AMPLIFIER_HOME)
"""
from __future__ import annotations
import asyncio, json, sys
from pathlib import Path


async def main(out_path: str) -> None:
    from amplifier_app_cli.lib.settings import AppSettings
    from amplifier_app_cli.runtime.config import resolve_config_async, inject_user_providers
    from amplifier_app_cli.console import console

    app_settings = AppSettings()
    config, prepared = await resolve_config_async(
        bundle_name=None, app_settings=app_settings, console=console
    )
    assert prepared is not None
    inject_user_providers(config, prepared)
    session = await prepared.create_session(session_cwd=Path.cwd())
    await session.initialize()
    try:
        tools = session.coordinator.get("tools") or {}
        rows = []
        for name, inst in sorted(tools.items()):
            desc = getattr(inst, "description", "") or ""
            schema = getattr(inst, "input_schema", None)
            try:
                schema = dict(schema) if schema else {}
            except Exception:
                schema = {}
            rows.append({"name": name, "description": desc, "input_schema": schema})
        Path(out_path).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {len(rows)} tools -> {out_path}")
    finally:
        try:
            await asyncio.wait_for(session.cleanup(), timeout=30)
        except Exception:
            pass


asyncio.run(main(sys.argv[1]))
