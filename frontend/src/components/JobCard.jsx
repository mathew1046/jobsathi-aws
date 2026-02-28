// components/JobCard.jsx
// Displays a single job match result.
// Used in the matching phase — after profile is complete.
//
// The card shows:
//   - Job title and company
//   - Location and salary
//   - Experience match indicator
//   - Apply / Skip / Details action row

export default function JobCard({ job, index, onApply, onSkip, isApplying }) {
  const {
    title,
    company,
    location,
    salary_min,
    salary_max,
    job_type,
    description,
    source,
  } = job;

  const salaryText = salary_min
    ? salary_max && salary_max !== salary_min
      ? `₹${salary_min}–${salary_max}/day`
      : `₹${salary_min}/day`
    : 'Salary not listed';

  const typeLabel = {
    full_time:   'Full Time',
    contract:    'Contract',
    daily:       'Daily Wage',
    daily_wage:  'Daily Wage',
    part_time:   'Part Time',
  }[job_type] || 'Regular Work';

  return (
    <div className="job-card">
      <div className="job-card__header">
        <div className="job-card__number">#{index}</div>
        <div className="job-card__badge">{typeLabel}</div>
      </div>

      <h3 className="job-card__title">{title || 'Job Opportunity'}</h3>

      <div className="job-card__company">
        <CompanyIcon />
        <span>{company || 'Local Company'}</span>
      </div>

      <div className="job-card__details">
        <div className="job-card__detail">
          <LocationIcon />
          <span>{location || 'Location not listed'}</span>
        </div>
        <div className="job-card__detail job-card__detail--salary">
          <RupeeIcon />
          <span>{salaryText}</span>
        </div>
      </div>

      {description && (
        <p className="job-card__desc">
          {description.length > 120 ? description.slice(0, 120) + '…' : description}
        </p>
      )}

      <div className="job-card__actions">
        <button
          className="job-action-btn job-action-btn--skip"
          onClick={onSkip}
          disabled={isApplying}
          aria-label="Skip this job"
        >
          <SkipIcon />
          Skip
        </button>
        <button
          className="job-action-btn job-action-btn--apply"
          onClick={onApply}
          disabled={isApplying}
          aria-label="Apply for this job"
        >
          {isApplying ? (
            <span className="btn-spinner btn-spinner--sm" />
          ) : (
            <ApplyIcon />
          )}
          {isApplying ? 'Applying…' : 'Apply'}
        </button>
      </div>

      {source && (
        <div className="job-card__source">via {source}</div>
      )}
    </div>
  );
}

function CompanyIcon() {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" opacity="0.6">
      <path d="M3 21h18M3 7h18M3 3h18M9 21V7M15 21V7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
function LocationIcon() {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 22s-8-4.5-8-11.8A8 8 0 0 1 12 2a8 8 0 0 1 8 8.2c0 7.3-8 11.8-8 11.8z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}
function RupeeIcon() {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" opacity="0.8">
      <text x="4" y="18" fontSize="16" fontFamily="sans-serif">₹</text>
    </svg>
  );
}
function SkipIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}
function ApplyIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
