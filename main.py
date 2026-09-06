"""
NBFC Collections Risk Dashboard — Data Pipeline
Generates loan data, calculates recovery-probability risk scores,
generates an AI daily brief (Groq), and pushes everything to Google Sheets
for Power BI to consume via scheduled refresh.
"""

import os
import json
import numpy as np
import pandas as pd
from faker import Faker

fake = Faker()
np.random.seed(42)

# ---------------------------------------------------------------------
# STEP 1: Generate (or update) synthetic loan book data
# ---------------------------------------------------------------------
def generate_loan_data(n=2000):
    rows = []
    for i in range(n):
        loan_amount = int(np.random.randint(20000, 500000))
        days_overdue = int(np.random.choice(
            [0, 5, 15, 30, 45, 60, 90, 120],
            p=[0.30, 0.15, 0.15, 0.15, 0.10, 0.08, 0.05, 0.02]
        ))
        past_defaults = int(np.random.choice([0, 1, 2, 3], p=[0.6, 0.25, 0.1, 0.05]))
        income_band = np.random.choice(["Low", "Mid", "High"], p=[0.4, 0.4, 0.2])
        payment_consistency = round(float(np.random.uniform(0.3, 1.0)), 2)

        rows.append({
            "loan_id": f"LN{1000 + i}",
            "borrower_name": fake.name(),
            "loan_amount": loan_amount,
            "days_overdue": days_overdue,
            "past_defaults": past_defaults,
            "income_band": income_band,
            "payment_consistency": payment_consistency,
            "city": fake.city(),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# STEP 2: Calculate recovery-probability risk score
# ---------------------------------------------------------------------
def recovery_score(row):
    score = 30
    score += row["payment_consistency"] * 50
    score -= row["days_overdue"] * 0.4
    score -= row["past_defaults"] * 12
    if row["income_band"] == "High":
        score += 8
    elif row["income_band"] == "Low":
        score -= 8
    return int(max(0, min(100, round(score))))


def add_risk_columns(df):
    df["recovery_probability"] = df.apply(recovery_score, axis=1)
    df["risk_flag"] = df["recovery_probability"].apply(
        lambda x: "High Priority" if x >= 60 else ("Medium" if x >= 35 else "Low Priority")
    )
    df["days_overdue_bucket"] = pd.cut(
        df["days_overdue"],
        bins=[-1, 15, 30, 45, 200],
        labels=["0-15", "16-30", "31-45", "45+"],
    )
    return df


# ---------------------------------------------------------------------
# STEP 3: Generate AI daily brief using Groq
# ---------------------------------------------------------------------
def generate_ai_brief(df):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "GROQ_API_KEY not set — skipping AI brief (set the secret to enable this step)."

    from groq import Groq
    client = Groq(api_key=api_key)

    high_priority = (
        df[df["risk_flag"] == "High Priority"]
        .sort_values("loan_amount", ascending=False)
        .head(10)
    )
    summary_data = high_priority[
        ["loan_id", "loan_amount", "days_overdue", "recovery_probability"]
    ].to_string(index=False)

    total_at_risk = int(df[df["risk_flag"] == "High Priority"]["loan_amount"].sum())

    prompt = f"""You are writing a daily brief for an NBFC collections manager.
Total high-priority (high recovery-probability) overdue amount: Rs {total_at_risk:,}
Top 10 high-priority overdue loans:
{summary_data}

In 3 short lines of plain English, tell the manager: how many accounts,
total rupee value, and which ones to follow up on first and why."""

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------
# STEP 4: Push to Google Sheets
# ---------------------------------------------------------------------
def push_to_sheets(df, brief_text):
    creds_json = os.environ.get("GOOGLE_CREDS")
    sheet_name = os.environ.get("SHEET_NAME", "loan_collections_data")

    if not creds_json:
        print("GOOGLE_CREDS not set — saving to local CSV instead.")
        df.to_csv("loan_book.csv", index=False)
        with open("ai_brief.txt", "w") as f:
            f.write(brief_text)
        return

    import gspread
    from google.oauth2.service_account import Credentials

    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)

    sh = gc.open(sheet_name)
    ws = sh.sheet1
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

    try:
        brief_ws = sh.worksheet("AI_Brief")
    except gspread.exceptions.WorksheetNotFound:
        brief_ws = sh.add_worksheet(title="AI_Brief", rows=10, cols=2)
    brief_ws.update("A1", [[brief_text]])


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
if __name__ == "__main__":
    print("Generating loan data...")
    df = generate_loan_data(n=2000)

    print("Calculating risk scores...")
    df = add_risk_columns(df)

    print("Generating AI brief...")
    brief = generate_ai_brief(df)
    print("\n--- AI BRIEF ---\n" + brief + "\n----------------\n")

    print("Pushing to Google Sheets...")
    push_to_sheets(df, brief)

    print(f"Done. {len(df)} loans processed. "
          f"{(df['risk_flag'] == 'High Priority').sum()} flagged High Priority.")