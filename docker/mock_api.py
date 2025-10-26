"""Mock REST API server for testing."""

import os
from flask import Flask, request, jsonify
import structlog

app = Flask(__name__)
logger = structlog.get_logger(__name__)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy'}), 200


@app.route('/api/upload', methods=['POST'])
def upload():
    """Handle file uploads."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    filename = file.filename

    # Save file to uploads directory
    upload_dir = '/uploads'
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)

    # Get file size after saving
    file_size = os.path.getsize(file_path)

    logger.info(
        "File received and saved",
        filename=filename,
        size=file_size,
        saved_path=file_path,
        content_type=file.content_type
    )

    return jsonify({
        'message': 'File uploaded successfully',
        'filename': filename,
        'size': file_size,
        'saved_path': file_path,
        'content_type': file.content_type,
        'received_headers': dict(request.headers)
    }), 200


@app.route('/api/echo', methods=['GET', 'POST', 'PUT', 'DELETE'])
def echo():
    """Echo endpoint that returns request details."""
    data = {
        'method': request.method,
        'path': request.path,
        'query_params': dict(request.args),
        'headers': dict(request.headers),
    }

    if request.data:
        data['body_size'] = len(request.data)

    logger.info(
        "Echo request received",
        method=request.method,
        path=request.path
    )

    return jsonify(data), 200


@app.route('/api/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def catch_all(subpath):
    """Catch-all endpoint for any path."""
    data = {
        'message': f'Received request to /{subpath}',
        'method': request.method,
        'headers': dict(request.headers),
    }

    if request.files:
        data['files'] = [
            {
                'field': field,
                'filename': file.filename,
                'size': len(file.read())
            }
            for field, file in request.files.items()
        ]

    logger.info(
        "Request received",
        method=request.method,
        path=f"/{subpath}"
    )

    return jsonify(data), 200


if __name__ == '__main__':
    # Configure logging
    import logging
    import sys
    from kafkasend.common.logging import configure_logging

    configure_logging('INFO')

    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
