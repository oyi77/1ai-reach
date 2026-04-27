"""Legacy scripts bridge package.

Centralizes all `scripts/` module imports so that `src/` code never
touches `sys.path.insert` directly. Each sub-module adds `scripts/`
to `sys.path` once (idempotently) and re-exports the legacy symbols.

Usage:
    from oneai_reach.infrastructure.legacy.state_manager import search_kb
    from oneai_reach.infrastructure.legacy.brain_client import search, add
    from oneai_reach.infrastructure.legacy.senders import send_email, send_whatsapp

MIGRATION PATH:
  Phase 1 (now): src/ files import from legacy/ instead of sys.path.insert
  Phase 2: Move actual logic into infrastructure/ packages
  Phase 3: Delete legacy/ entirely
"""