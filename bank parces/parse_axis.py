import re
import pandas as pd
import pdfplumber
from utils import clean_amount, get_save_path, get_cropped_page

def parse_axis(pdf_path, password=None, areas=None):
    rows = []
    # Axis Date: DD-MM-YYYY or DD/MM/YYYY
    date_pattern = re.compile(r"^(\d{2}[-/]\d{2}[-/]\d{4})")
    # Amount regex: looks for numbers with 2 decimal places (e.g., 12,345.00)
    # This helps distinguish financial amounts from other numbers
    amount_pattern = re.compile(r"((?:[\d,]*\d)\.\d{2})")

    running_balance = None
    
    with pdfplumber.open(pdf_path, password=password) as pdf:
        for i, page in enumerate(pdf.pages):
            page = get_cropped_page(page, areas, i)
            text = page.extract_text()
            if not text: continue
            lines = text.split("\n")
            
            for line in lines:
                line = line.strip()
                if not line: continue

                # 1. Handle Opening Balance (No Date)
                if "OPENING BALANCE" in line.upper():
                    matches = amount_pattern.findall(line)
                    if matches:
                        # The last match is the Balance
                        bal_str = matches[-1]
                        running_balance = clean_amount(bal_str)
                        
                        # Branch is text after the balance
                        # Find where the balance string ends in the line
                        idx = line.rfind(bal_str)
                        branch = line[idx + len(bal_str):].strip()
                        
                        rows.append(["", "", "OPENING BALANCE", 0.0, 0.0, running_balance, branch])
                    continue

                # 2. Handle Transaction Rows
                date_match = date_pattern.match(line)
                if date_match:
                    txn_date = date_match.group(1)
                    
                    matches = amount_pattern.findall(line)
                    
                    if matches:
                        current_balance = clean_amount(matches[-1])
                        debit = 0.0
                        credit = 0.0
                        
                        # MATH LOGIC: Determine Dr/Cr based on change in balance
                        if running_balance is not None:
                            diff = round(running_balance - current_balance, 2)
                            if diff > 0:
                                debit = diff  # Balance decreased -> Debit
                            elif diff < 0:
                                credit = abs(diff)  # Balance increased -> Credit
                        else:
                            # Fallback if Opening Balance missing (rare)
                            # If 3 amounts found, assume Dr, Cr, Bal
                            if len(matches) >= 3:
                                debit = clean_amount(matches[-3])
                                credit = clean_amount(matches[-2])
                        
                        # Update running balance for next row
                        running_balance = current_balance
                        
                        # Extract Description and Branch
                        # Description is between Date and the first amount found
                        first_amt_str = matches[0]
                        amt_start_idx = line.find(first_amt_str)
                        desc_part = line[len(txn_date):amt_start_idx].strip()
                        
                        # Branch is after the last amount
                        last_amt_str = matches[-1]
                        last_amt_idx = line.rfind(last_amt_str)
                        branch = line[last_amt_idx + len(last_amt_str):].strip()

                        # Separate Chq No from Description
                        parts = desc_part.split()
                        chq_no = ""
                        desc = desc_part
                        
                        if parts:
                            # Check for numeric Chq No or placeholders like NA, -
                            if (parts[0].isdigit() and len(parts[0]) > 1) or parts[0].upper() in ["NA", "N.A.", "-"]:
                                chq_no = parts[0]
                                desc = " ".join(parts[1:])
                        
                        rows.append([txn_date, chq_no, desc, debit, credit, current_balance, branch])
                    else:
                        # No amounts found
                        rows.append([txn_date, "", line, 0.0, 0.0, 0.0, ""])

                elif rows and not "OPENING BALANCE" in line and not "Statement" in line and not "Page" in line:
                    # Continuation of description for the previous row
                    rows[-1][2] += " " + line.strip()

    df = pd.DataFrame(rows, columns=["Txn Date", "Chq No", "Description", "Debit", "Credit", "Balance", "Branch Code"])
    return df

def convert_axis(pdf_path, password=None, areas=None):
    df = parse_axis(pdf_path, password, areas=areas)
    out_path = get_save_path("AXIS", pdf_path)
    df.to_excel(out_path, index=False)
    return out_path
