#!/bin/bash
pip install virtualenv
python -m virtualenv venv
venv/bin/pip install -r requirements.txt
npm install -g @mermaid-js/mermaid-cli
