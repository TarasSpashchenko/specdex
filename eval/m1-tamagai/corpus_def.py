"""Corpus definition for the M1 tamagai evaluation (dated v6 layout): paths, gold and authority conventions.

run_eval.py and layer_b.py load a corpus definition with `--corpus-def`; this one is the default.
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "tamagai"
CORPUS = HERE.parent / "corpora" / "tamagai-2026-10-04"
OVERLAY = HERE / "overlay.toml"           # None: the corpus's own BMad customization applies
LAYER_B_OVERLAY = OVERLAY                # Layer B edits its own copy of this overlay per case
GOLD = HERE / "gold"
RESULTS = HERE / "results"

# -- Layer A: discovery and authority conventions of this corpus -------------------------------------------
# Observed median requested range per document (extract-corpus §B6); default for others.
OBSERVED_RANGE = {"prd.md": 77, "EXPERIENCE.md": 145, "ARCHITECTURE-SPINE.md": 51, "addendum.md": 29, "DESIGN.md": 38}
ID_PATTERN = re.compile(r"(?<![\w-])(?:SM-C\d+|(?:NFR|FR|UJ|SM|AD|CAP|CR|OQ|CQ|ACR|UX|A)-(?:\d+|[A-Z]))(?:\.\d+)?(?![\w-])")
SECTION_REF = re.compile(r"\b(PRD addendum|brief addendum|addendum|PRD|spine|EXPERIENCE|DESIGN|OVERVIEW)\s*§\s*(\d+(?:\.\d+)*)", re.I)
MANIFEST = """Specs of record (Tamagai): PRD prd.md (FR/NFR headings, UJ list §2.3, glossary §3, CR §7, SM §13, OQ §15, CQ §15.1); PRD addendum.md;
DESIGN.md (tokens in frontmatter); EXPERIENCE.md; ARCHITECTURE-SPINE.md (AD headings, A-n rows); ARCHITECTURE-OVERVIEW.md; CHANGE-REQUESTS.md (ACR/UX rows);
brief.md and brief addendum.md (superseded by the PRD except economics, brief addendum §1.2). Everything else is supporting or trail."""
OWNER_FILE = {"FR": "prd.md", "NFR": "prd.md", "UJ": "prd.md", "SM": "prd.md", "CR": "prd.md", "OQ": "prd.md", "CQ": "prd.md",
              "AD": "ARCHITECTURE-SPINE.md", "A": "ARCHITECTURE-SPINE.md", "ACR": "CHANGE-REQUESTS.md", "UX": "CHANGE-REQUESTS.md"}
DOC_FILES = {"prd addendum": "prds/prd-tamagai-2026-09-29/addendum.md", "addendum": "prds/prd-tamagai-2026-09-29/addendum.md",
             "brief addendum": "briefs/brief-tamagai-2026-09-29/addendum.md", "prd": "prd.md", "spine": "ARCHITECTURE-SPINE.md",
             "experience": "EXPERIENCE.md", "design": "DESIGN.md", "overview": "ARCHITECTURE-OVERVIEW.md"}

# Authority (GOLD-SPEC "Historical text inside record files"; the overlay's [[historical]] and [[superseded]] rules).
HISTORICAL_SECTIONS = {"addendum.md": ("1.9 Declined proposals", "6. What this PRD changes", "Appendix A"),
                       "EXPERIENCE.md": ("PRD change requests", "Architecture change requests")}
HISTORICAL_LABELS = {"prd.md": "**Retired claims", "EXPERIENCE.md": "**Retired claims"}  # PRD §9 and EXPERIENCE lists
REQUEST_ROWS_FILE = "CHANGE-REQUESTS.md"  # each row's request text is historical; only its Decision cell is current
# Record files the PRD supersedes (path suffix → the one section that stays authority, or None). PRD §0.
SUPERSEDED = {"briefs/brief-tamagai-2026-09-29/brief.md": None, "briefs/brief-tamagai-2026-09-29/addendum.md": "1.2 Economics"}

# -- Layer B: documents the mutation cases edit or create ---------------------------------------------------
PA = "_bmad-output/planning-artifacts"
PRD_DIR = f"{PA}/prds/prd-tamagai-2026-09-29"
PRD = f"{PRD_DIR}/prd.md"
ADDENDUM = f"{PRD_DIR}/addendum.md"
UX_DIR = f"{PA}/ux-designs/ux-tamagai-2026-09-30"
DESIGN = f"{UX_DIR}/DESIGN.md"
EXPERIENCE = f"{UX_DIR}/EXPERIENCE.md"
SPINE_DIR = f"{PA}/architecture/architecture-tamagai-2026-10-03"
SPINE = f"{SPINE_DIR}/ARCHITECTURE-SPINE.md"
SPINE_NAME = "architecture-tamagai-2026-10-03"   # how an epic spine names its parent
SHARED_EXPERIENCE = "_bmad-output/shared/EXPERIENCE.md"
SPEC_A = "_bmad-output/specs/spec-alpha/SPEC.md"
SPEC_B = "_bmad-output/specs/spec-beta/SPEC.md"
SPECS_README = "_bmad-output/specs/README.md"
EPIC_SPINE = f"{PA}/architecture/architecture-epic-pairing/ARCHITECTURE-SPINE.md"
INITIATIVE_NAME = "initiative-tamagai-mvp"
INITIATIVE = f"_bmad-output/{INITIATIVE_NAME}"
SECOND_PRD = f"{PA}/prds/prd-tamagai-2026-10-05/prd.md"
DESIGN_EXPORT = f"{PA}/exports/DESIGN.md"
RENAMED_EXPERIENCE = f"{UX_DIR}/EXPERIENCE-renamed.md"
PRD_FILE_NAME = "prd.md"   # what a --rev snapshot listing shows for the PRD
