{
  description = "BlinkScoring ML";
  
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };
  
  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        
        pythonEnv = pkgs.python312.withPackages (ps: with ps; [
          # Data processing
          pandas
          numpy
          
          # ML libraries
          lightgbm
          scikit-learn
          shap
          treelite
          treelite_runtime
          
          # Web & API
          fastapi
          uvicorn
          
          # Database
          sqlalchemy
          psycopg2
          
          # Utils
          requests
          structlog
          python-dotenv
          pip
          
          # Testing
          pytest
          pytest-cov
        ]);
      in
      {
        packages.default = pkgs.stdenv.mkDerivation {
          name = "blinkscoring-ml";
          src = self;
          buildInputs = [ pythonEnv ];
          
          buildPhase = ''
            mkdir -p $out/bin
            mkdir -p $out/lib/blinkscoring-ml
            cp -r * $out/lib/blinkscoring-ml/
          '';
          
          installPhase = ''
            cat > $out/bin/blink-scoring-api <<EOF
            #!${pkgs.bash}/bin/bash
            export PYTHONPATH=$out/lib:$PYTHONPATH
            cd $out/lib/blinkscoring-ml
            exec ${pythonEnv}/bin/python -m uvicorn service_scoring.main:app --host 0.0.0.0 --port \''${PORT:-8000}
            EOF
            
            cat > $out/bin/blink-scoring-cron <<EOF
            #!${pkgs.bash}/bin/bash
            export PYTHONPATH=$out/lib:$PYTHONPATH
            cd $out/lib/blinkscoring-ml
            exec ${pythonEnv}/bin/python -m service_cron.worker
            EOF
            
            cat > $out/bin/blink-scoring-trainer <<EOF
            #!${pkgs.bash}/bin/bash
            export PYTHONPATH=$out/lib:$PYTHONPATH
            cd $out/lib/blinkscoring-ml
            exec ${pythonEnv}/bin/python -m service_trainer.train
            EOF
            
            chmod +x $out/bin/blink-scoring-api
            chmod +x $out/bin/blink-scoring-cron
            chmod +x $out/bin/blink-scoring-trainer
          '';
        };
        
        devShells.default = pkgs.mkShell {
          packages = [ pythonEnv ];
          shellHook = ''
            export PYTHONPATH=$PWD:$PYTHONPATH
            echo "BlinkScoring ML development environment activated"
          '';
        };
      }
    );
} 