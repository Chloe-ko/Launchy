import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GdkPixbuf, Pango  # type: ignore

from pathlib import Path


class LaunchApplication(Adw.Application):
    def __init__(self, *, appid: str, game_cmd: list, game_info: dict, config: dict):
        from gi.repository import Gio
        super().__init__(
            application_id="io.github.launchy.Launchy",
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
        self.set_default_size(640, -1)
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
        toolbar.add_top_bar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        toolbar.set_content(root)

        # ── image + info row ──────────────────────────────────────────
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        top.set_margin_start(16)
        top.set_margin_end(16)
        top.set_margin_top(16)
        top.set_margin_bottom(12)
        root.append(top)

        top.append(self._make_image())

        info = self._make_info()
        info.set_hexpand(True)
        top.append(info)

        # ── countdown ─────────────────────────────────────────────────
        self._cd_sep = Gtk.Separator()
        root.append(self._cd_sep)
        self._cd_box = self._make_countdown()
        root.append(self._cd_box)

        # ── buttons ───────────────────────────────────────────────────
        root.append(Gtk.Separator())
        root.append(self._make_buttons())

    def _make_image(self) -> Gtk.Widget:
        W, H = 230, 108
        frame = Gtk.Frame()
        frame.add_css_class("card")
        frame.set_size_request(W, H)

        img_path = self.game_info.get("image_path")
        if img_path and Path(img_path).exists():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(img_path, W, H, True)
                pic = Gtk.Picture.new_for_pixbuf(pb)
                pic.set_content_fit(Gtk.ContentFit.COVER)
                pic.set_size_request(W, H)
                frame.set_child(pic)
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
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_valign(Gtk.Align.CENTER)

        proton = self.config.get("general", {}).get("proton") or "Steam Default"
        prefix = self.game_info.get("prefix") or "N/A"
        game_dir = self.game_info.get("game_dir") or "N/A"

        for label_txt, value_txt, open_dir in [
            ("Proton",   proton,    None),
            ("Prefix",   prefix,    prefix    if prefix   != "N/A" else None),
            ("Game Dir", game_dir,  game_dir  if game_dir != "N/A" else None),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

            lbl = Gtk.Label(label=label_txt + ":")
            lbl.add_css_class("dim-label")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_size_request(68, -1)

            val = Gtk.Label(label=value_txt)
            val.set_halign(Gtk.Align.START)
            val.set_hexpand(True)
            val.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            val.set_selectable(True)
            val.set_tooltip_text(value_txt)

            row.append(lbl)
            row.append(val)

            if open_dir:
                btn = Gtk.Button(icon_name="folder-open-symbolic")
                btn.add_css_class("flat")
                btn.add_css_class("circular")
                btn.set_tooltip_text(f"Open {label_txt} folder")
                btn.connect("clicked", lambda _, d=open_dir: self._open_folder(d))
                row.append(btn)

            box.append(row)

        return box

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

        for btn in (play, game_s, global_s, cancel):
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
        from gi.repository import Gio
        Gio.AppInfo.launch_default_for_uri(f"file://{path}", None)

    def _open_settings(self, is_global: bool):
        self._stop_countdown()
        self._hide_countdown()
        from launchy.ui.settings_window import SettingsWindow
        win = SettingsWindow(appid=self.appid, is_global=is_global)
        win.set_transient_for(self)
        win.set_modal(True)
        win.connect("destroy", self._on_settings_closed)
        win.present()

    def _on_settings_closed(self, _win):
        from launchy.config import get_merged_config
        self.config = get_merged_config(self.appid)
        self._countdown_total = max(0, self.config.get("general", {}).get("countdown", 5))
        self._remaining = self._countdown_total
        self._cd_paused = False
        self._cd_pause_btn.set_icon_name("media-playback-pause-symbolic")
        self._refresh_countdown()
        self._show_countdown()
        self._start_countdown()
