# Contributing

Thanks for helping improve this reference implementation.

## Principles for contributions

1. **The repository interface is the contract.** New data sources belong behind `app/repository.py`'s contract, not in the routes.
2. **Tests must keep running without a database.** Anything that needs PostGIS gets a sample-backend equivalent or a clearly separated integration test.
3. **Follow the standard, or document the deviation.** If a response shape departs from OGC API – Features, the PR description and `docs/ogc-notes.md` should say why.
4. **No real data.** Examples and fixtures stay synthetic — no real parcel, utility, customer, or sensitive location data.

## Workflow

- Run `pytest` before opening a pull request.
- Keep routes thin: validation and response shaping in `app/main.py`, data access in the repository.
- New collections register in `COLLECTIONS` (repository) plus schema/fixtures as needed.
