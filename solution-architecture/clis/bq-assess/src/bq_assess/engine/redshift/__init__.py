"""Redshift Serverless Query Engine: Serverless RPU + S3 storage cost, rewrite guidance, placement.

The Query Engine is Redshift Serverless over the Iceberg Storage Target (ADR-0001): no node
sizing, no DISTKEY/SORTKEY, no provisioned-vs-serverless advisor. See
``.kiro/specs/phase1-assessment-tool/SCRUM_NOTES.md`` for the #2 restructure decision.
"""
