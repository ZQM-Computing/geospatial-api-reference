# Public API security boundaries

## Intended exposure

This repository is an educational reference implementation. The current FastAPI application does **not** implement user authentication, authorization, API keys, tenant isolation, or per-collection access policy. Its collection and feature routes are readable by any client that can reach the listening interface.

The default `uvicorn app.main:app --reload` quick start is for local development. The Docker Compose example binds both the API and database ports to `127.0.0.1`, but loopback binding is a local-demo guardrail, not an application authorization system. Network topology, reverse proxies, port forwarding, and deployment platform settings can change exposure.

**Do not expose this reference service or its PostGIS-backed mode to an untrusted network or use it to serve sensitive data without first implementing and independently testing the required authentication, authorization, and network controls.** Do not interpret the existence of OpenAPI documentation or passing functional tests as evidence of access control.

## Before a real deployment

Document and test each of the following against the actual deployment:

1. **Identity:** Define the trusted identity provider and token/session validation requirements. Reject missing, expired, malformed, and incorrectly signed credentials.
2. **Authorization:** Specify whether access is public, role-based, tenant-based, or collection/feature-level. Enforce policy server-side on every protected route; do not rely on hidden UI links or client-supplied identity headers.
3. **Database least privilege:** Use a dedicated database role with only the required read permissions. Do not use PostgreSQL superuser or broad write credentials for a read API.
4. **Network boundary:** Restrict the API and database to intended interfaces and trusted networks. Ensure the database is not reachable from the public internet; verify actual cloud firewall, tunnel, proxy, and port-forwarding rules rather than inferring exposure from Compose alone.
5. **Transport and proxy trust:** Require HTTPS for remote clients. Configure trusted proxy hops explicitly, strip untrusted forwarded/identity headers, and test direct-origin access and alternate routes.
6. **Data minimization:** Review every returned field and geometry for sensitive information. Apply row/field filtering before serialization and pagination.
7. **Abuse controls:** Add request limits, timeouts, rate limiting, audit logging, and monitoring appropriate to the threat model. Avoid logging credentials or sensitive feature payloads.
8. **Negative tests:** Verify anonymous requests are denied where required; users cannot cross tenant or collection boundaries; revoked/expired tokens fail; direct-origin requests cannot bypass the proxy; and database errors do not disclose secrets or connection details.
9. **Deployment evidence:** Record the deployed commit, image digest, effective routes, environment configuration, and test results. Local unit tests are not evidence that deployed controls are active.

## What the current tests prove

The existing sample-backend tests exercise route behavior, filtering, pagination, and error cases. They do not prove authentication, authorization, network isolation, database least privilege, OGC conformance, or security of a deployed service. The PostGIS integration suite should likewise be treated as integration evidence only for the environment and cases it actually runs.

Keep secrets outside source control. Use synthetic data in examples and CI.
