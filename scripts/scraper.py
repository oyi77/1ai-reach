import json
import subprocess
import pandas as pd
import os

def search_leads(query, location=None):
    """
    Search leads via Google Maps using AgentCash stableenrich.
    """
    payload = {"textQuery": query}
    if location:
        payload["location"] = location

    cmd = [
        "npx", "agentcash@latest", "fetch",
        "https://stableenrich.dev/api/google-maps/text-search/full",
        "-m", "POST",
        "-b", json.dumps(payload)
    ]
    
    print(f"Searching for: {query}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return []

    try:
        data = json.loads(result.stdout)
        places = data.get("data", {}).get("places", [])
        return places
    except Exception as e:
        print(f"Failed to parse output: {e}")
        return []

def save_leads(leads, filename="data/leads.csv"):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    df = pd.DataFrame(leads)
    if os.path.exists(filename):
        df_old = pd.read_csv(filename)
        df = pd.concat([df_old, df]).drop_duplicates(subset=['id'])
    
    df.to_csv(filename, index=False)
    print(f"Saved {len(df)} leads to {filename}")

if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "Coffee Shop in Jakarta"
    leads = search_leads(query)
    if leads:
        save_leads(leads)
