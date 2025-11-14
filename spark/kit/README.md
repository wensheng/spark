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
