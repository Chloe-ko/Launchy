PYTHON      ?= python3
PREFIX      ?= $(HOME)/.local
BINDIR      := $(PREFIX)/bin
PY_VER      := $(shell $(PYTHON) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
SITE_PKGS   := $(PREFIX)/lib/python$(PY_VER)/site-packages

.PHONY: install uninstall install-compat uninstall-compat

install:
	install -d "$(SITE_PKGS)/launchy/ui"
	install -m644 launchy/__init__.py launchy/__main__.py launchy/config.py launchy/install.py \
		launchy/main.py launchy/steam.py launchy/utils.py launchy/logo.svg \
		"$(SITE_PKGS)/launchy/"
	install -m644 launchy/ui/__init__.py launchy/ui/launch_window.py \
		launchy/ui/settings_window.py launchy/ui/set_window.py \
		"$(SITE_PKGS)/launchy/ui/"
	install -Dm755 bin/launchy "$(BINDIR)/launchy"
	install -Dm644 launchy/logo.svg "$(PREFIX)/share/icons/hicolor/scalable/apps/launchy.svg"
	install -Dm644 launchy.desktop "$(PREFIX)/share/applications/launchy.desktop"
	@echo ""
	@echo "Installed to $(PREFIX)."
	@echo "Make sure $(BINDIR) is in your PATH, then run: launchy install"

uninstall:
	-launchy uninstall
	rm -rf "$(SITE_PKGS)/launchy"
	rm -f  "$(BINDIR)/launchy"
	rm -f  "$(PREFIX)/share/icons/hicolor/scalable/apps/launchy.svg"
	rm -f  "$(PREFIX)/share/applications/launchy.desktop"
	@echo "Uninstalled from $(PREFIX)."

# Register / deregister with Steam (separate step)
install-compat:
	launchy install

uninstall-compat:
	launchy uninstall
