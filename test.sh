#!/bin/bash

flake8 -j$(nproc) *.py
pylint -j$(nproc) *.py
