import imaplib
import smtplib
import email
from email.mime.text import MIMEText
import json
import gc
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server named "Communications_Hub"
mcp = FastMCP("Communications_Hub")

def get_email_credentials():
    """Fetches Gmail credentials from the localized secrets directory."""
    dotenv_path = Path(__file__).resolve().parent.parent / 'secrets' / '.env'
    load_dotenv(str(dotenv_path))
    user = os.getenv('GMAIL_ADDRESS')
    password = os.getenv('GMAIL_APP_PASSWORD')
    if not user or not password:
        raise ValueError("Missing GMAIL_ADDRESS or GMAIL_APP_PASSWORD in .env")
    return user, password

@mcp.tool()
def fetch_unread_emails(max_results: int = 3) -> str:
    """Connects via bare-metal IMAP to fetch unread emails from the inbox."""
    try:
        user, password = get_email_credentials()
        
        # Connect to IMAP
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.select("inbox")
        
        # Search for unseen emails
        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK':
            return "Error searching for unseen emails."
            
        mail_ids = messages[0].split()
        if not mail_ids:
            return "No unread emails found."
            
        # Get the latest IDs
        latest_ids = mail_ids[-max_results:]
        results = []
        
        for m_id in reversed(latest_ids):
            status, data = mail.fetch(m_id, '(RFC822)')
            if status != 'OK':
                continue
                
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Extract Subject, From, Body
            subject = msg["Subject"]
            from_addr = msg["From"]
            
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
            else:
                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                
            results.append({
                "from": from_addr,
                "subject": subject,
                "body": body[:1000] # Truncate for LLM context
            })
            
        mail.logout()
        return json.dumps(results, indent=2)

    except Exception as e:
        return f"IMAP Error: {str(e)}"
    finally:
        gc.collect()

@mcp.tool()
def send_email(to_address: str, subject: str, body: str) -> str:
    """Connects via bare-metal SMTP to dispatch a professional email draft."""
    try:
        user, password = get_email_credentials()
        
        # Construct MIME message
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = user
        msg['To'] = to_address
        
        # Connect to SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(user, password)
            server.send_message(msg)
            
        return f"SUCCESS: Email dispatched to {to_address}"

    except Exception as e:
        return f"SMTP Error: {str(e)}"
    finally:
        gc.collect()

if __name__ == "__main__":
    mcp.run()
