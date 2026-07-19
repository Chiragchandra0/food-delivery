"""
main.py
-------
Entry point. Run with:  python main.py
"""

import tkinter as tk
from tkinter import messagebox

from gui import PhoneCaptureApp


def main():
    root = tk.Tk()
    try:
        app = PhoneCaptureApp(root)
    except Exception as e:
        # If the GUI itself fails to build, at least show a message box
        # instead of a silent crash.
        messagebox.showerror("Startup Error", f"Failed to start application:\n{e}")
        return

    root.protocol("WM_DELETE_WINDOW", app._on_exit)
    root.mainloop()


if __name__ == "__main__":
    main()
