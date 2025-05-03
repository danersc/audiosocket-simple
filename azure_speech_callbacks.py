import logging
import azure.cognitiveservices.speech as speechsdk
import wave
import os
import time

logger = logging.getLogger(__name__)

DEBUG_DIR = "audio/debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

class SpeechCallbacks:
    def __init__(self, call_id, audio_format):
        self.call_id = call_id
        self.audio_buffer = []
        self.audio_format = audio_format
        self.recognition_count = 0

    def log_event(self, event_type, data=None):
        logger.info(f"[{self.call_id}] {event_type}: {data}")

    def on_recognized(self, evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = evt.result.text
            self.log_event("RECOGNIZED", text)

            # Salva áudio no momento do reconhecimento
            self.recognition_count += 1
            filename = os.path.join(DEBUG_DIR, f"{self.call_id}_recognized_{self.recognition_count}_{int(time.time())}.wav")
            self.save_audio_to_wav(filename)
            self.audio_buffer.clear()

        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            self.log_event("NO_MATCH", evt.result.no_match_details)

            # Salva áudio mesmo quando não houver match
            filename = os.path.join(DEBUG_DIR, f"{self.call_id}_nomatch_{int(time.time())}.wav")
            self.save_audio_to_wav(filename)
            self.audio_buffer.clear()

    def register_callbacks(self, recognizer):
        recognizer.recognized.connect(self.on_recognized)
        recognizer.canceled.connect(lambda evt: self.log_event("CANCELED", evt.reason))
        recognizer.session_started.connect(lambda evt: self.log_event("SESSION_STARTED", evt.session_id))
        recognizer.session_stopped.connect(lambda evt: self.log_event("SESSION_STOPPED", evt.session_id))

    def add_audio_chunk(self, chunk):
        """Adiciona chunk ao buffer interno para debug."""
        self.audio_buffer.append(chunk)

    def save_audio_to_wav(self, filename):
        """Salva o áudio coletado no buffer em formato WAV para análise."""
        if not self.audio_buffer:
            self.log_event("SAVE_AUDIO_SKIPPED", "Buffer vazio.")
            return

        try:
            audio_data = b''.join(self.audio_buffer)
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(self.audio_format.channels)
                wf.setsampwidth(2)  # 16 bits = 2 bytes
                wf.setframerate(self.audio_format.samples_per_second)
                wf.writeframes(audio_data)

            self.log_event("AUDIO_SAVED", filename)

        except Exception as e:
            self.log_event("ERROR_SAVING_AUDIO", str(e))
