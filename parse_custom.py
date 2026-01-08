import re
import pandas as pd
import pdfplumber
try:
    import pypdfium2 as pdfium
except ImportError:
    pdfium = None
from utils import get_save_path, get_cropped_page

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from PIL import Image
except ImportError:
    Image = None

def parse_custom(pdf_path, password=None, areas=None, headers=None, column_indices=None, use_grid_lines=False, use_ocr=False, merge_multiline=False, skip_rows=0):
    """
    Parses a PDF based on visually selected areas and user-provided headers.
    Uses pdfplumber's table extraction with text-based strategies.
    """

    rows = []
    # Use text strategy as it works best for visual areas without explicit lines
    table_settings = {
        "vertical_strategy": "lines" if use_grid_lines else "text",
        "horizontal_strategy": "lines" if use_grid_lines else "text",
        "intersection_x_tolerance": 15,
        "intersection_y_tolerance": 15,
    }

    pdfium_doc = None
    if use_ocr and pdfium:
        pdfium_doc = pdfium.PdfDocument(pdf_path, password=password)

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for i, page in enumerate(pdf.pages):
            # Determine areas for this page (support list of rects)
            page_bboxes = []
            if areas:
                if 'all' in areas:
                    page_bboxes = areas['all']
                elif i in areas:
                    page_bboxes = areas[i]
            elif areas is None:
                # Fallback to full page if no areas defined (e.g. libraries missing)
                page_bboxes = [page.bbox]
            
            # If no areas defined, skip page
            if not page_bboxes:
                continue
            
            # 1. Group bboxes into "Row Groups" (tables or split tables) based on Y-overlap
            # Sort by top Y first
            page_bboxes.sort(key=lambda b: b[1]) 
            
            groups = []
            if page_bboxes:
                current_group = [page_bboxes[0]]
                # Union rect of current group
                g_y0, g_y1 = page_bboxes[0][1], page_bboxes[0][3]
                
                for bbox in page_bboxes[1:]:
                    b_y0, b_y1 = bbox[1], bbox[3]
                    
                    # Check overlap
                    overlap_start = max(g_y0, b_y0)
                    overlap_end = min(g_y1, b_y1)
                    overlap_height = max(0, overlap_end - overlap_start)
                    min_height = min(g_y1 - g_y0, b_y1 - b_y0)
                    
                    # If significant overlap (e.g., > 40% of the shorter box), group them (Columns)
                    if overlap_height > 0.4 * min_height:
                        current_group.append(bbox)
                        g_y0 = min(g_y0, b_y0)
                        g_y1 = max(g_y1, b_y1)
                    else:
                        groups.append(current_group)
                        current_group = [bbox]
                        g_y0, g_y1 = b_y0, b_y1
                groups.append(current_group)

            # 2. Process each group
            for group in groups:
                if len(group) == 1:
                    # Single area
                    bbox = group[0]
                    
                    if use_ocr and pdfium_doc and pytesseract and Image:
                        # OCR Strategy
                        try:
                            # Get image of the area
                            f_page = pdfium_doc[i]
                            # Render full page at 3x scale (approx 216 DPI)
                            bitmap = f_page.render(scale=3)
                            pil_img = bitmap.to_pil()
                            
                            # Crop to bbox (scale bbox coordinates by 3)
                            crop_rect = (bbox[0]*3, bbox[1]*3, bbox[2]*3, bbox[3]*3)
                            img = pil_img.crop(crop_rect)
                            
                            # Preprocessing: Grayscale and Thresholding
                            img = img.convert('L')
                            img = img.point(lambda x: 0 if x < 140 else 255, '1')
                            
                            # Run OCR (Assume uniform block of text - PSM 6)
                            ocr_text = pytesseract.image_to_string(img, config='--psm 6')
                            
                            # Simple parsing: split by lines, then by whitespace (approximate)
                            for line in ocr_text.split('\n'):
                                if line.strip():
                                    # Split by 2+ spaces to separate columns
                                    parts = [p.strip() for p in re.split(r'\s{2,}', line) if p.strip()]
                                    cleaned_row = process_row(parts, column_indices)
                                    if any(cleaned_row):
                                        rows.append(cleaned_row)
                        except Exception as e:
                            print(f"OCR Error on page {i}: {e}")
                        continue

                    # Standard Text Extraction
                    try:
                        cropped_page = page.crop(bbox, relative=False, strict=False)
                        tables = cropped_page.extract_tables(table_settings)
                        for table in tables:
                            for row in table:
                                cleaned_row = process_row(row, column_indices)
                                if any(cleaned_row):
                                    rows.append(cleaned_row)
                    except Exception as e:
                        print(f"Error processing area on page {i}: {e}")
                else:
                    # Multiple areas side-by-side -> Column Mode
                    # Sort by X to assign column order
                    group.sort(key=lambda b: b[0])
                    
                    # Extract words from each column-box
                    col_words = []
                    for col_idx, bbox in enumerate(group):
                        try:
                            c_page = page.crop(bbox, relative=False, strict=False)
                            words = c_page.extract_words(keep_blank_chars=True)
                            for w in words:
                                w['col_idx'] = col_idx
                            col_words.extend(words)
                        except:
                            pass
                    
                    # Group words by Y (rows)
                    col_words.sort(key=lambda w: w['top'])
                    
                    current_row_words = []
                    if col_words:
                        # Initialize row bounds with the first word
                        current_row_top = col_words[0]['top']
                        current_row_bottom = col_words[0]['bottom']
                        
                        for w in col_words:
                            # Check vertical overlap with current row
                            w_mid = (w['top'] + w['bottom']) / 2
                            if current_row_top - 3 <= w_mid <= current_row_bottom + 3:
                                current_row_words.append(w)
                                current_row_bottom = max(current_row_bottom, w['bottom'])
                            else:
                                # Finish current row
                                rows.append(build_row_from_words(current_row_words, len(group)))
                                # Start new row
                                current_row_words = [w]
                                current_row_top = w['top']
                                current_row_bottom = w['bottom']
                        # Append last row
                        rows.append(build_row_from_words(current_row_words, len(group)))

    # Post-Processing Options
    
    # 1. Merge Multi-line Rows
    if merge_multiline and rows:
        merged_rows = []
        prev_row = None
        for row in rows:
            # If first column is empty (and row has content), assume continuation
            if not row[0] and any(row) and prev_row:
                # Merge text into previous row
                for k in range(len(row)):
                    if row[k]:
                        prev_row[k] = (str(prev_row[k]) + " " + str(row[k])).strip()
            else:
                if prev_row: merged_rows.append(prev_row)
                prev_row = row
        if prev_row: merged_rows.append(prev_row)
        rows = merged_rows

    # 2. Skip Top Rows
    if skip_rows > 0 and len(rows) > skip_rows:
        rows = rows[skip_rows:]

    # Dynamic Header Adjustment
    if not rows:
        final_headers = headers if headers else ["No Data"]
    else:
        max_cols = max(len(r) for r in rows)
        if not headers:
            final_headers = [f"Column {i+1}" for i in range(max_cols)]
        else:
            final_headers = headers[:]
            if len(final_headers) < max_cols:
                final_headers.extend([f"Column {i+1}" for i in range(len(final_headers), max_cols)])
            elif len(final_headers) > max_cols:
                # Pad rows to match headers
                for r in rows:
                    r.extend([""] * (len(final_headers) - len(r)))

    df = pd.DataFrame(rows, columns=final_headers)
    
    # Attempt to convert numeric strings to actual numbers for Excel
    for col in df.columns:
        df[col] = df[col].apply(convert_to_number_if_possible)
        
    return df

def process_row(row, column_indices):
    cleaned_row = []
    if column_indices:
        for idx in column_indices:
            if idx < len(row):
                cell = row[idx]
                cleaned_row.append(cell.strip() if cell else "")
            else:
                cleaned_row.append("")
    else:
        cleaned_row = [cell.strip() if cell else "" for cell in row]
    return cleaned_row

def build_row_from_words(words, num_cols):
    row_data = [""] * num_cols
    cols = {}
    for w in words:
        idx = w['col_idx']
        if idx not in cols: cols[idx] = []
        cols[idx].append(w)
    
    for idx in cols:
        cols[idx].sort(key=lambda x: x['x0'])
        text = " ".join([word['text'] for word in cols[idx]])
        if idx < num_cols:
            row_data[idx] = text
    return row_data

def convert_to_number_if_possible(val):
    """Converts string to float if it looks like a number (handles commas)."""
    if not isinstance(val, str):
        return val
    val_clean = val.replace(',', '').strip()
    if not val_clean:
        return val
    
    # Avoid converting strings with leading zeros that are not decimals (e.g. "0123" -> 123)
    # This preserves Cheque Numbers
    if val_clean.startswith('0') and len(val_clean) > 1 and '.' not in val_clean:
        return val
        
    try:
        return float(val_clean)
    except ValueError:
        return val

def convert_custom(pdf_path, password=None, areas=None, headers=None, column_indices=None, use_grid_lines=False, use_ocr=False, merge_multiline=False, skip_rows=0, return_df=False):
    df = parse_custom(pdf_path, password, areas=areas, headers=headers, column_indices=column_indices, use_grid_lines=use_grid_lines, use_ocr=use_ocr, merge_multiline=merge_multiline, skip_rows=skip_rows)
    if return_df:
        return df
    out_path = get_save_path("Custom", pdf_path)
    df.to_excel(out_path, index=False)
    return out_path