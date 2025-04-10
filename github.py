import tempfile
from typing import Dict
import shutil
import os
import git
import re

def is_github_url(url):
    pattern = r'^https:\/\/github\.com\/([a-zA-Z0-9._-]+)\/([a-zA-Z0-9._-]+)\/?$'
    return re.match(pattern, url) is not None

def get_repo(github_url, clone_dir="./.git_wraith_repo") -> Dict[str, str]:
    if not is_github_url(github_url):
        raise ValueError("Invalid GitHub URL")

    # Backup the wraith.docs folder if it exists
    wraith_docs_path = os.path.join(clone_dir, "wraith.docs")
    temp_wraith_path = None

    if os.path.exists(wraith_docs_path):
        temp_wraith_path = tempfile.mkdtemp()
        print(f"Preserving 'wraith.docs' to {temp_wraith_path}")
        shutil.move(wraith_docs_path, os.path.join(temp_wraith_path, "wraith.docs"))

    # Clear and recreate the clone directory
    if os.path.exists(clone_dir):
        print(f"Clearing directory {clone_dir}...")
        shutil.rmtree(clone_dir)
    os.makedirs(clone_dir)

    # Clone the repository
    try:
        print(f"Cloning repository from {github_url}...")
        repo = git.Repo.clone_from(github_url, clone_dir)
    except Exception as e:
        raise ValueError(f"Failed to clone repository: {str(e)}")

    # Restore the wraith.docs folder
    if temp_wraith_path:
        try:
            shutil.move(os.path.join(temp_wraith_path, "wraith.docs"), wraith_docs_path)
            print("Restored 'wraith.docs' to repo directory.")
            shutil.rmtree(temp_wraith_path)
        except Exception as e:
            print(f"Warning: Failed to restore 'wraith.docs': {e}")

    # Read file contents
    file_contents = {}
    for root, dirs, files in os.walk(clone_dir):
        for file in files:
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, clone_dir)

    return file_contents
