#!/bin/bash

cd data

# ADULT DATASET
if [ ! -d "adult" ]; then
    mkdir adult
fi

cd adult
wget https://archive.ics.uci.edu/ml/machine-learning-databases/adult/adult.data
wget https://archive.ics.uci.edu/ml/machine-learning-databases/adult/adult.test


# CHEXPERT DATASET
URL = "" # See README.md

if [ ! -d "chexpert" ]; then
    mkdir chexpert
fi