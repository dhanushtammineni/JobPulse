"""Compatibility boundary for the Python.org parser."""
from jobpulse.ingestion.http import HTTPClient


def fetch_html(url):
    return HTTPClient().html(url)
