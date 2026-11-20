# Local Document Agent — User Manual

## 1. What you now have

The configured input folder has a new **`mock-workspace/` collection containing
18 populated, fictional documents**:

- 10 Markdown files.
- 4 plain-text files.
- 4 plain-text email files.

It describes a fictional Harbor project: plans, meeting decisions, budgets, risks,
tasks, contacts, approval rules, and related email. Some older records are explicitly
superseded, so you can practice comparing versions instead of treating every file
as equally current.

**These files are reference material, not model training.** The agent learns about
their contents for a conversation only when it searches and reads them. There is
no embedding index, permanent learning, mailbox connection, or long-term memory.

All names, amounts and addresses are fictional. Addresses use `example.invalid`.
The collection's snapshot date is **20 November 2026** and times are **UTC**.
When asking about deadlines, use that explicit date rather than "today."

## 2. Start the agent

From the `SecMate-PoC` workspace directory in PowerShell:

```powershell
.\local-document-agent\.venv\Scripts\local-document-agent.exe
```

Or, from `local-document-agent/`:

```powershell
$env:UV_NO_ENV_FILE = "1"
.\.tools\bin\uv.exe run --frozen --no-sync local-document-agent
```

You need the private app-local `.env` configured with the OpenRouter key and
transmission consent. Do not paste your key into chat. See `README.md` for setup.

### Commands

| Command | Effect |
|---|---|
| `/help` | Show basic help. |
| `/new` | Clear conversation/source memory and start a new session. |
| `/exit` | Exit. |
| Ctrl+C | Cancel active inference; at the input prompt, exit. |
| EOF | Exit. |

Use one ordinary message per `you>` prompt. Markdown tables may appear as raw
Markdown in the terminal; that is normal, not a separate graphical frontend.

## 3. Understand the folders first

Current workspace configuration:

```text
local-document-agent/
├── data/
│   ├── input/
│   │   ├── test.txt                    # Existing file; left untouched
│   │   └── mock-workspace/             # New fictional collection
│   └── output/                        # Reports and unsent drafts
├── examples/
│   └── mock-workspace/                 # Reusable fictional source copy
├── USER_MANUAL.md
└── .logs/errors.log                    # Sanitized diagnostics, when initialized
```

- **Input is read-only to the agent.** You add documents using your editor or file
  manager. The assistant cannot create or edit a document in input.
- **Output is create-only to the agent.** It saves new `.txt`/`.md` files there.
  It cannot overwrite existing files, edit originals, or delete files.
- Outputs are not readable through its input tools. To analyze an output later,
  inspect it yourself or manually copy it into input under a new, unused name.
- Paths in chat are relative to input and use `/`, not Windows `\`.
- Do not give it full disk paths or ask it to search the rest of your computer.

For example:

```text
Read mock-workspace/projects/harbor/overview.md.
```

To create a file, say:

```text
Save a new text report named hello-v1.txt containing "Hello from the demo" in the output folder.
```

Do **not** ask it to create that file in input. The application prevents it even
if a model's conversational wording suggests otherwise.

### Optional: isolate the fictional collection

The current input root also contains your existing `test.txt`. Full-text search
can inspect other supported files in the selected input root, not just the file
names mentioned in a question.

If you want only these fictional files available, privately set:

```dotenv
DOCUMENT_INPUT_DIR=./data/input/mock-workspace
DOCUMENT_OUTPUT_DIR=./data/output
```

Then restart the CLI. For that configuration, **remove `mock-workspace/` from all
example paths below**: use `projects/harbor/overview.md`, for example.
Do not make output a child of input or overlap the two roots.

Configuration changes require a restart. Adding new input documents usually does
not: the tools inspect files when invoked. `/new` helps avoid relying on earlier
conversation content after you change a document.

## 4. Discover the collection

Start with a fresh session:

```text
/new
Read mock-workspace/00-workspace-guide.md and briefly explain what information is available. Cite the file you read.
```

List the collection without reading every body:

```text
Find up to 20 files whose relative path contains "mock-workspace" using filename search. List their paths; don't read all their contents yet.
```

Find email:

```text
Find filenames containing ".eml" under mock-workspace and list the matching paths.
```

Find budget documents:

```text
Find filenames containing "harbor-budget". Tell me which files are available.
```

Find information by text:

```text
Search document text for "workshop". Show the matching filenames and short snippets.
```

Search is **literal and case-insensitive**, not semantic. If one term finds
nothing, try a related term such as `training` or give the exact path.
`*.eml` is not a wildcard query, and regular expressions are not supported.
Search snippets are discovery material; ask the agent to read the relevant files
before presenting a substantive summary.

## 5. Read, summarize and extract information

### Summarize one document

```text
Read mock-workspace/projects/harbor/overview.md. Summarize the goal, confirmed schedule, proposed dates, owners, and unfinished work. Cite source references.
```

### Extract tasks

```text
Read mock-workspace/projects/harbor/action-items.txt. As of 20 November 2026, list open items due by 25 November in a table: ID, action, owner, due date, and dependency. Don't treat obtaining a quote as approving a purchase.
```

### Find owners and contacts

```text
Read mock-workspace/people/team-directory.md and mock-workspace/projects/harbor/action-items.txt. Who owns the participant guide, training coordination, and spending approval? Cite the relevant files.
```

### Ask a narrow follow-up

```text
Which of those actions depends on the participant guide being approved?
```

Recent conversation context can support follow-ups, but it is bounded. If the
agent no longer has the relevant source, ask it to read the file again.

## 6. Compare sources and handle older information

### Explain a changed budget

```text
Read mock-workspace/finance/harbor-budget-2026-11-18.txt and mock-workspace/finance/harbor-budget-2026-11-20.txt. Compare the old and current envelope, commitments, and remaining funds. Explain which figures are historical and which spending is only proposed. Cite both files.
```

### Resolve a changed meeting date

```text
Read mock-workspace/mail/2026-11-18-harbor-review-proposal.eml and mock-workspace/mail/2026-11-20-harbor-review-confirmed.eml. What changed, and what is the confirmed date, time, and location? Distinguish a proposal from a confirmation.
```

### Separate an approval from an assumption

```text
Read mock-workspace/finance/expense-policy.md and mock-workspace/mail/2026-11-20-harbor-budget-clarification.eml. Is the workshop purchase approved? What evidence or approvals are still missing?
```

The model can still make interpretation or arithmetic errors. Source references
show what the host returned, not that every conclusion is correct. Review important
decisions and numbers yourself.

## 7. Create useful reports

Tell the agent the files to use, the required sections, a new output filename,
and that you want it saved—not merely displayed.

### Budget brief

```text
Read the current Harbor budget and the budget clarification email under mock-workspace. Save harbor-budget-brief-v1.md in output. Include approved envelope, current commitments, current remaining funds, and a separate conditional workshop scenario. Include the source files actually read.
```

### Action plan

```text
Read mock-workspace/projects/harbor/action-items.txt and mock-workspace/projects/harbor/risks.md. Save harbor-action-plan-v1.md with open actions, owners, due dates, dependencies, and the three most important recorded risks. Cite sources and mark missing information as unknown.
```

### Status report using a template

```text
Read mock-workspace/operations/weekly-status-template.md, mock-workspace/projects/harbor/meeting-2026-11-20.md, and mock-workspace/finance/harbor-budget-2026-11-20.txt. Create harbor-status-v1.md in output using that layout, reporting as of 20 November 2026. Keep proposed dates and spending separate from confirmed decisions. Include source references.
```

A good report request usually uses **two to four files**, not the entire collection
in one turn. If you need a larger synthesis, work in small sections and review
them. The application is intentionally bounded.

### Read an output yourself

From `local-document-agent/` in PowerShell:

```powershell
Get-ChildItem ".\data\output"
Get-Content ".\data\output\harbor-status-v1.md"
notepad ".\data\output\harbor-status-v1.md"
```

These are commands for **you**, not tools the agent can execute.

If a filename already exists, request `harbor-status-v2.md`. The agent will not
overwrite v1. It cannot edit that existing output in place.

## 8. Draft replies and new emails — never send them

### Reply to the review confirmation

```text
Read mock-workspace/mail/2026-11-20-harbor-review-confirmed.eml. As Casey, draft a polite reply confirming attendance at the agreed slot and saying I will bring the participant guide and sign-off pack. Save harbor-review-reply-v1.md in output. Include To, Subject, and body. Do not send anything.
```

### Request a hold without placing an order

```text
Read mock-workspace/mail/2026-11-20-harbor-training-quote.eml. As Jamie, draft a reply asking whether the quoted workshop slot can be provisionally held until the quote expires while approvals are pending. Do not accept the quote or claim a purchase is approved. Save harbor-training-hold-v1.md as an unsent draft.
```

### Draft a new approval request

```text
Read the current Harbor budget, expense policy, and training quote in mock-workspace. As Casey, draft a new email to Avery requesting review of the proposed workshop expense. Explain current versus conditional balances and outstanding approvals. Save harbor-approval-request-v1.md. Do not send it.
```

The host adds **`EMAIL DRAFT — NOT SENT`** to email-draft files.
There is no sending tool, mailbox login, reservation, purchase, or calendar booking.
An outgoing draft is not evidence that an external action happened.

## 9. Recognize real activity and references

You may see:

```text
[tool] search_documents -> 2 match(es)
[tool] read_document -> input/mock-workspace/...: lines 1-20
[tool] create_document -> output/harbor-status-v1.md: created
```

Then the CLI shows:

- Files actually read this turn.
- Earlier observed sources referenced, when applicable.
- Actual created-file paths.
- Explicit unsent-draft status.
- Possible partial files separately from successful creations.
- Unverified citation IDs, if the model invents them.

Source IDs such as `[R1]` vary by session. Do not memorize them or copy an old ID
into a new session; let the tools provide current references.
Email line references describe the **extracted email representation**, not raw
MIME lines.

**`No file creation was observed.` is normal after a question or summary.**
It means no successful create operation occurred. If you wanted a saved file,
explicitly ask for a new `.txt` or `.md` output and check the observed path.
Do not trust "I saved it" without a successful host-created file record.

## 10. Practical limits and troubleshooting

Default limits include four previous complete turns, eight model calls and twelve
tool calls per turn, 30 seconds per inference request and 120 seconds per turn.
A read returns at most 200 lines and 12,000 characters; input/extracted text is
limited to 256 KiB and a created file to 64 KiB. Search returns at most 20 matches
per request and has traversal/time/byte limits.

| What you see | What to do |
|---|---|
| No matches | Try an exact relative path or another literal term. Ask for filename search first. |
| `NOT_FOUND` | Check the path and current input root; do not include `data/input/` in a tool-relative path. |
| `FILE_EXISTS` | Use a new output basename such as `-v2`; originals are preserved. |
| `UNKNOWN_SOURCE` | Ask to reread the relevant input files; old source IDs may have been evicted or cleared. |
| Context/model/tool/token limit | Start `/new` and narrow the task to fewer files or a shorter section. |
| Timeout, rate limit, quota, route unavailable | Inspect diagnostics and provider/account status. There is no automatic retry or paid fallback. |
| HTML-only or malformed email | Supply a valid plain-text export; the assistant will not invent the missing body. |
| Decode error | Convert a copy of `.txt`/`.md` to UTF-8; do not overwrite your original accidentally. |
| Range too large | Ask for fewer lines or a smaller section. A single overlong line is not silently truncated. |
| Write failure / possible partial file | Inspect the reported local path yourself. It is not a confirmed successful output. |
| Cancelled or failed turn | Its conversation is not retained. Any already-written files remain; inspect the footer before requesting another save. |

The application does not automatically retry until success, repair arguments, or
switch providers. A manual new attempt is a user decision, not proof that a
previous write did or did not happen.

### Find diagnostics

From `local-document-agent/`:

```powershell
Get-Content ".\.logs\errors.log" -Tail 20
```

Logs contain safe codes, timestamps, session IDs, versions and code locations,
not keys, document bodies, chat messages, draft text, or raw provider responses.
If sharing a problem, provide the code and session/timestamp, not your `.env`.
Logging can itself fail on a full or inaccessible disk; the terminal warns when
an error may not have been saved.

## 11. Use it safely and effectively

1. State the task, exact files or search terms, desired structure, and output name.
2. Ask for sources and explicit separation of facts, proposals and unknowns.
3. Use small batches; do not ask for all 18 documents to be read in a single turn.
4. Start `/new` for unrelated tasks and after significant input revisions.
5. Keep only documents you permit the selected inference service to process.
6. Review drafts, amounts, dates and conclusions before relying on them.
7. Preserve originals and use new output names.
8. Keep your private key and transmission consent in app-local configuration.

Selected chat, snippets, document excerpts and generated content are transmitted
to OpenRouter and its serving provider during model-backed use. Local file
storage is not a guarantee of private/offline inference or provider zero retention.

Supported capabilities are search/read/answer/summarize/new report/unsent draft.
There is no web browsing, shell, PDF/Office/OCR, attachment extraction, email
sending/synchronization, calendar, permanent memory, scheduler, frontend or API adapter.

## 12. Quick orientation to the fictional facts

Use these only to spot mistakes after the agent reads the documents:

- Current review: **24 November 2026, 14:00 UTC**, not the older proposal.
- Current budget envelope: **USD 1200**; commitments **USD 650**; uncommitted **USD 550**.
- Proposed workshop: **USD 240**, not yet an approved commitment.
- If approved: commitments would be **USD 890**, uncommitted **USD 310**.
- Launch on **1 December 2026** is a proposed date, not a confirmed decision.

The reusable corpus is in `examples/mock-workspace/`; the installed runtime copy
is `data/input/mock-workspace/`. Runtime input/output files are Git-ignored.
No application code changes or additional inference features are needed to use it.
