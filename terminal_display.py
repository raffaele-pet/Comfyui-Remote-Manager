"""Tk SSH console with a VT screen, cursor, and scrollback."""

import tkinter as tk
from tkinter import font, ttk

import pyte


class ReplyScreen(pyte.HistoryScreen):
    def __init__(self, columns, lines, reply):
        self.reply = reply
        super().__init__(columns, lines, history=2000)

    def write_process_input(self, data):
        self.reply(data)


class SSHConsole(tk.Frame):
    def __init__(self, parent, send, resize):
        super().__init__(parent, bg="#080f1d")
        self.send = send
        self.resize_remote = resize
        self.closed = False
        self.screen = ReplyScreen(80, 24, send)
        self.stream = pyte.ByteStream(self.screen)
        self.console_font = font.Font(self, family="Consolas", size=10)
        self.text = tk.Text(self, bg="#080f1d", fg="#c9d7ea", insertbackground="#e8eef8",
                            font=self.console_font, wrap="none", relief="flat", bd=0,
                            padx=4, pady=4, undo=False, exportselection=False)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.bind("<KeyPress>", self.keypress)
        self.text.bind("<<Paste>>", self.paste)
        self.text.bind("<<Cut>>", lambda _event: "break")
        self.text.bind("<Configure>", self.resize)
        self._rendered = None

    @property
    def dimensions(self):
        return self.screen.columns, self.screen.lines

    def resize(self, event):
        columns = max(20, (event.width - 8) // max(1, self.console_font.measure("M")))
        lines = max(4, (event.height - 8) // self.console_font.metrics("linespace"))
        if (columns, lines) != self.dimensions:
            self.screen.resize(lines=lines, columns=columns)
            self.resize_remote(columns, lines)
            self.render()

    def feed(self, data):
        if isinstance(data, str):
            data = data.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
        self.stream.feed(data)
        self.render()

    def render(self):
        history = list(self.screen.history.top)
        rows = history + [self.screen.buffer[index] for index in range(self.screen.lines)]
        default = self.screen.default_char
        lines = ["".join(row.get(column, default).data for column in range(self.screen.columns)).rstrip()
                 for row in rows]
        cursor_row = len(history) + self.screen.cursor.y
        cursor_line = rows[cursor_row]
        column = sum(len(cursor_line.get(index, default).data) for index in range(self.screen.cursor.x))
        lines[cursor_row] = lines[cursor_row].ljust(column)
        while len(lines) > cursor_row + 1 and not lines[-1]:
            lines.pop()
        value = "\n".join(lines)
        follow = self.text.yview()[1] >= .999
        old_view = self.text.yview()[0]
        selection = self.text.tag_ranges("sel")
        if value != self._rendered:
            self.text.replace("1.0", "end-1c", value)
            self._rendered = value
            if selection:
                self.text.tag_add("sel", *selection)
        self.text.mark_set("insert", f"{cursor_row + 1}.{column}")
        self.text.configure(insertwidth=0 if getattr(self.screen.cursor, "hidden", False) else 2)
        if follow:
            self.text.see("insert")
        else:
            self.text.yview_moveto(old_view)
        self.screen.dirty.clear()

    def keypress(self, event):
        control = bool(event.state & 4)
        alt = bool(event.state & (8 | 0x20000))
        key = event.keysym.lower()
        if control and key == "c" and self.text.tag_ranges("sel"):
            self.text.event_generate("<<Copy>>")
            return "break"
        if self.closed:
            return "break"
        if (control and key == "v") or (event.keysym == "Insert" and event.state & 1):
            return self.paste()
        keys = {"Return": "\r", "KP_Enter": "\r", "BackSpace": "\x7f", "Tab": "\t",
                "Escape": "\x1b", "Up": "\x1b[A", "Down": "\x1b[B", "Right": "\x1b[C",
                "Left": "\x1b[D", "Home": "\x1b[H", "End": "\x1b[F", "Delete": "\x1b[3~",
                "Prior": "\x1b[5~", "Next": "\x1b[6~"}
        data = keys.get(event.keysym, event.char)
        if control and not alt and len(key) == 1 and "a" <= key <= "z":
            data = chr(ord(key) - ord("a") + 1)
        elif alt and data:
            data = "\x1b" + data
        if data:
            self.text.tag_remove("sel", "1.0", "end")
            self.text.see("insert")
            self.send(data)
        return "break"

    def paste(self, _event=None):
        if not self.closed:
            try:
                text = self.clipboard_get()
                self.text.tag_remove("sel", "1.0", "end")
                self.send(text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r"))
            except tk.TclError:
                pass
        return "break"

    def disable(self):
        self.closed = True
        self.text.configure(state="disabled")
