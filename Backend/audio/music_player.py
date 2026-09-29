import threading
import time
import numpy as np
import sounddevice as sd
import os
import sys

try:
    import torchaudio
except ImportError:
    torchaudio = None

class MusicPlayer:
    def __init__(self, file_path, volume=0.3):
        self.file_path = file_path
        self.volume = volume
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.fs = 44100
        self.data = None
        
        self._load_audio()
        
    def _load_audio(self):
        # Check explicit path first
        if not os.path.exists(self.file_path):
            # Try looking in the same directory as this script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            local_path = os.path.join(script_dir, "audio.mp3")
            
            if os.path.exists(local_path):
                print(f"[MusicPlayer] Redirecting to found audio: {local_path}")
                self.file_path = local_path
            else:
                print(f"[MusicPlayer] File not found: {self.file_path}")
                self._generate_fallback()
                return

        if torchaudio is None:
            print(f"[MusicPlayer] torchaudio not installed. Using fallback.")
            self._generate_fallback()
            return
            
        try:
            # Load audio using torchaudio
            # normalize=True is default
            print(f"[MusicPlayer] Loading {self.file_path}...")
            # Note: torchaudio.load returns (Tensor, int) -> (channels, time), rate
            waveform, sample_rate = torchaudio.load(self.file_path)
            self.fs = sample_rate
            
            # Convert to numpy (channels, samples) -> (samples, channels)
            # Ensure float32
            self.data = waveform.numpy().T.astype(np.float32)
            
            # Apply volume scaling
            self.data = self.data * self.volume
            
            print(f"[MusicPlayer] Loaded successfully. Duration: {self.data.shape[0]/self.fs:.2f}s")
            
        except Exception as e:
            print(f"[MusicPlayer] Error loading audio: {e}")
            self._generate_fallback()
            
    def _generate_fallback(self):
        print("[MusicPlayer] Generating fallback music.")
        self.fs = 44100
        duration = 5 # just a chunk to loop
        t = np.linspace(0, duration, int(self.fs * duration), endpoint=False)
        frequencies = [261.63, 329.63, 392.00, 493.88] # Major 7th
        
        # Mono initialized
        sine_wave = np.zeros(len(t), dtype=np.float32)
        for f in frequencies:
            # Random phase for natural sound
            start_phase = np.random.rand() * 2 * np.pi
            sine = 0.05 * np.sin(2 * np.pi * f * t + start_phase)
            sine_wave += sine.astype(np.float32)
            
        # Reshape to (samples, 1) for sounddevice
        self.data = sine_wave.reshape(-1, 1)
            
    def play(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self._playback_worker)
        self.worker_thread.start()
        
    def stop(self):
        if not self.worker_thread or not self.worker_thread.is_alive():
            return
        self.stop_event.set()
        # Wait for thread to finish (including fade out)
        self.worker_thread.join()
        
    def _playback_worker(self):
        try:
            if self.data is None:
                return

            channels = self.data.shape[1] if len(self.data.shape) > 1 else 1
            
            with sd.OutputStream(samplerate=self.fs, channels=channels, dtype='float32') as stream:
                idx = 0
                total_samples = len(self.data)
                chunk_size = 2048
                
                while not self.stop_event.is_set():
                    # Determine how much to write
                    # To allow interruption mid-chunk? No, chunk_size is small (46ms at 44.1k), so latency is low.
                    
                    # Logic for looping playback
                    end = idx + chunk_size
                    
                    if end <= total_samples:
                        chunk = self.data[idx:end]
                        idx += len(chunk)
                        if idx >= total_samples: 
                            idx = 0
                    else:
                        # Wrap around logic
                        first_part = self.data[idx:]
                        remaining = chunk_size - len(first_part)
                        
                        # Handle if remaining is larger than entire buffer (unlikely but possible if fallback is super short)
                        # Basic wrap:
                        second_part = self.data[:remaining]
                        # If remaining > total_samples, simpler to just take whole buffer and slice?
                        # Assuming data > chunk_size usually.
                        
                        chunk = np.concatenate((first_part, second_part))
                        idx = remaining
                        
                    stream.write(chunk)
                    
                # --- Fade Out Logic ---
                # Generate ~300-500ms fade out
                fade_ms = 400
                fade_samples = int(self.fs * fade_ms / 1000)
                
                if fade_samples > 0:
                    # Get next chunk
                    end = idx + fade_samples
                    # Handle wrap for fade too
                    if end <= total_samples:
                        fade_chunk = self.data[idx:end]
                    else:
                        # Simplified wrap for fade
                        first = self.data[idx:]
                        rem = fade_samples - len(first)
                        second = self.data[:rem]
                        fade_chunk = np.concatenate((first, second))
                    
                    if len(fade_chunk) > 0:
                        # Create fade curve
                        # linspace 1 -> 0
                        curve = np.linspace(1.0, 0.0, len(fade_chunk), dtype=np.float32)
                        
                        # Apply curve to all channels
                        # shape of fade_chunk: (N, C)
                        # shape of curve: (N,) -> need (N, 1)
                        if channels > 1:
                            curve = curve[:, np.newaxis]
                        else:
                            curve = curve.reshape(-1, 1)
                            
                        faded_data = fade_chunk * curve
                        stream.write(faded_data)
                        
        except Exception as e:
            print(f"[MusicPlayer] Playback error: {e}")
