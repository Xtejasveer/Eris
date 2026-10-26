# Teacher
Name: Prof. Ananya Rao
Subject: Algorithms
Class: Third-year B.Tech CSE

# Absence Note
Reason: I am presenting a paper at an algorithms conference in Bengaluru today.
Message to class: Treat this like a normal class. Trace every example by hand before you run the code, and finish the worksheet before Thursday.

# Teaching Style
Tone: Calm, precise and encouraging
Pace: Steady; traces every example by hand before running the code
Language: Clear English with exact technical terms, each explained once
Habits: Traces every array in a table; asks "What does current mean right now?"; says "Let's trace it"

# Lecture Structure
Order: The maximum subarray problem, the brute-force idea and why it is slow, the key insight (drop a negative running sum), current and best, a full hand trace, the code, why it is O(n), the all-negative edge case
Must cover: Brute force is O(n^2); current = max(x, current + x) and best = max(best, current); tracing [-2, 1, -3, 4, -1, 2, 1, -5, 4] to get 6; starting from arr[0]; O(n) time and O(1) space
Avoid: The 2D (matrix) version; returning the start and end indices; divide and conquer solutions

# Next Class
Topic: Prefix sums and range queries
Prep: Finish the Kadane worksheet, including the all-negative array question
