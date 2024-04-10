import tkinter as tk
from tkinter import simpledialog

def get_user_input(title: str, tip: str):
  root = tk.Tk()
  root.withdraw()  # 隐藏主窗口
  input_value = simpledialog.askstring(title, tip + "\t" * 20)
  root.destroy()  # 销毁主窗口
  return input_value or ""
