"""
"""
import sys
import json
from pathlib import Path
import os
import glob
import shutil
import logging
import rdflib
import networkx as nx
from networkx.readwrite.graphml import write_graphml, read_graphml
from typing import Optional, Set, Generator, Union, Tuple, Dict

FILE_EXTENSIONS = [".ttl", ".rdf", ".owl", ".n3", ".ntriples"]

# TODO: track dependencies in a graph and render it

OntologyLocation = Union[Path, str]


class OntoEnv:
    _dependencies: nx.DiGraph
    _graph_cache: Dict[str, rdflib.Graph]
    _failed_parsing: Set[str]

    def __init__(
        self,
        oe_dir: Optional[Path] = None,
        initialize: bool = False,
        strict: bool = False,
    ):
        self._graph_cache = {}
        self._failed_parsing = set()
        """
        *Idempotently* initializes the oe_dir. Creates directories if they don't exist
        and creates a default mapping file. Reads existing mapping file if one exists.
        Returns the resulting dictionary.

        Mapping file form:
        {
            "<ontology URI>": ["list of file paths defining the ontology"],
        }

        :param oe_dir: directory of the ontoenv mapping file, defaults to None
        :type oe_dir: Optional[Path], optional
        :param initialize: if true, then initialize the ontoenv mapping, defaults to False
        :type initialize: bool, optional
        :param strict: if true, error when an ontology is not found, defaults to False
        :type strict: bool, optional
        """
        self._strict = strict
        self._seen: Set[str] = set()
        if oe_dir is None:
            oe_dir = find_root_file()
            if oe_dir is None:
                oe_dir = Path(os.getcwd())
        self.oedir = Path(oe_dir)
        logging.info(f"Using {self.oedir} as .ontoenv directory")
        if os.path.basename(oe_dir) != ".ontoenv":
            oe_dir = oe_dir / ".ontoenv"
        self.oedir = oe_dir.resolve()
        self.cachedir = self.oedir / "cache"
        if initialize:
            logging.info(f"Create .ontoenv at {self.oedir.resolve()}")
            # create directory (ok if exists)
            os.makedirs(self.oedir, exist_ok=True)
            os.makedirs(self.cachedir, exist_ok=True)

        # read or create mapping file
        mapping_file = self.oedir / "mapping.json"
        created = False
        if not os.path.exists(mapping_file):
            if initialize:
                created = True
                with open(mapping_file, "w") as f:
                    json.dump({}, f)
            else:
                raise Exception(
                    f"No .ontoenv directory at {self.oedir}. Be sure to run 'ontoenv init'"
                )
        self.mapping = json.load(open(mapping_file))

        self._dependencies = nx.DiGraph()
        if os.path.exists(self.oedir / "dependencies.gml"):
            self._dependencies = read_graphml(self.oedir / "dependencies.gml")
            assert isinstance(self._dependencies, nx.DiGraph)

        self.cache_contents: Set[str] = set()
        self._refresh_cache_contents()

        if created:
            self.refresh()

    def refresh(self) -> None:
        """
        Ensure the ontoenv environment is up to date with the current set of imports.
        Does not currently re-fetch remote ontologies.
        """
        logging.info(f"Searching for RDF files in {self.oedir.parent}")
        for filename in find_ontology_files(self.oedir.parent):
            self._get_ontology_definition(filename)
        for filename in find_ontology_files(self.oedir.parent):
            self._resolve_imports_from_uri(filename)

        # remove old imports/files that are no longer in the mapping
        mapping_tmp = list(self.mapping.items())
        for uri, filename in mapping_tmp:
            if not os.path.exists(filename):
                del self.mapping[uri]
                self._dependencies.remove_node(uri)
                logging.info(f"Removed {uri} from mapping")

    def _refresh_cache_contents(self) -> None:
        self.cache_contents = set()
        for ext in FILE_EXTENSIONS:
            pat = str(self.cachedir / f"*{ext}")
            for fn in glob.glob(pat):
                self.cache_contents.add(fn)

    def _cache_file(self, filename: Path) -> None:
        if filename.parent == self.cachedir or filename in self.cache_contents:
            return
        shutil.copy(filename, self.cachedir)
        self._refresh_cache_contents()

    def _save(self) -> None:
        with open(self.oedir / "mapping.json", "w") as f:
            json.dump(self.mapping, f)
        write_graphml(self._dependencies, self.oedir / "dependencies.gml")

    def resolve_uri(
        self, uri: OntologyLocation
    ) -> Tuple[rdflib.Graph, OntologyLocation]:
        """
        Returns an rdflib.Graph which the provided uri resolves to. Prioritizes
        local files (including those in the cache), then remote URIs (which are
        then cached)

        :param uri: URI of the graph to return
        :return: Tuple of the RDF Graph and the physical filename where it was found
        :raises Exception: [TODO:description]
        """
        uri = str(uri)

        # attempt to resolve locally
        if uri in self.mapping:
            filename = self.mapping[uri]
            # check if the graph is in the cache
            if uri in self._graph_cache:
                return self._graph_cache[uri], filename
            # if not in the cache, parse the graph
            graph = rdflib.Graph()
            graph.parse(filename, format=rdflib.util.guess_format(filename) or "xml")
            # store the parsed graph in the cache
            self._graph_cache[uri] = graph
            return graph, filename
        # create graph object to hold the remote graph
        graph = rdflib.Graph()
        logging.info(
            f"URI {uri} was not defined locally or did not have a cached definition. Trying to fetch remote"
        )
        try:
            graph.parse(uri, format=rdflib.util.guess_format(uri) or "xml")
            filename = uri
        except Exception as e:
            raise Exception(f"No definition for {uri}: {e}")

        # if the filename does not exist locally, then serialize the graph into the cache
        # and upate the mapping
        if not os.path.exists(filename):
            filename = str(filename) + ".ttl"
            filename = self.cachedir / Path(
                filename.replace("/", "_").replace(":", "_")
            )
            graph.serialize(str(filename), format="ttl")
            self.mapping[str(uri)] = str(filename)
            self._refresh_cache_contents()
        return graph, filename

    def _get_ontology_definition(self, filename: OntologyLocation) -> None:
        """
        If the filename is not already in the mapping, it parses the file and updates the mapping.

        :param filename: The filename of the ontology
        """
        if (
            str(filename) in self.mapping.values()
            or str(filename) in self._failed_parsing
        ):
            return
        graph = rdflib.Graph()
        logging.info(f"Parsing {filename}")
        try:
            graph.parse(filename, format=rdflib.util.guess_format(str(filename)))
        except Exception as e:
            self._failed_parsing.add(str(filename))
            if self._strict:
                logging.fatal(f"Could not parse {filename}: {e}")
                sys.exit(1)
            else:
                logging.error(f"Could not parse {filename}: {e}")
                return
        # find ontology definitions and update mapping
        q = """SELECT ?ont ?prop ?value WHERE {
            ?ont a <http://www.w3.org/2002/07/owl#Ontology> .
            ?ont ?prop ?value
        }"""
        for row in graph.query(q):
            assert isinstance(row, tuple)
            self.mapping[str(row[0])] = str(filename)
        self._save()

    def _resolve_imports_from_uri(self, uri: OntologyLocation) -> None:
        """
        Resolves the imports from the given URI.

        :param uri: The URI to resolve imports from
        """
        logging.info(f"Resolving imports from {uri}")
        if str(uri) in self._seen:
            return
        self._seen.add(str(uri))
        try:
            graph, filename = self.resolve_uri(uri)
            self._get_ontology_definition(filename)
            for importURI in graph.objects(predicate=rdflib.OWL.imports):
                self._dependencies.add_edge(str(uri), str(importURI))
                self._resolve_imports_from_uri(str(importURI))
        except Exception as e:
            if self._strict:
                logging.fatal(f"Could not resolve {uri} ({e})")
                sys.exit(1)
            else:
                logging.error(f"Could not resolve {uri} ({e})")
                return

    def print_dependency_graph(self, root_uri: Optional[str] = None) -> None:
        """
        Prints the dependency graph.

        :param root_uri: The root URI to start from. If None, it starts from all nodes with no incoming edges.
        """
        print(
            "\033[1mBolded\033[0m values are duplicate imports whose deps are listed elsewhere in the tree"
        )
        if root_uri is None or root_uri == "":
            root_uris = [n for n, d in self._dependencies.in_degree() if d == 0]
        elif root_uri not in self._dependencies:
            root_uris = [self.mapping[root_uri]]
        else:
            root_uris = [root_uri]
        seen: Set[str] = set()
        for root in root_uris:
            print(f"{root}")
            for _, dep in self._dependencies.edges([root]):
                self._print_dep_graph(dep, 1, seen)

    def _print_dep_graph(
        self, uri: str, indent: int, seen: Set[str], last: bool = False
    ) -> None:
        char = "┕" if last else "┝"
        if uri in seen:
            print(f"{'|  '*indent}{char} \033[1m{uri}\033[0m")
            return
        print(f"{'|  '*indent}{char} {uri}")
        seen.add(uri)
        num_deps = len(self._dependencies.edges([uri]))
        for i, (_, dep) in enumerate(self._dependencies.edges([uri])):
            self._print_dep_graph(dep, indent + 1, seen, last=i == num_deps - 1)

    def import_dependencies(
        self, graph: rdflib.Graph, recursive: bool = True, recursive_limit: int = -1, remove_import_statements: bool = True
    ) -> None:
        """
        Imports all dependencies of the given graph. Rewrites sh:prefixes and sh:declare statements to
        hang off of the ontology declaration of the provided graph

        :param graph: The RDF graph to import dependencies for
        :param recursive: Whether to recursively import dependencies
        :param recursive_limit: The maximum depth to recursively import dependencies. -1 means no limit.
        :param remove_import_statements: Whether to remove the import statements from the graph after importing them
        """
        # get the base URI of this graph (subject of owl:Ontology)
        uri = graph.value(predicate=rdflib.RDF.type, object=rdflib.OWL.Ontology)
        if uri is None:
            raise Exception("No owl:Ontology found in graph")
        # import all dependencies
        self._import_dependencies(
            graph, recursive=recursive, recursive_limit=recursive_limit
        )
        # change all triples of form <x> <sh:prefixes> <uri1> to <x> <sh:prefixes> <uri>, where
        # <uri> is our base URI above
        for s, p, o in graph.triples((None, rdflib.SH.prefixes, None)):
            graph.remove((s, p, o))
            graph.add((s, p, uri))
        # change all triples of form <x> <sh:declare> <uri1> to <uri> <sh:declare> <uri1>, where
        # <uri> is our base URI above
        for s, p, o in graph.triples((None, rdflib.SH.declare, None)):
            graph.remove((s, p, o))
            graph.add((uri, p, o))
        # remove all import statements
        if remove_import_statements:
            graph.remove((None, rdflib.OWL.imports, None))

    def _import_dependencies(
        self,
        graph: rdflib.Graph,
        cache: Optional[set] = None,
        recursive: bool = True,
        recursive_limit: int = -1,
    ) -> None:
        if recursive_limit > 0:
            recursive = False
        elif recursive_limit == 0:
            return
        if cache is None:
            cache = set()
        new_imports = False
        for importURI in graph.objects(predicate=rdflib.OWL.imports):
            uri = str(importURI)
            if uri in cache:
                continue
            new_imports = True
            filename = self.mapping.get(uri)
            if filename is None:
                if self._strict:
                    raise Exception(f"Could not load {uri} (no definition found)")
                logging.error(f"Could not load {uri} (no definition found)")
                cache.add(uri)
                continue
            logging.info(f"Importing {uri} from {filename}")
            graph.parse(filename, format=rdflib.util.guess_format(filename))
            cache.add(uri)
        if (recursive or recursive_limit > 0) and new_imports:
            self._import_dependencies(
                graph,
                cache=cache,
                recursive=recursive,
                recursive_limit=recursive_limit - 1,
            )


def find_root_file(start: Optional[OntologyLocation] = None) -> Optional[Path]:
    """
    Starting at the current directory, traverse upwards until it finds a .ontoenv directory

    :param start: The directory to start from. If None, it starts from the current directory.
    :return: The path to the .ontoenv directory, or None if not found.
    """
    if start is None:
        start = Path(os.getcwd())
    start = Path(start)

    oe_dir = start / ".ontoenv"

    # if '.ontoenv' exists and is a directory
    if os.path.exists(oe_dir):
        if not oe_dir.is_dir():
            raise Exception(f".ontoenv ({oe_dir}) must be a directory")
        return oe_dir

    if len(start.parts) == 1:
        return None

    return find_root_file(start.parent)


def find_ontology_files(start: Path) -> Generator[OntologyLocation, None, None]:
    """
    Starting at the given directory, explore all subtrees and gather all ontology
    files, as identified by their file extension (see FILE_EXTENSIONS).
    Returns a generator which yields all files matching one of the FILE_EXTENSIONS

    :param start: The directory to start from.
    :return: A generator yielding all ontology files.
    """
    # use parent of the .ontoenv directory
    for filename in start.iterdir():
        full_suffix = ".".join(filename.suffixes)
        matches_extension = (
            filename.suffix in FILE_EXTENSIONS or full_suffix in FILE_EXTENSIONS
        )
        if matches_extension and not filename.is_dir():
            yield filename
        if not filename.is_dir():
            continue
        for newfn in find_ontology_files(filename):
            yield newfn
