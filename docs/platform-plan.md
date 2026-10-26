# Eris platform plan: courses, lessons on every student's device, prerequisite classes, attendance

Status: **v1 and v1.1 are built** (sections 1-6) and run as a pilot. Next is **v2** (sections 7-8).
Add points anywhere; the open questions are at the end.

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
  or the practice part after the lesson (section 7), can confirm the student was there.

What the teacher sees, per lesson:
- who is present (watched all of it), who started but didn't finish (and how far they got), who never opened it,
- how far each student got and when,
- the doubts each student asked (and which were passed to the teacher),
- the practice results, if the lesson has a practice part.

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

## 6. v1.1 (built)

What was built, and what was left out:
- **Code sandbox** (`eris/sandbox.py`): every program (lesson code, doubt answers, generation dry runs) runs with no
  network, no access to the project (so not `.env` or the database), writes only in its own folder, CPU, file and
  open-file limits, and no secrets in its environment. On macOS this is the OS sandbox; with
  `docker pull python:3.12-slim` it switches to a locked-down container (`ERIS_SANDBOX`).
- **Safe answers**: rules in the doubt prompt (graded work, personal problems, harmful requests, keeping its role).
- **Playback by checkpoints** (`web/js/checkpoints.js`): students jump only to checkpoints, never to any sentence.
  Checkpoints come from the script's structure, for any lesson: the first safe line of each section, plus extra ones
  in stretches longer than 75 s (at safe lines, preferring new steps on screen), none closer than 20 s. A safe line is
  one where nothing is half-done (no action spoken over, no program output waiting, no graph mid-slide, no diagram
  part-built). Students can go to checkpoints they reached (and the next one if the teacher allows skipping), restart
  the part, or continue where they left off. Jumps run one at a time: the old run stops completely before the board
  is rebuilt, and a voice clip still loading never starts. No code runs during playback (approved output is shown).
  Speed (0.75x-1.5x) changes from the next sentence. Voice clips are made in the background when a version is shared,
  and the server makes at most 3 clips at once. Breaks already taken are not asked again; the transcript is read-only.
  Not built: board snapshots (a rebuild takes about 30 ms) and tapping a line on the board to replay it.
- **Insights** per lesson (doubts, "confusing" flags and drop-offs per section) and **students' "Confusing?" flag**;
  the teacher can rewrite one section from that feedback, which makes a draft to approve as a new version.

The plan as written before building:

The first things to add to the v1 pilot: the playback controls students ask for first, two ways for the teacher to
see where a lesson is weak, and the two safety items that matter most once students use it on their own (answers that
stay safe, and code that never runs on the main server).

### Self-paced playback: a scrubber, rewind and speed

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

### Where the lesson is weak

- **Where students got stuck.** A per-lesson view of which sections drew the most doubts, and which students
  dropped off where. Solves: the teacher not knowing what to revisit in the next live class.
- **Students' feedback on a lesson.** "This part was confusing" on any section; the teacher sees it and can
  regenerate just that section. Solves: a weak part of a script staying weak.

### Safety

- **Safe answers.** The doubt agent stays on the course topic, refuses to do graded assignments for students,
  keeps answers age-appropriate, and passes anything about marks, exams or personal issues to the teacher. Every
  answer is logged. Solves: the AI saying something the teacher would not.
- **Code runs in a sandbox.** Lesson programs and doubt-answer programs run in an isolated, time- and
  memory-limited sandbox, never on the main server. Solves: today's server running code it is sent; in v1 a
  student's doubt can still make the agent run code on the server.

## 7. Making it more useful (v2)

Everything in this section is **v2** (none of it is in v1 or v1.1). Each item says which problem it solves.

### For students

- **Readiness check before a topic.** A short check on the prerequisites; students who pass can skip the
  prerequisite class, the rest are sent to it. Solves: everyone sitting through prerequisites they already know.
- **Point at it and ask.** When a student pauses, they can mark exactly what confused them on the board, and an
  "Ask AI about this" button appears beside the mark. Solves: doubts like "what does this mean?" where typing out the
  line, the formula or the part of a picture is slow or impossible.
  - Slides and notebook: highlight words or a line. Code: highlight one or more lines. Pictures, diagrams and
    graphs: circle or underline with a red pen (the board already has a pen for the teacher's circles).
  - The doubt agent gets what was marked: the exact text or code lines, the diagram block or the graph's current
    state, and for a picture the marked part of the image (sent to the vision model). It answers in the usual way, on
    the board, starting from the marked thing.
  - The mark stays on the board while the answer plays, then clears; the student can type or say the question too.
  - The teacher sees the marks with the doubts in Insights, so "most students circled this part of slide 7" shows up.
  - Watch: image marks cost a vision-model call, so they count toward the doubt limits; marks work only while paused,
    so the lesson never moves under the student's pen.
- **Practice after the lesson.** An optional part after the lesson ends, in the same workspaces the lesson used.
  Made in an extra step from the approved lesson, reviewed and approved in Studio, and locked into the version.
  Solves: students only watching, and the teacher not knowing whether watching turned into understanding.
  - Code: a starter file and a small task; the student edits and runs it in the code panel. Student code runs for
    real, in the sandbox, and is checked against tests the teacher approved.
  - Notebook (any subject): multiple-choice questions, fill in the blank, put things in order (checked by code), and
    short written answers (checked by the AI against a rubric the teacher approved).
  - Graphs: "move the slider until …", checked from the graph's state. Diagrams: put the blocks in order.
  - The doubt agent helps with hints, never the answer (the graded-work rule). Attendance stays "heard every line";
    practice scores are separate and show in Insights with the common wrong answers.
  - Watch: a limit on code runs per student (and the Docker sandbox for real use), the cost of AI-checked answers
    (so code-checked exercises come first), and copying (slightly different numbers per student).
  - Order: multiple-choice and code exercises first, then graph and diagram tasks, then written answers.
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

- **Doubt summary.** The doubts of the whole class grouped into a few common confusions, with how many students
  asked each, e.g. "12 students: why the base case returns 1". Solves: reading 200 doubts one by one.
- **Doubts passed to the teacher, as an inbox.** Marks, deadlines and anything the agent hands over arrive in one
  place; the teacher answers once, and can publish the answer as a course FAQ the agent uses from then on. Solves:
  questions lost or answered ten times.
- **Students who need attention.** A short list: not started, started but not finished, low practice scores, many
  doubts. Solves: struggling students staying invisible until the exam.
- **Reuse.** Copy a course to next year's batch with its chapters, topics and approved lessons. Solves:
  rebuilding the same course every year.
- **Co-teachers and TAs.** More than one teacher on a course, with roles. Solves: shared courses and lab
  sections.
- **Export.** Attendance and practice results as a CSV for the institution's records. Solves: copying attendance by
  hand.
- **Scheduling.** Release a lesson at a set time; mark late completions separately from on-time ones. Solves:
  lessons going out too early or too late.

## 8. Making it robust (v2)

Everything in this section is **v2**. Until these land (limits, backups and privacy above all, after v1.1's safe
answers and code sandbox), Eris should run only as a pilot with trusted teachers and students, not as a public site.

- **Progress that can't be faked.** The browser reports which spoken lines were played; the server checks the
  report against the script (real line ids, in order, at a believable pace) and computes attendance itself. Solves:
  someone calling the API to mark themselves present.
- **Progress that survives bad networks.** Progress is saved locally and sent in small batches with retries;
  re-sending is harmless. Resume on any device from the last line. Solves: lost progress on a dropped connection.
- **Generation as a proper job queue.** Script generation runs in a background worker with a queue, not a thread
  inside the web server, so a restart or deploy doesn't kill it, and many teachers can generate at once. Solves: today's
  "the job died when the server restarted".
- **Approved versions never change.** *Built in v1:* every approved script is kept as a read-only, numbered
  version; approving a new script gives it to the class, and the teacher can read any version and roll back. Still
  to do: attendance per version (see "Found while building v1"). Solves: disputes about what was taught.
- **Audio served as static files from a CDN.** Generated once per approved version. Solves: the server slowing
  down when a whole class opens a lesson at once.
- **Limits and budgets.** Doubts per student per lesson, generations per teacher per day, and a monthly AI budget
  per course with an alert. Solves: one user running up a large bill.
- **Backups and monitoring.** Nightly database and file backups, error tracking, and alerts when generation or
  the voice service fails. Solves: losing a semester of courses, or finding out from students that it's broken.
- **Privacy.** Collect only what the course needs; students can see their own data; data is deleted when a course
  is archived (with an export first). If any students are under 18, India's DPDP Act needs verifiable parental consent
  and limits tracking of children, so the attendance and progress tracking must be reviewed for that case. Solves:
  legal and trust problems with institutions.
- **Works when the AI services are down.** Approved lessons still play from cached audio; if the doubt service
  is down, students can still type a doubt and it goes to the teacher's inbox. Solves: a provider outage stopping
  classes.

### Found while building v1 (v2)

- **Doubts for many students at once.** v1 answers one doubt at a time across all students (a lock, because the doubt
  agent's tools read one shared board). Give each answer its own board so many students can ask at once. Solves:
  students waiting on each other's doubts when a whole class watches together.
- **Doubt threads in the database.** The conversation behind each student's doubts lives in server memory and is lost
  on a restart. Solves: a student's follow-up question losing its context after a deploy.
- **Accounts.** Password reset ("forgot password"), email verification, and turning off the demo sign-in buttons
  (`ERIS_DEMO_LOGINS`) for real use. Solves: locked-out users and fake accounts.
- **Course management.** Remove a student, archive a course, reorder chapters and topics, move a lesson to another
  topic. Solves: courses that can only grow, never be tidied.
- **Attendance by version.** Show which script version each student finished; today "present" carries over when a new
  version is given to the class. Solves: not knowing who saw the corrected lesson.
- **Phone layout for the lesson.** The player is built for laptop screens. Solves: students who only have a phone.
- **Notifications.** A new lesson shared, a due date coming up, a new version given to the class. Solves: students
  not knowing there is something to watch.
- **Scale and deployment.** Move from SQLite to Postgres, and a real deployment (HTTPS, a domain, environment
  settings). Solves: the pilot outgrowing one machine.

## 9. What this needs underneath

v1:
- Accounts and roles: teacher and student, sign-in, course enrolment by class code. Today there is no login at all.
- A real database for courses, chapters, topics, posts, lessons and script versions, enrolments, per-student
  sessions and progress, attendance and doubt logs, replacing today's folders and JSON files.
- File storage for the shared notes and material, and the lessons' audio.
- Hosting with a persistent database and storage (see the deployment discussion: not Vercel alone).

v1.1 (section 6):
- A code sandbox (an isolated runner with time and memory limits).

v2 (from section 8):
- A background worker and job queue for generation, a CDN for audio, backups and monitoring, Postgres.
- More roles: TAs and an institution admin.

## 10. Suggested order

v1 (sections 1-5), **built**:
1. Foundations: accounts and roles, a real database.
2. Courses with class codes, the course → chapter → topic structure (today's lectures moved into it), and home pages
   (course grids) for teachers and students.
3. Sharing: posts with notes and material, and approved lectures shared to a course, with due dates.
4. Lessons on each student's device: locked script versions, a session per student, doubt logs.
5. Attendance: tracking which spoken lines each student played, present at 100%, the teacher's attendance view.
6. Prerequisite lessons.

v1.1 (section 6), **built**:
7. Safety first: the code sandbox, then safe answers.
8. Self-paced playback: scrubber, rewind, speed, board snapshots.
9. Where students got stuck, and students' feedback on a lesson (with regenerating one section).

v2 (sections 7-8):
10. Robustness: limits and budgets, backups and monitoring, privacy, server-checked and network-proof progress, the
    job queue, doubts for many students at once, doubt threads in the database, accounts, attendance by version.
11. Teacher tools: the doubt inbox and FAQ, export, the doubt summary, students who need attention, scheduling, course
    management, notifications.
12. Student tools: point at it and ask, practice after the lesson, catch-up list, transcript and notes, readiness
    check, study helper, low-data mode, phone layout.
13. Later in v2: revision reminders, translated lessons, reuse, co-teachers, CDN for audio, working when AI services
    are down, Postgres and a real deployment.

## 11. Open questions

- Sign-in: v1 uses email and password (plus demo accounts for the pilot). Add Google sign-in later?
- Course size: roughly how many students per course? This decides how heavy progress tracking needs to be.
- Prerequisite sources: may Eris teach prerequisites from general knowledge, or always from material the teacher
  provides?
- Attendance: should finishing the practice part also be required on top of hearing 100%?
- Doubt limits: how many questions per student per lesson before a limit applies?
- Students' ages: are any under 18 (school use)? This changes the privacy and consent requirements.
- Institutions: will colleges want their own admin view and integration with their systems (e.g. Google Classroom or
  Moodle), or is it teacher-by-teacher at first?

## 12. More points

<!-- Add new ideas here. -->
