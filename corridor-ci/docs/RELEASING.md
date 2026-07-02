# Releasing

Use semver tags for releases.

1. Update `README.md` and `examples/workflow.yml` to the new major tag first,
   so the tagged tree references itself.
2. Publish an immutable `vX.Y.Z` tag.
3. Move the matching major tag, such as `v9`, to that release.
4. Create a GitHub release on the `vX.Y.Z` tag and mark it as latest
   (`gh release create vX.Y.Z --latest`); tags alone do not update the
   Releases page.

Consistency is enforced twice: the test suite keeps `README.md` and
`examples/workflow.yml` on the same tag, and a CI job on tag pushes verifies
the tagged tree references its own major tag.
