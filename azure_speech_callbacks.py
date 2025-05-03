
import logging
import azure.cognitiveservices.speech as speechsdk

logger = logging.getLogger(__name__)

class SpeechCallbacks:
    def __init__(self, call_id):
        self.call_id = call_id

    def log_event(self, event_type, data=None):
        logger.info(f"[{self.call_id}] {event_type}: {data}")

    def on_recognized(self, evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = evt.result.text
            self.log_event("RECOGNIZED", text)
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            self.log_event("NO_MATCH", evt.result.no_match_details)

    def register_callbacks(self, recognizer):
        recognizer.recognized.connect(self.on_recognized)
        recognizer.canceled.connect(lambda evt: self.log_event("CANCELED", evt.reason))
        recognizer.session_started.connect(lambda evt: self.log_event("SESSION_STARTED", evt.session_id))
        recognizer.session_stopped.connect(lambda evt: self.log_event("SESSION_STOPPED", evt.session_id))
