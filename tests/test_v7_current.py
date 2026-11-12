"""specdex on BMad's current v7 layout (tests/fixtures/v7-current, changed per test in a private copy).

The fixture follows BMad a867e160, and BMad's own tickets.py and check_ids.py accept it. The parent initiative
initiative-shop has a charter defining SM-1, SM-2, RULE-1 and RULE-2, Requirements `R1 (RULE-1)` and `R2 (SM-1)`, and
lists initiative-cart and initiative-search in `[[initiative]]` tables. The active child initiative-cart has
Requirements `R1 (FR-1, FR-2)`, `R2 (prd FR-3)`, `R3 (parent R1)`, `R4 (brd BR-1)` and `R5 (Scope)`. Its PRD defines
FR-1 to FR-7 (FR-7 withdrawn), UJ-1, UJ-2, RULE-3, SM-3 and OQ-1 in every form check_ids.py accepts; its BRD defines
BR-1, BR-2 and RULE-4; its spine binds R1 to R4 (AD-1: R1, R2; AD-2: R3, R4). Its tickets/ folder holds epic 1
epic-checkout and the dropped epic 2 epic-wishlist. epic-checkout has Requirements `R1 (parent R1)`, `R2 (parent R1)`,
`R3 (parent R2)`, `R4 (parent R3)` and `R5 (prd FR-8)`, its own PRD (FR-8, FR-9) and spine (AD-3 binds R1, R2, R5),
and entries 1.1 [R1] done, 1.2 [R2, R3, R5] in progress and 1.3 [R4] planned. initiative-search has no epics: its
entry 1 covers R1 `(parent R2)`. backlog/ holds a bug covering FR-5; archive/ holds an old PRD.
"""
from __future__ import annotations

import shutil
import subprocess
from collections import defaultdict

from support import GIT_ENV, REPO_ROOT, line_of, requires_git
from test_v7_tickets import FIXTURE as OCTOBER, TicketTreeProject
from specdexlib import cli, tickets
from specdexlib.index import open_index
from specdexlib.queries import Queries

CURRENT = REPO_ROOT / "tests" / "fixtures" / "v7-current"
SHARDED_PRD = REPO_ROOT / "tests" / "fixtures" / "v7-current-sharded" / "prd-cart"
FOLDED = REPO_ROOT / "tests" / "fixtures" / "v7-folded"
USER_CONFIG = "_bmad/custom/config.user.toml"
OUT = "_bmad-output"
SHOP = f"{OUT}/initiative-shop"
CHARTER = f"{SHOP}/charter-shop/charter-shop.md"
CART = f"{OUT}/initiative-cart"
CART_FILE = f"{CART}/initiative-cart.md"
PRD = f"{CART}/prd-cart/prd-cart.md"
BRD = f"{CART}/brd-cart/brd-cart.md"
SPINE = f"{CART}/architecture-cart/architecture-cart.md"
EXPERIENCE = f"{CART}/ux-cart/EXPERIENCE.md"
CHECKOUT = f"{CART}/tickets/epic-checkout"
CHECKOUT_FILE = f"{CHECKOUT}/epic-checkout.md"
CHECKOUT_PRD = f"{CHECKOUT}/prd-checkout/prd-checkout.md"
CHECKOUT_SPINE = f"{CHECKOUT}/architecture-checkout/architecture-checkout.md"
CHECKOUT_TOML = f"{CHECKOUT}/tickets/tickets.toml"
ADD_ITEM = f"{CHECKOUT}/tickets/story-add-an-item.md"
SEARCH = f"{OUT}/initiative-search"
ARCHIVED_PRD = f"{OUT}/archive/prd-cart-2026-09/prd.md"
PRD_SOURCE = "_bmad-output/initiative-cart/prd-cart/prd-cart.md, "
ENTRY_3_COVERS = 'covers = ["R4"]'


class CurrentProject(TicketTreeProject):
    fixture = CURRENT

    def chains(self) -> dict[tuple[str, str], list[tuple[str, str | None]]]:
        """(ticket ref, covered id) → [(state, target)] for every chain."""
        q = self.queries()
        found = defaultdict(list)
        for chain in tickets.chains(q, tickets.load_tree(q)):
            found[(chain.ticket, chain.covered_id)].append((chain.state, chain.target))
        return found

    def lint(self) -> list[dict]:
        return self.run_cli("lint", "--no-validators")[1]["findings"]

    def roles(self) -> dict[str, str]:
        q = self.queries()
        return {path: info["role"] for path, info in q.files.items()}

    def resolve(self, ident: str) -> dict:
        return self.run_cli("resolve", ident)[1]

    def architecture_rows(self) -> dict[str, dict]:
        rows = self.run_cli("coverage", "--by", "architecture")[1]["rows"]
        return {row["id"]: row for row in rows}

    def activate(self, initiative: str) -> None:
        self.write(USER_CONFIG, f'[core]\nactive_initiative = "{initiative}"\n')


# T1–T3, T11: one reader for the tickets/ folder layout
class TicketTreeTest(CurrentProject):
    def test_the_tickets_folder_holds_the_tree_and_every_chain_resolves(self):
        q = self.queries()
        refs = {t.ref for t in tickets.load_tree(q).tickets}
        self.assertEqual(refs, {"1", "2", "1.1", "1.2", "1.3", "2.1", "initiative-cart", "initiative-search",
                                "backlog.bug-total-rounds-wrong"})
        covers = self.covers()
        self.assertEqual((covers["problems"], covers["drift"], covers["planned"]), ([], [], ["1.3"]))
        self.assertEqual(sorted(covers["dropped"]), ["2", "2.1"])

    def test_an_initiative_without_epics_stays_an_initiative_under_its_tickets_folder(self):
        self.activate("initiative-search")
        q = self.queries()
        container = tickets.load_tree(q).containers[SEARCH]
        self.assertEqual((container.kind, container.parent), ("initiative", SHOP))
        self.assertEqual(self.chains()[("1", "R1")], [("resolved", "SM-1")])


# T4, T5, T7: Requirements lines
class RequirementLineTest(CurrentProject):
    def test_a_parent_line_reaches_every_source_id_of_the_parents_line(self):
        self.assertEqual(self.chains()[("1.1", "R1")], [("resolved", "FR-1"), ("resolved", "FR-2")])

    def test_a_typed_source_id_is_looked_up_in_a_source_of_that_type_only(self):
        self.assertEqual(self.chains()[("1.2", "R3")], [("resolved", "FR-3")])
        self.edit(CART_FILE, "R2 (prd FR-3)", "R2 (brd FR-3)")
        self.assertEqual(self.chains()[("1.2", "R3")], [("upstream-unresolved", "FR-3")])

    def test_a_line_citing_only_a_source_section_is_local_never_a_problem(self):
        self.edit(CHECKOUT_FILE, "- R5 (prd FR-8)", "- R6 (Boundaries): The cart page loads in a second.\n- R5 (prd FR-8)")
        self.edit(CHECKOUT_TOML, ENTRY_3_COVERS, 'covers = ["R6"]')
        covers = self.covers()
        self.assertEqual(covers["problems"], [])
        self.assertEqual([(item["ticket"], item["covers"]) for item in covers["local"]], [("1.3", "R6")])

    def test_a_line_naming_neither_a_parent_nor_a_source_is_flagged(self):
        self.edit(CHECKOUT_FILE, "- R2 (parent R1):", "- R2:")
        self.assertIn(("1.2", "R2", "no-source"), self.problems(self.covers()))
        self.assertIn("ticket-no-source", {f["code"] for f in self.lint()})

    def test_a_parent_id_the_parent_lacks_is_flagged(self):
        self.edit(CHECKOUT_FILE, "R4 (parent R3)", "R4 (parent R9)")
        self.assertIn(("1.3", "R4", "upstream-unresolved"), self.problems(self.covers()))


class FoldedSpecTest(TicketTreeProject):
    """tests/fixtures/v7-folded: the October fixture after BMad's spec fold and migration-2."""
    fixture = FOLDED
    csv = f"{OUT}/initiative-shelf/tickets/epic-csv-transfer"

    def test_the_folded_tree_reads_as_its_october_layout_did(self):
        covers = self.covers()
        self.assertEqual(self.problems(covers), [("1.3", "E5", "unresolved")])
        self.fixture = OCTOBER
        self.setUp()
        self.assertEqual(self.problems(self.covers()), self.problems(covers))

    def test_a_folded_spec_id_names_its_own_line(self):
        self.edit(f"{self.csv}/tickets/tickets.toml", 'covers = ["FR-5"]', 'covers = ["R1"]')
        covers = self.covers()
        self.assertEqual(self.problems(covers), [("1.3", "E5", "unresolved")])
        self.assertIn(("2.2", "R1"), [(item["ticket"], item["covers"]) for item in covers["local"]])


# T6, T10: sources and companions are paths from the project root
class SourcesTest(CurrentProject):
    def test_the_prd_named_in_sources_is_the_requirement_source(self):
        self.edit(CART_FILE, PRD_SOURCE, "")  # its References line still points at it: a pointer, not a source
        self.assertEqual(self.chains()[("1.1", "R1")], [("upstream-unresolved", "FR-1"), ("upstream-unresolved", "FR-2")])

    def test_a_source_named_from_the_tickets_folder_still_resolves(self):
        self.edit(CART_FILE, PRD_SOURCE, "prd-cart/prd-cart.md, ")  # as BMad's spec fold writes it
        self.assertEqual(self.chains()[("1.1", "R1")], [("resolved", "FR-1"), ("resolved", "FR-2")])

    def test_a_companion_named_from_the_project_root_is_found(self):
        notes = f"{CART}/notes/pricing-table.md"
        self.write(notes, "# Pricing table\n")
        self.edit(PRD, "template: prd\n", f"template: prd\ncompanions: [{notes}]\n")
        self.assertNotIn("missing-companion", {f["code"] for f in self.lint()})
        self.assertEqual(self.roles()[notes], "record")


# T9: parent initiatives
class ParentInitiativeTest(CurrentProject):
    def test_the_parent_initiatives_documents_are_records_and_the_siblings_are_not(self):
        roles = self.roles()
        self.assertEqual((roles[CHARTER], roles[f"{SHOP}/initiative-shop.md"]), ("record", "ticket"))
        self.assertEqual(roles[f"{SEARCH}/initiative-search.md"], "noncurrent")
        self.assertEqual(self.run_cli("status")[1]["parent_initiatives"], [SHOP])

    def test_a_childs_parent_line_reaches_the_parents_source(self):
        self.assertEqual(self.chains()[("1.3", "R4")], [("resolved", "RULE-1")])
        rows = self.coverage_rows("RULE")
        self.assertEqual((rows["RULE-1"]["state"], rows["RULE-1"]["declared"]), ("declared", ["1.3 (planned)"]))

    def test_the_parents_initiative_records_resolve_against_the_parent(self):
        chains = self.chains()
        self.assertEqual(chains[("initiative-cart", "R1")], [("resolved", "RULE-1")])
        self.assertEqual(chains[("initiative-search", "R2")], [("resolved", "SM-1")])


# T8: a ticket's R ids
class RequirementIdTest(CurrentProject):
    def test_each_tickets_r1_is_a_definition_and_the_citing_document_decides(self):
        result = self.resolve("R1")
        self.assertTrue(result["status"].startswith("ambiguous: defined in 4 scopes"), result["status"])
        self.assertEqual({hit["path"] for hit in result["definitions"]},
                         {CART_FILE, CHECKOUT_FILE, f"{CART}/tickets/epic-wishlist/epic-wishlist.md", f"{SHOP}/initiative-shop.md"})

    def test_r_citations_resolve_in_their_own_container_and_prose_is_no_citation(self):
        self.assertEqual(self.lint(), [])  # Notes say "Parked: R5"; the epic file's covers name the parent's R ids
        rows = self.run_cli("refs", "R5", "--scope", "current")[1]["lines"]
        story = f"{CHECKOUT}/tickets/story-remove-an-item.md"
        self.assertEqual({(row["path"], row["kind"]) for row in rows}, {(story, "mentions"), (story, "covers"), (CHECKOUT_SPINE, "binds")})

    def test_a_planned_entry_citing_an_r_id_is_found_in_tickets_toml(self):
        rows = self.run_cli("refs", "R4", "--kind", "covers")[1]["lines"]
        self.assertIn((CHECKOUT_TOML, line_of(self.read(CHECKOUT_TOML), ENTRY_3_COVERS), "ticket 1.3"),
                      {(row["path"], row["line"], row["src_id"]) for row in rows})

    def test_a_storys_r_id_its_epic_lacks_never_falls_through_to_the_initiatives(self):
        text = self.read(CHECKOUT_FILE)
        self.write(CHECKOUT_FILE, text.replace(next(l for l in text.split("\n") if l.startswith("- R3 (parent R2)")) + "\n", ""))
        self.assertEqual(self.chains()[("1.2", "R3")], [("unresolved", None)])

    def test_an_r_id_its_container_lacks_is_dangling(self):
        self.edit(ADD_ITEM, "covers: [R1]", "covers: [R9]")
        self.edit(CHECKOUT_SPINE, "- **Binds:** R1, R2, R5", "- **Binds:** R1, R2, R5, R6")
        findings = {(f["code"], f["path"]) for f in self.lint()}
        self.assertIn(("ticket-unresolved", ADD_ITEM), findings)
        self.assertIn(("citation-unresolved", CHECKOUT_SPINE), findings)


# P1: the spine binds the ticket's R ids
class ArchitectureCoverageTest(CurrentProject):
    def test_r_bindings_reach_the_ids_their_requirement_lines_name(self):
        rows = self.architecture_rows()
        self.assertEqual({ident: (row["state"], row["declared"]) for ident, row in rows.items()}, {
            "FR-1": ("declared", ["AD-1", "AD-3"]), "FR-2": ("declared", ["AD-1", "AD-3"]), "FR-3": ("declared", ["AD-1"]),
            "FR-4": ("missing", []), "FR-5": ("missing", []), "FR-6": ("missing", []), "FR-8": ("declared", ["AD-3"]),
            "FR-9": ("missing", [])})

    def test_binding_fr_ids_directly_gives_the_same_coverage(self):
        shutil.rmtree(self.root / CHECKOUT / "architecture-checkout")
        by_r = self.architecture_rows()
        self.edit(SPINE, "binds: [R1, R2, R3, R4]", "binds: [FR-1, FR-2, FR-3, RULE-1, BR-1]")
        self.edit(SPINE, "- **Binds:** R1, R2", "- **Binds:** FR-1, FR-2, FR-3")
        self.edit(SPINE, "- **Binds:** R3, R4", "- **Binds:** RULE-1, BR-1")
        self.assertEqual(self.architecture_rows(), by_r)


# P2–P7, P9: planning documents
class PlanningDocumentTest(CurrentProject):
    def test_an_epics_documents_are_records_beside_its_initiatives(self):
        roles = self.roles()
        self.assertEqual({roles[p] for p in (PRD, CHECKOUT_PRD, SPINE, CHECKOUT_SPINE, BRD, EXPERIENCE)}, {"record"})
        self.assertNotIn("ambiguous-current", {d["code"] for d in self.run_cli("status")[1]["diagnostics"]})

    def test_two_prds_in_one_initiative_stay_ambiguous_and_the_fix_is_named(self):
        self.write(f"{CART}/prd-cart-v6/prd-cart-v6.md", self.read(PRD))
        finding = next(f for f in self.lint() if f["code"] == "ambiguous-current")
        self.assertIn("records setting", finding["detail"])
        self.assertIn("_bmad-output/archive", finding["detail"])

    def test_every_form_check_ids_accepts_defines_and_the_others_cite(self):
        text = self.read(PRD)
        expected = {"FR-1": "### FR-1:", "FR-2": "- **FR-2.**", "FR-3": "- FR-3:", "FR-4": "FR-4. A shopper",
                    "FR-5": "| FR-5 |", "FR-6": "**FR-6**", "UJ-1": "UJ-1. ", "UJ-2": "UJ-2. ", "RULE-3": "**RULE-3:**",
                    "SM-3": "- SM-3:", "OQ-1": "- OQ-1:"}
        for ident, needle in expected.items():
            with self.subTest(ident):
                result = self.resolve(ident)
                self.assertEqual(result["status"], "defined")
                self.assertEqual((result["definitions"][0]["path"], result["definitions"][0]["start"]), (PRD, line_of(text, needle)))
        self.assertEqual(self.resolve("FR-7")["status"], "historical only (retired or declined; not a current definition)")
        cited = {(row["line"], row["kind"]) for row in self.run_cli("refs", "UJ-1")[1]["lines"] if row["path"] == PRD}
        self.assertIn((line_of(text, "| UJ-1 | FR-1, FR-2 |"), "mentions"), cited)  # a table re-citing earlier IDs

    def test_new_families_resolve_in_their_documents(self):
        for ident, path in (("BR-1", BRD), ("RULE-4", BRD), ("RULE-1", CHARTER), ("SM-1", CHARTER), ("FR-8", CHECKOUT_PRD)):
            with self.subTest(ident):
                result = self.resolve(ident)
                self.assertEqual((result["status"], result["definitions"][0]["path"]), ("defined", path))

    def test_ranges_in_words_cite_every_member(self):
        text = self.read(PRD)
        lines = {row["line"] for row in self.run_cli("refs", "FR-2")[1]["lines"] if row["path"] == PRD and row["via_range"]}
        self.assertEqual(lines, {line_of(text, "— FR-1 to FR-6"), line_of(text, "In: FR-1 to FR-4"), line_of(text, "validates FR-1 to FR-5")})

    def test_an_engine_documents_template_decides_its_type(self):
        self.write(f"{CART}/business-case-cart/business-case-cart.md", "---\ntemplate: business-case\n---\n\n# Case\n\n- BR-9: Grow carts.\n")
        self.assertEqual(self.roles()[f"{CART}/business-case-cart/business-case-cart.md"], "rationale")
        self.assertTrue(self.resolve("BR-9")["status"].startswith("not defined"))
        self.assertEqual(self.queries().files[BRD]["artifact"], "brd")

    def test_archives_template_copies_and_shard_sources_are_trail(self):
        self.write(f"{CART}/prd-cart/.source/prd-cart.md", self.read(PRD))
        roles = self.roles()
        self.assertEqual({roles[p] for p in (ARCHIVED_PRD, f"{CART}/prd-cart/.template.md", f"{CART}/prd-cart/.source/prd-cart.md")}, {"trail"})
        self.assertEqual(self.resolve("FR-1")["status"], "defined")


# P8: a bmad-shard-pro document answers as its unsharded original
class ShardTest(CurrentProject):
    IDS = ("FR-1", "FR-2", "FR-3", "FR-4", "FR-5", "FR-6", "FR-7", "UJ-1", "UJ-2", "RULE-3", "SM-3", "OQ-1", "R1")

    def answers(self) -> dict:
        def unit_text(ident: str) -> str:
            hits = self.run_cli("get", ident)[1].get("hits", [])  # an ID an earlier PRD's forms do not define has none
            return "\n".join(hit["text"] for hit in hits)
        return {
            "resolve": {ident: self.resolve(ident)["status"] for ident in self.IDS},
            "get": {ident: unit_text(ident) for ident in ("FR-1", "FR-3", "FR-5", "UJ-1")},
            "refs": {ident: sorted(row["excerpt"].strip() for row in self.run_cli("refs", ident)[1]["lines"]) for ident in ("FR-2", "UJ-2")},
            "coverage": {by: self.run_cli("coverage", "--by", by)[1]["rows"] for by in ("tickets", "architecture", "ux")},
            "lint": sorted((f["code"], f["detail"]) for f in self.lint()),
        }

    RECAP = "- FR-1 — recap: one line per product.\n"

    def shard(self) -> None:
        shutil.rmtree(self.root / CART / "prd-cart")
        shutil.copytree(SHARDED_PRD, self.root / CART / "prd-cart")

    def test_sharding_the_prd_changes_no_answer_but_paths_and_lines(self):
        unsharded = self.answers()
        self.shard()
        self.assertEqual(self.roles()[f"{CART}/prd-cart/features-and-requirements.md"], "record")
        self.assertEqual(self.answers(), unsharded)

    def test_shards_follow_their_main_files_rules_even_when_only_the_main_file_changes(self):
        # A PRD written before the engine (no `template`) keeps the earlier forms: its recap line cites FR-1.
        self.edit(PRD, "template: prd\n", "")
        self.write(PRD, self.read(PRD) + self.RECAP)
        unsharded = self.answers()
        self.assertEqual(self.resolve("FR-1")["status"], "defined")
        self.shard()
        shard = f"{CART}/prd-cart/metrics-and-open-questions.md"
        self.write(shard, self.read(shard) + self.RECAP)
        self.assertTrue(self.resolve("FR-1")["status"].startswith("ambiguous"))  # an engine PRD's line `- FR-1 — …` defines
        self.edit(f"{CART}/prd-cart/prd-cart.md", "template: prd\n", "")
        self.assertEqual(self.answers(), unsharded)


# X3, X4: exit codes and lint
class ExitAndLintTest(CurrentProject):
    def test_coverage_of_an_empty_population_is_no_clean_result(self):
        code, report = self.run_cli("coverage", "--by", "tickets", "--family", "SC")
        self.assertEqual((code, report["rows"]), (1, []))

    def test_coverage_over_an_incomplete_scope_is_no_clean_result(self):
        self.edit(EXPERIENCE, "## UJ-1", "## UJ-2 — Lee removes a line\n\nLee removes a line.\n\n## UJ-1")
        self.assertEqual(self.run_cli("coverage", "--by", "ux")[0], 0)
        self.write(f"{CART}/prd-cart-v6/prd-cart-v6.md", self.read(PRD))
        code, report = self.run_cli("coverage", "--by", "ux", "--only", "declared")
        self.assertEqual(code, 1)
        self.assertTrue(report["scope"].startswith("incomplete"), report["scope"])

    def test_lint_reports_a_broken_covers_chain_where_the_covers_are_written(self):
        self.edit(CHECKOUT_TOML, ENTRY_3_COVERS, 'covers = ["R7"]')
        finding = next(f for f in self.lint() if f["code"] == "ticket-unresolved")
        self.assertEqual((finding["severity"], finding["path"], finding["line"]),
                         ("high", CHECKOUT_TOML, line_of(self.read(CHECKOUT_TOML), 'covers = ["R7"]')))
        self.assertEqual(self.run_cli("lint", "--no-validators")[0], 1)


# X1: the profile's bindings match the BMad installed in this repository
class BindingTest(CurrentProject):
    def test_the_v7_profile_is_verified_against_the_installed_bmad(self):
        if not (REPO_ROOT / ".agents" / "skills" / "bmod-method").is_dir():
            self.skipTest("no BMad installed in this checkout")
        config = cli.load_config(REPO_ROOT)
        index = open_index(config, db_path=self.db)
        self.addCleanup(index.conn.close)
        self.assertEqual(Queries(index).binding(), {"state": "verified", "mismatched": [], "missing": []})


# diff: a change to either definition of a duplicated ID is a change
@requires_git
class DuplicateDiffTest(CurrentProject):
    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.root), *args], env=GIT_ENV, check=True, capture_output=True)

    def test_an_edit_to_one_of_two_definitions_is_reported(self):
        self.write(PRD, self.read(PRD) + "- **FR-1** — recap: one line per product.\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.edit(PRD, "from its page, quantity one.", "from its page, quantity two.")
        self.assertIn("FR-1", [item["id"] for item in self.run_cli("diff", "HEAD")[1]["changed"]])


# Review findings (docs/m3-report.md lists them): each stays fixed.
class ReviewFindingTest(CurrentProject):
    def test_a_spine_binds_the_r_ids_of_an_initiative_not_sliced_yet(self):
        shutil.rmtree(self.root / CART / "tickets")
        rows = self.architecture_rows()
        self.assertEqual({i: rows[i]["declared"] for i in ("FR-1", "FR-2", "FR-3")}, {"FR-1": ["AD-1"], "FR-2": ["AD-1"], "FR-3": ["AD-1"]})

    def test_a_parent_named_without_an_id_is_flagged(self):
        self.edit(CHECKOUT_FILE, "R4 (parent R3)", "R4 (parent)")
        self.assertIn(("1.3", "R4", "upstream-unresolved"), self.problems(self.covers()))

    def test_a_source_id_must_be_in_the_tickets_own_sources(self):
        self.edit(CHECKOUT_FILE, "- R5 (prd FR-8)", "- R6 (FR-3): The cart shows removed lines struck through.\n- R5 (prd FR-8)")
        self.edit(CHECKOUT_TOML, ENTRY_3_COVERS, 'covers = ["R6"]')
        self.assertEqual(self.chains()[("1.3", "R6")], [("upstream-unresolved", "FR-3")])

    def test_parent_initiatives_listing_each_other_end_the_walk(self):
        self.write(f"{SHOP}/tickets/tickets.toml", self.read(f"{SHOP}/tickets/tickets.toml")
                   + '\n[[initiative]]\nid = 3\nslug = "initiative-shop"\ntitle = "Itself"\ncovers = ["R1"]\n'
                   + '\n[[initiative]]\nid = 4\nslug = "initiative-ops"\ntitle = "Ops"\ncovers = ["R2"]\n')
        self.write(f"{OUT}/initiative-ops/initiative-ops.md", "---\ntype: initiative\ntitle: Ops\n---\n\n# Ops\n")
        self.write(f"{OUT}/initiative-ops/tickets/tickets.toml", '[[initiative]]\nid = 1\nslug = "initiative-shop"\ntitle = "Shop"\n')
        self.assertEqual(self.chains()[("1.3", "R4")], [("resolved", "RULE-1")])

    def test_a_range_in_a_requirements_line_names_every_member(self):
        self.edit(CART_FILE, "R1 (FR-1, FR-2)", "R1 (FR-1–FR-2)")
        self.assertEqual(self.chains()[("1.1", "R1")], [("resolved", "FR-1"), ("resolved", "FR-2")])

    def test_crlf_fences_and_comments_hide_nothing_and_cite_nothing(self):
        self.edit(PRD, "### FR-1: Add an item", "```text\nexample FR-98\n```\n\n<!-- FR-99 was merged into FR-1 -->\n\n### FR-1: Add an item")
        (self.root / PRD).write_bytes(self.read(PRD).replace("\n", "\r\n").encode())
        for ident in ("FR-1", "FR-5", "FR-6", "UJ-2", "OQ-1"):
            with self.subTest(ident):
                self.assertEqual(self.resolve(ident)["status"], "defined")
        self.assertEqual([f for f in self.lint() if f["code"].startswith("citation")], [])

    def test_naming_a_record_keeps_the_epics_own_document_of_that_type(self):
        self.write("_bmad/custom/specdex.toml", f'[workflow]\nrecords = ["{PRD}"]\n')
        roles = self.roles()
        self.assertEqual((roles[PRD], roles[CHECKOUT_PRD]), ("record", "record"))

    def test_a_containers_own_r_definition_is_never_a_citation_of_its_parent(self):
        self.edit(CHECKOUT_FILE, "- R5 (prd FR-8)", "- R6 (prd FR-9): Saved carts survive a sign-out.\n- R5 (prd FR-8)")
        self.assertEqual(self.lint(), [])

    def test_a_childs_table_re_citing_its_parent_initiatives_ids_defines_nothing(self):
        self.write(f"{SHOP}/prd-shop/prd-shop.md", "---\ntemplate: prd\n---\n\n# Shop\n\n### FR-20: Browse\n\nBrowse.\n\n### FR-21: Pay\n\nPay.\n")
        self.edit(PRD, "## Rules", "| Shop | Cart |\n| --- | --- |\n| FR-20 | the cart page |\n| FR-21 | checkout |\n\n## Rules")
        self.assertEqual(self.resolve("FR-20")["definitions"][0]["path"], f"{SHOP}/prd-shop/prd-shop.md")
        self.assertNotIn("duplicate-definition", {f["code"] for f in self.lint()})

    def test_an_id_of_another_family_opening_a_row_ends_the_row_as_check_ids_reads_it(self):
        self.edit(PRD, "| Pricing | **FR-6**", "| NFR-2 | **FR-30** A fast cart. |\n| Pricing | **FR-6**")
        self.assertTrue(self.resolve("FR-30")["status"].startswith("not defined"))

    def test_a_sentence_lead_in_one_shard_cites_an_id_another_shard_defines(self):
        lead = "- **FR-2 is verified by the remove test.** Three changes show three totals.\n"
        self.write(PRD, self.read(PRD) + lead)
        self.assertEqual(self.resolve("FR-2")["status"], "defined")
        shutil.rmtree(self.root / CART / "prd-cart")
        shutil.copytree(SHARDED_PRD, self.root / CART / "prd-cart")
        shard = f"{CART}/prd-cart/metrics-and-open-questions.md"
        self.write(shard, self.read(shard) + lead)
        self.assertEqual(self.resolve("FR-2")["status"], "defined")
