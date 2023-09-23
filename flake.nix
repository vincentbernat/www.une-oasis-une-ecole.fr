{
  inputs = {
    nixpkgs.url = "nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };
  outputs = { self, flake-utils, ... }@inputs:
    flake-utils.lib.eachDefaultSystem (system:
      let
        l = pkgs.lib // builtins;
        pkgs = inputs.nixpkgs.legacyPackages."${system}";
        pythonEnv = pkgs.poetry2nix.mkPoetryEnv {
          projectDir = ./.;
          overrides = pkgs.poetry2nix.overrides.withDefaults (self: super:
            (l.listToAttrs (l.map
              # Many dependencies do not declare explicitely their build tools
              (x: {
                name = x;
                value = super."${x}".overridePythonAttrs (old: {
                  nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ self.setuptools self.flit-core ];
                });
              })
              [
                "commando"
                "fswrap"
                "hyde"
              ]))
          );
        };
        nodeEnv = pkgs.mkYarnModules {
          pname = "www-yarn-modules";
          version = "1.0.0";
          packageJSON = ./package.json;
          yarnLock = ./yarn.lock;
        };
      in
      {
        apps = {
          yarn = {
            type = "app";
            program = "${pkgs.yarn}/bin/yarn";
          };
          poetry = {
            type = "app";
            program = "${pkgs.poetry}/bin/poetry";
          };
        };
        packages = {
          build.optimizeImages =
            # Impure!
            # Optimize SVG, JPG and PNG
            let
              jpegoptim = pkgs.jpegoptim.override { libjpeg = pkgs.mozjpeg; };
              inherit (pkgs) libwebp libavif pngquant;
              inherit (pkgs.nodePackages) svgo;
              svgoConfig = pkgs.writeText "svgo.config.js" ''
                module.exports = {
                  plugins: [
                    {
                      name: 'preset-default',
                      params: {
                        overrides: {
                          cleanupIDs: false,
                        }
                      }
                    }
                  ]
                };
              '';
            in
            pkgs.stdenvNoCC.mkDerivation {
              name = "optimize-images";
              src = <target>;
              buildPhase = ''
                find . -type d -print \
                  | sed "s,^,$out/," \
                  | xargs mkdir -p

                # SVG
                for d in $(find . -type d | grep -Ev './(l|obj)(/|$)'); do
                  find $d -maxdepth 1 -type f -name '*.svg' -print0 \
                    | sort -z \
                    | xargs -r0 -P$(nproc) ${svgo}/bin/svgo --config ${svgoConfig} -o $out/$d -i
                done

                # JPG→WebP
                find . -type f -name '*.jpg' -print0 \
                  | xargs -0 -P$(nproc) -i ${libwebp}/bin/cwebp -q 84 -af '{}' -o $out/'{}'.webp

                # JPG→AVIF
                find . -type f -name '*.jpg' -print0 \
                  | xargs -0 -P$(nproc) -i ${libavif}/bin/avifenc --codec aom --yuv 420 \
                                                                       --ignore-icc \
                                                                       --min 20 --max 25 \
                                                                  '{}' $out/'{}'.avif

                # Optimize JPG
                for d in $(find . -type d); do
                  find $d -maxdepth 1 -type f -name '*.jpg' -print0 \
                    | sort -z \
                    | xargs -r0n3 -P$(nproc) ${jpegoptim}/bin/jpegoptim \
                                                -d $out/$d --max=84 --all-progressive --strip-all
                done

                # Optimize PNG
                find . -type f -name '*.png' -print0 \
                    | xargs -0 -P$(nproc) -i ${pngquant}/bin/pngquant --skip-if-larger --strip \
                                                --quiet -o $out/'{}' '{}' \
                    || [ $? -eq 123 ]

                # PNG→WebP
                find $out -type f -name '*.png' -print0 \
                    | xargs -0 -P$(nproc) -i ${libwebp}/bin/cwebp -z 8 '{}' -o '{}'.webp
              '';
              installPhase = "true";
            };
        };
        devShell = pythonEnv.env.overrideAttrs (oldAttrs: {
          name = "www";
          buildInputs = [
            # Build
            pkgs.git
            pkgs.git-annex
            pkgs.nodejs
            pkgs.openssl
            pkgs.python3Packages.invoke
          ];
          shellHook = ''
            ln -nsf ${nodeEnv}/node_modules node_modules
          '';
        });
      });
}
