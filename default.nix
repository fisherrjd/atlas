{ pkgs ? import
    (fetchTarball {
      name = "jpetrucciani-2026-07-21";
      url = "https://github.com/jpetrucciani/nix/archive/31fe870656eadb142fd1cb18f9d1a2100c1ffe32.tar.gz";
      sha256 = "1k6biif8rcwdn9yqgdlqzp62r5ly5l30sp006gjhcywlq6nzkj49";
    })
    { }

}:
let
  name = "atlas";
  uvEnv = pkgs.uv-nix.mkEnv {
    inherit name; python = pkgs.python313;
    workspaceRoot = pkgs.hax.filterSrc { path = ./.; };
    pyprojectOverrides = final: prev: { };
  };

  tools = with pkgs; {
    cli = [
      jfmt
      nixup
    ];
    bun = [ bun ];
    uv = [ uv uvEnv ];
    scripts = pkgs.lib.attrsets.attrValues scripts;
  };

  scripts = with pkgs; {
    dev = pog {
      name = "dev";
      description = "run backend (:3040) and frontend (:3041) together";
      script = ''
        trap 'kill 0' EXIT INT TERM
        echo "→ api: http://localhost:3040  web: http://localhost:3041"
        python main.py &
        (cd frontend && { [ -d node_modules ] || bun install; } && bun run dev) &
        wait
      '';
    };

    api = pog {
      name = "api";
      description = "run the backend only (uvicorn reload, :3040)";
      script = ''python main.py'';
    };

    web = pog {
      name = "web";
      description = "run the frontend dev server only (:3041)";
      script = ''
        cd frontend || exit 1
        if [ ! -d node_modules ]; then bun install; fi
        bun run dev
      '';
    };

    build = pog {
      name = "build";
      description = "typecheck and build the SPA to frontend/dist";
      script = ''
        cd frontend || exit 1
        if [ ! -d node_modules ]; then bun install; fi
        bun run build
      '';
    };

    serve = pog {
      name = "serve";
      description = "serve the built SPA + api on :3040 (prod mode)";
      script = ''
        if [ ! -d frontend/dist ]; then
          echo "→ No frontend/dist. Building first..."
          ${scripts.build}/bin/build
        fi
        uvicorn atlas.main:app --host 0.0.0.0 --port 3040
      '';
    };

    check = pog {
      name = "check";
      description = "frontend typecheck + backend tests";
      script = ''
        (cd frontend && { [ -d node_modules ] || bun install; } && bun run typecheck)
        pytest
      '';
    };

    sync-now = pog {
      name = "sync-now";
      description = "trigger a github sync against the running api";
      script = ''curl -s -X POST localhost:3040/api/sync | ${jq}/bin/jq'';
    };
  };
  paths = pkgs.lib.flatten [ (builtins.attrValues tools) ];
  env = pkgs.buildEnv {
    inherit name paths; buildInputs = paths;
  };
in
(env.overrideAttrs (_: {
  inherit name;
  NIXUP = "0.0.11";
} // uvEnv.uvEnvVars)) // { inherit scripts; }
