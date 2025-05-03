import logging
import azure.cognitiveservices.speech as speechsdk
import wave
import os
import time

logger = logging.getLogger(__name__)

DEBUG_DIR = "audio/debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

SAMPLE_RATE = 8000
CHANNELS = 1
BITS_PER_SAMPLE = 16

class SpeechCallbacks:
    def __init__(self, call_id, session_manager):
        self.call_id = call_id
        self.audio_buffer = []
        self.recognition_count = 0
        self.session_manager = session_manager  # sessão_manager injetado

    def log_event(self, event_type, data=None):
        logger.info(f"[{self.call_id}] {event_type}: {data}")

    def on_recognized(self, evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = evt.result.text
            self.log_event("RECOGNIZED", text)

            # Enviar texto reconhecido ao session_manager
            self.session_manager.process_visitor_text(self.call_id, text)

            self.recognition_count += 1
            filename = os.path.join(
                DEBUG_DIR,
                f"{self.call_id}_recognized_{self.recognition_count}_{int(time.time())}.wav"
            )
            self.save_audio_to_wav(filename)
            self.audio_buffer.clear()

        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            self.log_event("NO_MATCH", evt.result.no_match_details)

            filename = os.path.join(
                DEBUG_DIR,
                f"{self.call_id}_nomatch_{int(time.time())}.wav"
            )
            self.save_audio_to_wav(filename)
            self.audio_buffer.clear()

    def register_callbacks(self, recognizer):
        recognizer.recognized.connect(self.on_recognized)
        recognizer.canceled.connect(lambda evt: self.log_event("CANCELED", evt.reason))
        recognizer.session_started.connect(lambda evt: self.log_event("SESSION_STARTED", evt.session_id))
        recognizer.session_stopped.connect(lambda evt: self.log_event("SESSION_STOPPED", evt.session_id))

    def add_audio_chunk(self, chunk):
        self.audio_buffer.append(chunk)

    def save_audio_to_wav(self, filename):
        if not self.audio_buffer:
            self.log_event("SAVE_AUDIO_SKIPPED", "Buffer vazio.")
            return

        try:
            audio_data = b''.join(self.audio_buffer)
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(BITS_PER_SAMPLE // 8)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio_data)

            self.log_event("AUDIO_SAVED", filename)

        except Exception as e:
            self.log_event("ERROR_SAVING_AUDIO", str(e))
