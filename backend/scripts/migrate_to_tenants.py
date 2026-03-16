"""
Data migration script: move legacy uploads to tenant-scoped directories.

Legacy layout (pre-SaaS):
  uploads/simulations/{sim_id}/          -- simulation directories
  uploads/projects/{project_id}/         -- project directories

New tenant layout:
  uploads/tenants/{tenant_id}/data/simulations/{sim_id}/
  uploads/tenants/{tenant_id}/data/projects/{project_id}/

Orphaned data (tenant cannot be determined):
  uploads/_orphaned/simulations/{sim_id}/
  uploads/_orphaned/projects/{project_id}/

Usage:
  python migrate_to_tenants.py            # dry-run (no files moved)
  python migrate_to_tenants.py --execute  # actually move files
"""

import argparse
import json
import logging
import os
import shutil
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("migrate_to_tenants")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _uploads_dir() -> str:
    """Absolute path to the uploads directory (backend/uploads)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "uploads")


def _legacy_simulations_dir() -> str:
    return os.path.join(_uploads_dir(), "simulations")


def _legacy_projects_dir() -> str:
    return os.path.join(_uploads_dir(), "projects")


def _tenants_dir() -> str:
    return os.path.join(_uploads_dir(), "tenants")


def _orphaned_dir() -> str:
    return os.path.join(_uploads_dir(), "_orphaned")


def _tenant_sim_dir(tenant_id: str, sim_id: str) -> str:
    return os.path.join(_tenants_dir(), tenant_id, "data", "simulations", sim_id)


def _tenant_project_dir(tenant_id: str, project_id: str) -> str:
    return os.path.join(_tenants_dir(), tenant_id, "data", "projects", project_id)


def _orphaned_sim_dir(sim_id: str) -> str:
    return os.path.join(_orphaned_dir(), "simulations", sim_id)


def _orphaned_project_dir(project_id: str) -> str:
    return os.path.join(_orphaned_dir(), "projects", project_id)


# ---------------------------------------------------------------------------
# Tenant discovery
# ---------------------------------------------------------------------------

def _list_tenant_ids() -> list:
    """Return all tenant IDs present in uploads/tenants/."""
    tenants_dir = _tenants_dir()
    if not os.path.isdir(tenants_dir):
        return []
    return [
        d for d in os.listdir(tenants_dir)
        if os.path.isdir(os.path.join(tenants_dir, d))
    ]


def _build_project_to_tenant_map() -> dict:
    """
    Scan all tenant project directories and build a mapping
    {project_id -> tenant_id} for quick lookup.

    This covers projects that were already migrated or created directly
    under a tenant.
    """
    mapping: dict = {}
    for tenant_id in _list_tenant_ids():
        projects_root = os.path.join(_tenants_dir(), tenant_id, "data", "projects")
        if not os.path.isdir(projects_root):
            continue
        for project_id in os.listdir(projects_root):
            if os.path.isdir(os.path.join(projects_root, project_id)):
                if project_id in mapping:
                    logger.warning(
                        "project %s is associated with multiple tenants (%s, %s); "
                        "keeping first mapping",
                        project_id,
                        mapping[project_id],
                        tenant_id,
                    )
                else:
                    mapping[project_id] = tenant_id
    return mapping


def _find_tenant_for_project_via_legacy(project_id: str) -> str | None:
    """
    When a project lives only in the legacy directory, try to find its
    owning tenant by reading the legacy project.json (no tenant_id field
    there) and then cross-referencing any hint in the legacy data.

    In practice there is no reliable tenant reference in the legacy
    project.json, so this always returns None — the project ends up
    orphaned unless it was already found via the tenant map.
    """
    legacy_path = os.path.join(_legacy_projects_dir(), project_id, "project.json")
    if not os.path.isfile(legacy_path):
        return None
    # Legacy project.json has no tenant_id field — cannot determine owner.
    return None


# ---------------------------------------------------------------------------
# Move helpers
# ---------------------------------------------------------------------------

def _move_directory(src: str, dst: str, dry_run: bool) -> bool:
    """
    Move src directory to dst.

    - dst must not already exist (idempotency: if it does, src is already
      migrated and we skip).
    - src must exist.
    - On dry_run, only logs what would happen.

    Returns True if a move was performed (or would be in dry_run).
    """
    if not os.path.isdir(src):
        logger.warning("source does not exist, skipping: %s", src)
        return False

    if os.path.exists(dst):
        logger.info("SKIP (destination exists — already migrated): %s -> %s", src, dst)
        return False

    logger.info("%s MOVE: %s -> %s", "[DRY-RUN]" if dry_run else "[EXECUTE]", src, dst)

    if not dry_run:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        logger.info("OK moved: %s", dst)

    return True


# ---------------------------------------------------------------------------
# Per-entity migration
# ---------------------------------------------------------------------------

def migrate_simulations(project_to_tenant: dict, dry_run: bool) -> dict:
    """
    Migrate legacy simulations.

    Each simulation's state.json contains a project_id; we use
    project_to_tenant to resolve the owning tenant.

    Returns stats: {"moved": int, "orphaned": int, "skipped": int}
    """
    stats = {"moved": 0, "orphaned": 0, "skipped": 0}

    legacy_dir = _legacy_simulations_dir()
    if not os.path.isdir(legacy_dir):
        logger.info("No legacy simulations directory found: %s", legacy_dir)
        return stats

    sim_ids = [
        d for d in os.listdir(legacy_dir)
        if os.path.isdir(os.path.join(legacy_dir, d))
    ]

    if not sim_ids:
        logger.info("No legacy simulation directories found.")
        return stats

    for sim_id in sorted(sim_ids):
        src = os.path.join(legacy_dir, sim_id)
        state_path = os.path.join(src, "state.json")

        # Read project_id from state.json
        project_id = None
        if os.path.isfile(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                project_id = state.get("project_id")
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Cannot read state.json for sim %s: %s", sim_id, exc)

        tenant_id = project_to_tenant.get(project_id) if project_id else None

        if tenant_id:
            dst = _tenant_sim_dir(tenant_id, sim_id)
            moved = _move_directory(src, dst, dry_run)
            if moved:
                stats["moved"] += 1
            else:
                stats["skipped"] += 1
        else:
            logger.warning(
                "sim %s: cannot determine tenant (project_id=%s) — moving to _orphaned",
                sim_id,
                project_id,
            )
            dst = _orphaned_sim_dir(sim_id)
            moved = _move_directory(src, dst, dry_run)
            if moved:
                stats["orphaned"] += 1
            else:
                stats["skipped"] += 1

    return stats


def migrate_projects(project_to_tenant: dict, dry_run: bool) -> dict:
    """
    Migrate legacy projects.

    project_to_tenant was built from already-migrated tenant dirs; any
    project not found there has no known owner and is moved to _orphaned.

    Returns stats: {"moved": int, "orphaned": int, "skipped": int}
    """
    stats = {"moved": 0, "orphaned": 0, "skipped": 0}

    legacy_dir = _legacy_projects_dir()
    if not os.path.isdir(legacy_dir):
        logger.info("No legacy projects directory found: %s", legacy_dir)
        return stats

    project_ids = [
        d for d in os.listdir(legacy_dir)
        if os.path.isdir(os.path.join(legacy_dir, d))
    ]

    if not project_ids:
        logger.info("No legacy project directories found.")
        return stats

    for project_id in sorted(project_ids):
        src = os.path.join(legacy_dir, project_id)

        tenant_id = project_to_tenant.get(project_id)

        if not tenant_id:
            # One more attempt: check if a project.json references something useful.
            tenant_id = _find_tenant_for_project_via_legacy(project_id)

        if tenant_id:
            dst = _tenant_project_dir(tenant_id, project_id)
            moved = _move_directory(src, dst, dry_run)
            if moved:
                stats["moved"] += 1
            else:
                stats["skipped"] += 1
        else:
            logger.warning(
                "project %s: cannot determine tenant — moving to _orphaned",
                project_id,
            )
            dst = _orphaned_project_dir(project_id)
            moved = _move_directory(src, dst, dry_run)
            if moved:
                stats["orphaned"] += 1
            else:
                stats["skipped"] += 1

    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Migrate legacy uploads/simulations and uploads/projects to tenant-scoped directories."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually move files. Without this flag the script runs in dry-run mode.",
    )
    args = parser.parse_args()

    dry_run = not args.execute

    if dry_run:
        logger.info("=== DRY-RUN MODE — no files will be moved. Pass --execute to apply. ===")
    else:
        logger.info("=== EXECUTE MODE — files will be moved. ===")

    # Build project -> tenant mapping from existing tenant directories.
    project_to_tenant = _build_project_to_tenant_map()
    logger.info(
        "Found %d tenant(s), %d known project->tenant mappings.",
        len(_list_tenant_ids()),
        len(project_to_tenant),
    )

    # Migrate simulations first (they reference project_id to resolve tenant).
    sim_stats = migrate_simulations(project_to_tenant, dry_run)
    logger.info(
        "Simulations: moved=%d orphaned=%d skipped=%d",
        sim_stats["moved"],
        sim_stats["orphaned"],
        sim_stats["skipped"],
    )

    # Migrate projects.
    proj_stats = migrate_projects(project_to_tenant, dry_run)
    logger.info(
        "Projects:    moved=%d orphaned=%d skipped=%d",
        proj_stats["moved"],
        proj_stats["orphaned"],
        proj_stats["skipped"],
    )

    total_moved = sim_stats["moved"] + proj_stats["moved"]
    total_orphaned = sim_stats["orphaned"] + proj_stats["orphaned"]

    if dry_run:
        logger.info(
            "Dry-run complete. Would move %d item(s), orphan %d item(s). "
            "Run with --execute to apply.",
            total_moved,
            total_orphaned,
        )
    else:
        logger.info(
            "Migration complete. Moved %d item(s), orphaned %d item(s).",
            total_moved,
            total_orphaned,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
