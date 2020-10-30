"""This module handles all the graph building"""

import logging
from abc import abstractmethod
from typing import Union

import cv2
import dgl
import numpy as np
import pandas as pd
import torch
from dgl.data.utils import load_graphs, save_graphs
from skimage.measure import regionprops

from constants import CENTROID, GNN_EDGE_FEAT, GNN_NODE_FEAT_IN, LABEL
from utils import PipelineStep, fast_histogram


class BaseGraphBuilder(PipelineStep):
    """
    Base interface class for graph building.
    """

    def __init__(self, nr_classes: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.nr_classes = nr_classes

    def process(
        self,
        structure: np.ndarray,
        features: torch.Tensor,
        annotation: Union[None, np.ndarray] = None,
    ) -> dgl.DGLGraph:
        """Generates a graph with a given structure and features

        Args:
            structure (np.array): Structure, depending on the graph can be superpixel connectivity, or centroids
            features (torch.Tensor): Features of each node. Shape (nr_nodes, nr_features)
            annotation (Union[None, np.array], optional): Optional node level to include. Defaults to None.

        Returns:
            dgl.DGLGraph: The constructed graph
        """

        # add nodes
        num_nodes = features.shape[0]
        graph = dgl.DGLGraph()
        graph.add_nodes(num_nodes)

        # add node features
        self._set_node_features(features, graph)
        self._set_node_centroids(structure, graph)
        if annotation is not None:
            self._set_node_labels(structure, annotation, graph)

        # build edges
        self._build_topology(
            structure,
            graph,
        )
        return graph

    def process_and_save(
        self,
        structure: np.ndarray,
        features: torch.Tensor,
        output_name: str,
        annotation: Union[None, np.ndarray] = None,
    ) -> dgl.DGLGraph:
        assert (
            self.base_path is not None
        ), f"Can only save intermediate output if base_path was not None when constructing the object"
        output_path = self.output_dir / f"{output_name}.bin"
        if output_path.exists():
            logging.info(
                f"Output of {output_name} already exists, using it instead of recomputing"
            )
            graphs, _ = load_graphs(str(output_path))
            assert len(graphs) == 1
            graph = graphs[0]
        else:
            graph = self.process(
                structure=structure, features=features, annotation=annotation
            )
            save_graphs(str(output_path), [graph])
        return graph

    @staticmethod
    def _set_node_features(features: torch.Tensor, graph: dgl.DGLGraph) -> None:
        """Set the provided node features

        Args:
            features (torch.Tensor): Node features
            graph (dgl.DGLGraph): Graph to add the features to
        """
        graph.ndata[GNN_NODE_FEAT_IN] = features

    @staticmethod
    def _set_node_centroids(superpixels: np.ndarray, graph: dgl.DGLGraph) -> None:
        regions = regionprops(superpixels)
        centroids = np.empty((len(regions), 2))
        for i, region in enumerate(regions):
            center_x, center_y = region.centroid
            center_x = int(round(center_x))
            center_y = int(round(center_y))
            centroids[i, 0] = center_x
            centroids[i, 1] = center_y
        graph.ndata[CENTROID] = centroids

    def _set_node_labels(
        self, superpixels: np.ndarray, annotation: np.ndarray, graph: dgl.DGLGraph
    ) -> None:
        assert (
            self.nr_classes < 256
        ), f"Cannot handle that many classes with 8 byte representation"
        region_labels = pd.unique(np.ravel(superpixels))
        labels = torch.empty(len(region_labels), dtype=torch.uint8)
        for region_label in region_labels:
            assignment = np.argmax(
                fast_histogram(
                    annotation[superpixels == region_label], nr_values=self.nr_classes
                )
            )
            labels[region_label - 1] = int(assignment)
        graph.ndata[LABEL] = labels

    @abstractmethod
    def _build_topology(self, instances: np.ndarray, graph: dgl.DGLGraph) -> None:
        """Generate the graph topology from the provided structure

        Args:
            instances (np.array): Graph structure
            graph (dgl.DGLGraph): Graph to add the edges
        """

    def __repr__(self) -> str:
        """Representation of a graph builder

        Returns:
            str: Representation of a graph builder
        """
        return f'{self.__class__.__name__}({",".join([f"{k}={v}" for k, v in vars(self).items()])})'


class RAGGraphBuilder(BaseGraphBuilder):
    """
    Super-pixel Graphs class for graph building.
    """

    def __init__(self, kernel_size: int = 5, **kwargs) -> None:
        """Create a graph builder that uses a provided kernel size to detect connectivity

        Args:
            kernel_size (int, optional): Size of the kernel to detect connectivity. Defaults to 5.
        """
        logging.debug("*** RAG Graph Builder ***")
        self.kernel_size = kernel_size
        super().__init__(**kwargs)

    def _build_topology(self, instances: np.ndarray, graph: dgl.DGLGraph) -> None:
        """Create the graph topology from the connectivty of the provided superpixels

        Args:
            instances (np.array): Superpixels
            graph (dgl.DGLGraph): Graph to add the edges to
        """
        instance_ids = np.sort(pd.unique(np.ravel(instances))).astype(int)
        kernel = np.ones((self.kernel_size, self.kernel_size), np.uint8)
        adjacency = np.zeros(shape=(len(instance_ids), len(instance_ids)))
        for instance_id in instance_ids:
            mask = (instances == instance_id).astype(np.uint8)
            dilation = cv2.dilate(mask, kernel, iterations=1)
            boundary = dilation - mask
            idx = pd.unique(instances[boundary.astype(bool)])
            instance_id -= 1  # because instance_map id starts from 1
            idx -= 1  # because instance_map id starts from 1
            adjacency[instance_id, idx] = 1

        edge_list = np.nonzero(adjacency)
        graph.add_edges(list(edge_list[0]), list(edge_list[1]))
