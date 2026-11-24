"""Batch grading of saved student activities: one CSV and one HTML report for a whole class.

Each saved .pka is graded with the lab's local checks (the same as `ptlab check`) on the student's network. With a
folder of variant specs (`ptlab variants`), every file is graded against each variant and reported with the one it
matches best, so each student is marked on their own addressing.
"""
import csv
import html
from pathlib import Path
import xml.etree.ElementTree as ET

from . import labgen, ptlab


def _student_tree(path):
    tree = ptlab.read_pkt(str(path))
    if tree.getroot().tag == "PACKETTRACER5_ACTIVITY":
        student = tree.getroot().find("PACKETTRACER5")
        if student is None:
            raise ValueError("no student network")
        tree = ET.ElementTree(student)
    return tree


def grade_file(specs, path):
    """(spec id, [(check description, ok)]) for the spec this file matches best."""
    tree = _student_tree(path)
    best = None
    for spec in specs:
        _, checks = labgen.compile_grade(spec)
        res = ptlab.grade({"check": checks}, tree, checks, quiet=True)
        if best is None or sum(res) > sum(best[1]):
            best = (spec["_id"], [ok for ok in res], [c["desc"] for c in checks])
    sid, res, descs = best
    return sid, list(zip(descs, res))


def grade_dir(spec_path, folder):
    spec_path = Path(spec_path)
    paths = sorted(spec_path.glob("*.toml")) if spec_path.is_dir() else [spec_path]
    specs = [labgen.load_spec(str(p)) for p in paths]
    rows = []
    for f in sorted(Path(folder).glob("*.pka")):
        try:
            sid, results = grade_file(specs, f)
            rows.append({"student": f.stem, "variant": sid, "results": results, "error": ""})
        except Exception as e:                      # an unreadable file is reported, not fatal
            rows.append({"student": f.stem, "variant": "", "results": [], "error": str(e)})
    return rows


def write_reports(rows, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    checks = []
    for r in rows:
        for d, _ in r["results"]:
            if d not in checks:
                checks.append(d)
    with open(out / "grades.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["student", "variant", "score", "total", "percent"] + checks + ["error"])
        for r in rows:
            got = dict(r["results"])
            score, total = sum(got.values()), len(got)
            w.writerow([r["student"], r["variant"], score, total, f"{100 * score / total:.0f}" if total else ""]
                       + [("ok" if got[c] else "FAIL") if c in got else "" for c in checks] + [r["error"]])
    head = "".join(f"<th title='{html.escape(c)}'>{i + 1}</th>" for i, c in enumerate(checks))
    body = []
    for r in rows:
        got = dict(r["results"])
        score, total = sum(got.values()), len(got)
        cells = "".join(f"<td class='{'ok' if got[c] else 'no'}'>{'&#10003;' if got[c] else '&#10007;'}</td>"
                        if c in got else "<td></td>" for c in checks)
        pct = f"{100 * score / total:.0f}%" if total else html.escape(r["error"])
        body.append(f"<tr><th>{html.escape(r['student'])}</th><td>{html.escape(r['variant'])}</td>"
                    f"<td class='n'>{score}/{total}</td><td class='n'>{pct}</td>{cells}</tr>")
    per_check = []
    for i, c in enumerate(checks):
        n = sum(1 for r in rows if dict(r["results"]).get(c))
        per_check.append(f"<li><b>{i + 1}.</b> {html.escape(c)} <span>{n}/{len(rows)} students</span></li>")
    (out / "grades.html").write_text(f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Lab grades</title><style>
:root {{ --bg: #fff; --fg: #1b1b1f; --ok: #1a7f37; --no: #c62828; --line: #ddd; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #16161a; --fg: #e8e8ec; --ok: #5bd17a; --no: #ff7b72; --line: #333; }} }}
body {{ background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, sans-serif; margin: 16px; }}
table {{ border-collapse: collapse; overflow-x: auto; display: block; }}
th, td {{ border: 1px solid var(--line); padding: 4px 8px; text-align: center; }}
th:first-child {{ text-align: left; }} .ok {{ color: var(--ok); }} .no {{ color: var(--no); }} .n {{ white-space: nowrap; }}
li span {{ opacity: .7; margin-left: 8px; }}
</style></head><body><h1>Lab grades</h1><p>{len(rows)} student files, {len(checks)} checks.</p>
<table><tr><th>Student</th><th>Variant</th><th>Score</th><th>%</th>{head}</tr>{''.join(body)}</table>
<h2>Checks</h2><ol style="list-style:none;padding:0">{''.join(per_check)}</ol></body></html>""", encoding="utf-8")
    return out / "grades.csv", out / "grades.html"
