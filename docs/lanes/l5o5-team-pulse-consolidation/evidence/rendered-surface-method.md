# How the rendered tool surface was measured

The numbers in `sizes-before-after.md` are not counted from source. They are read
out of a **live mounted Amplifier session** built from a fresh, throwaway
`AMPLIFIER_HOME`, so what is measured is the payload a provider actually receives.

## The scratch home

The owner's `~/.amplifier/settings.yaml` was **read and copied, never written**
(md5 log and a disclosure in `owner-settings-md5.txt`). Its 20-entry
`bundle.app` list was deep-copied into a new settings file; the single
`team-pulse` git entry was swapped for this working checkout so the edits under
test are the ones mounted. Nothing else was changed.

```python
owner = yaml.safe_load(open('~/.amplifier/settings.yaml'))
app   = copy.deepcopy(owner['bundle']['app'])          # COPY of the app list
app   = [a for a in app if 'team-pulse' not in a]
app.append(f"file://{REPO}#subdirectory=behaviors/team-pulse.yaml")
Path('/tmp/l5o5/amp-home/settings.yaml').write_text(yaml.safe_dump({'bundle': {'app': app}}))
```

Result: 20 app entries in, 20 out. 86 tools mounted before, 77 after — a
difference of exactly 9, which is entirely the 12 -> 3 team-pulse change.

## The dump

`render_surface.py` (in this directory, carried over from the `hd-team-pulse`
lane) mirrors `amplifier_app_cli.commands.tool._get_mounted_tools_from_bundle_async`
but emits each tool's full `{name, description, input_schema}` instead of a
one-line summary. `amplifier tool info` was rejected for this: it prints mount
metadata and never the description, so it cannot measure this.

```bash
AMPLIFIER_HOME=/tmp/l5o5/amp-home \
  ~/.local/share/uv/tools/amplifier/bin/python render_surface.py surface-before.json
# ... apply the change ...
AMPLIFIER_HOME=/tmp/l5o5/amp-home \
  ~/.local/share/uv/tools/amplifier/bin/python render_surface.py surface-after.json
```

`rendered-surface-before.json` and `rendered-surface-after.json` are the
team-pulse slices of those two dumps, verbatim.

## The formula

`rendered = len(name) + len(description) + len(json.dumps(input_schema, ensure_ascii=False))`

Both sides use this one formula on one machine, so the delta is apples-to-apples.
The absolute figure is only comparable to another figure produced the same way —
see the closing note in `sizes-before-after.md` about the 9,967 / 10,317 / 10,624
readings of the same 12 tools.

## Regression guard

`tests/test_consolidated_surface.py::test_rendered_surface_is_within_budget`
recomputes the same formula against `mount()`'s own output and fails above 4,000
chars, so the surface cannot silently regrow without a live session to notice it.
