# Validation record

Date: October 17, 2026

## Performed

- Python 3.12.14, Linux development environment.
- `python -m pytest -q`: **23 passed**, 0 failed.
- `node --check app/static/app.js`: passed JavaScript syntax validation.
- TestClient HTTP coverage includes root document, create/edit, photo upload, comparable review, jobs and catalogue export.
- Original photo preservation and atomic rollback for a partially invalid upload batch.
- Duplicate image hashes skipped; duplicate research jobs reuse the active job.
- Stale record versions reject writes; completed model jobs do not overwrite human edits.
- Research errors and invalid provider responses do not become empty-market results.
- Restarted jobs become interrupted without resending an external request.
- Asking prices, foreign currencies, unreviewed comps and stale sales are excluded from the USD observed-price summary.
- Invalid prices, future dates and unsafe source URL schemes are rejected.
- Source-query cache and local monthly request cap tested against a mock transport.
- Cross-origin writes, missing mutation headers and unexpected Host headers rejected.
- Provider credentials excluded from public status and catalogue export.

## Limits

- No real garments were supplied during implementation. Fixture images are synthetic test inputs, not model benchmarks.
- No Ollama instance was available in this environment. Vision requests were contract-tested with fake responses, not run against the selected model.
- No sold-provider key was available. CompsAPI integration is an optional, unverified live adapter. No actual sales were fetched or assessed.
- No browser interaction or screenshot QA was performed. UI syntax and server routes were checked; visual layout, camera/phone behavior, clipboard behavior and cross-browser accessibility still need a browser pass.
- Neither Mac M2 nor Windows/RTX 5080 execution was tested here. Both setup paths are documented, not proven on those machines.
- No cross-listing, marketplace connection, automatic sale sync or public deployment is included.
- Test output contains one upstream deprecation warning: the installed Starlette version recommends `httpx2` for its test client. The tested httpx transport still passed; no compatibility rewrite was made for a passing prototype.
- A single process is required. The thread-based worker is not a distributed queue; use one uvicorn worker, and do not expose the service publicly.

The test count is evidence of the specific contracts above, not a claim of model accuracy, pricing accuracy, security certification, or production readiness.
