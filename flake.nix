
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

          # Avoid double-wrapping Python executables.
          dontWrapGApps = true;

          # Pass GTK wrapper arguments to the Python executable wrapper.
          preFixup = ''
            makeWrapperArgs+=("''${gappsWrapperArgs[@]}")
          '';

          postPatch = ''
            # Preserve Python module paths and GTK environment in
            # Launchy's clean UI subprocess environment.
            substituteInPlace launchy/main.py \
              --replace-fail \
                'env = {k: os.environ[k] for k in _SUBPROCESS_KEEP if k in os.environ}' \
                'env = {**{k: os.environ[k] for k in _SUBPROCESS_KEEP if k in os.environ}, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p), **{k: os.environ[k] for k in ("GI_TYPELIB_PATH", "GIO_EXTRA_MODULES", "GDK_PIXBUF_MODULE_FILE") if k in os.environ}}'

            # Import os for PATH filtering.
            substituteInPlace launchy/install.py \
              --replace-fail \
                'import shutil' \
                'import os; import shutil' \
              --replace-fail \
                'launchy_bin = shutil.which("launchy")' \
                'launchy_bin = shutil.which("launchy", path=os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if p and not p.startswith("/nix/store/")))' \
              --replace-fail \
                'launchy_bin = str(Path(launchy_bin).resolve())' \
                'launchy_bin = launchy_bin'
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
