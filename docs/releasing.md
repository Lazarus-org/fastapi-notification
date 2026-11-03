# Releasing fastapi-notification

The release workflow builds and checks the package, runs the complete reusable
CI workflow, and publishes the verified distributions through PyPI Trusted
Publishing. It uses the existing Poetry lockfile and does not require a PyPI API
token. Publication is disabled while `PYPI_PUBLISH_ENABLED` is unset or false.

## One-time configuration

1. Create a GitHub environment named `pypi`. Configure required reviewers and tag
   deployment restrictions. Merely referencing the environment in YAML does not
   configure approval protection. Confirm that the repository's GitHub plan
   supports the chosen protection rules.
2. Register a Trusted Publisher on PyPI for the actual GitHub repository owner,
   repository name, workflow filename `release.yml`, and environment `pypi`.
   Use a pending publisher for a project that has not yet been created on PyPI.
3. After verifying those settings, set the **repository variable**
   `PYPI_PUBLISH_ENABLED` to the exact string `true`.

See the official [PyPI Trusted Publishing guide](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
and [GitHub environment configuration](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

## Release procedure

1. Review and merge the release changes. Keep the Poetry and Commitizen versions
   aligned in `pyproject.toml`, and finalize the changelog. The current intended
   release remains `1.0.0`.
2. Run `python scripts/check_packaging.py` and `poetry check --lock`.
3. A manual workflow dispatch on a branch runs validation and builds artifacts
   without publishing. Use this to check the workflow before creating a tag.
4. Create and push the matching release tag, for example `v1.0.0`, when ready.
   The tag triggers the release workflow. A mismatched tag fails before upload.
5. Wait for `verify-and-build` and `test-release` to pass, then review the `pypi`
   environment deployment. Approve publication when the artifacts and CI are ready.
6. Verify installation from PyPI and prepare the GitHub release notes separately.
   This workflow does not create GitHub releases or modify repository contents.

The publishing job downloads the exact artifact ID produced by the build job;
it does not check out source or rebuild packages. Only that job receives
`id-token: write`. Twine runs in a separate verification environment to avoid
conflicting with the project's Sphinx/docutils development dependencies.
The release build job also runs the clean-wheel smoke test on that artifact.
Reusable CI skips its duplicate distribution job for release calls; normal
push/PR CI continues to build and check distributions itself.

Before migrating existing digest batch tables, stop digest workers and review
the reference migrations in `migrations/README.md` for the host application's
revision chain. Migration and worker deployment are application responsibilities.
