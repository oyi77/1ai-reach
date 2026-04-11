import pandas as pd
import subprocess
import os
import json

def generate_proposal(lead_name, lead_business):
    prompt = f"""
    Create a professional business proposal and a short WhatsApp draft for the following lead:
    Business Name: {lead_name}
    Niche: {lead_business}
    
    Our Company: BerkahKarya
    Services: AI Automation, Digital Marketing, and Software Development.
    Goal: Help them improve efficiency and revenue with AI.
    
    Format output:
    ---PROPOSAL---
    [Long professional text]
    ---WHATSAPP---
    [Short engaging text with clear call to action]
    """
    
    # Using 'oracle' or 'gemini' if available, or just use agent sessions_spawn for heavy lifting.
    # For now, let's assume we can use a simple python call to an LLM provider or just mock for logic.
    # Since I'm the agent, I'll use a direct subprocess to 'gemini' CLI or similar if I have it.
    
    cmd = ["gemini", "ask", prompt]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout
    return "Failed to generate proposal."

def process_proposals(filename="data/leads.csv"):
    df = pd.read_csv(filename)
    os.makedirs("proposals/drafts", exist_ok=True)
    
    for index, row in df.iterrows():
        name = row['displayName'] # simplifying
        if isinstance(name, str) and name.startswith('{'):
            try:
                name = json.loads(name.replace("'", '"'))['text']
            except:
                pass
        
        # Determine business type from categories or name
        business = "Local Business"
        
        print(f"Generating proposal for {name}...")
        proposal_text = generate_proposal(name, business)
        
        with open(f"proposals/drafts/{index}_{name.replace(' ', '_')}.txt", "w") as f:
            f.write(proposal_text)

if __name__ == "__main__":
    process_proposals()
