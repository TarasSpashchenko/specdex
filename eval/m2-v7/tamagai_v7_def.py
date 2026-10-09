"""Corpus definition for tamagai-v7: the M1 tamagai corpus moved into the BMad v7 initiative layout.

Built by make_tamagai_v7.py (same bytes, new paths). Layer A reads the corpus's own BMad customization
(`_bmad/custom/specdex.toml`, no records list: the active initiative decides). Layer B uses an explicit overlay,
the M1 one with v7 paths, so every M1 mutation runs unchanged; each copy drops the corpus's customization.
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "tamagai-v7"
CORPUS = HERE.parent / "corpora" / "tamagai-v7-2026-10-09"
OVERLAY = None
CORPUS_SETTINGS = "_bmad/custom/specdex.toml"
LAYER_B_OVERLAY = HERE / "overlay-tamagai-v7.toml"
GOLD = HERE / "gold-tamagai-v7"
RESULTS = HERE / "results-tamagai-v7"

# -- Layer A: the M1 conventions with v7 file names -------------------------------------------------------
OBSERVED_RANGE = {"prd-tamagai.md": 77, "EXPERIENCE.md": 145, "architecture-tamagai.md": 51, "addendum.md": 29, "DESIGN.md": 38}
ID_PATTERN = re.compile(r"(?<![\w-])(?:SM-C\d+|(?:NFR|FR|UJ|SM|AD|CAP|CR|OQ|CQ|ACR|UX|A)-(?:\d+|[A-Z]))(?:\.\d+)?(?![\w-])")
SECTION_REF = re.compile(r"\b(PRD addendum|brief addendum|addendum|PRD|spine|EXPERIENCE|DESIGN|OVERVIEW)\s*§\s*(\d+(?:\.\d+)*)", re.I)
MANIFEST = """Specs of record (Tamagai): PRD prd-tamagai.md (FR/NFR headings, UJ list §2.3, glossary §3, CR §7, SM §13, OQ §15, CQ §15.1); PRD addendum.md;
DESIGN.md (tokens in frontmatter); EXPERIENCE.md; architecture-tamagai.md (spine: AD headings, A-n rows); ARCHITECTURE-OVERVIEW.md; CHANGE-REQUESTS.md (ACR/UX rows);
brief-tamagai.md and brief addendum.md (superseded by the PRD except economics, brief addendum §1.2). Everything else is supporting or trail."""
OWNER_FILE = {"FR": "prd-tamagai.md", "NFR": "prd-tamagai.md", "UJ": "prd-tamagai.md", "SM": "prd-tamagai.md", "CR": "prd-tamagai.md",
              "OQ": "prd-tamagai.md", "CQ": "prd-tamagai.md", "AD": "architecture-tamagai.md", "A": "architecture-tamagai.md",
              "ACR": "CHANGE-REQUESTS.md", "UX": "CHANGE-REQUESTS.md"}
DOC_FILES = {"prd addendum": "prd-tamagai/addendum.md", "addendum": "prd-tamagai/addendum.md",
             "brief addendum": "brief-tamagai/addendum.md", "prd": "prd-tamagai.md", "spine": "architecture-tamagai.md",
             "experience": "EXPERIENCE.md", "design": "DESIGN.md", "overview": "ARCHITECTURE-OVERVIEW.md"}
HISTORICAL_SECTIONS = {"addendum.md": ("1.9 Declined proposals", "6. What this PRD changes", "Appendix A"),
                       "EXPERIENCE.md": ("PRD change requests", "Architecture change requests")}
HISTORICAL_LABELS = {"prd-tamagai.md": "**Retired claims", "EXPERIENCE.md": "**Retired claims"}
REQUEST_ROWS_FILE = "CHANGE-REQUESTS.md"
SUPERSEDED = {"brief-tamagai/brief-tamagai.md": None, "brief-tamagai/addendum.md": "1.2 Economics"}

# -- Layer B: v7 homes for the documents the mutation cases edit or create ------------------------------
INITIATIVE_NAME = "initiative-tamagai"   # the active initiative: tickets must live in it to be checked
INITIATIVE = f"_bmad-output/{INITIATIVE_NAME}"
PRD_DIR = f"{INITIATIVE}/prd-tamagai"
PRD = f"{PRD_DIR}/prd-tamagai.md"
ADDENDUM = f"{PRD_DIR}/addendum.md"
UX_DIR = f"{INITIATIVE}/ux-tamagai"
DESIGN = f"{UX_DIR}/DESIGN.md"
EXPERIENCE = f"{UX_DIR}/EXPERIENCE.md"
SPINE_DIR = f"{INITIATIVE}/architecture-tamagai"
SPINE = f"{SPINE_DIR}/architecture-tamagai.md"
SPINE_NAME = "architecture-tamagai"
SHARED_EXPERIENCE = "_bmad-output/shared/EXPERIENCE.md"
SPEC_A = f"{INITIATIVE}/spec-alpha/spec-alpha.md"
SPEC_B = f"{INITIATIVE}/spec-beta/spec-beta.md"
SPECS_README = f"{INITIATIVE}/specs-index.md"
EPIC_SPINE = f"{INITIATIVE}/architecture-epic-pairing/architecture-epic-pairing.md"
SECOND_PRD = f"{INITIATIVE}/prd-tamagai-copy/prd-tamagai-copy.md"
DESIGN_EXPORT = "_bmad-output/exports/DESIGN.md"
RENAMED_EXPERIENCE = f"{UX_DIR}/EXPERIENCE-renamed.md"
PRD_FILE_NAME = "prd-tamagai.md"
