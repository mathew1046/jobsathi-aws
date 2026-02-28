// hooks/useVoice.js
// Core voice interaction hook for JobSathi.
//
// Manages the full voice pipeline:
//   1. Microphone permission request
//   2. Hold-to-record audio capture (MediaRecorder API)
//   3. Live audio level analysis via Web Audio API AnalyserNode
//      → passed to MicButton for the waveform visualizer
//   4. Send audio blob to backend POST /api/message
//   5. Decode and play base64 MP3 response (Web Audio API)
//   6. Session persistence across page reloads (localStorage)
//   7. Profile and progress state tracking
//
// Design note: This hook is the only place in the app that touches
// raw audio APIs. Components only see clean state + callbacks.

import { useState, useRef, useCallback, useEffect } from 'react';

const API_BASE = process.env.REACT_APP_API_URL || '';

export function useVoice(phoneNumber) {
  // ── Recording state ─────────────────────────────────────────────────────
  const [isRecording, setIsRecording]   = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPlaying, setIsPlaying]       = useState(false);
  const [error, setError]               = useState(null);

  // ── Conversation content ────────────────────────────────────────────────
  const [lastTranscript, setLastTranscript] = useState('');
  const [lastResponse, setLastResponse]     = useState('');
  const [lastAudioBase64, setLastAudioBase64] = useState('');

  // ── App state ────────────────────────────────────────────────────────────
  const [progress, setProgress]           = useState({ questions_answered: 0, total: 20, percent: 0 });
  const [profileComplete, setProfileComplete] = useState(false);
  const [currentAgent, setCurrentAgent]   = useState('onboarding');
  const [language, setLanguage]           = useState('hi');
  const [profile, setProfile]             = useState(null);

  // ── Refs ─────────────────────────────────────────────────────────────────
  const mediaRecorderRef  = useRef(null);
  const audioChunksRef    = useRef([]);
  const audioContextRef   = useRef(null);
  const analyserRef       = useRef(null);    // ← passed to MicButton for waveform
  const sourceNodeRef     = useRef(null);    // current playing audio source
  const sessionIdRef      = useRef(localStorage.getItem('jobsathi_session_id') || '');

  // ── Restore session on mount ──────────────────────────────────────────
  useEffect(() => {
    if (!phoneNumber) return;
    const savedSessionId = localStorage.getItem('jobsathi_session_id');
    if (savedSessionId) {
      sessionIdRef.current = savedSessionId;
    }
  }, [phoneNumber]);

  // ── Ensure AudioContext exists ────────────────────────────────────────
  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    // Resume if suspended (browser autoplay policy)
    if (audioContextRef.current.state === 'suspended') {
      audioContextRef.current.resume();
    }
    return audioContextRef.current;
  }, []);

  // ── Start Recording ───────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    if (isProcessing || isPlaying) return;
    setError(null);

    // Stop any currently playing audio immediately when user starts speaking
    if (sourceNodeRef.current) {
      try { sourceNodeRef.current.stop(); } catch {}
      sourceNodeRef.current = null;
      setIsPlaying(false);
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,   // 16kHz — ideal for Amazon Transcribe
          channelCount: 1,     // Mono — reduces file size by 50%
        }
      });

      // ── Set up audio analyser for waveform visualizer ─────────────────
      const ctx = getAudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);
      analyserRef.current = analyser;

      // ── MediaRecorder: collect audio chunks ───────────────────────────
      // Try opus/webm first (best quality+size), fallback to webm
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';

      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start(100);  // chunk every 100ms — smooth waveform
      setIsRecording(true);

    } catch (err) {
      const msg = err.name === 'NotAllowedError'
        ? 'Microphone permission denied. Please allow microphone access.'
        : `Could not start recording: ${err.message}`;
      setError(msg);
    }
  }, [isProcessing, isPlaying, getAudioContext]);

  // ── Stop Recording → Send to Backend ─────────────────────────────────
  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') return;

    recorder.onstop = async () => {
      setIsRecording(false);
      setIsProcessing(true);

      // Disconnect analyser and stop mic stream
      if (analyserRef.current) {
        analyserRef.current.disconnect();
        analyserRef.current = null;
      }
      recorder.stream.getTracks().forEach(t => t.stop());

      const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });

      if (audioBlob.size < 800) {
        setError('Recording too short — hold the button while speaking.');
        setIsProcessing(false);
        return;
      }

      try {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');
        formData.append('phone_number', phoneNumber);
        if (sessionIdRef.current) {
          formData.append('session_id', sessionIdRef.current);
        }

        const res = await fetch(`${API_BASE}/api/message`, {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) {
          const detail = await res.text();
          throw new Error(`Server error ${res.status}: ${detail}`);
        }

        const data = await res.json();

        // ── Persist session ──────────────────────────────────────────────
        if (data.session_id) {
          sessionIdRef.current = data.session_id;
          localStorage.setItem('jobsathi_session_id', data.session_id);
        }

        // ── Update state ─────────────────────────────────────────────────
        setLastTranscript(data.transcribed_input || '');
        setLastResponse(data.text || '');
        setLastAudioBase64(data.audio_base64 || '');
        setProgress(data.progress || { questions_answered: 0, total: 20, percent: 0 });
        setProfileComplete(data.profile_complete || false);
        setCurrentAgent(data.agent || 'onboarding');
        if (data.language) setLanguage(data.language);
        if (data.profile) setProfile(data.profile);

        // ── Auto-play audio response ────────────────────────────────────
        if (data.audio_base64) {
          setIsProcessing(false);
          await playAudio(data.audio_base64);
        }

      } catch (err) {
        setError(`Failed to process your message: ${err.message}`);
        console.error('[useVoice] Error:', err);
      } finally {
        setIsProcessing(false);
      }
    };

    recorder.stop();
  }, [phoneNumber]);

  // ── Play Audio (base64 MP3) ───────────────────────────────────────────
  const playAudio = useCallback(async (base64Audio) => {
    if (!base64Audio) return;
    setIsPlaying(true);

    try {
      // Decode base64 → ArrayBuffer
      const binary = atob(base64Audio);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

      const ctx = getAudioContext();
      const audioBuffer = await ctx.decodeAudioData(bytes.buffer);

      // Stop previous if still playing
      if (sourceNodeRef.current) {
        try { sourceNodeRef.current.stop(); } catch {}
      }

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      source.onended = () => {
        setIsPlaying(false);
        sourceNodeRef.current = null;
      };
      source.start(0);
      sourceNodeRef.current = source;

    } catch (err) {
      console.error('[useVoice] Playback error:', err);
      setIsPlaying(false);
    }
  }, [getAudioContext]);

  // ── Replay last response ──────────────────────────────────────────────
  const replayLastResponse = useCallback(() => {
    if (lastAudioBase64) playAudio(lastAudioBase64);
  }, [lastAudioBase64, playAudio]);

  // ── Load profile from API ─────────────────────────────────────────────
  const loadProfile = useCallback(async (phone) => {
    if (!phone) return;
    try {
      const res = await fetch(`${API_BASE}/api/profile/${encodeURIComponent(phone)}`);
      if (res.ok) {
        const data = await res.json();
        if (data.profile_exists !== false) setProfile(data);
      }
    } catch {}
  }, []);

  return {
    // Controls
    startRecording,
    stopRecording,
    replayLastResponse,
    loadProfile,
    playAudio,

    // Recording state
    isRecording,
    isProcessing,
    isPlaying,
    error,

    // Voice pipeline output
    lastTranscript,
    lastResponse,
    lastAudioBase64,

    // App state
    progress,
    profileComplete,
    currentAgent,
    language,
    profile,

    // Audio analyser for waveform (passed to MicButton)
    analyserNode: analyserRef.current,
  };
}
