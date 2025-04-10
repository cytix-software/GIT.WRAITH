import json
from bottle import route, request, response, get, post
from github import get_repo
import hashlib
import tempfile
import os
import random

random.seed(0)
tmp_dir = tempfile.mkdtemp()
def string_to_sha256(input_string):
    # Create a sha256 hash object
    sha256_hash = hashlib.sha256()

    # Update the hash object with the bytes of the input string
    sha256_hash.update(input_string.encode('utf-8'))

    # Return the hexadecimal representation of the hash
    return sha256_hash.hexdigest()

@route('/api')
def healthCheck():
  response.content_type = 'text/text; charset=UTF8'
  return "Wraith API Healthy"

def get_clone_dir(repo_url):
    return os.path.join(tmp_dir, string_to_sha256(repo_url))

@get('/api/scan')
@post('/api/scan')
def scan():
  if 'repo_url' in request.query: repo_url = request.query['repo_url']
  elif request.json and 'repo_url' in request.json: repo_url = request.json['repo_url']
  else:
    response.status = 400
    return { 'status': response.status, 'message': 'Bad Request - parameter repo_url is required.' }

  clone_dir = get_clone_dir(repo_url)

  # Attempt to retrieve files from github URL
  get_repo(repo_url, clone_dir)

  from main import process_repository, LANGUAGE_CONFIG
  try:
    result = process_repository(
      repo_path=clone_dir,
      config=LANGUAGE_CONFIG
    )
    if not result:
      response.status = 500
      return { 'error': 'An unknown error occurred when generating docs.' }

    response.content_type = 'application/json'
    return json.dumps({ 'files': result })
  except Exception as e:
    response.status = 500
    print(e)
    return e

@get('/diagram')
def renderDiagram():
    if 'repo_url' in request.query:
        repo_url = request.query['repo_url']
    elif request.json and 'repo_url' in request.json:
        repo_url = request.json['repo_url']
    else:
        response.status = 400
        return { 'status': response.status, 'message': 'Bad Request - parameter repo_url is required.' }

    try:
        with open(os.path.join(get_clone_dir(repo_url), 'wraith.docs/system-dataflow.md'), 'r') as f:
            mermaidStr = f.read()
        with open('./server/diagram.html', 'r') as f:
            html = f.read()

        return html.replace('%mermaidStr%', mermaidStr)
    except Exception as e:
        response.status = 500
        print(e)
        return { 'error': f'Failed to read diagram file: {str(e)}' }
