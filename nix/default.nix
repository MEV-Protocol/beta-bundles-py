{ ... }: {
  perSystem = { pkgs, ... }:
    let app = pkgs.callPackage ./pkgs/beta-bundles.nix { };
    in {
      packages = {
        default = app;

        beta-bundles-py = app;
        docker-beta-bundles-py = app.docker;
      };

      devShells.default = app.devShell;

      treefmt = {
        projectRootFile = ../flake.nix;

        programs.black.enable = true;
        programs.nixfmt.enable = true;
      };
    };
}

