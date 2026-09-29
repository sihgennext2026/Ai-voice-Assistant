
import os
import sys
import time
import msvcrt
import re
import atexit
from pathlib import Path
import sounddevice as sd
import numpy as np
from dotenv import load_dotenv

# Load env immediately
load_dotenv()

# Ensure paths are correct
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
sys.path.append(os.path.join(os.path.dirname(__file__), "audio-transcription"))

from audio.recorder import AudioRecorder
# Dynamic import for ASR to handle potential path issues gracefully-ish
try:
    from asr_service.api.asr.model import ASRModel
except ImportError:
    try:
        from asr.model import ASRModel
    except ImportError:
        print("Error importing ASRModel. Check paths.")
        sys.exit(1)

from config import get_settings
from tts.service import SpeechService
from llm.agent import run_agent, clear_history
from vad.vad_service import SileroVAD


class VoiceAgent:
    def __init__(self):
        print("Initializing RAGAVA (Autonomous Voice Agent)...")
        self.running = True
        
        settings = get_settings()
        for service, status in settings.capability_report().items():
            print(f"  {service}: {status}")

        # 1. Components
        try:
            self.recorder = AudioRecorder()
            print("[OK] Microphone initialized.")
            
            self.asr_model = ASRModel()
            print("[OK] ASR Model loaded.")
            
            # ElevenLabs with Piper fallback
            try:
                models_dir = os.path.join(os.path.dirname(__file__), "models")
                self.tts = SpeechService(settings, models_dir)
                if not self.tts.valid:
                    print("[ERROR] No TTS engine available.")
                    sys.exit(1)
                print(f"[OK] TTS initialized ({self.tts.provider}, Piper fallback).")
            except Exception as e:
                print(f"[ERROR] Piper TTS failed to initialize: {e}")
                sys.exit(1)

            # Interruption VAD is disabled by default.
            # Keep the recorder using RMS-based silence detection only.
            self.vad = None
            
        except Exception as e:
            print(f"[CRITICAL] Initialization failed: {e}")
            sys.exit(1)
            

        
        # State

        self.response_buffer = ""
        self.in_think_block = False
        self.filter_buffer = ""
        self.vad_positive_count = 0 # Counter for consecutive VAD detections

        # Register cleanup
        atexit.register(self.cleanup)

    def cleanup(self):
        """Cleanup resources on exit."""
        print("\nCleaning up resources...")
        try:
            clear_history() 
            if hasattr(self, 'tts'):
                self.tts.stop()
        except:
            pass

    def check_quit(self):
        """Check for 'q' key."""
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key.lower() == b'q':
                self.running = False
                return True
        return False




    def filter_text(self, chunk: str) -> str:
        """
        Filter out <think> tags from chunks for TTS.
        Maintains state to handle tags split across chunks.
        """
        text = self.filter_buffer + chunk
        self.filter_buffer = ""
        
        filtered = ""
        i = 0
        while i < len(text):
            if self.in_think_block:
                close_idx = text.find("</think>", i)
                if close_idx != -1:
                    self.in_think_block = False
                    i = close_idx + 8 
                else:
                    # Check for partial closing tag at end
                    partial_found = False
                    for length in range(1, 8):
                        suffix = text[-length:]
                        if "</think>".startswith(suffix):
                            self.filter_buffer = suffix
                            partial_found = True
                            break
                    break # Discard everything else
            else:
                # Not in think block
                open_idx = text.find("<think>", i)
                close_idx = text.find("</think>", i)
                
                # Handle orphaned </think> by skipping it
                if close_idx != -1 and (open_idx == -1 or close_idx < open_idx):
                    filtered += text[i:close_idx]
                    i = close_idx + 8
                    continue

                if open_idx != -1:
                    filtered += text[i:open_idx]
                    self.in_think_block = True
                    i = open_idx + 7
                    continue
                
                # Check for partial tags (opening OR closing) at end
                partial_found = False
                for length in range(1, 9):
                    if i + length > len(text): 
                        # Cannot have a suffix longer than remaining text
                        continue
                        
                    suffix = text[-length:]
                    # Check if suffix could be start of <think> OR </think>
                    if "<think>".startswith(suffix) or "</think>".startswith(suffix):
                        filtered += text[i:-length]
                        self.filter_buffer = suffix
                        partial_found = True
                        break
                
                if not partial_found:
                    filtered += text[i:]
                break
                
        return filtered

    def check_for_interruption(self, stream):
        """Interruption VAD is disabled. Always return False."""
        return False

    def run(self):
        """Main execution loop."""
        clear_history() 
        
        print("\n--- Agent Ready ---")
        print("Speak Now")
        print("Press 'q' to quit.")
        
        while self.running:
            if self.check_quit(): break
            
            # Listen using RMS silence detection only.
            # Interruption VAD is intentionally disabled.
            audio = self.recorder.record_until_silence(
                threshold=0.005,
                silence_duration=1.0,
                interrupt_check=self.check_quit,
                vad_function=None
            )
            
            if self.check_quit() or audio is None or len(audio) == 0:
                # print(" [No audio] ")
                continue
            
            duration = len(audio) / self.recorder.sample_rate
            print(f" [captured {duration:.2f}s] ", end="", flush=True)

            # Transcribe
            print("\rTranscribing...          ", end="", flush=True)
            try:
                segments, _ = self.asr_model.transcribe(audio)
                text = " ".join([s.text for s in segments]).strip()
                print("\r" + " " * 30 + "\r", end="", flush=True)
                
                if not text:
                    continue
                    
                print(f"You: {text}")
                
            except Exception as e:
                print(f"\nASR Error: {e}")
                continue

            # Response
            print("Assistant: ", end="", flush=True)
            self.process_response(text)
            print("\n")
            
            # Wait for TTS to finish (if not already interrupted)
            if self.tts.is_busy:
                 self.wait_for_tts()
            
            time.sleep(0.5)

    def process_response(self, user_text):
        """Get LLM response and feed to TTS."""
        full_buffer = ""
        sentence_buffer = ""
        self.in_think_block = False # Reset state for new turn
        self.filter_buffer = ""
        interrupted = False
        self.vad_positive_count = 0 # Reset counter
        
        # Interruption VAD is disabled. Keep the agent flowing without mic-based interruption logic.
        try:
            for chunk in run_agent(user_text):
                if self.check_quit(): break
                
                # Buffer to handle split tags
                clean_chunk = chunk
                sentence_buffer += clean_chunk
                
                if clean_chunk:
                    # Print without tags if possible, but cleaner to just print what we have
                    print(clean_chunk, end="", flush=True)

                    
                    if any(p in clean_chunk for p in [".", "?", "!", "\n", ":"]):
                        if sentence_buffer.strip():
                             if not interrupted:
                                self.tts.synthesize(sentence_buffer)
                             sentence_buffer = ""

            if not interrupted and sentence_buffer.strip():
                to_speak = sentence_buffer.strip()
                if to_speak:
                    self.tts.synthesize(to_speak)
            elif not interrupted and not sentence_buffer.strip():
                 print("(No response generated)")
                
        except Exception as e:
            print(f"Error in process_response: {e}")
        finally:
            pass
            
        self.tts.end_turn()

    def wait_for_tts(self):
        """Block until TTS is done, while monitoring for interruption."""
        if not self.tts.is_busy:
            return

        self.vad_positive_count = 0 # Reset counter

        try:
            while self.tts.is_busy:
                if self.check_quit():
                    self.tts.stop()
                    break
                time.sleep(0.05)
        except Exception as e:
            print(f"TTS wait error: {e}")
            while self.tts.is_busy:
                time.sleep(0.1)

if __name__ == "__main__":
    agent = VoiceAgent()
    agent.run()
