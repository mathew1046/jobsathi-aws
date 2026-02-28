// components/StatusBar.jsx
// Bottom status indicator showing current voice pipeline state.
// Rendered above the mic button.

export default function StatusBar({ isRecording, isProcessing, isPlaying, language }) {
  const state = isRecording ? 'recording' : isProcessing ? 'processing' : isPlaying ? 'playing' : 'idle';

  const labels = {
    idle: {
      hi: 'बोलने के लिए बटन दबाएं',
      en: 'Hold button to speak',
      ta: 'பேச பட்டனை அழுத்துங்கள்',
      te: 'మాట్లాడటానికి బటన్ పట్టుకోండి',
      mr: 'बोलण्यासाठी बटण दाबा',
    },
    recording: {
      hi: 'सुन रहा हूँ…',
      en: 'Listening…',
      ta: 'கேட்கிறேன்…',
      te: 'వింటున్నాను…',
      mr: 'ऐकतो आहे…',
    },
    processing: {
      hi: 'सोच रहा हूँ…',
      en: 'Processing…',
      ta: 'செயலாக்குகிறேன்…',
      te: 'ప్రాసెస్ చేస్తున్నాను…',
      mr: 'प्रक्रिया करतो आहे…',
    },
    playing: {
      hi: 'बोल रहा हूँ…',
      en: 'Speaking…',
      ta: 'பேசுகிறேன்…',
      te: 'మాట్లాడుతున్నాను…',
      mr: 'बोलतो आहे…',
    },
  };

  const lang = language || 'hi';
  const labelMap = labels[state] || labels.idle;
  const label = labelMap[lang] || labelMap.en;

  const colors = {
    idle:       'var(--text-muted)',
    recording:  'var(--red)',
    processing: 'var(--amber)',
    playing:    'var(--teal)',
  };

  return (
    <div className="status-bar" style={{ '--status-color': colors[state] }}>
      {state === 'recording' && <span className="status-dot status-dot--pulse" />}
      {state === 'processing' && <span className="status-spinner-sm" />}
      {state === 'playing' && <SoundWaveIcon />}
      <span className="status-label">{label}</span>
    </div>
  );
}

function SoundWaveIcon() {
  return (
    <svg viewBox="0 0 20 14" width="18" height="12" fill="none">
      <rect x="0"  y="4" width="2.5" height="6" rx="1.25" fill="var(--teal)" />
      <rect x="4"  y="1" width="2.5" height="12" rx="1.25" fill="var(--teal)" />
      <rect x="8"  y="3" width="2.5" height="8" rx="1.25" fill="var(--teal)" />
      <rect x="12" y="0" width="2.5" height="14" rx="1.25" fill="var(--teal)" />
      <rect x="16" y="4" width="2.5" height="6" rx="1.25" fill="var(--teal)" />
    </svg>
  );
}
