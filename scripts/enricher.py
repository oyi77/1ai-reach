import json
import subprocess
import pandas as pd
import os
import time

def enrich_lead(website, name):
    """
    Enrich contact info using stableenrich minerva or clado.
    """
    if not website or website == 'nan':
        return None
    
    # Try Minerva enrichment
    payload = {"domain": website, "name": name}
    cmd = [
        "npx", "agentcash@latest", "fetch",
        "https://stableenrich.dev/api/minerva/enrich",
        "-m", "POST",
        "-b", json.dumps(payload)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            person = data.get("data", {}).get("person", {})
            return {
                "email": person.get("email"),
                "phone": person.get("phone"),
                "linkedin": person.get("linkedin_url")
            }
        except:
            pass
    return None

def process_leads(filename="data/leads.csv"):
    if not os.path.exists(filename):
        print("No leads file found.")
        return

    df = pd.read_csv(filename)
    if 'email' not in df.columns:
        df['email'] = None
    if 'phone' not in df.columns:
        df['phone'] = None

    for index, row in df.iterrows():
        if pd.isna(row['email']) or pd.isna(row['phone']):
            print(f"Enriching: {row['displayName']['text'] if isinstance(row['displayName'], dict) else row.get('name')}...")
            name = row['displayName']['text'] if isinstance(row['displayName'], dict) else row.get('name')
            info = enrich_lead(row.get('websiteUri'), name)
            if info:
                df.at[index, 'email'] = info.get('email')
                df.at[index, 'phone'] = info.get('phone')
                df.at[index, 'linkedin'] = info.get('linkedin')
            time.sleep(1) # Slow down for rate limits

    df.to_csv(filename, index=False)
    print("Enrichment complete.")

if __name__ == "__main__":
    process_leads()
