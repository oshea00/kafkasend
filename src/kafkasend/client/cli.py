"""Command-line interface for the Kafka client."""

import sys
import click
import structlog

from kafkasend.common.config import KafkaConfig, ClientConfig
from kafkasend.common.logging import configure_logging
from kafkasend.common.models import HttpMethod
from kafkasend.common.chunking import decode_chunk
from kafkasend.client.sender import KafkaSender
from kafkasend.client.receiver import KafkaReceiver

logger = structlog.get_logger(__name__)


@click.group()
@click.option('--log-level', default='INFO', help='Logging level')
@click.pass_context
def cli(ctx, log_level):
    """Kafka to REST API client."""
    ctx.ensure_object(dict)
    ctx.obj['log_level'] = log_level
    configure_logging(log_level)


@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--endpoint', '-e', required=True, help='API endpoint path')
@click.option('--method', '-m', type=click.Choice(['POST', 'PUT', 'PATCH']), default='POST', help='HTTP method')
@click.option('--header', '-h', multiple=True, help='HTTP header in format "Key: Value"')
@click.option('--content-type', '-t', help='Content type of the file')
@click.option('--wait/--no-wait', default=True, help='Wait for response')
@click.option('--output', '-o', type=click.Path(), help='Output file for response')
@click.pass_context
def send_file(ctx, file_path, endpoint, method, header, content_type, wait, output):
    """Send a file to the REST API via Kafka."""
    try:
        # Parse headers
        headers = {}
        for h in header:
            if ':' in h:
                key, value = h.split(':', 1)
                headers[key.strip()] = value.strip()

        # Initialize sender
        kafka_config = KafkaConfig()
        sender = KafkaSender(kafka_config)

        # Send file
        click.echo(f"Sending file: {file_path}")
        job_id = sender.send_file(
            file_path=file_path,
            endpoint=endpoint,
            method=HttpMethod(method),
            headers=headers,
            content_type=content_type
        )

        click.echo(f"Job ID: {job_id}")

        sender.close()

        # Wait for response if requested
        if wait:
            click.echo("Waiting for response...")
            receiver = KafkaReceiver(kafka_config)

            def progress_callback(state):
                if state.total_chunks and state.total_chunks > 1:
                    progress = len(state.chunks) / state.total_chunks * 100
                    click.echo(f"Response progress: {progress:.1f}%")

            try:
                response = receiver.wait_for_response(job_id, callback=progress_callback)

                if response.error_message:
                    click.echo(f"Error: {response.error_message}", err=True)
                    sys.exit(1)

                click.echo(f"Status Code: {response.status_code}")
                click.echo(f"Headers: {response.headers}")

                # Get response data
                response_data = response.get_complete_data()

                if response.is_text:
                    click.echo(f"Response (text):\n{response_data}")
                    if output:
                        with open(output, 'w') as f:
                            f.write(response_data)
                        click.echo(f"Response saved to: {output}")
                else:
                    # Decode binary data
                    binary_data = decode_chunk(response_data)
                    click.echo(f"Response size: {len(binary_data)} bytes")

                    if output:
                        with open(output, 'wb') as f:
                            f.write(binary_data)
                        click.echo(f"Response saved to: {output}")
                    else:
                        click.echo("Binary response received (use --output to save)")

            finally:
                receiver.close()

    except Exception as e:
        logger.error("Error sending file", error=str(e), exc_info=True)
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--endpoint', '-e', required=True, help='API endpoint path')
@click.option('--method', '-m', type=click.Choice(['GET', 'POST', 'PUT', 'DELETE', 'PATCH']), default='GET', help='HTTP method')
@click.option('--header', '-h', multiple=True, help='HTTP header in format "Key: Value"')
@click.option('--wait/--no-wait', default=True, help='Wait for response')
@click.pass_context
def send_request(ctx, endpoint, method, header, wait):
    """Send a simple HTTP request (no body) via Kafka."""
    try:
        # Parse headers
        headers = {}
        for h in header:
            if ':' in h:
                key, value = h.split(':', 1)
                headers[key.strip()] = value.strip()

        # Initialize sender
        kafka_config = KafkaConfig()
        sender = KafkaSender(kafka_config)

        # Send request
        click.echo(f"Sending {method} request to: {endpoint}")
        job_id = sender.send_request(
            endpoint=endpoint,
            method=HttpMethod(method),
            headers=headers
        )

        click.echo(f"Job ID: {job_id}")

        sender.close()

        # Wait for response if requested
        if wait:
            click.echo("Waiting for response...")
            receiver = KafkaReceiver(kafka_config)

            try:
                response = receiver.wait_for_response(job_id)

                if response.error_message:
                    click.echo(f"Error: {response.error_message}", err=True)
                    sys.exit(1)

                click.echo(f"Status Code: {response.status_code}")
                click.echo(f"Headers: {response.headers}")

                response_data = response.get_complete_data()
                click.echo(f"Response:\n{response_data}")

            finally:
                receiver.close()

    except Exception as e:
        logger.error("Error sending request", error=str(e), exc_info=True)
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == '__main__':
    main()
