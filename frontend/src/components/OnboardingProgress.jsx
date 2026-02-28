// components/OnboardingProgress.jsx
// Compact progress indicator shown in the header during the 20-question onboarding.
// Shows: filled steps bar + current count + current question label.

export default function OnboardingProgress({ questionsAnswered, total = 20, currentQuestion }) {
  const pct = Math.round((questionsAnswered / total) * 100);

  return (
    <div className="onboarding-progress">
      <div className="op-bar">
        <div className="op-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="op-label">
        <span className="op-count">{questionsAnswered}<span className="op-total">/{total}</span></span>
        {currentQuestion && (
          <span className="op-question">{currentQuestion}</span>
        )}
      </div>
    </div>
  );
}
