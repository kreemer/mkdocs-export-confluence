#!/bin/bash
set -e
sudo apt-get install -y bats
pip install -e .
pip install mkdocs mkdocs-material
