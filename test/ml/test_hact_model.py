"""Unit test for ml.models.hact_model"""
import unittest
import torch
import dgl
import os
import yaml
from dgl.data.utils import load_graphs

from histocartography.ml import HACTModel
from histocartography.utils.graph import set_graph_on_cuda
from histocartography.utils.io import download_box_link


IS_CUDA = torch.cuda.is_available()


class HACTModelTestCase(unittest.TestCase):
    """HACTModelTestCase class."""

    @classmethod
    def setUpClass(self):
        self.current_path = os.path.dirname(__file__)
        self.data_path = os.path.join(self.current_path, '..', 'data')
        self.model_fname = os.path.join(self.data_path, 'models', 'tg_model.pt')
        self.tg_graph_path = os.path.join(self.data_path, 'tissue_graphs')
        self.tg_graph_name = '283_dcis_4_tg.bin'
        self.cg_graph_path = os.path.join(self.data_path, 'cell_graphs')
        self.cg_graph_name = '283_dcis_4.bin'

    def test_hact_model(self):
        """Test HACT model."""

        # 1. Load a cell graph 
        cell_graph, _ = load_graphs(os.path.join(self.cg_graph_path, self.cg_graph_name))
        cell_graph = cell_graph[0]
        cell_graph = set_graph_on_cuda(cell_graph) if IS_CUDA else cell_graph
        cg_node_dim = cell_graph.ndata['feat'].shape[1]

        tissue_graph, _ = load_graphs(os.path.join(self.tg_graph_path, self.tg_graph_name))
        tissue_graph = tissue_graph[0]
        tissue_graph.ndata['feat'] = torch.cat(
            (tissue_graph.ndata['feat'].float(),
            (tissue_graph.ndata['centroid']).float()),
            dim=1
        )
        tissue_graph = set_graph_on_cuda(tissue_graph) if IS_CUDA else tissue_graph
        tg_node_dim = tissue_graph.ndata['feat'].shape[1]

        assignment_matrix = torch.randint(2, (tissue_graph.number_of_nodes(), cell_graph.number_of_nodes())).float()
        assignment_matrix = assignment_matrix.cuda() if IS_CUDA else assignment_matrix
        assignment_matrix = [assignment_matrix]  # ie. batch size is 1. 
        
        # 2. load config 
        config_fname = os.path.join(self.current_path, 'config', 'hact_model.yml')
        with open(config_fname, 'r') as file:
            config = yaml.load(file)

        model = HACTModel(
            cg_gnn_params=config['cg_gnn_params'],
            tg_gnn_params=config['tg_gnn_params'],
            classification_params=config['classification_params'],
            cg_node_dim=cg_node_dim,
            tg_node_dim=tg_node_dim,
            num_classes=3
        )

        # 4. forward pass
        logits = model(cell_graph, tissue_graph, assignment_matrix)

        self.assertIsInstance(logits, torch.Tensor)
        self.assertEqual(logits.shape[0], 1)
        self.assertEqual(logits.shape[1], 3) 

    def tearDown(self):
        """Tear down the tests."""


if __name__ == "__main__":
    unittest.main()