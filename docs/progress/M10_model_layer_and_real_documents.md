# M10: a hosted model option, and requirement documents as people really write them

I did two things in this step. Both come from the same question: what happens when ReviewPulse meets input we did not write
ourselves, a model we do not run, and a requirement document that is forty pages of prose, tables and lists.

## Part 1. Using a hosted model without giving up control

**What a user gets.** The local model stays the default and reads every clause. A hosted model (a free API such as Groq or
OpenRouter, or any service that speaks the common chat format) can be added as a second opinion, and it is asked only about
the clauses the local model could not turn into a checked rule.

**Why it is safe to add.**
- The hosted answer goes through exactly the same checks as a local one: sentence check, catalogue check, plain-words
  reading, human approval. A stronger model needs no extra trust, so the guarantee that an unknown is never a pass is kept.
- Nothing is sent unless the reviewer switches it on for that project (`external_consent`). It is off by default.
- What leaves the machine is the clause text and the list of declared fact names. Never the plan, never the drawing, and the
  document's file name (which may name a client) is replaced by the word "document".
- The API key is read from the environment or a `.env` file, is never written into an error message, and `.env` is not
  committed.
- A clause read by a hosted model is marked as such in the result (`model`, `external`, `escalated_from`), so a reviewer
  and the coverage report can see who wrote each rule.

**How it works.** One client for every provider that offers the common chat format (`llm/openai_compat.py`). It asks for a
strict JSON schema first, falls back to a looser JSON mode and then to plain text if the provider refuses, waits out rate
limits (it obeys Retry-After and paces itself under the provider's per-minute cap) and treats a cut-off answer as an error
rather than guessing. An answer cache (`llm/cache.py`) means a clause read once is never paid for again and a demo can be
replayed without any network.

**Provider choice.** Free tiers differ in what they do with your text. I wrote what each provider's own pages say into
`llm/config.py` and show it next to the consent switch. As of November 2026: Groq says it does not retain or train on inputs;
OpenRouter does not log prompts by default; Google's free tier may use prompts to improve its products and have people read
them, so it is not suitable for a confidential document; Mistral's free mode may train unless you opt out. Terms change, so a
reviewer must read the current terms before allowing a document out.

**Setup.** In a `.env` file in the folder you run from:

```
REVIEWPULSE_FALLBACK=openai
REVIEWPULSE_FALLBACK_PROVIDER=groq
REVIEWPULSE_FALLBACK_API_KEY=your key here
```

Then in the Requirements tab of a project, allow hosted help for hard clauses.

**What is not measured yet.** I have no API key in this environment, so I have not measured how much a hosted model improves
the results. The mechanism, the privacy rules and the cascade are tested with a mock provider (`tests/unit/test_llm.py`). The
comparison script is the next step and the numbers will go here when it has been run with a key.

## Part 2. Real requirement documents

I probed the clause splitter with six documents written in six styles. It failed badly:

| Document style | Clauses found before | Clauses found now |
| --- | --- | --- |
| Plain prose, no numbering | 0 | one per sentence |
| Legal nesting, `Rule 5 (1) (a)` | 0 | full hierarchy |
| Codes and bullets, `REQ-001`, `-` | 0 | all |
| Numbers repeated in an appendix | crashed on duplicate ids | distinct ids |
| French with `§` and `Art.` mixed | half | all |
| Table thresholds | rows lost from their header | rows kept with their header |

**What changed** (`rules/clauses.py`, `interpreter/context.py`):
- **Structure is detected by shape, not by one numbering scheme.** A word and a number (`Rule 5`) counts as structure only
  when that word starts several lines, which is what real numbering looks like and prose does not. Codes, `1.2.3`, `(1)`,
  `(a)`, `(ii)`, `§ 3` and bullets are all understood, and their depth decides who is whose child.
- **Text no marker owns is not lost.** A preamble, prose under a heading, or a document with no numbering is cut into
  paragraphs and sentences. Abbreviations ("Art.", "e.g.") and decimals do not end a sentence; a unit such as "30 m." does.
- **A wrapped line is not a clause number.** "30 m to reach an exit" on a new line is text, not clause 30.
- **Repeated numbers get distinct ids**, told apart by the heading they sit under, so the interpreter no longer refuses a
  document.
- **Tables keep their header.** A row is a clause whose parent is the table header, so the threshold travels with the rule
  that points at it, and "Table 2" is never mistaken for clause 2.
- **Definitions travel with every clause.** "A habitable room means a bedroom, a living room or a kitchen" is a definition,
  not a rule to check, and it is included in the context of every clause.
- **A clause that names another by its code** ("see REQ-002") is linked to it.
- **PDF.** Repeated headers, footers and page numbers are dropped, and words split over lines by a hyphen are joined.
- **Word.** List numbers and heading levels live outside the text in a Word file; they are put back so the structure shows.
- **Titles are not rules.** A short numbered line with no figure and no obligation ("2 Requirements") is not offered for
  reading.

**How it is measured without annotation.** `xeval/doc_styles.py` writes the same eight requirements in eight document styles
and checks that none is lost or merged with another, and that a table row reaches its header and the definitions. All eight
styles pass (`tests/unit/test_requirements_hard.py`). This measures the structure step only; it says nothing yet about how
well a model reads a long document.

## Part 3. Long documents take long

Reading a 24 clause document with the local model took about 15 minutes. Two changes help: clauses are read in parallel when
the model is a hosted one (a local model answers one question at a time, so it stays at one; override with
`REVIEWPULSE_DRAFT_WORKERS`), and the answer cache means a second pass costs nothing.

## Known limits

- Scanned PDFs (pictures of text) need text recognition first; they are not read yet.
- Two-column PDFs depend on the reading order the PDF library reports.
- A requirement that spans two sentences ("Rooms must be ventilated. In kitchens the rate is doubled.") is cut in two; the
  second sentence is read without the first.
- An exception that sits in a separate paragraph ("This does not apply to storage rooms") is not yet attached to the clause
  it modifies.
- Hosted-model quality is unmeasured (see above).
