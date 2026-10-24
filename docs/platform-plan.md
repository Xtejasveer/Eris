# Eris platform plan: courses, lessons on every student's device, prerequisite classes, attendance

Status: planning (nothing built yet). Add points anywhere; the open questions are at the end.

## Goal

Turn Eris from a substitute for one class into a course platform, like Google Classroom: a teacher teaches several
subjects to different years, and each subject is organised into chapters and topics. The AI lecture we already have
becomes one kind of lesson inside a topic.

Example teacher:
- DSA, 4th year
- History, 1st year
- Statistics, 2nd year

## 1. Structure

```
Teacher
 └─ Course: subject + year          e.g. DSA · 4th year
     └─ Chapter                     e.g. Dynamic programming
         └─ Topic                   e.g. Coin change
             └─ Posts               notes and study material · absent lecture · prerequisite class
```

- Home page for both roles: a grid of course cards, like Google Classroom.
  - Teacher: the courses they teach.
  - Student: the courses they are enrolled in.
- Today's "lecture" becomes a lesson inside a topic. Studio, generation and approval stay as they are, one level deeper.
- Material can live at any level: a textbook at course level, slides at chapter level, notes at topic level. A
  lesson uses its own topic's material plus everything above it.

## 2. Joining a course and sharing

- The teacher creates a course and gets a class code (and an invite link). Students join with it.
- The teacher shares into the course, like Google Classroom posts:
  - notes and other study material (files students can open and download),
  - an approved absent lecture (the AI substitute lecture),
  - an approved prerequisite class,
  - optionally a due date ("watch before Monday's class").
- Students see a course stream: what was shared, what is due, what they have finished.

## 3. Lessons run on each student's own device (no projected class)

We do not show the lecture to the whole class on one screen. Each student opens the shared lesson and Eris teaches
it on their own device: the board, the voice, the tutor and live doubts, just for them.

- Every student gets the same approved, locked script: consistent teaching, no recordings.
- Doubts stay live: each student can interrupt, ask anything and use the question breaks; the doubt agent answers
  them personally. Their questions no longer compete with 40 others.
- Each student has their own pace: pause, resume, rewatch a section.
- Cheap to scale: narration audio for a locked script is generated once and cached, so every student plays the same
  clips; the only per-student cost is the AI answering their doubts.
- Teacher control: unlock, edit and re-approve; the new version is what students get from then on.

Watch out for:
- Versioning: lock a specific script version and record which version each student saw.
- Doubt answers are not locked: they are generated live and can vary, so log them for the teacher.
- Each student needs their own session: class clock, question breaks, progress, doubt thread.
- Cost control: a per-student or per-lesson limit on doubt questions, so one student can't run up a large bill.
- Devices: it must work well on phones and cheap laptops (the classroom page is already light; the 3D tutor is now
  a pair of small videos).

## 4. Attendance from watching

Because each student watches on their own device, Eris knows how much of each lesson they actually took. A student
who watched 100% of a lesson (every spoken line played) is marked present for it, so the teacher knows who has done
the absent lecture and the prerequisite class instead of trusting what students say.

How "watched" should be measured (so it can't be gamed by leaving a tab open):
- Count spoken lines (segments) actually played, not minutes the page was open.
- Count only while the tab is visible and the lesson is playing (not paused, not hidden in the background).
- Skipping ahead does not count the skipped part.
- Optional engagement checks: the question breaks already ask "any doubts?"; an occasional "still with me?" tap,
  or a 2-3 question check at the end, can confirm the student was there.

What the teacher sees, per lesson:
- who is present (watched all of it), who started but didn't finish (and how far they got), who never opened it,
- how far each student got and when,
- the doubts each student asked (and which were passed to the teacher),
- the check results, if the lesson has a check.

Attendance needs 100% of the lesson. A student can stop and come back as often as they like (progress is kept, and
lines already played stay counted); rewinding is fine. Question breaks and doubt answers are not counted, only the
lesson's own spoken lines.

## 5. Prerequisite classes

Problem: when a teacher tells students to study the prerequisites, ten students learn them ten different ways
(YouTube, ChatGPT): some too briefly, some in far more depth than the coursework needs. The teacher cannot see what
they actually learnt.

Solution: the teacher runs the prerequisite class on Eris, so learning is centralised and visible.

- The teacher marks what students need before a topic (e.g. "recursion basics" before "dynamic programming").
- The teacher creates a prerequisite lesson, reviews the script and approves it, like a normal lecture, and shares it
  to the course.
- The prompt knows it is a prerequisite for a specific coursework topic: it covers only what that topic needs, at the
  right depth, and ends by linking forward ("next class you'll use this for…").
- Students take it on their own devices, with live doubts; attendance (section 4) shows the teacher who did it.

Decision needed: where prerequisite content comes from when the teacher has no material for it. Options: the teacher
uploads a short reference, or approves a generated outline first. Either way the approved script is the safeguard,
because everything else in Eris is grounded in the teacher's material.

## 6. Making it more useful (v2)

Everything in this section is **v2**: none of it is part of v1. Each item says which problem it solves.

### For students

- **Readiness check before a topic.** A short check on the prerequisites; students who pass can skip the
  prerequisite class, the rest are sent to it. Solves: everyone sitting through prerequisites they already know.
- **Quick check at the end of a lesson.** Optional per lesson: 2-3 questions made from the locked script and
  approved by the teacher. Solves: the teacher not knowing whether watching turned into understanding; also confirms
  attendance.
- **Course study helper.** Ask doubts outside a lesson, answered only from that course's material and approved
  lessons, and visible to the teacher. Solves: students going back to YouTube or ChatGPT between classes.
- **Missed-lesson catch-up.** A student who joins late or misses a due date sees exactly which lessons they still
  owe, in order. Solves: students falling behind without anyone noticing.
- **Transcript and notes after the lesson.** The board notes and the full transcript, downloadable. Solves:
  revision without re-watching.
- **Low-data mode.** Voice, captions and board only (no tutor video, smaller downloads), for slow connections
  and cheap phones. Solves: students who can't stream reliably.
- **Revision reminders.** A short recap or check a few days after a lesson (spaced repetition). Solves:
  forgetting before the exam.
- **Lesson in the student's language.** The teacher approves a translated version of a script (Eris already
  generates in 10 languages); students pick theirs. Solves: students who learn better in their first language.

### For teachers

- **Where students got stuck.** A per-lesson view of which sections drew the most doubts, and which students
  dropped off where. Solves: the teacher not knowing what to revisit in the next live class.
- **Doubt summary.** The doubts of the whole class grouped into a few common confusions, with how many students
  asked each, e.g. "12 students: why the base case returns 1". Solves: reading 200 doubts one by one.
- **Doubts passed to the teacher, as an inbox.** Marks, deadlines and anything the agent hands over arrive in one
  place; the teacher answers once, and can publish the answer as a course FAQ the agent uses from then on. Solves:
  questions lost or answered ten times.
- **Students who need attention.** A short list: not started, started but not finished, low check scores, many doubts.
  Solves: struggling students staying invisible until the exam.
- **Students' feedback on a lesson.** "This part was confusing" on any section; the teacher sees it and can
  regenerate just that section. Solves: a weak part of a script staying weak.
- **Reuse.** Copy a course to next year's batch with its chapters, topics and approved lessons. Solves:
  rebuilding the same course every year.
- **Co-teachers and TAs.** More than one teacher on a course, with roles. Solves: shared courses and lab
  sections.
- **Export.** Attendance and check results as a CSV for the institution's records. Solves: copying attendance by
  hand.
- **Scheduling.** Release a lesson at a set time; mark late completions separately from on-time ones. Solves:
  lessons going out too early or too late.

### Self-paced playback: a scrubber, rewind and speed (v2)

Each student watches on their own, so they need the controls of a video player: a scrubber (progress bar) to jump
around, rewind when they missed something, and a speed control. A lesson is not a video, though: it is a script played
live (voice, board writing, slides, code, graphs), so every jump must also put the board in the right state.

How it works:
- **The scrubber.** A bar under the board shows the whole lesson: its sections as labelled marks, the question breaks
  as small ticks, and the part the student has watched. Hovering shows the section and the sentence at that point.
  The student drags it and lets go; nothing is rebuilt while dragging, only on release, so dragging stays smooth.
- **What happens on a jump.** The player stops the voice, rebuilds the board instantly as it was at that point (every
  note written, the right slide, the code and its output, diagrams and graphs at their state), then plays on from the
  start of that sentence with voice and animation. The pieces already exist: today a section jump and "resume" already
  rebuild the board silently from the script (the player's restore step); the scrubber makes that work at any sentence.
- **Rewind when you missed something.**
  - "Back one sentence" and "back 10 seconds" buttons (and the left arrow key): the most common case.
  - Tap any sentence in the transcript, or any section in the outline, to go there.
  - Tap a line on the board ("what did she say about this?") to replay the sentence that wrote it.
- **Speed.** 0.75x to 1.5x. The voice plays faster (pitch kept) and everything the stager drives speeds up with it:
  handwriting, code typing, slide changes, diagram blocks, slider moves and pauses all use the same clock, so the board
  stays in step with the voice. (The player already scales its timing by a rate; the voice already supports a playback
  rate.)
- **Question breaks.** Rewinding past a break the student already went through does not ask again; a break they skipped
  by jumping forward asks when they reach it. Doubt answers they already got stay in their doubt history and are not
  replayed onto the board.

Keeping it fast (the "stager performance" on a jump):
- **Board snapshots at each section.** Rebuilding from the start of a long lesson replays every action; instead the
  player keeps a snapshot of the board at the start of each section and rebuilds only from the nearest one. A jump
  then costs one section's worth of actions, done without animation, which takes well under a second.
- **No real work during a rebuild.** Program output comes from the approved script (code is never re-run), diagrams
  are drawn in one step, only the last slide is shown, and graphs are moved straight to their final value. Heavy
  pieces (interactive graphs) are created only when they come into view.
- **Audio is ready.** The voice clips of an approved lesson are cached; the player fetches the clip at the jump target
  first, then the next few, so the voice starts at once.

How it works with attendance (100%):
- Rewinding and replaying are free; lines already played stay counted.
- Jumping forward is allowed, but the skipped lines stay unwatched (shown as a gap on the scrubber, "3 parts still to
  watch"), and the student is not present until every line is played. The teacher can choose to block jumping forward
  past unwatched parts for a lesson.
- Lines played at any speed up to 1.5x count as watched.

## 7. Making it robust (v2)

Everything in this section is **v2**: none of it is part of v1. Until these land (the code sandbox, limits, backups
and privacy above all), v1 should run only as a pilot with trusted teachers and students, not as a public site.

- **Progress that can't be faked.** The browser reports which spoken lines were played; the server checks the
  report against the script (real line ids, in order, at a believable pace) and computes attendance itself. Solves:
  someone calling the API to mark themselves present.
- **Progress that survives bad networks.** Progress is saved locally and sent in small batches with retries;
  re-sending is harmless. Resume on any device from the last line. Solves: lost progress on a dropped connection.
- **Generation as a proper job queue.** Script generation runs in a background worker with a queue, not a thread
  inside the web server, so a restart or deploy doesn't kill it, and many teachers can generate at once. Solves: today's
  "the job died when the server restarted".
- **Approved versions never change.** An approved script version is read-only; edits make a new version that
  needs approval. Attendance and doubts point to the version the student saw. Solves: disputes about what was taught.
- **Audio served as static files from a CDN.** Generated once per approved version. Solves: the server slowing
  down when a whole class opens a lesson at once.
- **Limits and budgets.** Doubts per student per lesson, generations per teacher per day, and a monthly AI budget
  per course with an alert. Solves: one user running up a large bill.
- **Safe answers.** The doubt agent stays on the course topic, refuses to do graded assignments for students,
  keeps answers age-appropriate, and passes anything about marks, exams or personal issues to the teacher. Every
  answer is logged. Solves: the AI saying something the teacher would not.
- **Code runs in a sandbox.** Lesson programs and doubt-answer programs run in an isolated, time- and
  memory-limited sandbox, never on the main server. Solves: today's server running code it is sent.
- **Backups and monitoring.** Nightly database and file backups, error tracking, and alerts when generation or
  the voice service fails. Solves: losing a semester of courses, or finding out from students that it's broken.
- **Privacy.** Collect only what the course needs; students can see their own data; data is deleted when a course
  is archived (with an export first). If any students are under 18, India's DPDP Act needs verifiable parental consent
  and limits tracking of children, so the attendance and progress tracking must be reviewed for that case. Solves:
  legal and trust problems with institutions.
- **Works when the AI services are down.** Approved lessons still play from cached audio; if the doubt service
  is down, students can still type a doubt and it goes to the teacher's inbox. Solves: a provider outage stopping
  classes.

## 8. What this needs underneath

v1:
- Accounts and roles: teacher and student, sign-in, course enrolment by class code. Today there is no login at all.
- A real database for courses, chapters, topics, posts, lessons and script versions, enrolments, per-student
  sessions and progress, attendance and doubt logs, replacing today's folders and JSON files.
- File storage for the shared notes and material, and the lessons' audio.
- Hosting with a persistent database and storage (see the deployment discussion: not Vercel alone).

v2 (from section 7):
- A background worker and job queue for generation, a code sandbox, a CDN for audio, backups and monitoring.
- More roles: TAs and an institution admin.

## 9. Suggested order

v1 (sections 1-5):
1. Foundations: accounts and roles, a real database.
2. Courses with class codes, the course → chapter → topic structure (today's lectures moved into it), and home pages
   (course grids) for teachers and students.
3. Sharing: posts with notes and material, and approved lectures shared to a course, with due dates.
4. Lessons on each student's device: locked script versions, a session per student, doubt logs.
5. Attendance: tracking which spoken lines each student played, present at 100%, the teacher's attendance view.
6. Prerequisite lessons.

v2 (sections 6-7):
7. Robustness first: the code sandbox, limits and budgets, safe answers, backups and monitoring, privacy, server-checked
   and network-proof progress, the job queue, read-only approved versions.
8. Teacher tools: the doubt inbox and FAQ, where students got stuck, export, the doubt summary, students who need
   attention, lesson feedback, scheduling.
9. Student tools: self-paced playback (scrubber, rewind, speed, board snapshots), quick checks, catch-up list,
   transcript and notes, readiness check, study helper, low-data mode.
10. Later in v2: revision reminders, translated lessons, reuse, co-teachers, CDN for audio, working when AI services
    are down.

## 10. Open questions

- Sign-in: a real one (email or Google sign-in), or a demo login to start?
- Course size: roughly how many students per course? This decides how heavy progress tracking needs to be.
- Prerequisite sources: may Eris teach prerequisites from general knowledge, or always from material the teacher
  provides?
- Attendance: should a short end-of-lesson check also be required on top of watching 100%?
- Doubt limits: how many questions per student per lesson before a limit applies?
- Students' ages: are any under 18 (school use)? This changes the privacy and consent requirements.
- Institutions: will colleges want their own admin view and integration with their systems (e.g. Google Classroom or
  Moodle), or is it teacher-by-teacher at first?

## 11. More points

<!-- Add new ideas here. -->
