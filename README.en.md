# Feedback Station · Real-Device Test Feedback

[中文](README.md) | **English**

A **zero-dependency** LAN feedback site built for the loop *a coding agent ships a build → a human tests it on a real device → the agent reads the feedback from disk and fixes*.

- One command on the computer starts the server (Python 3 standard library, single file); a phone on the same Wi-Fi opens it in a browser.
- Testers mark each checklist item **pass / fail / not tested**, attach notes, screenshots and screen recordings; anything outside the checklist goes in as a **new bug** or a **feature request**.
- Everything is saved to JSON files and folders on the computer's disk. **The agent reads the feedback straight from disk**, so testers no longer shuttle screenshots around or write up reports for the chat.
- Ships with an agent-agnostic **Agent Skill** (`SKILL.md`, in the open [agentskills.io](https://agentskills.io) format, loadable by Claude Code, Codex, Cursor, Gemini CLI, OpenCode, GitHub Copilot, Kimi Code, Qwen Code, Lingma, Qoder, Trae, CodeBuddy, WorkBuddy, DeepSeek Harness and more): how to write the verification checklist for each delivery, how to read the results afterwards, and the UI conventions and pitfalls worth knowing.

It came out of an iOS app's development process: dozens of TestFlight batches and hundreds of verification items ran through it.
The UI follows the tester's browser language (Simplified and Traditional Chinese, English, Japanese, Korean, Spanish, French, German, Portuguese, Russian) and is mobile-first (designed at ~393pt wide, centered and width-capped on desktop).

## Why

Simulators can't exercise real data when you build a mobile app: real accounts, real networks, push, location, camera and photo library, system permissions, gesture feel and animation all have to be checked on a physical device. So every build still has to be tested by a person on a phone, and that is exactly where the friction is:

- "Go try the new build" tells the tester nothing about what changed or where to look; "it feels laggy" or "something's off" coming back tells the agent nothing about which change is at fault.
- Working through a long checklist on a phone, the tester tracks progress from memory or in a separate notes app.
- Every screenshot or recording has to travel from phone to computer (AirDrop, chat, email), get dragged into the conversation, and then be explained in words: which item it belongs to. Dozens of findings mean dozens of round trips.
- The feedback ends up scattered across a chat history the agent can't read attachments from, so someone has to write it up again; the next round of re-verification starts from scratch.

Feedback Station collapses that into one path: the agent writes the checklist to a file, the tester ticks items and shoots photos or recordings straight from the phone's browser, everything lands on the computer's disk, and the agent reads it from there. No transferring screenshots, no writing up feedback, no lost history.

And it is precise in both directions. The agent knows exactly what changed in a build, so it writes the checklist item by item, each with a stable id and its own wording; the tester sees at a glance what to test and what counts as passing. Feedback lands back on that same id, so the agent gets "which item, which status, which attachment" instead of a description it has to guess at. Nothing that needs testing is missed, nothing that doesn't is tested for nothing, and re-verification maps cleanly onto the previous batch.

## Quick start (standalone)

```bash
git clone https://github.com/ccc333cn/feedback-station.git feedback-station
cd feedback-station
cp checklist.example.json checklist.json     # edit into your checklist
python3 server.py --title "My App · Device Test"
```

The terminal prints `http://<LAN IP>:8787/`; open it on a phone on the same Wi-Fi. If the phone can't connect on the first try, check whether the computer is showing a firewall prompt asking to let Python accept incoming connections.

Options:

| Option | Default | Meaning |
|---|---|---|
| `--root DIR` | the script's directory | where `checklist.json` and `data/` live |
| `--port N` | `8787` | port to listen on |
| `--host` | `0.0.0.0` | use `127.0.0.1` to keep it local-only |
| `--title` | follows browser language | page title; pass one to fix it |

Runtime data all lives in `<root>/data/` (excluded by `.gitignore`):

| File | Content |
|---|---|
| `results.json` | `{status, note, files, updatedAt}` per checklist item, keyed by itemId |
| `bugs.json` | array of new bugs `{id, title, note, files, batchId, createdAt, updatedAt}` |
| `requirements.json` | array of feature requests, same shape as `bugs.json` |
| `uploads/` | original screenshots and recordings |

Summarize the feedback (latest batch by default; `--all` for everything, `--batch <id>` for specific ones):

```bash
python3 summarize.py --root .
```

## Using it as an Agent Skill

`SKILL.md` follows the open [Agent Skills](https://agentskills.io) format, so Claude Code, Codex, Cursor, Gemini CLI, OpenCode, Copilot,
Kimi Code, Qwen Code, Lingma, Qoder, Trae, CodeBuddy, WorkBuddy, DeepSeek Harness and any other skills-aware agent can load it, whatever model it runs.
Clone the repo into your host's skills directory (keep the directory name `feedback-station`), or simply hand the repo URL to the agent and let it install the skill itself — it knows where skills go:

```bash
git clone https://github.com/ccc333cn/feedback-station.git <your host's skills dir>/feedback-station
```

Then tell the agent to "set up the feedback station". The skill walks it through picking a `<root>` directory in your project (`Tools/FeedbackStation/` is suggested), starting the server with `--root`, and handing you the URL; on each delivery it writes the verification checklist to the head of `checklist.json`; when you say "done testing" it reads the results from disk.

The skill body is written in Chinese; its `description` carries English trigger phrases, and any current model reads the instructions fine. It tells the agent to write checklist items, the page title and its replies in the user's own language.

Agents without a skill mechanism (or a plain chat UI) can use it too: paste `SKILL.md` into the system prompt or the conversation as the operating manual. It only needs a host that can run shell commands and read/write files.

The skill directory holds only code; the checklist and data live in your project's `<root>`, so updating the skill never touches your data.

## Checklist format

`checklist.json`:

```json
{ "batches": [
  { "id": "b2", "title": "Batch 2 · build 12 fixes", "date": "2026-09-06", "sections": [
      { "title": "1. Section title", "items": [
          { "id": "b2-1", "label": "2-1", "text": "Item text" } ] } ] } ] }
```

- New batches go at the **head** of `batches` (newest on top); old batches are never deleted, testers use the batch chips to look back.
- `id` is unique site-wide and never reused (results are keyed by it); `label` is just the display number.
- `text` is plain text, markdown is not parsed. Emphasize with quotes or an emoji prefix; enumerate with ①②③.
- `date` is optional but recommended, format `YYYY-MM-DD`.
- No restart needed after editing; refresh the page.

Full example in [checklist.example.json](checklist.example.json).

## What the page does

- Header: title plus a save-status dot (saving / saved / failed, tap to retry); a "☰ Batches" vertical multi-select panel (lists the most recent few, scroll for older) plus a horizontally scrolling row of batch chips; only the latest batch is selected when the page opens; a "Show: all / failed / not tested / passed / unmarked" filter; a progress line "tested x / y · failed n · not tested m · bugs · requests".
- Item card: number plus text; three buttons "pass / fail / not tested", tap the same one again to clear. "Fail / not tested" expand the note and attachment area; "pass" stays collapsed behind a "+ add a suggestion (optional)" link.
- Attachments: camera / photo library / screen recording, multi-select upload, thumbnails, in-page lightbox (video supports Range requests, so Safari plays it directly); ✕ to delete.
- New bugs and feature requests: one-line title plus details plus attachments, tied to a batch and shown only under that batch's view.
- Auto-save: text debounced 500ms, status and uploads immediate; failed saves retry every 3s; refresh or switch devices and everything comes back from the server.
- UI language follows the browser (10 languages), switchable in the footer or with `?lang=en` in the URL; checklist content itself is not translated.

Design trade-offs and the API table are in [docs/api.md](docs/api.md) (Chinese).

## Layout

```
feedback-station/
├── SKILL.md                 # agent-agnostic Agent Skill (agentskills.io format)
├── server.py                # LAN server (Python 3 standard library)
├── index.html               # single-page frontend (vanilla JS)
├── summarize.py             # folds the three data files into one Markdown report
├── checklist.example.json   # checklist example
├── docs/api.md              # API contract, data model, record lifecycle, frontend conventions
└── data/                    # generated at runtime, not committed
```

## Limits and safety

- Binds LAN HTTP only, **no authentication**: run it only on trusted Wi-Fi, never expose it to the internet.
- Two devices editing the same item **at the same time** is last-writer-wins.
- Single upload limit 512MB; the upload directory is guarded against path traversal.
- JSON is written atomically (temp file + `os.replace`) under a lock; a corrupt file is never overwritten, it is renamed as evidence and the server falls back to empty data.
