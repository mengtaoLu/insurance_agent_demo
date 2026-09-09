import logging
import os
import sys

def setup_logging():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL","INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s" ,
        stream=sys.stderr,
        force=True
    )