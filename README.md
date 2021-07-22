# OntoEnv

OntoEnv is a simple tool for managing a collection of ontology definitions (instances of `owl:Ontology`) and dependencies (`owl:imports` statements). This is functionality that is often provided by modeling IDEs such as [Protégé](https://protege.stanford.edu/) and [TopBraid Composer](https://www.topquadrant.com/products/topbraid-composer/), but seems currently lacking in the Python/RDFlib ecosystem. Once initialized in a directory, OntoEnv will search for all RDF files and resolve their `owl:imports` statements, downloading remote files or resolving from local definitions as needed.

OntoEnv provides Python bindings which will import the ontology definitions for all `owl:imports` statements into an `rdflib.Graph`.

## Typical Usage

Typical usage looks as follows.

First, tell OntoEnv to figure out the dependency graph and cache the ontology/graph definitions.

```bash
$ ontoenv init # resolving imports can take a few seconds, depending on the number of dependencies
$ ontoenv refresh # run 'refresh' if any dependencies change
```

Then, use the Python bindings to import ontology definitions into a graph

```python
import rdflib
import ontoenv

# initialize environment
env = ontoenv.OntoEnv()

g = rdflib.Graph()
g.parse("my_graph.ttl", format="ttl")
env.import_dependencies(g)
```

Other commands:
- `dump`: print the locations of all URIs known by `ontoenv`

The `deps` command will print a tree of imports for a particular file or URI:

```
% ontoenv deps /home/gabe/src/223p/223standard/data/sample.ttl
Bolded values are duplicate imports whose deps are listed elsewhere in the tree
/home/gabe/src/223p/223standard/data/sample.ttl
|  ┝ http://data.ashrae.org/standard223/1.0/model/all
|  |  ┝ http://data.ashrae.org/standard223/1.0/vocab/role
|  |  |  ┝ http://www.w3.org/ns/shacl#
|  |  |  ┕ http://data.ashrae.org/standard223/1.0/model/core
|  |  |  |  ┝ http://www.w3.org/ns/shacl#
|  |  |  |  ┝ http://www.w3.org/ns/sosa/
|  |  |  |  ┝ http://qudt.org/2.1/vocab/unit
|  |  |  |  |  ┝ http://qudt.org/2.1/vocab/prefix
|  |  |  |  |  |  ┕ http://qudt.org/2.1/schema/qudt
|  |  |  |  |  |  |  ┝ http://www.w3.org/2004/02/skos/core
|  |  |  |  |  |  |  ┝ http://qudt.org/2.1/schema/extensions/imports
|  |  |  |  |  |  |  |  ┕ http://qudt.org/2.1/schema/extensions/functions
|  |  |  |  |  |  |  |  |  ┕ http://spinrdf.org/spl
|  |  |  |  |  |  |  |  |  |  ┕ http://spinrdf.org/spin
|  |  |  |  |  |  |  |  |  |  |  ┕ http://spinrdf.org/sp
|  |  |  |  |  |  |  ┝ http://www.linkedmodel.org/schema/vaem
|  |  |  |  |  |  |  ┕ http://www.linkedmodel.org/schema/dtype
|  |  |  |  |  |  |  |  ┕ http://www.linkedmodel.org/schema/vaem
|  |  |  |  |  ┝ http://qudt.org/2.1/schema/qudt
|  |  |  |  |  ┝ http://qudt.org/2.1/vocab/quantitykind
|  |  |  |  |  |  ┝ http://qudt.org/2.1/vocab/dimensionvector
|  |  |  |  |  |  |  ┕ http://qudt.org/2.1/schema/qudt
|  |  |  |  |  |  ┕ http://qudt.org/2.1/schema/qudt
|  |  |  |  |  ┕ http://qudt.org/2.1/vocab/sou
|  |  |  |  |  |  ┕ http://qudt.org/2.1/schema/qudt
|  |  |  |  ┝ http://data.ashrae.org/standard223/1.0/extensions/settings
|  |  |  |  |  ┝ http://data.ashrae.org/standard223/1.0/validation/schema
|  |  |  |  |  |  ┝ http://data.ashrae.org/standard223/1.0/model/all
|  |  |  |  |  |  ┕ http://www.w3.org/ns/shacl#
|  |  |  |  |  ┝ http://data.ashrae.org/standard223/1.0/validation/data
|  |  |  |  |  |  ┝ http://data.ashrae.org/standard223/1.0/model/all
|  |  |  |  |  |  ┕ http://www.w3.org/ns/shacl#
|  |  |  |  |  ┝ http://data.ashrae.org/standard223/1.0/validation/model
|  |  |  |  |  |  ┝ http://www.w3.org/ns/shacl#
|  |  |  |  |  |  ┕ http://data.ashrae.org/standard223/1.0/model/all
|  |  |  |  |  ┝ http://data.ashrae.org/standard223/1.0/inference/model-rules
|  |  |  |  |  |  ┝ http://www.w3.org/ns/shacl#
|  |  |  |  |  |  ┕ http://data.ashrae.org/standard223/1.0/model/all
|  |  |  |  |  ┝ http://data.ashrae.org/standard223/1.0/inference/owl-subset
|  |  |  |  |  |  ┝ http://data.ashrae.org/standard223/1.0/model/all
|  |  |  |  |  |  ┕ http://www.w3.org/ns/shacl#
|  |  |  |  |  ┕ http://data.ashrae.org/standard223/1.0/inference/data-rules
|  |  |  |  |  |  ┝ http://data.ashrae.org/standard223/1.0/model/all
|  |  |  |  |  |  ┕ http://www.w3.org/ns/shacl#
|  |  |  |  ┕ https://brickschema.org/schema/1.2/Brick
|  |  ┝ http://data.ashrae.org/standard223/1.0/model/device
|  |  |  ┝ http://data.ashrae.org/standard223/1.0/model/core
|  |  |  ┕ http://www.w3.org/ns/shacl#
|  |  ┝ http://data.ashrae.org/standard223/1.0/vocab/domain
|  |  |  ┝ http://data.ashrae.org/standard223/1.0/model/core
|  |  |  ┕ http://www.w3.org/ns/shacl#
|  |  ┝ http://data.ashrae.org/standard223/1.0/model/system
|  |  |  ┝ http://www.w3.org/ns/shacl#
|  |  |  ┕ http://data.ashrae.org/standard223/1.0/model/core
|  |  ┕ http://data.ashrae.org/standard223/1.0/model/core
```

## Installation

```
pip install ontoenv
```

## Details

An RDF graph can be associated with a URI by including a statement in the graph that the URI is an instance of `owl:Ontology`.

```ttl
@prefix owl: <http://www.w3.org/2002/07/owl#> .

<http://example.com/my/graph> a owl:Ontology .
# ... other triples
```

Other RDF graphs can import the contents of `http://example.com/my/graph` in their own `owl:Ontology` definitions:

```ttl
@prefix owl: <http://www.w3.org/2002/07/owl#> .

<http://corporation.inc/my/other/graph> a owl:Ontology ;
    owl:imports <http://example.com/my/graph> .
```

OntoEnv has the option of transitively resolving these dependencies.
