"""ReviewPulse product service: projects, uploads, background jobs, rule review and results (``rp serve``).

Layout: ``store`` keeps projects on disk, ``jobs`` runs long work in the background, ``service`` holds the
operations (all of them reuse pipeline.py, rules/ and report/), ``api`` exposes them over HTTP and serves
the single-page UI in ``static/``.
"""
