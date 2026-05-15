import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Pango  # type: ignore

from launchy.config import get_set_config, save_set_config
from launchy.ui.settings_window import _KVRow, _WrapperRow, _ListRow


class SetWindow(Adw.Window):
    def __init__(self, *, set_id: str, on_saved=None, parent=None):
        super().__init__()
        self.set_id = set_id
        self._config = get_set_config(set_id)
        self._on_saved_cb = on_saved

        self.set_title("Edit Set")
        self.set_default_size(650, 520)
        if parent:
            self.set_transient_for(parent)
            self.set_modal(True)

        self._build_ui()

    def _build_ui(self):
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()
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

        general_page = self._build_general_tab()
        notebook.append_page(general_page, Gtk.Label(label="General"))

        env_page, self._env_rows = self._build_kv_tab(
            "Environment variables added by this set.",
            {k: str(v) for k, v in self._config.get("env", {}).items()},
        )
        notebook.append_page(env_page, Gtk.Label(label="Environment"))

        wrappers_page, self._wrapper_rows = self._build_simple_list_tab(
            "Commands prepended to the game launch (e.g. mangohud, gamescope …).\n"
            "Wrappers are applied in order, top to bottom.",
            [str(w) for w in self._config.get("wrappers", {}).get("pre", [])],
            is_wrapper=True,
        )
        notebook.append_page(wrappers_page, Gtk.Label(label="Wrappers"))

        args_page, self._arg_rows = self._build_simple_list_tab(
            "Extra arguments for this set.\nArguments are passed in order, top to bottom.",
            [str(a) for a in self._config.get("args", {}).get("extra", [])],
            is_wrapper=False,
        )
        notebook.append_page(args_page, Gtk.Label(label="Arguments"))

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_general_tab(self):
        outer, content = self._tab_outer()

        grp = Adw.PreferencesGroup()
        grp.set_margin_start(16)
        grp.set_margin_end(16)
        grp.set_margin_top(12)
        grp.set_margin_bottom(8)
        content.append(grp)

        self._name_entry = Adw.EntryRow(title="Set Name")
        self._name_entry.set_text(self._config.get("general", {}).get("name", ""))
        grp.add(self._name_entry)

        self._show_in_launch = Adw.SwitchRow(
            title="Show in launch window",
            subtitle="Show a quick-enable checkbox when launching games",
        )
        self._show_in_launch.set_active(
            self._config.get("general", {}).get("show_in_launch", False)
        )
        grp.add(self._show_in_launch)

        self._enabled_by_default = Adw.SwitchRow(
            title="Enabled by default",
            subtitle="Automatically enable for games with no custom configuration",
        )
        self._enabled_by_default.set_active(
            self._config.get("general", {}).get("enabled_by_default", False)
        )
        grp.add(self._enabled_by_default)

        self._requires_checks: dict = {}
        from launchy.config import get_global_config, get_set_config as _gsc
        gcfg = get_global_config()
        other_sets = []
        for sid in gcfg.get("sets", {}).get("order", []):
            if sid == self.set_id:
                continue
            try:
                name = _gsc(sid).get("general", {}).get("name", "Unnamed Set")
                other_sets.append((sid, name))
            except Exception:
                pass

        if other_sets:
            current_requires = set(self._config.get("general", {}).get("requires", []))
            req_grp = Adw.PreferencesGroup()
            req_grp.set_title("Requires")
            req_grp.set_description("Sets that are automatically activated when this set is enabled")
            req_grp.set_margin_start(16)
            req_grp.set_margin_end(16)
            req_grp.set_margin_top(8)
            req_grp.set_margin_bottom(8)
            content.append(req_grp)
            for sid, name in other_sets:
                check = Gtk.CheckButton()
                check.set_active(sid in current_requires)
                check.set_valign(Gtk.Align.CENTER)
                row = Adw.ActionRow(title=name)
                row.add_suffix(check)
                row.set_activatable_widget(check)
                req_grp.add(row)
                self._requires_checks[sid] = check

        return outer

    def _build_kv_tab(self, description: str, initial: dict):
        outer, content = self._tab_outer()
        rows = []
        lb = self._make_listbox()
        lb.set_placeholder(self._make_empty_label())

        def add_row(key="", value=""):
            row = _KVRow(key=key, value=value)
            row.connect_remove(lambda r: self._remove_row(r, rows, lb))
            rows.append(row)
            lb.append(row)

        for k, v in initial.items():
            add_row(k, v)

        content.append(self._make_desc_label(description))
        content.append(lb)

        add_btn = self._add_button()
        add_btn.connect("clicked", lambda _: add_row())
        outer.append(add_btn)

        return outer, rows

    def _build_simple_list_tab(self, description: str, initial: list, is_wrapper: bool):
        outer, content = self._tab_outer()
        rows = []
        lb = self._make_listbox()
        lb.set_placeholder(self._make_empty_label())

        def add_row(value=""):
            if is_wrapper:
                parts = value.split(None, 1)
                row = _WrapperRow(
                    command=parts[0] if parts else "",
                    args=parts[1] if len(parts) > 1 else "",
                )
            else:
                row = _ListRow(value=value)
            row.connect_remove(lambda r: self._remove_row(r, rows, lb))
            row.connect_move(rows, lb)
            rows.append(row)
            lb.append(row)

        for item in initial:
            add_row(item)

        content.append(self._make_desc_label(description))
        content.append(lb)

        add_btn = self._add_button()
        add_btn.connect("clicked", lambda _: add_row())
        outer.append(add_btn)

        return outer, rows

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save(self, _btn):
        from launchy.config import get_global_config, get_set_config as _gsc

        new_name = self._name_entry.get_text().strip() or "Unnamed Set"

        gcfg = get_global_config()
        for other_id in gcfg.get("sets", {}).get("order", []):
            if other_id == self.set_id:
                continue
            try:
                other_name = _gsc(other_id).get("general", {}).get("name", "")
                if other_name == new_name:
                    dialog = Adw.MessageDialog(
                        transient_for=self,
                        heading="Duplicate Name",
                        body=f'A set named "{new_name}" already exists. Choose a different name.',
                    )
                    dialog.add_response("ok", "OK")
                    dialog.present()
                    return
            except Exception:
                pass

        cfg = dict(self._config)
        if "general" not in cfg:
            cfg["general"] = {}
        cfg["general"]["name"] = new_name
        cfg["general"]["show_in_launch"] = self._show_in_launch.get_active()
        cfg["general"]["enabled_by_default"] = self._enabled_by_default.get_active()
        cfg["general"]["requires"] = [
            sid for sid, chk in self._requires_checks.items() if chk.get_active()
        ]

        env: dict = {}
        for row in self._env_rows:
            k = row.get_key().strip()
            if k:
                env[k] = row.get_value()
        cfg["env"] = env

        wrappers = []
        for r in self._wrapper_rows:
            cmd = r.get_command().strip()
            if cmd:
                args = r.get_args().strip()
                wrappers.append(f"{cmd} {args}".strip())
        if "wrappers" not in cfg:
            cfg["wrappers"] = {}
        cfg["wrappers"]["pre"] = wrappers

        args_list = [r.get_value().strip() for r in self._arg_rows if r.get_value().strip()]
        if "args" not in cfg:
            cfg["args"] = {}
        cfg["args"]["extra"] = args_list

        save_set_config(self.set_id, cfg)
        if self._on_saved_cb:
            self._on_saved_cb(cfg)
        self.close()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _tab_outer(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_vexpand(True)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        outer.append(scrolled)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        content.set_margin_top(8)
        content.set_margin_bottom(8)
        scrolled.set_child(content)
        return outer, content

    @staticmethod
    def _make_listbox() -> Gtk.ListBox:
        lb = Gtk.ListBox()
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        lb.set_margin_start(16)
        lb.set_margin_end(16)
        lb.set_margin_top(4)
        lb.set_margin_bottom(4)
        return lb

    @staticmethod
    def _make_empty_label() -> Gtk.Widget:
        lbl = Gtk.Label(label="No entries. Press Add to add one.")
        lbl.add_css_class("dim-label")
        lbl.set_margin_top(12)
        lbl.set_margin_bottom(12)
        return lbl

    @staticmethod
    def _make_desc_label(text: str) -> Gtk.Widget:
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("dim-label")
        lbl.add_css_class("caption")
        lbl.set_halign(Gtk.Align.START)
        lbl.set_wrap(True)
        lbl.set_margin_start(16)
        lbl.set_margin_end(16)
        lbl.set_margin_top(8)
        lbl.set_margin_bottom(4)
        return lbl

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
