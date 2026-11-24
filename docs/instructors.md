# For instructors

## From a topic to a class set

```bash
ptlab recipes                                        # proven labs by topic, level, kind and time
ptlab new static-routing work/routing-week3.toml     # a fresh copy with new addressing; edit the story and steps
ptlab lint work/routing-week3.toml                   # spec check + self-check: the answer scores full marks, the start does not
ptlab troubleshoot work/routing-week3.toml work/routing-week3-ts.toml --faults 3   # a troubleshooting version
ptlab variants work/routing-week3.toml --count 30 --output-dir work/class --build  # one re-addressed lab per student
```

Each built lab comes with an `-answer.md` key: the scenario, the reference configuration, every graded item and,
for troubleshooting labs, each fault with its symptom and explanation.

## Grading

Students submit their saved `.pka`. Packet Tracer's own Check Results is what they see; for the class:

```bash
ptlab grade work/class submitted/      # grades.csv and grades.html: per student, per check, per variant
```

`ptlab grade` uses the lab's local checks on each student's network; with a folder of variants every file is graded
against the variant it matches.

## Before a lab goes out

Prove it once in Packet Tracer (see the README): `ptlab verify` on a saved copy shows Packet Tracer kept every item
with the right value, and the live check shows Packet Tracer itself solves it to full marks. The shipped recipes are
already proven; a lab you changed should be proven again.

## When Packet Tracer is not enough

`ptlab gns3 SPEC OUT.toml` compiles a lab for a GNS3 engine (IOU routers and switches, VPCS hosts), for topics
Packet Tracer cannot run. Serial WAN links export to IOU serial ports. Labs with ASAs, home gear or wireless stay in Packet Tracer.
