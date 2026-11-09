"""Shared dark ttk controls for the app and setup wizards."""

from tkinter import ttk


def configure_dark_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    background = "#0f1623"
    panel = "#101826"
    border = "#263244"
    text = "#e8eef8"
    muted = "#708096"
    input_color = "#0d1420"

    style.configure("Treeview", background=panel, foreground=text, fieldbackground=panel,
                    bordercolor=border, lightcolor=border, darkcolor=border, rowheight=24)
    style.map("Treeview", background=[("selected", "#243b61")],
              foreground=[("selected", text)])
    style.configure("Treeview.Heading", background="#1a2636", foreground=text,
                    bordercolor=border, lightcolor=border, darkcolor=border, relief="flat")
    style.map("Treeview.Heading", background=[("active", "#253044")])

    for orientation in ("Vertical", "Horizontal"):
        name = f"{orientation}.TScrollbar"
        style.layout(name, [(f"{orientation}.Scrollbar.trough", {
            "sticky": "nswe", "children": [(f"{orientation}.Scrollbar.thumb", {
                "sticky": "nswe", "expand": True,
            })],
        })])
        style.configure(name, background="#34445b", troughcolor=panel, bordercolor=panel,
                        lightcolor="#34445b", darkcolor="#34445b", relief="flat",
                        borderwidth=0, width=10, arrowsize=10)
        style.map(name, background=[("pressed", "#58a6ff"), ("active", "#526782")],
                  lightcolor=[("pressed", "#58a6ff"), ("active", "#526782")],
                  darkcolor=[("pressed", "#58a6ff"), ("active", "#526782")])

    style.configure("TCombobox", fieldbackground=input_color, background="#253044",
                    foreground=text, arrowcolor=text, bordercolor=border,
                    lightcolor=border, darkcolor=border, padding=(8, 5),
                    selectbackground="#243b61", selectforeground=text)
    style.map("TCombobox", fieldbackground=[("readonly", input_color), ("disabled", panel)],
              foreground=[("disabled", muted), ("readonly", text)],
              background=[("active", "#34445b"), ("readonly", "#253044")],
              arrowcolor=[("disabled", muted), ("readonly", text)],
              bordercolor=[("focus", "#2f81f7"), ("readonly", border)])
    root.option_add("*TCombobox*Listbox.background", input_color)
    root.option_add("*TCombobox*Listbox.foreground", text)
    root.option_add("*TCombobox*Listbox.selectBackground", "#243b61")
    root.option_add("*TCombobox*Listbox.selectForeground", text)
    root.option_add("*TCombobox*Listbox.font", "{Segoe UI} 9")
    root.option_add("*TCombobox*Listbox.relief", "flat")

    style.configure("Horizontal.TProgressbar", background="#2f81f7", troughcolor=input_color,
                    bordercolor=border, lightcolor="#2f81f7", darkcolor="#2f81f7",
                    thickness=8)
    return style
