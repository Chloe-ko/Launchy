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
    def __init__(self, *, appid: str, is_global: bool, on_saved=None):
        super().__init__()
        self.appid = appid
        self.is_global = is_global
        self._on_saved_cb = on_saved

        self._config = get_global_config() if is_global else get_game_config(appid)
        self._proton_versions = get_available_proton_versions()

        if is_global:
            self._header_title = "Global Settings"
            self._header_subtitle = ""
            self._steam_env = {}
            self._steam_args = ""
            self._steam_wrappers = ""
            self._global_config = None
        else:
            from launchy.steam import get_game_info, get_steam_launch_env
            game_name = get_game_info(appid).get("name") or f"App {appid}"
            self._header_title = "Game Settings"
            self._header_subtitle = f"{game_name}  ·  App {appid}"
            self._steam_env = get_steam_launch_env(appid)
            from launchy.steam import get_steam_launch_args, get_steam_launch_wrappers
            self._steam_args = get_steam_launch_args(appid)
            self._steam_wrappers = get_steam_launch_wrappers(appid)
            self._global_config = get_global_config()

        self.set_title(self._header_title)
        self.set_default_size(800, 680)

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

        self._set_rows = []  # populated by _build_game_sets_tab for per-game
        self._explicit_set_ids: set = set()
        if not self.is_global:
            self._explicit_set_ids = set(self._config.get("sets", []))

        general_page, self._general_widgets = self._build_general_tab()
        notebook.append_page(general_page, Gtk.Label(label="General"))

        gcfg = self._global_config or {}

        global_env = {k: str(v) for k, v in gcfg.get("env", {}).items()}
        env_data = self._config.get("env", {})
        env_page, self._env_rows, self._global_env_rows = self._build_kv_tab(
            "Key=value pairs added to the game's environment.",
            {k: str(v) for k, v in env_data.items()},
            self._steam_env,
            global_env if not self.is_global else {},
        )
        notebook.append_page(env_page, Gtk.Label(label="Environment"))

        global_wrappers = [str(w) for w in gcfg.get("wrappers", [])]
        wrappers = self._config.get("wrappers", [])
        wrappers_page, self._wrapper_rows, self._global_wrapper_rows = self._build_wrappers_tab(
            [str(w) for w in wrappers],
            self._steam_wrappers,
            global_wrappers if not self.is_global else [],
        )
        notebook.append_page(wrappers_page, Gtk.Label(label="Wrappers"))

        args_desc = (
            "Extra arguments appended after the game command (all games)."
            if self.is_global
            else "Arguments passed directly to the game executable."
        )
        global_extra = [str(a) for a in gcfg.get("args", [])]
        args_data = self._config.get("args", [])
        args_page, self._arg_rows, self._global_arg_rows = self._build_list_tab(
            args_desc,
            [str(a) for a in args_data],
            self._steam_args,
            global_extra if not self.is_global else [],
        )
        notebook.append_page(args_page, Gtk.Label(label="Arguments"))

        if self.is_global:
            sets_page = self._build_global_sets_tab()
        else:
            sets_page = self._build_game_sets_tab()
        notebook.append_page(sets_page, Gtk.Label(label="Sets"))

        if not self.is_global:
            self._refresh_set_sections()

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

        self._skip_group = None
        self._skip_rows = []

        group = Adw.PreferencesGroup()
        box.append(group)

        widgets = {}

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

        current_id = self._config.get("general", {}).get("proton", "")

        if not self.is_global:
            gcfg = self._global_config or {}
            global_proton_id = gcfg.get("general", {}).get("proton", "")
            global_proton_name = next(
                (v["name"] for v in self._proton_versions if v["id"] == global_proton_id),
                global_proton_id or "None",
            )
            inherited_label = f"Inherit Global: {global_proton_name}"
            names = [inherited_label] + [v["name"] for v in self._proton_versions]
            model = Gtk.StringList.new(names)
            if current_id:
                current_idx = next(
                    (i + 1 for i, v in enumerate(self._proton_versions) if v["id"] == current_id), 0
                )
            else:
                current_idx = 0
            subtitle = "Overrides the global Proton setting for this game only."
            widgets["proton_inherited_label"] = inherited_label
        else:
            names = [v["name"] for v in self._proton_versions]
            model = Gtk.StringList.new(names)
            current_idx = next(
                (i for i, v in enumerate(self._proton_versions) if v["id"] == current_id), 0
            )
            subtitle = "Default Proton/compat tool for all games (unless overridden per-game)."

        proton_row = Adw.ComboRow(
            title="Proton Version",
            subtitle=subtitle,
            model=model,
            selected=current_idx,
        )
        group.add(proton_row)
        widgets["proton_row"] = proton_row

        if not self.is_global:
            skip_val = self._config.get("general", {}).get("skip_countdown", False)
            skip_row = Adw.SwitchRow(
                title="Launch Instantly",
                subtitle="Skip the countdown window and launch this game directly.",
                active=skip_val,
            )
            group.add(skip_row)
            widgets["skip_row"] = skip_row

        if self.is_global:
            self._skip_group = Adw.PreferencesGroup(
                title="Skip Countdown",
                description="Games that skip the launch window and launch instantly.",
            )
            box.append(self._skip_group)
            self._rebuild_skip_list()

        return scrolled, widgets

    def _rebuild_skip_list(self):
        from launchy.config import get_games_with_skip_countdown, get_game_config
        for row in self._skip_rows:
            self._skip_group.remove(row)
        self._skip_rows = []

        appids = get_games_with_skip_countdown()
        if not appids:
            row = Adw.ActionRow(title="No games configured")
            row.set_sensitive(False)
            self._skip_group.add(row)
            self._skip_rows.append(row)
            return

        entries = []
        for appid in appids:
            cfg_name = get_game_config(appid).get("general", {}).get("name", "")
            img_path = None
            steam_name = ""
            try:
                from launchy.steam import get_game_info
                info = get_game_info(appid)
                steam_name = info.get("name", "")
                img_path = info.get("header_image_path")
            except Exception:
                pass
            entries.append((appid, cfg_name or steam_name or f"App {appid}", img_path))
        entries.sort(key=lambda x: x[1].lower())

        thumb_w, thumb_h = 60, 30
        for appid, name, img_path in entries:
            row = Adw.ActionRow(title=name, subtitle=f"App {appid}")

            if img_path:
                try:
                    from gi.repository import GdkPixbuf
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(img_path, thumb_w * 2, -1, True)
                    pic = Gtk.Picture.new_for_pixbuf(pb)
                    pic.set_content_fit(Gtk.ContentFit.COVER)
                    pic.set_size_request(thumb_w, thumb_h)
                    pic.set_margin_top(6)
                    pic.set_margin_bottom(6)
                    pic.set_margin_start(4)
                    row.add_prefix(pic)
                except Exception:
                    pass

            btn = Gtk.Button(label="Remove")
            btn.add_css_class("destructive-action")
            btn.set_valign(Gtk.Align.CENTER)
            btn.connect("clicked", lambda _, aid=appid: self._remove_skip(aid))
            row.add_suffix(btn)
            self._skip_group.add(row)
            self._skip_rows.append(row)

    def _remove_skip(self, appid: str):
        from launchy.config import get_game_config, save_game_config
        cfg = get_game_config(appid)
        if "general" not in cfg:
            cfg["general"] = {}
        cfg["general"]["skip_countdown"] = False
        save_game_config(appid, cfg)
        self._rebuild_skip_list()

    def _build_kv_tab(self, description: str, initial: dict, steam_env: dict = {}, global_env: dict = {}):
        outer, content = self._tab_outer()
        global_rows = []

        if steam_env:
            lb = self._make_listbox()
            for k, v in steam_env.items():
                lb.append(_ReadOnlyKVRow(key=k, value=v))
            content.append(self._make_collapsible_section("Steam Launch Options", lb))

        if not self.is_global and global_env:
            ignore_env = set(self._config.get("global_ignore", {}).get("env", []))
            per_game_keys = set(initial.keys())
            lb = self._make_listbox()
            for k, v in global_env.items():
                overridden = k in per_game_keys
                row = _ReadOnlyKVRow(
                    key=k, value=v, tooltip=_TOOLTIP_GLOBAL,
                    has_ignore=True, ignored=(k in ignore_env), overridden=overridden,
                )
                global_rows.append(row)
                lb.append(row)
            content.append(self._make_collapsible_section("Global Options", lb))

        if not self.is_global:
            self._set_env_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            content.append(self._set_env_slot)

        rows = []
        lb = self._make_listbox()
        lb.set_placeholder(self._make_empty_label())

        def add_row(key="", value=""):
            row = _KVRow(key=key, value=value)
            row.connect_remove(lambda r: (self._remove_row(r, rows, lb), self._update_override_states()))
            if not self.is_global:
                row.connect_key_changed(self._update_override_states)
            rows.append(row)
            lb.append(row)

        for k, v in initial.items():
            add_row(k, v)

        section_title = "Per-Game Options" if not self.is_global else "Options"
        content.append(self._make_section_header(section_title, description))
        content.append(lb)

        add_btn = self._add_button()
        add_btn.connect("clicked", lambda _: add_row())
        outer.append(add_btn)

        return outer, rows, global_rows

    def _build_wrappers_tab(self, initial: list, steam_wrappers: str = "", global_wrappers: list = []):
        outer, content = self._tab_outer()
        global_rows = []
        description = "Commands prepended to the game launch (e.g. mangohud, gamescope …)."

        if steam_wrappers:
            lb = self._make_listbox()
            lb.append(_ReadOnlyListRow(value=steam_wrappers))
            content.append(self._make_collapsible_section("Steam Launch Options", lb))

        if not self.is_global and global_wrappers:
            ignore_wrappers = set(self._config.get("global_ignore", {}).get("wrappers", []))
            per_game_binaries = {w.split()[0] for w in initial if w.strip()}
            lb = self._make_listbox()
            for w in global_wrappers:
                binary = w.split()[0] if w.strip() else w
                overridden = binary in per_game_binaries
                row = _ReadOnlyListRow(
                    value=w, row_id=binary, tooltip=_TOOLTIP_GLOBAL,
                    has_ignore=True, ignored=(binary in ignore_wrappers), overridden=overridden,
                )
                global_rows.append(row)
                lb.append(row)
            content.append(self._make_collapsible_section("Global Options", lb))

        if not self.is_global:
            self._set_wrappers_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            content.append(self._set_wrappers_slot)

        rows = []
        lb = self._make_listbox()
        lb.set_placeholder(self._make_empty_label())

        def add_row(value=""):
            parts = value.split(None, 1)
            cmd = parts[0] if parts else ""
            args = parts[1] if len(parts) > 1 else ""
            row = _WrapperRow(command=cmd, args=args)
            row.connect_remove(lambda r: (self._remove_row(r, rows, lb), self._update_override_states()))
            if not self.is_global:
                row.connect_command_changed(self._update_override_states)
            row.connect_move(rows, lb)
            rows.append(row)
            lb.append(row)

        for item in initial:
            add_row(item)

        section_title = "Per-Game Options" if not self.is_global else "Options"
        content.append(self._make_section_header(
            section_title,
            description + "\nWrappers are applied in order, top to bottom.",
        ))
        content.append(lb)

        add_btn = self._add_button()
        add_btn.connect("clicked", lambda _: add_row())
        outer.append(add_btn)

        return outer, rows, global_rows

    def _build_list_tab(self, description: str, initial: list, steam_args: str = "", global_args: list = []):
        outer, content = self._tab_outer()
        global_rows = []

        if steam_args:
            lb = self._make_listbox()
            lb.append(_ReadOnlyListRow(value=steam_args))
            content.append(self._make_collapsible_section("Steam Launch Options", lb))

        if not self.is_global and global_args:
            ignore_args = set(self._config.get("global_ignore", {}).get("args", []))
            lb = self._make_listbox()
            for a in global_args:
                row = _ReadOnlyListRow(
                    value=a, tooltip=_TOOLTIP_GLOBAL,
                    has_ignore=True, ignored=(str(a) in ignore_args), overridden=False,
                )
                global_rows.append(row)
                lb.append(row)
            content.append(self._make_collapsible_section("Global Options", lb))

        if not self.is_global:
            self._set_args_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            content.append(self._set_args_slot)

        rows = []
        lb = self._make_listbox()
        lb.set_placeholder(self._make_empty_label())

        def add_row(value=""):
            row = _ListRow(value=value)
            row.connect_remove(lambda r: self._remove_row(r, rows, lb))
            row.connect_move(rows, lb)
            rows.append(row)
            lb.append(row)

        for item in initial:
            add_row(item)

        section_title = "Per-Game Options" if not self.is_global else "Options"
        content.append(self._make_section_header(
            section_title,
            description + "\nArguments are passed in order, top to bottom.",
        ))
        content.append(lb)

        add_btn = self._add_button()
        add_btn.connect("clicked", lambda _: add_row())
        outer.append(add_btn)

        return outer, rows, global_rows

    def _build_global_sets_tab(self):
        from launchy.config import (
            get_set_config, delete_set_config, create_set,
            get_global_config, save_global_config,
        )
        from launchy.ui.set_window import SetWindow

        outer, content = self._tab_outer()

        desc = Gtk.Label(
            label="Sets are named groups of env variables, wrappers, and arguments.\n"
                  "Enable them per game in each game's Sets tab. "
                  "Higher sets take priority over lower ones."
        )
        desc.add_css_class("dim-label")
        desc.add_css_class("caption")
        desc.set_halign(Gtk.Align.START)
        desc.set_wrap(True)
        desc.set_margin_start(16)
        desc.set_margin_end(16)
        desc.set_margin_top(8)
        desc.set_margin_bottom(4)
        content.append(desc)

        lb = self._make_listbox()
        placeholder = Gtk.Label(label="No sets. Press New Set to create one.")
        placeholder.add_css_class("dim-label")
        placeholder.set_margin_top(12)
        placeholder.set_margin_bottom(12)
        lb.set_placeholder(placeholder)
        content.append(lb)

        rows: list = []

        def _save_order():
            order = [r.set_id for r in rows]
            cfg = get_global_config()
            cfg["sets"] = order
            save_global_config(cfg)
            # keep self._config in sync so _on_save doesn't clobber the order
            self._config["sets"] = order

        def _add_row(set_id, name):
            row = _GlobalSetRow(set_id=set_id, name=name)

            def on_edit(_row):
                sw = SetWindow(
                    set_id=set_id, parent=self,
                    on_saved=lambda cfg: row.update_name(
                        cfg.get("general", {}).get("name", "")
                    ),
                )
                sw.present()

            def on_delete(_row):
                delete_set_config(set_id)
                if row in rows:
                    rows.remove(row)
                lb.remove(row)
                _save_order()

            row.connect_edit(on_edit)
            row.connect_delete(on_delete)
            row.connect_move(rows, lb, _save_order)
            rows.append(row)
            lb.append(row)
            return row

        # Load existing sets
        all_set_ids = self._config.get("sets", [])
        for sid in all_set_ids:
            try:
                scfg = get_set_config(sid)
                _add_row(sid, scfg.get("general", {}).get("name", "Unnamed Set"))
            except Exception:
                pass

        # New Set button
        add_btn = Gtk.Button()
        add_btn.set_margin_start(16)
        add_btn.set_margin_end(16)
        add_btn.set_margin_top(6)
        add_btn.set_margin_bottom(12)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        inner.set_halign(Gtk.Align.CENTER)
        inner.append(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        inner.append(Gtk.Label(label="New Set"))
        add_btn.set_child(inner)

        def on_add(_btn):
            sid = create_set()
            scfg = get_set_config(sid)
            row = _add_row(sid, scfg.get("general", {}).get("name", "New Set"))
            _save_order()
            sw = SetWindow(
                set_id=sid, parent=self,
                on_saved=lambda cfg: row.update_name(
                    cfg.get("general", {}).get("name", "")
                ),
            )
            sw.present()

        add_btn.connect("clicked", on_add)
        outer.append(add_btn)

        return outer

    def _build_game_sets_tab(self):
        from launchy.config import get_set_config, _expand_with_deps

        outer, content = self._tab_outer()

        desc = Gtk.Label(
            label="Enable sets to apply their env variables, wrappers, and arguments to this game.\n"
                  "Sets are listed in priority order — higher sets override lower ones."
        )
        desc.add_css_class("dim-label")
        desc.add_css_class("caption")
        desc.set_halign(Gtk.Align.START)
        desc.set_wrap(True)
        desc.set_margin_start(16)
        desc.set_margin_end(16)
        desc.set_margin_top(8)
        desc.set_margin_bottom(4)
        content.append(desc)

        lb = self._make_listbox()
        placeholder = Gtk.Label(label="No sets defined. Create sets in Global Settings → Sets.")
        placeholder.add_css_class("dim-label")
        placeholder.set_margin_top(12)
        placeholder.set_margin_bottom(12)
        lb.set_placeholder(placeholder)
        content.append(lb)

        gcfg = self._global_config or {}
        set_order = gcfg.get("sets", [])
        explicit_ids = self._explicit_set_ids

        def _refresh_list():
            children = []
            child = lb.get_first_child()
            while child is not None:
                children.append(child)
                child = child.get_next_sibling()
            for c in children:
                lb.remove(c)

            requirers: dict = {}
            for eid in explicit_ids:
                try:
                    ename = get_set_config(eid).get("general", {}).get("name", "Unnamed Set")
                    for dep_id in _expand_with_deps({eid}, set_order) - {eid}:
                        requirers.setdefault(dep_id, []).append(ename)
                except Exception:
                    pass

            self._set_rows = []
            for sid in set_order:
                try:
                    scfg = get_set_config(sid)
                    name = scfg.get("general", {}).get("name", "Unnamed Set")
                    is_explicit = sid in explicit_ids
                    required_by = requirers.get(sid)
                    row = _GameSetRow(set_id=sid, name=name, enabled=is_explicit, required_by=required_by)

                    def on_toggle(btn, set_id=sid):
                        if btn.get_active():
                            explicit_ids.add(set_id)
                        else:
                            explicit_ids.discard(set_id)
                        _refresh_list()
                        self._refresh_set_sections()

                    row.connect_toggled(on_toggle)
                    lb.append(row)
                    self._set_rows.append(row)
                except Exception:
                    pass

        _refresh_list()
        return outer

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
    def _make_collapsible_multi(title: str, groups: list) -> Gtk.Widget:
        """Collapsible card whose expanded area shows multiple (set_name, listbox) groups."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("card")
        card.set_margin_start(16)
        card.set_margin_end(16)
        card.set_margin_top(4)
        card.set_margin_bottom(4)

        header_btn = Gtk.Button()
        header_btn.add_css_class("flat")
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hbox.set_margin_start(12)
        hbox.set_margin_end(8)
        hbox.set_margin_top(10)
        hbox.set_margin_bottom(10)
        title_lbl = Gtk.Label(label=title)
        title_lbl.add_css_class("heading")
        title_lbl.set_halign(Gtk.Align.START)
        title_lbl.set_hexpand(True)
        hbox.append(title_lbl)
        arrow = Gtk.Image.new_from_icon_name("pan-end-symbolic")
        hbox.append(arrow)
        header_btn.set_child(hbox)
        card.append(header_btn)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        inner.set_margin_bottom(8)
        for name, lb in groups:
            name_lbl = Gtk.Label(label=name)
            name_lbl.add_css_class("heading")
            name_lbl.set_halign(Gtk.Align.START)
            name_lbl.set_margin_start(20)
            name_lbl.set_margin_top(10)
            name_lbl.set_margin_bottom(8)
            inner.append(name_lbl)
            lb.set_margin_start(8)
            lb.set_margin_end(8)
            lb.set_margin_top(0)
            lb.set_margin_bottom(0)
            inner.append(lb)

        revealer = Gtk.Revealer()
        revealer.set_reveal_child(False)
        revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        revealer.set_transition_duration(200)
        revealer.set_child(inner)
        card.append(revealer)

        def _toggle(_btn):
            exp = not revealer.get_reveal_child()
            revealer.set_reveal_child(exp)
            arrow.set_from_icon_name("pan-down-symbolic" if exp else "pan-end-symbolic")

        header_btn.connect("clicked", _toggle)
        return card

    @staticmethod
    def _make_collapsible_section(title: str, listbox: Gtk.ListBox) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("card")
        card.set_margin_start(16)
        card.set_margin_end(16)
        card.set_margin_top(4)
        card.set_margin_bottom(4)

        header_btn = Gtk.Button()
        header_btn.add_css_class("flat")

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hbox.set_margin_start(12)
        hbox.set_margin_end(8)
        hbox.set_margin_top(10)
        hbox.set_margin_bottom(10)

        title_lbl = Gtk.Label(label=title)
        title_lbl.add_css_class("heading")
        title_lbl.set_halign(Gtk.Align.START)
        title_lbl.set_hexpand(True)
        hbox.append(title_lbl)

        arrow = Gtk.Image.new_from_icon_name("pan-end-symbolic")
        hbox.append(arrow)
        header_btn.set_child(hbox)
        card.append(header_btn)

        listbox.set_margin_start(8)
        listbox.set_margin_end(8)
        listbox.set_margin_top(0)
        listbox.set_margin_bottom(8)

        revealer = Gtk.Revealer()
        revealer.set_reveal_child(False)
        revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        revealer.set_transition_duration(200)
        revealer.set_child(listbox)
        card.append(revealer)

        def _toggle(_btn):
            exp = not revealer.get_reveal_child()
            revealer.set_reveal_child(exp)
            arrow.set_from_icon_name("pan-down-symbolic" if exp else "pan-end-symbolic")

        header_btn.connect("clicked", _toggle)
        return card

    @staticmethod
    def _make_section_header(title: str, subtitle: str = "") -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(8)
        box.set_margin_bottom(4)

        lbl = Gtk.Label(label=title)
        lbl.add_css_class("heading")
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)

        if subtitle:
            sub = Gtk.Label(label=subtitle)
            sub.add_css_class("dim-label")
            sub.add_css_class("caption")
            sub.set_halign(Gtk.Align.START)
            sub.set_wrap(True)
            box.append(sub)

        return box

    @staticmethod
    def _make_empty_label() -> Gtk.Widget:
        lbl = Gtk.Label(label="No entries. Press Add to add one.")
        lbl.add_css_class("dim-label")
        lbl.set_margin_top(12)
        lbl.set_margin_bottom(12)
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

    @staticmethod
    def _clear_slot(box: Gtk.Box):
        children = []
        child = box.get_first_child()
        while child:
            children.append(child)
            child = child.get_next_sibling()
        for c in children:
            box.remove(c)

    def _update_override_states(self):
        if self.is_global:
            return
        per_game_keys = {r.get_key().strip() for r in self._env_rows}
        for row in self._global_env_rows:
            row.set_overridden(row.get_id() in per_game_keys)
        for row in getattr(self, "_set_env_display_rows", []):
            row.set_overridden(row.get_id() in per_game_keys)

        per_game_bins = {r.get_command().strip() for r in self._wrapper_rows}
        for row in self._global_wrapper_rows:
            row.set_overridden(row.get_id() in per_game_bins)
        for row in getattr(self, "_set_wrappers_display_rows", []):
            row.set_overridden(row.get_id() in per_game_bins)

    def _refresh_set_sections(self):
        if self.is_global:
            return
        from launchy.config import get_set_config, _expand_with_deps
        gcfg = self._global_config or {}
        set_order = gcfg.get("sets", [])
        all_enabled = _expand_with_deps(self._explicit_set_ids, set_order)
        active_sets = []  # [(sid, sc), ...] highest priority first
        for sid in set_order:
            if sid in all_enabled:
                try:
                    active_sets.append((sid, get_set_config(sid)))
                except Exception:
                    pass

        _TOOLTIP_SET = "Contributed by active sets — not editable here"

        # Env — one group per set inside a single collapsible
        self._clear_slot(self._set_env_slot)
        self._set_env_display_rows = []
        claimed_keys: set = set()
        per_game_keys = {r.get_key().strip() for r in self._env_rows}
        env_groups = []
        for sid, sc in active_sets:
            sc_env = {k: str(v) for k, v in sc.get("env", {}).items()}
            visible = {k: v for k, v in sc_env.items() if k not in claimed_keys}
            claimed_keys.update(sc_env.keys())
            if not visible:
                continue
            lb = self._make_listbox()
            for k, v in visible.items():
                row = _ReadOnlyKVRow(key=k, value=v, tooltip=_TOOLTIP_SET, overridden=(k in per_game_keys))
                self._set_env_display_rows.append(row)
                lb.append(row)
            env_groups.append((sc.get("general", {}).get("name", "Unnamed Set"), lb))
        if env_groups:
            self._set_env_slot.append(self._make_collapsible_multi("Sets", env_groups))

        # Wrappers — one group per set inside a single collapsible
        self._clear_slot(self._set_wrappers_slot)
        self._set_wrappers_display_rows = []
        claimed_bins: set = set()
        per_game_bins = {r.get_command().strip() for r in self._wrapper_rows}
        wrapper_groups = []
        for sid, sc in active_sets:
            wrappers = []
            for w in sc.get("wrappers", []):
                b = w.split()[0] if w.strip() else w
                if b not in claimed_bins:
                    wrappers.append(w)
                    claimed_bins.add(b)
            if not wrappers:
                continue
            lb = self._make_listbox()
            for w in wrappers:
                b = w.split()[0] if w.strip() else w
                row = _ReadOnlyListRow(value=w, row_id=b, tooltip=_TOOLTIP_SET, overridden=(b in per_game_bins))
                self._set_wrappers_display_rows.append(row)
                lb.append(row)
            wrapper_groups.append((sc.get("general", {}).get("name", "Unnamed Set"), lb))
        if wrapper_groups:
            self._set_wrappers_slot.append(self._make_collapsible_multi("Sets", wrapper_groups))

        # Args — one group per set inside a single collapsible
        self._clear_slot(self._set_args_slot)
        args_groups = []
        for sid, sc in active_sets:
            args = [str(a) for a in sc.get("args", [])]
            if not args:
                continue
            lb = self._make_listbox()
            for a in args:
                lb.append(_ReadOnlyListRow(value=a, tooltip=_TOOLTIP_SET))
            args_groups.append((sc.get("general", {}).get("name", "Unnamed Set"), lb))
        if args_groups:
            self._set_args_slot.append(self._make_collapsible_multi("Sets", args_groups))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save(self, _btn):
        cfg = dict(self._config)

        if "general" not in cfg:
            cfg["general"] = {}

        gw = self._general_widgets
        if self.is_global and "countdown_spin" in gw:
            cfg["general"]["countdown"] = int(gw["countdown_spin"].get_value())

        idx = gw["proton_row"].get_selected()
        if not self.is_global:
            if idx == 0:
                cfg["general"]["proton"] = ""
            elif 1 <= idx <= len(self._proton_versions):
                cfg["general"]["proton"] = self._proton_versions[idx - 1]["id"]
            if "skip_row" in gw:
                cfg["general"]["skip_countdown"] = gw["skip_row"].get_active()
        else:
            if 0 <= idx < len(self._proton_versions):
                cfg["general"]["proton"] = self._proton_versions[idx]["id"]

        env: dict = {}
        for row in self._env_rows:
            k = row.get_key().strip()
            v = row.get_value()
            if k:
                env[k] = v
        cfg["env"] = env

        wrappers = []
        for r in self._wrapper_rows:
            cmd = r.get_command().strip()
            if cmd:
                args = r.get_args().strip()
                wrappers.append(f"{cmd} {args}".strip())
        cfg["wrappers"] = wrappers

        args_list = [r.get_value().strip() for r in self._arg_rows if r.get_value().strip()]
        cfg["args"] = args_list

        if self.is_global:
            save_global_config(cfg)
        else:
            ignore_env = [r.get_id() for r in self._global_env_rows if r.is_ignored()]
            ignore_wrappers = [r.get_id() for r in self._global_wrapper_rows if r.is_ignored()]
            ignore_args = [r.get_id() for r in self._global_arg_rows if r.is_ignored()]
            cfg["global_ignore"] = {
                "env": ignore_env,
                "wrappers": ignore_wrappers,
                "args": ignore_args,
            }
            cfg["sets"] = [r.set_id for r in self._set_rows if r.is_enabled()]
            save_game_config(self.appid, cfg)

        if self._on_saved_cb:
            self._on_saved_cb()
        self.close()


# ---------------------------------------------------------------------------
# Row widgets
# ---------------------------------------------------------------------------

_TOOLTIP_STEAM = "Inherited from Steam launch options — not editable here"
_TOOLTIP_GLOBAL = "Inherited from global settings — not editable here"


def _apply_strikethrough(labels: list, strike: bool):
    attrs = Pango.AttrList()
    if strike:
        attrs.insert(Pango.attr_strikethrough_new(True))
    for lbl in labels:
        lbl.set_attributes(attrs)


class _ReadOnlyKVRow(Gtk.ListBoxRow):
    def __init__(self, *, key: str, value: str, tooltip: str = _TOOLTIP_STEAM,
                 has_ignore: bool = False, ignored: bool = False, overridden: bool = False):
        super().__init__()
        self.set_activatable(False)
        self._key_str = key
        self._overridden = overridden
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        self.set_child(box)

        content_lbl = Gtk.Label(label=f"{key} = {value}")
        content_lbl.add_css_class("dim-label")
        content_lbl.set_selectable(True)
        content_lbl.set_hexpand(True)
        content_lbl.set_halign(Gtk.Align.START)
        content_lbl.set_xalign(0.0)
        content_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        content_lbl.set_tooltip_text(f"{key} = {value}")

        self._labels = [content_lbl]
        box.append(content_lbl)

        if has_ignore and not overridden:
            self._checkbox = Gtk.CheckButton(label="Exclude")
            self._checkbox.set_active(ignored)
            self._checkbox.connect("toggled", lambda _: self._update_appearance())
            box.append(self._checkbox)
        else:
            self._checkbox = None

        info_btn = Gtk.Button(icon_name="dialog-information-symbolic")
        info_btn.add_css_class("flat")
        info_btn.add_css_class("circular")
        info_btn.set_tooltip_text(
            "Overridden by your per-game setting below" if overridden else tooltip
        )
        box.append(info_btn)

        self._update_appearance()

    def _update_appearance(self):
        strike = self._overridden or (self._checkbox is not None and self._checkbox.get_active())
        _apply_strikethrough(self._labels, strike)

    def set_overridden(self, flag: bool):
        self._overridden = flag
        self._update_appearance()

    def get_id(self) -> str:
        return self._key_str

    def is_ignored(self) -> bool:
        return self._checkbox is not None and self._checkbox.get_active()


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
        self._key.set_width_chars(20)

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

    def connect_key_changed(self, callback):
        self._key.connect("changed", lambda _: callback())

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

        self._up = Gtk.Button(icon_name="go-up-symbolic")
        self._up.add_css_class("flat")
        self._up.add_css_class("circular")

        self._down = Gtk.Button(icon_name="go-down-symbolic")
        self._down.add_css_class("flat")
        self._down.add_css_class("circular")

        self._rm = Gtk.Button(icon_name="list-remove-symbolic")
        self._rm.add_css_class("flat")
        self._rm.add_css_class("circular")

        box.append(self._cmd)
        box.append(sep)
        box.append(self._args)
        box.append(self._up)
        box.append(self._down)
        box.append(self._rm)

    def connect_remove(self, callback):
        self._rm.connect("clicked", lambda _: callback(self))

    def connect_command_changed(self, callback):
        self._cmd.connect("changed", lambda _: callback())

    def connect_move(self, rows: list, listbox: Gtk.ListBox):
        def _move(delta):
            idx = rows.index(self)
            new_idx = idx + delta
            if 0 <= new_idx < len(rows):
                rows.pop(idx)
                listbox.remove(self)
                rows.insert(new_idx, self)
                listbox.insert(self, new_idx)
        self._up.connect("clicked", lambda _: _move(-1))
        self._down.connect("clicked", lambda _: _move(1))

    def get_command(self) -> str:
        return self._cmd.get_text()

    def get_args(self) -> str:
        return self._args.get_text()


class _ReadOnlyListRow(Gtk.ListBoxRow):
    def __init__(self, *, value: str, row_id: str = None, tooltip: str = _TOOLTIP_STEAM,
                 has_ignore: bool = False, ignored: bool = False, overridden: bool = False):
        super().__init__()
        self.set_activatable(False)
        self._id = row_id if row_id is not None else value
        self._overridden = overridden
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        self.set_child(box)

        val_lbl = Gtk.Label(label=value)
        val_lbl.add_css_class("dim-label")
        val_lbl.set_selectable(True)
        val_lbl.set_hexpand(True)
        val_lbl.set_halign(Gtk.Align.START)
        val_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        val_lbl.set_tooltip_text(value)

        self._val_lbl = val_lbl
        box.append(val_lbl)

        if has_ignore and not overridden:
            self._checkbox = Gtk.CheckButton(label="Exclude")
            self._checkbox.set_active(ignored)
            self._checkbox.connect("toggled", lambda _: self._update_appearance())
            box.append(self._checkbox)
        else:
            self._checkbox = None

        info_btn = Gtk.Button(icon_name="dialog-information-symbolic")
        info_btn.add_css_class("flat")
        info_btn.add_css_class("circular")
        info_btn.set_tooltip_text(
            "Overridden by your per-game setting below" if overridden else tooltip
        )
        box.append(info_btn)

        self._update_appearance()

    def _update_appearance(self):
        strike = self._overridden or (self._checkbox is not None and self._checkbox.get_active())
        _apply_strikethrough([self._val_lbl], strike)

    def set_overridden(self, flag: bool):
        self._overridden = flag
        self._update_appearance()

    def get_id(self) -> str:
        return self._id

    def is_ignored(self) -> bool:
        return self._checkbox is not None and self._checkbox.get_active()


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

        self._up = Gtk.Button(icon_name="go-up-symbolic")
        self._up.add_css_class("flat")
        self._up.add_css_class("circular")

        self._down = Gtk.Button(icon_name="go-down-symbolic")
        self._down.add_css_class("flat")
        self._down.add_css_class("circular")

        self._rm = Gtk.Button(icon_name="list-remove-symbolic")
        self._rm.add_css_class("flat")
        self._rm.add_css_class("circular")

        box.append(self._val)
        box.append(self._up)
        box.append(self._down)
        box.append(self._rm)

    def connect_remove(self, callback):
        self._rm.connect("clicked", lambda _: callback(self))

    def connect_move(self, rows: list, listbox: Gtk.ListBox):
        def _move(delta):
            idx = rows.index(self)
            new_idx = idx + delta
            if 0 <= new_idx < len(rows):
                rows.pop(idx)
                listbox.remove(self)
                rows.insert(new_idx, self)
                listbox.insert(self, new_idx)
        self._up.connect("clicked", lambda _: _move(-1))
        self._down.connect("clicked", lambda _: _move(1))

    def get_value(self) -> str:
        return self._val.get_text()


class _GlobalSetRow(Gtk.ListBoxRow):
    """Row in global settings Sets tab — shows name with edit/reorder/delete buttons."""
    def __init__(self, *, set_id: str, name: str):
        super().__init__()
        self.set_id = set_id
        self.set_activatable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        self.set_child(box)

        self._name_lbl = Gtk.Label(label=name)
        self._name_lbl.set_hexpand(True)
        self._name_lbl.set_halign(Gtk.Align.START)
        self._name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(self._name_lbl)

        self._edit_btn = Gtk.Button(icon_name="document-edit-symbolic")
        self._edit_btn.add_css_class("flat")
        self._edit_btn.add_css_class("circular")
        self._edit_btn.set_tooltip_text("Edit set")

        self._up_btn = Gtk.Button(icon_name="go-up-symbolic")
        self._up_btn.add_css_class("flat")
        self._up_btn.add_css_class("circular")
        self._up_btn.set_tooltip_text("Move up (increase priority)")

        self._down_btn = Gtk.Button(icon_name="go-down-symbolic")
        self._down_btn.add_css_class("flat")
        self._down_btn.add_css_class("circular")
        self._down_btn.set_tooltip_text("Move down (decrease priority)")

        self._del_btn = Gtk.Button(icon_name="list-remove-symbolic")
        self._del_btn.add_css_class("flat")
        self._del_btn.add_css_class("circular")
        self._del_btn.set_tooltip_text("Delete set")

        for btn in (self._edit_btn, self._up_btn, self._down_btn, self._del_btn):
            box.append(btn)

    def update_name(self, name: str):
        self._name_lbl.set_label(name)

    def connect_edit(self, callback):
        self._edit_btn.connect("clicked", lambda _: callback(self))

    def connect_delete(self, callback):
        self._del_btn.connect("clicked", lambda _: callback(self))

    def connect_move(self, rows: list, listbox: Gtk.ListBox, on_reorder):
        def _move(delta):
            idx = rows.index(self)
            new_idx = idx + delta
            if 0 <= new_idx < len(rows):
                rows.pop(idx)
                listbox.remove(self)
                rows.insert(new_idx, self)
                listbox.insert(self, new_idx)
                on_reorder()
        self._up_btn.connect("clicked", lambda _: _move(-1))
        self._down_btn.connect("clicked", lambda _: _move(1))


class _GameSetRow(Gtk.ListBoxRow):
    """Row in per-game Sets tab — shows name with enable/disable checkbox."""
    def __init__(self, *, set_id: str, name: str, enabled: bool, required_by: list = None):
        super().__init__()
        self.set_id = set_id
        self._implicit = bool(required_by)
        self._explicitly_enabled = enabled
        self.set_activatable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        self.set_child(box)

        lbl = Gtk.Label(label=name)
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(lbl)

        self._check = Gtk.CheckButton(label="Enable")
        if required_by:
            self._check.set_active(True)
            self._check.set_sensitive(False)
            self._check.set_tooltip_text("Required by " + ", ".join(required_by))
        else:
            self._check.set_active(enabled)
        box.append(self._check)

    def connect_toggled(self, callback):
        if not self._implicit:
            self._check.connect("toggled", callback)

    def is_enabled(self) -> bool:
        return self._explicitly_enabled if self._implicit else self._check.get_active()
