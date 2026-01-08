import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import subprocess
import threading
import platform
import uuid
import hashlib
import json

# Try importing libraries for visual selection
pdfium_error = None
try:
    import pypdfium2 as pdfium
except ImportError as e:
    print(f"DEBUG: pypdfium2 import failed: {e}")
    pdfium = None
    pdfium_error = str(e)

pil_error = None
try:
    from PIL import Image, ImageTk
except ImportError as e:
    print(f"DEBUG: Pillow import failed: {e}")
    Image = None
    ImageTk = None
    pil_error = str(e)

try:
    import pdfplumber  # Required for auto-detection
except ImportError:
    pdfplumber = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

from licensing import (
    verify_license_key,
    load_license_from_file,
    save_license_to_file,
    format_license_remaining,
)
from parse_generic import convert_generic
from parse_custom import convert_custom

BANK_HANDLERS = {
    "Generic": convert_generic,
}

CONTACT_EMAIL = "akash@shrimadhavraiassociates.in"
CONTACT_PHONE = "+91-9157199960"
OFFICE_HOURS = "MON-FRI 10:00 AM - 6:00 PM"


def generate_machine_id():
    unique_str = f"{uuid.getnode()}_{platform.system()}"
    return hashlib.sha256(unique_str.encode()).hexdigest()


class PDFCropSelector(tk.Toplevel):
    def __init__(self, parent, pdf_path, password=None):
        super().__init__(parent)
        self.title("Select Area to Extract")
        self.geometry("900x700")
        self.pdf_path = pdf_path
        self.password = password
        self.areas = {}  # {page_index: [(x0, y0, x1, y1), ...]}
        self.headers = None
        self.use_grid_lines = False
        self.use_ocr = False
        self.merge_multiline = False
        self.skip_rows = 0
        self.current_page_idx = 0
        self.doc = None
        self.plumber_doc = None
        self.rect_start = None
        self.zoom_scale = 1.0  # To handle display scaling
        self.cancelled = True

        try:
            # pypdfium2 handles password in constructor
            self.doc = pdfium.PdfDocument(self.pdf_path, password=password)
            
            # Open pdfplumber instance for grid preview
            if pdfplumber:
                self.plumber_doc = pdfplumber.open(self.pdf_path, password=self.password)

        except Exception as e:
            messagebox.showerror("Error", f"Could not open PDF: {e}")
            self.destroy()
            return

        # Make window modal and set focus
        self.transient(parent)
        self.grab_set()
        self.focus_set()

        # --- UI Layout ---
        
        # Top Toolbar
        toolbar = tk.Frame(self, bg="#f0f2f5")
        toolbar.pack(side="top", fill="x", padx=5, pady=5)

        tk.Button(toolbar, text="Zoom In (+)", command=self.zoom_in).pack(side="left", padx=5)
        tk.Button(toolbar, text="Zoom Out (-)", command=self.zoom_out).pack(side="left", padx=5)
        tk.Button(toolbar, text="Fit Page", command=self.fit_page).pack(side="left", padx=5)
        tk.Button(toolbar, text="Undo", command=self.undo_last_action).pack(side="left", padx=5)
        
        tk.Frame(toolbar, width=20, bg="#f0f2f5").pack(side="left") # Spacer
        
        tk.Button(toolbar, text="<< Prev", command=self.prev_page).pack(side="left", padx=5)
        self.lbl_page = tk.Label(toolbar, text="Page 1", bg="#f0f2f5", font=("Segoe UI", 10, "bold"))
        self.lbl_page.pack(side="left", padx=10)
        tk.Button(toolbar, text="Next >>", command=self.next_page).pack(side="left", padx=5)

        # Settings Panel (Left Side)
        settings_panel = tk.Frame(self, bg="#e3f2fd", width=250, padx=10, pady=10)
        settings_panel.pack(side="left", fill="y")
        settings_panel.pack_propagate(False)

        tk.Label(settings_panel, text="Extraction Settings", bg="#e3f2fd", font=("Segoe UI", 12, "bold")).pack(pady=(0, 10))
        
        tk.Label(settings_panel, text="Column Headers (comma sep):", bg="#e3f2fd", anchor="w").pack(fill="x")
        self.headers_entry = tk.Entry(settings_panel)
        self.headers_entry.pack(fill="x", pady=(0, 10))
        
        self.grid_var = tk.BooleanVar()
        tk.Checkbutton(settings_panel, text="Use Grid Lines (Borders)", variable=self.grid_var, bg="#e3f2fd", command=self.redraw_rects).pack(anchor="w", pady=(0, 10))

        # Advanced Options
        tk.Label(settings_panel, text="Advanced Options:", bg="#e3f2fd", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 5))
        
        self.merge_var = tk.BooleanVar()
        tk.Checkbutton(settings_panel, text="Merge Multi-line Rows", variable=self.merge_var, bg="#e3f2fd").pack(anchor="w")
        
        self.ocr_var = tk.BooleanVar()
        ocr_state = "normal" if pytesseract else "disabled"
        ocr_text = "Enable OCR (Scanned)" if pytesseract else "Enable OCR (Install Tesseract)"
        tk.Checkbutton(settings_panel, text=ocr_text, variable=self.ocr_var, bg="#e3f2fd", state=ocr_state).pack(anchor="w")

        tk.Label(settings_panel, text="Skip Top N Rows:", bg="#e3f2fd").pack(anchor="w", pady=(5, 0))
        self.skip_rows_entry = tk.Entry(settings_panel, width=5)
        self.skip_rows_entry.insert(0, "0")
        self.skip_rows_entry.pack(anchor="w", pady=(0, 10))

        tk.Button(settings_panel, text="Auto-Detect Tables", bg="#2196f3", fg="white", command=self.auto_detect_tables).pack(fill="x", pady=5)
        tk.Button(settings_panel, text="Clear Page Selection", bg="#ffcdd2", command=self.clear_page_selection).pack(fill="x", pady=5)
        tk.Button(settings_panel, text="Apply to ALL Pages", bg="#ff9800", fg="black", command=self.apply_to_all).pack(fill="x", pady=5)
        tk.Button(settings_panel, text="Clear ALL Pages", bg="#d32f2f", fg="white", command=self.clear_all_pages).pack(fill="x", pady=5)
        
        tk.Label(settings_panel, text="Right-click on a box to delete it.", bg="#e3f2fd", fg="gray", wraplength=230).pack(side="bottom", pady=10)
        tk.Button(settings_panel, text="CONVERT", bg="#4caf50", fg="white", font=("Segoe UI", 12, "bold"), command=self.finish).pack(side="bottom", fill="x", pady=10)

        self.canvas_frame = tk.Frame(self)
        self.canvas_frame.pack(fill="both", expand=True)

        self.v_scroll = tk.Scrollbar(self.canvas_frame, orient="vertical")
        self.h_scroll = tk.Scrollbar(self.canvas_frame, orient="horizontal")
        self.canvas = tk.Canvas(self.canvas_frame, bg="gray", xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)
        
        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)
        
        self.v_scroll.pack(side="right", fill="y")
        self.h_scroll.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Button-3>", self.on_right_click) # Right click to delete

        self.show_page(0)

    def zoom_in(self):
        self.zoom_scale += 0.25
        self.show_page(self.current_page_idx)

    def zoom_out(self):
        if self.zoom_scale > 0.25:
            self.zoom_scale -= 0.25
            self.show_page(self.current_page_idx)

    def fit_page(self):
        self.update_idletasks()
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        if canvas_width > 10 and canvas_height > 10:
            page = self.doc[self.current_page_idx]
            # Calculate scale to fit
            width, height = page.get_size()
            scale_w = canvas_width / width
            scale_h = canvas_height / height
            self.zoom_scale = min(scale_w, scale_h) * 0.95  # 95% to leave a small margin
            self.show_page(self.current_page_idx)

    def undo_last_action(self):
        if self.current_page_idx in self.areas and self.areas[self.current_page_idx]:
            self.areas[self.current_page_idx].pop()
            self.redraw_rects()

    def show_page(self, page_idx):
        if 0 <= page_idx < len(self.doc):
            self.current_page_idx = page_idx
            page = self.doc[page_idx]
            
            # Render page to image using pypdfium2
            bitmap = page.render(scale=self.zoom_scale)
            pil_image = bitmap.to_pil()
            
            self.tk_img = ImageTk.PhotoImage(pil_image)
            
            self.canvas.delete("all")
            self.canvas.config(scrollregion=(0, 0, pil_image.width, pil_image.height))
            self.canvas.create_image(0, 0, image=self.tk_img, anchor="nw")
            
            self.lbl_page.config(text=f"Page {page_idx + 1} of {len(self.doc)}")
            
            # Redraw existing selection if any
            self.redraw_rects()

    def redraw_rects(self):
        self.canvas.delete("saved_rect")
        self.canvas.delete("grid_line")
        if self.current_page_idx in self.areas:
            for (x0, y0, x1, y1) in self.areas[self.current_page_idx]:
                s = self.zoom_scale
                self.canvas.create_rectangle(x0*s, y0*s, x1*s, y1*s, outline="red", width=2, tags="saved_rect")
                self.draw_grid_preview((x0, y0, x1, y1))

    def draw_grid_preview(self, bbox):
        """Draws the detected table cells (rows/cols) inside the selection."""
        if not self.plumber_doc: return
        try:
            page = self.plumber_doc.pages[self.current_page_idx]
            # Ensure bbox is valid
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]: return
            
            # Crop the page to the selection
            cropped = page.crop(bbox, relative=False, strict=False)
            
            use_lines = self.grid_var.get()
            settings = {
                "vertical_strategy": "lines" if use_lines else "text",
                "horizontal_strategy": "lines" if use_lines else "text",
                "intersection_x_tolerance": 15,
                "intersection_y_tolerance": 15,
            }
            
            # Find table structure
            tables = cropped.find_tables(settings)
            s = self.zoom_scale
            
            for table in tables:
                for cell in table.cells:
                    # cell is (x0, top, x1, bottom)
                    if cell[0] is None: continue
                    cx0, cy0, cx1, cy1 = cell
                    self.canvas.create_rectangle(cx0*s, cy0*s, cx1*s, cy1*s, outline="#00e5ff", width=1, tags="grid_line")
        except Exception as e:
            print(f"Grid preview error: {e}")

    def prev_page(self):
        self.show_page(self.current_page_idx - 1)

    def next_page(self):
        self.show_page(self.current_page_idx + 1)

    def on_mouse_down(self, event):
        self.rect_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        self.canvas.delete("drag_rect")

    def on_mouse_drag(self, event):
        if self.rect_start:
            cur_x = self.canvas.canvasx(event.x)
            cur_y = self.canvas.canvasy(event.y)
            self.canvas.delete("drag_rect")
            self.canvas.create_rectangle(self.rect_start[0], self.rect_start[1], cur_x, cur_y, outline="blue", dash=(4, 4), width=2, tags="drag_rect")

    def on_mouse_up(self, event):
        if self.rect_start:
            cur_x = self.canvas.canvasx(event.x)
            cur_y = self.canvas.canvasy(event.y)
            # Normalize coordinates
            x0, x1 = sorted([self.rect_start[0], cur_x])
            y0, y1 = sorted([self.rect_start[1], cur_y])
            
            # Ignore tiny clicks
            if (x1 - x0) < 5 or (y1 - y0) < 5:
                self.rect_start = None
                self.canvas.delete("drag_rect")
                return

            # Store unscaled coordinates (PDF points)
            s = self.zoom_scale
            new_rect = (x0/s, y0/s, x1/s, y1/s)
            
            if self.current_page_idx not in self.areas:
                self.areas[self.current_page_idx] = []
            self.areas[self.current_page_idx].append(new_rect)
            
            self.rect_start = None
            self.canvas.delete("drag_rect")
            self.redraw_rects()

    def on_right_click(self, event):
        # Delete rect under cursor
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        s = self.zoom_scale
        
        if self.current_page_idx in self.areas:
            rects = self.areas[self.current_page_idx]
            # Iterate backwards to remove top-most first
            for i in range(len(rects) - 1, -1, -1):
                x0, y0, x1, y1 = rects[i]
                # Check if click is inside scaled rect
                if (x0*s) <= cx <= (x1*s) and (y0*s) <= cy <= (y1*s):
                    del rects[i]
                    self.redraw_rects()
                    return

    def auto_detect_tables(self):
        if not pdfplumber:
            messagebox.showerror("Error", "pdfplumber library missing.")
            return
        
        detect_all = messagebox.askyesno("Auto-Detect Tables", "Do you want to detect tables on ALL pages?\n\nClick 'Yes' for All Pages.\nClick 'No' for Current Page only.")
        
        try:
            self.config(cursor="watch")
            self.update()
            
            count = 0
            with pdfplumber.open(self.pdf_path, password=self.password) as pdf:
                if detect_all:
                    pages_indices = range(len(pdf.pages))
                else:
                    pages_indices = [self.current_page_idx]
                
                for i in pages_indices:
                    page = pdf.pages[i]
                    tables = page.find_tables()
                    
                    if tables:
                        new_rects = [t.bbox for t in tables]
                        self.areas[i] = new_rects
                        count += len(new_rects)
                    
                    # Keep UI responsive
                    self.update()
            
            self.redraw_rects()
            self.config(cursor="")
            messagebox.showinfo("Auto-Detect", f"Detected {count} table(s) across {len(pages_indices)} page(s).")

        except Exception as e:
            self.config(cursor="")
            messagebox.showerror("Error", f"Detection failed: {e}")

    def clear_page_selection(self):
        if self.current_page_idx in self.areas:
            del self.areas[self.current_page_idx]
            self.redraw_rects()

    def clear_all_pages(self):
        if messagebox.askyesno("Confirm", "Clear selections from ALL pages?"):
            self.areas = {}
            self.redraw_rects()

    def apply_to_all(self):
        if self.current_page_idx in self.areas:
            self.areas = {'all': self.areas[self.current_page_idx]}
            messagebox.showinfo("Applied", "Selection applied to all pages.")
            self.destroy()

    def finish(self):
        h_str = self.headers_entry.get().strip()
        if h_str:
            self.headers = [h.strip() for h in h_str.split(",") if h.strip()]
        self.use_grid_lines = self.grid_var.get()
        self.use_ocr = self.ocr_var.get()
        self.merge_multiline = self.merge_var.get()
        try:
            self.skip_rows = int(self.skip_rows_entry.get())
        except ValueError:
            self.skip_rows = 0
            
        self.cancelled = False
        self.destroy()
    
    def destroy(self):
        if self.plumber_doc:
            self.plumber_doc.close()
        super().destroy()

class BankConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Pro by Akash")
        self.geometry("1100x750")
        self.configure(bg="#f0f2f5")
        self.machine_id = generate_machine_id()
        self.license_data = None
        self.converted_file_path = None

        self.current_frame = None
        self.center_window()
        self.load_license()
        self.show_home()

    def copy_machine_id(self):
        self.clipboard_clear()
        self.clipboard_append(self.machine_id)
        messagebox.showinfo("Copied", "Machine ID copied to clipboard.\nSend this to the admin to get a license.")

    def center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def load_license(self):
        license_key, _ = load_license_from_file()
        if license_key:
            valid, data = verify_license_key(license_key, self.machine_id)
            if valid:
                self.license_data = data
            else:
                self.license_data = None
        else:
            self.license_data = None

    def clear_frame(self):
        if self.current_frame is not None:
            self.current_frame.destroy()
            self.current_frame = None

    def footer(self, parent):
        footer_frame = tk.Frame(parent, bg="#f0f2f5")
        footer_frame.pack(side="bottom", fill="x", pady=8)
        if self.license_data:
            text = (
                f"Licensed to: {self.license_data.get('name', '')} | "
                f"Email: {self.license_data.get('email', '')} | "
                f"Mobile: {self.license_data.get('mobile', '')} | "
                f"Machine ID Start: {self.machine_id[:8]}... | "
                f"Valid: {format_license_remaining(self.license_data)}"
            )
            fg = "green"
        else:
            text = "License not activated."
            fg = "red"
        tk.Label(footer_frame, text=text, fg=fg, bg="#f0f2f5", font=("Segoe UI", 9)).pack()
        tk.Label(
            footer_frame,
            text=CONTACT_EMAIL,
            fg="blue",
            bg="#f0f2f5",
            font=("Segoe UI", 9, "underline"),
        ).pack()
        tk.Label(
            footer_frame, text=f"Call: {CONTACT_PHONE} | Office Hours: {OFFICE_HOURS}", fg="#333333", bg="#f0f2f5", font=("Segoe UI", 9)
        ).pack()

    def show_home(self):
        self.clear_frame()
        frame = tk.Frame(self, bg="#f0f2f5")
        frame.pack(expand=True, fill="both")
        self.current_frame = frame

        tk.Label(
            frame,
            text="PDF Pro by Akash",
            font=("Segoe UI", 28, "bold"),
            fg="#1a237e",
            bg="#f0f2f5",
        ).pack(pady=30)
        tk.Label(
            frame, 
            text="Select your bank to proceed:", 
            font=("Segoe UI", 16), 
            bg="#f0f2f5", 
            fg="#555").pack(pady=10)

        button_frame = tk.Frame(frame, bg="#f0f2f5")
        button_frame.pack(pady=20)

        banks = list(BANK_HANDLERS.keys()) + ["Custom"]
        for idx, bank in enumerate(banks):
            r, c = divmod(idx, 3)
            btn = tk.Button(
                button_frame,
                text=bank,
                font=("Segoe UI", 12, "bold"),
                width=18,
                height=3,
                bg="#ffffff",
                fg="#0d47a1",
                activebackground="#e8eaf6",
                relief="raised",
                borderwidth=1,
                command=lambda b=bank: self.convert_bank_page(b),
            )
            btn.grid(row=r, column=c, padx=15, pady=15)

        tk.Button(
            frame,
            text="Copy Machine ID",
            font=("Segoe UI", 10),
            bg="#e0e0e0",
            fg="black",
            relief="raised",
            command=self.copy_machine_id,
        ).pack(pady=(10, 5))

        tk.Button(
            frame,
            text="Activate License",
            font=("Segoe UI", 12, "bold"),
            bg="#FFA500",
            fg="black",
            relief="flat",
            command=self.activate_license,
            width=20,
        ).pack(pady=10)

        self.footer(frame)

    def activate_license(self):
        license_key = simpledialog.askstring(
            "License Activation", "Paste your license key here:", parent=self
        )
        if not license_key:
            messagebox.showinfo("Activation Cancelled", "No license key entered.")
            return
        
        try:
            valid, data_or_msg = verify_license_key(license_key.strip(), self.machine_id)
            if valid:
                save_license_to_file(license_key.strip())
                self.license_data = data_or_msg
                messagebox.showinfo(
                    "Activation Successful", f"License activated for {data_or_msg.get('name', 'User')}"
                )
                self.show_home()
            else:
                messagebox.showerror("Invalid License", data_or_msg)
        except Exception as e:
            messagebox.showerror("Activation Error", f"An error occurred: {e}")

    def convert_bank_page(self, bank_name):
        self.clear_frame()
        frame = tk.Frame(self, bg="#f0f2f5")
        frame.pack(expand=True, fill="both")
        self.current_frame = frame

        tk.Label(
            frame,
            text=f"Convert PDF for {bank_name}",
            font=("Segoe UI", 24, "bold"),
            bg="#f0f2f5",
            fg="#1a237e",
        ).pack(pady=20)

        tk.Button(
            frame,
            text="Select PDF File",
            font=("Segoe UI", 14),
            bg="#2e7d32",
            fg="white",
            width=20,
            relief="flat",
            command=lambda: self.convert_pdf(bank_name),
        ).pack(pady=15)

        tk.Button(
            frame,
            text="Select Area & Convert",
            font=("Segoe UI", 12),
            bg="#0277bd",
            fg="white",
            width=20,
            relief="flat",
            command=lambda: self.convert_pdf(bank_name, select_area=True),
        ).pack(pady=5)

        tk.Button(
            frame,
            text="Back to Home",
            font=("Segoe UI", 12),
            bg="#757575",
            fg="white",
            width=15,
            relief="flat",
            command=self.show_home,
        ).pack(pady=15)

        self.footer(frame)

    def open_file_location(self, filepath):
        if not os.path.exists(filepath):
            messagebox.showerror("Error", "File does not exist.")
            return
        folder_path = os.path.dirname(filepath)
        try:
            if platform.system() == "Windows":
                os.startfile(filepath)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", filepath])
            else:  # Linux and others
                subprocess.Popen(["xdg-open", filepath])
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open file: {e}")

    def open_folder_location(self, filepath):
        if not os.path.exists(filepath):
            messagebox.showerror("Error", "File does not exist.")
            return
        folder_path = os.path.dirname(filepath)
        try:
            if platform.system() == "Windows":
                subprocess.Popen(f'explorer /select,"{filepath}"')
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", folder_path])
            else:  # Linux and others
                subprocess.Popen(["xdg-open", folder_path])
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open folder: {e}")

    def convert_pdf(self, bank, select_area=False):
        if not self.license_data:
            messagebox.showwarning("License", "Activate license to convert PDFs.")
            self.show_home()
            return

        pdf_path = filedialog.askopenfilename(
            title=f"Select {bank} PDF file", filetypes=[("PDF Files", "*.pdf")]
        )
        if not pdf_path:
            return

        pdf_pwd = simpledialog.askstring(
            "PDF Password", "Enter PDF password (leave blank if none):", show="*"
        )

        headers = None
        column_indices = None
        use_grid_lines = False
        use_ocr = False
        merge_multiline = False
        skip_rows = 0

        areas = None
        
        # Check if we have the libraries needed for visual selection
        has_visual_libs = (pdfium is not None) and (Image is not None)
        should_open_selector = False

        if select_area:
            # User explicitly requested visual selection. Must have dependencies.
            if not has_visual_libs:
                msg = "Visual selection libraries failed to load:\n"
                if pdfium is None:
                    msg += f"\n• pypdfium2 Error: {pdfium_error}\n  (Try running: pip install pypdfium2)"
                if Image is None:
                    msg += f"\n• Pillow Error: {pil_error}\n  (Try running: pip install pillow)"
                msg += "\n\nCannot proceed with visual selection."
                messagebox.showerror("Dependency Error", msg)
                return
            should_open_selector = True
        
        elif (bank == "Generic" or bank == "Custom") and has_visual_libs:
            # Optional visual selection: Only ask if libraries are present
            if messagebox.askyesno("Select Area", "Do you want to visually select the table area?"):
                should_open_selector = True

        if should_open_selector:
            selector = PDFCropSelector(self, pdf_path, pdf_pwd)
            self.wait_window(selector)
            
            if getattr(selector, 'cancelled', True):
                return

            areas = selector.areas
            
            if bank == "Custom":
                headers = selector.headers
                use_grid_lines = selector.use_grid_lines
                use_ocr = selector.use_ocr
                merge_multiline = selector.merge_multiline
                skip_rows = selector.skip_rows

            if not areas:
                if not messagebox.askyesno("No Selection", "No area selected. Continue with full page?"):
                    return

        self.show_loading(f"Processing {bank} PDF...\nPlease wait.")

        # Run conversion in a separate thread to prevent UI freezing
        thread = threading.Thread(target=self._run_conversion, args=(bank, pdf_path, pdf_pwd, areas, headers, column_indices, use_grid_lines, use_ocr, merge_multiline, skip_rows))
        thread.daemon = True
        thread.start()

    def show_loading(self, message):
        self.clear_frame()
        frame = tk.Frame(self, bg="#f0f2f5")
        frame.pack(expand=True, fill="both")
        self.current_frame = frame

        tk.Label(
            frame,
            text=message,
            font=("Segoe UI", 20),
            bg="#f0f2f5",
            fg="#0d47a1"
        ).pack(pady=100)

        # Indeterminate progress bar
        pb = ttk.Progressbar(frame, orient="horizontal", length=400, mode="indeterminate")
        pb.pack(pady=20)
        pb.start(10)

    def _run_conversion(self, bank, pdf_path, pdf_pwd, areas=None, headers=None, column_indices=None, use_grid_lines=False, use_ocr=False, merge_multiline=False, skip_rows=0):
        try:
            if bank == "Custom":
                out_file = convert_custom(pdf_path, pdf_pwd, areas=areas, headers=headers, column_indices=column_indices, use_grid_lines=use_grid_lines, use_ocr=use_ocr, merge_multiline=merge_multiline, skip_rows=skip_rows)
            else:
                convert_func = BANK_HANDLERS.get(bank, BANK_HANDLERS["Generic"])
                if areas:
                    out_file = convert_func(pdf_path, pdf_pwd, areas=areas)
                else:
                    out_file = convert_func(pdf_path, pdf_pwd)
            # Schedule UI update on main thread
            self.after(0, lambda: self.on_conversion_success(out_file))
        except Exception as e:
            self.after(0, lambda: self.on_conversion_error(str(e)))

    def on_conversion_success(self, out_file):
        self.converted_file_path = out_file
        self.show_post_conversion()

    def on_conversion_error(self, error_msg):
        messagebox.showerror("Conversion Failed", error_msg)
        self.show_home()

    def show_post_conversion(self):
        self.clear_frame()
        frame = tk.Frame(self, bg="#f0f2f5")
        frame.pack(expand=True, fill="both")
        self.current_frame = frame

        tk.Label(
            frame,
            text="Conversion Successful!",
            font=("Segoe UI", 28, "bold"),
            fg="#2e7d32",
            bg="#f0f2f5",
        ).pack(pady=50)

        tk.Label(
            frame,
            text=f"File saved at:\n{self.converted_file_path}",
            font=("Segoe UI", 12),
            bg="#f0f2f5",
            fg="#333",
            wraplength=800
        ).pack(pady=15)

        btn_frame = tk.Frame(frame, bg="#f0f2f5")
        btn_frame.pack(pady=15)

        tk.Button(
            btn_frame,
            text="Open File",
            font=("Segoe UI", 12),
            bg="#2e7d32",
            fg="white",
            width=15,
            relief="flat",
            command=lambda: self.open_file_location(self.converted_file_path),
        ).grid(row=0, column=0, padx=10)

        tk.Button(
            btn_frame,
            text="Open Folder",
            font=("Segoe UI", 12),
            bg="#1565c0",
            fg="white",
            width=15,
            relief="flat",
            command=lambda: self.open_folder_location(self.converted_file_path),
        ).grid(row=0, column=1, padx=10)

        tk.Button(
            frame,
            text="Back to Home",
            font=("Segoe UI", 12),
            bg="#0d47a1",
            fg="white",
            width=20,
            relief="flat",
            command=self.show_home,
        ).pack(pady=30)

        self.footer(frame)


if __name__ == "__main__":
    app = BankConverterApp()
    app.mainloop()
