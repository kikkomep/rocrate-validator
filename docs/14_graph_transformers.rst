..
   Copyright (c) 2024-2026 CRS4

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

.. _graph-transformers:

Graph transformers
==================

Graph transformers are an internal preprocessing extension point for cases in
which a SHACL shape needs information that is available in the original
RO-Crate graph but would be lost or become ambiguous after ontology inoculation,
inference, or SHACL rule expansion. They can also add a reusable annotation
which would otherwise have to be recomputed by several expensive SPARQL
targets.

Do not use a transformer for an ordinary validation condition. Prefer SHACL
Core, a SPARQL constraint, or a Python check whenever those can express the
requirement directly. A transformer changes the graph seen by every SHACL
shape, so its output is global to the validation run and requires broader
regression testing.

Execution model
---------------

``prepare_data_graph`` creates one transient copy of the parsed RO-Crate graph,
discovers all modules below ``rocrate_validator.graph_transformers``, and runs
their registered transformers sequentially. The cached source graph is never
passed to a transformer and remains unchanged.

The validator skips this preprocessing when pySHACL is called with
``sparql_mode=True``. Transformer-dependent validation therefore requires the
normal in-memory or serialized-graph validation mode.

Lower ``order`` values run first. Transformers with the same order are sorted
by their fully qualified Python name, so their order is deterministic but
should not be used to encode an implicit dependency. Assign distinct orders
when one transformer consumes triples produced by another.

Every transformer must:

* accept exactly one ``rdflib.Graph``;
* return an ``rdflib.Graph`` (returning ``None`` is an error);
* be deterministic for the same input graph;
* avoid network access and process-global mutable state;
* treat the graph as transient validator state, never as metadata to write back
  to the RO-Crate.

The discovery mechanism covers modules bundled in the
``rocrate_validator.graph_transformers`` package. It is not an entry-point
system for arbitrary profile-local or third-party plugins.

Function transformers
---------------------

Use ``@graph_transformer`` for a stateless transformation that is naturally
expressed as a function:

.. code-block:: python

   from rdflib import Graph

   from rocrate_validator.graph_transformers import graph_transformer


   @graph_transformer(order=50)
   def add_example_annotations(data_graph: Graph) -> Graph:
       # Add annotations to the transient graph.
       ...
       return data_graph

The module does not need to be imported manually. It is imported by discovery
the first time ``prepare_data_graph`` runs.

Class transformers
------------------

Use a ``GraphTransformer`` subclass when the implementation benefits from
private helper methods or a clearer class-level contract:

.. code-block:: python

   from rdflib import Graph

   from rocrate_validator.graph_transformers import GraphTransformer


   class ExampleTransformer(GraphTransformer):
       order = 60

       def transform(self, data_graph: Graph) -> Graph:
           ...
           return data_graph

Every concrete subclass is registered automatically. It must have a no-argument
constructor; a new instance is created for each pipeline execution so state
does not leak between validations. Abstract intermediate subclasses are not
registered.

Private marker predicates and prefixes
--------------------------------------

A transformer may annotate the transient graph with private predicates. Keep
these predicates in the validator-owned namespace
``https://github.com/crs4/rocrate-validator/graph-transformers/`` and define
their RDFLib vocabulary terms in ``graph_transformers/vocabulary.py``. These triples
are implementation details: they must not be serialized into an RO-Crate or
presented as vocabulary terms owned by the crate.

When a SHACL query consumes a marker, declare the namespace in the profile's
shared ``sh:prefixes`` block. For example:

.. code-block:: turtle

   sh:declare [
       sh:prefix "validator-transformers" ;
       sh:namespace
           "https://github.com/crs4/rocrate-validator/graph-transformers/"^^xsd:anyURI ;
   ] .

The query can then select only nodes annotated before pySHACL expands the
graph:

.. code-block:: sparql

   FILTER EXISTS {
       ?this validator-transformers:validationCandidate true
   }

Testing a transformer
---------------------

Add unit tests for the transformation itself and integration tests for every
SHACL target which consumes its output. At minimum, verify that:

* the source graph is unchanged;
* consecutive transformers see their predecessors' output;
* ordering is explicit when transformers depend on each other;
* ontology and inference triples do not accidentally enter the intended scope;
* representative large graphs remain within the project's performance budget.
