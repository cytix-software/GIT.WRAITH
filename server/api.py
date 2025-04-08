from bottle import route, request, response, get, post

@route('/api')
def healthCheck():
  response.content_type = 'text/text; charset=UTF8'
  return "Wraith API Healthy"

@get('/api/scan')
@post('/api/scan')
def scan():
  repo_url = request.query['repo_url']

  if not repo_url and (not request.json or 'repo_url' not in request.json):
    response.status = 400
    return { 'status': response.status, 'message': 'Bad Request - parameter repo_url is required.' }

  repo_url = repo_url or request.json['repo_url']

  from main import process_repository, LANGUAGE_CONFIG, MAX_TOKENS

  result = process_repository(
    repo_path=repo_url,
    config=LANGUAGE_CONFIG,
    max_tokens=MAX_TOKENS
  )
  return result