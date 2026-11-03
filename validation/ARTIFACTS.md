# Validation sources and generated evidence

Reproduction scripts, requirements, migration scope and narrative reports are
versioned. JSON/XML results, logs, coverage databases, distributions and source
ZIPs are generated locally and remain outside Git. They are preserved in the
workspace; the delivered Issue 17.1 source archive includes the complete evidence.

The reports are historical snapshots of their validation checkpoints. Their
“No commits” statements describe the time those checks ran, before the later
request to commit the changes. Links to generated diagnostics resolve after
running the corresponding validation tools or unpacking the delivered archive.

The current checkpoint is `issue17-1/REPORT.md`. Its supported Python range is
3.11–3.15; earlier 3.9/3.10 exploration is retained only as historical evidence.
