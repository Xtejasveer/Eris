"""Builds the four new demo lessons' material in templates/demo/<id>/: slides, notes and persona."""
from pathlib import Path

from docx import Document
from docx.shared import Pt as DPt
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Inches, Pt

ROOT = Path("templates/demo")
INK, MUTED, BAND = RGBColor(0x1C, 0x25, 0x33), RGBColor(0x5B, 0x65, 0x77), RGBColor(0xEA, 0xF2, 0xFB)


class Deck:
    def __init__(self, accent):
        self.p = Presentation()
        self.p.slide_width, self.p.slide_height = Inches(10), Inches(5.625)
        self.accent = RGBColor.from_string(accent)

    def _slide(self, title, dark=False):
        s = self.p.slides.add_slide(self.p.slide_layouts[6])
        bg = s.background.fill
        bg.solid()
        bg.fore_color.rgb = INK if dark else RGBColor(0xFF, 0xFF, 0xFF)
        if not dark:
            bar = s.shapes.add_shape(1, 0, 0, Inches(0.18), self.p.slide_height)
            bar.fill.solid(); bar.fill.fore_color.rgb = self.accent; bar.line.fill.background()
        tb = s.shapes.add_textbox(Inches(0.55), Inches(0.35 if not dark else 1.9), Inches(8.9), Inches(0.9))
        tf = tb.text_frame; tf.word_wrap = True
        r = tf.paragraphs[0].add_run(); r.text = title
        r.font.size, r.font.bold = Pt(30 if not dark else 38), True
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF) if dark else INK
        return s

    def title(self, title, subtitle):
        s = self._slide(title, dark=True)
        tb = s.shapes.add_textbox(Inches(0.55), Inches(3.0), Inches(8.9), Inches(0.8))
        r = tb.text_frame.paragraphs[0].add_run(); r.text = subtitle
        r.font.size, r.font.color.rgb = Pt(18), RGBColor(0xC7, 0xD3, 0xEA)

    def points(self, title, lines, size=19):
        s = self._slide(title)
        tb = s.shapes.add_textbox(Inches(0.6), Inches(1.35), Inches(8.8), Inches(3.9))
        tf = tb.text_frame; tf.word_wrap = True
        for i, line in enumerate(lines):
            par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            r = par.add_run(); r.text = line
            r.font.size, r.font.color.rgb = Pt(size), INK
            par.space_after = Pt(9)

    def code(self, title, intro, code):
        s = self._slide(title)
        tb = s.shapes.add_textbox(Inches(0.6), Inches(1.25), Inches(8.8), Inches(0.6))
        r = tb.text_frame.paragraphs[0].add_run(); r.text = intro
        r.font.size, r.font.color.rgb = Pt(17), MUTED
        box = s.shapes.add_shape(1, Inches(0.6), Inches(1.95), Inches(8.8), Inches(3.2))
        box.fill.solid(); box.fill.fore_color.rgb = RGBColor(0x13, 0x20, 0x3B); box.line.fill.background()
        tf = box.text_frame; tf.word_wrap = True
        for i, line in enumerate(code.splitlines()):
            par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            r = par.add_run(); r.text = line or " "
            r.font.name, r.font.size, r.font.color.rgb = "Consolas", Pt(17), RGBColor(0xE6, 0xED, 0xF7)

    def chart(self, title, kind, categories, series_name, values, chart_title, note):
        s = self._slide(title)
        data = CategoryChartData()
        data.categories = categories
        data.add_series(series_name, values)
        gf = s.shapes.add_chart(kind, Inches(0.6), Inches(1.25), Inches(6.2), Inches(4.0), data)
        ch = gf.chart
        ch.has_title = True
        ch.chart_title.text_frame.text = chart_title
        ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
        ch.has_legend = False
        plot = ch.plots[0]
        plot.has_data_labels = True
        plot.data_labels.font.size = Pt(11)
        ser = plot.series[0]
        if kind == XL_CHART_TYPE.LINE_MARKERS:
            ser.format.line.color.rgb = self.accent
            ser.smooth = True
        else:
            ser.format.fill.solid(); ser.format.fill.fore_color.rgb = self.accent
        card = s.shapes.add_shape(1, Inches(7.0), Inches(1.45), Inches(2.6), Inches(3.4))
        card.fill.solid(); card.fill.fore_color.rgb = BAND; card.line.fill.background()
        tf = card.text_frame; tf.word_wrap = True
        r = tf.paragraphs[0].add_run(); r.text = note
        r.font.size, r.font.color.rgb = Pt(15), INK

    def picture(self, title, image, alt, lines):
        """A figure from the book on the left (its alt text says what it is), what to notice on the right."""
        from PIL import Image
        s = self._slide(title)
        w, h = Image.open(image).size
        box_w, box_h = 5.4, 4.0
        scale = min(box_w / w, box_h / h)
        pic = s.shapes.add_picture(str(image), Inches(0.6), Inches(1.3), Inches(w * scale), Inches(h * scale))
        pic._element.xpath("./p:nvPicPr/p:cNvPr")[0].set("descr", alt)
        tb = s.shapes.add_textbox(Inches(6.3), Inches(1.4), Inches(3.3), Inches(3.8))
        tf = tb.text_frame; tf.word_wrap = True
        for i, line in enumerate(lines):
            par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            r = par.add_run(); r.text = line
            r.font.size, r.font.color.rgb = Pt(15), INK
            par.space_after = Pt(8)

    def save(self, path):
        self.p.save(path)


IMG = Path(__file__).parent  # the figures cut from the books (book pages 4, 5 and 230)


def notes_docx(path, title, blocks):
    """blocks: ("h", text) heading, ("p", text) paragraph, ("code", text) program."""
    doc = Document()
    doc.add_heading(title, 0)
    for kind, text in blocks:
        if kind == "h":
            doc.add_heading(text, 1)
        elif kind == "code":
            for line in text.splitlines():
                p = doc.add_paragraph(); r = p.add_run(line); r.font.name = "Consolas"; r.font.size = DPt(10)
                p.paragraph_format.space_after = DPt(0)
        else:
            doc.add_paragraph(text)
    doc.save(path)


def persona(path, **f):
    path.write_text(f"""# Teacher
Name: {f['name']}
Subject: {f['subject']}
Class: {f['klass']}

# Absence Note
Reason: {f['reason']}
Message to class: {f['message']}

# Teaching Style
Tone: {f['tone']}
Pace: {f['pace']}
Language: {f['language']}
Habits: {f['habits']}

# Lecture Structure
Order: {f['order']}
Must cover: {f['must']}
Avoid: {f['avoid']}

# Next Class
Topic: {f['next']}
Prep: {f['prep']}
""", encoding="utf-8")


# ---------------------------------------------------------------- history
d = ROOT / "history_french_society"; d.mkdir(parents=True, exist_ok=True)
k = Deck("8C3B2E")
k.title("French Society Before the Revolution", "The Old Regime, its taxes and the struggle to survive")
k.points("France in 1774", [
    "Louis XVI became king at the age of 20.",
    "He found an empty treasury: long wars and a costly court at Versailles.",
    "Helping the American colonies added more than 1 billion livres to a debt of over 2 billion livres.",
    "Lenders now charged 10 per cent interest on loans.",
    "To meet its expenses, the state had to raise taxes."])
k.points("The Society of Estates: Who Was Who", [
    "First estate: the clergy.",
    "Second estate: the nobility.",
    "Third estate: merchants, lawyers and officials, peasants, artisans, labourers and servants.",
    "Peasants were about 90 per cent of the population, but few owned the land they farmed.",
    "Nobles, the Church and rich members of the third estate owned about 60 per cent of the land.",
    "Only the third estate paid taxes to the state."])
k.picture("The Society of Estates: Fig. 2 in Your Book", IMG / "fig2_society_of_estates.png",
          "Fig. 2 from the NCERT book (page 4): a diagram of the society of estates. The 1st estate (clergy) is at the top, "
          "the 2nd estate (nobility) below it, and the 3rd estate at the bottom in three groups: big businessmen, merchants, "
          "court officials and lawyers; peasants and artisans; small peasants, landless labour and servants.",
          ["Fig. 2, NCERT page 4.", "1st estate: clergy.", "2nd estate: nobility.",
           "3rd estate: three groups, from rich businessmen and lawyers down to landless labourers and servants.",
           "Within the third estate, some were rich and others poor."])
k.points("The Society of Estates: Who Paid What", [
    "Tithes: a tax paid to the Church.",
    "Taille: a direct tax paid to the state.",
    "Indirect taxes: on everyday things like salt and tobacco.",
    "Feudal dues and services: owed to the lord, such as work in his house and fields.",
    "The clergy and nobles were exempt from taxes to the state, by birth."])
k.picture("The Society of Estates: The Spider and the Fly", IMG / "fig3_spider_and_fly.png",
          "Fig. 3 from the NCERT book (page 5), The Spider and the Fly, an anonymous etching: a well-dressed nobleman sits "
          "at ease while a poor peasant brings him a bag of money and a basket of produce; a spider's web with a fly hangs "
          "in the window above.",
          ["Fig. 3, NCERT page 5: an anonymous etching.", "The nobleman sits; the peasant brings grain, fruit and money.",
           "'The nobleman is the spider, the peasant the fly.'",
           "Why did the artist draw the noble as a spider and the peasant as a fly?"])
k.points("The Struggle to Survive", [
    "The population of France grew from about 23 million in 1715 to 28 million in 1789.",
    "Grain production could not keep pace with the demand for food.",
    "The price of bread, the staple food, rose rapidly.",
    "Wages did not keep pace with prices, so the gap between rich and poor widened.",
    "A drought or hail that cut the harvest made things worse."])
k.points("How a Subsistence Crisis Happens", [
    "1. Bad harvest",
    "2. Scarcity of grain",
    "3. Rising food prices",
    "4. The poorest can no longer buy bread",
    "5. Weaker bodies and disease epidemics",
    "6. More deaths and food riots"])
k.points("Remember", [
    "Three estates, but only the third estate paid taxes to the state.",
    "Peasants paid tithes, taille, indirect taxes and feudal dues.",
    "More people, too little grain and low wages led to subsistence crises.",
    "Anger at unfair taxes and hunger set the stage for 1789."])
k.save(d / "french_society_old_regime.pptx")
persona(d / "persona.md", name="Ms. Anjali Verma", subject="History", klass="Class 9-A",
        reason="I am attending a history teachers' workshop today.",
        message="Keep your NCERT History book open at pages 4 and 5. Listen for who paid the taxes and why that made people angry.",
        tone="Calm storyteller; makes the past feel real with everyday comparisons",
        pace="Moderate; pauses after each cause to ask what it led to",
        language="Simple, clear English; explains each new word (estate, tithe, taille, subsistence) once in everyday words",
        habits="Starts with a question about fairness; asks the class to imagine being a peasant; links every cause to its effect",
        order="France's empty treasury in 1774, the three estates with Fig. 2 from the book, who paid which taxes with Fig. 3 (The Spider and the Fly), the struggle to survive, how a subsistence crisis happens",
        must="Fig. 2 from the book (the society of estates) and what it shows; Fig. 3 from the book (The Spider and the Fly) and why the noble is the spider and the peasant the fly; the three estates and that only the third estate paid taxes to the state; tithes, taille and indirect taxes; peasants were about 90 per cent of the population; population grew from 23 million to 28 million; the subsistence crisis as a chain of causes",
        avoid="The storming of the Bastille and later events of the revolution; the middle class and the ideas of the philosophers (next class)",
        next="A growing middle class and the ideas of Locke, Rousseau and Montesquieu", prep="Read pages 6 and 7 of the NCERT book")

# ---------------------------------------------------------------- maths
d = ROOT / "maths_quadratic_factorisation"; d.mkdir(parents=True, exist_ok=True)
k = Deck("1F6FB2")
k.title("Quadratic Equations by Factorisation", "Finding the roots by splitting the middle term")
k.points("What Is a Root?", [
    "A quadratic equation: ax² + bx + c = 0, where a ≠ 0.",
    "A number α is a root if aα² + bα + c = 0.",
    "Example: x = 1 is a root of 2x² – 3x + 1 = 0, because 2 – 3 + 1 = 0.",
    "A quadratic equation has at most two roots."])
k.points("Splitting the Middle Term", [
    "1. Write the equation as ax² + bx + c = 0",
    "2. Find two numbers whose product is a × c and whose sum is b",
    "3. Split the middle term bx using those two numbers",
    "4. Group the terms and take out the common factors",
    "5. Write it as a product of two linear factors",
    "6. Set each factor to zero and solve"])
k.chart("Roots on the Graph", XL_CHART_TYPE.LINE_MARKERS, ["0", "0.5", "1", "1.5", "2", "2.5", "3"], "y",
        (3, 1, 0, 0, 1, 3, 6), "y = 2x² – 5x + 3",
        "The graph meets the x-axis where y = 0: at x = 1 and x = 1.5. These are the roots of 2x² – 5x + 3 = 0.")
k.points("Example 3 (NCERT page 42)", [
    "Find the roots of 2x² – 5x + 3 = 0 by factorisation.",
    "Here a × c = 2 × 3 = 6 and b = –5.",
    "Which two numbers multiply to 6 and add to –5?"])
k.points("Remember", [
    "Product of the two numbers = a × c; their sum = b.",
    "Each linear factor set to zero gives one root.",
    "Check every root in the original equation.",
    "The roots are where the graph meets the x-axis."])
k.save(d / "quadratic_factorisation.pptx")
persona(d / "persona.md", name="Mr. Arjun Iyer", subject="Mathematics", klass="Class 10-B",
        reason="I am at a mathematics olympiad training session today.",
        message="Keep your NCERT book open at page 42. Try Example 3 yourself before I solve it, then check your roots.",
        tone="Encouraging and precise; celebrates every correct step",
        pace="Slow and steady; writes every step of the working before moving on",
        language="Simple, clear English; explains each term (root, factor, middle term) once in everyday words",
        habits="Asks the class to find the two numbers before revealing them; always checks the roots by putting them back into the equation",
        order="What a root is, the steps of splitting the middle term, the roots on the graph, NCERT Example 3 solved and checked",
        must="A root makes ax² + bx + c equal to zero; the steps of splitting the middle term; NCERT Example 3 (roots 1 and 3/2); the roots are where the graph meets the x-axis",
        avoid="The quadratic formula; the nature of roots and the discriminant; forming quadratic equations from word problems",
        next="More factorisation practice and the nature of roots", prep="Solve NCERT Example 4 on page 43 yourself, then check your roots")

# ---------------------------------------------------------------- chemistry
d = ROOT / "chemistry_carbonyl_properties"; d.mkdir(parents=True, exist_ok=True)
k = Deck("2E7D32")
k.title("Physical Properties of Aldehydes and Ketones", "States, boiling points, solubility and odour")
k.picture("Meet Aldehydes and Ketones: Their Structures", IMG / "carbonyl_structures.png",
          "Structures from the NCERT book (page 230): 3-Oxopentanal, 2,4-Dimethylpentan-3-one, 4-Nitrobenzaldehyde and "
          "Propane-1,2,3-tricarbaldehyde, with each carbonyl group (C=O, and CHO in aldehydes) shown in pink.",
          ["Structures from NCERT page 230.", "Every one has a carbonyl group, C=O (in pink).",
           "Aldehydes: C=O at the end of the chain, as -CHO (3-Oxopentanal, 4-Nitrobenzaldehyde).",
           "Ketones: C=O inside the chain (2,4-Dimethylpentan-3-one)."])
k.points("Meet Aldehydes and Ketones: States at Room Temperature", [
    "Methanal (HCHO) is a gas.",
    "Ethanal (CH3CHO) is a volatile liquid.",
    "Other aldehydes and ketones are liquids or solids."])
k.points("Boiling Points: Why They Sit in the Middle", [
    "Higher than hydrocarbons and ethers of similar molecular mass: the polar C=O group gives dipole-dipole attraction.",
    "Lower than alcohols of similar molecular mass: aldehydes and ketones cannot hydrogen bond with each other.",
    "Compare molecules of similar molecular mass, so size does not decide the order."])
k.chart("Boiling Points: The Numbers", XL_CHART_TYPE.COLUMN_CLUSTERED,
        ["n-Butane", "Methoxyethane", "Propanal", "Acetone", "Propan-1-ol"], "b.p. (K)", (273, 281, 322, 329, 370),
        "Boiling points (K), molecular mass 58-60",
        "Hydrocarbon and ether lowest, aldehyde and ketone in the middle, alcohol highest.")
k.points("Solubility and Odour", [
    "Methanal, ethanal and propanone mix with water in all proportions: they form hydrogen bonds with water.",
    "Solubility in water falls quickly as the alkyl chain gets longer.",
    "All are fairly soluble in benzene, ether, methanol and chloroform.",
    "Lower aldehydes smell sharp and pungent; bigger molecules smell more fragrant, so many are used in perfumes and flavours."])
k.points("Ranking Boiling Points (NCERT Example 8.2)", [
    "1. Check that the molecular masses are similar",
    "2. Find the molecules that hydrogen bond with each other: they boil highest",
    "3. Compare polarity: more polar means stronger dipole-dipole attraction",
    "4. Molecules with only van der Waals forces boil lowest",
    "5. Write the order from lowest to highest"])
k.points("Remember", [
    "Hydrocarbons and ethers < aldehydes and ketones < alcohols (similar mass).",
    "Dipole-dipole attraction raises the boiling point; hydrogen bonding raises it most.",
    "Small aldehydes and ketones dissolve in water; long-chain ones do not."])
k.save(d / "carbonyl_physical_properties.pptx")
persona(d / "persona.md", name="Dr. Farah Khan", subject="Chemistry", klass="Class 12 Science",
        reason="I am at a chemistry teachers' conference today.",
        message="Keep your NCERT Chemistry book open at page 235. Before each answer, try to rank the boiling points yourself.",
        tone="Clear and curious; connects every property to the forces between molecules",
        pace="Moderate; compares molecules one pair at a time",
        language="Simple, clear English; explains each term (dipole, hydrogen bond, van der Waals forces) once in everyday words",
        habits="Asks which force holds the molecules together before giving any boiling point; uses kitchen and perfume examples",
        order="Their structures from the book and the carbonyl group, states at room temperature, boiling points and why they sit between hydrocarbons and alcohols, solubility and odour, ranking boiling points with NCERT Example 8.2",
        must="The structures from the book and where the carbonyl group (C=O) sits in an aldehyde and in a ketone; boiling points of aldehydes and ketones are higher than hydrocarbons and ethers but lower than alcohols of similar mass, with the reason for each; the values 273, 281, 322, 329 and 370 K; small aldehydes and ketones dissolve in water through hydrogen bonds; NCERT Example 8.2 and its order",
        avoid="Chemical reactions such as nucleophilic addition; methods of preparation",
        next="Nucleophilic addition reactions of aldehydes and ketones", prep="Read section 8.4 of the NCERT book")

# ---------------------------------------------------------------- python
d = ROOT / "python_while_loop"; d.mkdir(parents=True, exist_ok=True)
k = Deck("F28C28")
k.title("The while Loop in Python", "Repeating code while a condition is True")
k.code("Writing a while Loop", "A loop repeats code for us; a while loop repeats its indented body while the condition is True.",
       "while condition:\n    # body: runs again and again\n    # while the condition is True\nprint(\"after the loop\")")
k.points("How a while Loop Runs", [
    "1. Check the condition",
    "2. If it is True, run the indented body",
    "3. Update the variable the condition uses",
    "4. Go back and check the condition again",
    "5. When the condition is False, leave the loop"])
k.code("Examples: Countdown", "count starts at 5 and goes down by 1 each time round.",
       "count = 5\nwhile count > 0:\n    print(count)\n    count = count - 1\nprint(\"Lift off!\")")
k.code("Examples: Adding 1 to 10", "total grows as n goes from 1 to 10.",
       "total = 0\nn = 1\nwhile n <= 10:\n    total = total + n\n    n = n + 1\nprint(\"Total:\", total)")
k.points("Watch Out: Infinite Loops", [
    "If the body never changes the variable in the condition, the condition stays True for ever.",
    "Example: forgetting count = count - 1 in the countdown.",
    "Always ask: what makes this condition False in the end?"])
k.save(d / "while_loop.pptx")
notes_docx(d / "while_loop_notes.docx", "The while loop: notes and programs", [
    ("h", "How a while loop runs (steps)"),
    ("p", "1. Check the condition."),
    ("p", "2. If it is True, run the indented body."),
    ("p", "3. Update the variable the condition uses."),
    ("p", "4. Go back to step 1."),
    ("p", "5. When the condition is False, leave the loop and go on."),
    ("h", "Program 1: countdown"),
    ("code", "count = 5\nwhile count > 0:\n    print(count)\n    count = count - 1\nprint(\"Lift off!\")"),
    ("p", "It prints 5, 4, 3, 2, 1 and then Lift off!"),
    ("h", "Program 2: adding 1 to 10"),
    ("code", "total = 0\nn = 1\nwhile n <= 10:\n    total = total + n\n    n = n + 1\nprint(\"Total:\", total)"),
    ("p", "It prints Total: 55."),
    ("h", "Common mistake"),
    ("p", "Forgetting to update the variable in the condition gives an infinite loop: the condition never becomes False."),
])
persona(d / "persona.md", name="Mr. Vikram Nair", subject="Computer Science (Python)", klass="Class 11 Computer Science",
        reason="I am at a coding teachers' training day today.",
        message="Type each program yourself after the class and change the numbers to see what happens.",
        tone="Friendly and hands-on; treats every program like a small experiment",
        pace="Moderate; traces every program line by line before running it",
        language="Simple, clear English; explains each term (condition, body, update, infinite loop) once in everyday words",
        habits="Asks the class to predict the output before running a program; traces the variables in a small table",
        order="Why loops are needed and how to write a while loop, how a while loop runs step by step, the countdown and adding 1 to 10 programs, infinite loops",
        must="The syntax of a while loop with its indented body; the condition is checked before every pass; the update step; the countdown program (5 to 1, then Lift off!); adding 1 to 10 gives 55; why a missing update gives an infinite loop",
        avoid="for loops and range(); break and continue; reading input with input()",
        next="The for loop and range()", prep="Change the countdown program to count down from 10")
print("built")
