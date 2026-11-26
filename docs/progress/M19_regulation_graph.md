# M19: the regulation graph (step 5, first half)

This is the first half of step 5 of `docs/PLAN_general_reviewpulse.md`. The second half, the normative form (the logical tree of a
clause), is not started. Here I read a requirement document as a graph, with rules and no model, so that a clause can be handed to
a model together with everything the document itself says about it.

## What I built

Everything is new files. Nothing existing was edited.

| File | What it is |
| --- | --- |
| `src/reviewpulse/regs/graph.py` | the graph: nodes, typed edges, `build_graph`, `resolve_context` |
| `src/reviewpulse/regs/cues.yaml` | every word that depends on a language (English, French, German, Spanish today) |
| `src/reviewpulse/regs/synthetic.py` | documents with a known structure, in four languages, that can be renumbered and moved |
| `scripts/reg_graph_audit.py` | the measures below |
| `tests/unit/test_regulation_graph.py` | 26 tests |

**Input.** The text and the clauses that `rules/clauses.py` already produces (`split_document` or `split_cached`). I do not change
the splitter and I do not bump its version. The split of the nine real documents comes from the cache of M14 that is still valid
for the current splitter (`reports/m14_split_cache2`; the folder `reports/split_cache_m14` named in the brief does not exist on this
machine, the content is the same).

**Nodes.** A clause, a table (a table header that has a caption), a definition (a span: the entry of a glossary, or a quoted term
followed by "means"), an exception (a span: an "Exception 1." paragraph, a clause that begins with "Exception", or a sentence that
holds an exception cue).

**Edges.** Five types, one direction for all of them: an edge runs from a provider to a consumer and says what the provider gives
the consumer.

| Type | The provider is | Read from |
| --- | --- | --- |
| `reference` | the cited clause | "see 3.4", "in accordance with 206.2.9", "paragraphs 3.6 to 3.23" |
| `table_of` | the table | "Table B4", "tableau 3", "Tabelle 2" |
| `definition_of` | the definition | a defined term used in the clause, or "as defined in", "définis à l'article 4" |
| `exception_of` | the exception | "except as provided in 1011.5", "Exception 1.", "unless ...", "sous réserve de l'article 5", "notwithstanding 4.1" (this one runs the other way: the citing clause is the exception) |
| `condition_from` | the clause that holds the condition | "where the conditions of 4.2 are met" |

Each edge keeps its evidence: the clause and the character span where it was read (the quote is `text[start:end]`), the cue words
that decided its type, a short reason, and a status. A reference is never forced: it is `resolved`, `first_of_many` (the label is
carried by several clauses, the first is taken and the status says so), `group` ("Section 3" or "206" is a set of clauses numbered
3.x or 206.x, the first one is the head), `anchor` (the label starts a line inside a clause the splitter did not cut), `partial`
("regulation 7(3)": 7 found, the sub-item not), `external` (it names another document: "Regulation 7 of the Building Regulations
2010", "BS 9991", "du code de la construction") or `unresolved`.

**The function.** `resolve_context(graph, clause_id, depth=1)` returns, for one clause, the referenced clauses, the definitions of
the terms it uses, the tables it cites (with their rows), the exceptions that attach to it (both the ones it cites and the ones that
override it), the clauses that hold its conditions, and what could not be resolved or is external. Each is a `Link` with the source
span and quote, the target clause and span, the cue and the reason. `depth` 2 or more follows the same links one level further
(an exception of an exception); `via` names the path. On the ADA, clause 403.5.1 comes back with its two "Except as provided in"
clauses and its own "EXCEPTION:" paragraph; clause 208.2 comes back with section 502 as a group, Table 208.2, three exception
clauses and four definitions (site, facility, spaces, accessible).

**Language free.** The code has no word of any language. Part words (article, section, paragraph, table, figure, appendix,
regulation) are grouped by what they mean, and the cues for reference, exception, override, condition, definition, "another document"
and units are lists in `cues.yaml`. `load_cues(extra={...})` adds words without touching the file; a test reads an Italian sentence
after adding one phrase and one part word, and no code.

## How it works, in the order it runs

1. Every clause gets the labels it can be cited by, from its caption or its first words ("3.79", "Art. 5", "Table B4", "§ 35.151",
   "B26", "Advisory 206.2.8"). A table written under a caption line is named by that caption. Rows of tables and bullets that merely
   start with a label are not parts.
2. References are found by a part word followed by a label (with lists and ranges: "articles 5 et 6", "paragraphs 3.6 to 3.23"), or by
   a reference cue followed by a dotted label ("see 3.4"). Contents and index clauses (many different places named, no obligation)
   are skipped, and so are caption lines of tables.
3. Each reference is typed from the words that come before it in the same sentence (override, exception, definition, condition, table,
   plain), then resolved: exact label, then a clause the splitter renamed, then a group, then a line anchor. A reference followed by
   the name of another law or standard, or preceded by an acronym of another code ("FBC-B Table 1604.5"), is external when it does not
   resolve exactly.
4. Exceptions are added: clauses that begin with "Exception", "Exception 1." paragraphs inside a clause, and sentences with an
   exception cue and no citation.
5. Definitions are read only in two shapes, to keep them exact: a quoted term followed by a definition cue, and the entries of a
   glossary (a heading such as "Defined Terms" or "Key terms", then "Term.  Definition" or "Term Definition" paragraphs). A term that
   is used in another clause becomes an edge, once per term and clause, the longest term first.

It takes about two seconds on the 2,775 clauses of the ADA.

## What I measured

No label was used for the real documents. Command: `python scripts/reg_graph_audit.py` (about 8 s with the cache; the old table
reference audit takes minutes on the ADB and its answer is kept in `reports/reg_graph/compare_cache.json`).

### The nine real documents

| Document | Clauses | Edges (ref / table / definition / exception / condition) | References | Exact | Approximate | External | Unresolved |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ADA 2010 | 2,775 | 3,278 (867 / 41 / 2,033 / 334 / 3) | 1,096 | 585 | 367 | 49 | 95 |
| UK ADB vol 1 | 2,014 | 2,005 (576 / 200 / 1,095 / 109 / 25) | 954 | 636 | 185 | 33 | 100 |
| FR arrêté 2014 | 75 | 5 | 15 | 3 | 0 | 8 | 4 |
| FR AQC fiche | 71 | 0 | 4 | 0 | 0 | 0 | 4 |
| FR CAUE | 76 | 1 | 1 | 0 | 0 | 0 | 1 |
| US Allentown checklist | 45 | 3 | 3 | 0 | 0 | 0 | 3 |
| US St Pete checklist | 132 | 0 | 3 | 0 | 0 | 3 | 0 |
| US Berkeley, US Bloomfield checklists | 28, 93 | 0 | 0 | 0 | 0 | 0 | 0 |

"Approximate" is a group (ADA 358, ADB 111), a line anchor (ADB 52), a first of several (7, 13) or a partial (2, 9).

**Share of references that resolve to a node, among those that name a place in the document** (exact plus approximate, over
exact plus approximate plus unresolved; external ones are left out because they point elsewhere on purpose): **ADA 90.9 percent
(exact only 55.9), ADB 89.1 percent (exact only 69.1)**. The French arrêté resolves 3 of 7 (the four others are annexes I, II, III
and 2, which are not in the text I have). I give the exact-only figure next to the other because a group is a coarser answer: "in
accordance with 404" lands on the first of the 30 clauses numbered 404.x, which is the right place and not a single clause.

Against the two earlier audits, on the same cached split:

| | Earlier audit | The graph, on the same references |
| --- | --- | --- |
| `split_audit.py` references | ADA 62 of 62, ADB 57 of 57 | ADB: 57 of 57 found, 55 resolved. ADA: 38 of 62 found, all 38 resolved |
| `table_refs.py` | ADA 28 of 28, ADB 165 of 168 (the 168 are targets per clause) | ADA: 41 of 42 table mentions become a `table_of` edge, 41 reach a table. ADB: 197 of 234 mentions become an edge, 194 reach a table |
| A simpler method (regex on "Section N", resolved when a clause id equals N) | ADA 55 of 58, ADB 53 of 53 | the graph reports 1,096 and 954 references, and says for each what it is |

The 24 ADA references of the splitter audit that the graph does not carry are, for most, clauses that say "in accordance with"
followed by their own number (a scoping clause 206.4 that cites 206.4 is a self reference, which I drop) and two "See 28 CFR
35.150" (another document). I did not count them one by one; I read the list of the missed ones. About 37 ADB table mentions do not
become an edge: they sit in index and contents clauses, which I skip on purpose. So the graph does not lose what the earlier audits
counted, it finds more places named (1,096 and 954 against the 58 and 53 of the regex), and every edge has a type and a source
span, which the regex does not give. More found is not more right: the hand reading below is the check on that.

**Unresolved cases, read.** ADA 95: 50 are "Chapter N" or "Chapters 1 and 2" (the splitter makes no node for a chapter heading, so
nothing can be reached), 21 are "Figure 305.7" and the like (figures are drawings, they are not clauses), 8 are "appendices B and
D" of other regulations, 7 are "paragraph (b) of this section" whose enclosing section is a heading the splitter did not cut, and
the rest are "section 4.1.3(5)" of a 1991 standard, "Section 508", and a character the PDF reader garbled ("§" shown as a
question mark). ADB 100: about 70 are appendix references, nearly all inside index entries ("Definition Appendix A",
"Appendix D4, Diagram D1"; my index filter does not catch every index clause, and there is no node for Appendix A itself), 12 are
Diagram D2 to D6 whose captions are not in any clause, 6 are "clause 9.3.4" and "Table 9" that belong to BS 9990 (cited in a
paragraph that names only the standard before) and the rest are laws ("section 33 of the Prison Act 1952", "Schedule 4") that my
list of external nouns does not cover. The checklists hold three table references to the IRC and FBC, which are other documents (St
Pete is marked external, Allentown stays unresolved because nothing in the line names the code). I did not hide any of these: they
are in `reports/reg_graph/reg_graph_audit.json` with their context.

**Exception edges found.** ADA 421: 197 "EXCEPTION:" or "EXCEPTIONS:" paragraphs inside a clause, 25 clauses that begin with
"Exception" and attach to the clause before, 35 reached through a cue and a citation ("Except as provided in 403.5.2 and 403.5.3"),
77 sentences with an exception cue and no citation. ADB 109: 19 through a citation, 90 sentences with a cue. The French arrêté 2 ("à
l'exception du cabinet d'aisances"), the CAUE 1 ("sauf lorsque ces éléments ouvrent directement sur un escalier"), Allentown 3.
The sentence-level ones have the exact words as their span, but about a third are exclusions inside a description and not rules
that remove an obligation (see the hand reading).

**Definition coverage.** ADA: 71 terms (the glossary of 106.5), 68 are used, and 1,113 of 2,487 body clauses use at least one.
ADB: 71 terms (the glossary of Appendix A, which sits mostly outside any clause and which I read from the text), 64 used, 592 of
1,285 clauses. The glossary region of the ADB holds 78 paragraphs that start like an entry; 67 terms were read from it. The missing ones
have a term followed by a long parenthesis ("Height (of a building or storey for the purposes of ...)"), or are headings and page
headers. French and checklists define no terms, so nothing is found there. A first version of this reader found only 30 ADB terms because a
page number stopped the glossary at the end of the first page; I found that by counting the entries against the paragraphs of the
text, then fixed it.

### Synthetic documents in English, French, German and Spanish

Six sections of five clauses, with planted references, exceptions through a citation, tables, conditions, defined terms, inline
exceptions, a reference to another law, a dangling reference and plain numbers ("2.5 m"). Five seeds, so 166 planted edges per
language and wording. The cues were written first; a second wording of every cue (`held_out`) was chosen before I checked the file
against it.

| | Precision | Recall |
| --- | --- | --- |
| Graph, first wording, en / fr / de / es | 1.00 / 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 / 1.00 |
| Graph, second wording, en / fr / de / es | 1.00 / 0.98 / 0.99 / 0.83 | 1.00 / 0.99 / 1.00 / 0.83 |
| Graph, second wording, Spanish, after adding one phrase ("con excepcion de") to the cue list, no code | 0.99 | 1.00 |
| Baseline (regex on "Section N"), untyped links, en | 1.00 | 0.14 (23 of 166) |
| Baseline, fr / de / es | none found | 0.00 |

The perfect score on the first wording is partly because I wrote both the generator and the cue list; read it as "the machinery
works", not as a score on text I did not write. The second wording is the honest one: it reaches 0.83 recall in Spanish before
the missing phrase is added. The baseline finds no typed edge at all, and finds a reference only when the document says "Section".
The remaining errors of the second wording are "se reporter au" and "gemäß" not counted as reference cues, so that a table
citation after an exception is typed as an exception.

### Metamorphic checks

* Synthetic, four languages: the same structure written with every number moved by 40, part words rotated, sections written in the
  reverse order and renumbered, both at once. In all 12 cases the set of edges (named by the marker of each clause, not by its number)
  is identical.
* Real text: the first 120,000 characters of the ADA and of the ADB, every dotted number moved (3.79 becomes 503.79, 206.2.8 becomes
  706.2.8, except before a unit) and "Section N" with it, then split again and rebuilt. ADA: 29 of 29 edges kept, 2 new. ADB: 149 of
  161 kept, 12 lost, 0 new. The 12 lost are references to a whole section ("Section 7"), whose head is the first clause carrying a
  label of that section, and the numbers followed by a unit that my transform leaves in place change which clause is first. That is a
  limit of the transform and of "group" targets, not a proof of failure, but I count them as lost.

### Edges read by hand

I read 51 edges drawn at random from the three documents that have any (20 citations, 14 exceptions, 17 definitions; fewer
exceptions and definitions because the sample is spread over documents, and the smaller ones have few). I wrote the code and the
grades, so this is not blind. The sample was drawn before the late fixes listed under the losses, one of which removed the single
wrong edge.

| Class | Right | Partial | Wrong |
| --- | --- | --- | --- |
| Citations (reference, table, condition) | 18 | 2 | 0 |
| Exceptions | 8 | 5 | 1 |
| Definitions | 16 | 1 | 0 |
| Total of 51 | 42 | 8 | 1 |

The partial ones: two groups whose head clause is a poor representative ("Section 7" lands on a table fragment "7.5 max.",
"Appendix C" on its first paragraph); five exceptions whose span is cut at an abbreviation ("min.") or that are exclusions inside a
description ("but excluding the cleansing procedure", "unless otherwise specified"), one exception that cites a sub-item that is not
a clause, and a defined term that is a generic word used in a compound ("sign space" linked to the definition of "space"). The wrong one
was "Schedule 4 to the Building Regulations" read as a group of clauses numbered 4.x. After the sample I read 24 more definition
edges of the ADB, once its glossary was complete: 22 right, 2 partial ("control rooms" linked to "room", a title in a bibliography).
That second reading is also by me.

## Losses and limits

* **Groups are coarse.** 358 ADA references and 106 ADB references land on a group, and their head is the first clause of the group,
  sometimes a poor one. The context function returns the head only; a model that needs the whole section has to ask for it.
* **The splitter limits the graph.** Chapter headings, most diagrams and the whole text of some glossary pages are not clauses, so the
  references to them stay unresolved or fall back to a line anchor. I did not change the splitter.
* **External detection is a list.** A reference to a law that is not in my list of nouns, or to a standard named only once before in
  the paragraph (BS 9990), stays unresolved, never external.
* **Index pages.** My index filter needs four different places and no modal verb; the ADB index leaks about 40 unresolved
  references, which are real mentions of places but of no use to a requirement.
* **Exception spans end at a full stop**, so an abbreviation cuts one short, and a sentence cue is often an exclusion inside a
  description, not a rule. They are marked as such by their reason, never as references to another clause.
* **Typing by the words before the reference.** A citation after an earlier cue in the same sentence is typed by the nearest cue; I
  repaired the common case ("except as provided in 4.5 (see 3.3)"), not every case. "gemäß" and "nach" are weak cues.
* **Defined terms are exact but plain.** Matching is by words (with a plural), the longest term first. A generic term ("space", "room")
  is linked inside compounds that do not mean it. Terms defined inside running text without quotes ("X means ...") are not read: it
  would have taken verbs of definition that are also nouns ("means of escape").
* **French and German are measured only on synthetic text and on three short French documents** with 1 to 15 references each. I have
  no real German or Spanish document, so for those two languages the only evidence is the synthetic one.
* **Late fixes were made after the first sample**: a year after a part word ("Building Regulations 2010", 131 false edges, fixed
  before the sample), table rows and bullets as labels, "point 60 inches", numbered Schedule or Part as groups, the glossary cut by
  page numbers, the roman numeral annexes of the French text, and the index filter (it dropped real requirement clauses that had no
  "shall" or "should"; now it asks for few words per place named). The audit numbers above are from the final code. The 51 edges
  were graded on the code before the last five of these fixes, and I did not grade them again; only the 24 ADB definitions were
  read after the glossary fix. The hand reading is therefore a check of the method, not of the exact final output.
* The **normative form** (applicability, requirement, exceptions as a logical tree) is the second half of step 5 and is not touched.
  This graph gives that step its input, the exceptions and the definitions with their spans.

## Reproduce

```powershell
$env:PYTHONPATH = "src"; $env:SPLIT_CACHE = "reports\m14_split_cache2"; $env:REVIEWPULSE_LABEL_LLM = "0"
python scripts\reg_graph_audit.py data\real_docs --out reports\reg_graph --sample 20 --seed 11
python -m pytest tests\unit\test_regulation_graph.py
```

`reports/reg_graph/sample_for_hand_reading.txt` holds the edges I read, with their words. `reports/reg_graph/context_examples.json`
holds one resolved context per document.

```python
from reviewpulse.rules.clauses import split_cached
from reviewpulse.regs import build_graph, resolve_context
full, clauses = split_cached(path, cache_dir)
graph = build_graph(full, clauses)
ctx = resolve_context(graph, "208.2")      # ctx.references, .definitions, .tables, .exceptions, .conditions, .unresolved, .external
```
