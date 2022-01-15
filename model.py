from tokenize import group
import torch
import torch.nn as nn
import torch.nn.functional as F

import torchvision.models as models

import numpy as np

ADULT_DATASET_FEATURE_SIZE = 105
NODE_SIZE = 80


def drop_classification_layer(model):
    return torch.nn.Sequential(*(list(model.children())[:-1]))


def get_model(dataset_name: str, pretrained: bool=True):
    """
    Returns the model architecture for the provided dataset_name. 
    """
    if dataset_name == 'adult':
        model = nn.Sequential(
            nn.Linear(ADULT_DATASET_FEATURE_SIZE, NODE_SIZE),
            nn.SELU()
            )
        out_features = NODE_SIZE

    elif dataset_name == 'celeba':
        model = models.resnet50(pretrained=pretrained)
        model = drop_classification_layer(model)
        out_features = 2048

    elif dataset_name == 'civilcomments':
        bert_model = torch.hub.load('huggingface/pytorch-transformers', 'model', 'bert-base-uncased')
        fc_model = nn.Sequential(
            nn.Linear(1024, NODE_SIZE),
            nn.SELU()
            )
        model = torch.nn.Sequential(bert_model, fc_model)
        out_features = NODE_SIZE

    elif dataset_name =='chexpert':
        model = models.densenet121(pretrained=pretrained)
        model = drop_classification_layer(model)
        model = nn.Sequential(model, nn.AdaptiveMaxPool2d((1,1)))
        out_features = 1024
        
    else:
        assert False, f'Unknown network architecture \"{dataset_name}\"'
        
    return out_features, model


class FairClassifier(nn.Module):
    def __init__(self, input_model: str, nr_attr_values: int = 2):
        """
        FairClassifier Model
        """
        super(FairClassifier, self).__init__()
        in_features, self.featurizer = get_model(input_model)

        # Fully Connected models for binary classes
        self.group_specific_models = nn.ModuleList([nn.Linear(in_features, 1) for key in range(nr_attr_values)])

        # Join Classifier T
        self.joint_classifier = nn.Linear(in_features, 1)

    def split(self, x: torch.Tensor, d: torch.Tensor):
        # Groups x samples based on d-values
        sorter = torch.argsort(d, dim=1)
        _, counts = torch.unique(d, return_counts=True)
        return sorter, torch.split(torch.squeeze(x[sorter, :]), counts.tolist())

    def group_forward(self, x: torch.Tensor, d: torch.Tensor):
        """ The forward pass of the group specific models. """

        features = self.featurizer(x).squeeze()

        # Sort the inputs on the value of d
        group_indices, group_splits = self.split(features, d)

        group_pred = torch.zeros(features.shape[0], device=self.device())
        group_pred[group_indices] = torch.cat([self.group_specific_models[i](group_split) for i, group_split in enumerate(group_splits)])

        return torch.sigmoid(group_pred)

    def joint_forward(self, x: torch.Tensor) -> torch.Tensor:
        """Returns the model prediction by the joint classifier

        Args:
            x (torch.Tensor): the input values for the classifer

        Returns:
            torch.Tensor: the label prediction by the joint classifer
        """
        features = self.featurizer(x).squeeze()
        joint_pred = self.joint_classifier(features)

        return torch.sigmoid(joint_pred).squeeze()

    # def forward(self, x: torch.Tensor, d_true: torch.Tensor, d_random: torch.Tensor):
    #     """
    #     Forward Pass
    #     """
    #     # x = (x - x.mean()) / torch.sqrt(x.var())
    #     features = self.featurizer(x).squeeze()

    #     joint_y = self.joint_classifier(features)

    #     # Split on random sampled d-values
    #     random_indices, (random_d_0, random_d_1) = self.split(features, d_random)

    #     # Split on true d-values
    #     group_indices, (group_d_0, group_d_1) = self.split(features, d_true)

    #     group_agnostic_y = torch.zeros(features.shape[0], device=self.device())
    #     group_specific_y = torch.zeros(features.shape[0], device=self.device())

    #     group_agnostic_y[random_indices] = torch.cat([self.fc0(random_d_0), self.fc1(random_d_1)])
    #     group_specific_y[group_indices] = torch.cat([self.fc0(group_d_0), self.fc1(group_d_1)])

    #     return torch.sigmoid(joint_y).squeeze(), torch.sigmoid(group_specific_y), torch.sigmoid(group_agnostic_y)

    def device(self):
        return next(self.parameters()).device