import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import os
import uuid
import platform
import hashlib
from licensing import generate_license, save_license_to_file, verify_admin_password, save_admin_password

ADMIN_PASS_FILE = os.path.expanduser("~/.sma_admin_password.json")

def generate_machine_id():
    unique_str = f"{uuid.getnode()}_{platform.system()}"
    return hashlib.sha256(unique_str.encode()).hexdigest()

class AdminPanelApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Admin Licensing Console")
        self.geometry("600x480")
        self.configure(bg="white")

        self.machine_id = generate_machine_id()

        tk.Label(self, text="Admin Licensing Console", font=("Arial", 20), bg="white").pack(pady=10)
        tk.Label(self, text=f"Current Machine ID: {self.machine_id}", font=("Arial", 9), fg="gray", bg="white").pack()

        form_frame = tk.Frame(self, bg="white")
        form_frame.pack(pady=20)

        tk.Label(form_frame, text="Customer Name:", bg="white").grid(row=0, column=0, sticky="w", pady=5)
        self.name_var = tk.StringVar()
        tk.Entry(form_frame, textvariable=self.name_var, width=30).grid(row=0, column=1)

        tk.Label(form_frame, text="Email:", bg="white").grid(row=1, column=0, sticky="w", pady=5)
        self.email_var = tk.StringVar()
        tk.Entry(form_frame, textvariable=self.email_var, width=30).grid(row=1, column=1)

        tk.Label(form_frame, text="Mobile:", bg="white").grid(row=2, column=0, sticky="w", pady=5)
        self.mobile_var = tk.StringVar()
        tk.Entry(form_frame, textvariable=self.mobile_var, width=30).grid(row=2, column=1)

        tk.Label(form_frame, text="Target Machine ID:", bg="white").grid(row=3, column=0, sticky="w", pady=5)
        self.target_machine_id_var = tk.StringVar()
        tk.Entry(form_frame, textvariable=self.target_machine_id_var, width=30).grid(row=3, column=1)
        tk.Button(form_frame, text="Use Current", command=self.use_current_machine_id, bg="#e0e0e0").grid(row=3, column=2, padx=5)

        tk.Label(form_frame, text="Validity Period:", bg="white").grid(row=4, column=0, sticky="w", pady=5)
        validity_frame = tk.Frame(form_frame, bg="white")
        validity_frame.grid(row=4, column=1)

        self.validity_amount = tk.StringVar(value="30")
        tk.Entry(validity_frame, width=5, textvariable=self.validity_amount).grid(row=0, column=0)

        self.validity_unit = tk.StringVar(value="days")
        validity_combo = ttk.Combobox(
            validity_frame,
            values=["hours", "days", "months", "years"],
            state="readonly",
            width=10,
            textvariable=self.validity_unit,
        )
        validity_combo.grid(row=0, column=1)
        validity_combo.current(1)

        tk.Label(self, text="Generated License Key:", bg="white").pack(pady=10)
        self.license_key_entry = tk.Entry(self, font=("Consolas", 11), width=60)
        self.license_key_entry.pack()

        tk.Button(
            self, text="Generate & Activate License", bg="#4285F4", fg="white", command=self.generate_license
        ).pack(pady=10)

        tk.Button(self, text="Generate Trial License (1 hour)", bg="#FFC107", command=self.generate_trial).pack()

        password_frame = tk.Frame(self, bg="white")
        password_frame.pack(pady=20)

        tk.Label(password_frame, text="Old Admin Password:", bg="white").grid(row=0, column=0, sticky="w", pady=5)
        self.old_password_var = tk.StringVar()
        tk.Entry(password_frame, textvariable=self.old_password_var, show="*").grid(row=0, column=1)

        tk.Label(password_frame, text="New Admin Password:", bg="white").grid(row=1, column=0, sticky="w", pady=5)
        self.new_password_var = tk.StringVar()
        tk.Entry(password_frame, textvariable=self.new_password_var, show="*").grid(row=1, column=1)

        tk.Button(
            self, text="Change Admin Password", bg="#D32F2F", fg="white", command=self.change_password
        ).pack(pady=10)

    def use_current_machine_id(self):
        self.target_machine_id_var.set(self.machine_id)

    def generate_license(self):
        try:
            name = self.name_var.get().strip()
            email = self.email_var.get().strip()
            mobile = self.mobile_var.get().strip()
            target_mid = self.target_machine_id_var.get().strip()
            amount_str = self.validity_amount.get().strip()
            unit = self.validity_unit.get()
            if not (name and email and mobile and target_mid and amount_str.replace(".", "", 1).isdigit()):
                messagebox.showerror("Error", "Please fill all fields correctly.")
                return
            amount = float(amount_str)
            # Convert validity to days
            if unit == "hours":
                amount = amount / 24
            elif unit == "months":
                amount = amount * 30
            elif unit == "years":
                amount = amount * 365

            key = generate_license(name, email, mobile, target_mid, amount)
            self.license_key_entry.delete(0, tk.END)
            self.license_key_entry.insert(0, key)
            save_license_to_file(key)
            messagebox.showinfo("Success", f"License generated for {name} and saved.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate license: {e}")

    def generate_trial(self):
        target = self.target_machine_id_var.get().strip()
        if not target:
            target = self.machine_id
        key = generate_license("Trial User", "trial@example.com", "0000000000", target, 0, trial=True)
        self.license_key_entry.delete(0, tk.END)
        self.license_key_entry.insert(0, key)
        messagebox.showinfo("Trial License", "Trial license generated. Copy and activate it in the main app.")

    def change_password(self):
        old_pwd = self.old_password_var.get()
        new_pwd = self.new_password_var.get()
        if not old_pwd or not new_pwd:
            messagebox.showerror("Error", "Enter both old and new admin passwords.")
            return
        if not verify_admin_password(old_pwd):
            messagebox.showerror("Error", "Old password is incorrect.")
            return
        save_admin_password(new_pwd)
        messagebox.showinfo("Success", "Admin password changed. Please restart the admin panel.")
        self.destroy()

if __name__ == "__main__":
    app = AdminPanelApp()
    app.mainloop()
