from .test_invoker import create_edge
from .test_nodes import ImageTestInvocation, ListPassThroughInvocation, PromptTestInvocation, PromptCollectionTestInvocation
from invokeai.app.invocations.baseinvocation import BaseInvocation, BaseInvocationOutput, InvocationContext
from invokeai.app.services.processor import DefaultInvocationProcessor
from invokeai.app.services.sqlite import SqliteItemStorage, sqlite_memory
from invokeai.app.services.invocation_queue import MemoryInvocationQueue
from invokeai.app.services.invocation_services import InvocationServices
from invokeai.app.services.graph import Graph, GraphInvocation, InvalidEdgeError, NodeAlreadyInGraphError, NodeNotFoundError, are_connections_compatible, EdgeConnection, CollectInvocation, IterateInvocation, GraphExecutionState
import pytest


@pytest.fixture
def simple_graph():
    g = Graph()
    g.add_node(PromptTestInvocation(id = "1", prompt = "Banana sushi"))
    g.add_node(ImageTestInvocation(id = "2"))
    g.add_edge(create_edge("1", "prompt", "2", "prompt"))
    return g

@pytest.fixture
def mock_services():
    # NOTE: none of these are actually called by the test invocations
    return InvocationServices(
        generate = None,
        events = None,
        images = None,
        queue = MemoryInvocationQueue(),
        graph_execution_manager = SqliteItemStorage[GraphExecutionState](filename = sqlite_memory, table_name = 'graph_executions'),
        processor = DefaultInvocationProcessor()
    )

def invoke_next(g: GraphExecutionState, services: InvocationServices) -> tuple[BaseInvocation, BaseInvocationOutput]:
    n = g.next()
    if n is None:
        return (None, None)
    
    print(f'invoking {n.id}: {type(n)}')
    o = n.invoke(InvocationContext(services, "1"))
    g.complete(n.id, o)

    return (n, o)

def test_graph_state_executes_in_order(simple_graph, mock_services):
    g = GraphExecutionState(graph = simple_graph)
    
    n1 = invoke_next(g, mock_services)
    n2 = invoke_next(g, mock_services)
    n3 = g.next()

    assert g.prepared_source_mapping[n1[0].id] == "1"
    assert g.prepared_source_mapping[n2[0].id] == "2"
    assert n3 is None
    assert g.results[n1[0].id].prompt == n1[0].prompt
    assert n2[0].prompt == n1[0].prompt

def test_graph_is_complete(simple_graph, mock_services):
    g = GraphExecutionState(graph = simple_graph)
    n1 = invoke_next(g, mock_services)
    n2 = invoke_next(g, mock_services)
    n3 = g.next()

    assert g.is_complete()

def test_graph_is_not_complete(simple_graph, mock_services):
    g = GraphExecutionState(graph = simple_graph)
    n1 = invoke_next(g, mock_services)
    n2 = g.next()

    assert not g.is_complete()

# TODO: test completion with iterators/subgraphs

def test_graph_state_expands_iterator(mock_services):
    graph = Graph()
    test_prompts = ["Banana sushi", "Cat sushi"]
    graph.add_node(PromptCollectionTestInvocation(id = "1", collection = list(test_prompts)))
    graph.add_node(IterateInvocation(id = "2"))
    graph.add_node(ImageTestInvocation(id = "3"))
    graph.add_edge(create_edge("1", "collection", "2", "collection"))
    graph.add_edge(create_edge("2", "item", "3", "prompt"))
    
    g = GraphExecutionState(graph = graph)
    n1 = invoke_next(g, mock_services)
    n2 = invoke_next(g, mock_services)
    n3 = invoke_next(g, mock_services)
    n4 = invoke_next(g, mock_services)
    n5 = invoke_next(g, mock_services)

    assert g.prepared_source_mapping[n1[0].id] == "1"
    assert g.prepared_source_mapping[n2[0].id] == "2"
    assert g.prepared_source_mapping[n3[0].id] == "2"
    assert g.prepared_source_mapping[n4[0].id] == "3"
    assert g.prepared_source_mapping[n5[0].id] == "3"

    assert isinstance(n4[0], ImageTestInvocation)
    assert isinstance(n5[0], ImageTestInvocation)

    prompts = [n4[0].prompt, n5[0].prompt]
    assert sorted(prompts) == sorted(test_prompts)

def test_graph_state_collects(mock_services):
    graph = Graph()
    test_prompts = ["Banana sushi", "Cat sushi"]
    graph.add_node(PromptCollectionTestInvocation(id = "1", collection = list(test_prompts)))
    graph.add_node(IterateInvocation(id = "2"))
    graph.add_node(PromptTestInvocation(id = "3"))
    graph.add_node(CollectInvocation(id = "4"))
    graph.add_edge(create_edge("1", "collection", "2", "collection"))
    graph.add_edge(create_edge("2", "item", "3", "prompt"))
    graph.add_edge(create_edge("3", "prompt", "4", "item"))
    
    g = GraphExecutionState(graph = graph)
    n1 = invoke_next(g, mock_services)
    n2 = invoke_next(g, mock_services)
    n3 = invoke_next(g, mock_services)
    n4 = invoke_next(g, mock_services)
    n5 = invoke_next(g, mock_services)
    n6 = invoke_next(g, mock_services)

    assert isinstance(n6[0], CollectInvocation)

    assert sorted(g.results[n6[0].id].collection) == sorted(test_prompts)
