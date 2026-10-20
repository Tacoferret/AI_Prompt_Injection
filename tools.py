"""Two simulated tools. They never touch the network, files, or real accounts.

search_info(query)   -> returns the task's search result (same result for any query)
read_document(doc_id) -> returns the task's document body for the matching doc_id

The harness (not the model) decides which text each tool returns, based on the
condition: E1 clean, E2 payload in the document body, E3 payload in the search snippet.
"""
import json

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_info",
            "description": "Search the campus information index. Returns a list of results with title, snippet and doc_id.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": "Read the full text of a document by its doc_id.",
            "parameters": {
                "type": "object",
                "properties": {"doc_id": {"type": "string", "description": "The doc_id from a search result."}},
                "required": ["doc_id"],
            },
        },
    },
]


class MockTools:
    """Fresh instance per trial, so no state carries over between trials."""

    def __init__(self, record):
        self.record = record
        self.calls = []  # (tool_name, arguments_dict)

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "search_info":
            return self.search_info(arguments.get("query", ""))
        if name == "read_document":
            return self.read_document(arguments.get("doc_id", ""))
        return json.dumps({"error": f"Unknown tool: {name}"})

    def search_info(self, query):
        sr = self.record["search_result"]
        return json.dumps({"results": [{"title": sr["title"], "snippet": sr["snippet"], "doc_id": self.record["doc_id"]}]})

    def read_document(self, doc_id):
        if doc_id != self.record["doc_id"]:
            return json.dumps({"error": f"Document not found: {doc_id}"})
        d = self.record["document"]
        return json.dumps({"doc_id": doc_id, "title": d["title"], "body": d["body"]})
