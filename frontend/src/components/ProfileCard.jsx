// components/ProfileCard.jsx
// Shown at the top of the matching screen once profile is complete.
// Displays: name/anonymous, primary skill badge, location, experience, wage.

export default function ProfileCard({ profile }) {
  if (!profile) return null;

  const {
    name,
    primary_skill,
    secondary_skills = [],
    years_experience,
    city,
    state,
    expected_daily_wage,
    availability,
  } = profile;

  const skillLabel = primary_skill
    ? primary_skill.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
    : 'Worker';

  const availabilityLabel = {
    immediate:  'Available Now',
    employed:   'Currently Employed',
    '1_week':   'Available in 1 Week',
    '1_month':  'Available in 1 Month',
  }[availability] || 'Available';

  return (
    <div className="profile-card">
      <div className="profile-card__left">
        <div className="profile-avatar">
          {(name || 'W').charAt(0).toUpperCase()}
        </div>
        <div className="profile-info">
          <span className="profile-name">{name || 'Anonymous Worker'}</span>
          <span className="profile-skill-badge">{skillLabel}</span>
        </div>
      </div>
      <div className="profile-card__stats">
        {years_experience && (
          <div className="profile-stat">
            <span className="stat-value">{years_experience}</span>
            <span className="stat-label">yrs exp</span>
          </div>
        )}
        {expected_daily_wage && (
          <div className="profile-stat">
            <span className="stat-value">₹{expected_daily_wage}</span>
            <span className="stat-label">per day</span>
          </div>
        )}
        {city && (
          <div className="profile-stat">
            <span className="stat-value">{city}</span>
            <span className="stat-label">{state || 'India'}</span>
          </div>
        )}
      </div>
      <div className="profile-availability">
        <span className={`avail-dot avail-dot--${availability === 'immediate' ? 'green' : 'amber'}`} />
        {availabilityLabel}
      </div>
    </div>
  );
}
