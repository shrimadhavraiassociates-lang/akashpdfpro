import os

def clean_amount(value):
    """Cleans currency strings (e.g., '1,200.00 Cr') into floats."""
    if value is None or value.strip() in ["", "-"]:
        return 0.0
    try:
        # Remove commas, currency symbols, Cr/Dr markers
        cleaned = value.replace(",", "").replace("Cr", "").replace("Dr", "").replace("Rs.", "").strip()
        return float(cleaned) if cleaned else 0.0
    except:
        return 0.0

def get_save_path(bank_name, original_pdf_path):
    """Generates a save path in the user's Documents folder."""
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    folder = os.path.join(docs, "SMA_TRANSACTION", bank_name)
    os.makedirs(folder, exist_ok=True)
    filename = os.path.basename(original_pdf_path).replace(".pdf", f"_{bank_name.lower()}.xlsx")
    return os.path.join(folder, filename)

def get_cropped_page(page, areas, page_idx):
    """Crops the page if areas are defined for this page or globally."""
    if not areas:
        return page
    bbox = None
    if 'all' in areas:
        bbox = areas['all']
    elif page_idx in areas:
        bbox = areas[page_idx]
    
    if bbox:
        # Handle list of rects (take first one as fallback for single-area parsers)
        if isinstance(bbox, list):
            if len(bbox) > 0:
                bbox = bbox[0]
            else:
                return page
        return page.crop(bbox, relative=False, strict=False)
    return page