import re
import pandas as pd
import pdfplumber
from utils import clean_amount, get_save_path, get_cropped_page

def parse_pnb(pdf_path, password=None, areas=None):
    rows = []
    # PNB Date: dd/mm/yyyy. Use search because Txn No is often the first column.
    date_pattern = re.compile(r"(\d{2}/\d{2}/\d{4})")
    amount_pattern = re.compile(r"((?:[\d,]*\d)\.\d{2})")

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for i, page in enumerate(pdf.pages):
            page = get_cropped_page(page, areas, i)
            text = page.extract_text()
            if not text: continue
            lines = text.split('\n')
            current_row = None
            
            for line in lines:
                line = line.strip()
                if not line: continue
                
                # Skip header lines
                if "Txn No" in line and "Txn Date" in line:
                    continue

                # Search for date
                date_match = date_pattern.search(line)
                if date_match:
                    txn_date = date_match.group(1)
                    
                    # Text before date is Txn No
                    pre_date = line[:date_match.start()].strip()
                    txn_no = pre_date
                    
                    # Text after date
                    post_date = line[date_match.end():].strip()
                    
                    # Find amounts in the text after date
                    amounts = amount_pattern.findall(post_date)
                    cleaned_amts = [clean_amount(x) for x in amounts]
                    
                    debit = 0.0
                    credit = 0.0
                    balance = 0.0
                    
                    if not amounts:
                        continue

                    # Identify Description vs Amounts
                    first_amt_str = amounts[0]
                    idx_amt = post_date.find(first_amt_str)
                    
                    # Description + Branch + Cheque
                    middle_text = post_date[:idx_amt].strip()
                    
                    # Try to extract Cheque No (usually numeric at end of description)
                    cheque_no = ""
                    desc = middle_text
                    tokens = middle_text.split()
                    if tokens:
                        possible_chq = tokens[-1]
                        if possible_chq.isdigit() and len(possible_chq) >= 3:
                            cheque_no = possible_chq
                            desc = " ".join(tokens[:-1])
                    
                    # Assign amounts based on count
                    if len(cleaned_amts) >= 3:
                        debit = cleaned_amts[-3]
                        credit = cleaned_amts[-2]
                        balance = cleaned_amts[-1]
                    elif len(cleaned_amts) == 2:
                        val = cleaned_amts[0]
                        balance = cleaned_amts[1]
                        # Determine Dr/Cr based on previous balance if available
                        if rows:
                            prev_bal = rows[-1][6]
                            # Check if Balance = Prev - Val (Debit) or Prev + Val (Credit)
                            if abs(prev_bal - val - balance) < 1.0:
                                debit = val
                            elif abs(prev_bal + val - balance) < 1.0:
                                credit = val
                            else:
                                debit = val # Default to Debit
                        else:
                            debit = val
                    elif len(cleaned_amts) == 1:
                        balance = cleaned_amts[0]

                    # Use Cheque No as Ref No, fallback to Txn No
                    ref_no = cheque_no if cheque_no else txn_no
                    
                    current_row = [txn_date, "", desc, ref_no, debit, credit, balance]
                    rows.append(current_row)
                
                elif current_row:
                    # Append continuation lines
                    if "Page" not in line and "Statement" not in line and "Balance" not in line and "Txn No" not in line:
                        current_row[2] += " " + line.strip()

    df = pd.DataFrame(rows, columns=["Txn Date", "Value Date", "Description", "Ref No.", "Debit", "Credit", "Balance"])
    return df

def convert_pnb(pdf_path, password=None, areas=None):
    df = parse_pnb(pdf_path, password, areas=areas)
    out_path = get_save_path("PNB", pdf_path)
    df.to_excel(out_path, index=False)
    return out_path
