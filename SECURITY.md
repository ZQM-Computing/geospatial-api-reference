# Security policy

## Supported version

Security fixes are applied to the `main` branch. This repository is a reference implementation, not a hosted service.

## Reporting a vulnerability

Email **zqmcomputing@gmail.com** with the subject `geospatial-api-reference security` if you find a vulnerability in the service code or workflow configuration. Please do not open a public issue for a sensitive report.

Include the affected file or endpoint, the impact you observed, and reproduction steps when available.

## Deployment note

The defaults in this repository are for local demonstration: the sample backend needs no credentials, and the Docker Compose database is a disposable demo instance. Do not expose a deployment built from these defaults to a network you do not control without adding authentication in front of the API, real database credentials, and TLS — the code intentionally ships without an auth layer so the OGC surface stays readable, which makes the deployment boundary your responsibility.
