[SECTION title="Introduction"]
Good morning, everyone. Prof. Sharma is at a faculty workshop today, so I am filling in.
Prof. Sharma says: please practise every example on your own laptop tonight.
Today we will learn list comprehensions, a short way to build lists.

[SLIDE n=1]
[SECTION title="Basic syntax"]
[NOTE_TITLE text="List comprehension"]
[NOTE while_speaking=true]
Shape: [expression for item in iterable]
Example: runs = 10, 25, 4
Doubled: 20, 50, 8
[/NOTE]
Imagine a batsman's runs in three overs. We want each score doubled.
[NOTE_HIGHLIGHT text="expression"]
The expression is what happens to every item.

[WRITE_CODE file="demo.py"]
runs = [10, 25, 4]
doubled = [r * 2 for r in runs]
print(doubled)
[/WRITE_CODE]

[HIGHLIGHT file="demo.py" text="doubled = [r * 2 for r in runs]"]
Line two reads like English: r times two, for every r in runs.
[r * 2 for r in runs]
That line above is narration, not a marker, because it starts with a lowercase name.

[RUN cmd="python demo.py"]
[READ_OUTPUT]
Every score is doubled. Clear so far?

[SLIDE_HIGHLIGHT n=2 text="expression for item in iterable"]
[WRITE text="[expr for item in iterable]"]
[PAUSE s=3]
[DOUBT_CHECK]

[SECTION title="Recap"]
Today we learned the basic syntax. Next class is dictionary comprehensions, so revise dictionaries.
[DOUBT_CHECK]
