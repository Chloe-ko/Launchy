
{
  description = "Launchy - configurable Steam compatibility tool launcher";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;

      packageFor = system:
        let
          pkgs = import nixpkgs { inherit system; };
          pythonPackages = pkgs.python3Packages;
        in
        pythonPackages.buildPythonApplication {
          pname = "launchy";
          version = "0.1";

          pyproject = true;
          src = self;

          build-system = [
            pythonPackages.setuptools
          ];

          dependencies = [
            pythonPackages.pygobject3
          ];

          nativeBuildInputs = [
            pkgs.gobject-introspection
            pkgs.wrapGAppsHook4
          ];

          buildInputs = [
            pkgs.gtk4
            pkgs.libadwaita
          ];

          # Avoid double-wrapping: let the Python builder handle
          # the executable wrapper, using the GApps arguments.
          dontWrapGApps = true;

          preFixup = ''
            makeWrapperArgs+=("''${gappsWrapperArgs[@]}")
          '';

          postPatch = ''
            # Preserve the Python module search path in Launchy's
            # clean GTK subprocess environment.
            substituteInPlace launchy/main.py \
              --replace-fail \
                'env = {k: os.environ[k] for k in _SUBPROCESS_KEEP if k in os.environ}' \
                'env = {**{k: os.environ[k] for k in _SUBPROCESS_KEEP if k in os.environ}, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}'

            # Pass the GTK/GObject environment into the GTK subprocess.
            substituteInPlace launchy/main.py \
              --replace-fail \
                '"DBUS_SESSION_BUS_ADDRESS",' \
                '"DBUS_SESSION_BUS_ADDRESS", "GI_TYPELIB_PATH", "GIO_EXTRA_MODULES", "GDK_PIXBUF_MODULE_FILE",'

            # Preserve the profile symlink instead of resolving it
            # into the Nix store when registering the Steam tool.
            substituteInPlace launchy/install.py \
              --replace-fail \
                'import shutil' \
                'import os
            import shutil' \
              --replace-fail \
                'launchy_bin = shutil.which("launchy")' \
                'search_path = os.pathsep.join(
                entry for entry in os.environ.get("PATH", "").split(os.pathsep)
                if entry and not entry.startswith("/nix/store/")
            )
            launchy_bin = shutil.which("launchy", path=search_path)' \
              --replace-fail \
                'launchy_bin = str(Path(launchy_bin).resolve())' \
                '# Preserve the profile path returned by shutil.which()'
          '';

          # Install desktop integration and application icon.
          postInstall = ''
            install -Dm644 launchy.desktop \
              $out/share/applications/launchy.desktop

            install -Dm644 launchy/logo.svg \
              $out/share/icons/hicolor/scalable/apps/launchy.svg
          '';

          pythonImportsCheck = [
            "launchy"
          ];

          meta = {
            description = "Configurable Steam compatibility tool launcher with per-game settings";
            homepage = "https://github.com/Chloe-ko/Launchy";
            license = pkgs.lib.licenses.gpl3Only;
            platforms = pkgs.lib.platforms.linux;
            mainProgram = "launchy";
          };
        };
    in
    {
      packages = forAllSystems (system:
        let
          launchy = packageFor system;
        in
        {
          inherit launchy;
          default = launchy;
        }
      );

      apps = forAllSystems (system:
        let
          launchy = packageFor system;
        in
        {
          default = {
            type = "app";
            program = "${launchy}/bin/launchy";
          };
        }
      );
    };
}
