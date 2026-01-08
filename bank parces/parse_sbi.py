import re
import pandas as pd
import pdfplumber
from utils import clean_amount, get_save_path, get_cropped_page

def parse_sbi(pdf_path, password=None, areas=None):
    rows = []
    date_pattern = re.compile(r"\d{2}[-/]\d{2}[-/]\d{4}")
    amount_pattern = re.compile(r"((?:[\d,]*\d)\.\d{2})")
    running_balance = None

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for i, page in enumerate(pdf.pages):
            page = get_cropped_page(page, areas, i)
            text = page.extract_text()
            if not text: continue
            lines = text.split("\n")
            current_row = None
            
            for line in lines:
                # Check for Opening Balance
                if "BROUGHT FORWARD" in line.upper() or "OPENING BALANCE" in line.upper():
                    matches = amount_pattern.findall(line)
                    if matches:
                        running_balance = clean_amount(matches[-1])
                    continue

                if date_pattern.match(line):
                    matches = amount_pattern.findall(line)
                    if matches:
                        current_balance = clean_amount(matches[-1])
                        debit = 0.0
                        credit = 0.0
                        
                        if running_balance is not None:
                            diff = round(running_balance - current_balance, 2)
                            if diff > 0: debit = diff
                            elif diff < 0: credit = abs(diff)
                        elif len(matches) >= 3:
                            # Fallback if no running balance yet
                            debit = clean_amount(matches[-3])
                            credit = clean_amount(matches[-2])
                        
                        running_balance = current_balance
                        
                        # Extract Description
                        parts = line.split()
                        txn_date = parts[0]
                        val_date = parts[1] if len(parts) > 1 else ""
                        
                        # Description is between Val Date and first amount
                        first_amt = matches[0]
                        idx = line.find(first_amt)
                        desc = line[len(txn_date) + len(val_date) + 2 : idx].strip()
                        
                        current_row = [txn_date, val_date, desc, "", debit, credit, current_balance]
                        rows.append(current_row)
                elif current_row and not "Statement" in line:
                    current_row[2] += " " + line.strip()

    df = pd.DataFrame(rows, columns=["Txn Date", "Value Date", "Description", "Ref No.", "Debit", "Credit", "Balance"])
    return df

def convert_sbi(pdf_path, password=None, areas=None):
    df = parse_sbi(pdf_path, password, areas=areas)
    out_path = get_save_path("SBI", pdf_path)
    df.to_excel(out_path, index=False)
    return out_path
