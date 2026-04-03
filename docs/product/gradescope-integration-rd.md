# Gradescope Integration R&D (Deferred)

Status: deferred until Canvas integration and production auth are complete.

## Goal

Ingest assignment/exam grades and submission status from Gradescope.

## Prerequisites

- Stable source-of-truth mapping for courses/tasks.
- Secure credential/token handling.
- User-consented third-party integration UX.

## Initial plan

1. Investigate supported API/auth options.
2. Model mapping: Gradescope items -> internal tasks + grade events.
3. Incremental sync and reconciliation job design.

## Risks

- API availability and unofficial endpoints.
- Terms-of-service and rate-limit constraints.
