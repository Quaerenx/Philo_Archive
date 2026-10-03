# Corpus representative images

Prepared on 2026-10-01 for the dashboard row layout. The four files are 1254×1254 RGBA PNGs with real transparency. Display uses fixed square boxes and `object-fit: contain`; the original generated files are preserved outside the repository. No remote image URL is required at runtime.

| Asset | Source and preparation |
|---|---|
| `nietzsche.png` | [Gustav Adolf Schultze's 1882 portrait](https://commons.wikimedia.org/wiki/File:Nietzsche1882.jpg). Background removed and framing prepared with built-in imagegen while retaining the historical likeness and pose. Commons marks the original as public domain. |
| `kierkegaard.png` | [Luplau Janssen's Kierkegaard portrait](https://commons.wikimedia.org/wiki/File:Kierkegaard_portrait.jpg). The background, desk and surrounding objects were removed with built-in imagegen; the painted likeness is retained. Commons marks the original artwork and reproduction as public domain. |
| `wittgenstein.png` | [Moritz Nähr's Wittgenstein photograph](https://commons.wikimedia.org/wiki/File:Ludwig_Wittgenstein.jpg). Background removal and grayscale framing with built-in imagegen. Commons marks the original as public domain. |
| `bible.png` | A new representative open-book illustration generated with built-in imagegen. It is not presented as a photograph of a particular manuscript or edition. |

[Full prompt set](prompts.json) records the background-extraction and book-image instructions. The edited portraits are derivatives prepared with imagegen, not claims of pixel-identical archival scans.

Biographical dates use the user's Nietzsche reference, checked against [Stanford's biography](https://plato.stanford.edu/archives/fall2005/entries/nietzsche/); Kierkegaard dates are confirmed by the [University of Copenhagen](https://teol.ku.dk/skc/english/about-soeren-kierkegaard/the-global-dane-soeren-kierkegaard-teologian-philosopher-author/soeren-kierkegaard/); Wittgenstein dates and Vienna are confirmed by [MacTutor, University of St Andrews](https://mathshistory.st-andrews.ac.uk/Biographies/Wittgenstein/). The Nietzsche regional label follows the supplied reference. Bible rows describe the repository's Hebrew Bible, Greek New Testament, Septuagint and deuterocanonical corpus rather than inventing a single person's lifespan or nationality.
