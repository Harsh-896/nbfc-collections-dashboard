# NBFC Collections Risk Dashboard

Automated Power BI dashboard that flags high-recovery-probability overdue
loans daily, with an AI-generated (Groq) prioritization brief for the
collections team.

## How it works

1. `main.py` generates/updates synthetic loan data, calculates a
   recovery-probability score per loan, and buckets loans into
   High / Medium / Low priority.
2. Groq generates a 3-line plain-English daily brief on the top
   high-priority accounts.
3. Data + brief get pushed to a Google Sheet.
4. GitHub Actions runs this automatically every day at 8 AM IST
   (see `.github/workflows/daily_run.yml`).
5. Power BI connects to the Google Sheet and refreshes on a schedule
   (Power BI service, "My workspace", free tier — up to 8 refreshes/day).

## Local setup

```bash
pip install -r requirements.txt
python main.py
```

Without any secrets set, it saves `loan_book.csv` and `ai_brief.txt`
locally instead of pushing to Google Sheets — good for testing the
data/scoring logic before wiring up the cloud pieces.

## Setting up the cloud pipeline

1. **Groq API key**: sign up at console.groq.com (free), get an API key.
2. **Google Sheets**:
   - Create a Google Cloud service account, enable the Sheets API,
     download the JSON key.
   - Share your target Google Sheet with the service account's email
     (found inside the JSON key) as an Editor.
3. **GitHub repo secrets** (Settings → Secrets and variables → Actions):
   - `GROQ_API_KEY`: your Groq key
   - `GOOGLE_CREDS`: paste the entire service account JSON as one secret
4. Push this repo to GitHub — the workflow runs automatically on its
   schedule, or trigger it manually from the Actions tab
   ("Run workflow" button).

## Risk scoring logic

```
score = 30
      + payment_consistency * 50
      - days_overdue * 0.4
      - past_defaults * 12
      + income adjustment (High: +8, Low: -8)
```

Flags: score >= 60 → High Priority, 35-59 → Medium, < 35 → Low Priority.

## Power BI

Connect Power BI Desktop to the Google Sheet (published-to-web CSV link,
or the raw sheet via Web connector). Suggested pages:

- Overview: total loans, % High Priority, total at-risk amount
- Risk heatmap: city x risk_flag
- Priority list: sortable table of High Priority loans
- AI Brief: text card pulling from the AI_Brief tab
