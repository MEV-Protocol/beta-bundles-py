{
  mkShell,
  poetry2nix,
  python311,
  python311Packages,
  direnv,
  poetry,
  solc,
  openssl,
  dasel,
}:
  let
    projectDir = poetry2nix.cleanPythonSources { src = ./../..; };
    python = python311;
    pythonPackages = python311Packages;

    overrides = poetry2nix.overrides.withDefaults (final: prev: {
      pyunormalize = prev.pyunormalize.overridePythonAttrs (old: {
        buildInputs = (old.buildInputs or [ ]) ++ [ final.setuptools ];
      });
      yarl = prev.yarl.overridePythonAttrs
        (old: { buildInputs = (old.buildInputs or [ ]) ++ [ final.tomli ]; });
      frozenlist = prev.frozenlist.overridePythonAttrs
        (old: { buildInputs = (old.buildInputs or [ ]) ++ [ final.tomli ]; });
      web3 = prev.web3.overridePythonAttrs
        (old: { buildInputs = (old.buildInputs or [ ]) ++ (with pythonPackages; [ cytoolz toolz ]); });
      });

      devShell = mkShell {
        buildInputs = [
          (poetry2nix.mkPoetryEnv {
            inherit overrides projectDir python;

            editablePackageSources = { mev = projectDir + "/mev"; };
          })

          python
          poetry
          solc

          openssl

          direnv
          dasel
        ];
      };

    app = poetry2nix.mkPoetryApplication {
      inherit overrides projectDir python;

      doCheck = true;
    };
  in
app // { inherit devShell; }
