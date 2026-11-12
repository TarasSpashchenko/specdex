"""Corpus definition for tamagai-v7-current: tamagai-v7 after make_v7_current.py (BMad's current layout).

tamagai has no ticket tree and no spec folder, so the conversion moved nothing (path-map-tamagai.json is empty) and
the corpus is byte-identical to tamagai-v7: every path, overlay and Layer A convention of tamagai_v7_def.py holds
unchanged and is imported from it. This module adds what M3's Layer B cases (layer_b_current.py) need: the
initiative's `tickets/` folder and the plan that shards the PRD with bmad-shard-pro.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "m2-v7"))
from tamagai_v7_def import *  # noqa: E402,F401,F403 - same corpus bytes, same paths and conventions
from tamagai_v7_def import INITIATIVE, INITIATIVE_NAME  # noqa: E402 - used below

HERE = Path(__file__).resolve().parent
NAME = "tamagai-v7-current"
CORPUS = HERE.parent / "corpora" / "tamagai-v7-current-2026-11-11"
RESULTS = HERE

# -- Layer B (M3): the current-layout ticket tree inside the active initiative ---------------------------------
INITIATIVE_FILE = f"{INITIATIVE}/{INITIATIVE_NAME}.md"
TICKETS_DIR = f"{INITIATIVE}/tickets"

# -- Layer B (M3): bmad-shard-pro plan for the PRD (shard_tool.py `build`; lines of prd-tamagai.md) -----------
# Cuts follow the PRD's own sections, 3-14 KB each; titles and summaries name no identifiers, so the map adds no
# citations. The lookup pattern matches the ids the PRD defines, as the skill advises for hundreds of ids.
PRD_SHARD_TITLE = "PRD: Tamagai"
PRD_SHARD_LOOKUP = r"\b(?:NFR|FR|UJ|SM|CR|OQ|CQ)-\d+\b"
PRD_SHARD_GROUPS = [
    ("Purpose, users and terms", [
        ("purpose-and-vision.md", "Purpose and vision", "Document status, readers, the vision, why now and the horizon.", 11, 57),
        ("users-and-journeys.md", "Target users and journeys", "Jobs to be done, non-users and the key user journeys.", 58, 179),
        ("glossary.md", "Glossary", "Every product term the requirements use.", 180, 303),
    ]),
    ("Features", [
        ("setup-and-hatching.md", "Setup, tiers and hatching", "Feature overview, first run, tiers, basic mode, hatching and the first visits.", 304, 480),
        ("pet-life-and-talk.md", "Pet life and talk", "Daily pet life and how the child talks with the pet.", 481, 651),
        ("teaching-and-show-and-tell.md", "Teaching, growth and show-and-tell", "What the child teaches the pet, how it grows, and show-and-tell.", 652, 783),
        ("safety-engine.md", "The safety engine", "How every line the pet says is checked before the child hears it.", 784, 869),
        ("wellbeing-and-time-limits.md", "Wellbeing, crisis and time limits", "Wellbeing, crisis handling, transparency and time limits.", 870, 982),
        ("parent-area-and-profiles.md", "Parent area and child profiles", "What parents see and change, linking and consent, deletion, and child profiles.", 983, 1153),
        ("the-unlock.md", "The unlock", "The demo, the offer, purchase, restore and refunds.", 1154, 1238),
        ("server-tier.md", "The server tier", "Consent, the server credential, the talk allowance, outages and shutdown.", 1239, 1332),
        ("on-device-brain.md", "The on-device brain", "The on-device model: download, integrity, updates, removal and continuity.", 1333, 1392),
        ("counters-and-additions.md", "Counters, diagnostics and later additions", "Counters, crash reports, helpline counts, and the additions after early access.", 1393, 1459),
    ]),
    ("Quality, guardrails and commitments", [
        ("non-functional-requirements.md", "Cross-cutting non-functional requirements", "Experience budget, devices, offline, privacy, security, accessibility and evaluation gates.", 1460, 1636),
        ("guardrails.md", "Guardrails", "Safety choices, the privacy data map and cost guardrails.", 1637, 1714),
        ("compliance-and-positioning.md", "Compliance, monetization, claims and tone", "Regulation, monetization, claims, aesthetic and the non-goals.", 1715, 1820),
    ]),
    ("Scope, measures and open questions", [
        ("mvp-scope.md", "MVP scope", "What is in and out of the first release, and its phases and gates.", 1821, 1910),
        ("success-metrics-and-risks.md", "Success metrics and risks", "How success is measured and the risks to it.", 1911, 1949),
        ("open-questions.md", "Open questions and counsel register", "Open product questions and the questions for counsel.", 1950, 2040),
        ("assumptions.md", "Assumptions", "The load-bearing assumptions and their index.", 2041, 2136),
    ]),
]
