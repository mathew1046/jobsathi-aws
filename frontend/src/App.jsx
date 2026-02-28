// App.jsx
// Main JobSathi React app
// Single-page app with three states:
//   1. Phone entry (first visit)
//   2. Onboarding (20 questions via voice)
//   3. Job matching (browse and apply)

import { useState, useEffect, useRef } from 'react';
import { useVoice } from './hooks/useVoice';
import './App.css';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export default function App() {
  const [phoneNumber, setPhoneNumber] = useState('');
  const [phoneSubmitted, setPhoneSubmitted] = useState(false);
  const [messages, setMessages] = useState([]);
  const messagesEndRef = useRef(null);

  const {
    startRecording,
    stopRecording,
    isRecording,
    isProcessing,
    isPlaying,
    error,
    lastTranscript,
    lastResponse,
    progress,
    profileComplete,
    currentAgent,
  } = useVoice(phoneNumber);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Add new messages when voice interaction completes
  useEffect(() => {
    if (lastTranscript || lastResponse) {
      setMessages(prev => [
        ...prev,
        ...(lastTranscript ? [{ role: 'user', text: lastTranscript }] : []),
        ...(lastResponse ? [{ role: 'assistant', text: lastResponse }] : []),
      ]);
    }
  }, [lastTranscript, lastResponse]);

  // Check for saved session on load
  useEffect(() => {
    const savedPhone = localStorage.getItem('jobsathi_phone');
    const savedSession = localStorage.getItem('jobsathi_session_id');
    if (savedPhone && savedSession) {
      setPhoneNumber(savedPhone);
      setPhoneSubmitted(true);
      // Load session state from backend
      loadSessionState(savedPhone);
    }
  }, []);

  const loadSessionState = async (phone) => {
    try {
      const res = await fetch(`${API_BASE}/api/session/${encodeURIComponent(phone)}`);
      const data = await res.json();
      if (data.exists) {
        // Session exists — set a welcome back message
        setMessages([{
          role: 'assistant',
          text: data.profile_complete
            ? 'Welcome back! Ready to find more jobs?'
            : `Welcome back! We had answered ${data.progress?.questions_answered || 0} questions. Let's continue.`
        }]);
      }
    } catch (e) {
      console.error('Could not load session:', e);
    }
  };

  const handlePhoneSubmit = (e) => {
    e.preventDefault();
    if (phoneNumber.length < 10) return;
    localStorage.setItem('jobsathi_phone', phoneNumber);
    setPhoneSubmitted(true);
    // Initial greeting will come when they speak for the first time
    setMessages([{
      role: 'assistant',
      text: 'Hello! I am JobSathi. Press and hold the button below to speak. I will help you find work.'
    }]);
  };

  // Determine status text
  const getStatusText = () => {
    if (isRecording) return 'Listening…';
    if (isProcessing) return 'Processing…';
    if (isPlaying) return 'Speaking…';
    return 'Hold to speak';
  };

  const getStatusColor = () => {
    if (isRecording) return '#E8304A';
    if (isProcessing || isPlaying) return '#F4A300';
    return '#FF6B00';
  };

  // ── Phone Entry Screen ──────────────────────────────────────────────────
  if (!phoneSubmitted) {
    return (
      <div className="app-container">
        <div className="phone-entry">
          <div className="logo">
            <span className="logo-text">JobSathi</span>
            <span className="logo-tagline">Voice-First Jobs for Every Worker</span>
          </div>
          <form onSubmit={handlePhoneSubmit} className="phone-form">
            <label>Enter your phone number to get started</label>
            <div className="phone-input-row">
              <span className="country-code">+91</span>
              <input
                type="tel"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value.replace(/\D/g, ''))}
                placeholder="9876543210"
                maxLength={10}
                required
              />
            </div>
            <button type="submit" className="start-btn" disabled={phoneNumber.length < 10}>
              Start — बोलकर नौकरी पाएं
            </button>
            <p className="privacy-note">
              We never share your number. It is only used to save your profile.
            </p>
          </form>
        </div>
      </div>
    );
  }

  // ── Main Voice Interface ────────────────────────────────────────────────
  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <span className="header-logo">JobSathi</span>
        <div className="header-right">
          {!profileComplete && (
            <div className="progress-pill">
              <div
                className="progress-fill"
                style={{ width: `${progress.percent}%` }}
              />
              <span className="progress-text">
                {progress.questions_answered}/{progress.total}
              </span>
            </div>
          )}
          {profileComplete && (
            <span className="agent-badge">
              {currentAgent === 'matching' ? '🔍 Finding Jobs' : '✓ Profile Done'}
            </span>
          )}
        </div>
      </header>

      {/* Chat area */}
      <div className="chat-area">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            {msg.role === 'assistant' && (
              <div className="agent-avatar">JS</div>
            )}
            <div className="message-bubble">
              {msg.text}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Error display */}
      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      {/* Voice controls */}
      <div className="voice-controls">
        <div className="status-text" style={{ color: getStatusColor() }}>
          {getStatusText()}
        </div>

        {/* The big mic button — hold to record */}
        <button
          className={`mic-button ${isRecording ? 'recording' : ''} ${isProcessing || isPlaying ? 'busy' : ''}`}
          onMouseDown={startRecording}
          onMouseUp={stopRecording}
          onTouchStart={(e) => { e.preventDefault(); startRecording(); }}
          onTouchEnd={(e) => { e.preventDefault(); stopRecording(); }}
          disabled={isProcessing || isPlaying}
          aria-label="Hold to speak"
        >
          {isRecording ? (
            <svg viewBox="0 0 24 24" className="mic-icon">
              <rect x="9" y="3" width="6" height="10" rx="3" fill="currentColor"/>
              <path d="M5 11a7 7 0 0 0 14 0" fill="none" stroke="currentColor" strokeWidth="2"/>
              <line x1="12" y1="18" x2="12" y2="21" stroke="currentColor" strokeWidth="2"/>
              <line x1="8" y1="21" x2="16" y2="21" stroke="currentColor" strokeWidth="2"/>
            </svg>
          ) : isProcessing ? (
            <div className="spinner" />
          ) : (
            <svg viewBox="0 0 24 24" className="mic-icon">
              <rect x="9" y="3" width="6" height="10" rx="3" fill="currentColor" opacity="0.7"/>
              <path d="M5 11a7 7 0 0 0 14 0" fill="none" stroke="currentColor" strokeWidth="2" opacity="0.7"/>
              <line x1="12" y1="18" x2="12" y2="21" stroke="currentColor" strokeWidth="2" opacity="0.7"/>
              <line x1="8" y1="21" x2="16" y2="21" stroke="currentColor" strokeWidth="2" opacity="0.7"/>
            </svg>
          )}
        </button>

        <p className="mic-hint">
          {isRecording
            ? 'Release to send'
            : profileComplete
            ? 'Say "yes", "no", or ask a question'
            : 'Speak your answer'}
        </p>
      </div>
    </div>
  );
}
