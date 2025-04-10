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

@get('/diagram')
def renderDiagram():
    try:
        with open('./.git_wraith_repo/wraith.docs/system-dataflow.md', 'r') as f:
            mermaidStr = f.read()
        with open('./server/diagram.html', 'r') as f:
            html = f.read()
        
        return html.replace('%mermaidStr%', mermaidStr)
    except Exception as e:
        response.status = 500
        print(e)
        return { 'error': f'Failed to read diagram file: {str(e)}' }