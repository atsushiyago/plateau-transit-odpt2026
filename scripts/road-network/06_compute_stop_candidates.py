"""
routing-graph.json を使い、全78,542棟の住宅に対して「道路網＋勾配負荷で近い主要バス停の候補
（最低6件、および実効距離600m以内の全候補: stopIdx, 一般実効距離, 高齢者実効距離）」を
多始点 K-best ダイクストラ法で算出し、public/data/building-stop-candidates.json として出力する。

600mは道路網距離モデルの最大緩和基準（400m×1.5倍）に相当するため、この範囲内の候補を
すべて保持することで運行頻度フィルタ・待ち時間ペナルティの境界判定を厳密に保てる。
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

MIN_CANDIDATES = 6
EXACT_COVERAGE_CUTOFF_M = 600.0
ELDERLY_SEARCH_CUTOFF_M = 1200.0
MAX_CANDIDATES_CAP = 32


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
    min_k: int,
    max_dist: float,
    max_k: int,
) -> list[dict[int, float]]:
    """全停留所を同時始点とし、各ノードについて min_k 件以上・かつ max_dist 以内の候補をすべて記録する。"""
    settled: list[dict[int, float]] = [{} for _ in range(n_nodes)]
    heap: list[tuple[float, int, int]] = []
    for stop_idx, node_idx in enumerate(stop_nodes):
        heapq.heappush(heap, (0.0, stop_idx, node_idx))

    while heap:
        cost, stop_idx, u = heapq.heappop(heap)
        node_map = settled[u]
        if stop_idx in node_map or len(node_map) >= max_k:
            continue
        if len(node_map) >= min_k and cost > max_dist:
            continue
        node_map[stop_idx] = cost
        for v, weight in adj[u]:
            v_map = settled[v]
            if stop_idx in v_map or len(v_map) >= max_k:
                continue
            next_cost = cost + weight
            if len(v_map) >= min_k and next_cost > max_dist:
                continue
            heapq.heappush(heap, (next_cost, stop_idx, v))

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

    # 1. 一般プロファイル (edge[3]): min_k=6 以上、かつ 600m 以内を漏れなく探索
    adj_gen: list[list[tuple[int, float]]] = [[] for _ in range(n_nodes)]
    for u, v, _, eff_gen, _, _ in edges:
        adj_gen[u].append((v, eff_gen))
        adj_gen[v].append((u, eff_gen))
    print(f"Running exact<={EXACT_COVERAGE_CUTOFF_M}m (min_k={MIN_CANDIDATES}) Dijkstra (general)...", flush=True)
    settled_gen = k_best_dijkstra(n_nodes, adj_gen, stop_nodes, MIN_CANDIDATES, EXACT_COVERAGE_CUTOFF_M, MAX_CANDIDATES_CAP)
    del adj_gen

    # 2. 高齢者プロファイル (edge[4]): 一般側で 600m 以内に入った停留所の高齢者コストも欠落しないよう 1200m まで探索
    adj_eld: list[list[tuple[int, float]]] = [[] for _ in range(n_nodes)]
    for u, v, _, _, eff_eld, _ in edges:
        adj_eld[u].append((v, eff_eld))
        adj_eld[v].append((u, eff_eld))
    print(f"Running exact<={ELDERLY_SEARCH_CUTOFF_M}m (min_k={MIN_CANDIDATES}) Dijkstra (elderly)...", flush=True)
    settled_eld = k_best_dijkstra(n_nodes, adj_eld, stop_nodes, MIN_CANDIDATES, ELDERLY_SEARCH_CUTOFF_M, MAX_CANDIDATES_CAP)
    del adj_eld

    # 3. 各建物の候補停留所 [stopIdx, round(effGen, 1), round(effEld, 1)] をまとめる
    #    ※最低 MIN_CANDIDATES 件、および一般実効距離が EXACT_COVERAGE_CUTOFF_M 以下の停留所をすべて収録
    building_candidates: list[list[int | float]] = []
    mismatch_count = 0
    max_cand_count = 0
    total_cand_count = 0

    for row in scores:
        b_node = row["networkNode"]
        gen_map = settled_gen[b_node]
        eld_map = settled_eld[b_node]

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
            best_g, _, _, _ = items[0]
            if abs(best_g - row["busEffectiveDistanceM_general"]) > 0.2:
                mismatch_count += 1
        flat: list[int | float] = []
        kept = 0
        for g, sid, g_r, e_r in items:
            if kept < MIN_CANDIDATES or g <= EXACT_COVERAGE_CUTOFF_M:
                flat.extend([sid, g_r, e_r])
                kept += 1
            else:
                break
        max_cand_count = max(max_cand_count, kept)
        total_cand_count += kept
        building_candidates.append(flat)

    avg_cand = total_cand_count / max(len(building_candidates), 1)
    payload = {
        "version": version,
        "k": MIN_CANDIDATES,
        "cutoffMeters": EXACT_COVERAGE_CUTOFF_M,
        "maxCandidatesPerBuilding": max_cand_count,
        "format": "flat_triples_by_score_row_index: [stopIdx, effGen, effEld, ...]",
        "rows": building_candidates,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    size_mb = OUTPUT_JSON.stat().st_size / (1024 * 1024)
    print(
        f"Wrote {OUTPUT_JSON.name}: {len(building_candidates)} buildings, "
        f"avg_k={avg_cand:.2f}, max_k={max_cand_count}, "
        f"mismatches={mismatch_count}, size={size_mb:.2f}MB",
        flush=True,
    )


if __name__ == "__main__":
    main()
