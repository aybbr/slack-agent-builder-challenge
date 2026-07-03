import json
import logging
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_manifest(manifest_path: str) -> dict[str, dict]:
    """Load manifest.json and return model + test nodes keyed by unique_id.

    Args:
        manifest_path: Path to manifest.json

    Returns:
        Dict mapping unique_id → node dict for all model and test nodes.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        json.JSONDecodeError: If the manifest contains invalid JSON.
    """
    path = Path(manifest_path)
    with path.open() as f:
        raw = json.load(f)
    nodes = raw.get("nodes", {})
    return {
        uid: node
        for uid, node in nodes.items()
        if uid.startswith("model.") or uid.startswith("test.")
    }


def _get_node(unique_id: str, nodes: dict[str, dict]) -> dict | None:
    """Safely retrieve a node by unique_id. Returns None if not found."""
    return nodes.get(unique_id)


def _resolve_asset_id(asset_id: str, nodes: dict[str, dict]) -> str:
    """Map a short model name to its full unique_id.

    Searches model nodes for any whose 'name' field matches asset_id.

    Args:
        asset_id: Short model name (e.g. 'fct_sales_pipeline').
        nodes: Dict of unique_id → node from _load_manifest.

    Returns:
        Full unique_id (e.g. 'model.tracey_demo.fct_sales_pipeline').

    Raises:
        ValueError: If no match or multiple matches found.
    """
    matches = [
        uid
        for uid, node in nodes.items()
        if uid.startswith("model.") and node.get("name") == asset_id
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        raise ValueError(f"Asset '{asset_id}' not found in manifest")
    raise ValueError(
        f"Ambiguous asset name '{asset_id}' matches {len(matches)} nodes"
    )


def _get_upstream_models(unique_id: str, nodes: dict[str, dict]) -> list[str]:
    """Return direct upstream model unique_ids for a node.

    Filters out test and macro dependencies — only model nodes are returned.

    Args:
        unique_id: Full unique_id of the node.
        nodes: Dict of unique_id → node from _load_manifest.

    Returns:
        List of upstream model unique_ids.
    """
    node = nodes.get(unique_id)
    if node is None:
        return []
    upstream = node.get("depends_on", {}).get("nodes", [])
    return [uid for uid in upstream if uid.startswith("model.")]


def _get_downstream_models(unique_id: str, nodes: dict[str, dict]) -> list[str]:
    """Return all transitive downstream model unique_ids.

    Traverses the graph breadth-first from children to all descendants.

    Args:
        unique_id: Full unique_id of the starting node.
        nodes: Dict of unique_id → node from _load_manifest.

    Returns:
        List of downstream model unique_ids (may be empty).
    """
    children_map: dict[str, list[str]] = {}
    for uid, node in nodes.items():
        if not uid.startswith("model."):
            continue
        for dep in node.get("depends_on", {}).get("nodes", []):
            children_map.setdefault(dep, []).append(uid)

    visited: set[str] = set()
    queue: deque[str] = deque(children_map.get(unique_id, []))
    result: list[str] = []
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        if not current.startswith("model."):
            continue
        visited.add(current)
        result.append(current)
        queue.extend(children_map.get(current, []))
    return result


def _topological_sort(
    node_ids: list[str], nodes: dict[str, dict]
) -> list[str]:
    """Kahn's algorithm on the subgraph spanned by node_ids.

    Only considers edges between nodes that are both in node_ids.

    Args:
        node_ids: List of unique_ids to sort.
        nodes: Dict of unique_id → node from _load_manifest.

    Returns:
        Topologically sorted list of unique_ids.

    Raises:
        ValueError: If a cycle is detected in the subgraph.
    """
    ids_set = set(node_ids)

    in_degree: dict[str, int] = {uid: 0 for uid in node_ids}
    adjacency: dict[str, list[str]] = {uid: [] for uid in node_ids}

    for uid in node_ids:
        node = nodes.get(uid)
        if node is None:
            continue
        for dep in node.get("depends_on", {}).get("nodes", []):
            if dep in ids_set and dep.startswith("model."):
                adjacency.setdefault(dep, []).append(uid)
                in_degree[uid] += 1

    queue: deque[str] = deque(
        uid for uid in node_ids if in_degree.get(uid, 0) == 0
    )
    result: list[str] = []

    while queue:
        current = queue.popleft()
        result.append(current)
        for neighbor in adjacency.get(current, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(node_ids):
        raise ValueError("Cycle detected in model dependency graph")

    return result
