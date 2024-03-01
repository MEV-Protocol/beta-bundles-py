{
  lib,
  mkShell,
  poetry2nix,
  python311,
  python311Packages,
  direnv,
  poetry,
  solc,
  openssl,
}:
  let
    projectDir = poetry2nix.cleanPythonSources { src = ./../..; };
    python = python311;
    pythonPackages = python.pkgs;

    overrides = poetry2nix.overrides.withDefaults (final: prev: {
      pyunormalize = prev.pyunormalize.overridePythonAttrs (old: {
        buildInputs = (old.buildInputs or [ ]) ++ [ final.setuptools ];
      });
      yarl = prev.yarl.overridePythonAttrs
        (old: { buildInputs = (old.buildInputs or [ ]) ++ [ final.tomli ]; });
      frozenlist = prev.frozenlist.overridePythonAttrs
        (old: { buildInputs = (old.buildInputs or [ ]) ++ [ final.tomli ]; });
      web3 = prev.web3.overridePythonAttrs
        (old: { buildInputs = (old.buildInputs or [ ]) ++ [ pythonPackages.toolz pythonPackages.cytoolz ]; });
      });

      devShell = mkShell {
        buildInputs = [
          (poetry2nix.mkPoetryEnv {
            inherit overrides projectDir python;

            editablePackageSources = { beta_bundles_py = projectDir + "/beta_bundles_py"; };
          })

          python
          poetry

          openssl
        ];
      };

    app = poetry2nix.mkPoetryApplication {
      inherit overrides projectDir python;

      doCheck = true;
    };
  in
app // { inherit devShell; }
