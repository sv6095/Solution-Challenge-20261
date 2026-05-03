"""
gnn_model.py — Trained GNN Risk Propagation (PyTorch Geometric)
================================================================
Replaces the heuristic distance-based scoring in gnn_stub.py with
learned GraphSAGE + GAT message-passing on the supply chain graph.

Architecture:
  Input features (per node):   [proximity, severity, tier, criticality,
                                single_source, contract_value_log, safety_stock_inv,
                                substitutability_avg, location_precision_enc]
  
  Layer 1: SAGEConv(in=9, out=32)   — aggregate neighbor features
  Layer 2: GATConv(32, 16, heads=2) — attention-weighted aggregation
  Layer 3: Linear(32, 1)            — risk score prediction (sigmoid output)

Training data source:
  Historical incidents from governance_feedback table:
    - TRUE_POSITIVE incidents → affected nodes get label 1.0
    - FALSE_POSITIVE incidents → affected nodes get label 0.0
    - Each incident's graph structure provides edge_index

Fallback:
  If no trained model exists at MODEL_WEIGHTS_PATH, propagate_risk()
  transparently falls back to the gnn_stub heuristic. This ensures
  zero downtime during the training bootstrap phase.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Lazy imports for PyTorch Geometric (heavy) ────────────────────────────────

_torch_available = False
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.nn import SAGEConv, GATConv
    from torch_geometric.data import Data
    _torch_available = True
except ImportError:
    pass

from ml.gnn_stub import (
    SupplierNode,
    SupplyEdge,
    DisruptionEvent,
    GNNResult,
    SupplyChainGraph,
    _haversine_km,
    _proximity_score,
    _criticality_weight,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

_ML_DIR = Path(__file__).resolve().parent
MODEL_WEIGHTS_PATH = _ML_DIR / "gnn_weights.pt"
TRAINING_LOG_PATH = _ML_DIR / "gnn_training_log.json"

# ── Feature engineering ───────────────────────────────────────────────────────

FEATURE_DIM = 9

def _encode_node_features(
    node: SupplierNode,
    event: DisruptionEvent,
    graph: SupplyChainGraph,
) -> list[float]:
    """
    Encode a SupplierNode into a fixed-size feature vector.
    All values normalized to [0, 1] range for stable training.
    """
    # 1. Proximity to event (0-1)
    proximity = _proximity_score(event, node)

    # 2. Event severity normalized (0-1)
    severity_norm = min(1.0, event.severity / 10.0)

    # 3. Tier (0=logistics, 1-3=supplier tiers) → normalized
    tier_norm = min(1.0, node.tier / 3.0) if node.tier > 0 else 0.0

    # 4. Criticality encoded
    crit_map = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}
    criticality_enc = crit_map.get(node.criticality, 0.5)

    # 5. Single source flag
    single_source = 1.0 if node.single_source else 0.0

    # 6. Contract value (log-scaled, normalized)
    contract_log = math.log1p(node.contract_value_usd) / 20.0  # log($1B) ≈ 20.7

    # 7. Safety stock inverse (lower stock = higher risk)
    safety_inv = 1.0 / max(1.0, node.safety_stock_days)

    # 8. Average substitutability of connected edges
    neighbors = graph._adj.get(node.id, [])
    if neighbors:
        avg_sub = sum(edge.substitutability for _, edge in neighbors) / len(neighbors)
    else:
        avg_sub = 0.5
    sub_inv = 1.0 - avg_sub  # low substitutability = high risk

    # 9. Location precision (exact=0, country=0.5, synthetic=1.0)
    prec_map = {"exact": 0.0, "country": 0.5, "synthetic": 1.0}
    precision_enc = prec_map.get(node.location_precision, 0.5)

    return [
        proximity, severity_norm, tier_norm, criticality_enc,
        single_source, contract_log, safety_inv, sub_inv, precision_enc,
    ]


def _build_pyg_data(
    graph: SupplyChainGraph,
    event: DisruptionEvent,
    labels: dict[str, float] | None = None,
) -> tuple[Any, list[str]]:
    """
    Convert SupplyChainGraph + DisruptionEvent → PyG Data object.
    
    Returns:
        (Data, node_id_order) where node_id_order maps tensor indices to node IDs.
    """
    if not _torch_available:
        raise RuntimeError("PyTorch Geometric not available")

    node_ids = list(graph.nodes.keys())
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

    # Node features
    features = []
    for nid in node_ids:
        features.append(_encode_node_features(graph.nodes[nid], event, graph))
    x = torch.tensor(features, dtype=torch.float32)

    # Edge index (COO format)
    src_list, dst_list = [], []
    for edge in graph.edges:
        if edge.from_id in id_to_idx and edge.to_id in id_to_idx:
            src_list.append(id_to_idx[edge.from_id])
            dst_list.append(id_to_idx[edge.to_id])
            # Undirected: add reverse edge
            src_list.append(id_to_idx[edge.to_id])
            dst_list.append(id_to_idx[edge.from_id])

    if src_list:
        edge_index = torch.tensor([src_list, dst_list], dtype=torch.long)
    else:
        # No edges: self-loops for each node so GNN layers don't fail
        self_loops = list(range(len(node_ids)))
        edge_index = torch.tensor([self_loops, self_loops], dtype=torch.long)

    # Labels (for training)
    if labels:
        y = torch.tensor(
            [labels.get(nid, 0.0) for nid in node_ids],
            dtype=torch.float32,
        )
    else:
        y = torch.zeros(len(node_ids), dtype=torch.float32)

    data = Data(x=x, edge_index=edge_index, y=y)
    return data, node_ids


# ── Model definition ─────────────────────────────────────────────────────────

if _torch_available:
    class SupplyChainGNN(nn.Module):
        """
        Two-layer GNN: GraphSAGE aggregation → GAT attention → risk score.
        
        GraphSAGE captures structural neighborhood patterns.
        GAT attention learns which neighbors matter most.
        Final linear layer outputs per-node risk probability.
        """
        def __init__(self, in_channels: int = FEATURE_DIM, hidden: int = 32, heads: int = 2):
            super().__init__()
            self.sage = SAGEConv(in_channels, hidden)
            self.gat = GATConv(hidden, hidden // heads, heads=heads, concat=True)
            self.lin = nn.Linear(hidden, 1)
            self.dropout = nn.Dropout(0.2)

        def forward(self, data: Data) -> torch.Tensor:
            x, edge_index = data.x, data.edge_index

            # Layer 1: GraphSAGE
            x = self.sage(x, edge_index)
            x = F.elu(x)
            x = self.dropout(x)

            # Layer 2: GAT
            x = self.gat(x, edge_index)
            x = F.elu(x)
            x = self.dropout(x)

            # Output: risk score per node
            x = self.lin(x)
            return torch.sigmoid(x).squeeze(-1)


# ── Training ─────────────────────────────────────────────────────────────────

def _load_training_data_from_feedback() -> list[dict[str, Any]]:
    """
    Extract training samples from governance_feedback + incidents tables.
    
    Each sample = {
        "incident_id": ...,
        "verdict": "TRUE_POSITIVE" | "FALSE_POSITIVE",
        "affected_nodes": [...],  # node IDs
        "event": {...},           # disruption event details
    }
    """
    from services.local_store import DB_PATH
    
    samples = []
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        
        # Get all feedback records with incident details
        rows = con.execute("""
            SELECT gf.incident_id, gf.verdict, gf.affected_stage,
                   i.payload_json
            FROM governance_feedback gf
            LEFT JOIN incidents i ON gf.incident_id = i.incident_id
            WHERE gf.verdict IN ('TRUE_POSITIVE', 'FALSE_POSITIVE')
            ORDER BY gf.created_at DESC
            LIMIT 500
        """).fetchall()
        
        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}") if row["payload_json"] else {}
                affected_nodes = []
                for node in payload.get("affected_nodes", []):
                    if isinstance(node, dict) and node.get("id"):
                        affected_nodes.append(node["id"])
                
                event_data = {
                    "id": row["incident_id"],
                    "title": payload.get("event_title", ""),
                    "event_type": payload.get("event_type", ""),
                    "severity": float(payload.get("severity_raw", payload.get("severity", 5.0)) or 5.0),
                    "lat": float(payload.get("lat", 0)),
                    "lng": float(payload.get("lng", 0)),
                    "radius_km": float(payload.get("radius_km", 500)),
                    "duration_days": float(payload.get("duration_days", 7)),
                }
                
                samples.append({
                    "incident_id": row["incident_id"],
                    "verdict": row["verdict"],
                    "affected_nodes": affected_nodes,
                    "event": event_data,
                })
            except Exception:
                continue
        
        con.close()
    except Exception:
        pass
    
    return samples


def train_gnn_model(
    graph: SupplyChainGraph,
    epochs: int = 100,
    lr: float = 0.01,
    min_samples: int = 5,
) -> dict[str, Any]:
    """
    Train the GNN model on historical feedback data.
    
    Returns training report with loss curve and metrics.
    
    Requires at least `min_samples` TRUE_POSITIVE + FALSE_POSITIVE
    feedback records to produce meaningful weights.
    """
    if not _torch_available:
        return {"status": "skipped", "reason": "PyTorch Geometric not installed"}

    samples = _load_training_data_from_feedback()
    
    if len(samples) < min_samples:
        return {
            "status": "insufficient_data",
            "samples_found": len(samples),
            "min_required": min_samples,
            "reason": f"Need at least {min_samples} feedback records. "
                      f"Found {len(samples)}. Submit more governance feedback.",
        }

    model = SupplyChainGNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = nn.BCELoss()

    training_log: list[dict] = []
    best_loss = float("inf")

    model.train()
    for epoch in range(epochs):
        epoch_loss = 0.0
        batch_count = 0

        for sample in samples:
            # Build labels: affected nodes in TRUE_POSITIVE get 1.0,
            # affected nodes in FALSE_POSITIVE get 0.0 (they were wrongly flagged)
            labels: dict[str, float] = {}
            if sample["verdict"] == "TRUE_POSITIVE":
                for nid in sample["affected_nodes"]:
                    labels[nid] = 1.0
            elif sample["verdict"] == "FALSE_POSITIVE":
                for nid in sample["affected_nodes"]:
                    labels[nid] = 0.0

            if not labels:
                continue

            # Build event
            ev = sample["event"]
            event = DisruptionEvent(
                id=ev["id"],
                title=ev.get("title", ""),
                event_type=ev.get("event_type", ""),
                severity=ev.get("severity", 5.0),
                lat=ev.get("lat", 0.0),
                lng=ev.get("lng", 0.0),
                radius_km=ev.get("radius_km", 500.0),
                duration_days=ev.get("duration_days", 7.0),
            )

            try:
                data, node_ids = _build_pyg_data(graph, event, labels)
            except Exception:
                continue

            # Mask: only compute loss on nodes we have labels for
            id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
            mask_indices = [id_to_idx[nid] for nid in labels if nid in id_to_idx]
            if not mask_indices:
                continue

            mask = torch.zeros(len(node_ids), dtype=torch.bool)
            mask[mask_indices] = True

            optimizer.zero_grad()
            pred = model(data)
            loss = loss_fn(pred[mask], data.y[mask])
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            batch_count += 1

        if batch_count > 0:
            avg_loss = epoch_loss / batch_count
            if avg_loss < best_loss:
                best_loss = avg_loss
                torch.save(model.state_dict(), MODEL_WEIGHTS_PATH)

            if epoch % 10 == 0 or epoch == epochs - 1:
                training_log.append({
                    "epoch": epoch,
                    "avg_loss": round(avg_loss, 6),
                    "best_loss": round(best_loss, 6),
                })

    # Save training log
    report = {
        "status": "trained",
        "epochs": epochs,
        "samples_used": len(samples),
        "best_loss": round(best_loss, 6),
        "model_path": str(MODEL_WEIGHTS_PATH),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_log": training_log,
    }
    try:
        TRAINING_LOG_PATH.write_text(json.dumps(report, indent=2))
    except Exception:
        pass

    return report


# ── Inference ────────────────────────────────────────────────────────────────

def _load_trained_model() -> Any:
    """Load trained model weights if available."""
    if not _torch_available:
        return None
    if not MODEL_WEIGHTS_PATH.exists():
        return None
    try:
        model = SupplyChainGNN()
        model.load_state_dict(torch.load(MODEL_WEIGHTS_PATH, weights_only=True))
        model.eval()
        return model
    except Exception:
        return None


# Module-level cached model (loaded once)
_cached_model = None
_cached_model_mtime = 0.0


def _get_model():
    """Get the trained model with file-modification caching."""
    global _cached_model, _cached_model_mtime
    if not MODEL_WEIGHTS_PATH.exists():
        return None
    mtime = MODEL_WEIGHTS_PATH.stat().st_mtime
    if _cached_model is None or mtime != _cached_model_mtime:
        _cached_model = _load_trained_model()
        _cached_model_mtime = mtime
    return _cached_model


def propagate_risk_learned(
    graph: SupplyChainGraph,
    event: DisruptionEvent,
    affected_score_threshold: float = 0.3,
) -> GNNResult | None:
    """
    Run the trained GNN model for risk propagation.
    
    Returns GNNResult if trained model is available, None otherwise.
    The caller should fall back to gnn_stub.propagate_risk() on None.
    """
    model = _get_model()
    if model is None:
        return None

    if not _torch_available:
        return None

    try:
        data, node_ids = _build_pyg_data(graph, event)
    except Exception:
        return None

    try:
        with torch.no_grad():
            scores_tensor = model(data)
        scores = {nid: float(scores_tensor[i]) for i, nid in enumerate(node_ids)}
    except Exception:
        return None

    # Post-process: compute financial impact for nodes above threshold
    severity_factor = min(1.0, event.severity / 10.0)
    affected: list[SupplierNode] = []
    max_exposure = 0.0
    min_stockout = 999.0

    for nid, score in scores.items():
        if score < affected_score_threshold:
            continue
        node = graph.nodes[nid]
        node.risk_score = round(score, 3)

        duration_factor = min(1.0, event.duration_days / 30.0)
        node.exposure_usd = round(node.contract_value_usd * score * duration_factor, 2)

        if severity_factor > 0:
            node.days_to_stockout = round(
                node.safety_stock_days / (1 + severity_factor * score), 1
            )
        else:
            node.days_to_stockout = node.safety_stock_days

        # BOM granularity: perishables degrade into total loss
        if node.product_category.lower() in ("cold-chain", "perishable", "hazardous"):
            if node.days_to_stockout < node.safety_stock_days - 1.0:
                node.exposure_usd = node.contract_value_usd
                node.days_to_stockout = 0.0

        max_exposure = max(max_exposure, node.exposure_usd)
        min_stockout = min(min_stockout, node.days_to_stockout)
        affected.append(node)

    affected.sort(key=lambda n: n.risk_score, reverse=True)

    # GNN confidence is higher when using learned weights
    if affected:
        avg_score = sum(n.risk_score for n in affected) / len(affected)
        confidence = min(0.98, 0.82 + avg_score * 0.15 + min(0.05, len(affected) * 0.005))
    else:
        confidence = 0.0

    return GNNResult(
        event=event,
        affected_nodes=affected,
        all_scores=scores,
        max_exposure_usd=max_exposure,
        min_stockout_days=min_stockout if min_stockout < 999 else 0,
        confidence=round(confidence, 3),
    )
