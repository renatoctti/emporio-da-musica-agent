# Spec 12: Local web interface

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-11-01
**Scope:** conversation setup shared with the CLI, a small local HTTP server, a static single-page UI
**Depends on:** 05, 08, 09
**Delivery:** autonomous (after its dependencies)

---

## Summary

`emporio web` serves a chat page on the local machine. It uses the same agent, tools and database
as the CLI. Next to every answer the page shows **how the agent decided** (catalog data, manual,
identity check, return rules, human handoff), which is the behavior the challenge asks to see.

## Context

The challenge accepts a CLI, so this is an addition for people who evaluate the project. It adds
no dependency: the server uses the standard library and the page is plain HTML, CSS and
JavaScript with no external request, so it works offline. The server is for one person on one
machine and stores personal data, so it listens on `127.0.0.1` only.

---

## Allowed files

**Production**

- `src/emporio/conversation.py` (new): `Conversation`, `start_conversation`
- `src/emporio/config.py`: `Settings.simulated` (true when `EMPORIO_TODAY` is set)
- `src/emporio/prompt.py`: public `WEEKDAYS` and store address, phone and e-mail constants shared with the page
- `src/emporio/cli.py`: build the agent through `start_conversation`; add the `web` command
- `src/emporio/web/__init__.py`, `app.py`, `server.py` (new)
- `src/emporio/web/static/index.html`, `app.css`, `app.js`, `theme.js`, `favicon.svg` (new)
- `pyproject.toml`: ship the static files with the package

**Tests**

- `tests/test_web.py` (new)
- `tests/test_config.py`: the `simulated` flag
- `tests/test_cli.py`: the `web` command

**Docs:** `README.md`, `PROJECT_MAP.md`

**Do not touch:** the domain modules, the tools, the prompt.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance criterion |
|---|---|---|---|
| ✅ RF-01 | `start_conversation(settings, client, data, policies, handoffs, session_id)` builds the agent for one session and returns a `Conversation` with the `reply` function and its `SessionState`; the CLI uses it | Must | Every existing CLI test still passes unchanged |
| ✅ RF-02 | `emporio web [--port N] [--today D] [--no-browser]` serves on `127.0.0.1` (default port 8765) and opens the browser unless `--no-browser`; a missing API key exits with code 1 before binding; a busy port exits with code 1 and a message | Must | Port 0 in tests; both exit codes covered |
| ✅ RF-03 | `GET /` returns the page; `GET /static/<name>` returns only the files of the static folder with the right content type; anything else, including `..` paths, is 404 | Must | `/static/../../pyproject.toml` returns 404 |
| ✅ RF-04 | `GET /api/state` returns the store status (open or closed now, the next opening, hours, address, phone), the reference date and whether it is simulated, the model, the session id, the verified customer's first name or `null`, four suggestions, the number of open tickets, the two fictional customers an evaluator can use to try the identity check and the turns of the current conversation (so a page reload restores the transcript and the trace) | Must | Open on Wednesday 10:00, closed on Sunday with Monday 09:00 as next opening |
| ✅ RF-05 | `POST /api/chat` with `{"text"}` runs one turn, saves its messages in one transaction and returns `reply`, `trace`, `verified` and `handoffs_open` | Must | A scripted model answer and a stored conversation of 2 messages |
| ✅ RF-06 | Each trace item has `name`, `kind` (`data`, `policy`, `identity`, `rules`, `handoff`), a Portuguese `title` and `summary`, the parsed `arguments` (the `contact` value is replaced by `"(oculto)"`), the parsed `result` (cut when over 4000 characters, with `truncated: true`) and `ok` (false when the result is an error or the identity check failed) | Must | One test per tool name |
| ✅ RF-07 | `POST /api/reset` starts a new session and clears the verification | Must | `verified` is `null` afterwards and the session id changes |
| ✅ RF-08 | `GET /api/handoffs` lists the open tickets (protocol, category label, summary, due date, order) | Must | A ticket opened in a chat shows up |
| ✅ RF-09 | `POST` requests need `Content-Type: application/json`, a body of at most 16 KB and a text of 1 to 2000 characters after trimming; wrong route 404, wrong method 405 | Must | 400, 413, 415 covered |
| ✅ RF-10 | A request whose `Host` is not `127.0.0.1` or `localhost` with the server port, or whose `Origin` (when sent) is another origin, gets 403 | Must | Protects the API key's credit and the data from other web pages (DNS rebinding, cross-site posts) |
| ✅ RF-11 | A failure of the model or the network answers 502 with a short message (no traceback) and saves nothing for that turn | Must | A model that raises leaves the stored conversation unchanged |
| ✅ RF-12 | The static files make no external request (no `http://` or `https://` in a `src`, `href` or `url()`) and declare `lang="pt-BR"` | Must | Checked by a test over the three files |

### What the page must do (checked by hand in a browser)

The first view is complete without scrolling: the brand and the store status, the reference date,
a short invitation and four example questions that each name what they demonstrate.

- **Conversation.** The agent's replies are plain text blocks under its name, the customer's are
  tinted blocks on the right; a typing indicator while waiting; **bold** and list items in replies
  are rendered; Enter sends, Shift+Enter adds a line; the composer grows up to six lines.
- **How it decided.** A side panel lists the tools used in each turn as a timeline, with a kind
  label, a one-line summary and the arguments and result on expand; each reply carries small
  labels of the kinds used and selecting one scrolls the panel to that turn.
- **Collapsible panel.** The side panel can be collapsed and expanded at any width: a header button and a close button inside the panel. On a wide screen the choice is remembered in the browser and the chat takes the whole width while the panel is hidden; opening a reply's label expands it again. Under 900 px the same control opens and closes the drawer, and the dimmed backdrop appears only there.
- **Store panel.** A second tab lists the open tickets; opening one in the chat updates it.
- **Identity.** After a successful check the composer area shows who is verified.
- **States.** Empty, waiting, error (with a retry that resends the message) and success.
- **Themes.** A light and a dark theme, each designed on its own rather than inverted. A three-way control in the header (system, light, dark), remembered in the browser; the default follows the system and both themes keep every text pair at WCAG AA contrast.
- **Responsive.** Under 900 px the panel becomes a drawer opened from the header; a 400 px screen
  has no horizontal scroll and 16 px side gutters.
- **Accessibility.** The conversation is an `aria-live` log, every control has a name and a visible
  focus ring, motion is off with `prefers-reduced-motion`, contrast meets WCAG AA in both themes.

---

## Contracts

**`src/emporio/conversation.py`** ✅

```python
@dataclass
class Conversation:
    session_id: str
    state: SessionState
    reply: Callable[[list[dict[str, Any]], str], AgentTurn]

def start_conversation(settings: Settings, client: ChatClient, data: StoreData,
                       policies: tuple[PolicySection, ...], handoffs: HandoffStore,
                       session_id: str) -> Conversation
```

**`src/emporio/web/app.py`** ✅

```python
@dataclass(frozen=True)
class Response:
    status: int
    content_type: str
    body: bytes

class WebApp:
    def __init__(self, settings: Settings, client: ChatClient, *, port: int,
                 data: StoreData | None = None,
                 policies: tuple[PolicySection, ...] | None = None) -> None
    def handle(self, method: str, path: str, headers: Mapping[str, str], body: bytes) -> Response

def trace_item(name: str, arguments: str, result: str) -> dict[str, Any]
```

**`src/emporio/web/server.py`** ✅

```python
def make_server(app: WebApp, port: int) -> http.server.HTTPServer   # binds 127.0.0.1 only
```

Errors in `/api/*` are `{"error": "<short message>"}`.

---

## Edge cases

| ID | Scenario | Trigger | Expected behavior |
|---|---|---|---|
| ✅ EC-01 | Tool result that is not JSON | a tool returned plain text | `result` is the text, `ok` is true |
| ✅ EC-02 | Several tool calls in one turn | search and policy together | One trace item per call, in order |
| ✅ EC-03 | Text with only spaces | `"   "` | 400 and no model call |
| ✅ EC-04 | Host header spoofed | `evil.example` | 403 before anything runs |
| ✅ EC-05 | Reset during a verified conversation | verification then reset | The next order question asks for the identity again |

---

## Minimum test cases

| # | Target | Scenario | Expected result | Test file |
|---|---|---|---|---|
| ✅ T-01 | `start_conversation` and the CLI | existing suite | Unchanged behavior | `tests/test_cli.py` |
| ✅ T-02 | `handle` GET routes | page, static, traversal, unknown | RF-03 | `tests/test_web.py` |
| ✅ T-03 | `/api/state` | Wednesday and Sunday | RF-04 | `tests/test_web.py` |
| ✅ T-04 | `/api/chat` | plain turn, tool turn, stored messages | RF-05 | `tests/test_web.py` |
| ✅ T-05 | `trace_item` | each tool, redaction, truncation, errors, text results | RF-06, EC-01 | `tests/test_web.py` |
| ✅ T-06 | verification and reset | verified then reset | RF-04, RF-07, EC-05 | `tests/test_web.py` |
| ✅ T-07 | `/api/handoffs` | ticket from a chat | RF-08 | `tests/test_web.py` |
| ✅ T-08 | request validation | content type, size, empty text, routes | RF-09, EC-03 | `tests/test_web.py` |
| ✅ T-09 | host and origin checks | spoofed host, foreign origin | RF-10, EC-04 | `tests/test_web.py` |
| ✅ T-10 | model failure | a client that raises | RF-11 | `tests/test_web.py` |
| ✅ T-11 | real HTTP round trip | server on a free port, `urllib` | RF-02, RF-03 | `tests/test_web.py` |
| ✅ T-12 | static files | no external requests, `lang` | RF-12 | `tests/test_web.py` |
| ✅ T-13 | `emporio web` | missing key, busy port | exit codes of RF-02 | `tests/test_cli.py` |

### Acceptance criterion

```bash
python -m pytest tests/test_web.py tests/test_cli.py -q
```

Plus the manual pass in a browser described above, in light and dark, at 1280 px and 400 px.

---

## Implementation checklist

- [x] ✅ `git diff --stat` checked against **Allowed files**
- [x] ✅ Tests written before the code
- [x] ✅ The page injects replies with `textContent`, never `innerHTML` with model output
- [x] ✅ No dependency added; no external request from the page
- [x] ✅ Manual browser pass in both themes at desktop and phone width
- [x] ✅ `ruff check` and `ruff format --check` pass

## Open questions

None.

## Architectural adherence

| Rule | Status | Note |
|---|---|---|
| The web layer calls the agent; the agent and the domain never import it | ✅ | |
| Business errors travel as JSON; infrastructure errors become a short 502 | ✅ | |
| Scope respected | ✅ | |