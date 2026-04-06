import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import easyocr
import cv2
import numpy as np
from pdf2image import convert_from_bytes
from extract import extract_key_value_pairs, extract_table_rows
import csv
import re
import threading
import time
import os
import sys

# For compatibility with PyInstaller
POPLER_PATH = os.path.join(getattr(sys, '_MEIPASS', os.path.abspath(".")), "poppler", "Library", "bin")

class InvoiceOCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📜 Invoice OCR")
        self.root.geometry("1080x860")
        self.root.configure(bg="#ecf0f1")
        self.root.attributes('-alpha', 0.0)

        self.reader = easyocr.Reader(['en'])
        self.file_path = ""
        self.results = []
        self.key_values = {}
        self.table_rows = []
        self.extracted_text = []

        self.create_start_screen()
        threading.Thread(target=self.fade_in).start()

    def fade_in(self, duration=1.5):
        for i in range(11):
            alpha = i / 10
            self.root.attributes('-alpha', alpha)
            time.sleep(duration / 10)

    def create_start_screen(self):
        self.clear_root()
        self.bg_img = Image.open("background.jpg").resize((1080, 860))
        self.bg_img_tk = ImageTk.PhotoImage(self.bg_img)
        bg_label = tk.Label(self.root, image=self.bg_img_tk)
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        self.splash_frame = tk.Frame(self.root, bg="#ffffff", bd=0)
        self.splash_frame.place(relx=0.5, rely=0.5, anchor="center")

        title = tk.Label(
            self.splash_frame,
            text="📄 Invoice Extraction App",
            font=("Segoe UI", 28, "bold"),
            bg="#ffffff",
            fg="#2c3e50"
        )
        title.pack(pady=(20, 40))

        self.start_btn = tk.Button(
            self.splash_frame,
            text="🚀 Start & Upload Invoice",
            font=("Segoe UI", 18, "bold"),
            bg="#2ecc71",
            fg="white",
            padx=30,
            pady=10,
            relief="flat",
            activebackground="#27ae60",
            command=lambda: [self.create_main_interface(), self.load_file()]
        )
        self.start_btn.pack()

    def create_main_interface(self):
        self.clear_root()

        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True)

        sidebar = tk.Frame(main_frame, bg="#2c3e50", width=180)
        sidebar.pack(side="left", fill="y")

        def add_sidebar_button(text, command):
            return tk.Button(
                sidebar,
                text=text,
                command=command,
                font=("Segoe UI", 10, "bold"),
                bg="#34495e",
                fg="white",
                relief="flat",
                activebackground="#16a085",
                activeforeground="white",
                padx=10,
                pady=10,
                anchor="w"
            )

        self.entry_key = ttk.Entry(sidebar, width=18)
        self.entry_key.pack(padx=10, pady=(20, 10))

        add_sidebar_button("📤 Upload Invoice", self.load_file).pack(fill="x")
        add_sidebar_button("🔎 Search Key", self.search_key).pack(fill="x")
        add_sidebar_button("📋 Show OCR Text", self.show_ocr).pack(fill="x")
        add_sidebar_button("📊 Show Table Rows", self.show_table).pack(fill="x")
        add_sidebar_button("📋 Show Exact Table", self.show_exact_table).pack(fill="x")
        add_sidebar_button("📋 Show Table (Grid)", self.show_table_grid).pack(fill="x")
        add_sidebar_button("📈 Summary Stats", self.show_summary).pack(fill="x")
        add_sidebar_button("💾 Export CSV", self.export_csv).pack(fill="x")
        add_sidebar_button("🔁 Back to Start", self.create_start_screen).pack(fill="x")

        content_frame = ttk.Frame(main_frame)
        content_frame.pack(side="right", fill="both", expand=True)

        frame_img = ttk.LabelFrame(content_frame, text="📄 Uploaded Invoice", padding=10)
        frame_img.pack(padx=10, pady=10, fill="both", expand=True)

        frame_results = ttk.LabelFrame(content_frame, text="🔍 Results", padding=10)
        frame_results.pack(padx=10, pady=10, fill="both", expand=True)

        self.lbl_image = ttk.Label(frame_img)
        self.lbl_image.pack()

        self.text_result = tk.Text(frame_results, wrap=tk.WORD, height=20, bg="#ffffff", font=("Segoe UI", 10))
        self.text_result.pack(padx=5, pady=5, fill="both", expand=True)

    def clear_root(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def load_file(self):
        self.file_path = filedialog.askopenfilename(filetypes=[("Images or PDFs", "*.jpg *.jpeg *.png *.pdf")])
        if not self.file_path:
            return

        self.text_result.delete("1.0", tk.END)
        self.extracted_text = []

        try:
            if self.file_path.lower().endswith(".pdf"):
                images = convert_from_bytes(open(self.file_path, 'rb').read(), poppler_path=POPLER_PATH)
                image = cv2.cvtColor(np.array(images[0]), cv2.COLOR_RGB2BGR)
            else:
                image = cv2.imread(self.file_path)

            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            self.results = self.reader.readtext(image_rgb)
            self.key_values = extract_key_value_pairs(self.results)
            self.table_rows = extract_table_rows(self.results)

            for (bbox, text, prob) in self.results:
                self.extracted_text.append((text, f"{round(prob*100, 1)}%"))
                (tl, tr, br, bl) = bbox
                tl = tuple(map(int, tl))
                br = tuple(map(int, br))
                cv2.rectangle(image, tl, br, (0, 255, 0), 2)

            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(image).resize((400, 300))
            self.img_tk = ImageTk.PhotoImage(img)
            self.lbl_image.configure(image=self.img_tk)
            self.lbl_image.image = self.img_tk

            self.show_ocr()
            self.show_table()

            messagebox.showinfo("Success", "Invoice loaded and processed successfully!")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to process the invoice:\n{str(e)}")

    def search_key(self):
        query = self.entry_key.get().strip().lower()
        self.text_result.delete("1.0", tk.END)
        found = False

        for k, v in self.key_values.items():
            # Normalize: remove punctuation/spaces for fuzzy match
            key_normalized = re.sub(r'[^a-zA-Z0-9]', '', k.lower())
            query_normalized = re.sub(r'[^a-zA-Z0-9]', '', query)

            if query in k.lower() or query_normalized in key_normalized:
                self.text_result.insert(tk.END, f"🔑 {k}: {v}\n\n")
                found = True

        if not found:
            self.text_result.insert(tk.END, "❌ No matching key found.")


    def show_ocr(self):
        self.text_result.delete("1.0", tk.END)
        if not self.extracted_text:
            self.text_result.insert(tk.END, "No OCR data found.")
            return
        for text, conf in self.extracted_text:
            self.text_result.insert(tk.END, f"📄 {text}  ➔  Confidence: {conf}\n")

    def show_table(self):
        self.text_result.delete("1.0", tk.END)
        if not self.table_rows:
            self.text_result.insert(tk.END, "❌ No table rows detected.")
            return
        for row in self.table_rows:
            line = " | ".join([f"{k}: {v}" for k, v in row.items()])
            self.text_result.insert(tk.END, f"📊 {line}\n\n")

    def show_exact_table(self):
        self.text_result.delete("1.0", tk.END)
        if not self.table_rows:
            self.text_result.insert(tk.END, "❌ No table rows detected.")
            return
        headers = list(self.table_rows[0].keys())
        line = " | ".join(headers)
        self.text_result.insert(tk.END, f"📋 {line}\n")
        self.text_result.insert(tk.END, "-" * len(line) + "\n")
        for row in self.table_rows:
            row_line = " | ".join([row.get(h, "") for h in headers])
            self.text_result.insert(tk.END, f"{row_line}\n")

    def show_table_grid(self):
        if not self.table_rows:
            messagebox.showinfo("No Table", "No table data found.")
            return

        table_win = tk.Toplevel(self.root)
        table_win.title("📋 Invoice Table")
        table_win.geometry("700x400")

        columns = list(self.table_rows[0].keys())
        tree = ttk.Treeview(table_win, columns=columns, show='headings')
        tree.pack(fill="both", expand=True)

        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150, anchor="center")

        for row in self.table_rows:
            values = [row.get(col, "") for col in columns]
            tree.insert("", "end", values=values)

        scrollbar = ttk.Scrollbar(table_win, orient="vertical", command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

    def export_csv(self):
        if not self.extracted_text:
            messagebox.showwarning("No Data", "Please load an invoice first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Detected Text", "Confidence"])
            for text, conf in self.extracted_text:
                writer.writerow([text, conf])
        messagebox.showinfo("Exported", f"CSV saved to:\n{path}")

    def show_summary(self):
        self.text_result.delete("1.0", tk.END)
        numeric_data = []
        for text, _ in self.extracted_text:
            matches = re.findall(r'\d{1,3}(?:,\d{3})*(?:\.\d+)?', text.replace(',', ''))
            numeric_data.extend([float(val) for val in matches])
        if numeric_data:
            self.text_result.insert(tk.END, f"🔢 Total: {sum(numeric_data)}\n")
            self.text_result.insert(tk.END, f"📈 Max: {max(numeric_data)}\n")
            self.text_result.insert(tk.END, f"📉 Min: {min(numeric_data)}\n")
        else:
            self.text_result.insert(tk.END, "No numeric values found.")

if __name__ == "__main__":
    root = tk.Tk()
    app = InvoiceOCRApp(root)
    root.mainloop()
