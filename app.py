"""YouTube Notes Extractor: paste a video URL, get structured notes and a PDF."""
import html
import os
import re
import textwrap

import streamlit as st
from dotenv import load_dotenv

from notes_generator import generate_notes, section_meta, split_sections
from pdf_export import build_pdf
from transcript import TranscriptError, get_transcript
from utils import extract_video_id, fmt_time, get_video_info, transcript_text

load_dotenv()
st.set_page_config(page_title="YouTube Notes Extractor", page_icon="📝", layout="wide",
                   initial_sidebar_state="collapsed")

# ---- Lucide icons (inline SVG paths) -------------------------------------------------
ICON = {
    "youtube": '<path d="M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17"/><path d="m10 15 5-3-5-3z"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "pin": '<line x1="12" x2="12" y1="17" y2="22"/><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z"/>',
    "file-text": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    "code": '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    "lightbulb": '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>',
    "terminal": '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>',
    "book-open": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "clipboard-list": '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>',
    "circle-help": '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
}


def svg(name: str, size: int = 18) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{ICON[name]}</svg>')


# ---- Theme ---------------------------------------------------------------------------
PALETTE = {
    "dark": {"bg": "#0E1120", "surface": "#161A2E", "surface2": "#1D2238", "border": "#2A3050",
             "text": "#E9ECF8", "muted": "#98A2C3", "accent": "#A5B4FC", "code-bg": "#0B0E1B",
             "code-fg": "#D8DEF5", "shadow": "0 1px 2px rgba(0,0,0,.35),0 10px 28px rgba(0,0,0,.30)",
             "scheme": "dark"},
    "light": {"bg": "#F4F5FA", "surface": "#FFFFFF", "surface2": "#F0F2F9", "border": "#E1E4F0",
              "text": "#1B2140", "muted": "#667085", "accent": "#4F46E5", "code-bg": "#F3F4FA",
              "code-fg": "#1B2140", "shadow": "0 1px 2px rgba(27,33,64,.06),0 10px 28px rgba(27,33,64,.08)",
              "scheme": "light"},
}

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');
html,body,.stApp,.stApp button,.stApp input,.stApp textarea,.stMarkdown{font-family:'Figtree',system-ui,sans-serif}
.stApp,[data-testid="stAppViewContainer"]{background:var(--bg);color:var(--text)}
[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1020px;padding-top:1.6rem;padding-bottom:4rem}
.stApp :is(p,li,label,h1,h2,h3,h4,summary,small){color:var(--text)}
[data-testid="stCaptionContainer"]{color:var(--muted)}
/* widgets */
[data-baseweb="input"],[data-baseweb="base-input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{background:var(--surface2)!important;border-color:var(--border)!important;border-radius:12px!important}
.stApp input,.stApp textarea{color:var(--text)!important;-webkit-text-fill-color:var(--text)!important;background:transparent!important}
[data-baseweb="select"] *{color:var(--text)}
[data-baseweb="select"] svg{fill:var(--muted)}
[data-baseweb="popover"] ul,[data-baseweb="popover"] [data-baseweb="menu"]{background:var(--surface)!important}
[data-baseweb="popover"] li{color:var(--text)!important}
[data-testid="stExpander"]{border:1px solid var(--border)!important;border-radius:14px;background:var(--surface)}
[data-testid="stForm"]{border:0;padding:0}
.stApp button[kind="primary"],.stApp button[kind="primaryFormSubmit"]{background:linear-gradient(135deg,#4F46E5,#0891B2)!important;border:0!important;border-radius:12px;font-weight:600;box-shadow:0 4px 14px rgba(79,70,229,.32);transition:transform .15s ease,box-shadow .15s ease}
.stApp button[kind="primary"]:hover,.stApp button[kind="primaryFormSubmit"]:hover{transform:translateY(-1px);box-shadow:0 8px 20px rgba(79,70,229,.4)}
.stApp :is(button[kind="primary"],button[kind="primaryFormSubmit"]) p{color:#fff!important}
.stApp :is(button[kind="secondary"],button[kind="secondaryFormSubmit"]){background:var(--surface)!important;border:1px solid var(--border)!important;border-radius:12px;transition:transform .15s ease,box-shadow .15s ease}
.stApp :is(button[kind="secondary"]):hover{transform:translateY(-1px);box-shadow:var(--shadow)}
[data-baseweb="tab-list"]{gap:.4rem;border-bottom:1px solid var(--border)}
[data-baseweb="tab"] p{color:var(--muted)!important;font-weight:600}
[data-baseweb="tab"][aria-selected="true"] p{color:var(--accent)!important}
/* code */
[data-testid="stCode"],[data-testid="stCode"] pre{background:var(--code-bg)!important;border-radius:12px}
[data-testid="stCode"]{border:1px solid var(--border)}
[data-testid="stCode"] :is(code,span){color:var(--code-fg)!important;font-family:'JetBrains Mono',ui-monospace,monospace!important;font-size:.87rem}
.stMarkdown :not(pre)>code{background:var(--surface2);color:var(--accent);padding:.1rem .4rem;border-radius:6px;font-family:'JetBrains Mono',ui-monospace,monospace;font-size:.88em}
/* layout pieces */
.brand{display:flex;align-items:center;gap:.6rem;font-weight:700;font-size:1.05rem;color:var(--text)}
.brand span.logo{display:grid;place-items:center;width:34px;height:34px;border-radius:10px;color:#fff;background:linear-gradient(135deg,#4F46E5,#0891B2)}
.hero{padding:1.7rem 1.9rem;border-radius:20px;border:1px solid var(--border);box-shadow:var(--shadow);margin:.8rem 0 1.1rem;background:linear-gradient(135deg,color-mix(in srgb,#4F46E5 14%,var(--surface)),color-mix(in srgb,#0891B2 9%,var(--surface)))}
.hero h1{font-size:1.9rem;font-weight:800;letter-spacing:-.02em;margin:0;padding:0;line-height:1.2}
.hero p{margin:.5rem 0 0;color:var(--muted);font-size:1.02rem;max-width:62ch}
.st-key-formcard{background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:1.1rem 1.2rem;box-shadow:var(--shadow);margin-bottom:1.2rem}
.vcard{display:flex;gap:1.2rem;align-items:center;padding:1rem;border-radius:18px;margin:.4rem 0 1.2rem;background:var(--surface);border:1px solid var(--border);box-shadow:var(--shadow)}
.vcard img{width:230px;max-width:38%;border-radius:12px}
.vcard h3{margin:0 0 .6rem;font-size:1.25rem;line-height:1.35;padding:0}
.pills{display:flex;flex-wrap:wrap;gap:.45rem;margin-bottom:.7rem}
.pill{display:inline-flex;align-items:center;gap:.4rem;padding:.25rem .65rem;border-radius:999px;font-size:.86rem;color:var(--muted);background:var(--surface2);border:1px solid var(--border)}
.vlink{color:var(--accent)!important;font-weight:600;text-decoration:none}
.vlink:hover{text-decoration:underline}
[class*="st-key-sec_"]{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--c);border-radius:16px;padding:1.1rem 1.5rem 1.25rem;margin-bottom:1rem;box-shadow:var(--shadow);transition:box-shadow .2s ease,transform .2s ease}
[class*="st-key-sec_"]:hover{transform:translateY(-1px);box-shadow:0 2px 4px rgba(0,0,0,.08),0 14px 34px rgba(0,0,0,.14)}
.sec-h{display:flex;align-items:center;gap:.7rem;font-size:1.2rem;font-weight:700;color:var(--text);margin-bottom:.4rem}
.chip{display:grid;place-items:center;width:34px;height:34px;border-radius:10px;color:var(--c);background:color-mix(in srgb,var(--c) 15%,transparent)}
[class*="st-key-sec_"] :is(p,li){line-height:1.7;font-size:1.02rem}
[class*="st-key-sec_"] li{margin:.2rem 0}
[class*="st-key-sec_"] :is(h3,h4){font-size:1.08rem;font-weight:700;margin:1rem 0 .3rem;padding:0}
.notice{padding:.85rem 1.1rem;border-radius:14px;border:1px solid;margin:.6rem 0;font-size:.98rem}
.notice.error{color:#E11D48;border-color:#E11D4855;background:#E11D4814}
.notice.info{color:var(--muted);border-color:var(--border);background:var(--surface)}
@media(max-width:700px){.vcard{flex-direction:column;align-items:flex-start}.vcard img{max-width:100%;width:100%}}
"""


def inject_theme(dark: bool) -> None:
    p = PALETTE["dark" if dark else "light"]
    root = ":root{" + "".join(f"--{k}:{v};" for k, v in p.items() if k != "scheme") + f"color-scheme:{p['scheme']}}}"
    st.markdown(f"<style>{root}{CSS}</style>", unsafe_allow_html=True)


def notice(msg: str, kind: str = "error") -> None:
    st.markdown(f'<div class="notice {kind}">{html.escape(msg)}</div>', unsafe_allow_html=True)


def render_body(body: str) -> None:
    """Markdown text via st.markdown, fenced code via st.code (copy button included)."""
    parts = re.split(r"```([\w+#.-]*)[ \t]*\n(.*?)```", body, flags=re.S)
    for i in range(0, len(parts), 3):
        if parts[i].strip():
            st.markdown(textwrap.dedent(parts[i]))
        if i + 2 < len(parts):
            st.code(textwrap.dedent(parts[i + 2]).rstrip(), language=parts[i + 1] or None)


@st.cache_data(show_spinner=False, ttl=3600)
def load_transcript(video_id: str) -> list:
    return get_transcript(video_id)


@st.cache_data(show_spinner=False, ttl=3600)
def load_info(video_id: str) -> dict:
    return get_video_info(video_id)


# ---- Page ----------------------------------------------------------------------------
inject_theme(st.session_state.get("dark", True))

left, right = st.columns([5, 1.3], vertical_alignment="center")
left.markdown(f'<div class="brand"><span class="logo">{svg("youtube", 20)}</span>Notes Extractor</div>',
              unsafe_allow_html=True)
right.toggle("Dark mode", value=True, key="dark")

st.markdown(
    '<div class="hero"><h1>Turn any YouTube video into study notes</h1>'
    "<p>Get a summary, key points, code, shortcuts, a revision sheet, FAQs and practice questions, "
    "ready to read here or download as a PDF.</p></div>",
    unsafe_allow_html=True,
)

env_key = os.getenv("GEMINI_API_KEY", "")
with st.container(key="formcard"):
    with st.form("generate", border=False):
        url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...",
                            label_visibility="collapsed")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1.2], vertical_alignment="bottom")
        detail = c1.selectbox("Note length", ["Short", "Medium", "Detailed"], index=1)
        tone = c2.selectbox("Tone", ["Student", "Professional", "Casual"])
        language = c3.selectbox("Language", ["English", "Hindi", "Spanish", "French", "German"])
        go = c4.form_submit_button("Generate notes", type="primary", use_container_width=True)
        with st.expander("API settings", expanded=not env_key):
            api_key = st.text_input("Gemini API key", value=env_key, type="password")
            model = st.text_input("Model", value=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))

if go:
    vid = extract_video_id(url)
    if not vid:
        notice("That isn't a YouTube link. Paste a youtube.com or youtu.be URL.")
    elif not api_key:
        notice("Add your Gemini API key under API settings or in the .env file.")
    else:
        try:
            with st.spinner("Fetching transcript..."):
                segments = load_transcript(vid)
            info = load_info(vid)
            bar = st.progress(0.0, text="Starting...")
            notes = generate_notes(
                api_key, segments, info["title"], model, detail, tone, language,
                on_progress=lambda f, m: bar.progress(min(max(f, 0.0), 1.0), text=m),
            )
            bar.empty()
            st.session_state["result"] = {"info": info, "segments": segments, "notes": notes}
        except TranscriptError as e:
            notice(str(e))
        except Exception as e:
            notice(f"Notes could not be generated. {e}")

res = st.session_state.get("result")
if not res:
    notice("Paste a link above and press Generate notes. The video needs captions.", "info")
    st.stop()

info, segments, notes = res["info"], res["segments"], res["notes"]
secs = split_sections(notes)
length = fmt_time(segments[-1]["start"]) if segments else "unknown"
author = html.escape(info["author"] or "Unknown channel")
st.markdown(
    f'<div class="vcard"><img src="{info["thumbnail"]}" alt="Video thumbnail"><div>'
    f'<h3>{html.escape(info["title"])}</h3><div class="pills">'
    f'<span class="pill">{svg("user", 14)}{author}</span>'
    f'<span class="pill">{svg("clock", 14)}{length}</span>'
    f'<span class="pill">{svg("file-text", 14)}{len(secs)} sections, {len(notes.split())} words</span></div>'
    f'<a class="vlink" href="{info["url"]}" target="_blank">Watch on YouTube</a></div></div>',
    unsafe_allow_html=True,
)

tab_notes, tab_tr, tab_export = st.tabs(["Notes", "Full transcript", "Export"])

with tab_notes:
    colors_css = "".join(f".st-key-sec_{i}{{--c:{section_meta(t)[1]}}}" for i, (t, _) in enumerate(secs))
    st.markdown(f"<style>{colors_css}</style>", unsafe_allow_html=True)
    if not secs:
        st.markdown(notes)
    for i, (title, body) in enumerate(secs):
        with st.container(key=f"sec_{i}"):
            st.markdown(f'<div class="sec-h"><span class="chip">{svg(section_meta(title)[0])}</span>'
                        f"<span>{html.escape(title)}</span></div>", unsafe_allow_html=True)
            render_body(body)

with tab_tr:
    st.text_area("Transcript", transcript_text(segments), height=500, label_visibility="collapsed")

with tab_export:
    slug = re.sub(r"[^a-z0-9]+", "-", info["title"].lower()).strip("-")[:50] or "notes"
    md = f"# {info['title']}\n\n{info['url']}\n\n{notes}\n"
    if "pdf" not in res:
        try:
            res["pdf"] = build_pdf(info["title"], info["url"], info["author"], notes)
        except Exception as e:
            res["pdf"] = None
            notice(f"PDF could not be created. {e}")
    c1, c2, c3, c4 = st.columns(4)
    if res["pdf"]:
        c1.download_button("Download PDF", res["pdf"], f"{slug}.pdf", "application/pdf",
                           type="primary", use_container_width=True)
    c2.download_button("Markdown", md, f"{slug}.md", "text/markdown", use_container_width=True)
    c3.download_button("Plain text", md, f"{slug}.txt", "text/plain", use_container_width=True)
    c4.download_button("Transcript", transcript_text(segments), f"{slug}-transcript.txt",
                       "text/plain", use_container_width=True)
    st.caption("The PDF uses standard fonts, so notes written in non-Latin scripts (such as Hindi) "
               "show as '?'. Use the Markdown download for those.")

