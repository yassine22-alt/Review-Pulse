"""Connectors: how ReviewPulse findings enter, and come back from, the systems reviewers and engineers already use.

One neutral model (`ReviewComment`) and one adapter per route: standard PDF markups (Bluebeam Revu and others), BCF 2.1,
Accela Document Review, Bluebeam Studio, OpenGov step comments, and JSON, CSV, drop folder and signed webhook for offices
without an API. The vendor connectors are contract tested from documentation, not tested live.
"""

from .model import ReviewComment, from_findings, json_schema

__all__ = ["ReviewComment", "from_findings", "json_schema"]
