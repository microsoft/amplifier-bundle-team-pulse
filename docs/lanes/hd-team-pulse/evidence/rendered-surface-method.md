# How the rendered tool surface was measured

The numbers in `sizes-before-after.md` are not counted from source. They are read
out of a **live mounted Amplifier session** built from a fresh, throwaway
`AMPLIFIER_HOME`, so what is measured is the payload a provider actually receives.

## The scratch home

The owner's `~/.amplifier/settings.yaml` was **read and copied, never moved or
edited** (verified by md5 before and after). Its 20-entry `bundle.app` list was
deep-copied into a new settings file; the single `team-pulse` git entry was
swapped for this working checkout so the edits under test are the ones mounted.
Nothing else was changed, and the owner's cache was never written to.

```python
owner = yaml.safe_load(open('~/.amplifier/settings.yaml'))
app   = copy.deepcopy(owner['bundle']['app'])          # COPY of the app list
app   = [a for a in app if 'team-pulse' not in a]
app.append(f"file://{REPO}#subdirectory=behaviors/team-pulse.yaml")
Path('/tmp/hdtp/amp-home/settings.yaml').write_text(yaml.safe_dump({'bundle': {'app': app}}))
```

Result: 20 app entries in, 20 out. 86 tools mounted, 12 of them `team_pulse_*`.

## The dump

`render_surface.py` (in this directory) mirrors
`amplifier_app_cli.commands.tool._get_mounted_tools_from_bundle_async`, but emits
each tool's full `{name, description, input_schema}` instead of a one-line
summary. `amplifier tool info` was tried first and rejected: it prints mount
metadata and never the description, so it cannot measure this.

```bash
AMPLIFIER_HOME=/tmp/hdtp/amp-home \
  ~/.local/share/uv/tools/amplifier/bin/python render_surface.py surface-before.json
# ... apply the change ...
AMPLIFIER_HOME=/tmp/hdtp/amp-home \
  ~/.local/share/uv/tools/amplifier/bin/python render_surface.py surface-after.json
```

Because the scratch home mounts the checkout by `file://`, the second run picks
up the edited descriptions live -- same 86 tools, same schemas, only the 12
team-pulse `description` strings differ.

`rendered-surface-before.json` and `rendered-surface-after.json` are the
team-pulse slices of those two dumps, verbatim.

## Note on the 10,624-char figure in the goal

Measured here: the 12 `description` strings total **6,144** chars; the rendered
surface (name + description + `input_schema` JSON) totals **10,317**. The goal's
10,624 is the rendered figure, not the descriptions alone -- the ~300-char gap is
serialization whitespace. Both numbers are reported so neither reading is
ambiguous.
