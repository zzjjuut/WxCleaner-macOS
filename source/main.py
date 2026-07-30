from wx_gui import WxCleanerApp
import customtkinter as ctk

if __name__ == "__main__":
    ctk.set_appearance_mode("light")
    root = ctk.CTk()
    app = WxCleanerApp(root)
    root.mainloop()