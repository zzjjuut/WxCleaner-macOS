from wx_gui import WxCleanerApp
import ttkbootstrap as ttk

if __name__ == "__main__":
    # themename 可选: cosmo, flatly, journal, literal, lumen, minty, pulse, sandstone, united, yeti
    # 深色主题: cyborg, darkly, solar, superhero
    root = ttk.Window(themename="cosmo") 
    app = WxCleanerApp(root)
    root.mainloop()