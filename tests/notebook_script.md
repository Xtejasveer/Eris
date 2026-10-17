[SECTION title="Opening"]
Good morning, everyone. Prof. Sharma is at a faculty workshop today, so I am your substitute.
Today we learn while loops: how to repeat code until something happens.

[SECTION title="while loop syntax"]
[SLIDE n=3]
[NOTE_TITLE text="while loop"]
[NOTE]
Repeats AS LONG AS the condition is True
Shape:  while condition:
            body
Condition is checked BEFORE every round
[/NOTE]
Look at the notebook. A while loop keeps going as long as its condition is true.
[NOTE_HIGHLIGHT text="BEFORE every round"]
Python checks the condition before every round, even the very first one.
[NOTE]
Example: count = 1, stop after 3
count = 1 -> 2 -> 3 -> 4 (4 <= 3 is False, stop)
Prints: 1, 2, 3
[/NOTE]
Let's trace it together. Count starts at one, we print, add one, and check again. Clear so far?

[WRITE_CODE file="count.py"]
count = 1
while count <= 3:
    print(count)
    count = count + 1
[/WRITE_CODE]

[HIGHLIGHT file="count.py" text="while count <= 3:"]
This line is the condition from our notebook.
[HIGHLIGHT file="count.py" text="count = count + 1"]
This line is the update. Without it, the loop would never stop.

[RUN cmd="python count.py"]
[READ_OUTPUT]
One, two, three: exactly the numbers we wrote in the notebook.
[NOTE_HIGHLIGHT text="Prints: 1, 2, 3"]

[DOUBT_CHECK]
