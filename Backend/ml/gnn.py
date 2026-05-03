import logging

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.nn import SAGEConv, GATConv
    HAS_PYG = True
except ImportError:
    HAS_PYG = False
    logger.warning("PyTorch Geometric is not installed. SupplyChainGNN will run in fallback stub mode.")

class SupplyChainGNN(nn.Module if HAS_PYG else object):
    """
    GraphSAGE + GAT architecture for multi-tier supply chain risk propagation.
    Inductive learning handles new supplier nodes added after training.
    """
    def __init__(self, node_feat_dim=14, edge_feat_dim=7, hidden_dim=128, output_dim=1):
        if not HAS_PYG:
            return # Stub mode
            
        super().__init__()
        # SAGEConv uses mean aggregation by default
        # We add edge features via a separate edge MLP
        self.conv1 = SAGEConv(node_feat_dim, hidden_dim)
        self.conv2 = SAGEConv(hidden_dim, hidden_dim)
        self.attn  = GATConv(hidden_dim, hidden_dim, heads=4, concat=False)
        self.head  = nn.Linear(hidden_dim, output_dim)  # risk score per node
        self.edge_mlp = nn.Sequential(
            nn.Linear(edge_feat_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1)                            # edge weight scalar
        )

    def forward(self, x, edge_index, edge_attr):
        if not HAS_PYG:
            raise NotImplementedError("PyTorch Geometric is required for forward pass.")
            
        edge_weights = self.edge_mlp(edge_attr).squeeze()
        x = F.relu(self.conv1(x, edge_index, edge_weights))
        x = F.relu(self.conv2(x, edge_index, edge_weights))
        x = self.attn(x, edge_index)
        return torch.sigmoid(self.head(x))              # 0–1 risk score per node

# Example inference helper placeholder
def forward_pass(graph_data, event_node_data):
    """
    Takes a snapshot of the current active graph from Firestore, 
    injects the event node, and passes it through the GNN.
    Returns: Dict[node_id, float risk_score]
    """
    if not HAS_PYG:
        # Fallback to stub if not installed
        from ml.gnn_stub import assign_weights
        return assign_weights(event_node_data)
        
    # TODO: Build PyG Data object from Firestore graph structure
    pass
