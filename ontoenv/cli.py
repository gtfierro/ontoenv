import sys
import rdflib
import click
import logging
from ontoenv import OntoEnv
import networkx as nx


@click.group(help="Manage ontology definition mappings")
@click.option("-v", is_flag=True)
def i(v):
    if v:
        logging.basicConfig(level=logging.INFO)


@i.command(help="Initializes .ontoenv in the current directory")
@click.option("-v", help="Verbose output", is_flag=True)
@click.option("-s", help="Strict mode (error on missing ontologies)", is_flag=True)
def init(v, s):
    if v:
        logging.basicConfig(level=logging.INFO)
    OntoEnv(initialize=True, strict=s)


@i.command(help="Rebuilds the .ontoenv cache and mapping in the current directory")
@click.option("-v", help="Verbose output", is_flag=True)
@click.option("-s", help="Strict mode (error on missing ontologies)", is_flag=True)
def refresh(v, s):
    if v:
        logging.basicConfig(level=logging.INFO)
    oe = OntoEnv(initialize=False, strict=s)
    oe.refresh()


@i.command(help="Print mapping of ontology URI => filename!")
@click.option("-v", help="Verbose output", is_flag=True)
@click.option("-s", help="Strict mode (error on missing ontologies)", is_flag=True)
def dump(v, s):
    if v:
        logging.basicConfig(level=logging.INFO)
    oe = OntoEnv(initialize=False, strict=s)
    for ontology, filename in oe.mapping.items():
        print(f"{ontology} => {filename}")


@i.command(help="Output dependency graph")
@click.argument("output_filename", default="dependencies.pdf")
def output(output_filename):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logging.error("Could not import matplotlib; please install and try again")
        sys.exit(1)
    oe = OntoEnv(initialize=False)
    pos = nx.spring_layout(oe._dependencies, 2)
    nx.draw_networkx(oe._dependencies, pos=pos, with_labels=True)
    plt.savefig(output_filename)


@i.command(help="Print dependency graph")
@click.argument("root_uri", default="")
def deps(root_uri):
    oe = OntoEnv(initialize=False)
    oe.print_dependency_graph(root_uri)


# accepts arguments for import_dependencies; the graph is given as a filename
@i.command(help="Import all dependencies specified by the given graph and output the new graph to a file")
@click.argument("input_filename")
@click.argument("output_filename")
@click.argument("recursive", default=False)
@click.argument("recursive_limit", default=-1)
def import_deps(input_filename, output_filename, recursive, recursive_limit):
    g = rdflib.Graph()
    g.parse(input_filename, format=rdflib.util.guess_format(input_filename))
    oe = OntoEnv(initialize=False)
    oe.import_dependencies(g, recursive, recursive_limit)
    g.serialize(output_filename, format="turtle")


if __name__ == "__main__":
    i()
