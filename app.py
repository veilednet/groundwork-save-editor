"""Groundwork Simulator Save Editor - GUI."""
import os, sys, re, json, time, threading, subprocess
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gwsave as S
import gwcodec as C
from gwcodec import F32

APP_NAME = "Groundwork Save Editor"
APP_VERSION = "1.0.0"

# Palette shared with the Rake Mod's in-game menu, so the two look like one family.
BG, CARD, ROW, TRACK = "#0f1115", "#15171c", "#232731", "#2e333e"
ACCENT, ACCENT_HI = "#f2a93b", "#ffbe5c"
TEXT, MUTED, FILL = "#eceef2", "#8b91a0", "#6b7180"
GOOD, ERR = "#5bd68a", "#f06a6a"
if sys.platform == "darwin":
    FONT = "SF Pro Text"
elif sys.platform.startswith("win"):
    FONT = "Segoe UI"
else:
    FONT = "DejaVu Sans"
# Labels from the game's own INCOME/EXPENDITURE ledger table in game.exe (1 has no label there).
CATEGORY_NAMES = {0: "Contract Income", 2: "Gold Sold", 3: "Sold Machines", 4: "New Machines", 5: "Machine Rental",
                  6: "Fuel Cost", 7: "Payroll", 8: "Maintenance", 9: "Tax", 10: "Bank Proceeds",
                  11: "Bank Repayments", 12: "Machine Transport"}
DIFFICULTIES = ["Easy", "Normal", "Realistic", "Creative"]
RAW_LIMIT = 1500
PAGES = {
    "Money": "Balance, ledger, loans and statistics",
    "Fleet": "Every machine on the map and the fleet you own",
    "Player & World": "Your position, the clock, difficulty and soil",
    "Gold": "Pallets, wash plants and the cleanup ledger",
    "Raw Editor": "Every value in the save, searchable and editable",
    "Save Info": "File details, slot name and backups",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def _apply_theme():
    t = ctk.ThemeManager.theme
    c = lambda v: [v, v]
    t["CTk"]["fg_color"] = c(BG)
    t["CTkToplevel"]["fg_color"] = c(BG)
    t["CTkFrame"].update(fg_color=c(CARD), top_fg_color=c(CARD), border_color=c(TRACK), corner_radius=12)
    t["CTkButton"].update(fg_color=c(ROW), hover_color=c(TRACK), text_color=c(TEXT), text_color_disabled=c(FILL),
                          corner_radius=8, border_width=0)
    t["CTkEntry"].update(fg_color=c(ROW), border_color=c(TRACK), text_color=c(TEXT), placeholder_text_color=c(FILL),
                         corner_radius=6, border_width=1)
    t["CTkCheckBox"].update(fg_color=c(ACCENT), hover_color=c(ACCENT_HI), border_color=c(FILL), checkmark_color=c(CARD),
                            text_color=c(TEXT), corner_radius=5, border_width=2)
    t["CTkOptionMenu"].update(fg_color=c(ROW), button_color=c(ROW), button_hover_color=c(TRACK), text_color=c(TEXT),
                              corner_radius=6)
    t["CTkScrollbar"].update(fg_color="transparent", button_color=c(TRACK), button_hover_color=c(FILL))
    t["CTkLabel"].update(text_color=c(TEXT))
    t["CTkScrollableFrame"].update(label_fg_color=c(CARD))
    t["DropdownMenu"].update(fg_color=c(CARD), hover_color=c(ROW), text_color=c(TEXT))
    f = t["CTkFont"]
    for platform in ("Windows", "macOS", "Linux"):
        f.setdefault(platform, {}).update(family=FONT, size=13)


_apply_theme()


# ------------------------------------------------------------------ building blocks
def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12, **kw)


def section(parent, title, note="", padx=18, pady=(16, 8)):
    """Amber caps heading with an optional muted note, like the Rake Mod's card titles."""
    row = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
    row.pack(fill="x", padx=padx, pady=pady)
    ctk.CTkLabel(row, text=title.upper(), font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT).pack(side="left")
    if note:
        ctk.CTkLabel(row, text=note, font=ctk.CTkFont(size=11), text_color=MUTED).pack(side="left", padx=(10, 0))
    return row


def hint(parent, text, **pack):
    lbl = ctk.CTkLabel(parent, text=text, justify="left", anchor="w", text_color=MUTED, font=ctk.CTkFont(size=11))
    lbl.pack(anchor="w", **({"padx": 18, "pady": (0, 12)} | pack))
    return lbl


BUTTON_KINDS = {
    "primary": dict(fg_color=ACCENT, hover_color=ACCENT_HI, text_color=CARD),
    "secondary": dict(fg_color=ROW, hover_color=TRACK, text_color=TEXT),
    "danger": dict(fg_color="#2c1d22", hover_color="#3d242b", text_color=ERR),
}


def button(parent, text, command, kind="secondary", width=None, height=32):
    font = ctk.CTkFont(size=13, weight="bold" if kind == "primary" else "normal")
    return ctk.CTkButton(parent, text=text, command=command, width=width or max(72, 8 * len(text) + 28), height=height,
                         font=font, **BUTTON_KINDS[kind])


def divider(parent, **pack):
    d = tk.Frame(parent, height=1, bg=TRACK, bd=0, highlightthickness=0)
    d.pack(fill="x", **({"padx": 18} | pack))
    return d


class EntryVar:
    """get/set on a CTkEntry, so an entry can keep its placeholder (which a textvariable disables)."""

    def __init__(self, entry): self.e = entry
    def get(self): return self.e.get()

    def set(self, v):
        self.e.delete(0, "end")
        if str(v): self.e.insert(0, str(v))


class NavRow(ctk.CTkFrame):
    """A sidebar entry. Selected = lighter row with an amber bar on the left (the Rake Mod's selected-row look)."""

    def __init__(self, parent, text, on_click):
        super().__init__(parent, fg_color="transparent", corner_radius=6, height=38, cursor="hand2")
        self.pack_propagate(False)
        self.bar = ctk.CTkFrame(self, width=3, fg_color="transparent", corner_radius=2)
        self.bar.pack(side="left", fill="y", pady=9)
        self.lbl = ctk.CTkLabel(self, text=text, anchor="w", text_color=MUTED, font=ctk.CTkFont(size=13), cursor="hand2")
        self.lbl.pack(side="left", fill="x", expand=True, padx=(12, 8))
        self.selected = False
        for w in (self, self.lbl):
            w.bind("<Button-1>", lambda _e: on_click())
            w.bind("<Enter>", lambda _e: self._paint(True))
            w.bind("<Leave>", lambda _e: self._paint(False))

    def select(self, on):
        self.selected = on
        self._paint(False)

    def _paint(self, hover):
        self.configure(fg_color=ROW if self.selected else ("#1b1e25" if hover else "transparent"))
        self.bar.configure(fg_color=ACCENT if self.selected else "transparent")
        self.lbl.configure(text_color=TEXT if self.selected or hover else MUTED)


class Pages:
    """Sidebar navigation with the same add/tab/get/set calls as CTkTabview."""

    def __init__(self, body, nav, on_change):
        self.body, self.nav, self.on_change = body, nav, on_change
        self.frames, self.rows, self.cur = {}, {}, None

    def add(self, name):
        self.frames[name] = ctk.CTkFrame(self.body, fg_color="transparent", corner_radius=0)
        self.rows[name] = NavRow(self.nav, name, lambda n=name: self.set(n, user=True))
        self.rows[name].pack(fill="x", padx=10, pady=1)
        if self.cur is None: self.set(name)

    def tab(self, name): return self.frames[name]
    def get(self): return self.cur

    def set(self, name, user=False):
        if name == self.cur: return
        if self.cur:
            self.frames[self.cur].pack_forget(); self.rows[self.cur].select(False)
        self.cur = name
        self.frames[name].pack(fill="both", expand=True)
        self.rows[name].select(True)
        self.on_change(name, user)


# ------------------------------------------------------------------ helpers
def like(old, val):
    """Convert val to the same numeric flavour as old (keeps f32 / f64 / int exactness)."""
    if isinstance(old, bool): return bool(val)
    if isinstance(old, F32): return F32(float(val))
    if isinstance(old, float): return float(val)
    if isinstance(old, int):
        return int(round(float(val)))
    return val


def parse_num(s, integer=False):
    s = str(s).replace(",", "").replace("_", "").replace(" ", "").strip()
    if s == "": raise ValueError("empty number")
    if integer:
        try: return int(s)
        except ValueError: return int(round(float(s)))
    return float(s)


def fmt(v):
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, F32): return "%.7g" % v
    if isinstance(v, float): return repr(v)
    if v is None: return "null"
    return str(v)


def nested_get(obj, path):
    for p in path: obj = obj[p]
    return obj


def nested_set(obj, path, val):
    for p in path[:-1]: obj = obj[p]
    obj[path[-1]] = like(obj[path[-1]], val) if not isinstance(val, (str, type(None))) else val


def summary(v):
    if isinstance(v, dict): return "{%d}" % len(v)
    if isinstance(v, list): return "[%d]" % len(v)
    if isinstance(v, str): return v if len(v) < 90 else v[:87] + "..."
    return fmt(v)


def typename(v):
    if isinstance(v, bool): return "bool"
    if isinstance(v, F32): return "f32"
    if isinstance(v, float): return "f64"
    if isinstance(v, int): return "int"
    if isinstance(v, str): return "string"
    if v is None: return "null"
    if isinstance(v, dict): return "object"
    if isinstance(v, list): return "array"
    return type(v).__name__


def make_tree(parent, columns, widths, height=8, selectmode="browse"):
    frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
    tv = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height, selectmode=selectmode)
    for (cid, title), w in zip(columns, widths):
        tv.heading(cid, text=title, anchor="w")
        tv.column(cid, width=w, anchor="w", stretch=(w >= 120))
    sb = ctk.CTkScrollbar(frame, command=tv.yview, width=12)
    tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, tv


def F(label, path, kind="float", scale=1.0, choices=None, integer=False):
    return dict(label=label, path=tuple(path) if not isinstance(path, tuple) else path, kind=kind, scale=scale, choices=choices)


class ObjEditor(ctk.CTkFrame):
    """A small form that edits fields of one dict (nested paths allowed)."""

    def __init__(self, parent, fields, on_apply, title="", cols=1, apply_text="Apply changes", note="", transparent=False):
        super().__init__(parent, fg_color="transparent" if transparent else CARD, corner_radius=12)
        self.fields, self.on_apply, self.obj = fields, on_apply, None
        self.vars = {}
        r = 0
        if title:
            head = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
            head.grid(row=r, column=0, columnspan=2 * cols, sticky="w", padx=18, pady=(16, 10)); r += 1
            ctk.CTkLabel(head, text=title.upper(), font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT).pack(side="left")
            if note: ctk.CTkLabel(head, text=note, font=ctk.CTkFont(size=11), text_color=MUTED).pack(side="left", padx=(10, 0))
        for i, f in enumerate(fields):
            rr, cc = r + i // cols, (i % cols) * 2
            if f["kind"] == "bool":
                v = tk.BooleanVar(); w = ctk.CTkCheckBox(self, text=f["label"], variable=v, checkbox_width=20, checkbox_height=20)
                w.grid(row=rr, column=cc, columnspan=2, sticky="w", padx=18, pady=4)
            else:
                v = tk.StringVar()
                ctk.CTkLabel(self, text=f["label"], anchor="w", text_color=MUTED).grid(row=rr, column=cc, sticky="w", padx=(18, 10), pady=4)
                if f["kind"] == "choice":
                    w = ctk.CTkOptionMenu(self, values=f["choices"], variable=v, width=170)
                else:
                    w = ctk.CTkEntry(self, textvariable=v, width=170, height=30)
                w.grid(row=rr, column=cc + 1, sticky="w", padx=(0, 18), pady=4)
            self.vars[f["path"]] = v
        r += (len(fields) + cols - 1) // cols
        self.btn = button(self, apply_text, self.apply, "primary")
        self.btn.grid(row=r, column=0, columnspan=2 * cols, sticky="w", padx=18, pady=(12, 18))

    def load(self, obj):
        self.obj = obj
        self.loaded = {}
        for f in self.fields:
            try: val = nested_get(obj, f["path"])
            except (KeyError, IndexError, TypeError): val = None
            v = self.vars[f["path"]]
            if f["kind"] == "bool": v.set(bool(val))
            elif f["kind"] == "choice": v.set(str(val))
            elif val is None: v.set("")
            elif f["kind"] == "str": v.set(str(val))
            else: v.set(fmt(val * f["scale"] if isinstance(val, (int, float)) and f["scale"] != 1.0 else val))
            self.loaded[f["path"]] = v.get()

    def apply(self):
        if self.obj is None: return
        try:
            for f in self.fields:
                try: old = nested_get(self.obj, f["path"])
                except (KeyError, IndexError, TypeError): continue
                v = self.vars[f["path"]].get()
                if v == self.loaded.get(f["path"]): continue      # untouched field: leave the original value exactly as is
                if f["kind"] == "bool": new = bool(v)
                elif f["kind"] in ("str", "choice"): new = v
                else:
                    x = parse_num(v) / f["scale"]
                    new = x
                if f["kind"] in ("bool", "str", "choice"): nested_set(self.obj, f["path"], new)
                else:
                    parent = nested_get(self.obj, f["path"][:-1]) if len(f["path"]) > 1 else self.obj
                    k = f["path"][-1]
                    if f["kind"] == "int" or (isinstance(old, int) and not isinstance(old, bool) and not isinstance(old, float)):
                        parent[k] = int(round(new))
                    else:
                        parent[k] = like(old, new)
            self.on_apply(self.obj)
            self.load(self.obj)
        except Exception as e:
            messagebox.showerror(APP_NAME, "Could not apply changes:\n%s" % e)


# ------------------------------------------------------------------ app
class App(ctk.CTk):
    def __init__(self, path=None):
        super().__init__()
        self.title("%s v%s" % (APP_NAME, APP_VERSION))
        self.geometry("1360x840")
        self.minsize(1180, 720)
        here = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        icon = next((p for p in (os.path.join(here, "icon.ico"), os.path.join(here, "media", "icon.ico")) if os.path.exists(p)), None)
        if icon:
            try: self.iconbitmap(icon)
            except tk.TclError: pass
        self.doc = None
        self.busy = False
        self.pending_slot = {}
        self.slot_no = None
        self.cli_path = path
        self._style()
        self._layout()
        self.tabs = Pages(self.body, self.nav, self._page_changed)
        for name in PAGES:
            self.tabs.add(name)
        self.build_money(); self.build_fleet(); self.build_world(); self.build_gold(); self.build_raw(); self.build_info()
        self.bind_all("<Control-s>", lambda _e: self.do_save())
        self.bind_all("<F5>", lambda _e: self.load_selected())
        self.after(200, self.refresh_slots)
        self.after(300, self._poll_game)
        self.protocol("WM_DELETE_WINDOW", self._close)

    # -------------------------------------------------------------- chrome
    def _style(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        st.layout("Treeview.Item", [("Treeitem.padding", {"sticky": "nswe", "children": [
            ("Treeitem.indicator", {"side": "left", "sticky": ""}), ("Treeitem.image", {"side": "left", "sticky": ""}),
            ("Treeitem.text", {"side": "left", "sticky": ""})]})])
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=28, borderwidth=0,
                     font=(FONT, 10), indicatorsize=10)
        st.configure("Treeview.Heading", background=CARD, foreground=MUTED, relief="flat", borderwidth=0,
                     lightcolor=CARD, darkcolor=CARD, bordercolor=TRACK, font=(FONT, 9, "bold"), padding=(6, 4, 6, 8))
        st.map("Treeview", background=[("selected", ROW)], foreground=[("selected", ACCENT)])
        st.map("Treeview.Heading", background=[("active", CARD)], foreground=[("active", TEXT)])

    def _layout(self):
        self.grid_columnconfigure(1, weight=1); self.grid_rowconfigure(0, weight=1)

        # sidebar: brand, save slot, page list, then game state / last message / key hints at the bottom
        side = card(self, width=262)
        side.grid(row=0, column=0, sticky="nsw", padx=(14, 7), pady=14)
        side.pack_propagate(False)
        brand = ctk.CTkFrame(side, fg_color="transparent", corner_radius=0); brand.pack(fill="x", padx=20, pady=(20, 0))
        ctk.CTkLabel(brand, text="SAVE EDITOR", font=ctk.CTkFont(size=16, weight="bold"), text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(brand, text="v" + APP_VERSION, font=ctk.CTkFont(size=11), text_color=MUTED).pack(side="right")
        ctk.CTkLabel(side, text="Groundwork Simulator", font=ctk.CTkFont(size=11), text_color=MUTED).pack(anchor="w", padx=20)

        ctk.CTkLabel(side, text="SAVE SLOT", font=ctk.CTkFont(size=10, weight="bold"), text_color=MUTED).pack(anchor="w", padx=20, pady=(22, 4))
        self.slot_var = tk.StringVar(value="(no saves found)")
        self.slot_menu = ctk.CTkOptionMenu(side, values=["(none)"], variable=self.slot_var, width=222, height=32,
                                           dynamic_resizing=False, command=lambda _: self.load_selected())
        self.slot_menu.pack(padx=20, anchor="w")
        button(side, "Reload from disk", self.load_selected, width=222).pack(padx=20, pady=(8, 0), anchor="w")
        divider(side, padx=20, pady=(20, 12))
        self.nav = ctk.CTkFrame(side, fg_color="transparent", corner_radius=0)
        self.nav.pack(fill="x")

        foot = ctk.CTkFrame(side, fg_color="transparent", corner_radius=0); foot.pack(side="bottom", fill="x", padx=20, pady=(8, 16))
        ctk.CTkLabel(foot, text="Ctrl+S  save      F5  reload", font=ctk.CTkFont(size=11), text_color=MUTED).pack(side="left")
        ctk.CTkLabel(foot, text="veilednet", font=ctk.CTkFont(size=11), text_color=FILL).pack(side="right")
        divider(side, side="bottom", padx=20, pady=(0, 0))
        self.status = ctk.CTkLabel(side, text="", anchor="w", justify="left", wraplength=222, text_color=MUTED, font=ctk.CTkFont(size=11))
        self.status.pack(side="bottom", fill="x", padx=20, pady=(4, 10))
        game = ctk.CTkFrame(side, fg_color=ROW, corner_radius=8); game.pack(side="bottom", fill="x", padx=14, pady=(0, 4))
        self.game_dot = ctk.CTkLabel(game, text="●", font=ctk.CTkFont(size=14), text_color=FILL, width=14)
        self.game_dot.pack(side="left", padx=(12, 8), pady=8)
        gtxt = ctk.CTkFrame(game, fg_color="transparent", corner_radius=0); gtxt.pack(side="left", fill="x", pady=8)
        self.game_lbl = ctk.CTkLabel(gtxt, text="Checking the game...", anchor="w", font=ctk.CTkFont(size=12, weight="bold"), height=18)
        self.game_lbl.pack(anchor="w")
        self.game_sub = ctk.CTkLabel(gtxt, text="", anchor="w", text_color=MUTED, font=ctk.CTkFont(size=11), height=16)
        self.game_sub.pack(anchor="w")

        # main column: page title + save button, then the page itself
        main = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=(7, 14), pady=14)
        head = ctk.CTkFrame(main, fg_color="transparent", corner_radius=0); head.pack(fill="x", pady=(4, 12))
        titles = ctk.CTkFrame(head, fg_color="transparent", corner_radius=0); titles.pack(side="left")
        self.page_title = ctk.CTkLabel(titles, text="", font=ctk.CTkFont(size=24, weight="bold"))
        self.page_title.pack(anchor="w")
        self.page_sub = ctk.CTkLabel(titles, text="", text_color=MUTED, font=ctk.CTkFont(size=12))
        self.page_sub.pack(anchor="w")
        self.save_btn = button(head, "Save changes", self.do_save, "primary", width=150, height=40)
        self.save_btn.pack(side="right")
        self.dirty_lbl = ctk.CTkLabel(head, text="", text_color=ACCENT, font=ctk.CTkFont(size=12))
        self.dirty_lbl.pack(side="right", padx=16)
        self.body = ctk.CTkFrame(main, fg_color="transparent", corner_radius=0)
        self.body.pack(fill="both", expand=True)

    def _page_changed(self, name, user):
        self.page_title.configure(text=name)
        self.page_sub.configure(text=PAGES[name])
        if user: self._tab_changed()

    def set_status(self, msg, color=MUTED):
        icon = {GOOD: "✔  ", ERR: "✖  ", ACCENT: "●  "}.get(color, "")
        self.status.configure(text=icon + msg, text_color=color)
        self.update_idletasks()

    def _update_dirty(self):
        self.dirty_lbl.configure(text="●  Unsaved changes" if self.is_dirty() else "")

    def _poll_game(self):
        running = S.game_running()
        self.game_dot.configure(text_color=ERR if running else GOOD)
        self.game_lbl.configure(text="Game is running" if running else "Game is closed")
        self.game_sub.configure(text="Close it before you save" if running else "Safe to save")
        self.after(3000, self._poll_game)

    def _close(self):
        if self.doc is not None and self.is_dirty() and not messagebox.askyesno(APP_NAME, "You have unsaved changes. Quit anyway?"):
            return
        self.destroy()

    def is_dirty(self):
        d = self.doc
        return bool(d and (d.dirty_world or d.ext_dirty or self.pending_slot or getattr(d, "meta_changed", False)))

    def mark(self, msg="Edit applied (not saved yet)."):
        self.set_status(msg + " Not saved yet.", ACCENT)
        self._update_dirty()

    # -------------------------------------------------------------- slots / load / save
    def refresh_slots(self):
        slots = S.list_slots()
        names = {}
        txt = S.read_slot_index()
        for m in re.finditer(r"(\d+): SaveSlotEntry\((.*?)\n\s*\),", txt, re.S):
            nm = re.search(r'save_name: "(.*?)"', m.group(2))
            names[int(m.group(1))] = nm.group(1) if nm else ""
        self.slot_map = {}
        if self.cli_path:
            self.slot_map["File: " + os.path.basename(self.cli_path)] = (0, self.cli_path)
        for n, p in slots:
            self.slot_map[("Slot %d  \u00b7  %s" % (n, names[n])) if names.get(n) else "Slot %d" % n] = (n, p)
        if not self.slot_map:
            self.set_status("No save slots found in %s" % S.SLOT_DIR, ERR); return
        keys = list(self.slot_map)
        self.slot_menu.configure(values=keys)
        self.slot_var.set(keys[0])
        self.load_selected()

    def run_bg(self, work, done, label="Working..."):
        if self.busy: return
        self.busy = True
        self.configure(cursor="watch")
        box = {}
        def runner():
            try: box["result"] = work(lambda s: box.__setitem__("msg", s))
            except Exception as e: box["error"] = e
            box["done"] = True
        threading.Thread(target=runner, daemon=True).start()
        def poll():
            if "msg" in box: self.set_status(box["msg"])
            if box.get("done"):
                self.busy = False; self.configure(cursor="")
                done(box.get("result"), box.get("error"))
            else: self.after(80, poll)
        self.set_status(label); poll()

    def load_selected(self):
        key = self.slot_var.get()
        if key not in getattr(self, "slot_map", {}): return
        if self.doc is not None and self.is_dirty() and not messagebox.askyesno(APP_NAME, "Discard your unsaved changes and reload from disk?"): return
        n, path = self.slot_map[key]
        def work(prog): return S.SaveDoc(path).load(prog)
        def done(doc, err):
            if err:
                messagebox.showerror(APP_NAME, "Failed to load save:\n%s" % err); self.set_status("Load failed.", ERR); return
            self.doc, self.slot_no, self.pending_slot = doc, n, {}
            self._update_dirty()
            self.set_status("Loaded %s (%.1f MB). Checksum %s." % (os.path.basename(path), len(doc.raw) / 1e6, "valid" if doc.checksum_ok else "INVALID"),
                            GOOD if doc.checksum_ok else ERR)
            self.refresh_all()
        self.run_bg(work, done, "Loading save...")

    def do_save(self):
        if not self.doc: return
        if not self.is_dirty():
            messagebox.showinfo(APP_NAME, "There are no changes to save."); return
        if S.game_running():
            messagebox.showwarning(APP_NAME, "Groundwork Simulator is still running.\n\nQuit the game completely first - otherwise its autosave will overwrite your edits (or you could corrupt the save).")
            return
        doc, slot_no, pend = self.doc, self.slot_no, dict(self.pending_slot)
        def work(prog):
            bak = doc.save(prog)
            if slot_no: S.SaveDoc.update_slot_index(slot_no, **pend)
            return bak
        def done(bak, err):
            if err:
                messagebox.showerror(APP_NAME, "Save failed:\n%s" % err); self.set_status("Save failed.", ERR); return
            self._update_dirty(); messagebox.showinfo(APP_NAME, "Saved!\n\nYour original was backed up to:\n%s\n\nStart the game and load the save to see your changes." % bak)
            self.set_status("Saved. Reloading...", GOOD)
            self.after(100, self._reload_after_save)
        self.run_bg(work, done, "Saving...")

    def _reload_after_save(self):
        self.pending_slot = {}
        self.doc.dirty_world.clear(); self.doc.ext_dirty = False; self.doc.meta_changed = False
        self.load_selected()

    # -------------------------------------------------------------- refresh
    def refresh_all(self):
        for fn in (self.refresh_money, self.refresh_fleet, self.refresh_world, self.refresh_gold, self.refresh_raw, self.refresh_info):
            try: fn()
            except Exception as e: print("refresh error", fn.__name__, e)

    def _tab_changed(self):
        if self.doc is None: return
        t = self.tabs.get()
        try:
            if t == "Raw Editor": self.refresh_raw()
            elif t == "Money": self.refresh_money()
            elif t == "Fleet": self.refresh_fleet()
            elif t == "Gold": self.refresh_gold()
            elif t == "Player & World": self.refresh_world()
        except Exception as e: print("tab refresh", e)

    # ============================================================ MONEY
    def build_money(self):
        t = self.tabs.tab("Money")
        t.grid_columnconfigure(0, weight=5, uniform="m"); t.grid_columnconfigure(1, weight=6, uniform="m"); t.grid_rowconfigure(0, weight=1)
        col = ctk.CTkScrollableFrame(t, fg_color="transparent", corner_radius=0)
        col.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        right = card(t); right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

        bal = card(col); bal.pack(fill="x")
        section(bal, "Current balance")
        big = ctk.CTkFrame(bal, fg_color="transparent", corner_radius=0); big.pack(anchor="w", padx=18)
        self.bal_lbl = ctk.CTkLabel(big, text="-", font=ctk.CTkFont(size=42, weight="bold"))
        self.bal_lbl.pack(side="left")
        ctk.CTkLabel(big, text="EUR", text_color=MUTED, font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=(10, 0), pady=(14, 0))
        self.bal_sub = ctk.CTkLabel(bal, text="", text_color=MUTED, justify="left", font=ctk.CTkFont(size=12))
        self.bal_sub.pack(anchor="w", padx=18, pady=(0, 14))
        divider(bal)
        row = ctk.CTkFrame(bal, fg_color="transparent", corner_radius=0); row.pack(fill="x", padx=18, pady=(14, 6))
        ctk.CTkLabel(row, text="Set balance to", text_color=MUTED, width=110, anchor="w").pack(side="left")
        e = ctk.CTkEntry(row, width=170, height=32, placeholder_text="e.g. 250,000"); e.pack(side="left", padx=(0, 8))
        self.newbal = EntryVar(e)
        e.bind("<Return>", lambda _e: self.money_set())
        button(row, "Set", self.money_set, "primary", width=70).pack(side="left")
        row2 = ctk.CTkFrame(bal, fg_color="transparent", corner_radius=0); row2.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(row2, text="Quick add", text_color=MUTED, width=110, anchor="w").pack(side="left")
        for amt in (10_000, 100_000, 1_000_000, 10_000_000):
            button(row2, "+" + ("%dk" % (amt // 1000) if amt < 1_000_000 else "%dM" % (amt // 1_000_000)), lambda a=amt: self.money_add(a), width=64).pack(side="left", padx=(0, 6))
        row3 = ctk.CTkFrame(bal, fg_color="transparent", corner_radius=0); row3.pack(fill="x", padx=18, pady=(6, 14))
        ctk.CTkLabel(row3, text="", width=110).pack(side="left")
        button(row3, "Max out (999,999,999)", lambda: self.money_set_to(999_999_999)).pack(side="left", padx=(0, 6))
        hint(bal, "Your balance is the opening balance plus every ledger entry. The editor changes\n"
                  "the opening balance so the total comes out exactly right.")

        loans = card(col); loans.pack(fill="x", pady=(14, 0))
        section(loans, "Loans")
        lrow = ctk.CTkFrame(loans, fg_color="transparent", corner_radius=0); lrow.pack(fill="x", padx=18, pady=(0, 16))
        self.loan_lbl = ctk.CTkLabel(lrow, text="-", font=ctk.CTkFont(size=13, weight="bold")); self.loan_lbl.pack(side="left")
        button(lrow, "Clear all loans", self.clear_loans, "danger").pack(side="right")

        self.fund_editor = ObjEditor(col, [
            F("Fuel used (litres)", ("fuel", "litres")), F("Fuel cost paid (EUR)", ("fuel", "cost_eur"), "int"),
            F("Gold sold (grams)", ("gold", "grams")), F("Gold revenue (EUR)", ("gold", "revenue_eur"), "int"),
            F("Real seconds elapsed", ("clock", "elapsed_real_seconds")), F("Wake hour", ("clock", "wake_hour"), "int"),
            F("Clock speed index", ("clock", "speed_index"), "int"),
        ], self.funds_applied, title="Statistics & clock", note="these don't change the balance")
        self.fund_editor.pack(fill="x", pady=(14, 0))

        section(right, "Ledger", "every income and expense")
        fr, self.ledger = make_tree(right, [("i", "#"), ("day", "Day"), ("cat", "Category"), ("amt", "Amount (EUR)")], [60, 60, 190, 130], height=16)
        fr.pack(fill="both", expand=True, padx=(12, 8), pady=(0, 6))
        self.ledger.bind("<<TreeviewSelect>>", self.ledger_pick)
        self.ledger.column("amt", anchor="e"); self.ledger.heading("amt", anchor="e")
        divider(right)
        ed = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0); ed.pack(fill="x", padx=18, pady=(12, 8))
        self.l_day, self.l_cat, self.l_amt = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for lab, var, w in (("Day", self.l_day, 56), ("Category", self.l_cat, 56), ("Amount", self.l_amt, 110)):
            ctk.CTkLabel(ed, text=lab, text_color=MUTED).pack(side="left", padx=(0, 6))
            ctk.CTkEntry(ed, textvariable=var, width=w, height=32).pack(side="left", padx=(0, 12))
        button(ed, "Delete", self.ledger_delete, "danger").pack(side="right")
        button(ed, "Add", self.ledger_add).pack(side="right", padx=6)
        button(ed, "Update", self.ledger_update, "primary").pack(side="right")
        hint(right, "Categories: 0 contract income, 2 gold sold, 3 sold machines, 4 new machines, 5 machine rental,\n"
                    "6 fuel, 7 payroll, 8 maintenance, 9 tax, 10 bank proceeds, 11 bank repayments, 12 machine transport.",
             pady=(0, 16))

    def refresh_money(self):
        d = self.doc
        if not d or not d.campaign:
            self.bal_lbl.configure(text="n/a"); self.bal_sub.configure(text="No campaign funds data in this save."); return
        f = d.campaign["funds"]
        bal = d.balance()
        self.bal_lbl.configure(text="{:,}".format(bal))
        net = sum(p["amount_eur"] for p in f["ledger_postings"])
        self.bal_sub.configure(text="Opening {:,}   \u00b7   ledger net {:,}   \u00b7   {:,} entries".format(f["opening_balance_eur"], net, len(f["ledger_postings"])))
        self.fund_editor.load(f)
        n = len(f.get("loans", [])); self.loan_lbl.configure(text="No open loans" if not n else "%d open loan%s" % (n, "s" * (n > 1)))
        self.ledger.delete(*self.ledger.get_children())
        for i, p in enumerate(f["ledger_postings"]):
            self.ledger.insert("", "end", iid=str(i), values=(i, p["day_number"], "%s  (%s)" % (p["category"], CATEGORY_NAMES.get(p["category"], "?")), "{:,}".format(p["amount_eur"])))
        if f["ledger_postings"]: self.ledger.see(str(len(f["ledger_postings"]) - 1))

    def money_set_to(self, target):
        if not self.doc or not self.doc.campaign: return
        self.doc.set_balance(target); self.refresh_money(); self.mark("Balance set to {:,}.".format(int(target)))

    def money_set(self):
        try: self.money_set_to(parse_num(self.newbal.get(), True))
        except Exception as e: messagebox.showerror(APP_NAME, "Enter a whole number, e.g. 250000.\n(%s)" % e)

    def money_add(self, amt):
        if self.doc and self.doc.campaign: self.money_set_to(self.doc.balance() + amt)

    def funds_applied(self, f):
        self.doc.touch_ext(); self.refresh_money(); self.mark("Statistics updated.")

    def clear_loans(self):
        if not self.doc or not self.doc.campaign: return
        self.doc.campaign["funds"]["loans"] = []; self.doc.touch_ext(); self.refresh_money(); self.mark("Loans cleared.")

    def ledger_pick(self, _=None):
        sel = self.ledger.selection()
        if not sel: return
        p = self.doc.campaign["funds"]["ledger_postings"][int(sel[0])]
        self.l_day.set(p["day_number"]); self.l_cat.set(p["category"]); self.l_amt.set(p["amount_eur"])

    def _ledger_vals(self):
        return dict(day_number=parse_num(self.l_day.get(), True), category=parse_num(self.l_cat.get(), True), amount_eur=parse_num(self.l_amt.get(), True))

    def ledger_update(self):
        sel = self.ledger.selection()
        if not sel: return
        try: self.doc.campaign["funds"]["ledger_postings"][int(sel[0])].update(self._ledger_vals())
        except Exception as e: messagebox.showerror(APP_NAME, str(e)); return
        self.doc.touch_ext(); self.refresh_money(); self.mark("Ledger entry updated (balance changed).")

    def ledger_add(self):
        try: v = self._ledger_vals()
        except Exception as e: messagebox.showerror(APP_NAME, str(e)); return
        self.doc.campaign["funds"]["ledger_postings"].append(v); self.doc.touch_ext(); self.refresh_money(); self.mark("Ledger entry added.")

    def ledger_delete(self):
        sel = self.ledger.selection()
        if not sel: return
        del self.doc.campaign["funds"]["ledger_postings"][int(sel[0])]; self.doc.touch_ext(); self.refresh_money(); self.mark("Ledger entry deleted.")

    # ============================================================ FLEET
    MACH_FIELDS = [
        F("Fuel (%)", ("fuel_fraction",), "float", 100.0), F("Payload (m3)", ("payload_m3",)),
        F("Position X", ("translation", 0)), F("Position Y (height)", ("translation", 1)), F("Position Z", ("translation", 2)),
        F("Heading (rad)", ("heading",)), F("Light mode", ("vehicle_light_mode",), "int"),
        F("Retired", ("retired",), "bool"), F("Hired", ("hired",), "bool"), F("Parking brake", ("parking_brake",), "bool"),
        F("Off-road flag", ("off_road",), "bool"), F("Attachment attached", ("attachment_attached",), "bool"),
        F("Tree thumb fitted", ("tree_thumb_fitted",), "bool"), F("Grading bucket", ("grading_bucket",), "bool"),
        F("Stone bucket", ("stone_bucket",), "bool"), F("Hydraulic hammer", ("hydraulic_hammer",), "bool"),
        F("Paving enabled", ("paving_enabled",), "bool"), F("Roller compaction", ("roller_compaction_enabled",), "bool"),
    ]

    def build_fleet(self):
        t = self.tabs.tab("Fleet")
        t.grid_columnconfigure(0, weight=3); t.grid_columnconfigure(1, weight=0, minsize=380); t.grid_rowconfigure(0, weight=1)
        left = card(t); left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        top = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0); top.pack(fill="x", padx=18, pady=(14, 8))
        ctk.CTkLabel(top, text="MACHINES IN THE WORLD", font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT).pack(side="left")
        button(top, "Refill trailers", self.refill_trailers).pack(side="right")
        button(top, "Refuel all machines", self.refuel_all, "primary").pack(side="right", padx=8)
        fr, self.mach = make_tree(left, [("i", "#"), ("id", "Machine"), ("fuel", "Fuel"), ("ret", "Retired"), ("hired", "Hired"), ("pos", "Position")], [40, 160, 70, 70, 60, 230], height=10)
        fr.pack(fill="both", expand=True, padx=(12, 8), pady=(0, 10))
        self.mach.bind("<<TreeviewSelect>>", self.mach_pick)
        divider(left)
        top2 = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0); top2.pack(fill="x", padx=18, pady=(14, 8))
        ctk.CTkLabel(top2, text="OWNED FLEET", font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(top2, text="experimental, ownership flags only", font=ctk.CTkFont(size=11), text_color=MUTED).pack(side="left", padx=10)
        button(top2, "Own all", lambda: self.fleet_set_all(True)).pack(side="right")
        button(top2, "Toggle owned", self.fleet_toggle_owned).pack(side="right", padx=8)
        fr2, self.fleet = make_tree(left, [("i", "#"), ("label", "Label"), ("proto", "Type"), ("owned", "Owned"), ("active", "Active"), ("map", "Map machine")], [40, 200, 150, 70, 70, 100], height=7)
        fr2.pack(fill="both", expand=True, padx=(12, 8), pady=(0, 14))
        right = ctk.CTkScrollableFrame(t, fg_color=CARD, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self.mach_editor = ObjEditor(right, self.MACH_FIELDS, self.mach_applied, title="Selected machine",
                                     note="pick one on the left", transparent=True)
        self.mach_editor.pack(fill="x")

    def refresh_fleet(self):
        d = self.doc; self.mach.delete(*self.mach.get_children()); self.fleet.delete(*self.fleet.get_children())
        for i, m in enumerate(d.get("machines")):
            tr = m.get("translation", [0, 0, 0])
            self.mach.insert("", "end", iid=str(i), values=(i, m.get("id"), "%d%%" % round(m.get("fuel_fraction", 0) * 100), "yes" if m.get("retired") else "", "yes" if m.get("hired") else "", "%.1f, %.1f, %.1f" % tuple(tr)))
        for i, r in enumerate(d.get("authored_fleet").get("records", [])):
            self.fleet.insert("", "end", iid=str(i), values=(i, r.get("label"), r.get("prototypeId"), "yes" if r.get("owned") else "", "yes" if r.get("active") else "", "yes" if r.get("mapMachine") else ""))

    def mach_pick(self, _=None):
        sel = self.mach.selection()
        if sel: self.mach_editor.load(self.doc.get("machines")[int(sel[0])])

    def mach_applied(self, m):
        self.doc.touch("machines"); sel = self.mach.selection(); self.refresh_fleet()
        if sel: self.mach.selection_set(sel[0])
        self.mark("Machine updated.")

    def refuel_all(self):
        ms = self.doc.get("machines")
        for m in ms: m["fuel_fraction"] = like(m["fuel_fraction"], 1.0)
        self.doc.touch("machines")
        try:
            for tr in self.doc.get("low_loaders").get("trailers", []):
                if "fuel_litres" in tr: tr["fuel_litres"] = like(tr["fuel_litres"], max(tr["fuel_litres"], 500.0))
            self.doc.touch("low_loaders")
        except Exception: pass
        self.refresh_fleet(); self.mark("All machines refuelled.")

    def refill_trailers(self):
        ll = self.doc.get("low_loaders")
        for tr in ll.get("trailers", []):
            if "fuel_litres" in tr: tr["fuel_litres"] = like(tr["fuel_litres"], 500.0)
        self.doc.touch("low_loaders"); self.mark("Trailer fuel set to 500 L.")

    def fleet_toggle_owned(self):
        sel = self.fleet.selection()
        if not sel: return
        r = self.doc.get("authored_fleet")["records"][int(sel[0])]; r["owned"] = not r["owned"]
        self.doc.touch("authored_fleet"); self.refresh_fleet(); self.mark("Ownership toggled.")

    def fleet_set_all(self, val):
        for r in self.doc.get("authored_fleet")["records"]: r["owned"] = val
        self.doc.touch("authored_fleet"); self.refresh_fleet(); self.mark("All fleet records marked owned.")

    # ============================================================ PLAYER & WORLD
    def build_world(self):
        t = self.tabs.tab("Player & World")
        sc = ctk.CTkScrollableFrame(t, fg_color="transparent", corner_radius=0); sc.pack(fill="both", expand=True)
        sc.grid_columnconfigure((0, 1), weight=1, uniform="w")
        self.player_editor = ObjEditor(sc, [
            F("Position X", ("translation", 0)), F("Position Y (height)", ("translation", 1)), F("Position Z", ("translation", 2)),
            F("Heading (rad)", ("heading",)), F("Camera yaw", ("camera_yaw",)), F("Camera pitch", ("camera_pitch",)),
            F("Flashlight on", ("flashlight_enabled",), "bool"), F("First person view", ("first_person",), "bool"),
        ], self.player_applied, title="Player")
        self.player_editor.grid(row=0, column=0, sticky="nsew", padx=(0, 7), pady=(0, 14))
        right = ctk.CTkFrame(sc, fg_color="transparent", corner_radius=0); right.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(7, 0))
        self.time_editor = ObjEditor(right, [
            F("Simulation tick", ("tick",), "int"), F("Simulation seconds", ("elapsed_simulation_seconds",)),
            F("Paused", ("paused",), "bool"),
        ], self.time_applied, title="Simulation clock")
        self.time_editor.pack(fill="x")
        self.diff_frame = card(right); self.diff_frame.pack(fill="x", pady=(14, 0))
        section(self.diff_frame, "Difficulty")
        drow = ctk.CTkFrame(self.diff_frame, fg_color="transparent", corner_radius=0); drow.pack(fill="x", padx=18, pady=(0, 12))
        self.diff_var = tk.StringVar()
        ctk.CTkOptionMenu(drow, values=DIFFICULTIES, variable=self.diff_var, width=170, height=32).pack(side="left")
        button(drow, "Apply difficulty", self.diff_apply, "primary").pack(side="left", padx=10)
        divider(self.diff_frame)
        self.world_info = ctk.CTkLabel(self.diff_frame, text="", justify="left", anchor="w", text_color=MUTED, font=ctk.CTkFont(size=12))
        self.world_info.pack(anchor="w", padx=18, pady=(12, 16))
        self.soil_editor = ObjEditor(sc, [
            F("Friction angle (deg)", ("friction_angle_degrees",)), F("Cohesion (kPa)", ("cohesion_kpa",)), F("Adhesion (kPa)", ("adhesion_kpa",)),
            F("Unit weight (kN/m3)", ("unit_weight_kn_m3",)), F("Moisture (0-1)", ("moisture",)), F("Repose angle (deg)", ("repose_angle_degrees",)),
            F("Parcel budget", ("parcel_budget",), "int"), F("Quality", ("quality",), "str"), F("Soil sim paused", ("paused",), "bool"),
        ], self.soil_applied, title="Soil physics")
        self.soil_editor.grid(row=1, column=0, sticky="nsew", padx=(0, 7))

    def _players(self):
        d = self.doc; res = [d.get("player")]
        for op in d.get("operators").values():
            if isinstance(op, dict) and "player" in op: res.append(op["player"])
        return res

    def refresh_world(self):
        d = self.doc
        self.player_editor.load(d.get("player"))
        top = {"tick": d.get("tick"), "elapsed_simulation_seconds": d.get("elapsed_simulation_seconds"), "paused": d.get("paused")}
        self.time_editor.load(top); self._top = top
        self.soil_editor.load(d.get("soil_settings"))
        self.diff_var.set(d.get("session_difficulty").get("level", "Easy"))
        secs = d.get("elapsed_simulation_seconds")
        self.world_info.configure(text="Site  %s      Geology  %s\nSeed  %s\nSimulated play time  %.1f h" % (d.get("site"), d.get("geology"), d.get("seed"), secs / 3600.0))

    def player_applied(self, p):
        for q in self._players()[1:]:
            for k in ("translation", "heading", "camera_yaw", "camera_pitch", "flashlight_enabled", "first_person"):
                if k in p and k in q: q[k] = list(p[k]) if isinstance(p[k], list) else p[k]
        self.doc.touch("player"); self.doc.touch("operators"); self.mark("Player updated.")

    def time_applied(self, top):
        d = self.doc
        for k in ("tick", "elapsed_simulation_seconds", "paused"):
            if d.get(k) != top[k]: self._set_top(k, top[k])
        self.mark("Clock updated.")

    def _set_top(self, key, val):
        # scalar top-level world values are stored as tiny sections of their own
        d = self.doc
        d.cache[key] = val; d.readonly.pop(key, None); d.dirty_world.add(key)

    def soil_applied(self, s):
        self.doc.touch("soil_settings"); self.mark("Soil settings updated.")

    def diff_apply(self):
        sd = self.doc.get("session_difficulty"); sd["level"] = self.diff_var.get()
        self.doc.touch("session_difficulty"); self.pending_slot["difficulty"] = self.diff_var.get()
        self.mark("Difficulty set to %s." % self.diff_var.get())

    # ============================================================ GOLD
    def build_gold(self):
        t = self.tabs.tab("Gold")
        t.grid_columnconfigure(0, weight=3); t.grid_columnconfigure(1, weight=0, minsize=400); t.grid_rowconfigure(0, weight=1)
        left = card(t); left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        top = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0); top.pack(fill="x", padx=18, pady=(14, 8))
        ctk.CTkLabel(top, text="CONCENTRATE PALLETS", font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT).pack(side="left")
        self.gold_mult = tk.StringVar(value="2")
        button(top, "Multiply", self.gold_multiply, "primary").pack(side="right")
        ctk.CTkEntry(top, textvariable=self.gold_mult, width=56, height=32).pack(side="right", padx=8)
        ctk.CTkLabel(top, text="Multiply all pallet gold by", text_color=MUTED).pack(side="right")
        fr, self.pallets = make_tree(left, [("i", "#"), ("id", "Pallet id"), ("g", "Gold (g)"), ("w", "Washed"), ("pos", "Position")], [40, 120, 90, 80, 220], height=6)
        fr.pack(fill="both", expand=True, padx=(12, 8), pady=(0, 10))
        self.pallets.bind("<<TreeviewSelect>>", self.pallet_pick)
        divider(left)
        section(left, "Wash plants", "mobile trommels", pady=(14, 8))
        fr2, self.trom = make_tree(left, [("i", "#"), ("g", "Recovered gold (g)"), ("w", "Washed m3"), ("s", "Stacked m3"), ("pos", "Position")], [40, 140, 100, 100, 200], height=4)
        fr2.pack(fill="both", expand=True, padx=(12, 8), pady=(0, 10))
        self.trom.bind("<<TreeviewSelect>>", self.trom_pick)
        divider(left)
        section(left, "Cleanup ledger", "estimated claim value", pady=(14, 8))
        fr3, self.gledger = make_tree(left, [("i", "#"), ("claim", "Claim"), ("g", "Gold (g)"), ("v", "Value EUR"), ("tick", "Tick")], [40, 160, 100, 110, 100], height=3)
        fr3.pack(fill="both", expand=True, padx=(12, 8), pady=(0, 14))
        self.gledger.bind("<<TreeviewSelect>>", self.gledger_pick)
        right = ctk.CTkScrollableFrame(t, fg_color=CARD, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self.pallet_editor = ObjEditor(right, [
            F("Gold (grams)", ("concentrate", "gold_grams")), F("Washed bank volume m3", ("concentrate", "washed_bank_volume_m3")),
            F("Pay bank volume m3", ("concentrate", "pay_bank_volume_m3")), F("Pay grade volume", ("concentrate", "pay_grade_volume")),
            F("Washed fraction", ("washed_fraction",)),
        ], lambda o: self._gold_applied(), title="Selected pallet", transparent=True)
        self.pallet_editor.pack(fill="x")
        divider(right)
        self.trom_editor = ObjEditor(right, [
            F("Recovered gold (g)", ("recovered_gold_grams",)), F("Washed bank volume m3", ("washed_bank_volume_m3",)),
            F("Stacked bank volume m3", ("stacked_bank_volume_m3",)), F("Water used m3", ("water_used_m3",)),
            F("Hopper bank volume m3", ("hopper_bank_volume_m3",)), F("Master switch on", ("master_switch_on",), "bool"),
        ], lambda o: self._gold_applied("mobile_trommels"), title="Selected wash plant", transparent=True)
        self.trom_editor.pack(fill="x")
        divider(right)
        self.gl_editor = ObjEditor(right, [
            F("Gold (g)", ("gold_grams",)), F("Washed volume m3", ("washed_bank_volume_m3",)), F("Mean pay grade", ("mean_pay_grade",)),
            F("Estimated value EUR", ("estimated_value_eur",)),
        ], lambda o: self._gold_applied(), title="Selected ledger entry", transparent=True)
        self.gl_editor.pack(fill="x")

    def refresh_gold(self):
        d = self.doc
        gc = d.get("gold_cleanup")
        self.pallets.delete(*self.pallets.get_children()); self.trom.delete(*self.trom.get_children()); self.gledger.delete(*self.gledger.get_children())
        for i, p in enumerate(gc.get("pallets", [])):
            self.pallets.insert("", "end", iid=str(i), values=(i, p.get("stable_id"), fmt(p["concentrate"]["gold_grams"]), "%d%%" % round(p.get("washed_fraction", 0) * 100), "%.1f, %.1f, %.1f" % tuple(p["position"])))
        for i, m in enumerate(d.get("mobile_trommels").get("trommels", [])):
            self.trom.insert("", "end", iid=str(i), values=(i, fmt(m.get("recovered_gold_grams")), fmt(m.get("washed_bank_volume_m3")), fmt(m.get("stacked_bank_volume_m3")), "%.0f, %.0f, %.0f" % tuple(m["translation"])))
        for i, e in enumerate(gc.get("ledger", [])):
            self.gledger.insert("", "end", iid=str(i), values=(i, e.get("claim"), fmt(e.get("gold_grams")), fmt(e.get("estimated_value_eur")), e.get("recorded_tick")))

    def pallet_pick(self, _=None):
        sel = self.pallets.selection()
        if sel: self.pallet_editor.load(self.doc.get("gold_cleanup")["pallets"][int(sel[0])])

    def trom_pick(self, _=None):
        sel = self.trom.selection()
        if sel: self.trom_editor.load(self.doc.get("mobile_trommels")["trommels"][int(sel[0])])

    def gledger_pick(self, _=None):
        sel = self.gledger.selection()
        if sel: self.gl_editor.load(self.doc.get("gold_cleanup")["ledger"][int(sel[0])])

    def _gold_applied(self, section="gold_cleanup"):
        self.doc.touch(section); self.refresh_gold(); self.mark("Gold values updated.")

    def gold_multiply(self):
        try: k = parse_num(self.gold_mult.get())
        except Exception as e: messagebox.showerror(APP_NAME, str(e)); return
        for p in self.doc.get("gold_cleanup")["pallets"]:
            c = p["concentrate"]; c["gold_grams"] = like(c["gold_grams"], c["gold_grams"] * k)
        self._gold_applied(); self.mark("All pallet gold multiplied by %g." % k)

    # ============================================================ RAW EDITOR
    def build_raw(self):
        t = self.tabs.tab("Raw Editor")
        t.grid_columnconfigure(0, weight=3); t.grid_columnconfigure(1, weight=0, minsize=430); t.grid_rowconfigure(0, weight=1)
        left = card(t); left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        top = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0); top.pack(fill="x", padx=18, pady=(16, 10))
        e = ctk.CTkEntry(top, placeholder_text="Search keys or values, e.g. fuel, gold, 59054", height=34)
        self.search_var = EntryVar(e)
        e.pack(side="left", fill="x", expand=True, padx=(0, 8)); e.bind("<Return>", lambda _: self.raw_search())
        button(top, "Search", self.raw_search, "primary", height=34).pack(side="left")
        frame = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0); frame.pack(fill="both", expand=True, padx=(12, 8), pady=(0, 14))
        self.raw = ttk.Treeview(frame, columns=("val", "type"), selectmode="browse")
        self.raw.heading("#0", text="Key", anchor="w"); self.raw.heading("val", text="Value", anchor="w"); self.raw.heading("type", text="Type", anchor="w")
        self.raw.column("#0", width=280); self.raw.column("val", width=300); self.raw.column("type", width=70, stretch=False)
        sb = ctk.CTkScrollbar(frame, command=self.raw.yview, width=12); self.raw.configure(yscrollcommand=sb.set)
        self.raw.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.raw.bind("<<TreeviewOpen>>", lambda _: self.raw_open(self.raw.focus()))
        self.raw.bind("<<TreeviewSelect>>", self.raw_pick)
        self.raw_info = {}
        right = card(t); right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        section(right, "Edit value")
        self.raw_path = ctk.CTkLabel(right, text="Select an item on the left.", wraplength=390, justify="left", anchor="w", text_color=MUTED)
        self.raw_path.pack(fill="x", padx=18)
        self.raw_val = tk.StringVar()
        self.raw_entry = ctk.CTkEntry(right, textvariable=self.raw_val, height=34); self.raw_entry.pack(fill="x", padx=18, pady=10)
        self.raw_entry.bind("<Return>", lambda _e: self.raw_apply())
        b = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0); b.pack(fill="x", padx=18)
        button(b, "Apply value", self.raw_apply, "primary").pack(side="left")
        button(b, "Delete item", self.raw_delete, "danger").pack(side="right")
        hint(right, "true/false, null, a whole number, a decimal number or text.\nThe original number type (int, f32, f64) is kept automatically.", pady=(10, 14))
        divider(right)
        section(right, "Add to selected object or array")
        k = ctk.CTkEntry(right, placeholder_text="new key (objects only)", height=32); k.pack(fill="x", padx=18, pady=(0, 6))
        v = ctk.CTkEntry(right, placeholder_text='value as JSON, e.g. 5, "text", {"a": 1}', height=32); v.pack(fill="x", padx=18)
        self.raw_newkey, self.raw_newval = EntryVar(k), EntryVar(v)
        button(right, "Add", self.raw_add).pack(anchor="w", padx=18, pady=(8, 14))
        divider(right)
        section(right, "Search results", "double-click to jump")
        fr, self.results = make_tree(right, [("p", "Path"), ("v", "Value")], [250, 140], height=8)
        fr.pack(fill="both", expand=True, padx=(12, 8), pady=(0, 14))
        self.results.bind("<Double-1>", self.raw_goto)
        self.search_hits = {}

    def refresh_raw(self):
        d = self.doc
        self.raw.delete(*self.raw.get_children()); self.raw_info = {}; self.raw_top = {}
        if d.campaign is not None:
            iid = self.raw.insert("", "end", text="[campaign] funds & company data", values=("{%d}" % len(d.campaign), "object"))
            self.raw_info[iid] = dict(section=None, obj=d.campaign, parent=None, key=None, path=(), populated=False)
            self.raw.insert(iid, "end", text="...")
            self.raw_top[None] = iid
        for k in d.order:
            sz = d.section_size(k)
            if d.section_editable(k):
                iid = self.raw.insert("", "end", text=k, values=("%.1f KB" % (sz / 1024.0), "section"))
                self.raw_info[iid] = dict(section=k, obj=None, parent=None, key=None, path=(), populated=False)
                self.raw.insert(iid, "end", text="...")
                self.raw_top[k] = iid
            else:
                self.raw.insert("", "end", text=k + "   (binary data, read-only)", values=("%.1f MB" % (sz / 1e6), "large"))

    def raw_open(self, iid):
        info = self.raw_info.get(iid)
        if not info or info["populated"]: return
        if info["obj"] is None:
            try: info["obj"] = self.doc.get(info["section"])
            except Exception as e: messagebox.showerror(APP_NAME, str(e)); return
        obj = info["obj"]
        self.raw.delete(*self.raw.get_children(iid))
        items = list(obj.items()) if isinstance(obj, dict) else list(enumerate(obj)) if isinstance(obj, list) else []
        for n, (k, v) in enumerate(items):
            if n >= RAW_LIMIT:
                self.raw.insert(iid, "end", text="... %d more items not shown" % (len(items) - RAW_LIMIT)); break
            c = self.raw.insert(iid, "end", text=str(k), values=(summary(v), typename(v)))
            self.raw_info[c] = dict(section=info["section"], obj=v, parent=obj, key=k, path=info["path"] + (k,), populated=False)
            if isinstance(v, (dict, list)) and len(v) > 0: self.raw.insert(c, "end", text="...")
        info["populated"] = True

    def raw_pick(self, _=None):
        sel = self.raw.selection()
        if not sel: return
        info = self.raw_info.get(sel[0])
        if not info: return
        sec = info["section"] or "campaign"
        if info["parent"] is None:
            self.raw_path.configure(text="%s  (top-level section)" % sec); self.raw_val.set(""); return
        v = info["parent"][info["key"]]
        self.raw_path.configure(text="%s / %s\ntype: %s" % (sec, " / ".join(str(p) for p in info["path"]), typename(v)))
        self.raw_val.set("" if isinstance(v, (dict, list)) else ("null" if v is None else ("true" if v is True else "false" if v is False else str(v))))

    def _touch_info(self, info):
        if info["section"] is None: self.doc.touch_ext()
        else: self.doc.touch(info["section"])

    def raw_apply(self):
        sel = self.raw.selection()
        if not sel: return
        info = self.raw_info.get(sel[0])
        if not info or info["parent"] is None: return
        old = info["parent"][info["key"]]
        if isinstance(old, (dict, list)):
            messagebox.showinfo(APP_NAME, "Pick a single value inside this item to edit it."); return
        text = self.raw_val.get(); s = text.strip()
        is_int = re.fullmatch(r"-?\d+", s) is not None
        is_num = is_int or re.fullmatch(r"-?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?", s) is not None
        try:
            if s == "null": new = None
            elif s in ("true", "false"): new = (s == "true")
            elif isinstance(old, str) or not is_num: new = text
            elif isinstance(old, F32): new = F32(float(s))
            elif isinstance(old, float): new = float(s)
            elif is_int: new = int(s)
            else: new = float(s)
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e)); return
        info["parent"][info["key"]] = new
        self._touch_info(info)
        self.raw.item(sel[0], values=(summary(new), typename(new)))
        self.raw_pick(); self.mark("Value changed.")

    def raw_delete(self):
        sel = self.raw.selection()
        if not sel: return
        info = self.raw_info.get(sel[0])
        if not info or info["parent"] is None: return
        if not messagebox.askyesno(APP_NAME, "Delete this item from the save data?\nThis can break the save if the game expects it."): return
        p = info["parent"]
        if isinstance(p, list): del p[info["key"]]
        else: del p[info["key"]]
        self._touch_info(info)
        parent_iid = self.raw.parent(sel[0])
        pinfo = self.raw_info[parent_iid]; pinfo["populated"] = False; self.raw_open(parent_iid)
        self.mark("Item deleted.")

    def raw_add(self):
        sel = self.raw.selection()
        if not sel: return
        info = self.raw_info.get(sel[0])
        if not info or not isinstance(info["obj"], (dict, list)): messagebox.showinfo(APP_NAME, "Select an object or array first."); return
        try:
            val = json.loads(self.raw_newval.get())
            val = self._json_to_codec(val)
        except Exception as e:
            messagebox.showerror(APP_NAME, "Value must be valid JSON.\n%s" % e); return
        if isinstance(info["obj"], dict):
            k = self.raw_newkey.get().strip()
            if not k: messagebox.showinfo(APP_NAME, "Enter a key."); return
            info["obj"][k] = val
        else: info["obj"].append(val)
        self._touch_info(info); info["populated"] = False; self.raw_open(sel[0]); self.raw.item(sel[0], open=True); self.mark("Item added.")

    @staticmethod
    def _json_to_codec(v):
        if isinstance(v, float): return F32(v) if False else v
        return v

    def raw_search(self):
        q = self.search_var.get().strip().lower()
        if not q or not self.doc: return
        self.results.delete(*self.results.get_children()); self.search_hits = {}
        hits = []
        def walk(sec, obj, path):
            if len(hits) >= 400: return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if q in str(k).lower(): hits.append((sec, path + (k,), v))
                    if isinstance(v, (dict, list)): walk(sec, v, path + (k,))
                    elif q in str(v).lower() and q not in str(k).lower(): hits.append((sec, path + (k,), v))
                    if len(hits) >= 400: return
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    if isinstance(v, (dict, list)): walk(sec, v, path + (i,))
                    elif q in str(v).lower() and len(obj) < 200: hits.append((sec, path + (i,), v))
                    if len(hits) >= 400: return
        self.set_status("Searching...")
        if self.doc.campaign is not None: walk(None, self.doc.campaign, ())
        for k in self.doc.order:
            if self.doc.section_editable(k) and k not in ("trees", "rocks", "parcels"):
                try: walk(k, self.doc.get(k), ())
                except Exception: pass
        for i, (sec, path, v) in enumerate(hits):
            iid = str(i); self.search_hits[iid] = (sec, path)
            self.results.insert("", "end", iid=iid, values=("%s / %s" % (sec or "campaign", " / ".join(str(p) for p in path)), summary(v)))
        self.set_status("%d result(s)%s." % (len(hits), " (limited to 400)" if len(hits) >= 400 else ""))

    def raw_goto(self, _=None):
        sel = self.results.selection()
        if not sel: return
        sec, path = self.search_hits[sel[0]]
        cur = self.raw_top.get(sec)
        if cur is None: return
        for k in path:
            self.raw_open(cur); self.raw.item(cur, open=True)
            nxt = next((c for c in self.raw.get_children(cur) if self.raw_info.get(c, {}).get("key") == k), None)
            if nxt is None: break
            cur = nxt
        self.raw.selection_set(cur); self.raw.focus(cur); self.raw.see(cur)

    # ============================================================ SAVE INFO
    def build_info(self):
        t = self.tabs.tab("Save Info")
        t.grid_columnconfigure(0, weight=1, uniform="i"); t.grid_columnconfigure(1, weight=1, uniform="i"); t.grid_rowconfigure(0, weight=1)
        left = card(t); left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        section(left, "Save details")
        self.info_lbl = ctk.CTkLabel(left, text="", justify="left", anchor="w", text_color=MUTED, font=ctk.CTkFont(size=12), wraplength=520)
        self.info_lbl.pack(fill="x", padx=18, pady=(0, 10))
        self.meta_name, self.meta_play, self.slot_name = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for lab, var in (("Autosave label", self.meta_name), ("Play time (seconds)", self.meta_play), ("Slot name in the Load menu", self.slot_name)):
            r = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0); r.pack(fill="x", padx=18, pady=4)
            ctk.CTkLabel(r, text=lab, width=190, anchor="w", text_color=MUTED).pack(side="left")
            ctk.CTkEntry(r, textvariable=var, width=230, height=30).pack(side="left")
        button(left, "Apply", self.meta_apply, "primary").pack(anchor="w", padx=18, pady=(12, 16))
        divider(left)
        section(left, "World data sections")
        fr, self.sections = make_tree(left, [("k", "Section"), ("s", "Size"), ("e", "Editable")], [220, 100, 90], height=12)
        fr.pack(fill="both", expand=True, padx=(12, 8), pady=(0, 14))
        right = card(t); right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        section(right, "Backups", "made automatically before every save")
        fr2, self.backups = make_tree(right, [("f", "Backup file"), ("t", "Size")], [330, 90], height=12)
        fr2.pack(fill="both", expand=True, padx=(12, 8), pady=(0, 10))
        divider(right)
        b = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0); b.pack(fill="x", padx=18, pady=(12, 16))
        button(b, "Restore selected backup", self.restore_backup, "primary").pack(side="left")
        button(b, "Refresh", self.refresh_info).pack(side="right")
        button(b, "Open backup folder", self.open_backups).pack(side="right", padx=8)

    def refresh_info(self):
        d = self.doc
        if not d: return
        m = d.metadata
        self.info_lbl.configure(text="File: %s\nSize: %.1f MB     Format v%s     Checksum: %s\nBaseline: %s\nSite: %s   Machine: %s" % (
            d.path, len(d.raw) / 1e6, d.format_version, "valid" if d.checksum_ok else "INVALID", d.baseline[:16] + "...", m.get("site"), m.get("machine")))
        self.meta_name.set(m.get("display_name", "")); self.meta_play.set(str(m.get("play_time_seconds", "")))
        nm = ""
        mm = re.search(r"\n\s*%s: SaveSlotEntry\(.*?save_name: \"(.*?)\"" % (self.slot_no or 0), S.read_slot_index(), re.S)
        if mm: nm = mm.group(1)
        self.slot_name.set(nm)
        self.sections.delete(*self.sections.get_children())
        for k in d.order:
            sz = d.section_size(k)
            self.sections.insert("", "end", values=(k, "%.1f MB" % (sz / 1e6) if sz > 1e6 else "%.1f KB" % (sz / 1024), "yes" if d.section_editable(k) else "no (binary)"))
        self.backups.delete(*self.backups.get_children())
        if os.path.isdir(S.BACKUP_DIR):
            for f in sorted(os.listdir(S.BACKUP_DIR), reverse=True):
                p = os.path.join(S.BACKUP_DIR, f)
                self.backups.insert("", "end", iid=f, values=(f, "%.1f MB" % (os.path.getsize(p) / 1e6)))

    def meta_apply(self):
        d = self.doc
        try:
            d.metadata["display_name"] = self.meta_name.get()
            if self.meta_play.get().strip():
                pt = parse_num(self.meta_play.get(), True); d.metadata["play_time_seconds"] = pt; self.pending_slot["play_time"] = pt
            d.meta_changed = True
        except Exception as e: messagebox.showerror(APP_NAME, str(e)); return
        if self.slot_name.get().strip(): self.pending_slot["save_name"] = self.slot_name.get().strip()
        self.mark("Save details updated.")

    def restore_backup(self):
        sel = self.backups.selection()
        if not sel: return
        f = sel[0]
        if not f.endswith(".bak") or f.startswith("slots.ron"): messagebox.showinfo(APP_NAME, "Pick a slot-XX backup file."); return
        if S.game_running(): messagebox.showwarning(APP_NAME, "Quit the game first."); return
        m = re.match(r"(slot-\d+\.groundwork-simulator)\.", f)
        if not m or not messagebox.askyesno(APP_NAME, "Restore %s over the current save?\n(Your current file will be backed up first.)" % f): return
        target = os.path.join(S.SLOT_DIR, m.group(1))
        try:
            import shutil
            if os.path.exists(target): shutil.copy2(target, os.path.join(S.BACKUP_DIR, "%s.%s.pre-restore.bak" % (m.group(1), time.strftime("%Y%m%d-%H%M%S"))))
            shutil.copy2(os.path.join(S.BACKUP_DIR, f), target)
        except Exception as e: messagebox.showerror(APP_NAME, str(e)); return
        self.pending_slot = {}; self.doc.dirty_world.clear(); self.doc.ext_dirty = False; self.doc.meta_changed = False
        self.load_selected()

    def open_backups(self):
        os.makedirs(S.BACKUP_DIR, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(S.BACKUP_DIR)
        elif sys.platform == "darwin":
            subprocess.run(["open", S.BACKUP_DIR])
        else:
            subprocess.run(["xdg-open", S.BACKUP_DIR])


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    App(path).mainloop()
