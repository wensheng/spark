"""
Fake LLM utilities
"""

FAKE_TEXT = """
To be or not to be—that is the question:
Whether ’tis nobler in the mind to suffer
The slings and arrows of outrageous fortune,
Or to take arms against a sea of troubles
And, by opposing, end them. To die, to sleep—
No more—and by a sleep to say we end
The heartache and the thousand natural shocks
That flesh is heir to—’tis a consummation
Devoutly to be wished. To die, to sleep—
To sleep, perchance to dream. Ay, there’s the rub,
For in that sleep of death what dreams may come,
When we have shuffled off this mortal coil,
Must give us pause. There’s the respect
That makes calamity of so long life.
For who would bear the whips and scorns of time,
Th’ oppressor’s wrong, the proud man’s contumely,
The pangs of despised love, the law’s delay,
The insolence of office, and the spurns
That patient merit of th’ unworthy takes,
When he himself might his quietus make
With a bare bodkin? Who would fardels bear,
To grunt and sweat under a weary life,
But that the dread of something after death,
The undiscovered country from whose bourn
No traveler returns, puzzles the will
And makes us rather bear those ills we have
Than fly to others that we know not of?
Thus conscience does make cowards of us all,
And thus the native hue of resolution
Is sicklied o’er with the pale cast of thought,
And enterprises of great pitch and moment
With this regard their currents turn awry
And lose the name of action.
"""


def fake_stream_llm(_, predefined_text=FAKE_TEXT):
    """Return a list of simple objects that mimic OpenAI streaming responses."""
    # Split text into small chunks
    chunk_size = 10
    chunks = []

    # Create the chunks using a simple class outside the nested structure
    class SimpleObject:
        """Simple object for the fake stream LLM."""

        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    # Build the chunks
    for i in range(0, len(predefined_text), chunk_size):
        text_chunk = predefined_text[i : i + chunk_size]

        # Create the nested structure using simple objects
        delta = SimpleObject(content=text_chunk)
        choice = SimpleObject(delta=delta)
        chunk = SimpleObject(choices=[choice])

        chunks.append(chunk)

    return chunks
