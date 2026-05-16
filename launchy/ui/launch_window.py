import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk, GdkPixbuf, Pango  # type: ignore

from pathlib import Path


class LaunchApplication(Adw.Application):
    def __init__(self, *, appid: str, game_cmd: list, game_info: dict, config: dict):
        from gi.repository import Gio
        GLib.set_prgname("launchy")
        super().__init__(
            application_id=None,
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.appid = appid
        self.game_cmd = game_cmd
        self.game_info = game_info
        self.config = config
        self.result = "cancel"
        self.window_shown = False
        self.connect("activate", self._on_activate)

    def _on_activate(self, _app):
        win = LaunchWindow(
            application=self,
            appid=self.appid,
            game_info=self.game_info,
            config=self.config,
        )
        win.present()
        self.window_shown = True

    def do_launch(self):
        self.result = "launch"
        self.quit()

    def do_cancel(self):
        self.result = "cancel"
        self.quit()


class LaunchWindow(Adw.ApplicationWindow):
    def __init__(self, *, application, appid: str, game_info: dict, config: dict):
        super().__init__(application=application)
        self.appid = appid
        self.game_info = game_info
        self.config = config
        self._countdown_total = max(0, config.get("general", {}).get("countdown", 5))
        self._remaining = self._countdown_total
        self._timer_id = None
        self._cd_paused = False

        self.set_title("Launchy")
        self.set_default_size(1000, 650)
        self.set_resizable(False)

        self._build_ui()
        self._start_countdown()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()
        name = self.game_info.get("name") or f"App {self.appid}"
        header.set_title_widget(
            Adw.WindowTitle(title=name, subtitle=f"Steam App {self.appid}")
        )
        logo_path = Path(__file__).parent.parent / "logo.svg"
        if logo_path.exists():
            try:
                logo_pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(logo_path), 128, 128, True)
                logo_img = Gtk.Image.new_from_pixbuf(logo_pb)
                logo_img.set_margin_start(8)
                header.pack_start(logo_img)
            except Exception:
                pass
        toolbar.add_top_bar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        toolbar.set_content(root)

        # Zero-size focus sink: absorbs initial keyboard focus so no button appears pre-highlighted
        dummy = Gtk.Box()
        dummy.set_focusable(True)
        root.append(dummy)

        # ── image + info row ──────────────────────────────────────────
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        top.set_margin_start(16)
        top.set_margin_end(16)
        top.set_margin_top(16)
        top.set_margin_bottom(12)
        root.append(top)

        top.append(self._make_image())

        top.append(self._make_info())

        # ── sets quick-enable ─────────────────────────────────────────
        self._sets_sep = Gtk.Separator()
        root.append(self._sets_sep)
        self._sets_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._sets_box.set_margin_start(16)
        self._sets_box.set_margin_end(16)
        self._sets_box.set_margin_top(10)
        self._sets_box.set_margin_bottom(10)
        root.append(self._sets_box)
        self._refresh_sets_section()

        # ── spacer pushes countdown + buttons to bottom ───────────────
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        root.append(spacer)

        # ── countdown ─────────────────────────────────────────────────
        self._cd_sep = Gtk.Separator()
        root.append(self._cd_sep)
        self._cd_box = self._make_countdown()
        root.append(self._cd_box)

        # ── buttons ───────────────────────────────────────────────────
        root.append(Gtk.Separator())
        root.append(self._make_buttons())

    def _make_image(self) -> Gtk.Widget:
        W, H = 340, 160

        frame = Gtk.Frame()
        frame.add_css_class("card")
        frame.set_size_request(W, H)

        img_path = self.game_info.get("image_path")
        if img_path and Path(img_path).exists():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(img_path, W * 2, H * 2, True)
                pic = Gtk.Picture.new_for_pixbuf(pb)
                pic.set_content_fit(Gtk.ContentFit.COVER)
                pic.set_size_request(W, H)

                overlay = Gtk.Overlay()
                overlay.set_child(pic)

                logo_path = self.game_info.get("logo_path")
                if logo_path and Path(logo_path).exists():
                    try:
                        logo_pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                            logo_path, W // 2, -1, True
                        )
                        logo_pic = Gtk.Picture.new_for_pixbuf(logo_pb)
                        logo_pic.set_can_shrink(False)
                        logo_pic.set_halign(Gtk.Align.START)
                        logo_pic.set_valign(Gtk.Align.END)
                        logo_pic.set_margin_start(6)
                        logo_pic.set_margin_bottom(6)
                        overlay.add_overlay(logo_pic)
                    except Exception:
                        pass

                frame.set_child(overlay)
                return frame
            except Exception:
                pass

        lbl = Gtk.Label(label="No Image")
        lbl.add_css_class("dim-label")
        lbl.set_hexpand(True)
        lbl.set_vexpand(True)
        frame.set_child(lbl)
        return frame

    def _make_info(self) -> Gtk.Widget:
        from launchy.steam import get_available_proton_versions
        from launchy.config import get_global_config, get_game_config

        lb = Gtk.ListBox()
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        lb.set_hexpand(True)
        lb.set_valign(Gtk.Align.CENTER)

        def _add_row(content: Gtk.Widget):
            r = Gtk.ListBoxRow()
            r.set_activatable(False)
            content.set_margin_start(12)
            content.set_margin_end(8)
            content.set_margin_top(10)
            content.set_margin_bottom(10)
            r.set_child(content)
            lb.append(r)

        def _key_label(text: str) -> Gtk.Label:
            lbl = Gtk.Label(label=text)
            lbl.add_css_class("dim-label")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(80, -1)
            return lbl

        # ProtonDB
        pdb_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._protondb_lbl = Gtk.Label(label="…")
        self._protondb_lbl.add_css_class("dim-label")
        self._protondb_lbl.set_halign(Gtk.Align.START)
        self._protondb_lbl.set_hexpand(True)
        self._protondb_btn = Gtk.Button(icon_name="link-symbolic")
        self._protondb_btn.add_css_class("flat")
        self._protondb_btn.add_css_class("circular")
        self._protondb_btn.set_tooltip_text("Open on ProtonDB")
        self._protondb_btn.set_sensitive(False)
        self._protondb_btn.connect("clicked", self._open_protondb)
        pdb_box.append(_key_label("ProtonDB:"))
        pdb_box.append(self._protondb_lbl)
        pdb_box.append(self._protondb_btn)
        _add_row(pdb_box)
        self._fetch_protondb()

        # Proton menu button
        self._proton_versions = get_available_proton_versions()
        gcfg = get_global_config()
        global_proton_id = gcfg.get("general", {}).get("proton", "")
        global_proton_name = next(
            (v["name"] for v in self._proton_versions if v["id"] == global_proton_id),
            global_proton_id or "None",
        )
        self._proton_names = [f"Inherit Global: {global_proton_name}"] + [v["name"] for v in self._proton_versions]
        game_cfg = get_game_config(self.appid)
        current_id = game_cfg.get("general", {}).get("proton", "")
        self._proton_idx = next(
            (i + 1 for i, v in enumerate(self._proton_versions) if v["id"] == current_id), 0
        ) if current_id else 0

        self._proton_btn = Gtk.MenuButton()
        self._proton_btn.set_hexpand(True)
        btn_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._proton_sel_lbl = Gtk.Label(label=self._proton_names[self._proton_idx])
        self._proton_sel_lbl.set_hexpand(True)
        self._proton_sel_lbl.set_halign(Gtk.Align.START)
        self._proton_sel_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        btn_inner.append(self._proton_sel_lbl)
        btn_inner.append(Gtk.Image.new_from_icon_name("pan-down-symbolic"))
        self._proton_btn.set_child(btn_inner)

        self._proton_lb = Gtk.ListBox()
        self._proton_lb.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for name in self._proton_names:
            lbrow = Gtk.ListBoxRow()
            lbl = Gtk.Label(label=name)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_margin_start(8)
            lbl.set_margin_end(8)
            lbl.set_margin_top(6)
            lbl.set_margin_bottom(6)
            lbrow.set_child(lbl)
            self._proton_lb.append(lbrow)
        sel_row = self._proton_lb.get_row_at_index(self._proton_idx)
        if sel_row:
            self._proton_lb.select_row(sel_row)
        self._proton_lb.connect("row-activated", self._on_proton_row_activated)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_max_content_height(200)
        scroll.set_propagate_natural_height(True)
        scroll.set_child(self._proton_lb)

        popover = Gtk.Popover()
        popover.set_has_arrow(False)
        popover.set_child(scroll)
        self._proton_btn.set_popover(popover)
        self._proton_btn.connect("notify::active", lambda btn, _: self._on_proton_popup() if btn.get_active() else None)

        proton_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        proton_box.append(_key_label("Proton:"))
        proton_box.append(self._proton_btn)
        _add_row(proton_box)

        # Prefix and Game Dir
        prefix = self.game_info.get("prefix") or "N/A"
        game_dir = self.game_info.get("game_dir") or "N/A"
        for label_txt, value_txt, open_dir in [
            ("Prefix:",   prefix,   prefix   if prefix   != "N/A" else None),
            ("Game Dir:", game_dir, game_dir if game_dir != "N/A" else None),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            val = Gtk.Label(label=value_txt)
            val.set_halign(Gtk.Align.START)
            val.set_hexpand(True)
            val.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            val.set_tooltip_text(value_txt)
            btn = Gtk.Button(icon_name="folder-open-symbolic")
            btn.add_css_class("flat")
            btn.add_css_class("circular")
            if open_dir:
                btn.set_tooltip_text(f"Open {label_txt.rstrip(':')} folder")
                btn.connect("clicked", lambda _, d=open_dir: self._open_folder(d))
            else:
                btn.set_opacity(0)
                btn.set_sensitive(False)
            row.append(_key_label(label_txt))
            row.append(val)
            row.append(btn)
            _add_row(row)

        # Skip countdown
        skip_val = game_cfg.get("general", {}).get("skip_countdown", False)
        skip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._skip_check = Gtk.CheckButton(label="Launch instantly (skip countdown)")
        self._skip_check.set_active(skip_val)
        self._skip_check.set_hexpand(True)
        self._skip_check.connect("toggled", self._on_skip_toggled)
        skip_box.append(_key_label("Launch:"))
        skip_box.append(self._skip_check)
        _add_row(skip_box)

        return lb

    def _fetch_protondb(self):
        import threading
        appid = self.appid

        def _worker():
            try:
                import urllib.request, json
                url = f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json"
                with urllib.request.urlopen(url, timeout=5) as r:
                    tier = json.loads(r.read()).get("tier", "")
            except Exception:
                tier = ""
            GLib.idle_add(self._on_protondb_result, tier)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_protondb_result(self, tier: str):
        _COLORS = {
            "platinum": "#B4C7DC",
            "gold":     "#D4AF37",
            "silver":   "#A8A9AD",
            "bronze":   "#CD7F32",
            "borked":   "#E74C3C",
        }
        if not tier:
            self._protondb_lbl.set_text("N/A")
            return
        color = _COLORS.get(tier.lower())
        display = tier.capitalize()
        if color:
            self._protondb_lbl.set_markup(
                f'<span color="{color}" weight="bold">{display}</span>'
            )
        else:
            self._protondb_lbl.set_text(display)
        self._protondb_btn.set_sensitive(True)

    def _open_protondb(self, _btn):
        from gi.repository import Gio
        Gio.AppInfo.launch_default_for_uri(
            f"https://www.protondb.com/app/{self.appid}", None
        )

    def _refresh_sets_section(self):
        from launchy.config import (
            get_global_config, get_set_config, get_game_config,
            save_game_config, _expand_with_deps,
        )

        children = []
        child = self._sets_box.get_first_child()
        while child is not None:
            children.append(child)
            child = child.get_next_sibling()
        for c in children:
            self._sets_box.remove(c)

        gcfg = get_global_config()
        set_order = gcfg.get("sets", [])

        show_sets = []
        for sid in set_order:
            try:
                scfg = get_set_config(sid)
                if scfg.get("general", {}).get("show_in_launch", False):
                    show_sets.append((sid, scfg.get("general", {}).get("name", "Unnamed Set")))
            except Exception:
                pass

        if not show_sets:
            self._sets_sep.set_visible(False)
            self._sets_box.set_visible(False)
            return

        self._sets_sep.set_visible(True)
        self._sets_box.set_visible(True)

        game_cfg = get_game_config(self.appid)
        explicit_ids = set(game_cfg.get("sets", []))

        # dep_id → names of explicitly-enabled sets that (transitively) require it
        requirers: dict = {}
        for eid in explicit_ids:
            try:
                ename = get_set_config(eid).get("general", {}).get("name", "Unnamed Set")
                for dep_id in _expand_with_deps({eid}, set_order) - {eid}:
                    requirers.setdefault(dep_id, []).append(ename)
            except Exception:
                pass

        lbl = Gtk.Label(label="Sets")
        lbl.add_css_class("heading")
        lbl.set_halign(Gtk.Align.START)
        self._sets_box.append(lbl)

        checks_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        checks_box.set_margin_top(2)
        self._sets_box.append(checks_box)

        for sid, name in show_sets:
            is_explicit = sid in explicit_ids
            check = Gtk.CheckButton(label=name)

            if sid in requirers:
                check.set_active(True)
                check.set_sensitive(False)
                check.set_tooltip_text("Required by " + ", ".join(requirers[sid]))
            else:
                check.set_active(is_explicit)

                def on_toggle(btn, set_id=sid):
                    if not self._cd_paused:
                        self._cd_paused = True
                        self._cd_pause_btn.set_icon_name("media-playback-start-symbolic")
                        self._stop_countdown()
                    gcfg2 = get_game_config(self.appid)
                    cur_enabled = set(gcfg2.get("sets", []))
                    if btn.get_active():
                        cur_enabled.add(set_id)
                    else:
                        cur_enabled.discard(set_id)
                    gcfg2["sets"] = list(cur_enabled)
                    save_game_config(self.appid, gcfg2)
                    self._refresh_sets_section()

                check.connect("toggled", on_toggle)

            checks_box.append(check)

    def _make_countdown(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(12)
        box.set_margin_bottom(12)

        label_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        label_row.set_halign(Gtk.Align.CENTER)

        self._cd_label = Gtk.Label()
        label_row.append(self._cd_label)

        self._cd_pause_btn = Gtk.Button(icon_name="media-playback-pause-symbolic")
        self._cd_pause_btn.add_css_class("flat")
        self._cd_pause_btn.add_css_class("circular")
        self._cd_pause_btn.connect("clicked", lambda _: self._toggle_pause())
        label_row.append(self._cd_pause_btn)

        self._cd_bar = Gtk.ProgressBar()

        box.append(label_row)
        box.append(self._cd_bar)
        self._refresh_countdown()
        return box

    def _make_buttons(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(12)
        box.set_margin_bottom(16)
        box.set_homogeneous(True)

        play = Gtk.Button(label="Play Now")
        play.add_css_class("suggested-action")
        play.connect("clicked", lambda _: self._do_launch())

        game_s = Gtk.Button(label="Game Settings")
        game_s.connect("clicked", lambda _: self._open_settings(is_global=False))

        global_s = Gtk.Button(label="Global Settings")
        global_s.connect("clicked", lambda _: self._open_settings(is_global=True))

        cancel = Gtk.Button(label="Cancel")
        cancel.add_css_class("destructive-action")
        cancel.connect("clicked", lambda _: self._do_cancel())

        for btn in (cancel, game_s, global_s, play):
            box.append(btn)
        return box

    # ------------------------------------------------------------------
    # Countdown logic
    # ------------------------------------------------------------------

    def _start_countdown(self):
        if self._countdown_total > 0:
            self._timer_id = GLib.timeout_add(1000, self._tick)

    def _stop_countdown(self):
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _hide_countdown(self):
        self._cd_sep.set_visible(False)
        self._cd_box.set_visible(False)

    def _show_countdown(self):
        if self._countdown_total > 0:
            self._cd_sep.set_visible(True)
            self._cd_box.set_visible(True)

    def _tick(self) -> bool:
        self._remaining -= 1
        self._refresh_countdown()
        if self._remaining <= 0:
            self._do_launch()
            return False
        return True

    def _refresh_countdown(self):
        total = self._countdown_total
        rem = self._remaining
        if total <= 0:
            self._cd_label.set_text("Ready to launch.")
            self._cd_bar.set_fraction(1.0)
        else:
            s = "second" if rem == 1 else "seconds"
            self._cd_label.set_text(f"Launching in {max(0, rem)} {s}…")
            self._cd_bar.set_fraction(max(0.0, 1.0 - rem / total))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _do_launch(self):
        self._stop_countdown()
        self.get_application().do_launch()

    def _do_cancel(self):
        self._stop_countdown()
        self.get_application().do_cancel()

    def _toggle_pause(self):
        if self._cd_paused:
            self._cd_paused = False
            self._cd_pause_btn.set_icon_name("media-playback-pause-symbolic")
            self._start_countdown()
        else:
            self._cd_paused = True
            self._cd_pause_btn.set_icon_name("media-playback-start-symbolic")
            self._stop_countdown()

    def _open_folder(self, path: str):
        import subprocess
        subprocess.Popen(
            ["xdg-open", path],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _open_settings(self, is_global: bool):
        if not self._cd_paused:
            self._cd_paused = True
            self._cd_pause_btn.set_icon_name("media-playback-start-symbolic")
            self._stop_countdown()
        from launchy.ui.settings_window import SettingsWindow

        def on_saved():
            self._refresh_sets_section()
            if not is_global:
                self._sync_proton_dropdown()

        win = SettingsWindow(appid=self.appid, is_global=is_global, on_saved=on_saved)
        win.set_transient_for(self)
        win.set_modal(True)
        win.connect("destroy", self._on_settings_closed)
        win.present()

    def _sync_proton_dropdown(self):
        from launchy.config import get_global_config, get_game_config
        from launchy.steam import get_available_proton_versions
        self._proton_versions = get_available_proton_versions()
        gcfg = get_global_config()
        global_proton_id = gcfg.get("general", {}).get("proton", "")
        global_proton_name = next(
            (v["name"] for v in self._proton_versions if v["id"] == global_proton_id),
            global_proton_id or "None",
        )
        self._proton_names = [f"Inherit Global: {global_proton_name}"] + [v["name"] for v in self._proton_versions]
        game_cfg = get_game_config(self.appid)
        current_id = game_cfg.get("general", {}).get("proton", "")
        if current_id:
            self._proton_idx = next(
                (i + 1 for i, v in enumerate(self._proton_versions) if v["id"] == current_id), 0
            )
        else:
            self._proton_idx = 0
        self._proton_sel_lbl.set_text(self._proton_names[self._proton_idx])
        children = []
        child = self._proton_lb.get_first_child()
        while child is not None:
            children.append(child)
            child = child.get_next_sibling()
        for c in children:
            self._proton_lb.remove(c)
        for name in self._proton_names:
            lbrow = Gtk.ListBoxRow()
            lbl = Gtk.Label(label=name)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_margin_start(8)
            lbl.set_margin_end(8)
            lbl.set_margin_top(6)
            lbl.set_margin_bottom(6)
            lbrow.set_child(lbl)
            self._proton_lb.append(lbrow)
        sel_row = self._proton_lb.get_row_at_index(self._proton_idx)
        if sel_row:
            self._proton_lb.select_row(sel_row)

    def _on_proton_popup(self):
        if not self._cd_paused:
            self._cd_paused = True
            self._cd_pause_btn.set_icon_name("media-playback-start-symbolic")
            self._stop_countdown()

    def _on_proton_row_activated(self, lb, row):
        self._proton_btn.popdown()
        idx = row.get_index()
        self._proton_idx = idx
        self._proton_sel_lbl.set_text(self._proton_names[idx])
        lb.select_row(row)
        self._on_proton_selected(idx)

    def _on_proton_selected(self, idx: int):
        from launchy.config import get_game_config, save_game_config, get_merged_config
        game_cfg = get_game_config(self.appid)
        if "general" not in game_cfg:
            game_cfg["general"] = {}
        if idx == 0:
            game_cfg["general"]["proton"] = ""
        elif 1 <= idx <= len(self._proton_versions):
            game_cfg["general"]["proton"] = self._proton_versions[idx - 1]["id"]
        save_game_config(self.appid, game_cfg)
        self.config = get_merged_config(self.appid)
        if not self._cd_paused:
            self._cd_paused = True
            self._cd_pause_btn.set_icon_name("media-playback-start-symbolic")
            self._stop_countdown()

    def _on_skip_toggled(self, check):
        from launchy.config import get_game_config, save_game_config
        cfg = get_game_config(self.appid)
        if "general" not in cfg:
            cfg["general"] = {}
        cfg["general"]["skip_countdown"] = check.get_active()
        save_game_config(self.appid, cfg)

    def _on_settings_closed(self, _win):
        from launchy.config import get_merged_config
        self.config = get_merged_config(self.appid)
        self._countdown_total = max(0, self.config.get("general", {}).get("countdown", 5))
        self._remaining = self._countdown_total
        self._refresh_countdown()
