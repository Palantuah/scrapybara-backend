import imaplib
import email
from email.header import decode_header
import pandas as pd
import time

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


    # Creative
    "creativeindependent": "Creative", #creative independent
    "design-milk": "Creative", #design milk
    "creativebloq": "Creative", #creative bloq
    "colossal": "Creative", #colossal
    "aiga": "Creative", #aiga
    "creativeboom": "Creative", #creative boom

    # Global News
    "reuters": "Global News", #reuters
    "bbc": "Global News", #bbc
    "theguardian": "Global News", #the guardian
    "apnews": "Global News", #ap news
    "time": "Global News", #time

    # US News
    "nytimes": "US News", #ny times
    "washingtonpost": "US News", #washington post   
    "theguardian": "US News", #the guardian
    "cnn": "US News", #cnn
    "politico": "US News", #politico
    "axios": "US News", #axios
    "usatoday": "US News", #usa today
    "nytimes": "US News", #ny times

    # Tech
    "techcrunch": "Tech", #techcrunch
    "theverge": "Tech", #the verge
    "wired": "Tech", #wired
    "thedownload": "Tech", #the download
    "morningbrew": "Tech", #morning brew
    "engadget": "Tech", #engadget

    # Sports
    "morningblitz": "Sports", #morning blitz
    "yahoosports": "Sports", #yahoo sports
    "cbssports": "Sports", #cbssports
    "thesportsletter.com": "Sports", #the sports letter
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
                # Combine all categories and save to CSV
                all_emails = []
                for emails in categorized_emails.values():
                    all_emails.extend(emails)
                df = pd.DataFrame(all_emails)
                # Drop duplicates based on Message-ID before saving
                df.drop_duplicates(subset=['Message-ID'], keep='first', inplace=True)
                # Sort by date to keep newest entries at the bottom
                df['Date'] = pd.to_datetime(df['Date'])
                df.sort_values('Date', inplace=True)
                df.to_csv('email_database.csv', index=False)
            
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
