import re
import pandas as pd
import pdfplumber
from utils import clean_amount, get_save_path, get_cropped_page

def parse_generic(pdf_path, password=None, areas=None):
    """
    A robust generic parser that attempts to find transactions based on 
    Date patterns and Amount patterns (Debit/Credit/Balance).
    """
    rows = []
    # Matches dates like 01/01/2023, 01-01-2023, 01-Jan-2023
    # Removed ^ anchor to allow dates anywhere in the line (e.g. PNB has Txn No before date)
    date_pattern = re.compile(r"\d{2}[/-](?:\d{2}|[A-Za-z]{3})[/-]\d{2,4}")
    
    # Matches amounts like 1,234.56 or 1234.56 (requires 2 decimal places)
    amount_pattern = re.compile(r"((?:[\d,]*\d)\.\d{2})")

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for i, page in enumerate(pdf.pages):
            # Apply cropping if areas are defined
            page = get_cropped_page(page, areas, i)
            text = page.extract_text()
            if not text:
                continue
            
            lines = text.split("\n")
            current_row = None
            
            for line in lines:
                line = line.strip()
                if not line: continue

                # Check if line contains a date
                date_match = date_pattern.search(line)
                
                if date_match:
                    txn_date = date_match.group(0)
                    date_start = date_match.start()
                    date_end = date_match.end()
                    
                    # Find all valid amounts in the line
                    amounts = amount_pattern.findall(line)
                    
                    if amounts:
                        cleaned_amts = [clean_amount(x) for x in amounts]
                        
                        debit = 0.0
                        credit = 0.0
                        balance = 0.0
                        first_amt_str = amounts[0]

                        # Heuristic to determine columns based on number of amounts found
                        if len(cleaned_amts) >= 3:
                            # Assume format: ... Debit Credit Balance
                            debit = cleaned_amts[-3]
                            credit = cleaned_amts[-2]
                            balance = cleaned_amts[-1]
                            first_amt_str = amounts[-3]
                        elif len(cleaned_amts) == 2:
                            # Assume format: ... Amount Balance
                            # Try to guess if Amount is Cr or Dr based on text
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
                            if "CR" in line.upper():
                                credit = val
                            else:
                                debit = val
                            first_amt_str = amounts[-1]

                        # Extract Description: 
                        # 1. Text before the Date (e.g. Txn No)
                        # 2. Text between Date and the First Amount
                        
                        pre_date_text = line[:date_start].strip()
                        
                        # Find where the relevant amount starts, searching after the date
                        idx_amt = line.find(first_amt_str, date_end)
                        if idx_amt > -1:
                            mid_text = line[date_end:idx_amt].strip()
                        else:
                            mid_text = line[date_end:].strip() # Fallback
                        
                        desc = f"{pre_date_text} {mid_text}".strip()
                        
                        current_row = [txn_date, "", desc, "", debit, credit, balance]
                        rows.append(current_row)
                
                elif current_row:
                    # Append continuation lines to description (skipping headers/footers)
                    if "Page" not in line and "Statement" not in line and "Balance" not in line:
                        current_row[2] += " " + line

    df = pd.DataFrame(rows, columns=["Txn Date", "Value Date", "Description", "Ref No.", "Debit", "Credit", "Balance"])
    return df

def convert_generic(pdf_path, password=None, areas=None, return_df=False):
    df = parse_generic(pdf_path, password, areas=areas)
    if return_df:
        return df
    out_path = get_save_path("Generic", pdf_path)
    df.to_excel(out_path, index=False)
    return out_path