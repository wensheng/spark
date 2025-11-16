# Spark Kit

**Spark Spec CLI**

If spark is installed with pip, use:

    spark-spec 

Otherwise:

    python -m spark.kit.spec_cli

Generate a minimal spec:

    python -m spark.kit.spec_cli generate "Echo pipeline" -o out.json 

Compile to code:

    python -m spark.kit.spec_cli compile out.json -o gen/

This writes gen/spark_generated_graph.py

Validate any spec:

    python -m spark.kit.spec_cli validate out.json

Export from a Python graph (example pattern):

    python -m spark.kit.spec_cli export spark_package.examples.e003_simple_flow:main
    
adjust to a graph factory that returns Graph

**Governance helpers**

List pending approvals from a persisted GraphState (JSON or SQLite):

    python -m spark.kit.spec_cli approval-list --state run_state.json --status pending

Resolve an approval request:

    python -m spark.kit.spec_cli approval-resolve ap-123 --state run_state.json --status approved --reviewer ops

Scaffold and validate policy sets:

    python -m spark.kit.spec_cli policy-generate --name mission.policies -o policies.json
    python -m spark.kit.spec_cli policy-validate policies.json
    python -m spark.kit.spec_cli policy-diff old.json new.json

**Simulation harness**

Execute mission specs against simulated tools (static responses or custom handlers):

    python -m spark.kit.spec_cli simulation-run mission.json --format json

Provide alternate overrides via `--simulation-config overrides.json` or add inputs with `--inputs payload.json`.

Compare two simulation transcripts for drift:

    python -m spark.kit.spec_cli simulation-diff baseline.json candidate.json
