# Releasing

corridor-ci lives in a monorepo, so its release tags carry a `corridor-ci-`
prefix: immutable releases are `corridor-ci-vX.Y.Z`, and the floating major
tag is `corridor-ci-vX`.

1. Update `README.md` and `examples/workflow.yml` to the new major tag first,
   so the tagged tree references itself.
2. Publish an immutable `corridor-ci-vX.Y.Z` tag.
3. Move the matching major tag, such as `corridor-ci-v12`, to that release.
4. Create a GitHub release on the `corridor-ci-vX.Y.Z` tag and mark it as
   latest (`gh release create corridor-ci-vX.Y.Z --latest`); tags alone do
   not update the Releases page.

Consistency is enforced twice: the test suite keeps `README.md` and
`examples/workflow.yml` on the same tag, and a CI job on `corridor-ci-v*`
tag pushes verifies the tagged tree references its own major tag.

Releases `v10` and earlier live in the original standalone repository,
`shihchengwei-lab/corridor-ci`, and keep working for existing users.
