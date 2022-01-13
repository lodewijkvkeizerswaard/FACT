from posixpath import join
import torch
from torch import nn
import numpy as np

import os
from torch.nn.modules import loss
from tqdm import tqdm
import argparse

from data import get_train_validation_set, get_test_set
from model import FairClassifier

LAMBDA = 0.7 

def set_seed(seed: int):
    """
    Function for setting the seed for reproducibility.
    """
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.determinstic = True
    torch.backends.cudnn.benchmark = False

def generate_random_attributes(attributes):
    idx = torch.randperm(attributes.shape[0])
    return attributes[idx].view(attributes.size())

def calculate_overall_loss(target: torch.Tensor, joint_y: torch.Tensor, group_specific_y: torch.Tensor, 
                            group_agnostic_y: torch.Tensor, loss_module):
    """
    Calculates Regularized Loss Function
    """
    group_specific_loss = loss_module(group_specific_y, target)
    group_agnostic_loss = loss_module(group_agnostic_y, target)
    joint_loss = loss_module(joint_y, target)

    overall_loss = joint_loss + LAMBDA * (group_specific_loss - group_agnostic_loss)
    return overall_loss

def train_epoch(model, optimizer, train_loader, loss_module, device):
    for modality, target, attributes in train_loader:
        optimizer.zero_grad()
        target = torch.squeeze(target.to(device))

        random_attribute = generate_random_attributes(attributes)

        joint_y, group_spec_y, group_agno_y = model.forward(
                modality.to(device),
                attributes.to(device),
                random_attribute.to(device))

        overall_loss = calculate_overall_loss(target, joint_y, group_spec_y, group_agno_y, loss_module)

        overall_loss.backward()
        optimizer.step()


def train_model(model: nn.Module, dataset: str, lr: float, batch_size: int, 
                epochs: int, checkpoint_name: str, device: str):
    """
    Trains a given model architecture for the specified hyperparameters.

    Args:
        model: Model architecture to train.
        dataset: Specifiec dataset.
        lr: Learning rate to use in the optimizer.
        batch_size: Batch size to train the model with.
        epochs: Number of epochs to train the model for.
        checkpoint_name: Filename to save the best model on validation to.
        device: Device to use for training.
    Returns:
        model: Model that has performed best on the validation set.

    TODO:
    Implement the training of the model with the specified hyperparameters
    Save the best model to disk so you can load it later.
    """

    # Load the datasets
    train_set, val_set = get_train_validation_set(dataset)
    train_loader = torch.utils.data.DataLoader(train_set, batch_size=batch_size,
                                               shuffle=True, num_workers=2, drop_last=True)
    # validation_loader = torch.utils.data.DataLoader(val_set, batch_size=batch_size,
    #                                                 shuffle=True, num_workers=2)

    # Initialize the optimizer and loss function
    group_specific_params = []
    group_specific_params.extend(model.fc0.parameters())
    group_specific_params.extend(model.fc1.parameters())
    join_classifier_params = []
    join_classifier_params.extend(model.featurizer.parameters())
    join_classifier_params.extend(model.joint_classifier.parameters())

    group_specific_optimizer = torch.optim.SGD(group_specific_params, lr=lr)
    joint_classifier_optimizer = torch.optim.SGD(join_classifier_params, lr=lr)

    loss_module = nn.BCELoss()

    # Training loop with validation after each epoch. Save the best model, and remember to use the lr scheduler.
    best_accuracy = 0
    for epoch in tqdm(range(epochs)):
        train_epoch(model, group_specific_optimizer, train_loader, loss_module, device)
        train_epoch(model, joint_classifier_optimizer, train_loader, loss_module, device)
        
        # if train_accuracy > best_accuracy:
        #     best_accuracy = train_accuracy
        #     torch.save(model.state_dict(), "models/" + checkpoint_name)

    # Load best model and return it.
    model.load_state_dict(torch.load("models/" + checkpoint_name))
    torch.save(model.state_dict(), "models/finished_" + checkpoint_name)

    return model

def num_correct_predictions(predictions, targets):
    predictions = (predictions > 0.5)
    count = (predictions == targets).sum()
    return count.item()

def evaluate_model(model, data_loader, device):
    """
    Evaluates a trained model on a given dataset.

    Args:
        model: Model architecture to evaluate.
        data_loader: The data loader of the dataset to evaluate on.
        device: Device to use for training.
    Returns:
        accuracy: The accuracy on the dataset.

    TODO:
    Implement the evaluation of the model on the dataset.
    Remember to set the model in evaluation mode and back to training mode in the training loop.
    """

    num_correct = 0
    total_samples = 0

    with torch.no_grad():
        for modality, target, attributes in data_loader:
            target = torch.squeeze(target.to(device))

            random_attribute = generate_random_attributes(attributes)

            joint_y = model.forward(
                modality.to(device),
                attributes.to(device),
                random_attribute.to(device))
            
            num_correct += num_correct_predictions(joint_y, target)
            total_samples += len(modality)

    avg_accuracy = num_correct / total_samples

    return avg_accuracy


def test_model(model, dataset, batch_size, device, seed):
    """
    Tests a trained model on the test set with all corruption functions.

    Args:
        model: Model architecture to test.
        dataset: Specify dataset where test_set is loaded from.
        batch_size: Batch size to use in the test.
        device: Device to use for training.
        seed: The seed to set before testing to ensure a reproducible test.
    Returns:
        test_results: Dictionary containing an overview of the accuracies achieved on the different
                      corruption functions and the plain test set.

    TODO:
    Evaluate the model on the plain test set. Make use of the evaluate_model function.
    For each corruption function and severity, repeat the test. 
    Summarize the results in a dictionary (the structure inside the dict is up to you.)
    """

    set_seed(seed)
    test_set = get_test_set(dataset)
    test_loader = torch.utils.data.DataLoader(test_set, batch_size=batch_size,
                                                shuffle=True, num_workers=2)
    test_result = evaluate_model(model, test_loader, device)
    
    return test_result

def main(dataset: str, lr: float, batch_size: int, epochs: int, seed: int):
    """
    Function that summarizes the training and testing of a model.

    Args:
        dataset: Dataset to test.
        batch_size: Batch size to use in the test.
        device: Device to use for training.
        seed: The seed to set before testing to ensure a reproducible test.
    Returns:
        test_results: Dictionary containing an overview of the accuracies achieved on the different
                      corruption functions and the plain test set.

    TODO:
    Load model according to the model name.
    Train the model (recommendation: check if you already have a saved model. If so, skip training and load it)
    Test the model using the test_model function.
    Save the results to disk.
    """

    device = torch.device(
        "cuda:0") if torch.cuda.is_available() else torch.device("cpu")
    set_seed(seed)

    checkpoint_name = dataset+ '.pt'
    model = FairClassifier(dataset).to(device)
    if os.path.exists("models/finished_" + checkpoint_name):
        model.load_state_dict(torch.load("models/finished_" + checkpoint_name))
    else:
        model = train_model(model, dataset, lr, batch_size, epochs,
                            checkpoint_name, device)
    test_results = test_model(model, batch_size, dataset, device, seed)
    return test_results

if __name__ == '__main__':
    # Command line arguments
    parser = argparse.ArgumentParser()
    
    # Model hyperparameters
    parser.add_argument('--dataset', default='adult', type=str,
                        help='Name of the dataset to evaluate on.')
    
    # Optimizer hyperparameters
    parser.add_argument('--lr', default=0.01, type=float,
                        help='Learning rate to use')
    parser.add_argument('--batch_size', default=256, type=int,
                        help='Minibatch size')

    # Other hyperparameters
    parser.add_argument('--epochs', default=20, type=int,
                        help='Max number of epochs')
    parser.add_argument('--seed', default=42, type=int,
                        help='Seed to use for reproducing results')

    args = parser.parse_args()
    kwargs = vars(args)

    main(**kwargs)
        