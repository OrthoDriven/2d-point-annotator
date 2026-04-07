#!/usr/bin/env python3
import requests

API_URL = 'https://api.github.com/repos/OrthoDriven/2d-point-annotator/commits/new-prototype'
REPO_ZIP_URL = 'https://github.com/OrthoDriven/2d-point-annotator/archive/refs/heads/new-prototype.zip'

print('API URL:', API_URL)
print('ZIP URL:', REPO_ZIP_URL)
print('API status:', requests.get(API_URL, timeout=15).status_code)
print('ZIP status:', requests.get(REPO_ZIP_URL, timeout=15, allow_redirects=True).status_code)
