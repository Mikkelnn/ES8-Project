import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


PROJECT_DIR = Path(__file__).resolve().parent
SAVE_DIR = Path(__file__).resolve().parent  # same dir as this script
SAVE_ROUTE = '/save-selected-roads'
DEFAULT_FILE_NAME = 'selected_roads.json'


class RoadGuiHandler(SimpleHTTPRequestHandler):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, directory=str(PROJECT_DIR), **kwargs)

	def do_POST(self):
		if urlparse(self.path).path != SAVE_ROUTE:
			self._send_json({'error': 'Not found'}, HTTPStatus.NOT_FOUND)
			return

		try:
			content_length = int(self.headers.get('Content-Length', '0'))
		except ValueError:
			self._send_json({'error': 'Invalid Content-Length'}, HTTPStatus.BAD_REQUEST)
			return

		try:
			raw_body = self.rfile.read(content_length)
			body = json.loads(raw_body.decode('utf-8')) if raw_body else {}
		except (UnicodeDecodeError, json.JSONDecodeError):
			self._send_json({'error': 'Body must be valid JSON'}, HTTPStatus.BAD_REQUEST)
			return

		file_name = self._safe_file_name(body.get('fileName', DEFAULT_FILE_NAME))
		output_path = SAVE_DIR / file_name
		data = body.get('data')

		if data is None:
			self._send_json({'error': 'Missing data payload'}, HTTPStatus.BAD_REQUEST)
			return

		try:
			output_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
		except OSError as exc:
			self._send_json({'error': f'Could not write file: {exc}'}, HTTPStatus.INTERNAL_SERVER_ERROR)
			return

		self._send_json(
			{
				'ok': True,
				'fileName': file_name,
				'savedTo': str(output_path),
			},
			HTTPStatus.OK,
		)

	@staticmethod
	def _safe_file_name(candidate):
		value = Path(str(candidate or DEFAULT_FILE_NAME).strip()).name
		if not value:
			value = DEFAULT_FILE_NAME
		if not value.lower().endswith('.json'):
			value = f'{value}.json'
		return value

	def _send_json(self, payload, status):
		raw = json.dumps(payload).encode('utf-8')
		self.send_response(int(status))
		self.send_header('Content-Type', 'application/json; charset=utf-8')
		self.send_header('Content-Length', str(len(raw)))
		self.end_headers()
		self.wfile.write(raw)


def parse_args():
	parser = argparse.ArgumentParser(description='Serve road GUI and save selected roads JSON in PWD.')
	parser.add_argument('--host', default='127.0.0.1', help='Host to bind')
	parser.add_argument('--port', default=8000, type=int, help='Port to bind')
	return parser.parse_args()


def main():
	args = parse_args()
	address = (args.host, args.port)
	with ThreadingHTTPServer(address, RoadGuiHandler) as server:
		print(f'Serving UI from: {PROJECT_DIR}')
		print(f'Open: http://{args.host}:{args.port}/map_generator_gui.html')
		print(f'Saving selected_roads.json to:  {SAVE_DIR}')
		server.serve_forever()


if __name__ == '__main__':
	main()
