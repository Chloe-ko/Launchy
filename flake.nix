
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

          # Launchy deliberately starts its GTK UI in a clean subprocess.
          # Preserve the Nix GTK/GObject environment needed by that subprocess.
          postPatch = ''
            substituteInPlace launchy/main.py \
              --replace-fail \
                '"DBUS_SESSION_BUS_ADDRESS",' \
                '"DBUS_SESSION_BUS_ADDRESS", "PYTHONPATH", "GI_TYPELIB_PATH", "GIO_EXTRA_MODULES", "GDK_PIXBUF_MODULE_FILE",'
            substituteInPlace launchy/install.py \
              --replace-fail \
                'launchy_bin = str(Path(launchy_bin).resolve())' \
                'launchy_bin = str(Path(launchy_bin))'
          '';

          # The setuptools build installs the Python package and CLI.
          # Install the desktop integration and application icon separately.
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
