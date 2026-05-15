import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Pango  # type: ignore

from launchy.config import (
    get_global_config, get_game_config,
    save_global_config, save_game_config,
)
from launchy.steam import get_available_proton_versions


class SettingsApplication(Adw.Application):
    def __init__(self, *, appid: str, is_global: bool):
        from gi.repository import Gio
        super().__init__(
            application_id="io.github.launchy.Launchy.Settings",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.appid = appid
        self.is_global = is_global
        self.connect("activate", self._on_activate)

    def _on_activate(self, _app):
        win = SettingsWindow(appid=self.appid, is_global=self.is_global)
        win.set_application(self)
        win.connect("destroy", lambda _: self.quit())
        win.present()


class SettingsWindow(Adw.Window):
    def __init__(self, *, appid: str, is_global: bool):
        super().__init__()
        self.appid = appid
        self.is_global = is_global

        self._config = get_global_config() if is_global else get_game_config(appid)
        self._proton_versions = get_available_proton_versions()
        if not is_global:
            from launchy.steam import get_proc_launch_env
            self._steam_env = get_proc_launch_env(appid)
        else:
            self._steam_env = {}

        if is_global:
            self._header_title = "Global Settings"
            self._header_subtitle = ""
        else:
            from launchy.steam import get_game_info
            game_name = get_game_info(appid).get("name") or f"App {appid}"
            self._header_title = "Game Settings"
            self._header_subtitle = f"{game_name}  ·  App {appid}"

        self.set_title(self._header_title)
        self.set_default_size(580, 520)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title=self._header_title, subtitle=self._header_subtitle)
        )

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        header.pack_start(cancel_btn)

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_end(save_btn)

        toolbar.add_top_bar(header)

        notebook = Gtk.Notebook()
        notebook.set_vexpand(True)
        notebook.set_margin_start(8)
        notebook.set_margin_end(8)
        notebook.set_margin_top(8)
        notebook.set_margin_bottom(8)
        toolbar.set_content(notebook)

        # General tab
        general_page, self._general_widgets = self._build_general_tab()
        notebook.append_page(general_page, Gtk.Label(label="General"))

        # Environment tab
        env_data = self._config.get("env", {})
        env_page, self._env_rows = self._build_kv_tab(
            "Key=value pairs added to the game's environment.",
            {k: str(v) for k, v in env_data.items()},
            self._steam_env,
        )
        notebook.append_page(env_page, Gtk.Label(label="Environment"))

        # Wrappers tab
        wrappers = self._config.get("wrappers", {}).get("pre", [])
        wrappers_page, self._wrapper_rows = self._build_wrappers_tab(
            [str(w) for w in wrappers],
        )
        notebook.append_page(wrappers_page, Gtk.Label(label="Wrappers"))

        # Arguments tab
        args_key = "extra" if self.is_global else "game_args"
        args_desc = (
            "Extra arguments appended after the game command (all games)."
            if self.is_global
            else "Arguments passed directly to the game executable."
        )
        args_data = self._config.get("args", {}).get(args_key, [])
        args_page, self._arg_rows = self._build_list_tab(args_desc, [str(a) for a in args_data])
        notebook.append_page(args_page, Gtk.Label(label="Arguments"))

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_general_tab(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        scrolled.set_child(box)

        group = Adw.PreferencesGroup()
        box.append(group)

        widgets = {}

        # Countdown (global only)
        if self.is_global:
            adj = Gtk.Adjustment(
                value=self._config.get("general", {}).get("countdown", 5),
                lower=0, upper=300, step_increment=1, page_increment=5,
            )
            spin = Gtk.SpinButton(adjustment=adj, numeric=True)
            spin.set_valign(Gtk.Align.CENTER)

            row = Adw.ActionRow(
                title="Countdown",
                subtitle="Seconds before auto-launching (0 = disabled)",
            )
            row.add_suffix(spin)
            row.set_activatable_widget(spin)
            group.add(row)
            widgets["countdown_spin"] = spin

        # Proton dropdown
        names = [v["name"] for v in self._proton_versions]
        model = Gtk.StringList.new(names)

        current_id = self._config.get("general", {}).get("proton", "")
        current_idx = next(
            (i for i, v in enumerate(self._proton_versions) if v["id"] == current_id), 0
        )

        subtitle = (
            "Default Proton/compat tool for all games (unless overridden per-game)."
            if self.is_global
            else "Overrides the global Proton setting for this game only."
        )
        proton_row = Adw.ComboRow(
            title="Proton Version",
            subtitle=subtitle,
            model=model,
            selected=current_idx,
        )
        group.add(proton_row)
        widgets["proton_row"] = proton_row

        return scrolled, widgets

    def _build_kv_tab(self, description: str, initial: dict, steam_env: dict = {}):
        outer, listbox, rows = self._tab_scaffold(description)

        for k, v in steam_env.items():
            listbox.append(_ReadOnlyKVRow(key=k, value=v))

        def add_row(key="", value=""):
            row = _KVRow(key=key, value=value)
            row.connect_remove(lambda r: self._remove_row(r, rows, listbox))
            rows.append(row)
            listbox.append(row)

        for k, v in initial.items():
            add_row(k, v)

        add_btn = self._add_button()
        add_btn.connect("clicked", lambda _: add_row())
        outer.append(add_btn)

        return outer, rows

    def _build_wrappers_tab(self, initial: list):
        outer, listbox, rows = self._tab_scaffold(
            "Commands prepended to the game launch (e.g. mangohud, gamescope …)."
        )

        def add_row(value=""):
            parts = value.split(None, 1)
            cmd = parts[0] if parts else ""
            args = parts[1] if len(parts) > 1 else ""
            row = _WrapperRow(command=cmd, args=args)
            row.connect_remove(lambda r: self._remove_row(r, rows, listbox))
            rows.append(row)
            listbox.append(row)

        for item in initial:
            add_row(item)

        add_btn = self._add_button()
        add_btn.connect("clicked", lambda _: add_row())
        outer.append(add_btn)

        return outer, rows

    def _build_list_tab(self, description: str, initial: list):
        outer, listbox, rows = self._tab_scaffold(description)

        def add_row(value=""):
            row = _ListRow(value=value)
            row.connect_remove(lambda r: self._remove_row(r, rows, listbox))
            rows.append(row)
            listbox.append(row)

        for item in initial:
            add_row(item)

        add_btn = self._add_button()
        add_btn.connect("clicked", lambda _: add_row())
        outer.append(add_btn)

        return outer, rows

    def _tab_scaffold(self, description: str):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        desc_lbl = Gtk.Label(label=description)
        desc_lbl.add_css_class("dim-label")
        desc_lbl.set_wrap(True)
        desc_lbl.set_halign(Gtk.Align.START)
        desc_lbl.set_margin_start(16)
        desc_lbl.set_margin_end(16)
        desc_lbl.set_margin_top(12)
        desc_lbl.set_margin_bottom(8)
        outer.append(desc_lbl)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        listbox.set_margin_start(16)
        listbox.set_margin_end(16)
        listbox.set_margin_top(4)
        listbox.set_margin_bottom(4)

        scrolled.set_child(listbox)
        outer.append(scrolled)

        rows = []
        return outer, listbox, rows

    @staticmethod
    def _add_button() -> Gtk.Button:
        btn = Gtk.Button()
        btn.set_margin_start(16)
        btn.set_margin_end(16)
        btn.set_margin_top(6)
        btn.set_margin_bottom(12)

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        inner.set_halign(Gtk.Align.CENTER)
        inner.append(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        inner.append(Gtk.Label(label="Add"))
        btn.set_child(inner)
        return btn

    @staticmethod
    def _remove_row(row, rows: list, listbox: Gtk.ListBox):
        if row in rows:
            rows.remove(row)
        listbox.remove(row)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save(self, _btn):
        cfg = dict(self._config)

        # -- General
        if "general" not in cfg:
            cfg["general"] = {}

        gw = self._general_widgets
        if self.is_global and "countdown_spin" in gw:
            cfg["general"]["countdown"] = int(gw["countdown_spin"].get_value())

        idx = gw["proton_row"].get_selected()
        if 0 <= idx < len(self._proton_versions):
            cfg["general"]["proton"] = self._proton_versions[idx]["id"]

        # -- Environment
        env: dict = {}
        for row in self._env_rows:
            k = row.get_key().strip()
            v = row.get_value()
            if k:
                env[k] = v
        cfg["env"] = env

        # -- Wrappers
        wrappers = []
        for r in self._wrapper_rows:
            cmd = r.get_command().strip()
            if cmd:
                args = r.get_args().strip()
                wrappers.append(f"{cmd} {args}".strip())
        if "wrappers" not in cfg:
            cfg["wrappers"] = {}
        cfg["wrappers"]["pre"] = wrappers

        # -- Arguments
        args_key = "extra" if self.is_global else "game_args"
        args_list = [r.get_value().strip() for r in self._arg_rows if r.get_value().strip()]
        if "args" not in cfg:
            cfg["args"] = {}
        cfg["args"][args_key] = args_list

        if self.is_global:
            save_global_config(cfg)
        else:
            save_game_config(self.appid, cfg)

        self.close()


# ---------------------------------------------------------------------------
# Row widgets
# ---------------------------------------------------------------------------

class _ReadOnlyKVRow(Gtk.ListBoxRow):
    def __init__(self, *, key: str, value: str):
        super().__init__()
        self.set_activatable(False)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        self.set_child(box)

        key_lbl = Gtk.Label(label=key)
        key_lbl.add_css_class("dim-label")
        key_lbl.set_selectable(True)
        key_lbl.set_hexpand(True)
        key_lbl.set_halign(Gtk.Align.START)
        key_lbl.set_ellipsize(Pango.EllipsizeMode.END)

        eq = Gtk.Label(label="=")
        eq.add_css_class("dim-label")

        val_lbl = Gtk.Label(label=value)
        val_lbl.add_css_class("dim-label")
        val_lbl.set_selectable(True)
        val_lbl.set_hexpand(True)
        val_lbl.set_halign(Gtk.Align.START)
        val_lbl.set_ellipsize(Pango.EllipsizeMode.END)

        info_btn = Gtk.Button(icon_name="dialog-information-symbolic")
        info_btn.add_css_class("flat")
        info_btn.add_css_class("circular")
        info_btn.set_tooltip_text("Inherited from Steam launch options — not editable here")

        box.append(key_lbl)
        box.append(eq)
        box.append(val_lbl)
        box.append(info_btn)


class _KVRow(Gtk.ListBoxRow):
    def __init__(self, *, key: str = "", value: str = ""):
        super().__init__()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        self.set_child(box)

        self._key = Gtk.Entry()
        self._key.set_text(key)
        self._key.set_placeholder_text("VARIABLE_NAME")
        self._key.set_hexpand(True)

        eq = Gtk.Label(label="=")
        eq.add_css_class("dim-label")

        self._val = Gtk.Entry()
        self._val.set_text(value)
        self._val.set_placeholder_text("value")
        self._val.set_hexpand(True)

        self._rm = Gtk.Button(icon_name="list-remove-symbolic")
        self._rm.add_css_class("flat")
        self._rm.add_css_class("circular")

        box.append(self._key)
        box.append(eq)
        box.append(self._val)
        box.append(self._rm)

    def connect_remove(self, callback):
        self._rm.connect("clicked", lambda _: callback(self))

    def get_key(self) -> str:
        return self._key.get_text()

    def get_value(self) -> str:
        return self._val.get_text()


class _WrapperRow(Gtk.ListBoxRow):
    def __init__(self, *, command: str = "", args: str = ""):
        super().__init__()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        self.set_child(box)

        self._cmd = Gtk.Entry()
        self._cmd.set_text(command)
        self._cmd.set_placeholder_text("command")
        self._cmd.set_width_chars(18)

        sep = Gtk.Label(label="·")
        sep.add_css_class("dim-label")

        self._args = Gtk.Entry()
        self._args.set_text(args)
        self._args.set_placeholder_text("arguments (optional)")
        self._args.set_hexpand(True)

        self._rm = Gtk.Button(icon_name="list-remove-symbolic")
        self._rm.add_css_class("flat")
        self._rm.add_css_class("circular")

        box.append(self._cmd)
        box.append(sep)
        box.append(self._args)
        box.append(self._rm)

    def connect_remove(self, callback):
        self._rm.connect("clicked", lambda _: callback(self))

    def get_command(self) -> str:
        return self._cmd.get_text()

    def get_args(self) -> str:
        return self._args.get_text()


class _ListRow(Gtk.ListBoxRow):
    def __init__(self, *, value: str = ""):
        super().__init__()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        self.set_child(box)

        self._val = Gtk.Entry()
        self._val.set_text(value)
        self._val.set_placeholder_text("value")
        self._val.set_hexpand(True)

        self._rm = Gtk.Button(icon_name="list-remove-symbolic")
        self._rm.add_css_class("flat")
        self._rm.add_css_class("circular")

        box.append(self._val)
        box.append(self._rm)

    def connect_remove(self, callback):
        self._rm.connect("clicked", lambda _: callback(self))

    def get_value(self) -> str:
        return self._val.get_text()
