# JobSathi: How I Built a Voice-First AI Job Platform for India's 300 Million Invisible Workers

Every day, 10 million blue-collar workers in India wake up and walk to a street corner hoping someone drives by and picks them for work. In 2025. With AI everywhere and LLMs that can write poetry in fourteen languages. The problem was never a lack of workers or a lack of jobs. It was that the entire infrastructure of finding work, portals, resumes, application forms, profile pictures, cover letters, was designed by educated people, for educated people. And the 300 million workers who keep India's buildings standing, its pipes flowing, its wires connected, and its households running were simply never part of the design conversation.

JobSathi changes that. Not by building a better job app. By questioning whether a job app was ever the right answer to begin with.

**App Category: Social Impact**

---

![JobSathi hero overview: voice-first AI job platform connecting 300M blue-collar workers to the formal economy, showing the three channels and AWS services powering them](img1_jobsathi_overview.png)

---

## The Problem: A System Built for the Wrong Person

### The Labor Naka — Where India's Hiring System Actually Lives

On any given morning in Pune, Nagpur, Patna, or a hundred other Indian cities, you will find groups of men gathered at what locals call a labor naka, an informal street corner, usually near a hardware store or a main road intersection, where daily wage workers wait for contractors to arrive and hire them by the hour. There is no listing. No interview. No contract. A contractor drives up, sizes up the crowd, picks the faces he recognizes or the ones that look fit enough for the day's work, negotiates a rate on the spot, and drives away with a truckload of workers who may or may not be paid what was verbally agreed.

This is how India's construction workers, electricians, plumbers, painters, masons, domestic helpers, and factory hands find work in 2025. Word of mouth. Physical presence. Whoever shows up earliest. Middlemen who take 10 to 30 percent from both sides.

It is not a niche problem. It is the primary employment mechanism for the largest workforce segment in the country.

300+ million blue-collar workers in India are employed through informal channels. To put that in context, that is a workforce larger than the entire population of the United States, and virtually none of them have a resume, a professional profile, or any searchable presence in the formal job market.

The literacy barrier is real but deeply misunderstood. The narrative around India's informal workers tends to conflate skill with literacy. These are not the same thing. A mason with 15 years of experience laying earthquake-resistant foundations has more practical expertise than most credentialed professionals. A domestic helper who has managed the households of three families simultaneously possesses organizational capability that would be remarkable in any context. The problem is not skill. The problem is that the systems used to signal and market skill, resumes, profiles, certifications, all require literacy, and literacy in a language other than the one these workers grew up speaking.

Every existing job platform makes the same fatal assumption. Open any major Indian recruitment app. The first thing it asks you to do is type your name. Then your email address. Then your work history in text. Then upload a document. For a construction worker in rural Jharkhand who completed four years of schooling and has never typed a sentence in his life, the experience ends at step one. The app was not built for him. It was built for someone who looks nothing like him.

The employer side of the problem is equally broken. A construction company in Bengaluru trying to staff a 200-unit residential project needs 40 electricians with at least three years of experience, willing to relocate for six months. Their current process: call three contractors they know, ask those contractors to call their contacts, wait three days for names and numbers, make individual phone calls, try to verify experience through word of mouth, and hope that the workers who show up on day one are who they said they were. It is unreliable, geographically limited, and produces no verifiable record of who was hired and why.

The middleman economy is not just inefficient — it is exploitative. Workers in the informal hiring system frequently earn 20 to 40 percent less than the actual market rate for their skills because they have no visibility into what others are earning and no leverage to negotiate. Contractors who engage middlemen pass the commission cost onto workers through lower wages. Workers who resist middlemen lose access to jobs entirely. The information asymmetry is the product, and it extracts money from people who can least afford to lose it.

The downstream consequences compound over time. Because blue-collar workers have no formal employment records, they are invisible to the formal financial system. No bank will give them a loan. No insurance company will write them a policy without collateral. They cannot access government schemes that require employment documentation. A worker who has earned a living every day for thirty years has nothing to show for it in a system that demands paper proof. JobSathi is a job platform on day one. It is the foundation of financial identity over time.

---

![The vicious cycle: no formal record means no access to credit, insurance, or welfare, which means permanent dependence on the informal system](img3_vicious_cycle.png)

---

## The Solution: Talk Your Way Into a Job

### What JobSathi Actually Does

What if getting a job required nothing more than picking up any phone and speaking in your own language?

That is the entire product concept. A worker in Pune who has spent eight years doing tile and mosaic work picks up a phone — a feature phone, a smartphone, it does not matter — and says "main tile ka kaam karta hoon, kaam chahiye" (I do tile work, I need a job). Within minutes, a complete job profile has been constructed on their behalf, matched against real openings in their area, and submitted to employers who are actively looking for exactly that skill. No forms. No typing. No English. No resume. No middleman.

The worker does not need to know what a database is. They do not need to know what an API call is. They do not need to know that behind their thirty-second voice note, an orchestrated chain of AI agents running on AWS just did what would have taken a professional recruiter two days.

### The Three Channels — Designed Around Where Workers Already Are

JobSathi does not ask users to download a new app and learn a new interface. It meets them where they already are.

The **Web App** is designed for workers who have a smartphone and basic digital familiarity. The interface is radically simplified, a single large microphone button, large text in the user's detected language, and no navigation menus that require reading. The entire experience is voice-driven. Tap the button, speak, listen to the response. The visual interface exists as a safety net, not as the primary interaction mode.

**WhatsApp** is where the majority of Indian workers already live digitally. More than 500 million Indians use WhatsApp daily, including a significant portion of the blue-collar workforce who use it to receive construction site photos, communicate with family, and share voice notes. JobSathi integrates directly into WhatsApp through the Meta Business API. A worker sends a voice note. The system responds with a voice note. The entire job-seeking process happens inside a chat they already know how to use.

**Phone Call via PSTN** is the deepest reach, and arguably the most important channel. An AWS Connect toll-free number works on any phone made in the last thirty years, a basic keypad phone with no internet, no WhatsApp, no data plan. A worker can call from a payphone. They can borrow a neighbor's feature phone. The IVR experience is fully conversational, driven by the same agent stack that powers the web app, and it works for the 150 million Indian workers who do not own a smartphone.

---

![Three channels, one backend: web app for smartphone users, WhatsApp for messaging-first users, toll-free call for feature phone users](img5_three_channels.png)

---

### The Employer Panel: The Other Half of the Marketplace

A two-sided marketplace only works if both sides have a reason to show up. For employers, JobSathi provides a dedicated dashboard that solves a problem they currently have no good solution for.

Employers, construction companies, facility management firms, manufacturing units, staffing agencies, individual contractors — register on the platform with GST verification. They post job requirements specifying the skill category, location, minimum experience, salary range, and number of openings. The system immediately begins matching their requirements against the worker profile database and surfaces ranked candidates with structured profiles showing skills, experience years, location, and work history.

Employers can directly contact matched workers through the platform, which handles the outreach in the worker's preferred language. They can schedule interviews, shortlist candidates, and track hiring status through a dashboard that feels familiar to anyone who has used a modern HR tool. The difference is that the candidate pool they are accessing was never available to them before — workers who had no digital presence, no resume, and no way to be found.

Workers use the platform free. Employers pay for verified candidate access through subscription tiers. This is the monetization model, and it is clean precisely because the value is clear: for the first time, employers have structured access to a labor pool that was previously only accessible through informal networks and middlemen.

---

## How It Works: The Complete Technical Architecture

### One Endpoint, Five Agents, Infinite Conversations

The architectural principle behind JobSathi is deceptively simple: there is exactly one API endpoint that the outside world talks to. Everything else — the routing logic, the agent selection, the language detection, the database reads and writes, the employer notifications — happens behind that single entry point.

This is not a microservices architecture with separate services for each function. Each "agent" is a module within the same backend application, a function with its own system prompt, its own set of tools, and its own domain of responsibility. The orchestrator decides which module handles each incoming message. The result is a system that is easy to understand, easy to debug, and easy to scale.

The backend runs on Amazon ECS Fargate, a containerized, serverless compute platform that eliminates the need to manage EC2 instances while providing the persistent, low-latency connections that voice streaming requires. Lambda would introduce cold start latency that is unacceptable in a real-time voice conversation. Fargate stays warm, scales horizontally when call volume increases, and handles the sustained WebSocket connections that audio streaming demands.

Every incoming request, whether from a WhatsApp webhook, a web app API call, or an AWS Connect audio stream, hits Amazon API Gateway, which routes it to the Fargate backend. The backend loads the user's session from Amazon ElastiCache Redis, determines context, selects the appropriate agent, runs the LLM call via Amazon Bedrock, updates the session, writes any new data to Amazon RDS PostgreSQL, and returns a response. The entire round trip, from audio received to audio response, takes under three seconds.

---

![The complete JobSathi flow: from a worker's voice note to a matched job application in under five minutes](img4_complete_flow.png)

---

### The Five Agents: A Deep Dive

#### Agent 1 — The Voice and Language Agent: The Front Door

Before any job can be found or any profile built, the system must understand what the user is saying, and in a country with 22 scheduled languages, hundreds of dialects, and code-switching that blends Hindi with English and regional languages mid-sentence, this is not a trivial problem.

The Voice and Language Agent is the first thing that touches every user interaction across every channel. Its job is threefold: convert audio to text, identify the language and dialect being spoken, and convert all system responses back to natural-sounding speech in that same language and dialect.

Speech to Text is handled by Amazon Transcribe with Indian language models. Transcribe's support for Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi, Bengali, Gujarati, and Punjabi covers the primary languages of India's blue-collar workforce. For dialect handling, Bhojpuri, Haryanvi, Chhattisgarhi, and the dozens of regional variants that differ meaningfully from standard forms — the agent applies a post-processing layer that normalizes common dialectal variations before passing text to downstream agents. This is one of the hardest engineering problems in the product, and it is solved incrementally through real-world testing with actual users rather than through any single technical breakthrough.

Language Detection happens in parallel with transcription. The agent uses the transcribed text to confirm the language and tag the session so that all subsequent responses are delivered in the same language. A worker who speaks in Tamil gets a Tamil response. A worker who mixes Hindi and English gets a response that mirrors that same mix. The goal is not perfect linguistic purity but natural, comfortable communication.

Text to Speech is handled by Amazon Polly, which supports neural TTS voices for all major Indian languages. Neural voices are critical here — a robotic, clearly synthetic voice creates an uncanny, untrustworthy experience. Neural Polly voices in Hindi and Tamil are indistinguishable from natural speech to most listeners, which is what makes the interaction feel like a conversation rather than a system. Other relevant files would be translated to all available language and be pre-fetched whenever necessary.

This agent does not make any business decisions. It does not know what a job is or what a profile is. It only translates between human voice and system text, in both directions, for every interaction.

#### Agent 2 — The Onboarding Agent: The Invisible Form

The Onboarding Agent is where the product's core design philosophy becomes most tangible. Its purpose is to learn who the worker is — their skills, their experience, their location, their availability, their salary expectations — and store that information in a structured database record. What makes it distinctive is that it accomplishes this entirely through natural conversation, with the worker never aware that they are completing what is functionally a job application form.

The agent is powered by Amazon Bedrock and uses a carefully constructed system prompt that instructs it to behave as a friendly, patient, helpful local contact rather than a software system. It asks one question at a time. It acknowledges what the worker says before asking the next question. It handles tangents, corrections, and incomplete answers gracefully. If a worker says "main painting karta hoon, aur kabhi kabhi whitewash bhi" (I do painting, and sometimes whitewash too), the agent extracts two distinct skills from that single sentence without requiring the worker to enumerate them separately.

The data extracted through this conversation is saved incrementally to Amazon RDS after every response. This is a critical architectural decision: if a call drops, if WhatsApp disconnects, if the worker walks into a no-signal zone mid-conversation, the session resumes from exactly where it stopped. Nothing is lost. The worker does not have to start over. This reliability is not a nice-to-have — for a user population that frequently deals with unreliable connectivity, it is the difference between a product that works and one that gets abandoned.

The agent knows when a profile is complete enough to be useful. It does not demand perfection. A profile with a verified phone number, one skill category, a location, and an approximate salary expectation is enough to start matching against jobs. The agent surfaces additional questions over subsequent interactions as the worker engages with the platform more. The profile deepens over time rather than demanding completeness upfront.

What gets collected:

- Name (optional, many workers prefer to remain semi-anonymous initially)
- Primary and secondary skill categories (construction, electrical, plumbing, painting, driving, domestic work, security, factory work, and 40+ subcategories)
- Years of experience per skill
- Location: state, district, city, neighborhood
- Willingness to relocate and travel radius
- Current employment status
- Expected daily or monthly wage
- Preferred working hours and availability
- Languages spoken
- Whether they have prior formal employment records or references

None of this is collected through a form. All of it emerges through conversation.

#### Agent 3 — The Job Matching Agent: Finding the Right Work

With a complete profile, the Job Matching Agent's task is to find the best available jobs for this worker at this moment. It queries the jobs database with a multi-dimensional filter: primary skill match, location proximity, salary compatibility, experience requirements, and language preference of the hiring employer.

The matching algorithm runs in order of specificity. A worker who lists tile work as their primary skill and lives in Pune will first see tile work jobs in Pune. If fewer than five results are found, the radius expands to 50 kilometers. If experience requirements exceed the worker's stated years, those jobs are shown with a note rather than excluded entirely, because a worker who says they have "around 3 years" of experience may have more than they are articulating.

Results are presented not as a list but as individual spoken descriptions. The agent says, in the worker's language, something like: "Aapke liye ek achha option mila — Hinjewadi mein ek construction company ko tile workers chahiye, 180 rupaye per hour, kaam subah 8 baje se shaam 6 baje tak, 3 mahine ka contract. Kya aap is kaam mein interested hain?" (I found a good option for you — a construction company in Hinjewadi needs tile workers, 180 rupees per hour, work from 8am to 6pm, 3-month contract. Are you interested in this work?)

The worker says yes or no. If yes, the Application Agent takes over immediately. If no, the next option is presented. If the worker asks a question — "kitna door hai?" (how far is it?) — the agent answers from the job record before returning to the choice. The conversation never feels like a search interface. It feels like advice from someone who knows the local job market.

#### Agent 4 — The Application Agent: Doing the Work the Worker Cannot

When a worker says yes to a job, the Application Agent handles every subsequent step autonomously. It creates the application record in the database, sends a structured notification to the employer through the platform, and dispatches a confirmation to the worker through their preferred channel — a WhatsApp message or an SMS that says, in Hindi or Tamil or Bengali, that their application has been submitted and they will hear back.

The agent then becomes the worker's representative in the hiring process. When the employer views the profile, it sends the worker a voice notification. When the employer shortlists the candidate, the worker is notified with details about what happens next. When an interview is scheduled, the worker receives the time, location, and employer contact in a format they can actually use — not a calendar invite, but a spoken message and an SMS with the details written out simply.

The agent also handles rejection gracefully. If a worker is not selected, they receive a message that explains this clearly, without corporate HR language, and immediately offers the next available matching opportunity. The worker is never left wondering what happened to their application.

#### Agent 5 — The Employer Agent: The Professional Dashboard

The Employer Agent operates in a completely different mode from the worker-facing agents. Employers are assumed to be digitally literate, operating through a web dashboard, and requiring structured data and business-grade features. The agent powers the backend logic of the employer panel without requiring any voice interaction.

Through the employer dashboard, companies can post job requirements with detailed specifications, browse the pre-screened candidate pool with filters for skill, location, experience, and availability, view structured worker profiles with verified skill listings and work history summaries, initiate contact with candidates through the platform, track the status of all active job postings, and manage interview pipelines across multiple openings simultaneously.

The agent also handles bulk operations — a contractor who needs 25 workers for a project can post the requirement once and receive a ranked list of 25 best-matched candidates rather than making 25 individual hiring decisions. For large employers who need to staff multiple sites in multiple cities, this operational efficiency alone justifies the subscription cost.

---

### The Orchestrator — One Brain to Route Them All

The orchestrator is not a separate service. It is the decision layer at the top of the FastAPI backend that runs on ECS Fargate. Every incoming message, from any channel, arrives here first.

The orchestrator's job is to answer three questions for every interaction:

**Who is this?** It loads the user's session from ElastiCache Redis using their phone number as the key. The session contains their current agent context, their conversation history for the last 10 turns, their profile completion status, and any pending application updates that need to be delivered.

**What do they need right now?** Using the conversation history and the current message, the orchestrator classifies the intent. Is this a new user who needs onboarding? An existing user looking for jobs? A user checking on an application status? An employer posting a job? The classification uses a lightweight intent detection prompt against Bedrock rather than a rule-based system, which handles the messy real-world cases like "maine kaam apply kiya tha, kuch hua?" (I had applied for work, did anything happen?) — something that rule-based systems fail on.

**Which agent handles this?** Based on intent and session state, the orchestrator routes the interaction to the appropriate agent module, passes it the session context, waits for the response, updates the session state, and returns the response to the channel layer for delivery.

The entire orchestration flow is synchronous from the perspective of the user — they speak, they wait two to three seconds, they hear a response. Asynchronous operations, like sending employer notifications or updating application records, happen in the background via Amazon SQS without adding to the user-facing latency.

---

![The full system architecture: API Gateway, ECS Fargate backend, five agent modules, and the AWS services layer underneath](img6_system_architecture.png)

---

### The Calling Pipeline — The Most Important Channel No One Talks About

The phone call channel deserves its own section because it is the most technically complex piece of the system and the one with the greatest social significance. Everything described above — the agent architecture, the multilingual voice pipeline, the job matching — all of it is available to a person with a 15-year-old Nokia keypad phone and no internet connection. That is not a minor detail. That is the feature that makes this product matter at the scale India requires.

AWS Connect acts as the PSTN interface. When a worker dials the toll-free number, Connect answers the call and immediately begins streaming the audio to the backend via a WebSocket connection. There is no IVR menu asking the worker to "press 1 for Hindi" — language detection happens automatically from the first utterance.

The audio stream arrives at the Fargate backend in real time. Amazon Transcribe processes it in streaming mode, returning transcription results as the worker speaks rather than waiting for them to finish. This streaming transcription is what allows the system to respond in two to three seconds rather than waiting for the worker to hang up and then processing the entire call.

Once the transcribed text hits the orchestrator, the flow is identical to any other channel — session load, intent detection, agent routing, Bedrock call, response generation. The response text then goes to Amazon Polly in streaming synthesis mode, which begins returning audio before the full response has been generated. AWS Connect receives the audio stream and plays it back to the worker in real time.

The result is a telephone conversation that feels natural. The worker speaks. There is a brief pause. A natural-sounding voice responds in their language. They ask a follow-up. It responds again. The entire profile creation, job matching, and application submission flow can be completed in a single phone call of under ten minutes — on a phone that cannot run WhatsApp, cannot display a website, and cannot process a push notification.

### The WhatsApp Flow — Meeting 500 Million Users Where They Live

WhatsApp is not just a messaging app in India. For hundreds of millions of Indians, it is the internet. They receive family photos, government announcements, job site updates, and daily news entirely through WhatsApp. They are comfortable with voice notes, document sharing, and group chats. They are not comfortable with app downloads, account registrations, and multi-step onboarding flows.

JobSathi's WhatsApp integration uses the Meta Business API to create a fully functional two-way conversational interface within WhatsApp. When a worker sends a voice note to the JobSathi WhatsApp number, the backend receives it as a webhook, downloads the audio file from Meta's servers, processes it through the same voice and language pipeline used by the phone call channel, runs the orchestrator and agent logic, and returns a response as a WhatsApp voice note.

The worker never leaves WhatsApp. They never download anything. They never create an account — their phone number, already verified by WhatsApp, becomes their JobSathi identity automatically.

For workers who are more comfortable with text, the same number accepts text messages and responds in text. For workers who want to share a document, an Aadhaar card photo for identity verification, or a certificate from a previous employer — they can attach it to a WhatsApp message and the system processes it automatically. The channel is fully multimodal while remaining anchored in an interface the user already trusts.

WhatsApp also serves as the primary notification channel for application updates. When an employer shortlists a worker, the worker receives a WhatsApp message — in their language — within 60 seconds. When an interview is scheduled, the details arrive as a WhatsApp message that reads like it was written by a helpful person rather than generated by a system.

---

## AWS Services — Why Each One Was Chosen

### Why ECS Fargate Over Lambda for the Core Backend

This is a question worth answering precisely because Lambda is the obvious first choice for a serverless application and the reasons to deviate from it are not immediately obvious.

Lambda is excellent for stateless, short-duration, event-driven tasks. It is poorly suited for sustained, low-latency connections of the kind that real-time audio streaming requires. A phone call that lasts eight minutes involves a continuous audio stream being processed every 200 milliseconds. Lambda's cold start latency — even with provisioned concurrency — introduces jitter that creates an unacceptably choppy experience. Lambda's maximum execution time of 15 minutes is also a constraint for long conversations.

ECS Fargate containers start once and stay warm. The streaming audio WebSocket connection persists for the duration of the call without interruption. Horizontal scaling happens at the container level, adding new instances as call volume increases, and CloudWatch auto-scaling handles this automatically. Lambda is still used for the things it is excellent at — processing completed applications asynchronously, generating PDF resumes in the background, syncing new job postings to the OpenSearch index — but the voice pipeline runs on Fargate.

| AWS Service | Role | Why This One |
|---|---|---|
| Amazon ECS Fargate | Core backend runtime | Warm containers for streaming; no cold start |
| Amazon Bedrock | LLM for all 5 agents | Managed, no infrastructure; Claude for nuanced conversation |
| Amazon Connect | PSTN toll-free calling | Native audio streaming to backend; works on any phone |
| Amazon Transcribe | Speech to text | Indian language models; streaming mode |
| Amazon Polly | Text to speech | Neural voices for Indian languages; streaming synthesis |
| Amazon RDS PostgreSQL | Primary database | Relational structure for profiles, jobs, applications |
| Amazon ElastiCache Redis | Session cache | Sub-millisecond session reads across channels |
| Amazon S3 | Audio and document storage | Durable, cheap, lifecycle policies for old audio |
| Amazon API Gateway | Entry point | HTTPS + WebSocket; rate limiting; request routing |
| Amazon Cognito | Authentication | OTP via phone number; no password required |
| Amazon SQS | Async task queue | Background processing without blocking voice pipeline |
| Amazon SNS | Notifications | SMS and WhatsApp delivery for application updates |
| Amazon OpenSearch | Search at scale | Phase 3; geographic proximity + multi-attribute filtering |
| Amazon CloudWatch | Monitoring | Latency dashboards; auto-scaling triggers |

### The Employer Panel — A Product in Its Own Right

The employer-facing side of JobSathi deserves attention as a product, not just as the monetization mechanism. The problem it solves — accessing a skilled, pre-verified informal workforce — is one that every construction company, facility management firm, and manufacturing unit in India struggles with, and the current solutions range from bad to worse.

The employer dashboard is a React web application hosted on S3 and served through CloudFront. It is designed to feel familiar to anyone who has used a modern HR tool — clean data tables, filter panels, candidate cards with skill and experience summaries, and pipeline views that show where each candidate is in the hiring process.

**Job Posting** is a structured form that takes five minutes to complete. Skill category, subcategory, location, minimum experience, salary range, number of openings, job duration, and any specific requirements. Once posted, the matching algorithm immediately begins surfacing candidates. The employer does not wait — by the time they finish posting, there are already candidates in their queue.

**Candidate Browse** is the feature employers will spend the most time in. Workers appear as structured profiles — not resumes, but clean cards showing their primary skill, years of experience, location, current availability, expected wage, and a brief work history summary generated from their onboarding conversation. Employers can filter the entire pool by any combination of these attributes. For a contractor who needs plasterers in Nagpur willing to accept 500 rupees per day, a single filter query surfaces the exact candidates.

**Direct Outreach** happens through the platform. The employer clicks a contact button, selects a message type (interview invitation, job offer, information request), and the system delivers that message to the worker in their language via WhatsApp or SMS. The employer never needs the worker's personal phone number — the platform mediates all contact until both parties have agreed to proceed. This protects worker privacy while ensuring employer outreach actually reaches the right person.

**Analytics Dashboard** shows the employer their hiring funnel — postings created, candidates matched, profiles viewed, applications received, interviews scheduled, workers hired. Over time this data tells employers where their pipeline is healthy and where it is leaking, enabling more precise job posting that attracts better-matched candidates.

---

## The Impact Mathematics — Why This Scale Matters

The economic case for JobSathi is not subtle. It can be stated precisely.

**For workers:** A construction worker in Pune earning 450 rupees per day through a middleman network could earn 600 rupees for the same work found through JobSathi, because the middleman's 25 percent margin is no longer extracted. Over 250 working days, that is 37,500 rupees — approximately three months of additional income — returned to the worker every year. Multiplied across 10 million workers as the platform scales, this represents billions of rupees redistributed from informal intermediaries to the workers who actually do the labor.

**For employers:** A construction company currently spending 3 to 4 days and significant management time to staff each project can reduce that to under 2 hours using JobSathi's candidate pool. At scale, this productivity gain is worth more to employers than the subscription fee by an order of magnitude, which is what makes the subscription model sustainable.

**Beyond economics:** A worker who has a verified profile with a documented work history is eligible for the Pradhan Mantri Shram Yogi Maan-dhan pension scheme, the e-Shram social security card, and microfinance loans that require employment verification. JobSathi's profile becomes the key that unlocks access to these schemes — schemes that exist specifically to help this population but that require formal documentation most of them have never had.

The goal is not to build a better job app. It is to make the formal economy accessible to people the formal economy has always conducted business around. The job match is the first step. The formal identity it creates is the lasting change.

---

## How I Built This — Phase by Phase

### Phase 1 — Voice Pipeline and the Onboarding Agent: Proving the Core Hypothesis

The only question Phase 1 answers is this: can a semi-literate blue-collar worker in a tier-3 Indian city create a complete job profile using nothing but their voice, on the first try, without any guidance?

Everything else — job matching, employer panel, monetization — is secondary until this question has a confident yes as an answer.

Phase 1 infrastructure is deliberately minimal. ECS Fargate running the FastAPI backend. Amazon Transcribe for Hindi speech-to-text. Amazon Polly for response audio. Amazon RDS for profile storage. ElastiCache for session management. The Onboarding Agent powered by Bedrock. Nothing else.

Testing happens with 20 to 30 real workers from the target demographic — construction workers, domestic helpers, drivers — recruited through community organizations and NGO partners. Sessions are recorded with consent and reviewed to find every point where the conversation breaks down, where the language fails, where the worker gets confused or drops off. Every finding drives a revision to the agent's system prompt, the language handling logic, or the question sequence. This iterative refinement continues until completion rates consistently exceed 80 percent. Only then does Phase 2 begin.

### Phase 2 — Job Matching and WhatsApp: Building Both Sides of the Marketplace

Phase 2 adds the Job Matching Agent and the Application Agent on the worker side, and a basic version of the Employer Panel on the other side. The WhatsApp channel is added as the primary delivery mechanism, since it reaches more of the target demographic than any other digital channel.

A closed pilot runs with 5 to 10 employers and 100 workers in one city — Pune or Bengaluru, where the construction and domestic services markets are large enough to generate real matching signal. The metrics that matter are not vanity metrics. They are: profile completion rate, job match acceptance rate (does the worker say yes when offered a match), application-to-interview conversion rate, and interview-to-hire rate. These are the numbers that tell you whether the matching is working, not just whether people are signing up.

Phase 2 ends when 10 confirmed hires have been made through the platform — workers who received jobs they would not have received otherwise, employers who hired workers they would not have found otherwise. Ten hires is a small number. It is also proof that the product does what it claims to do.

### Phase 3 — AWS Connect and Geographic Expansion: The Depth of Reach

Phase 3 adds the phone call channel via AWS Connect, which is both the technically hardest channel to implement and the one with the highest social impact. Workers with feature phones and no internet access can now participate fully in the platform.

Geographic expansion begins in Phase 3. The second and third city are chosen based on where Phase 2 employer demand is strongest — where do employers have the largest unsatisfied need for skilled informal workers? Moving into those markets first creates the fastest path to matching density, which is what makes the product valuable on both sides.

Amazon OpenSearch is added in Phase 3 as the primary search layer, replacing direct PostgreSQL queries for job and candidate search. At 10,000 workers and 1,000 active job postings, PostgreSQL array queries are fast enough. At 100,000 workers and 10,000 postings, full-text search with geographic proximity ranking and multi-attribute filtering requires a dedicated search engine.

### Phase 4 — Monetization, Verification, and Intelligence

Phase 4 is where the business model becomes sustainable and the data begins generating value beyond individual transactions.

Employer subscription tiers launch — a free tier with limited monthly profile views, a professional tier with unlimited access and advanced filters, and an enterprise tier with bulk hiring workflows, API access, and dedicated account support. The pricing is set against the value of a single successful hire, which for most employers is well above the cost of any subscription tier.

Aadhaar-based identity verification is added for workers who want to unlock higher-trust opportunities — some employers, particularly in domestic work and security, require identity verification before hiring. Workers opt into this voluntarily, and verified profiles are marked distinctly in the candidate pool.

Regional skill data begins being published — anonymized, aggregated reports on skill availability by district, average wage rates by category, and demand signals from employer job postings. This data is valuable to government planning agencies, NGO workforce development programs, and the construction and manufacturing industries who need to plan labor procurement for large projects. It becomes a revenue line in its own right.

---

## What Building This Taught Me

### ① Voice is not a feature. It is the architecture.

The most common mistake in building accessible products is treating accessibility as a feature layer added on top of a standard product. A screen reader added to a text-first interface. A voice assistant bolted onto a form-based application. These retrofits never work well because the underlying information architecture was designed for a different mode of interaction.

JobSathi's information architecture was designed from day one around voice as the primary channel. The onboarding flow asks one question at a time not because that is a nice UX pattern but because that is how natural voice conversation works. The job matching results are presented as spoken descriptions rather than lists because lists require a user to scan, hold multiple items in working memory, and compare — cognitive operations that are harder in audio than in text. Every decision downstream of "voice first" is shaped by that constraint.

When voice is the architecture, the product works natively for users who cannot read. As a side effect, it works better for users who can read but are in hands-free situations — driving, cooking, working on a construction site. Radical accessibility turns out to be good design for everyone.

### ② The dialect problem is harder than the language problem.

Building for Hindi is a solved problem. Amazon Transcribe handles standard Hindi well. Building for the Hindi that a construction worker from Bhojpur district in Bihar actually speaks — with its distinct phonology, vocabulary, and syntactic patterns — is a significantly harder problem that no off-the-shelf model fully solves.

The approach that works is not finding a better model. It is investing in real-world testing with speakers of each target dialect, identifying the specific patterns that cause transcription errors, and building post-processing normalization layers that map dialectal forms to standard equivalents before the text reaches the agent. This normalization is a living codebase that grows with each new dialect and error pattern discovered in the field. It is never finished. It gets incrementally better.

The lesson for any voice product targeting India's informal workforce: plan for dialect handling as a core engineering investment, not an edge case. Your target users do not speak the standard dialect your model was trained on.

### ③ Incremental persistence is the reliability feature your users need most.

Workers in rural India have unreliable phone networks. Calls drop. WhatsApp connections time out. A user who has answered eight onboarding questions and then loses connection needs to find all eight answers preserved when they reconnect, not start over from the beginning.

Designing the Onboarding Agent to write each piece of collected data to RDS after every exchange — rather than at the end of a completed session — is not a difficult engineering decision. But it is the one that makes the product usable in the real world. Users who experience data loss once do not give the product a second chance. Users who experience seamless resumption of interrupted conversations trust the product immediately.

### ④ The employer trust problem is as important as the worker access problem.

Early product development focused almost entirely on the worker side — making onboarding work, making matching accurate, making the voice pipeline reliable. The employer side was treated as the simpler half of the marketplace.

It is not simpler. Employers who have been burned by informal contractors showing up with workers who lacked the claimed skills, or by workers who quit after two days, or by middlemen who promised 20 workers and delivered 12, are skeptical of any new hiring platform. The verification layer — GST for employers, Aadhaar for workers, skill assessment through work history documentation — is not optional. It is the foundation of employer trust. Without it, the platform is just another channel for the same unreliable informal market that already exists.

### ⑤ The two-sided marketplace chicken-and-egg problem has only one solution.

You cannot attract employers to a platform with no workers, and you cannot attract workers to a platform with no jobs. There is no clever product solution to this. The only solution is choosing which side to build first and going deep on that side before touching the other.

For JobSathi, the answer is workers first, always. Workers are the harder side to acquire because they have no digital presence and no existing behavior to build on. Acquiring them requires field operations — partnerships with NGOs, community organizations, labor unions, and local governments. It requires trust-building that happens offline before it can be converted to digital engagement. Employers, by contrast, are digitally fluent, actively looking for solutions to a problem they are aware of, and willing to adopt new tools that solve that problem credibly.

Get 1,000 workers fully profiled in one city. Then bring in employers. The supply side is the product. Everything else is distribution.

---

## Conclusion: The Calculation That Changes

There is a calculation that every informal worker in India runs every morning before they decide whether to show up at the labor naka or stay home. It goes roughly like this: is the probability of getting work today, multiplied by the wage I will receive if I get it, minus the time and transport cost of showing up, greater than zero?

For many workers, on many days, that calculation is negative. The uncertainty is too high. The rates are too low. The middlemen are too unreliable. They stay home. A day's income is lost. A project somewhere is understaffed. The economy absorbs the friction and moves on.

JobSathi changes the calculation. The probability of finding work increases because the worker is searchable beyond their immediate physical network. The wage improves because the worker has visibility into market rates and access to multiple employers competing for their skill. The time cost decreases because they do not need to travel to a labor naka and wait for hours. The middleman margin disappears.

This is not a marginal improvement. For a daily wage worker, a 30 percent increase in income certainty and a 20 percent improvement in wages is transformative. It is the difference between being able to save and not being able to. Between being able to afford school fees and not being able to. Between having financial identity and not having one.

The technology to deliver this has existed for years. Amazon Transcribe supports Indian languages. Amazon Bedrock can hold nuanced conversations in Hindi and Tamil and Telugu. AWS Connect can answer a million simultaneous phone calls. Amazon ECS can run a backend that never goes down. The AWS infrastructure to build JobSathi is not experimental — it is production-grade, globally deployed, and available today.

What has not existed until now is someone deciding that these 300 million workers were worth building for.

JobSathi is that decision made into a product.

---

**Built on:** Amazon ECS Fargate · Amazon Bedrock · Amazon Connect · Amazon Transcribe · Amazon Polly · Amazon RDS PostgreSQL · Amazon ElastiCache Redis · Amazon S3 · Amazon API Gateway · Amazon Cognito · Amazon SQS · Amazon SNS · Amazon OpenSearch · Amazon CloudWatch
