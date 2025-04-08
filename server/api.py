from bottle import route, request, response, get, post

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

  # TODO: find a way to turn a URL for a github project into actual file contents to feed into the process_repository function

  from main import process_repository, LANGUAGE_CONFIG, MAX_TOKENS
  try:
    result = process_repository(
      repo_path=repo_url,
      config=LANGUAGE_CONFIG,
      max_tokens=MAX_TOKENS
    )
    if not result:
      response.status = 500
      return { 'error': 'Something bad happened here' }
    return result
  except Exception as e:
    response.status = 500
    return e