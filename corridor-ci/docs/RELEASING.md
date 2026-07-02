# Releasing

Use semver tags for releases.

1. Publish an immutable `vX.Y.Z` tag.
2. Move the matching major tag, such as `v8`, to that release.
3. Keep `README.md` and `examples/workflow.yml` on the same major tag.

The tag consistency is enforced by the test suite.
