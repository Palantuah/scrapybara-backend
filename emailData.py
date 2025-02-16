import imaplib
import email
from email.header import decode_header
import pandas as pd
import time
import re

# Email configuration
user_email = "palantuah@gmail.com"
app_password = "kzwp ozof vwbu kivk"    

# Define sender categories with partial matches
SENDER_CATEGORIES = {
    # Finance
    "morningbrew": "Finance",        # Morning Brew
    "finimize": "Finance",           # Finimize
    "hustle": "Finance",             # The Hustle
    "cnbc": "Finance",               # CNBC
    "seekingalpha": "Finance",       # Seeking Alpha
    "bloomberg": "Finance",          # Bloomberg

    # Global News
    "reuters": "Global News",        # Reuters
    "bbc": "Global News",           # BBC
    "apnews": "Global News",        # AP News
    "time": "Global News",          # Time

    # US News
    "nytimes": "US News",           # NY Times
    "washingtonpost": "US News",    # Washington Post
    "theguardian": "US News",       # The Guardian
    "cnn": "US News",               # CNN
    "politico": "US News",          # Politico
    "axios": "US News",             # Axios
    "usatoday": "US News",          # USA Today

    # Tech
    "techcrunch": "Tech",           # TechCrunch
    "theverge": "Tech",             # The Verge
    "wired": "Tech",                # Wired
    "thedownload": "Tech",          # The Download
    "morningbrew": "Tech",          # Morning Brew
    "engadget": "Tech",             # Engadget

    # Sports
    "morningblitz": "Sports",       # Morning Blitz
    "yahoosports": "Sports",        # Yahoo Sports
    "cbssports": "Sports",          # CBS Sports
    "thesportsletter.com": "Sports" # The Sports Letter
}

def get_sender_category(from_address):
    from_address = from_address.lower()  # Convert to lowercase for case-insensitive matching
    for keyword, category in SENDER_CATEGORIES.items():
        if keyword.lower() in from_address:
            return category
    return "Uncategorized"

def process_email(msg):
    # Decode the email subject
    subject, encoding = decode_header(msg.get("Subject"))[0]
    if isinstance(subject, bytes):
        subject = subject.decode(encoding if encoding else "utf-8", errors="ignore")
    
    # Extract email address only from the From field
    from_full = msg.get("From")
    # Extract email address between < and >
    from_ = from_full[from_full.find("<")+1:from_full.find(">")]
    if "@" not in from_:  # If no angle brackets, use the full string
        from_ = from_full
    
    date_ = msg.get("Date")
    
    # Extract body
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                try:
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
                except Exception:
                    continue
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except Exception:
            pass
    
    category = get_sender_category(from_)
    
    return {
        "Subject": subject,
        "From": from_,
        "Date": date_,
        "Body": body,
        "Category": category
    }

def clean_content(text):
    """Clean email content by removing HTML and unnecessary formatting"""
    if not text:
        return ""
        
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove URLs
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    
    # Remove email addresses
    text = re.sub(r'[\w\.-]+@[\w\.-]+', '', text)
    
    # Handle quotes - escape double quotes with another double quote
    text = text.replace('"', '""')
    
    # Remove special characters and extra whitespace
    text = re.sub(r'[\r\n\t]+', ' ', text)  # Replace newlines/tabs with space
    text = re.sub(r'\s+', ' ', text)  # Normalize spaces
    
    return text.strip()

def main():
    # Initialize tracking sets and dicts
    processed_emails = set()
    categorized_emails = {}
    
    # Load existing data from CSV if it exists
    try:
        existing_df = pd.read_csv('email_database.csv')
        # Drop any duplicates that might exist in the CSV
        existing_df.drop_duplicates(subset=['Message-ID'], keep='first', inplace=True)
        
        # Initialize categorized_emails from deduplicated data
        for category in existing_df['Category'].unique():
            category_df = existing_df[existing_df['Category'] == category]
            categorized_emails[category] = category_df.to_dict('records')
        
        # Add existing message IDs to processed_emails set
        if 'Message-ID' in existing_df.columns:
            processed_emails.update(existing_df['Message-ID'].dropna().tolist())
            
        # Save deduplicated data back to CSV
        existing_df.to_csv('email_database.csv', index=False)
    except FileNotFoundError:
        pass
    
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    imap.login(user_email, app_password)
    
    while True:
        try:
            imap.select("INBOX")
            status, messages = imap.search(None, "ALL")
            if status != "OK":
                continue
            
            new_emails_found = False
            for num in messages[0].split():
                if num.decode() not in processed_emails:
                    status, data = imap.fetch(num, "(RFC822)")
                    if status != "OK":
                        continue
                    
                    msg = email.message_from_bytes(data[0][1])
                    message_id = msg.get("Message-ID", num.decode())  # Use Message-ID or fallback to num
                    
                    if message_id not in processed_emails:
                        email_data = process_email(msg)
                        email_data['Message-ID'] = message_id  # Add Message-ID to stored data
                        
                        category = email_data["Category"]
                        if category not in categorized_emails:
                            categorized_emails[category] = []
                        categorized_emails[category].append(email_data)
                        
                        processed_emails.add(message_id)
                        new_emails_found = True
                        print(f"New email received in category: {category}")
            
            if new_emails_found:
                all_emails = []
                for category, emails in categorized_emails.items():
                    # Only process valid categories
                    if category in ["Finance", "Global News", "US News", "Tech", "Sports"]:
                        # Clean each email's content before adding
                        for email_item in emails:
                            email_item['Body'] = clean_content(email_item['Body'])
                        all_emails.extend(emails)
                
                df = pd.DataFrame(all_emails)
                df.drop_duplicates(subset=['Message-ID'], keep='first', inplace=True)
                
                # Write CSV with minimal quoting
                df.to_csv('email_database.csv', index=False, quoting=1, escapechar='\\')
            
            time.sleep(15)
            
        except Exception as e:
            print(f"Error occurred: {e}")
            try:
                imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
                imap.login(user_email, app_password)
            except:
                print("Failed to reconnect, waiting before retry...")
            time.sleep(15)
            continue

    try:
        imap.logout()
    except:
        pass

if __name__ == "__main__":
    main()
