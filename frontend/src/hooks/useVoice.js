// hooks/useVoice.js
// Custom React hook that handles:
//   1. Requesting microphone permission
//   2. Recording audio when user holds the button
//   3. Sending audio to the backend
//   4. Receiving and playing the response audio
//   5. Returning state for the UI to display

import { useState, useRef, useCallback } from 'react';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export function useVoice(phoneNumber) {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [error, setError] = useState(null);
  const [lastTranscript, setLastTranscript] = useState('');
  const [lastResponse, setLastResponse] = useState('');
  const [progress, setProgress] = useState({ questions_answered: 0, total: 20, percent: 0 });
  const [profileComplete, setProfileComplete] = useState(false);
  const [currentAgent, setCurrentAgent] = useState('onboarding');

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const sessionIdRef = useRef(localStorage.getItem('jobsathi_session_id'));

  // ── Start Recording ──────────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    setError(null);

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,  // 16kHz is ideal for Transcribe
        }
      });

      // MediaRecorder captures audio as webm/opus
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });

      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start(100);  // collect chunks every 100ms
      setIsRecording(true);

    } catch (err) {
      if (err.name === 'NotAllowedError') {
        setError('Microphone permission denied. Please allow microphone access and try again.');
      } else {
        setError('Could not start recording: ' + err.message);
      }
    }
  }, []);

  // ── Stop Recording and Send to Backend ──────────────────────────────────
  const stopRecording = useCallback(() => {
    if (!mediaRecorderRef.current || !isRecording) return;

    const mediaRecorder = mediaRecorderRef.current;

    mediaRecorder.onstop = async () => {
      setIsRecording(false);
      setIsProcessing(true);

      // Stop all tracks (releases microphone)
      mediaRecorder.stream.getTracks().forEach(track => track.stop());

      // Build audio blob
      const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });

      if (audioBlob.size < 1000) {
        setError('Recording too short. Please hold the button and speak.');
        setIsProcessing(false);
        return;
      }

      try {
        // Build form data
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');
        formData.append('phone_number', phoneNumber);
        if (sessionIdRef.current) {
          formData.append('session_id', sessionIdRef.current);
        }

        // Send to backend
        const response = await fetch(`${API_BASE}/api/message`, {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          throw new Error(`Server error: ${response.status}`);
        }

        const data = await response.json();

        // Save session ID for continuity
        if (data.session_id) {
          sessionIdRef.current = data.session_id;
          localStorage.setItem('jobsathi_session_id', data.session_id);
        }

        // Update state from response
        setLastTranscript(data.transcribed_input || '');
        setLastResponse(data.text || '');
        setProgress(data.progress || { questions_answered: 0, total: 20, percent: 0 });
        setProfileComplete(data.profile_complete || false);
        setCurrentAgent(data.agent || 'onboarding');

        // Play the audio response
        if (data.audio_base64) {
          await playAudioBase64(data.audio_base64);
        }

      } catch (err) {
        setError('Failed to process your message: ' + err.message);
        console.error('Voice processing error:', err);
      } finally {
        setIsProcessing(false);
      }
    };

    mediaRecorder.stop();
  }, [isRecording, phoneNumber]);

  // ── Play Audio Response ───────────────────────────────────────────────────
  const playAudioBase64 = useCallback(async (base64Audio) => {
    setIsPlaying(true);
    try {
      // Decode base64 to ArrayBuffer
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Create AudioContext if needed
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      }

      const audioContext = audioContextRef.current;

      // Decode and play
      const audioBuffer = await audioContext.decodeAudioData(bytes.buffer);
      const source = audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContext.destination);

      source.onended = () => setIsPlaying(false);
      source.start(0);

    } catch (err) {
      console.error('Audio playback error:', err);
      setIsPlaying(false);
    }
  }, []);

  return {
    // Recording controls
    startRecording,
    stopRecording,

    // State
    isRecording,
    isProcessing,
    isPlaying,
    error,

    // Content
    lastTranscript,
    lastResponse,

    // Progress
    progress,
    profileComplete,
    currentAgent,
  };
}
