from bottle import route, static_file, get, response
import os

ROOT = './server/www'

@route('/')
@route('/<filepath:path>')
def serveStatic(filepath=''):
    # Look for an index.html file and server that if it exists
    if filepath == '' or filepath.endswith('/'):
        filepath = os.path.join(filepath, 'index.html')
    return static_file(filepath, root=ROOT)
