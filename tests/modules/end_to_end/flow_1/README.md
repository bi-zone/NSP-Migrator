# Flow 1 — Cisco ASA migration workflow

This directory owns one backend workflow acceptance test.  It starts with a
CSP profile and a Cisco ASA artifact, creates a canonical snapshot, maps three
policies, resolves intentionally ambiguous and unresolved mapping results,
prepares an execute plan, and pushes only the new policy.  It then reads the
saved report and its policy snapshots through the Reports application API,
including a comparison of the pushed-policy snapshot with the policy sent to
SD-WAN.

The test uses the real application DI graph, PostgreSQL-backed modules, and
runtime-cache adapters. `fake_sdwan.py` is the sole external boundary: it is a
stateful in-process implementation of the SD-WAN client contract. It has a
fixed catalog and persists policies created during the test, so the scenario is
deterministic and never calls an external service.
