import os
import subprocess
import pandas as pd
import json

def send_whatsapp(phone, message):
    if not phone:
        print("Skip WA: No phone number.")
        return
    print(f"Sending WA to {phone}...")
    # Using 'message' tool logic via subprocess if available, or wacli
    # For simulation/test, we check if wacli exists
    cmd = ["wacli", "send", "--target", phone, "--message", message]
    try:
        subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"[MOCK] WA Sent to {phone}: {message[:50]}...")

def send_email(email, subject, body):
    if not email:
        print("Skip Email: No email address.")
        return
    print(f"Sending Email to {email}...")
    cmd = ["himalaya", "send", "--to", email, "--subject", subject, "--body", body]
    try:
        subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"[MOCK] Email Sent to {email}: {subject}")

def blast(filename="1ai-engage/data/leads.csv"):
    if not os.path.exists(filename):
        print(f"File {filename} not found.")
        return
    
    df = pd.read_csv(filename)
    print(f"Found {len(df)} leads to processing.")
    
    for index, row in df.iterrows():
        email = row.get('email')
        # Handle phone from internationalPhoneNumber or phone column
        phone = row.get('internationalPhoneNumber')
        if not phone or str(phone).lower() == 'nan':
            phone = row.get('phone')
        
        # Parse display name
        name_raw = row.get('displayName')
        name = name_raw
        if isinstance(name_raw, str) and name_raw.startswith('{'):
            try:
                # Replace single quotes with double quotes for valid JSON
                fixed_json = name_raw.replace("'", '"')
                name = json.loads(fixed_json).get('text', 'Business')
            except:
                name = "Business"
        
        safe_name = "".join([c if c.isalnum() else "_" for c in str(name)])
        draft_path = f"1ai-engage/proposals/drafts/{index}_{safe_name}.txt"
        
        if os.path.exists(draft_path):
            with open(draft_path, "r") as f:
                content = f.read()
            
            # Split proposal and WhatsApp draft
            parts = content.split("---WHATSAPP---")
            proposal = parts[0].replace("---PROPOSAL---", "").strip()
            wa_draft = parts[1].strip() if len(parts) > 1 else proposal
            
            print(f"Proccessing Lead: {name}")
            if phone and str(phone) != 'nan':
                send_whatsapp(str(phone), wa_draft)
            
            if email and str(email) != 'nan':
                send_email(str(email), "Collaboration Proposal from BerkahKarya", proposal)
        else:
            print(f"Draft not found for {name} at {draft_path}")

if __name__ == "__main__":
    blast()

if __name__ == "__main__":
    blast()
