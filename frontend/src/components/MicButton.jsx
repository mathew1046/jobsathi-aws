// components/MicButton.jsx
// The core interaction element — a large hold-to-speak button with:
//   - Real-time audio level waveform (Web Audio API AnalyserNode)
//   - Animated ring pulse while recording
//   - State-aware appearance (idle / recording / processing / speaking)
//   - Touch-optimized (no tap delay, prevents text selection)

import { useEffect, useRef, useCallback } from 'react';

const WAVEFORM_BARS = 12;

export default function MicButton({
  isRecording,
  isProcessing,
  isPlaying,
  onStart,
  onStop,
  analyserNode,   // optional Web Audio AnalyserNode for live waveform
  disabled,
}) {
  const canvasRef = useRef(null);
  const animFrameRef = useRef(null);
  const dataArrayRef = useRef(null);

  // ── Waveform animation ──────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    if (!isRecording || !analyserNode) {
      // Draw flat line when not recording
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      drawFlatBars(ctx, canvas.width, canvas.height);
      return;
    }

    // Set up analyser data buffer
    analyserNode.fftSize = 64;
    const bufferLength = analyserNode.frequencyBinCount;
    dataArrayRef.current = new Uint8Array(bufferLength);

    const draw = () => {
      animFrameRef.current = requestAnimationFrame(draw);
      analyserNode.getByteFrequencyData(dataArrayRef.current);

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const barWidth = canvas.width / WAVEFORM_BARS;
      const step = Math.floor(bufferLength / WAVEFORM_BARS);

      for (let i = 0; i < WAVEFORM_BARS; i++) {
        const value = dataArrayRef.current[i * step] / 255;
        const barHeight = Math.max(4, value * canvas.height * 0.85);
        const x = i * barWidth + barWidth * 0.2;
        const y = (canvas.height - barHeight) / 2;
        const w = barWidth * 0.6;

        ctx.fillStyle = `rgba(255, 255, 255, ${0.5 + value * 0.5})`;
        ctx.beginPath();
        ctx.roundRect(x, y, w, barHeight, w / 2);
        ctx.fill();
      }
    };

    draw();

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [isRecording, analyserNode]);

  function drawFlatBars(ctx, width, height) {
    const barWidth = width / WAVEFORM_BARS;
    for (let i = 0; i < WAVEFORM_BARS; i++) {
      const x = i * barWidth + barWidth * 0.2;
      const barHeight = 4;
      const y = (height - barHeight) / 2;
      const w = barWidth * 0.6;
      ctx.fillStyle = 'rgba(255,255,255,0.35)';
      ctx.beginPath();
      ctx.roundRect(x, y, w, barHeight, 2);
      ctx.fill();
    }
  }

  // ── Determine button state ───────────────────────────────────────────────
  const state = isRecording ? 'recording'
    : isProcessing ? 'processing'
    : isPlaying ? 'playing'
    : 'idle';

  const stateColors = {
    idle:       'var(--orange)',
    recording:  'var(--red)',
    processing: 'var(--amber)',
    playing:    'var(--teal)',
  };

  const bgColor = stateColors[state];

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handlePointerDown = useCallback((e) => {
    e.preventDefault();
    if (!disabled && state === 'idle') onStart();
  }, [disabled, state, onStart]);

  const handlePointerUp = useCallback((e) => {
    e.preventDefault();
    if (isRecording) onStop();
  }, [isRecording, onStop]);

  return (
    <div className="mic-button-wrapper">
      {/* Outer glow ring — only visible while recording */}
      {isRecording && (
        <>
          <div className="mic-ring mic-ring-1" />
          <div className="mic-ring mic-ring-2" />
        </>
      )}

      <button
        className={`mic-button mic-button--${state}`}
        style={{ '--btn-color': bgColor }}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        disabled={disabled && !isRecording}
        aria-label={
          isRecording ? 'Release to send'
          : isProcessing ? 'Processing…'
          : isPlaying ? 'Speaking…'
          : 'Hold to speak'
        }
      >
        {/* Waveform canvas — shows while recording */}
        <canvas
          ref={canvasRef}
          width={80}
          height={48}
          className={`mic-waveform ${isRecording ? 'mic-waveform--visible' : ''}`}
        />

        {/* Icon overlay — hidden when recording (waveform shows) */}
        {!isRecording && (
          <div className="mic-icon-wrapper">
            {isProcessing ? (
              <SpinnerIcon />
            ) : isPlaying ? (
              <SpeakerIcon />
            ) : (
              <MicIcon />
            )}
          </div>
        )}
      </button>
    </div>
  );
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" className="btn-icon" fill="none">
      <rect x="9" y="2" width="6" height="11" rx="3" fill="currentColor" />
      <path
        d="M5 10a7 7 0 0 0 14 0"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      />
      <line x1="12" y1="17" x2="12" y2="21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <line x1="8"  y1="21" x2="16" y2="21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function SpinnerIcon() {
  return <div className="btn-spinner" />;
}

function SpeakerIcon() {
  return (
    <svg viewBox="0 0 24 24" className="btn-icon" fill="none">
      <polygon points="11,5 6,9 2,9 2,15 6,15 11,19" fill="currentColor" />
      <path d="M15.54 8.46a5 5 0 0 1 0 7.07" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
