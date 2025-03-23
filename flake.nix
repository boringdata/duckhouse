{
  description = "A devShell for uv using uv2nix";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    pre-commit-hooks = {
      url = "github:cachix/pre-commit-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs = {
        pyproject-nix.follows = "pyproject-nix";
        nixpkgs.follows = "nixpkgs";
      };
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs = {
        pyproject-nix.follows = "pyproject-nix";
        uv2nix.follows = "uv2nix";
        nixpkgs.follows = "nixpkgs";
      };
    };
  };

  outputs = { self, nixpkgs, flake-utils, pre-commit-hooks, pyproject-nix, uv2nix, pyproject-build-systems, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };

        # Load a uv workspace from workspace root
        workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

        # Create package overlay from workspace
        overlay = workspace.mkPyprojectOverlay {
          sourcePreference = "wheel";
        };

        pyprojectOverrides = final: prev: {
          # Override for cityhash to add setuptools
          cityhash = prev.cityhash.overrideAttrs (old: {
            nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ final.resolveBuildSystem {
              setuptools = [ ];
              wheel = [ ];
            };
          });

          # Since xorq might depend on cityhash, add override for it too
          xorq = prev.xorq.overrideAttrs (old: {
            nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ final.resolveBuildSystem {
              setuptools = [ ];
              wheel = [ ];
            };

            # Add buildInputs if there are C dependencies
            buildInputs = (old.buildInputs or [ ]) ++ [
              pkgs.openssl
            ];
          });
        };

        # Python version to use
        python = pkgs.python312;

        # Construct the Python package set
        pythonSet =
          (pkgs.callPackage pyproject-nix.build.packages {
            inherit python;
          }).overrideScope
            (
              pkgs.lib.composeManyExtensions [
                pyproject-build-systems.overlays.default
                overlay
                pyprojectOverrides
              ]
            );

        # Create an editable overlay for development
        editableOverlay = workspace.mkEditablePyprojectOverlay {
          root = "$REPO_ROOT";
        };

        # Package set with editable packages
        editablePythonSet = pythonSet.overrideScope editableOverlay;

        # Virtual environments
        venv = pythonSet.mkVirtualEnv "uv-venv" workspace.deps.default;
        venv-editable = editablePythonSet.mkVirtualEnv "uv-editable-venv" workspace.deps.all;

        # Pre-commit hooks
        pre-commit-check = pre-commit-hooks.lib.${system}.run {
          src = ./.;
          hooks = {
            nixpkgs-fmt.enable = true;
            ruff = {
              enable = true;
              files = "\\.py$";
              excludes = [ ];
            };
          };
          tools = {
            inherit (pkgs) ruff;
          };
        };
      in
      {
        apps = rec {
          ipython = {
            type = "app";
            program = "${venv}/bin/ipython";
          };
          default = ipython;
        };

        packages = {
          default = venv;
        };

        devShells = {
          default = self.devShells.${system}.editable;

          # Standard environment with prebuilt packages
          standard = pkgs.mkShell {
            packages = [
              venv
              pkgs.uv
            ];
            shellHook = ''
              echo "DEBUG: Entered standard shell with prebuilt packages"
              unset PYTHONPATH
              export UV_NO_SYNC=1
              export UV_PYTHON="${venv}/bin/python"
              export UV_PYTHON_DOWNLOADS=never
              ${pre-commit-check.shellHook}
            '';
          };

          # Editable environment for development
          editable = pkgs.mkShell {
            packages = [
              venv-editable
              pkgs.uv
            ];
            shellHook = ''
              echo "DEBUG: Entered editable shell"
              unset PYTHONPATH
              export UV_NO_SYNC=1
              export UV_PYTHON="${venv-editable}/bin/python"
              export UV_PYTHON_DOWNLOADS=never
              export REPO_ROOT=$(git rev-parse --show-toplevel)
              ${pre-commit-check.shellHook}
            '';
          };

          # Impure shell that just provides Python and uv
          impure = pkgs.mkShell {
            packages = [
              python
              pkgs.uv
            ];
            shellHook = ''
              echo "DEBUG: Entered impure shell"
              unset PYTHONPATH
              export UV_PYTHON_DOWNLOADS=never
              export UV_PYTHON="${python}/bin/python"
            '';
          };
        };
      });
}
