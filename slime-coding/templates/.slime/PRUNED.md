# Pruned Paths

Append-only log of rejected designs. Do not revive a record without new
evidence. The injection hook re-surfaces records tied to the current corridor
plus the most recent few; older ones stay here for the record. Use /slime-prune
to add entries.

## [2026-01-01] corridor:example-feature
**Pruned:** Pulling in a state-management package for one screen of state.
**Reason:** Adds a dependency; the existing ChangeNotifier seam already covers
this corridor. No attachment point justifies the new surface.
**Revive only if:** the feature grows to multiple screens sharing state.
