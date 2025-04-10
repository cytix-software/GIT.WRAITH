import json
from bottle import route, request, response, get, post
from github import get_repo

@route('/api')
def healthCheck():
  response.content_type = 'text/text; charset=UTF8'
  return "Wraith API Healthy"

@get('/api/scan')
@post('/api/scan')
def scan():
  if 'repo_url' in request.query: repo_url = request.query['repo_url']
  elif request.json and 'repo_url' in request.json: repo_url = request.json['repo_url']
  else: 
    response.status = 400
    return { 'status': response.status, 'message': 'Bad Request - parameter repo_url is required.' }

  # Attempt to retrieve files from github URL
  files = get_repo(repo_url)

  from main import process_repository, LANGUAGE_CONFIG
  try:
    result = process_repository(
      repo_path='./git_wraith_repo',
      config=LANGUAGE_CONFIG
    )
    if not result:
      response.status = 500
      return { 'error': 'An unknown error occurred when generating docs.' }

    response.content_type = 'application/json'
    return json.dumps(result)
  except Exception as e:
    response.status = 500
    print(e)
    return e