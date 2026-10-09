# Codex audit of specdex M1

**Verdict — review judgment:** M1 acceptance cannot be trusted yet. Passing existing tests does not establish the frozen authority, freshness or retrieval gates. Fix generation isolation, historical/ambiguous authority, ticket trace resolution and read-only enforcement first; then correct labels and evaluate independently of specdex's own answers. Recorded Stage A lookup completion is 16/20 versus B1's 19/20, failing its no-loss gate. Stage B completes all 20 lookup tasks, but its separate top-five benefit gate is not measured comparably. Keep held-out gold sealed until the corrected final protocol is fixed.

The findings and outputs below are **verified facts** from source reads or reproductions. Severity, verdict and suggested fixes are reviewer judgments. Reproduction writes/indexes were under /tmp; this report is the only repository file written. Neither held-out gold nor replay results were opened. **tiktoken is unavailable** here: Layer A token totals are recorded, not independently recomputed. The logic-only harness reproduction explicitly stubs token counting.

## Findings

| ID | Severity | Area | path:line | Finding | Evidence (reproduction or quote) | Suggested fix |
|---|---|---|---|---|---|---|
| A-01 | high | Read-only / execution | skills/specdex/scripts/specdexlib/maintenance.py:128 | Default lint executes project-controlled Python without checking the profile's recorded hash or containing side effects. | R2: replacement lint_spine.py writes inside the temp project: validator-write 1. Hash checking is only reported by queries.py:159. | Require verified adapter bytes and read-only execution; mark unverified adapters unchecked. |
| A-02 | high | Read-only / cache | skills/specdex/scripts/specdexlib/store.py:58 | Cache destinations can be inside the project, including through symlinks or XDG_CACHE_HOME. An old-schema target also loses unrelated tables. | R2: project-cache True; unrelated-table-survives False. No containment check before mkdir/SQLite creation; index.py:34 trusts the environment; store.py:73 enumerates and drops existing tables. | Reject resolved in-project cache locations, including snapshot siblings; verify cache ownership before destructive schema replacement. |
| A-03 | high | Freshness / concurrency | skills/specdex/scripts/specdexlib/index.py:54 | A pre-lock inventory can overwrite a newer committed inventory. Readers have no pinned read transaction, so SQL results can change while cached metadata/generation remain old. | R1 inventory True True 0: a later opener reinstalls the old generation after a newer writer. reader True 1: the old reader finds the new keyword under its old generation. SQLite is autocommit (store.py:59). | Reverify after acquiring the write lock; pin one read snapshot across query construction and answer generation. |
| A-04 | high | Authority / get | skills/specdex/scripts/specdexlib/extract.py:247 | Parent sections containing historical descendants are labelled current; exact-section get bypasses overlap-aware range labels. | R2: addendum §1 returns 21–116 [record], including declined proposals 109–116; §1.9 labels those same lines historical. queries.py:337 returns an exact span before overlap classification. | Label mixed sections partly historical, or segment output with per-region authority. |
| A-05 | high | Resolution / history | skills/specdex/scripts/specdexlib/resolve.py:138 | Historical definition candidates remain effective definitions and satisfy current citations. | R1: retired FR-99 is defined, its definition is historical, and current “See FR-99” resolves. | Exclude historical candidates from current resolution; retain separate historical lookup. |
| A-06 | high | Resolution / ambiguity | skills/specdex/scripts/specdexlib/queries.py:238 | An ID unique to one ambiguous current artifact returns defined; its sole citation candidate also resolves. | R1: two PRDs, only one defining FR-99 → defined ['ambiguous']. Contradicts resolve.py:59: “their IDs resolve to 'ambiguous'”. B12 duplicates identical IDs only. | Propagate artifact ambiguity regardless of definition count. |
| A-07 | high | Ticket trace edges | skills/specdex/scripts/specdexlib/queries.py:382 | refs --kind covers and impact's covers grouping cannot find ticket coverage: no extraction/derivation inserts occ.kind=covers. | R2: coverage FR-1 is declared, but covers refs say none in a fully indexed scope. Preview fixture has zero stored covers edges; chains are computed separately (tickets.py:159). | Materialize source-addressed covers edges, or use the adapter directly in refs/impact. |
| A-08 | high | Tickets / coverage | skills/specdex/scripts/specdexlib/tickets.py:209 | Sources use existence rather than unique authoritative resolution; direct upstream IDs bypass container-covers ownership checks. | R2: duplicate FR-1 is ambiguous but E1/E2 chains resolve with no 1.1 problems. A reading-list story covering FR-4 is accepted although its epic owns FR-1–FR-3. Guard exists only for mapped parents (tickets.py:179). | Resolve uniquely within the source; propagate ambiguity as unknown; apply ownership checks to direct/reused IDs too. |
| A-09 | high | Parse gaps / negatives | skills/specdex/scripts/specdexlib/queries.py:132 | YAML gaps are medium, while completeness checks only high gaps. Malformed authority/companion fields permit definite negatives. Unclosed frontmatter has no diagnostic. | R1 malformed companions list → none in a fully indexed scope despite parse-gap medium (extract.py:190). markdown.py:122 silently falls back without a closing frontmatter delimiter. | Interpretation-affecting parse gaps must make negatives unknown; diagnose unclosed frontmatter/invalid authority fields. |
| A-10 | high | Source containment | skills/specdex/scripts/specdexlib/sources.py:50 | File/directory symlinks are followed outside the project. Read failures silently disappear from the inventory. | R2 returns EXTERNAL_PRIVATE_TEXT through an external symlink. sources.py:67 permits external identities; :65 discards unreadable files without diagnostics. | Bound resolved targets to the project or require explicit external-source declarations; report skipped/unreadable sources as incomplete. |
| A-11 | high | Layer A / B0 fairness | eval/m1-tamagai/run_eval.py:199 | Oracle continuation repeats the same failing B0 lookup five times; B0 truncates before finding record definitions and has no progress guard. | R3 S01: 12 outputs, only 2 distinct, recall 0. Recorded S01 cost 40,530 tokens (eval/m1-tamagai/results/layer-a-dev.json:90). | Follow observed locations or change discovery strategy; stop repeated actions; validate baseline behavior against real agents. |
| A-12 | high | Layer A / independence | eval/m1-tamagai/run_eval.py:99 | All conditions get records, section boundaries and a definition oracle from the engine under test. Gold chooses pointers and stopping. | Definition lookup calls itself “ground truth from the index” (:126). Missing gold drives continuation (:192), including reads at gold unit starts (:205). docs/m1-plan.md:24 does not freeze this oracle continuation. | Build independent manifest/boundaries; identify the oracle-assisted experiment separately and freeze its policy before use. |
| A-13 | high | Layer A / gates | eval/m1-tamagai/run_eval.py:491 | Accumulated nonblank line unions are scored as complete evidence, rather than one containing span among five results. Only specdex searches get top-five metrics, on a selected mix of categories. Answers and negative/unknown status are not judged. | Summary includes only runs that happened to search (:582); no comparable B0/B1/Stage-A top-five metric. Recorded overall completion A/B/B1 = 23/29/30 (eval/m1-tamagai/results/layer-a-dev.json:12, :25, :52); R3 lookup completion A/B/B1 = 16/20, 20/20, 19/20. Stage A fails docs/m1-plan.md:26; Stage B's gate (:27) cannot be computed comparably. | Score frozen metrics on identical subsets; keep workflow recall separate; judge answers and negative claims. Do not declare gate passage from these summaries. |
| A-14 | high | Layer A / authority | eval/m1-tamagai/run_eval.py:555 | Baseline authority errors are structurally always zero because baselines never populate labelled. Broad current-labelled spans containing forbidden history evade the containment predicate. Retired-claim lists are absent from non_current. | R3 baseline shown forbidden text → authority 0. Containment at :556 misses A-04; registry at :533 omits PRD/EXPERIENCE retired claims. | Judge source use uniformly across answers; use overlap/segmentation and every frozen authority rule. |
| A-15 | high | Replay / evidence | eval/m1-tamagai/replay/replay.py:211 | Any one-line overlap receives full whole-unit credit. Non-unique filename suffixes can credit several files in both evidence and citation scoring. The docstring promises judge input that main does not produce. | R3: prd.md:1034 alone scores S01's full FR-68 section 1.0. Citation paths expand to every matching gold suffix (:222). main writes run records only (:290), not the promised input (:12). External blind judgments/results were not inspected. | Resolve paths uniquely against the corpus; require the agreed evidence criterion; generate the blind judge input or document its separate producer. |
| A-16 | medium | Textual scopes | skills/specdex/scripts/specdexlib/queries.py:402 | Textual bindings are suppressed without an explicit same-family bind elsewhere; otherwise every phrase is offered to that family regardless of its meaning. | R1 sole all FRs binding → definite empty FR-1 refs. R2 OQ-12 refs add line 63: all MVP FRs and NFRs, not OQs. | Return applicable textual scope evidence without requiring explicit examples; separate uncertain scope interpretation from exact citing lines. |
| A-17 | medium | Config freshness | skills/specdex/scripts/specdexlib/config.py:245 | Fingerprint omits effective variables from project config. Classification changes without source-byte changes remain cached. | R1: change planning_artifacts; same fingerprint, zero reindexed; cached role record versus fresh DB unverified. | Include effective variables/config bytes in stamp and generation. |
| A-18 | medium | Identity freshness | skills/specdex/scripts/specdexlib/index.py:82 | Freshness compares path/content hashes, excluding symlink identity and extraction state. | R1 equal-byte first.md → second.md retarget: zero reindexed, canonical remains first.md. | Include identity/link metadata in freshness and invalidation. |
| A-19 | medium | Scoped diff | skills/specdex/scripts/specdexlib/diffing.py:44 | Definitions keyed only by ID overwrite legitimate AD/CAP document scopes. Scoped changes disappear from ID diff/history. | R1: two CAP-1 definitions; edit alpha → changed=[]; only section diff notices it. | Key definitions, positional groups, citations and history by namespace scope plus ID. |
| A-20 | medium | Ranges / ID extraction | skills/specdex/scripts/specdexlib/extract.py:343 | Short ranges silently stop at a hardcoded gap 50 despite profile limit 200. Positional ranges bypass that bound. Invalid suffixed IDs can backtrack into valid parents. | R1: FR-1–60 has one occurrence/no diagnostic; long form has 60. FR-1.1–FR-1.202 expands 202. FR-1.2foo becomes FR-1 (config.py:182). | Use one configured bound for every form, diagnose unsupported ranges and prevent partial matches inside invalid tokens. |
| A-21 | medium | Section get | skills/specdex/scripts/specdexlib/queries.py:305 | doc §2 matches §2.1 and picks its first heading even when exact §2 exists later. | R1 returns 2.1 Child for prd §2. | Match the complete numeric identifier and prefer exact sections. |
| A-22 | medium | Validators / false-clean | skills/specdex/scripts/specdexlib/maintenance.py:138 | Failed/missing validators do not make lint incomplete; process exit status is ignored. Revision lint points adapters at the live workspace. | R2 exit-7 adapter → CLI 0 and no findings, followed by failed on. Workspace at :135 is live regardless of index mode. | Explicitly mark unchecked/incomplete validation, check exit/JSON contracts, and use a snapshot for revision adapters. |
| A-23 | medium | Citation proxies / output | eval/m1-tamagai/run_eval.py:248 | Baseline citation proxies ignore requested exclusions, range expansion and Binds filtering. Specdex instrumentation gets separate uncharged JSON and counts every refs row, potentially beyond the visible page. | Baselines set cited=set(hits) from literal grep. Specdex calls twice (:267, :271); all JSON rows count at :287; text pagination is in render.py:81. No dev citation gold exceeds 60 lines, so pagination inflation is a latent issue here. | Apply prompt/scope filtering equally; score only information actually shown; do not grant extra evidence from instrumentation. |
| A-24 | medium | Layer B controls | eval/m1-tamagai/layer_b.py:426 | Some passes do not establish their broader claim: B09 has existing coverage; B12 repeats IDs only; F6 checks post-edit status only; B13 checks constant disclaimer text. | All 23 rerun PASS. Existing story 1.1 already covers FR-71. B13's only detection condition is states_limit (:488). | Add counterfactual controls, unique-ID ambiguity and concurrent mutation cases; call B13 a limitation-message check. |
| A-25 | medium | Replay accounting / comparison | eval/m1-tamagai/replay/replay.py:162 | Codex counts only completed shell executions, omitting other tool calls/results and automatic skill context. Initial session context is outside tool_tokens. The baseline has no B1 manifest/protocol as planned; Codex model/config are unpinned. | R3 MCP event → zero calls. Claude pins a model; Codex command (:156) does not. Specdex-only guide/overlay (:107) change initial context. B1-style replay is specified in docs/m1-worklog.md:58. | State the measured boundary; parse relevant events/context; pin harnesses; replay the exact proxy condition claimed. Keep harness usage separate. |
| A-26 | medium | Provisional labels | skills/specdex/scripts/specdexlib/extract.py:282 | Child rows/items do not inherit an enclosing section's provisional marker. | R2 size-budget row 186 is [record], while heading 181 is [ASSUMPTION]. Heading path exposes the marker, but flags do not. | Propagate applicable section qualifications into descendant labels. |
| A-27 | medium | Dev labels | eval/m1-tamagai/gold/dev.json:1218 | Some answers need unlabelled evidence; some forbidden spans are current or mixed authority. Citation sets are correct. | Corrections below; every range exists and all six exhaustive sets match. | Correct affected tasks; distinguish wrong-target from non-current traps. |
| A-28 | low | SKILL.md | skills/specdex/SKILL.md:35 | refs does not accept a path suffix as a source target. get budget is chars/4, per-reference and soft, not one shared cap. Absolute never-stale/never-writes claims are contradicted above. | refs takes an ID (cli.py:53); every get reference receives full budget (:113). Absolute claims at SKILL.md:18 and :87. | Correct syntax, budget scope and verified limits; align promises with enforcement. |
| A-29 | low | Generality | skills/specdex/profiles/bmad-6.13.0-next.toml:246 | Range example names Tamagai's ACR family. No executable Tamagai path, registration or project rule was found in core/profile. | Comment ACR-A…ACR-Y; actual registration correctly lives in eval/m1-tamagai/overlay.toml:85. LinkCredential and colors.sleep-dim are explanatory core examples (extract.py:78, yamlfm.py:19), not matching rules. | Replace project examples with neutral ones; keep ACR rules in the overlay. |

## Dev label corrections

All 32 tasks' evidence/forbidden ranges exist. Full evidence-unit/answer review covered S01–S14, E01–E06, C01–C06 and Y01–Y06; citation sets were rederived independently. No correction was found for the remaining task units/citation lists.

GOLD-SPEC.md:52 permits different-ID forbidden traps, while this audit requests non-current-only traps. C04/Y06 therefore expose a contract ambiguity, not misidentified corpus history. Whole CHANGE-REQUESTS rows likewise combine historical request cells and current Decision cells (GOLD-SPEC.md:23).

| Task | Evidence of error | Corrected evidence / citations / label |
|---|---|---|
| S05 | eval/m1-tamagai/gold/dev.json:155: forbidden whole CHANGE-REQUESTS rows 35 and 72 contain current decisions. | Keep evidence unchanged. Remove these whole-row forbidden entries, retaining the stale extract trap; alternatively make request-column-specific labels/scoring. |
| E01 | eval/m1-tamagai/gold/dev.json:472: forbidden whole CHANGE-REQUESTS row 22 contains a current Decision. | Keep evidence unchanged. Remove that entry and retain the three trail traps, or introduce column-aware labels. |
| E06 | eval/m1-tamagai/gold/dev.json:619: do-not-optimize and proposal context are outside the sole SM-C2 item. Context is in eval/corpora/tamagai-2026-10-04/_bmad-output/planning-artifacts/prds/prd-tamagai-2026-09-29/prd.md:1913 and :1929. | Under the existing allowed-unit contract, replace 1931–1931 with whole §13, same path, **1911–1935**. Alternatively narrow the answer to the item or explicitly permit contextual list labels before freezing gold. |
| C04 | eval/m1-tamagai/gold/dev.json:870: forbidden PRD 371 is a current FR-4 memory definition. | Citation set stays **7 lines**, unchanged. Remove PRD 371 from non-current forbidden; preserve it as a typed wrong-match trap/notes. |
| C06 | eval/m1-tamagai/gold/dev.json:991: owner-can-overturn claim lies outside both evidence sections; source is eval/corpora/tamagai-2026-10-04/_bmad-output/planning-artifacts/architecture/architecture-tamagai-2026-10-03/CHANGE-REQUESTS.md:14. | Keep evidence and **5 citation rows (25, 41, 43, 64, 65)**. Remove this unnecessary last answer clause. |
| Y01 | eval/m1-tamagai/gold/dev.json:1073: forbidden whole CHANGE-REQUESTS row 41 contains the current conditional decision. | Keep evidence unchanged. Remove this entry or forbid only historical request cells, permitting its current Decision. |
| Y05 | eval/m1-tamagai/gold/dev.json:1218: neither gold unit supports seven-day retention/FR-70 reporting. | Retain PRD **1014** and addendum **62**; add eval/corpora/tamagai-2026-10-04/_bmad-output/planning-artifacts/prds/prd-tamagai-2026-09-29/prd.md **937–945 (FR-58)** and **1068–1076 (FR-70)**. Four complete units total. |
| Y06 | eval/m1-tamagai/gold/dev.json:1281: forbidden PRD 1049 is current FR-68.3, which the answer correctly describes. FR-94/CQ-32 example also lacks evidence. | Retain CHANGE-REQUESTS **36** and PRD **1050**. Move PRD **1049** from forbidden to evidence; add PRD **1330**, or drop the optional FR-94/CQ-32 example. PRD path: eval/corpora/tamagai-2026-10-04/_bmad-output/planning-artifacts/prds/prd-tamagai-2026-09-29/prd.md. |

Independent citation check: **C01 9/9; C02 6/6; C03 4/4; C04 7/7; C05 21/21; C06 5/5**, no missing/extra lines. C02 includes textual all-MVP/frontmatter range bindings; C03 excludes unnamed sleep-dim descriptions; C04 includes history; C05 excludes only the PRD definition; C06 filters Decision cells including ACR-V's partly conditional decision.

## Layer B case audit

All published pass decisions reproduce. The conclusions are narrower than universal integrity/freshness.

| Cases | Established by control/detection | Limit / possible wrong-reason pass |
|---|---|---|
| B01 | New short-range citing line appears in refs and impact. | No long/positional/invalid ranges. |
| B02–B03 | Specific deletion shifts cited FR-88.3; specific edit reports FR-88.4 only. | Counts/new text not fully asserted; no scoped collisions/complex list combinations. |
| B04 | Same-folder CAP mentions resolve; outside README is ambiguous. | No explicit cross-folder citations or third namespace. |
| B05 | Sole upstream AD resolves; local redefinition flags inherited conflict. | No competing parents; does not prove From-parent field determines target. |
| B06–B07 | Missing companion/absent local E9 flagged against clean controls. | No ambiguous upstream or ownership-bypass case. |
| B08 | File/entry disagreement detected. | Does not assert file coverage wins or inspect exit status. |
| B09 | No-file/no-plan entry labelled planned. | Existing 1.1 already covers FR-71; coverage assertion passes if planned entry contributes nothing (layer_b.py:383, :433). |
| B10–B11 | Reused OQ-26 differs from fresh OQ-27; restored-mtime edit updates results. | One same-file history only; no equal-byte identity/config change. |
| B12 | Copied PRD repeating FR-71 causes ambiguity. | Unique IDs in candidates remain falsely defined. |
| B13 | Lint prints its semantic limitation. | No agent detects/judges contradiction; agent-only 1/1 is a disclaimer check. |
| I1–I4 | Independent equal export stays extracted; equal replicas/internal link alias; drift flags. | I1 is a non-record export, not two independent record owners. No retarget/directory-order case. |
| F1–F3 | Sequential edits, inserted positions and delete/rename update results. | No generation coherence during reads. |
| F4 | Invalid inline list gets diagnostic; body stays searchable. | Does not check negative answers/exit status. |
| F5 | Sequential branch switch and commit lookup see expected keyword. | No branch change during inventory/query. |
| F6 | Two post-edit status processes return one generation. | Control is unconditionally true; no interleaving writer/reader across commits. |

## Reproductions

Run from the repository root. R1/R2 copy fixtures and keep databases under /tmp; R2 corpus queries are read-only. R1's hook schedules actual nested open/update calls without changing repository source.

### R1 — extraction, authority, freshness, scope and diff

~~~sh
PYTHONDONTWRITEBYTECODE=1 python3 -B - <<'PY'
import sys, tempfile, shutil
from pathlib import Path
sys.path.insert(0, "skills/specdex/scripts")
from specdexlib.config import load
from specdexlib.index import open_index
from specdexlib.queries import Queries
from specdexlib import extract, diffing, index

BASE = Path(tempfile.mkdtemp(prefix="specdex-audit-"))
PROFILE = Path("skills/specdex/profiles/bmad-6.13.0-next.toml").resolve()
PRD = "_bmad-output/planning-artifacts/prds/prd-demo-2026-01-01/prd.md"
SPINE = "_bmad-output/planning-artifacts/architecture/architecture-demo-2026-01-02/ARCHITECTURE-SPINE.md"

def project(name):
    root = BASE / name
    shutil.copytree("tests/fixtures/mini-project", root)
    return root, BASE / (name + ".sqlite")

def query(root, db):
    config = load(root, PROFILE, root / "overlay.toml")
    return Queries(open_index(config, db_path=db))

root, db = project("range")
config = load(root, PROFILE, root / "overlay.toml")
for text in ("FR-1–60.", "FR-1–FR-60.", "FR-1.1–FR-1.202.", "FR-1.2foo"):
    facts = extract.extract(config, PRD, text)
    ids = [o.id for o in facts.occurrences]
    print("range", text, len(ids), "FR-42" in ids, ids[:2], facts.diagnostics)

root, db = project("ambiguity")
other = root / "_bmad-output/planning-artifacts/prds/prd-other/prd.md"
other.parent.mkdir(parents=True)
other.write_text("# Other\n\n### FR-99: Other\n\nOther.\n")
q = query(root, db)
print("ambiguity", q.resolve("FR-99").status, [h.role for h in q.resolve("FR-99").definitions])

root, db = project("history")
with (root / "overlay.toml").open("a") as handle:
    handle.write('\n[[historical]]\nartifact="prd"\nsection="Retired"\n')
(root / PRD).write_text("# PRD\n\n## Retired\n\n### FR-99: Old\n\nOld.\n\n## Current\n\nSee FR-99.\n")
q = query(root, db)
print("history", q.resolve("FR-99").status,
      [h.temporal for h in q.resolve("FR-99").definitions],
      [r["status"] for r in q.refs("FR-99", "record", False)[1]])

root, db = project("reader")
q = query(root, db)
(root / PRD).write_text((root / PRD).read_text().replace("CSV", "zebracorn"))
new = query(root, db)
print("reader", q.index.generation != new.index.generation,
      len(q.search("zebracorn", "record", 5)[0]))

root, db = project("inventory")
q = query(root, db)
config = q.index.config
original_files = index.WorktreeSource.files
interleaved = False
writer_generation = None

def interleaved_files(source):
    global interleaved, writer_generation
    inventory = original_files(source)
    if not interleaved:
        interleaved = True
        (root / PRD).write_text((root / PRD).read_text().replace("CSV", "zebracorn"))
        writer_generation = open_index(config, db_path=db).generation
    return inventory

index.WorktreeSource.files = interleaved_files
try:
    late = open_index(config, db_path=db)
finally:
    index.WorktreeSource.files = original_files
print("inventory", late.generation == q.index.generation,
      late.generation != writer_generation, len(Queries(late).search("zebracorn", "record", 5)[0]))

root, db = project("yaml")
(root / PRD).write_text("---\ncompanions: [missing.md\n---\n\n# PRD\n")
q = query(root, db)
print("yaml", q.empty_answer(("record", "ambiguous")),
      [tuple(r) for r in q.conn.execute("SELECT code,severity FROM fdiag")])

root, db = project("phrase")
(root / PRD).write_text("# PRD\n\n### FR-1: Known\n\nKnown.\n")
(root / SPINE).write_text("# Spine\n\n## AD-1: Rule\n\n- **Binds:** all FRs\n")
q = query(root, db)
print("phrase", q.refs("FR-1", "record", False)[1:])

root, db = project("section")
(root / PRD).write_text("# PRD\n\n## 2.1 Child\n\nChild.\n\n## 2 Parent\n\nParent.\n")
q = query(root, db)
print("section", q.get("prd §2", 8000)[0][0].hpath)

root, db = project("diff")
for name in ("alpha", "beta"):
    file = root / f"_bmad-output/specs/spec-{name}/SPEC.md"
    file.parent.mkdir(parents=True)
    file.write_text("# Spec\n\n- **CAP-1** — " + name + " rule.\n")
with (root / "overlay.toml").open("a") as handle:
    handle.write('\n[current]\nrecords=["' + PRD + '","_bmad-output/specs/spec-alpha/SPEC.md","_bmad-output/specs/spec-beta/SPEC.md"]\n')
old = query(root, db)
file = root / "_bmad-output/specs/spec-alpha/SPEC.md"
file.write_text(file.read_text().replace("alpha rule", "CHANGED alpha rule"))
new = query(root, BASE / "diff-new.sqlite")
print("diff", len(old.resolve("CAP-1").definitions), diffing.diff(old, new)["changed"])

root, db = project("variables")
old = query(root, db)
file = root / "_bmad/custom/config.user.toml"
file.parent.mkdir(parents=True)
file.write_text('[modules.bmm]\nplanning_artifacts="_bmad-output/alternate"\n')
cached = query(root, db)
fresh = query(root, BASE / "variables-new.sqlite")
print("variables", old.index.config.fingerprint == cached.index.config.fingerprint,
      cached.index.changed, cached.files[PRD]["role"], fresh.files[PRD]["role"])

root, db = project("retarget")
for name in ("first", "second"):
    (root / ("_bmad-output/" + name + ".md")).write_text("Equal text\n")
link = root / "_bmad-output/link.md"
link.symlink_to("first.md")
query(root, db)
link.unlink()
link.symlink_to("second.md")
q = query(root, db)
row = q.conn.execute("SELECT canonical FROM files WHERE path='_bmad-output/link.md'").fetchone()
print("retarget", q.index.changed, row["canonical"], link.resolve().name)
PY
~~~

Output:

~~~text
range FR-1–60. 1 False ['FR-1'] []
range FR-1–FR-60. 60 True ['FR-1', 'FR-60'] []
range FR-1.1–FR-1.202. 202 False ['FR-1.1', 'FR-1.202'] []
range FR-1.2foo 1 False ['FR-1'] []
ambiguity defined ['ambiguous']
history defined ['historical'] ['resolved']
reader True 1
inventory True True 0
yaml none in a fully indexed scope [('parse-gap', 'medium')]
phrase ([], 'none in a fully indexed scope')
section prd.md › PRD › 2.1 Child
diff 2 []
variables True 0 record unverified
retarget 0 _bmad-output/first.md second.md
~~~

### R2 — safety, adapters and corpus labels

~~~sh
PYTHONDONTWRITEBYTECODE=1 python3 -B - <<'PY'
import sys, tempfile, shutil, io, contextlib, sqlite3
from pathlib import Path
sys.path.insert(0, "skills/specdex/scripts")
from specdexlib.config import load
from specdexlib.index import open_index
from specdexlib.queries import Queries
from specdexlib import coverage, tickets, maintenance, cli, render, store

BASE = Path(tempfile.mkdtemp(prefix="specdex-audit-adapters-"))
PROFILE = Path("skills/specdex/profiles/bmad-6.13.0-next.toml").resolve()

def copy_fixture(name, fixture="mini-project"):
    root = BASE / name
    shutil.copytree("tests/fixtures/" + fixture, root)
    overlay = root / ("overlay.toml" if fixture == "mini-project" else "_bmad/custom/specdex-overlay.toml")
    return root, overlay

def query(root, overlay, db):
    return Queries(open_index(load(root, PROFILE, overlay), db_path=db))

root, overlay = copy_fixture("safety")
outside = BASE / "outside.md"
outside.write_text("EXTERNAL_PRIVATE_TEXT\n")
(root / "_bmad-output/external.md").symlink_to(outside)
q = query(root, overlay, root / "cache.sqlite")
print("project-cache", (root / "cache.sqlite").exists())
print("external-symlink", q.get("_bmad-output/external.md:1", 8000)[0][0].text)
unrelated_db = BASE / "unrelated.sqlite"
with sqlite3.connect(unrelated_db) as connection:
    connection.execute("CREATE TABLE valuable_notes (body TEXT)")
connection = store.connect(unrelated_db)
print("unrelated-table-survives", bool(connection.execute(
    "SELECT 1 FROM sqlite_master WHERE name='valuable_notes'").fetchone()))
connection.close()

script = root / ".agents/skills/bmad-architecture/scripts/lint_spine.py"
script.parent.mkdir(parents=True)
script.write_text(
    "import sys,json\nfrom pathlib import Path\n"
    "Path(sys.argv[sys.argv.index('--workspace')+1],'audit-write.txt').write_text('written')\n"
    "print(json.dumps({'findings':[]}))\n")
maintenance.lint(q, "record", True)
print("validator-write", len(list(root.rglob("audit-write.txt"))))
script.write_text("raise SystemExit(7)\n")
output = io.StringIO()
with contextlib.redirect_stdout(output):
    status = cli.main(["--project", str(root), "--overlay", str(overlay),
                       "--db", str(BASE / "validator.sqlite"), "lint"])
print("validator-failure", status, output.getvalue().splitlines()[0],
      "failed on" in output.getvalue())

for name in ("bypass", "ambiguous"):
    root, overlay = copy_fixture(name, "preview-tickets")
    if name == "bypass":
        story = root / "_bmad-output/initiative-shelf-v1/epic-reading-list/story-add-a-book-by-isbn.md"
        story.write_text(story.read_text().replace("covers: [E1, E2]", "covers: [FR-4]"))
    else:
        prd = root / "_bmad-output/planning-artifacts/prds/prd-shelf-2026-09-15/prd.md"
        prd.write_text(prd.read_text() + "\n### FR-1: Duplicate\n\nDifferent rule.\n")
    q = query(root, overlay, BASE / (name + ".sqlite"))
    chains = [(c.covered_id, c.state, c.target)
              for c in tickets.chains(q, tickets.load_tree(q)) if c.ticket == "1.1"]
    problems = [p for p in coverage.covers(q)["problems"] if p["ticket"] == "1.1"]
    print(name, chains, problems)
    if name == "ambiguous":
        print("ambiguous-source-status", q.resolve("FR-1").status)

root, overlay = copy_fixture("refs", "preview-tickets")
q = query(root, overlay, BASE / "refs.sqlite")
print("covers-refs", q.refs("FR-1", "current", False, "covers")[1:])
print("covers-coverage", [r["state"] for r in coverage.coverage(q, "tickets", ["FR"])["rows"] if r["id"] == "FR-1"])

root = Path("eval/corpora/tamagai-2026-10-04").resolve()
q = query(root, Path("eval/m1-tamagai/overlay.toml"), BASE / "corpus.sqlite")
for ref in ("addendum §1", "addendum §1.9", "prd-tamagai-2026-09-29/addendum.md:186"):
    hit = q.get(ref, 8000)[0][0]
    print("corpus-label", ref, hit.start, hit.end, render.labels(hit))
print("OQ-12-textual", [(r["line"], r["raw"]) for r in q.refs("OQ-12", "record", False)[1] if r["status"] == "textual"])
PY
~~~

Output:

~~~text
project-cache True
external-symlink EXTERNAL_PRIVATE_TEXT
unrelated-table-survives False
validator-write 1
validator-failure 0 lint (scope record): no findings True
bypass [('FR-4', 'resolved', 'FR-4')] []
ambiguous [('E1', 'resolved', 'FR-1'), ('E2', 'resolved', 'FR-1')] []
ambiguous-source-status ambiguous: several definitions in one scope
covers-refs ([], 'none in a fully indexed scope')
covers-coverage ['declared']
corpus-label addendum §1 21 116 [record]
corpus-label addendum §1.9 109 116 [record; historical]
corpus-label prd-tamagai-2026-09-29/addendum.md:186 186 186 [record]
OQ-12-textual [(63, 'all MVP FRs and NFRs')]
~~~

### R3 — evaluation policy and replay scoring

**Logic only:** the stub avoids installing tiktoken and cannot establish costs. Harness mains are not run; DB is under /tmp; only dev gold is read; replay results are never accessed.

~~~sh
PYTHONDONTWRITEBYTECODE=1 python3 -B - <<'PY'
import sys, types, importlib.util, json
from pathlib import Path
# Logical-policy checks only; no token measurements use this stub.
sys.modules["tiktoken"] = types.SimpleNamespace(
    get_encoding=lambda _: types.SimpleNamespace(
        encode_ordinary=lambda text: [], encode=lambda text, **kwargs: []))

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result

layer = module("audit_layer", "eval/m1-tamagai/run_eval.py")
layer.DB = Path("/tmp/specdex-audit-layer-a.sqlite")
corpus = layer.Corpus()
task = next(t for t in json.loads(Path("eval/m1-tamagai/gold/dev.json").read_text()) if t["id"] == "S01")
run = layer.B0(corpus).answer(task)
print("B0", len(run.outputs), len(set(run.outputs)),
      layer.score(task, run, corpus)["evidence_recall"])
bad = task["forbidden"][0]
run = layer.Run("B0")
run.show(bad["path"], bad["start"], bad["end"])
print("baseline-authority", layer.authority_errors(task, run, corpus))
saved = json.loads(Path("eval/m1-tamagai/results/layer-a-dev.json").read_text())
lookups = [row for row in saved["tasks"] if row["category"] in ("section", "exact")]
print("lookup-complete", [(condition,
    sum(row["conditions"][condition]["evidence_recall"] == 1 for row in lookups),
    len(lookups)) for condition in ("specdex-A", "specdex-B", "B1")])

replay = module("audit_replay", "eval/m1-tamagai/replay/replay.py")
unit = task["evidence"][0]
print("replay-heading", replay.score_evidence(f"prd.md:{unit['start']}", task)[1])
print("replay-suffix", replay.score_citations("prd.md:1", [
    {"path": "one/prd.md", "line": 1}, {"path": "two/prd.md", "line": 1}]))
run = replay.Run("test", "codex", "specdex")
event = {"type": "item.completed", "item": {"type": "mcp_tool_call",
         "server": "docs", "tool": "read", "arguments": {"text": "x"},
         "result": {"text": "y"}}}
replay.parse_codex([json.dumps(event)], run, Path("/tmp/audit-workspace"))
print("replay-mcp-calls", run.calls)
PY
~~~

Output:

~~~text
B0 12 2 0.0
baseline-authority 0
lookup-complete [('specdex-A', 16, 20), ('specdex-B', 20, 20), ('B1', 19, 20)]
replay-heading 1.0
replay-suffix (1.0, 1.0)
replay-mcp-calls 0
~~~

### Existing suite and Layer B

~~~sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 python3 -B eval/m1-tamagai/layer_b.py --only B01 B02 B03 B04 B05 B06 B07 B08 B09 B10 B11 B12 B13 I1 I2 I3 I4 F1 F2 F3 F4 F5 F6 --no-latency
python3 -B eval/m1-tamagai/corpus_lock.py
~~~

Outputs: **105 tests, OK**; all **23 cases PASS**, summary deterministic **12/12**, identity **4/4**, freshness **6/6**, disclaimer **1/1**, false_clean=[]; **corpus OK**. Explicit --only suppresses the Layer B report write (layer_b.py:720). Tests/Layer B create temporary Git repositories; this repository's Git state was not changed.

## Checked and found sound

- Frozen corpus lock matches. All dev ranges exist; six citation sets independently match regex/range/table-cell scans. Request-versus-Decision authority was checked directly.
- Unit suite and all Layer B pass decisions reproduce, within the case limits above. Latency code measures complete CLI calls including verification (eval/m1-tamagai/layer_b.py:663); recorded 0.124 s warm p95 / 1.793 s rebuild satisfy the 1× SLO, but latency was not rerun.
- Index replacement, FTS updates and derivation use BEGIN IMMEDIATE with rollback. Schema version is actually read/stored and rechecked under the schema lock (skills/specdex/scripts/specdexlib/store.py:63, :72). Failures above concern inventory timing/read isolation/invalidation, not absence of a transaction.
- Document-derived SQL values are parameterized in queries/coverage; FTS terms are tokenized and quoted. No shell execution was found; Git uses argument arrays (skills/specdex/scripts/specdexlib/sources.py:73). Dynamic schema table names come from cache metadata, not Markdown. Validator execution is the exception to source-only behavior.
- Launcher suppresses bytecode writes (skills/specdex/scripts/specdex.py:13). Source scanning/ordinary retrieval contain no spec-writing operation. Scope-role filtering, unique get/outline suffix matching, ordinary same-file history evidence and simple appended/edited/shifted positional cases have passing tests.
- No executable Tamagai record paths, additional-family registrations or positional/historical project rules found in core/profile; those live in the overlay. Layer A uses one o200k_base output tokenizer for all conditions. Omitting tool inputs from its main total follows the frozen output-only policy; it is not a tokenizer mismatch.

Unchecked: sealed held-out results, replay transcripts/results, external blind judgments, 10×/100× SLOs and live Tamagai. No conclusion about them is implied.
