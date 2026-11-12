"""specdex agrees with BMad's own scripts on tests/fixtures/v7-current, which carries byte-identical copies of them.

check_ids.py (bmad-facilitate) decides where a planning document defines an ID and which IDs it cites; tickets.py
(bmad-agent-po, installed at _bmad/method/scripts/) decides which tickets a tree holds and their state. When BMad
changes either, the copies are refreshed from the installed files and these tests say what specdex must follow.
"""
from __future__ import annotations

import collections
import importlib.util
import json
import shutil
import subprocess
import unittest

from support import REPO_ROOT
from test_v7_current import BRD, CART, CHARTER, CHECKOUT_PRD, CURRENT, PRD, CurrentProject
from specdexlib import tickets

CHECK_IDS = CURRENT / ".agents" / "skills" / "bmad-facilitate" / "scripts" / "check_ids.py"
TICKETS = "_bmad/method/scripts/tickets.py"
INSTALLED = {CHECK_IDS: REPO_ROOT / ".agents" / "skills" / "bmad-facilitate" / "scripts" / "check_ids.py",
             CURRENT / TICKETS: REPO_ROOT / TICKETS}
# Documents BMad checks together: a document with its parent's (the epic PRD cites the initiative PRD's IDs).
GROUPS = ((PRD, CHECKOUT_PRD), (CHARTER,), (BRD,))


def check_ids_module():
    spec = importlib.util.spec_from_file_location("bmad_check_ids", CHECK_IDS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bmad_scan(root, paths: tuple[str, ...]) -> tuple[dict, dict[str, list[str]], dict[str, list[str]]]:
    """check_ids.py's report, plus where it found each definition and reference: its `scan` keeps them in its first
    two defaultdicts, captured here so the comparison uses BMad's own decisions line by line."""
    module = check_ids_module()
    made: list = []

    def recording(factory):
        made.append(collections.defaultdict(factory))
        return made[-1]

    module.defaultdict = recording
    report = module.scan([(path, (root / path).read_text(encoding="utf-8")) for path in paths])
    return report, made[0], made[1]


class OracleCopiesTest(unittest.TestCase):
    def test_the_oracles_are_byte_identical_to_the_installed_bmad(self):
        for copy, installed in INSTALLED.items():
            if not installed.is_file():
                self.skipTest("no BMad installed in this checkout")
            with self.subTest(copy.name):
                self.assertEqual(copy.read_bytes(), installed.read_bytes())


class CheckIdsConformanceTest(CurrentProject):
    def specdex_sides(self, paths: tuple[str, ...]) -> tuple[set, set, set[str]]:
        """(path, line, id) of specdex's definitions (current or withdrawn) and its other occurrences in the files,
        for the families the documents own; and those families."""
        q = self.queries()
        owned = {d.family for d in q.index.config.defines if d.artifact in {q.files[p]["artifact"] for p in paths}}
        marks = ",".join("?" * len(paths))
        defined = {(r["path"], r["line"], r["id"]) for r in q.conn.execute(
            f"SELECT path, line, id, family FROM defs WHERE path IN ({marks}) AND effective IN ('definition', 'historical')", paths)
            if r["family"] in owned}
        cited = {(r["path"], r["line"], r["id"]) for r in q.conn.execute(
            f"SELECT path, line, id, family FROM occ WHERE path IN ({marks}) AND kind != 'defines'", paths)
            if r["family"] in owned}
        return defined, cited, owned

    @staticmethod
    def bmad_sides(where: dict[str, list[str]], families: set[str]) -> set:
        found = set()
        for ident, places in where.items():
            if ident.rsplit("-", 1)[0] in families:
                found.update((place.rsplit(":", 1)[0], int(place.rsplit(":", 1)[1]), ident) for place in places)
        return found

    def test_definitions_and_citations_are_check_ids_own_line_by_line(self):
        for paths in GROUPS:
            with self.subTest(paths=paths):
                defined, cited, families = self.specdex_sides(paths)
                report, bmad_defined, bmad_cited = bmad_scan(self.root, paths)
                self.assertEqual(defined, self.bmad_sides(bmad_defined, families))
                self.assertEqual(cited, self.bmad_sides(bmad_cited, families))
                self.assertEqual((report["undefined"], report["duplicate"], report["withdrawn"]), ({}, {}, {}))

    def test_code_comments_crlf_and_other_families_are_read_alike(self):
        self.edit(PRD, "### FR-1: Add an item", "```text\n- FR-97: an example\n```\n\n<!-- FR-98: merged into FR-1 -->\n\n### FR-1: Add an item")
        self.edit(PRD, "| Pricing | **FR-6**", "| NFR-2 | **FR-30** A fast cart. |\n| Pricing | **FR-6**")
        self.edit(PRD, "- OQ-1:", "- **FR-4 to FR-6** stay in the first release.\n- OQ-1:")
        (self.root / PRD).write_bytes(self.read(PRD).replace("\n", "\r\n").encode())
        defined, cited, families = self.specdex_sides(GROUPS[0])
        report, bmad_defined, bmad_cited = bmad_scan(self.root, GROUPS[0])
        self.assertEqual(defined, self.bmad_sides(bmad_defined, families))
        self.assertEqual(cited, self.bmad_sides(bmad_cited, families))

    def test_duplicates_undefined_and_withdrawn_ids_are_reported_alike(self):
        self.edit(PRD, "- OQ-1:", "- FR-3: Change the quantity again.\n- OQ-1:")       # a duplicate
        self.edit(PRD, "blocks FR-3.", "blocks FR-3 and FR-7; see FR-99.")            # withdrawn and undefined
        report = bmad_scan(self.root, GROUPS[0])[0]
        self.assertEqual((set(report["duplicate"]), set(report["withdrawn"]), set(report["undefined"])), ({"FR-3"}, {"FR-7"}, {"FR-99"}))
        findings = {(f["code"], f["detail"]) for f in self.lint()}
        self.assertTrue(any(code == "duplicate-definition" and detail.startswith("FR-3 ") for code, detail in findings), findings)
        self.assertTrue({("citation-historical", "cites an ID defined only in historical text: FR-7"),
                         ("citation-unresolved", "dangling reference: FR-99")} <= findings, findings)


@unittest.skipUnless(shutil.which("uv"), "uv not installed (BMad's tickets.py needs PyYAML)")
class TicketsConformanceTest(CurrentProject):
    def bmad_status(self, folder: str) -> dict:
        result = subprocess.run(["uv", "run", "--quiet", str(self.root / TICKETS), "--project-root", str(self.root), "status", folder],
                                capture_output=True, text=True, timeout=300, check=True)
        return json.loads(result.stdout)

    def specdex_tree(self) -> tickets.Tree:
        return tickets.load_tree(self.queries())

    def test_the_tree_holds_bmads_tickets_with_their_state(self):
        status = self.bmad_status("initiative-cart")
        tree = self.specdex_tree()
        leaves = {t.ref: t for t in tree.tickets if t.kind == tickets.LEAF and t.container.startswith(f"{CART}/")}
        self.assertEqual(set(leaves), {row["ref"] for row in status["tickets"]})
        for row in status["tickets"]:
            with self.subTest(row["ref"]):
                ticket = leaves[row["ref"]]
                self.assertEqual((ticket.dropped, ticket.effective_covers, ticket.planned),
                                 (row["state"] == "dropped", row["covers"], row["state"] == "planned"))
                self.assertEqual(ticket.status or "", row["status"])
        epics = {t.epic_folder.rsplit("/", 1)[1]: t for t in tree.tickets if t.kind == tickets.EPIC}
        self.assertEqual({(e["slug"], str(e["id"]), e.get("status") == "dropped") for e in status["epics"]},
                         {(slug, t.ident, t.dropped) for slug, t in epics.items()})

    def test_a_parent_initiative_lists_the_same_children(self):
        status = self.bmad_status("initiative-shop")
        records = {t.ref: t for t in self.specdex_tree().tickets if t.kind == tickets.CHILD}
        self.assertEqual({(row["slug"], str(row["id"])) for row in status["initiatives"]}, {(ref, t.ident) for ref, t in records.items()})

    def test_the_backlog_holds_the_same_standalone_tickets(self):
        status = self.bmad_status("backlog")
        standalone = {t.ref for t in self.specdex_tree().tickets if t.kind == tickets.STANDALONE}
        self.assertEqual({f"backlog.{row['ref'].removesuffix('.md')}" for row in status["tickets"]}, standalone)
