"""Builtin cron jobs — auto-registered on gateway startup.

Each entry in BUILTIN_JOBS defines a cron job that the gateway ensures exists.
On startup, `ensure_builtin_jobs()` checks for each by name and creates any
that are missing. Existing jobs (even if paused or modified) are never touched.

This replaces the inline skill creation nudge (creation_nudge_interval) with a
richer nightly review that has access to session history + Discord conversations.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Builtin job definitions ─────────────────────────────────────────────────

NIGHTLY_REVIEW_PROMPT = """\
You are reviewing the last 24 hours of activity — Hermes session transcripts and \
Discord conversations — to decide what's worth saving as skills or memory.

The digest below was collected by a data script. Your job:

**Skills**: Look for non-trivial approaches that were discovered through trial and \
error, user corrections that changed the approach, or multi-step workflows that \
would be valuable to codify. Check the existing skills list to avoid duplicates. \
If an existing skill should be updated based on new learnings, update it. \
Only create new skills for genuinely reusable knowledge.

**Memory**: Look for user preferences, environment facts, tool quirks, or \
conventions that were revealed but might not have been captured yet. Check what's \
already in memory before adding.

Rules:
- Be selective. Most sessions don't produce skill-worthy knowledge.
- Prefer updating existing skills over creating new ones.
- Don't create skills for one-off tasks or simple commands.
- Don't save task progress or session logs to memory.
- If nothing is worth saving, just say "Nothing to save." and stop.
- Keep skill names lowercase with hyphens, max 64 chars.
- Keep memory entries compact — facts, not narratives.
"""

BUILTIN_JOBS: List[Dict[str, Any]] = [
    {
        "name": "Nightly Skill & Memory Review",
        "prompt": NIGHTLY_REVIEW_PROMPT,
        "schedule": "30 8 * * *",  # 8:30 UTC = 4:30 AM EST
        "script": "skill_review_digest.py",
        "deliver": "local",
    },
]


# ── Registration logic ──────────────────────────────────────────────────────

def ensure_builtin_jobs() -> List[str]:
    """Ensure all builtin cron jobs exist. Returns list of newly created job names.

    Checks by name — if a job with the same name already exists (active, paused,
    or disabled), it's left alone. Only missing jobs are created.
    """
    try:
        from cron.jobs import list_jobs, create_job
    except ImportError:
        logger.debug("Cron module not available — skipping builtin job registration")
        return []

    # Get ALL jobs including disabled ones for dedup
    existing_jobs = list_jobs(include_disabled=True)
    existing_names = {j.get("name", "").lower().strip() for j in existing_jobs}

    created = []
    for job_def in BUILTIN_JOBS:
        name = job_def["name"]
        if name.lower().strip() in existing_names:
            logger.debug("Builtin cron job already exists: %s", name)
            continue

        try:
            job = create_job(
                prompt=job_def["prompt"],
                schedule=job_def["schedule"],
                name=name,
                script=job_def.get("script"),
                deliver=job_def.get("deliver", "local"),
            )
            created.append(name)
            logger.info("Created builtin cron job: %s (id=%s)", name, job["id"])
        except Exception as e:
            logger.error("Failed to create builtin cron job %s: %s", name, e)

    return created
