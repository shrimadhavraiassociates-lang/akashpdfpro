import re
import pandas as pd
import pdfplumber
from utils import clean_amount, get_save_path, get_cropped_page

def parse_canara(pdf_path, password=None, areas=None):
    rows = []
    date_pattern = re.compile(r"\d{2}[-/]\w{3}[-/]\d{2,4}") # Often uses 01-JAN-2023
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
                if "OPENING BALANCE" in line.upper():
                    matches = amount_pattern.findall(line)
                    if matches:
                        running_balance = clean_amount(matches[-1])
                    continue

                if date_pattern.match(line) or re.match(r"\d{2}/\d{2}/\d{4}", line):
                    matches = amount_pattern.findall(line)
                    if matches:
                        current_balance = clean_amount(matches[-1])
                        debit = 0.0
                        credit = 0.0
                        
                        if running_balance is not None:
                            diff = round(running_balance - current_balance, 2)
                            if diff > 0: debit = diff
                            elif diff < 0: credit = abs(diff)
                        
                        running_balance = current_balance
                        
                        parts = line.split()
                        desc = " ".join(parts[1:-len(matches)])
                        current_row = [parts[0], desc, debit, credit, current_balance]
                        rows.append(current_row)
                elif current_row:
                    current_row[1] += " " + line.strip()

    df = pd.DataFrame(rows, columns=["Date", "Description", "Debit", "Credit", "Balance"])
    return df

def convert_canara(pdf_path, password=None, areas=None):
    df = parse_canara(pdf_path, password, areas=areas)
    out_path = get_save_path("Canara", pdf_path)
    df.to_excel(out_path, index=False)
    return out_path