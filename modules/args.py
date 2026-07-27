import argparse


def get_args():
    parser = argparse.ArgumentParser(description="SCE CICD Server")
    parser.add_argument(
        "--development",
        action="store_true",
        help='Disables subprocess.run for git and docker. It will log what it would have ran and send a "Development Mode" notification to Discord.',
    )
    parser.add_argument(
        "--port", type=int, default=3000, help="Port to run the server on"
    )
    parser.add_argument(
        "--config",
        default="config.yml",
        help="path to config file, defaults to ./config.yml",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="increase logging verbosity; can be used multiple times like -vvv"
    )
    return parser.parse_args()
