"""
routing-graph.json を使い、全78,542棟の住宅に対して「道路網＋勾配負荷で近い上位K=6件の
主要バス停（stopIdx, 一般実効距離, 高齢者実効距離）」を多始点 K-best ダイクストラ法で算出し、
public/data/building-stop-candidates.json として出力する。

これによりブラウザ上で時間帯・運行本数しきい値・待ち時間ペナルティを切り替えても、
78,542棟すべてを道路網に沿って即座に再評価できる。
"""

from __future__ import annotations

import heapq
import json
import pathlib

SCRIPT_DIR = pathlib.Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = REPO_ROOT / "public" / "data"

GRAPH_JSON = DATA_DIR / "routing-graph.json"
SCORES_JSON = DATA_DIR / "building-network-scores.json"
FREQ_JSON = DATA_DIR / "bus-stop-frequencies.json"
OUTPUT_JSON = DATA_DIR / "building-stop-candidates.json"

K_NEAREST_STOPS = 6


def find_stop_node_indices(nodes: list, stops: list[dict]) -> list[int]:
    """routing-graph.json の末尾側にある stop ノードを座標完全一致で特定する。"""
    coord_to_indices: dict[tuple[float, float], list[int]] = {}
    for idx, (lng, lat, _) in enumerate(nodes):
        coord_to_indices.setdefault((lng, lat), []).append(idx)

    stop_nodes: list[int] = []
    for s in stops:
        matches = coord_to_indices.get((s["lng"], s["lat"]), [])
        if not matches:
            raise ValueError(f"Stop node not found in routing-graph.json: {s['name']} ({s['lng']}, {s['lat']})")
        # 建物や既存ノードと同座標になった場合は、03_compute_scores.py の挿入順で後方の stop ノードを選ぶ
        stop_nodes.append(matches[-1])
    return stop_nodes


def k_best_dijkstra(
    n_nodes: int,
    adj: list[list[tuple[int, float]]],
    stop_nodes: list[int],
    k: int,
) -> list[dict[int, float]]:
    """全停留所を同時始点とし、各ノードに到達した上位K件の異なる停留所とコストを記録する。"""
    settled: list[dict[int, float]] = [{} for _ in range(n_nodes)]
    heap: list[tuple[float, int, int]] = []
    for stop_idx, node_idx in enumerate(stop_nodes):
        heapq.heappush(heap, (0.0, stop_idx, node_idx))

    while heap:
        cost, stop_idx, u = heapq.heappop(heap)
        node_map = settled[u]
        if stop_idx in node_map or len(node_map) >= k:
            continue
        node_map[stop_idx] = cost
        for v, weight in adj[u]:
            v_map = settled[v]
            if stop_idx not in v_map and len(v_map) < k:
                heapq.heappush(heap, (cost + weight, stop_idx, v))

    return settled


def main() -> None:
    print("Loading routing-graph, scores, and frequencies...", flush=True)
    graph = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    scores = json.loads(SCORES_JSON.read_text(encoding="utf-8"))
    freq = json.loads(FREQ_JSON.read_text(encoding="utf-8"))

    nodes = graph["nodes"]
    edges = graph["edges"]
    stops = freq["stops"]
    version = graph["version"]

    stop_nodes = find_stop_node_indices(nodes, stops)
    n_nodes = len(nodes)

    # 1. 一般プロファイル (edge[3])
    adj_gen: list[list[tuple[int, float]]] = [[] for _ in range(n_nodes)]
    for u, v, _, eff_gen, _, _ in edges:
        adj_gen[u].append((v, eff_gen))
        adj_gen[v].append((u, eff_gen))
    print(f"Running K={K_NEAREST_STOPS} Dijkstra (general)...", flush=True)
    settled_gen = k_best_dijkstra(n_nodes, adj_gen, stop_nodes, K_NEAREST_STOPS)
    del adj_gen

    # 2. 高齢者プロファイル (edge[4])
    adj_eld: list[list[tuple[int, float]]] = [[] for _ in range(n_nodes)]
    for u, v, _, _, eff_eld, _ in edges:
        adj_eld[u].append((v, eff_eld))
        adj_eld[v].append((u, eff_eld))
    print(f"Running K={K_NEAREST_STOPS} Dijkstra (elderly)...", flush=True)
    settled_eld = k_best_dijkstra(n_nodes, adj_eld, stop_nodes, K_NEAREST_STOPS)
    del adj_eld

    # 3. 各建物の候補停留所 [stopIdx, round(effGen, 1), round(effEld, 1)] をまとめる
    #    ※building-network-scores.json の行順と1対1対応のフラット配列にすることで容量を最小化
    building_candidates: list[list[int | float]] = []
    mismatch_count = 0

    for row in scores:
        b_node = row["networkNode"]
        gen_map = settled_gen[b_node]
        eld_map = settled_eld[b_node]

        # 一般側上位K件と高齢者側上位K件の和集合（多くの場合同じだが、坂道差で順位入替に備える）
        stop_ids = set(gen_map.keys()) | set(eld_map.keys())
        items = []
        for sid in stop_ids:
            g = gen_map.get(sid)
            e = eld_map.get(sid)
            if g is None or e is None:
                continue
            items.append((g, sid, round(g, 1), round(e, 1)))
        items.sort()

        if items:
            best_g, best_sid, _, _ = items[0]
            if abs(best_g - row["busEffectiveDistanceM_general"]) > 0.2:
                mismatch_count += 1
        flat: list[int | float] = []
        for _, sid, g_r, e_r in items[:K_NEAREST_STOPS]:
            flat.extend([sid, g_r, e_r])
        building_candidates.append(flat)

    payload = {
        "version": version,
        "k": K_NEAREST_STOPS,
        "format": "flat_triples_by_score_row_index: [stopIdx, effGen, effEld, ...]",
        "rows": building_candidates,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    size_mb = OUTPUT_JSON.stat().st_size / (1024 * 1024)
    print(
        f"Wrote {OUTPUT_JSON.name}: {len(building_candidates)} buildings, "
        f"mismatches={mismatch_count}, size={size_mb:.2f}MB",
        flush=True,
    )


if __name__ == "__main__":
    main()
