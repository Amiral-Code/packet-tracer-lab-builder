# Contributing

## The rule: evidence first

Packet Tracer's file format is undocumented. Nothing goes in on a guess:

1. **Find a real file** that shows the format: an activity, a sample shipped with Packet Tracer, or a file saved for
   the purpose. Record what you saw in `docs/research-evidence.md`, with its source; label inferences as inferences.
2. **Device templates and cards come only from real files** (`ptlab init --source`): never hand-written XML.
3. **Prove the change in Packet Tracer**: build an example, `ptlab verify --values` on Packet Tracer's own save
   (items kept, values identical), then the live check (`ptlab live-prepare`, solve and `--answer`). A behaviour is
   "done" only once seen working live; until then it is listed as pending in `docs/packet-tracer-capabilities.md`.
4. **Keep every example green**: unit tests (`PYTHONPATH=src:tests python3 -m unittest discover -s tests`), lint,
   round trip and live check for all examples, then update the spec reference, the skill and the README.

## Adding a grade statement

- Find the assessment node in a real activity (or in Packet Tracer's own tree: save a `ptlab bare` copy and read its
  `COMPARISONS`), with its path, display name, ID, eclass and value format.
- Add the item kind to `ptlab.PKA_KINDS`, the statement to `labgen.GRADE_STATEMENTS` and `labgen._statement`, a
  local check, its shape check in `validate._statement_problem`, and a hint.
- Prove it with an example: the item must be kept, its value identical to Packet Tracer's, and green after solving.

## Adding a device model

- Add its `(TYPE, model)` to `library.WANT` (or a variant table for fitted cards or optics), and its port names to
  `library.PORT_NAMES` when it has no IOS configuration (Packet Tracer derives port names; read them from links in
  real files).
- Check the template's state: switched on, in the root view, stock settings (no addresses or profiles from the
  source lab). The library resets what it can; anything else is a filter in `library_key`.

## Live checks

`pt-live-check.sh` (Hyprland) is one harness; any harness works that opens the `live-prepare` copy, accepts the
script-privilege prompt and waits for the JSON report. Never stop or move a Packet Tracer the harness did not start.
