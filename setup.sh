#!/bin/bash
#If you want it to stop asking for your password every time you try to clone a repo over ssh
#ssh-add -K ~/.ssh/id_rsa
pip install virtualenv
python -m virtualenv venv
venv/bin/pip install -r requirements.txt
npm install -g @mermaid-js/mermaid-cli
