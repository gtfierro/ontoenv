"""
"""
import json
from pathlib import Path
import os
import glob
import shutil
import logging
import rdflib
import click
import networkx as nx
from networkx.readwrite.graphml import write_graphml, read_graphml
import matplotlib.pyplot as plt

FILE_EXTENSIONS = [".ttl", ".rdf", ".owl", ".n3", ".ntriples"]

# TODO: track dependencies in a graph and render it


class OntoEnv:
    def __init__(self, oe_dir: Path = None, initialize=False):
        """
        *Idempotently* initializes the oe_dir. Creates directories if they don't exist
        and creates a default mapping file. Reads existing mapping file if one exists.
        Returns the resulting dictionary.

        Mapping file form:
        {
            "<ontology URI>": ["list of file paths defining the ontology"],
        }
        """
        self._seen = set()
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
                raise Exception(f"No .ontoenv directory at {self.oedir}. Be sure to run 'ontoenv init'")
        self.mapping = json.load(open(mapping_file))

        self._dependencies = nx.DiGraph()
        if os.path.exists(self.oedir / "dependencies.gml"):
            self._dependencies = read_graphml(self.oedir / "dependencies.gml")

        self.cache_contents = set()
        self._refresh_cache_contents()

        if created:
            self.refresh()

    def refresh(self):
        logging.info(f"Searching for RDF files in {self.oedir.parent}")
        for filename in find_ontology_files(self.oedir.parent):
            self._get_ontology_definition(filename)
        for filename in find_ontology_files(self.oedir.parent):
            self._resolve_imports_from_uri(filename)

    def _refresh_cache_contents(self):
        self.cache_contents = set()
        for ext in FILE_EXTENSIONS:
            pat = str(self.cachedir / f"*{ext}")
            for fn in glob.glob(pat):
                self.cache_contents.add(fn)

    def _cache_file(self, filename: Path):
        if filename.parent == self.cachedir or filename in self.cache_contents:
            return
        shutil.copy(filename, self.cachedir)
        self._refresh_cache_contents()

    def _save(self):
        with open(self.oedir / "mapping.json", "w") as f:
            json.dump(self.mapping, f)
        write_graphml(self._dependencies, self.oedir / "dependencies.gml")


    def _resolve_uri(self, uri: str):
        uri = str(uri)
        graph = rdflib.Graph()
        try:
            graph.parse(uri, format=rdflib.util.guess_format(uri) or "xml")
            filename = uri
        except Exception as e:
            logging.warning(f"Could not load {uri} ({e}); trying to resolve locally")
            if uri in self.mapping:
                filename = self.mapping[uri]
                graph.parse(filename, format=rdflib.util.guess_format(filename) or "xml")
            else:
                raise Exception(f"No definition for {uri}")
                # import sys;sys.exit(1)
        # if the filename does not exist locally, then serialize the graph into the cache
        # and upate the mapping
        if not os.path.exists(filename):
            filename = str(filename) + ".ttl"
            filename = self.cachedir / Path(filename.replace("/", "_"))
            graph.serialize(str(filename), format="ttl")
            self.mapping[str(uri)] = str(filename)
            self._refresh_cache_contents()
        return graph, filename

    def _get_ontology_definition(self, filename: str):
        if str(filename) in self.mapping.values():
            return
        graph = rdflib.Graph()
        filename = str(filename)
        logging.info(f"Parsing {filename}")
        try:
            graph.parse(filename, format=rdflib.util.guess_format(filename))
        except Exception as e:
            logging.error(f"Could not parse {filename}: {e}")
            return
        # find ontology definitions and update mapping
        q = """SELECT ?ont ?prop ?value WHERE {
            ?ont a <http://www.w3.org/2002/07/owl#Ontology> .
            ?ont ?prop ?value
        }"""
        for row in graph.query(q):
            self.mapping[str(row[0])] = str(filename)
        self._save()

    def _resolve_imports_from_uri(self, uri: str):
        logging.info(f"Resolving imports from {uri}")
        if str(uri) in self._seen:
            return
        self._seen.add(str(uri))
        try:
            graph, filename = self._resolve_uri(uri)
            self._get_ontology_definition(filename)
            for importURI in graph.objects(predicate=rdflib.OWL.imports):
                self._dependencies.add_edge(str(uri), str(importURI))
                self._resolve_imports_from_uri(str(importURI))
        except Exception as e:
            logging.error(f"Could not resolve {uri} ({e})")
            return

    def print_dependency_graph(self, root_uri=None):
        print("\033[1mBolded\033[0m values are duplicate imports whose deps are listed elsewhere in the tree")
        if root_uri is None or root_uri == "":
            root_uris = [n for n,d in self._dependencies.in_degree() if d==0]
        elif root_uri not in self._dependencies:
            root_uris = [self.mapping[root_uri]]
        else:
            root_uris = [root_uri]
        seen = set()
        for root in root_uris:
            print(f"{root}")
            for (_, dep) in self._dependencies.edges([root]):
                self._print_dep_graph(dep, 1, seen)

    def _print_dep_graph(self, uri, indent, seen, last=False):
        char = '┕' if last else '┝'
        if uri in seen:
            print(f"{'|  '*indent}{char} \033[1m{uri}\033[0m")
            return
        print(f"{'|  '*indent}{char} {uri}")
        seen.add(uri)
        num_deps = len(self._dependencies.edges([uri]))
        for (i, (_, dep)) in enumerate(self._dependencies.edges([uri])):
            self._print_dep_graph(dep, indent+1, seen, last=i==num_deps-1)


    def import_dependencies(self, graph, cache=None, recursive=True, recursive_limit=-1):
        if recursive_limit > 0:
            recursive=False
        elif recursive_limit==0:
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
                logging.error(f"Could not load {uri} (no definition found)")
                cache.add(uri)
                continue
            logging.info(f"Importing {uri} from {filename}")
            graph.parse(filename, format=rdflib.util.guess_format(filename))
            cache.add(uri)
        if (recursive or recursive_limit > 0) and new_imports:
            self.import_dependencies(graph, cache=cache, recursive=recursive, recursive_limit=recursive_limit-1)


def find_root_file(start=None):
    """
    Starting at the current directory, traverse upwards until it finds a .ontoenv directory
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

    if str(start) == start.root:
        return None

    return find_root_file(start.parent)


def find_ontology_files(start):
    """
    Starting at the given directory, explore all subtrees and gather all ontology
    files, as identified by their file extension (see FILE_EXTENSIONS).
    Returns a generator which yields all files matching one of the FILE_EXTENSIONS
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


@click.group(help="Manage ontology definition mappings")
@click.option('-v', is_flag=True)
def i(v):
    if v:
        logging.basicConfig(level=logging.INFO)


@i.command(help="Initializes .ontoenv in the current directory")
@click.option('-v', help="Verbose output", is_flag=True)
def init(v):
    if v:
        logging.basicConfig(level=logging.INFO)
    OntoEnv(initialize=True)


@i.command(help="Rebuilds the .ontoenv cache and mapping in the current directory")
@click.option('-v', help="Verbose output", is_flag=True)
def refresh(v):
    if v:
        logging.basicConfig(level=logging.INFO)
    oe = OntoEnv(initialize=False)
    oe.refresh()


@i.command(help="Print mapping of ontology URI => filename!")
@click.option('-v', help="Verbose output", is_flag=True)
def dump(v):
    if v:
        logging.basicConfig(level=logging.INFO)
    oe = OntoEnv(initialize=False)
    for ontology, filename in oe.mapping.items():
        print(f"{ontology} => {filename}")


@i.command(help="Output dependency graph")
@click.argument("output_filename", default="dependencies.pdf")
def output(output_filename):
    oe = OntoEnv(initialize=False)
    pos = nx.spring_layout(oe._dependencies, 2)
    nx.draw_networkx(oe._dependencies, pos=pos, with_labels=True)
    plt.savefig(output_filename)

@i.command(help="Print dependency graph")
@click.argument("root_uri", default="")
def deps(root_uri):
    oe = OntoEnv(initialize=False)
    oe.print_dependency_graph(root_uri)
