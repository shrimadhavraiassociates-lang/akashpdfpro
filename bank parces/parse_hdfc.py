import re
import pandas as pd
import fitz  # PyMuPDF
from utils import clean_amount, get_save_path

def parse_hdfc(pdf_path, password=None, areas=None):
    rows = []
    # Support / and - in dates, anchored to start of line. Supports 01-Jan-2023 and 01/01/2023
    date_pattern = re.compile(r"^\d{2}[/-](?:\d{2}|[A-Za-z]{3})[/-]\d{2,4}")
    # Amount regex to find financial numbers (e.g. 12,345.00)
    amount_pattern = re.compile(r"((?:[\d,]*\d)\.\d{2})")

    doc = fitz.open(pdf_path)
    if password:
        doc.authenticate(password)

    for i, page in enumerate(doc):
        # Determine areas to extract from
        page_rects = []
        if areas:
            if 'all' in areas:
                page_rects = areas['all']
            elif i in areas:
                page_rects = areas[i]
        
        # If no specific areas, use the whole page
        if not page_rects:
            page_rects = [page.rect]

        for rect in page_rects:
            # Extract text from the specific area (clip)
            text = page.get_text("text", clip=rect, sort=True)
            if not text: continue
            lines = text.split("\n")
            current_row = None
            
            for line in lines:
                line = line.strip()
                if not line: continue

                # Check if line starts with a date
                date_match = date_pattern.search(line)
                if date_match:
                    txn_date = date_match.group(0)
                    
                    # Find all amounts in the line
                    amounts = amount_pattern.findall(line)
                    cleaned_amts = [clean_amount(x) for x in amounts]
                    
                    debit = 0.0
                    credit = 0.0
                    balance = 0.0
                    
                    if not amounts:
                        continue

                    first_amt_str = amounts[0]

                    # Logic to assign Debit/Credit/Balance based on count
                    if len(cleaned_amts) >= 3:
                        # HDFC Format: ... Debit Credit Balance
                        debit = cleaned_amts[-3]
                        credit = cleaned_amts[-2]
                        balance = cleaned_amts[-1]
                        first_amt_str = amounts[-3]
                    elif len(cleaned_amts) == 2:
                        # Ambiguous, assume Amount and Balance
                        val = cleaned_amts[-2]
                        balance = cleaned_amts[-1]
                        if "CR" in line.upper() or "CREDIT" in line.upper():
                            credit = val
                        else:
                            debit = val
                        first_amt_str = amounts[-2]
                    else:
                        # Only 1 amount found. Assume it's the transaction amount.
                        val = cleaned_amts[-1]
                        if "CR" in line.upper() or "CREDIT" in line.upper():
                            credit = val
                        else:
                            debit = val
                        first_amt_str = amounts[-1]

                    # Extract Description: Text between Date and First Amount
                    # Check for Value Date (often appears right after Txn Date in HDFC)
                    desc_start_idx = len(txn_date)
                    val_date = ""
                    
                    remaining_text = line[desc_start_idx:].strip()
                    val_date_match = date_pattern.match(remaining_text)
                    if val_date_match:
                        val_date = val_date_match.group(0)
                        # Find where val_date is in the original line to adjust description start
                        val_date_idx = line.find(val_date, desc_start_idx)
                        if val_date_idx != -1:
                            desc_start_idx = val_date_idx + len(val_date)

                    idx_amt = line.find(first_amt_str, desc_start_idx)
                    if idx_amt > -1:
                        desc = line[desc_start_idx:idx_amt].strip()
                    else:
                        desc = line[desc_start_idx:].strip()
                    
                    current_row = [txn_date, val_date, desc, "", debit, credit, balance]
                    rows.append(current_row)
                
                elif current_row:
                    # Append continuation lines
                    if "Statement" not in line and "Page" not in line and "HDFC BANK" not in line and "Balance" not in line:
                        current_row[2] += " " + line.strip()

    df = pd.DataFrame(rows, columns=["Txn Date","Value Date","Description","Ref No.","Debit","Credit","Balance"])
    return df

def convert_hdfc(pdf_path, password=None, areas=None):
    df = parse_hdfc(pdf_path, password, areas=areas)
    out_path = get_save_path("HDFC", pdf_path)
    df.to_excel(out_path, index=False)
    return out_path
