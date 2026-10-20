"""Turn a transcript into structured notes with Gemini (chunk -> notes -> merge)."""
import os
import re
import time
from typing import Callable, Optional

from google import genai
from google.genai import types

from utils import chunk_segments, fmt_time

FALLBACK_MODELS = ["gemini-flash-latest", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
SINGLE_PASS_MAX_CHARS = 24000  # longer transcripts use chunk -> merge

LENGTH = {
    "Short": "Aim for about 800 words in total, still explaining each point in full sentences.",
    "Medium": "Aim for roughly 1500-2500 words in total, with clear explanations.",
    "Detailed": "Be exhaustive: 3000+ words covering every topic, example, number and code snippet.",
}
TONE = {
    "Student": "clear, simple study-notes language",
    "Professional": "concise, professional language",
    "Casual": "relaxed, friendly language",
}
# keyword in section title -> (Lucide icon name, accent colour)
SECTION_META = {
    "tl;dr": ("zap", "#D97706"),
    "key points": ("pin", "#E11D48"),
    "detailed": ("file-text", "#4F46E5"),
    "code": ("code", "#0D9488"),
    "tips": ("lightbulb", "#059669"),
    "shortcuts": ("terminal", "#0284C7"),
    "key terms": ("book-open", "#7C3AED"),
    "revision": ("clipboard-list", "#DB2777"),
    "faq": ("circle-help", "#2563EB"),
    "important": ("target", "#EA580C"),
}

STRUCTURE = """Write the notes in EXACTLY this structure. Use these ## headings, in this order, and no others:
## TL;DR
A 4-6 sentence overview of what the video teaches and why it matters.
## Key Points
8-12 bullets. Each bullet: a **bold label**, then 1-2 sentences explaining it.
## Detailed Notes
Group by topic with ### subheadings. Under each, explain the idea in short paragraphs or bullets: what it is, how it works, why, and a worked example when the video gives one. Keep [mm:ss] timestamps where useful.
## Code Snippets
Every algorithm or piece of code the video explains, as fenced code blocks with a language tag (use Python if the language is unclear). Put a one-line description before each block. If the code is only described aloud, reconstruct it faithfully from the explanation. If the video has no code, write "Not covered in this video."
## Tips & Tricks
Practical advice, common mistakes and edge cases from the video, each with a short explanation.
## Shortcuts & Quick Tricks
Commands, hotkeys, formulas, patterns or hacks. If there are none, write "Not covered in this video."
## Key Terms
- **Term**: a one-sentence definition
## Revision Sheet
A compact cheat sheet of 10-15 one-line bullets: definitions, formulas, complexities, steps to remember.
## FAQs
5-8 questions a learner would ask. Format each as a bold question line, then the answer on the next line, with a blank line between pairs:
**Q1. Question?**
Answer in 1-3 sentences.
## Important Questions
6-10 likely exam or interview questions as a numbered list. After each question add " - Hint: ..." with a short hint.

Formatting rules:
- Use "-" for bullets and indent nested bullets by exactly 2 spaces. Never use tables.
- Write math and complexities as plain text in backticks, like `O(N^2)`. Never use LaTeX or $ signs for math.
- Explain in full sentences; never leave a bare keyword or fragment as a point.
If a section has no relevant content, write "Not covered in this video."."""

def _system(tone: str, language: str) -> str:
    return (
        "You are an expert note-taker. Use ONLY information present in the provided "
        "material and never invent facts. Write in "
        f"{language}, using {TONE.get(tone, TONE['Student'])}. "
        "Use clean Markdown with concise bullets."
    )


def _generate(client, models, prompt, system, retries=3) -> str:
    """Call Gemini; retry on rate limits, move to the next model if one isn't available."""
    last = None
    for model in models:
        for attempt in range(retries):
            try:
                r = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(system_instruction=system, temperature=0.3),
                )
                if r.text:
                    return r.text
                last = RuntimeError("The model returned an empty response.")
                break
            except Exception as e:
                last, msg = e, str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "503" in msg or "UNAVAILABLE" in msg:
                    time.sleep(12 * (attempt + 1))
                    continue
                if "404" in msg or "NOT_FOUND" in msg:
                    break  # try next model
                raise
    raise RuntimeError(f"Gemini request failed: {last}")


def generate_notes(
    api_key: str,
    segments: list,
    title: str = "",
    model: Optional[str] = None,
    detail: str = "Medium",
    tone: str = "Student",
    language: str = "English",
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> str:
    progress = on_progress or (lambda f, m: None)
    client = genai.Client(api_key=api_key)
    models = list(dict.fromkeys([model or os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"] + FALLBACK_MODELS))
    system = _system(tone, language)
    chunks = chunk_segments(segments)
    total_chars = sum(len(c["text"]) for c in chunks)

    if total_chars <= SINGLE_PASS_MAX_CHARS:
        progress(0.3, "Writing notes…")
        material = " ".join(c["text"] for c in chunks)
        prompt = f'Video title: "{title}"\n\nTranscript:\n{material}\n\n{LENGTH[detail]}\n{STRUCTURE}'
        return normalize_md(_generate(client, models, prompt, system))

    parts = []
    n = len(chunks)
    for i, ch in enumerate(chunks, 1):
        progress((i - 1) / (n + 1), f"Reading part {i} of {n}…")
        prompt = (
            f'Part {i}/{n} ({fmt_time(ch["start"])}-{fmt_time(ch["end"])}) of the video "{title}".\n'
            "Write detailed, explained notes (full sentences, nested bullets with a 2-space indent). Keep [mm:ss] timestamps. Copy or faithfully reconstruct every code snippet in fenced code blocks. Include every concrete "
            "fact, step, example, tip, common mistake, shortcut/command and term definition, and note likely exam questions. No intro or outro.\n\n"
            f'{ch["text"]}'
        )
        notes = _generate(client, models, prompt, system)
        parts.append(f"### Part {i} ({fmt_time(ch['start'])}-{fmt_time(ch['end'])})\n{notes}")
        time.sleep(1)

    progress(n / (n + 1), "Merging into final notes…")
    merged = "\n\n".join(parts)
    prompt = (
        f'Below are partial notes covering the whole video "{title}", in order. '
        "Merge them into one coherent set of final notes. Remove repetition, keep every code snippet and explanation, and do not add new facts.\n\n"
        f"{merged}\n\n{LENGTH[detail]}\n{STRUCTURE}"
    )
    return normalize_md(_generate(client, models, prompt, system))


def normalize_md(md: str) -> str:
    """Tidy model output: consistent bullets/indent, no outer fence, no LaTeX math."""
    md = md.replace("\t", "    ").strip()
    md = re.sub(r"^```(?:markdown|md)\n(.*)\n```$", r"\1", md, flags=re.S)
    md = re.sub(r"^( *)[*\u2022] +", r"\1- ", md, flags=re.M)
    md = re.sub(r"(?<![\w$])\$([^$\s](?:[^$\n]*[^$\s])?)\$(?![\w$])", r"`\1`", md)
    md = re.sub(r"[ \t]+$", "", md, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", md)


def section_meta(title: str) -> tuple:
    """(icon name, colour) for a section title."""
    t = title.lower()
    return next((v for k, v in SECTION_META.items() if k in t), ("file-text", "#4F46E5"))


def split_sections(markdown: str) -> list:
    """Split notes on '## ' headings (ignoring code fences) -> [(title, body)]."""
    out, title, buf, fence = [], None, [], False
    for line in markdown.split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
        if not fence and re.match(r"^##\s+\S", line):
            if title is not None:
                out.append((title, "\n".join(buf).strip()))
            title, buf = line[2:].strip(), []
        elif title is not None:
            buf.append(line)
    if title is not None:
        out.append((title, "\n".join(buf).strip()))
    return out
