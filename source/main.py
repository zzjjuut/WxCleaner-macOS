from wx_gui import WxCleanerApp
import customtkinter as ctk
from version import __version__

if __name__ == "__main__":
    ctk.set_appearance_mode("light")
    root = ctk.CTk()
    root.title(f"WxCleaner {__version__}")
    app = WxCleanerApp(root)
    root.mainloop()
