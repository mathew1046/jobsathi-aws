// App.jsx
// JobSathi — three-screen voice-first app
//   Screen 1: Phone entry (first visit / no session)
//   Screen 2: Onboarding (20 questions via voice chat)
//   Screen 3: Job Matching (profile + voice + job cards)
//
// State management is intentionally kept in this one file.
// The useVoice hook owns all audio/API logic; App owns UI state.

import { useState, useEffect, useRef, useCallback } from 'react';
import { useVoice } from './hooks/useVoice';
import MicButton from './components/MicButton';
import ChatBubble from './components/ChatBubble';
import JobCard from './components/JobCard';
import OnboardingProgress from './components/OnboardingProgress';
import ProfileCard from './components/ProfileCard';
import StatusBar from './components/StatusBar';
import './App.css';

const API_BASE = process.env.REACT_APP_API_URL || '';

// ── Message helpers ────────────────────────────────────────────────────────────

function makeMessage(role, text, audio_base64 = '') {
  return { role, text, audio_base64, timestamp: Date.now() };
}

function typingMessage() {
  return { role: 'assistant', isTyping: true, timestamp: Date.now() };
}

// ── App ────────────────────────────────────────────────────────────────────────

export default function App() {
  // ── Phone / session state ──────────────────────────────────────────────────
  const [phoneNumber, setPhoneNumber]       = useState('');
  const [phoneInput, setPhoneInput]         = useState('');
  const [phoneSubmitted, setPhoneSubmitted] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);

  // ── Conversation state ─────────────────────────────────────────────────────
  const [messages, setMessages]     = useState([]);
  const [jobCards, setJobCards]     = useState([]);     // visual job cards shown alongside chat
  const [applyingId, setApplyingId] = useState(null);  // job index currently being applied to
  const messagesEndRef = useRef(null);

  // ── useVoice hook ──────────────────────────────────────────────────────────
  const voice = useVoice(phoneNumber);
  const {
    startRecording,
    stopRecording,
    replayLastResponse,
    loadProfile,
    playAudio,
    isRecording,
    isProcessing,
    isPlaying,
    error,
    lastTranscript,
    lastResponse,
    lastAudioBase64,
    progress,
    profileComplete,
    currentAgent,
    language,
    profile,
    analyserNode,
  } = voice;

  // ── Auto-scroll on new messages ────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ── Append new voice turn to message list ──────────────────────────────────
  // We track the previous values so we don't duplicate on re-renders.
  const prevTranscript = useRef('');
  const prevResponse   = useRef('');

  useEffect(() => {
    const newMsgs = [];

    if (lastTranscript && lastTranscript !== prevTranscript.current) {
      prevTranscript.current = lastTranscript;
      newMsgs.push(makeMessage('user', lastTranscript));
    }

    if (lastResponse && lastResponse !== prevResponse.current) {
      prevResponse.current = lastResponse;
      // Replace the typing indicator (if present) with the real message
      setMessages(prev => {
        const withoutTyping = prev.filter(m => !m.isTyping);
        return [...withoutTyping, ...newMsgs, makeMessage('assistant', lastResponse, lastAudioBase64)];
      });
      return;
    }

    if (newMsgs.length) {
      setMessages(prev => [...prev, ...newMsgs]);
    }
  }, [lastTranscript, lastResponse, lastAudioBase64]);

  // ── Show typing indicator while processing ─────────────────────────────────
  useEffect(() => {
    if (isProcessing) {
      setMessages(prev => {
        // Only add if there isn't one already
        if (prev.length && prev[prev.length - 1].isTyping) return prev;
        return [...prev, typingMessage()];
      });
    } else {
      // Remove typing indicator when processing finishes
      setMessages(prev => prev.filter(m => !m.isTyping));
    }
  }, [isProcessing]);

  // ── Restore session on load ────────────────────────────────────────────────
  useEffect(() => {
    const savedPhone   = localStorage.getItem('jobsathi_phone');
    const savedSession = localStorage.getItem('jobsathi_session_id');
    if (savedPhone && savedSession) {
      setPhoneNumber(savedPhone);
      setPhoneInput(savedPhone);
      setPhoneSubmitted(true);
      setSessionLoading(true);
      restoreSession(savedPhone).finally(() => setSessionLoading(false));
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const restoreSession = async (phone) => {
    try {
      const res = await fetch(`${API_BASE}/api/session/${encodeURIComponent(phone)}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.exists) {
        const welcomeText = data.profile_complete
          ? 'Welcome back! Ready to find more jobs?'
          : `Welcome back! We had answered ${data.progress?.questions_answered || 0} questions. Let's continue.`;
        setMessages([makeMessage('assistant', welcomeText)]);
        if (data.profile_complete) {
          await loadProfile(phone);
        }
      }
    } catch {}
  };

  // ── Phone submit ───────────────────────────────────────────────────────────
  const handlePhoneSubmit = useCallback((e) => {
    e.preventDefault();
    const clean = phoneInput.replace(/\D/g, '');
    if (clean.length < 10) return;
    localStorage.setItem('jobsathi_phone', clean);
    setPhoneNumber(clean);
    setPhoneSubmitted(true);
    setMessages([makeMessage('assistant',
      'Hello! I am JobSathi. Press and hold the button below to speak in Hindi, Tamil, Telugu or any Indian language. I will help you find work nearby.'
    )]);
  }, [phoneInput]);

  // ── Apply to a job (visual card action) ───────────────────────────────────
  // This sends a voice-style message "I want to apply to job #N"
  // The matching agent handles it and calls the application agent.
  const handleApply = useCallback(async (jobIndex) => {
    setApplyingId(jobIndex);
    // Add a user-style message showing intent
    setMessages(prev => [...prev, makeMessage('user', `Apply for job #${jobIndex + 1}`)]);
    // We do a text POST since this is a button action, not a voice recording.
    // The backend /api/apply endpoint (if it exists) or we reuse /api/message with text.
    try {
      const formData = new FormData();
      formData.append('phone_number', phoneNumber);
      const sessionId = localStorage.getItem('jobsathi_session_id') || '';
      if (sessionId) formData.append('session_id', sessionId);
      formData.append('text_override', `Apply for job number ${jobIndex + 1}`);

      const res = await fetch(`${API_BASE}/api/message`, {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        if (data.text) {
          setMessages(prev => [
            ...prev.filter(m => !m.isTyping),
            makeMessage('assistant', data.text, data.audio_base64 || ''),
          ]);
          if (data.audio_base64) playAudio(data.audio_base64);
        }
        // Remove the applied card
        setJobCards(prev => prev.filter((_, i) => i !== jobIndex));
      }
    } catch (err) {
      console.error('[App] Apply error:', err);
    } finally {
      setApplyingId(null);
    }
  }, [phoneNumber, playAudio]);

  const handleSkip = useCallback((jobIndex) => {
    setJobCards(prev => prev.filter((_, i) => i !== jobIndex));
  }, []);

  // ── Determine current screen ───────────────────────────────────────────────
  if (!phoneSubmitted) {
    return <PhoneEntryScreen
      phoneInput={phoneInput}
      setPhoneInput={setPhoneInput}
      onSubmit={handlePhoneSubmit}
    />;
  }

  if (sessionLoading) {
    return (
      <div className="app-container app-container--center">
        <div className="loading-screen">
          <div className="loading-logo">JobSathi</div>
          <div className="loading-spinner" />
          <p className="loading-text">Loading your profile…</p>
        </div>
      </div>
    );
  }

  // ── Main voice interface ───────────────────────────────────────────────────
  return (
    <div className="app-container">
      {/* ── Header ── */}
      <header className="app-header">
        <span className="header-logo">JobSathi</span>
        <div className="header-right">
          {!profileComplete ? (
            <OnboardingProgress
              questionsAnswered={progress.questions_answered}
              total={progress.total || 20}
            />
          ) : (
            <span className="agent-badge">
              {currentAgent === 'matching' ? 'Finding Jobs' : 'Profile Done'}
            </span>
          )}
        </div>
      </header>

      {/* ── Profile card (matching phase only) ── */}
      {profileComplete && profile && (
        <ProfileCard profile={profile} />
      )}

      {/* ── Chat area ── */}
      <div className="chat-area">
        {messages.map((msg, i) => (
          <ChatBubble
            key={i}
            message={msg}
            onReplayAudio={playAudio}
          />
        ))}

        {/* Job cards — rendered inline after the last assistant message */}
        {jobCards.length > 0 && (
          <div className="job-cards-panel">
            {jobCards.map((job, i) => (
              <JobCard
                key={job.external_id || i}
                job={job}
                index={i + 1}
                onApply={() => handleApply(i)}
                onSkip={() => handleSkip(i)}
                isApplying={applyingId === i}
              />
            ))}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ── Error banner ── */}
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      {/* ── Voice controls ── */}
      <div className="voice-controls">
        <StatusBar
          isRecording={isRecording}
          isProcessing={isProcessing}
          isPlaying={isPlaying}
          language={language}
        />

        <MicButton
          isRecording={isRecording}
          isProcessing={isProcessing}
          isPlaying={isPlaying}
          onStart={startRecording}
          onStop={stopRecording}
          analyserNode={analyserNode}
          disabled={isProcessing || isPlaying}
        />

        <p className="mic-hint">
          {isRecording
            ? 'Release to send'
            : isPlaying
            ? (
              <button className="replay-hint-btn" onClick={replayLastResponse}>
                Tap to replay
              </button>
            )
            : profileComplete
            ? 'Say "yes", "no", or ask about a job'
            : 'Speak your answer in any language'}
        </p>
      </div>
    </div>
  );
}

// ── Phone Entry Screen ─────────────────────────────────────────────────────────

function PhoneEntryScreen({ phoneInput, setPhoneInput, onSubmit }) {
  const clean = phoneInput.replace(/\D/g, '');
  const isValid = clean.length === 10;

  return (
    <div className="app-container">
      <div className="phone-entry">
        {/* Logo */}
        <div className="logo">
          <span className="logo-mark" aria-hidden="true">
            <svg viewBox="0 0 40 40" width="56" height="56" fill="none">
              <circle cx="20" cy="20" r="20" fill="var(--orange)" opacity="0.15" />
              <circle cx="20" cy="20" r="14" fill="var(--orange)" opacity="0.25" />
              {/* Mic shape */}
              <rect x="16" y="10" width="8" height="13" rx="4" fill="var(--orange)" />
              <path
                d="M12 21a8 8 0 0 0 16 0"
                stroke="var(--orange)" strokeWidth="2.5" strokeLinecap="round"
              />
              <line x1="20" y1="29" x2="20" y2="32" stroke="var(--orange)" strokeWidth="2.5" strokeLinecap="round" />
              <line x1="15" y1="32" x2="25" y2="32" stroke="var(--orange)" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          </span>
          <span className="logo-text">JobSathi</span>
          <span className="logo-tagline">Voice-First Jobs for Every Worker</span>
          <span className="logo-sub">बोलकर नौकरी पाएं — No resume, no app needed</span>
        </div>

        {/* Form */}
        <form onSubmit={onSubmit} className="phone-form">
          <label htmlFor="phone-input" className="phone-label">
            Enter your mobile number to get started
          </label>
          <div className="phone-input-row">
            <span className="country-code">+91</span>
            <input
              id="phone-input"
              type="tel"
              inputMode="numeric"
              value={phoneInput}
              onChange={(e) => setPhoneInput(e.target.value.replace(/\D/g, '').slice(0, 10))}
              placeholder="9876543210"
              maxLength={10}
              autoComplete="tel-national"
              required
            />
          </div>
          <button
            type="submit"
            className="start-btn"
            disabled={!isValid}
          >
            Start — बोलकर नौकरी पाएं
          </button>
          <p className="privacy-note">
            We never share your number. It is only used to save your profile.
          </p>
        </form>

        {/* Language badges */}
        <div className="lang-badges">
          {['हिंदी', 'தமிழ்', 'తెలుగు', 'मराठी', 'বাংলা', 'English'].map(l => (
            <span key={l} className="lang-badge">{l}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
