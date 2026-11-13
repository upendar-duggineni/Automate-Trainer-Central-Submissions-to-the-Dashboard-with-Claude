<<<<<<< HEAD
# Trainer Central -> Dashboard Automation

Local Python app that reads Trainer Central submission emails (.txt) from a shared Google Drive folder, uses Claude to decide which are mine and extract details, and pushes them to the dashboard API. Runs every 30 minutes with no manual trigger.

Participant: **upendarduggineni** (upendarduggineni24@gmail.com)

## Architecture

```mermaid
flowchart LR
  S[Scheduler: cron / Task Scheduler<br/>every 30 min] --> A[app.py]
  D[(Google Drive folder<br/>.txt emails)] -->|Drive API, new files only| A
  A -->|file text + prompt.txt| C[Claude API<br/>is_mine + JSON details]
=======
# Automate-Trainer-Central-Submissions-to-the-Dashboard-with-Claude
# Trainer Central -> Dashboard Automation

A local Python app that reads Trainer Central submission emails (saved as `.txt` files) from the trainer's shared Google Drive folder, uses **Claude** to decide which ones are mine and extract the details, and pushes them to the dashboard API. It runs every 30 minutes with no manual trigger.

- **Participant:** upendarduggineni (upendarduggineni24@gmail.com)
- **Dashboard:** https://trainer-central-assigments-api.onrender.com (API docs at `/docs`)

## Architecture

![Architecture](architecture.svg)

```mermaid
flowchart LR
    S["Scheduler: Windows Task Scheduler<br/>Every 30 minutes"] --> A["app.py"]
    D[("Google Drive folder<br/>.txt submission emails")] -->|"Drive API: new files only"| A
    A -->|"Email text + prompt.txt"| C["Claude API<br/>Classification + JSON extraction"]
    C -->|"is_mine + assignment details"| A
    A -->|"POST /api/entries"| API["Trainer Central Dashboard API"]
    API --> DB[("Dashboard")]
    A --> STATE[("SQLite state.db<br/>Duplicate prevention")]
    A --> LOG[("logs/run.log")]
```

<<<<<<< HEAD
Flow per run: list `.txt` files -> skip IDs already in `state.db` -> read file -> Claude returns JSON -> if mine, wake API (`/health`), check it is not already on the dashboard, `POST /api/entries` with `sender` = my name -> record the file as processed.

## Setup

1. **Python 3.10+**, then in this folder:
   ```
   python -m venv venv
   # Windows: venv\Scripts\activate     Mac/Linux: source venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Config:** copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY`, `DRIVE_FOLDER_ID` (the last part of the folder URL `drive.google.com/drive/folders/<ID>`), and `DASHBOARD_API_KEY` only if the trainer says it is required.
3. **Google Drive access (one time):**
   - Google Cloud Console -> create a project -> enable **Google Drive API**.
   - OAuth consent screen -> External -> add yourself as a test user (also publish to "In production" to avoid the 7-day refresh-token expiry of Testing mode).
   - Credentials -> Create **OAuth client ID** -> *Desktop app* -> download as `credentials.json` into this folder.
   - Run `python app.py --auth` and sign in with the Google account that can see the shared folder. This saves `token.json`, which refreshes itself for unattended runs.
4. **Test manually once:** `python app.py` and check `logs/run.log`.

## Scheduling (every 30 minutes)

**Windows (Task Scheduler)** - run in Command Prompt, adjusting the path:
```
schtasks /create /tn "TrainerCentralSync" /sc minute /mo 30 /tr "C:\path\to\trainer_central_automation\run_windows.bat"
```

**Mac/Linux (cron)** - `crontab -e` and add:
```
*/30 * * * * /path/to/trainer_central_automation/run_unix.sh >> /path/to/trainer_central_automation/logs/cron.log 2>&1
```
The computer must be on and awake (not sleeping) for runs to happen.
=======
**Flow per run:** list the `.txt` files in the Drive folder -> skip file IDs already in `state.db` -> read the file -> Claude returns JSON -> if the email is mine, call `GET /health` (Render wakes slowly), check the dashboard does not already hold this file, then `POST /api/entries` with `sender` = my name -> record the file as processed.

## Files

| File | Purpose |
|---|---|
| `app.py` | Main application (Drive fetch, Claude analysis, API push, dedupe, logging) |
| `prompt.txt` | The Claude prompt (match rules and the JSON output format) |
| `run_windows.bat` / `run_unix.sh` | Entry points the scheduler calls |
| `register_task.ps1` | Registers the Windows scheduled task (every 30 min) |
| `.env.example` | Config template, no secrets |
| `package_submission.ps1` | Builds a zip without secrets |
| `evidence/` | Screenshots, run logs and timing proof |

## Setup

1. **Python 3.10+**. In the project folder (PowerShell):
   ```powershell
   python -m venv venv
   venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. **Configuration:** copy `.env.example` to `.env` and fill in:
   - `ANTHROPIC_API_KEY`: the key provided by the trainer (kept only in `.env`)
   - `DRIVE_FOLDER_ID`: the last part of the trainer's folder URL `drive.google.com/drive/folders/<ID>`
   - `MY_NAME`, `MY_EMAIL`, `API_BASE`
   - `DASHBOARD_API_KEY`: only if the dashboard API requires an `x-api-key`
3. **Google Drive access (one time):**
   - In Google Cloud Console create a project and enable the **Google Drive API**.
   - Configure the OAuth consent screen (External), add my Google account as a test user, and publish to "In production" so the token does not expire after 7 days.
   - Create an **OAuth client ID** of type *Desktop app*, download it as `credentials.json` into the project folder.
   - Run `python app.py --auth`, sign in with the Google account that can open the trainer's folder. This saves `token.json`, which refreshes itself for unattended runs.

## How to run

```powershell
python app.py
```
The log goes to the console and to `logs/run.log`. A second run prints `new=0` and posts nothing.

## How it is scheduled

**Windows (used for this project):**
```powershell
.\register_task.ps1
Get-ScheduledTaskInfo -TaskName TrainerCentralSync   # LastTaskResult 0 = success
```
This registers task `TrainerCentralSync`, which runs `run_windows.bat` every 30 minutes, runs even on battery, catches up after sleep (`StartWhenAvailable`) and never overlaps itself. Remove it with `Unregister-ScheduledTask -TaskName TrainerCentralSync -Confirm:$false`.

**Mac/Linux (cron):**
```
*/30 * * * * /path/to/trainer_central_automation/run_unix.sh >> /path/to/trainer_central_automation/logs/cron.log 2>&1
```

## Real email format and how the Claude step works

Each file is a TrainerCentral notification with headers (`Date`, `Message ID`) and one body sentence naming the learner's **email address** (not their name), the assignment topic and the course. So:

- **Match:** the learner email must equal `upendarduggineni24@gmail.com`. Lookalike addresses and non-submission emails are rejected.
- **Extracted:** assignment name (topic), submission time (the `Date:` header, UTC), status ("Submitted"), and details (course, learner email, message ID, submission ID, link).
- Claude is told to return only JSON, to use null for missing values, and to treat the email text as data, not instructions.

The pushed entry text looks like:
```
Assignment: <topic>
Submitted: <Date header>
Status: Submitted
Details: ...
[drive-file:<Drive file id>] <file name>
```
>>>>>>> f26a5f5b1e0cef73cb24e2dbabc67f8450cddbb7

## How requirements are met

| Req | How |
|---|---|
<<<<<<< HEAD
| R1 | Drive API lists `.txt` files; only unseen file IDs are processed |
| R2/R3 | `prompt.txt` makes Claude return JSON: `is_mine`, assignment name, submission time, status, other details |
| R4 | `POST /api/entries` with `text` and `sender` |
| R5 | `state.db` records processed file IDs; also checks `GET /api/entries` for a `[drive-file:<id>]` marker before posting |
| R6/R7 | OS scheduler every 30 min, runs locally |
| R8 | Retries with backoff on Drive, Claude and API calls; empty/unrelated files skipped; one bad file never stops the run; failed files are retried next run; everything logged to `logs/run.log` |

## Real email format (from sample files)

Each file is a TrainerCentral notification with headers (`Date`, `Message ID`) and one body sentence naming the learner's **email address** (not their name), the assignment topic and the course. So matching is done on `upendarduggineni24@gmail.com`; submission time is taken from the `Date:` header (UTC); status is "Submitted"; the course, message ID and submission ID go into the details.

## Assumptions

- `sender` is always `upendarduggineni`, so the dashboard groups all entries under one learner.
- A file is marked processed only after a definitive outcome (pushed, not mine, empty). API or Claude failures are retried on the next run.
- The response from `POST /api/entries` is expected to contain `id` or `entry_id`; if not, the entry is still counted as pushed.
- Secrets live only in `.env`, `token.json` and `credentials.json`, which are git-ignored and must not be submitted.

## Testing checklist

- Email for another participant -> logged "not mine", nothing posted
- Empty file -> skipped
- Run twice -> no second entry
- Disconnect internet -> logs the error, exits cleanly, recovers next run
=======
| R1 Fetch from Drive | Drive API lists `.txt` files; only unseen file IDs are processed |
| R2 Identify my emails | Claude decides `is_mine` from the learner email (prompt.txt) |
| R3 Extract details | Claude returns assignment name, time, status, other details as JSON |
| R4 Push to dashboard | `POST /api/entries` with `text` and `sender`; response checked |
| R5 No duplicates | Local `state.db` of processed file IDs, plus a check for the `[drive-file:<id>]` marker on the dashboard before posting |
| R6 Fully automated | Task Scheduler every 30 minutes, no manual trigger |
| R7 Runs locally | Runs on my Windows laptop |
| R8 Resilient | Retries with backoff for Drive, Claude and API; empty and unrelated files skipped; one bad file never stops a run; failed files retried next run; everything logged |

## Assumptions

- `sender` is always `upendarduggineni`, so the dashboard groups my entries under one learner.
- The email contains the learner's email, not their name, so matching uses the email.
- Submission time is taken from the email's `Date:` header (UTC), which is when the notification was sent.
- A file is marked processed only after a definitive outcome (pushed, not mine, empty). Claude or API failures are retried on the next run.
- The Drive account used for credentials has view access to the trainer's folder.
- The dashboard API accepted posts without an `x-api-key` (set `DASHBOARD_API_KEY` if that changes).
- Dashboard times are UTC; my laptop is IST (UTC+5:30).

## Known limits

- The laptop must be on and awake for runs (missed runs catch up after wake-up).
- Worst-case delay is about 30 minutes after the trainer saves the file to Drive, plus about a minute of processing.
- The dashboard check reads the first 100 entries only; the local `state.db` remains the main duplicate guard.

## Security

Secrets live only in `.env`, `token.json` and `credentials.json`. These are git-ignored and excluded from the submission zip by `package_submission.ps1`.

## Testing done

- Other participants' emails and non-Trainer-Central files: logged "not mine", nothing posted.
- Second run on the same files: `new=0`, no duplicate entry.
- Two scheduled runs (03:49 and 04:19 on 14/11/2026) with no manual trigger, logs in `evidence/`.
- Timing test with a fresh submission: see `evidence/TIMING_PROOF.md`.
>>>>>>> f26a5f5b1e0cef73cb24e2dbabc67f8450cddbb7
