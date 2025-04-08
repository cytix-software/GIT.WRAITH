from bottle import route, run, static_file
import os

ROOT = './server/www'

@route('/')
@route('/<filepath:path>')
def serve(filepath=''):
    # Look for an index.html file and server that if it exists
    if filepath == '' or filepath.endswith('/'):
        filepath = os.path.join(filepath, 'index.html')
    return static_file(filepath, root=ROOT)

run(host='0.0.0.0', port=3000, debug=True, reloader=True)