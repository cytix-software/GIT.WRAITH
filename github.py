from typing import Dict
import shutil
import os
import git
import re

def is_github_url(url):
    pattern = r'^https:\/\/github\.com\/([a-zA-Z0-9._-]+)\/([a-zA-Z0-9._-]+)\/?$'
    return re.match(pattern, url) is not None

def get_repo(github_url, clone_dir="/tmp/repo") -> Dict[str, str]:
    if not is_github_url(github_url):
        raise ValueError("Invalid GitHub URL")

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

    file_contents = {}
    for root, dirs, files in os.walk(clone_dir):
        for file in files:
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, clone_dir)

            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    file_contents[rel_path] = content
            except Exception as e:
                print(f"Skipping {rel_path}: {e}")

    return file_contents