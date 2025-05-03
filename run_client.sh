#!/bin/bash
source /Users/danerdosreis/development/environments/audiosocket-simple/bin/activate
cd /Users/danerdosreis/development/projects/cienciadigital/audiosocket-simple
export AZURE_SPEECH_KEY=dummy-key-for-testing
export AZURE_SPEECH_REGION=westus
python microfone_client.py