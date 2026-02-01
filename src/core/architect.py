# Copyright 2026 Pramod Kumar Voola
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# -----------------------------------------------------------------------------
# THE BRAIN - BEDROCK ARCHITECT
# -----------------------------------------------------------------------------
# Responsibility: Uses AWS Bedrock (Claude 3.5 Sonnet) to draft the
# Fabrication Instructions (GantryManifest) from a voice memo.
#
# Features:
# - Vision/Multimodal support for mockup matching
# - 95% mockup accuracy target for uploaded designs
# - Auto-includes design reference in generated README
#
# Authentication: Uses Bedrock API Key (simpler than IAM).
# -----------------------------------------------------------------------------

import base64
import json
import os
import re
from pathlib import Path

import requests
from pydantic import ValidationError
from rich.console import Console

from src.domain.models import GantryManifest

console = Console()

# Missions directory for reading design images
MISSIONS_DIR = Path(__file__).parent.parent.parent / "missions"

# Bedrock API configuration
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")
BEDROCK_ENDPOINT = f"https://bedrock-runtime.{BEDROCK_REGION}.amazonaws.com"

# =============================================================================
# 3-TIER MODEL ARCHITECTURE (Robust Multi-Model Fallback)
# =============================================================================
# GantryFleet uses a tiered approach to maximize success rate:
# - Tier 1 (Primary): Claude 4 Opus - Most capable, best for complex apps
# - Tier 2 (Fallback): Claude 4 Sonnet - Balanced, fast, reliable
# - Tier 3 (Safety Net): Claude 3.5 Sonnet - Battle-tested, production-proven
#
# The system tries each tier before declaring failure, ensuring simple apps
# NEVER fail and complex apps get multiple chances with smarter models.
# =============================================================================

MODEL_TIERS = [
    {
        "name": "Claude Sonnet 4",
        "id": "anthropic.claude-sonnet-4-20250514-v1:0",
        "max_tokens": 8192,
        "description": "Latest model - best for complex applications",
    },
    {
        "name": "Claude 3.5 Sonnet V2",
        "id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "max_tokens": 8192,
        "description": "Updated 3.5 Sonnet - excellent reliability",
    },
    {
        "name": "Claude 3.5 Sonnet V1",
        "id": "anthropic.claude-3-5-sonnet-20240620-v1:0",
        "max_tokens": 4096,
        "description": "Battle-tested production model",
    },
]

# Default to highest tier, fallback enabled
CLAUDE_MODEL_ID = MODEL_TIERS[0]["id"]
ENABLE_MODEL_FALLBACK = True

# =============================================================================
# FAMOUS THEMES DESIGN SYSTEM
# =============================================================================
# Pixel-perfect cloning of famous apps. When user says "Build LinkedIn",
# Gantry injects these exact design specs into the system prompt.
# =============================================================================

FAMOUS_THEMES: dict[str, dict] = {
    "LINKEDIN": {
        "name": "LinkedIn",
        "colors": {
            "primary": "#0a66c2",
            "secondary": "#f3f2ef",
            "background": "#f4f2ee",
            "card": "#ffffff",
            "text": "#000000e6",
            "text_secondary": "#00000099",
            "border": "#00000026",
            "success": "#057642",
        },
        "font": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "layout": "navbar-top-fixed, three-column-grid",
        "components": [
            "Fixed top navbar (white, 52px height, shadow)",
            "Left sidebar (profile card, 225px width)",
            "Center feed (main content, max 555px)",
            "Right sidebar (news/ads, 300px width)",
            "Rounded profile pictures",
            "Card-based posts with reactions bar",
        ],
        "icons": "lucide-react",
        "border_radius": "8px",
        "sample_page": "feed/home with post composer and posts",
    },
    "TWITTER": {
        "name": "Twitter/X",
        "colors": {
            "primary": "#1d9bf0",
            "secondary": "#0f1419",
            "background": "#000000",
            "card": "#16181c",
            "text": "#e7e9ea",
            "text_secondary": "#71767b",
            "border": "#2f3336",
            "accent": "#f91880",
        },
        "font": "'TwitterChirp', -apple-system, system-ui, sans-serif",
        "layout": "sidebar-left-fixed, feed-center, trends-right",
        "components": [
            "Left sidebar navigation (68px collapsed, 275px expanded)",
            "Center timeline (max 600px)",
            "Right sidebar (search, trends, 350px)",
            "Circular profile pictures",
            "Tweet cards with reply/retweet/like/share bar",
            "Floating compose button (mobile)",
        ],
        "icons": "lucide-react",
        "border_radius": "16px (full round for buttons)",
        "sample_page": "home timeline with tweet composer",
    },
    "INSTAGRAM": {
        "name": "Instagram",
        "colors": {
            "primary": "#0095f6",
            "gradient": "linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)",
            "background": "#000000",
            "card": "#000000",
            "text": "#f5f5f5",
            "text_secondary": "#a8a8a8",
            "border": "#262626",
        },
        "font": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, sans-serif",
        "layout": "navbar-top, stories-row, grid-feed",
        "components": [
            "Top navbar with logo, search, icons",
            "Stories row (horizontal scroll, circular thumbnails)",
            "Post cards (square images, action bar)",
            "Grid profile view (3 columns)",
            "Bottom tab navigation (mobile)",
        ],
        "icons": "lucide-react",
        "border_radius": "8px cards, full round for stories",
        "sample_page": "feed with stories and posts",
    },
    "FACEBOOK": {
        "name": "Facebook",
        "colors": {
            "primary": "#1877f2",
            "secondary": "#42b72a",
            "background": "#f0f2f5",
            "card": "#ffffff",
            "text": "#050505",
            "text_secondary": "#65676b",
            "border": "#dddfe2",
            "login_green": "#42b72a",
        },
        "font": "Segoe UI Historic, Segoe UI, Helvetica, Arial, sans-serif",
        "layout": "centered-card, two-column on desktop",
        "components": [
            "Blue 'facebook' logo text (font-size: 60px, color: #1877f2)",
            "Login card (white, rounded, shadow)",
            "Input fields (large, rounded, 16px padding)",
            "Blue 'Log In' button (full-width, rounded)",
            "Green 'Create new account' button (42b72a)",
            "Recent logins section (profile cards with X to remove)",
            "Footer with language selector and links",
            "Divider line with 'or' text",
            "Forgot password link (blue, centered)",
        ],
        "login_page": {
            "logo": "facebook (lowercase, #1877f2, 60px, font-weight: bold)",
            "tagline": "Recent Logins / Click your picture or add an account",
            "left_section": "Recent login profile cards",
            "right_section": "Login form + Create account",
        },
        "icons": "lucide-react",
        "border_radius": "8px",
        "sample_page": "news feed with post composer",
    },
    "SLACK": {
        "name": "Slack",
        "colors": {
            "primary": "#4a154b",
            "secondary": "#36c5f0",
            "accent": "#ecb22e",
            "background": "#1a1d21",
            "sidebar": "#19171d",
            "card": "#222529",
            "text": "#d1d2d3",
            "text_secondary": "#ababad",
        },
        "font": "Slack-Lato, Lato, 'Helvetica Neue', sans-serif",
        "layout": "sidebar-left-fixed, channel-center, thread-right",
        "components": [
            "Workspace switcher (left edge)",
            "Channel sidebar (220px)",
            "Main message area (threaded)",
            "Thread panel (right, optional)",
            "Message input with rich formatting",
            "Channel header with info",
        ],
        "icons": "lucide-react",
        "border_radius": "6px",
        "sample_page": "channel view with messages",
    },
    "SPOTIFY": {
        "name": "Spotify",
        "colors": {
            "primary": "#1db954",
            "background": "#121212",
            "card": "#181818",
            "card_hover": "#282828",
            "text": "#ffffff",
            "text_secondary": "#b3b3b3",
        },
        "font": "Circular, spotify-circular, Helvetica, Arial, sans-serif",
        "layout": "sidebar-left, main-content, now-playing-bottom",
        "components": [
            "Left navigation sidebar (dark)",
            "Main content area (scrollable grid)",
            "Now Playing bar (bottom, fixed)",
            "Album art grid (cards)",
            "Playlist headers with gradient",
            "Progress bar with hover preview",
        ],
        "icons": "lucide-react",
        "border_radius": "8px cards, 4px for now-playing",
        "sample_page": "home with playlists grid",
    },
    "NOTION": {
        "name": "Notion",
        "colors": {
            "primary": "#000000",
            "background": "#191919",
            "card": "#202020",
            "text": "#ffffffcf",
            "text_secondary": "#ffffff71",
            "accent": "#35a9ff",
            "border": "#ffffff1a",
        },
        "font": "ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif",
        "layout": "sidebar-left-collapsible, main-editor",
        "components": [
            "Collapsible sidebar with pages tree",
            "Page header with icon/cover",
            "Block-based editor",
            "Slash command menu",
            "Breadcrumb navigation",
            "Properties panel",
        ],
        "icons": "lucide-react",
        "border_radius": "3px",
        "sample_page": "workspace with page tree and editor",
    },
    "AIRBNB": {
        "name": "Airbnb",
        "colors": {
            "primary": "#ff385c",
            "secondary": "#00a699",
            "background": "#ffffff",
            "card": "#ffffff",
            "text": "#222222",
            "text_secondary": "#717171",
            "border": "#dddddd",
        },
        "font": "Circular, -apple-system, BlinkMacSystemFont, Roboto, sans-serif",
        "layout": "navbar-top, search-hero, card-grid",
        "components": [
            "Sticky navbar with search bar",
            "Category filter bar (horizontal scroll)",
            "Listing cards (image carousel, details)",
            "Map view toggle",
            "Filter modal",
            "Wishlist heart icon",
        ],
        "icons": "lucide-react",
        "border_radius": "12px",
        "sample_page": "home with search and listings grid",
    },
}


def get_theme_prompt(design_target: str) -> str:
    """
    Get the design system injection prompt for a famous app clone.

    Args:
        design_target: The app to clone (LINKEDIN, TWITTER, etc.)

    Returns:
        Additional system prompt text with exact design specs.
    """
    theme = FAMOUS_THEMES.get(design_target.upper())
    if not theme:
        return ""

    colors = theme.get("colors", {})
    color_lines = "\n".join([f"    --{k}: {v};" for k, v in colors.items()])

    components = "\n".join([f"  - {c}" for c in theme.get("components", [])])

    # Special handling for Facebook login page
    facebook_extra = ""
    if theme["name"] == "Facebook":
        facebook_extra = """

CRITICAL: FACEBOOK LOGIN PAGE EXACT LAYOUT:
The Facebook login page has a VERY SPECIFIC layout that MUST be followed:

1. LIGHT BACKGROUND - Use #f0f2f5 (NOT dark theme!)
2. TWO-COLUMN LAYOUT on desktop:
   - LEFT: Blue "facebook" logo (60px, bold) + "Recent Logins" section with profile cards
   - RIGHT: White login card with form
3. LOGIN CARD CONTENTS:
   - Email/phone input (large, rounded corners)
   - Password input (large, rounded corners)
   - Blue "Log In" button (#1877f2, full width, rounded)
   - "Forgot password?" link (centered, blue)
   - Horizontal divider line
   - Green "Create new account" button (#42b72a, centered, smaller width)
4. FOOTER: Language selector and legal links

DO NOT use dark theme. Facebook's login page is LIGHT themed."""

    return f"""
=== DESIGN SYSTEM: {theme["name"]} Style ===

Apply the {theme["name"]}-style design pattern. Use this color palette and layout.
Build an ORIGINAL app that follows modern {theme["name"]}-style design patterns.

CSS VARIABLES (MUST USE EXACTLY):
:root {{
{color_lines}
    --font-family: {theme.get("font", "system-ui")};
    --border-radius: {theme.get("border_radius", "8px")};
}}

LAYOUT: {theme.get("layout", "standard")}
{facebook_extra}

REQUIRED COMPONENTS:
{components}

ICONS: Use {theme.get("icons", "lucide-react")} for matching icons.

SAMPLE PAGE TO BUILD: {theme.get("sample_page", "main view")}

CRITICAL:
1. Use Tailwind CSS classes that match these exact hex colors
2. Include a realistic mock login page as entry point
3. Use placeholder content that looks real (names, avatars, posts)
4. Mobile responsive (works on phone)
5. Include hover states and transitions

"""


def detect_design_target(prompt: str) -> str | None:
    """
    Detect if user is requesting a clone of a famous app.

    Args:
        prompt: User's request.

    Returns:
        Design target key if detected, None otherwise.
    """
    prompt_lower = prompt.lower()

    keywords_map = {
        "LINKEDIN": ["linkedin", "professional network", "job network"],
        "TWITTER": ["twitter", "x.com", "tweet", "microblog"],
        "INSTAGRAM": ["instagram", "insta", "photo sharing"],
        "FACEBOOK": ["facebook", "fb", "social network"],
        "SLACK": ["slack", "team chat", "workspace chat"],
        "SPOTIFY": ["spotify", "music streaming", "music player"],
        "NOTION": ["notion", "note taking", "workspace"],
        "AIRBNB": ["airbnb", "vacation rental", "booking"],
    }

    for target, keywords in keywords_map.items():
        if any(kw in prompt_lower for kw in keywords):
            return target

    return None


# System prompt that constrains Claude to output valid JSON
SYSTEM_PROMPT = """You are the Gantry Chief Architect. Generate REAL WEB APPLICATIONS with beautiful UI.

CRITICAL RULES:
1. Output ONLY valid JSON matching the GantryManifest schema.
2. NO markdown, NO explanation, NO commentary - just pure JSON.
3. Build REAL web apps with HTML/CSS/JavaScript UI - NOT just JSON APIs.
4. Make the UI beautiful, modern, and functional.
5. Prefer first-pass success: use valid syntax, correct paths, and audit_command/run_command that run without errors so the build does not need self-healing.

=== MOCKUP/SCREENSHOT MATCHING (CRITICAL - 95% ACCURACY TARGET) ===

If a design mockup, screenshot, or sketch image is provided:

1. **ANALYZE THE IMAGE CAREFULLY**: Study every visual element - layout, colors, typography, spacing, components, icons.

2. **95% VISUAL FIDELITY TARGET**: Your generated UI MUST match the uploaded design at 95% accuracy:
   - EXACT color values (use eyedropper-equivalent precision)
   - EXACT layout structure (columns, rows, spacing, alignment)
   - EXACT typography (font sizes, weights, line-heights)
   - EXACT component styles (buttons, inputs, cards, borders, shadows)
   - EXACT spacing and padding (use the visible relationships)

3. **WHAT TO REPLICATE**:
   - Overall page structure and grid system
   - Navigation placement and style
   - Card/component layouts and shadows
   - Button styles, sizes, and colors
   - Input field styles and placeholders
   - Color scheme (primary, secondary, background, text)
   - Icon styles and placement (use similar icons from lucide-react)
   - Spacing rhythm and whitespace patterns

4. **INCLUDE DESIGN REFERENCE IN README**:
   When a mockup is provided, ALWAYS include in your generated README.md:
   ```
   ## Design Reference
   This project was built to match the following design mockup:
   
   ![Design Mockup](./design-reference.png)
   
   The UI has been crafted to achieve 95%+ visual fidelity with the original design.
   ```

5. **CSS PRECISION**:
   - Use CSS custom properties for colors (--primary, --secondary, etc.)
   - Extract exact hex values from the mockup
   - Match border-radius precisely (sharp, slightly rounded, or pill-shaped)
   - Match shadow depths and blur radii
   - Match font weights and letter-spacing

DESIGN SYSTEM MATCHING (IMPORTANT):
- When user requests "social network style" or "professional network style": Apply the specified design system.
- Use the exact COLOR PALETTE and LAYOUT from the design target variables.
- Light backgrounds for social/professional apps (#f0f2f5 or #f4f2ee).
- Proper font families, border-radius, and spacing.
- Build ORIGINAL apps that follow industry design patterns, not copies.
- Focus on creating a WORKING prototype with the specified aesthetic.

SCHEMA:
{
  "project_name": "string (alphanumeric, starts with letter, max 64 chars)",
  "stack": "node",
  "files": [{"path": "relative/path.ext", "content": "file content here"}],
  "audit_command": "command to verify the build works",
  "run_command": "command to run the app locally"
}

=== UI/UX QUALITY STANDARDS (STAFF ENGINEER LEVEL) ===

You are a STAFF ENGINEER with 10+ years of experience. Build UIs that are:
- PROFESSIONAL: No amateur mistakes like tiny fonts, text overflow, or missing hover states
- POLISHED: Smooth transitions, proper shadows, consistent spacing
- ACCESSIBLE: Good contrast ratios, focus states, readable fonts

TYPOGRAPHY (MANDATORY):
- Font stack: `font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;`
- Body text: minimum 14px, line-height: 1.5-1.6
- Headings: Use proper hierarchy (h1 > h2 > h3)

TEXT HANDLING (CRITICAL - PREVENTS OVERFLOW):
- All text containers: `word-wrap: break-word; overflow-wrap: break-word; word-break: break-word;`
- FLEXBOX TEXT WRAPPING: Add `min-width: 0;` to flex children that contain text (CRITICAL!)
- Long text: Use `text-overflow: ellipsis; overflow: hidden; white-space: nowrap;` OR
- Multi-line truncation: `-webkit-line-clamp: 3; -webkit-box-orient: vertical; display: -webkit-box; overflow: hidden;`
- Max content width for readability: `max-width: 70ch;` for paragraphs
- ALWAYS wrap text content in a `<span>` inside flex containers for proper wrapping

SPACING & LAYOUT:
- Use consistent spacing scale: 4px, 8px, 12px, 16px, 24px, 32px
- Card padding: minimum 16px
- Section margins: minimum 24px
- NEVER let content touch container edges

INTERACTIVE ELEMENTS (MANDATORY):
- ALL buttons need: `cursor: pointer;` and `:hover` state with slight color change
- ALL inputs need: `:focus` state with border/outline change
- Transitions: `transition: all 0.2s ease;` on interactive elements

PROFESSIONAL POLISH:
- Shadows for depth: `box-shadow: 0 2px 8px rgba(0,0,0,0.1);`
- Border radius: 6px-12px for cards, 4px for inputs
- Subtle borders: `border: 1px solid rgba(0,0,0,0.1);`

=== BUILD REAL WEB APPLICATIONS (VERCEL STRUCTURE - CRITICAL) ===

ALWAYS create these files with EXACT structure for Vercel deployment:

1. **public/index.html** - The main HTML page with embedded CSS and JavaScript
2. **vercel.json** - Configuration (REQUIRED)
3. **package.json** - Minimal config
4. **tests/index.test.js** - Unit tests (REQUIRED)
5. **api/index.js** - Backend API if needed (use module.exports format!)

=== VERCEL STRUCTURE REQUIREMENTS (MUST FOLLOW) ===

**vercel.json** (CORRECT format):
```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/public/index.html" }
  ]
}
```

**api/index.js** (CORRECT format - use module.exports NOT export default):
```javascript
module.exports = (req, res) => {
  res.status(200).json({ message: "Hello from API" });
};
```

**WRONG (will fail):**
```javascript
export default function handler(req, res) {...}  // ESM - DON'T USE
```

**FILE STRUCTURE (MUST MATCH):**
```
project/
├── public/
│   └── index.html      # Main HTML with embedded CSS/JS
├── api/
│   └── index.js        # Optional API (use module.exports!)
├── tests/
│   └── index.test.js   # REQUIRED - unit tests
├── vercel.json         # REQUIRED - deployment config
└── package.json        # REQUIRED - project config
```

=== EXAMPLE: Todo App ===

public/index.html:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Todo App</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 16px; line-height: 1.5;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
      min-height: 100vh; display: flex; justify-content: center; align-items: center;
      padding: 16px;
    }
    .container { 
      background: white; padding: 24px; border-radius: 16px; 
      box-shadow: 0 20px 60px rgba(0,0,0,0.2); width: 100%; max-width: 420px;
    }
    h1 { color: #1a1a2e; margin-bottom: 20px; text-align: center; font-size: 1.75rem; font-weight: 600; }
    .input-group { display: flex; gap: 8px; margin-bottom: 20px; }
    input { 
      flex: 1; padding: 12px 16px; border: 2px solid #e5e7eb; border-radius: 8px; 
      font-size: 1rem; font-family: inherit; transition: border-color 0.2s ease;
    }
    input:focus { outline: none; border-color: #667eea; }
    input::placeholder { color: #9ca3af; }
    button { 
      padding: 12px 20px; background: #667eea; color: white; border: none; 
      border-radius: 8px; cursor: pointer; font-weight: 600; font-family: inherit;
      transition: background 0.2s ease, transform 0.1s ease;
    }
    button:hover { background: #5a6fd6; transform: translateY(-1px); }
    button:active { transform: translateY(0); }
    ul { list-style: none; }
    li { 
      padding: 14px 16px; background: #f8f9fa; margin-bottom: 8px; border-radius: 10px;
      display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
      transition: background 0.2s ease;
    }
    li:hover { background: #f1f3f5; }
    li.done span { text-decoration: line-through; opacity: 0.5; }
    li span { 
      flex: 1; min-width: 0; /* CRITICAL: allows text to shrink and wrap */
      word-wrap: break-word; overflow-wrap: break-word; word-break: break-word;
    }
    .delete { 
      background: #ff4757; padding: 6px 10px; font-size: 0.75rem; border-radius: 6px;
      transition: background 0.2s ease; flex-shrink: 0; /* Don't shrink the button */
    }
    .delete:hover { background: #ee3b4b; }
    .empty { color: #9ca3af; text-align: center; padding: 32px; font-style: italic; }
  </style>
</head>
<body>
  <div class="container">
    <h1>My Todos</h1>
    <div class="input-group">
      <input type="text" id="input" placeholder="Add a todo..." onkeypress="if(event.key==='Enter')addTodo()">
      <button onclick="addTodo()">Add</button>
    </div>
    <ul id="list"></ul>
  </div>
  <script>
    let todos = JSON.parse(localStorage.getItem('todos') || '[]');
    function render() {
      document.getElementById('list').innerHTML = todos.map((t, i) =>
        `<li class="${t.done ? 'done' : ''}" onclick="toggle(${i})"><span>${t.text}</span><button class="delete" onclick="event.stopPropagation();del(${i})">x</button></li>`
      ).join('');
    }
    function addTodo() {
      const input = document.getElementById('input');
      if (input.value.trim()) {
        todos.push({ text: input.value.trim(), done: false });
        input.value = '';
        save(); render();
      }
    }
    function toggle(i) { todos[i].done = !todos[i].done; save(); render(); }
    function del(i) { todos.splice(i, 1); save(); render(); }
    function save() { localStorage.setItem('todos', JSON.stringify(todos)); }
    render();
  </script>
</body>
</html>
```

vercel.json (routes static files and API):
```json
{
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/index.js" }
  ]
}
```

package.json:
```json
{"name": "todo-app", "version": "1.0.0"}
```

=== DESIGN REQUIREMENTS ===
1. Use modern CSS: gradients, shadows, rounded corners, flexbox/grid
2. Make it VISUALLY IMPRESSIVE - use colors, animations
3. Mobile responsive (use viewport meta, relative units)
4. Interactive with JavaScript (not just static HTML)
5. Include proper error handling and loading states

=== FOR DIFFERENT APP TYPES ===
- **Dashboard**: Cards, charts (use CSS or simple canvas), stats
- **Landing Page**: Hero section, features, call-to-action buttons
- **Calculator**: Buttons grid, display, interactive calculations
- **Game**: Canvas or DOM-based, score tracking, animations
- **Form App**: Input validation, success/error messages, submissions
- **Weather/Temperature App** (IMPORTANT): 
  - MUST have a city search input where user can type city name
  - MUST use a free weather API (Open-Meteo: https://open-meteo.com/en/docs)
  - MUST show at least 7-day forecast with min/max temperatures
  - Show weather icons/conditions (sunny, cloudy, rain, etc.)
  - Include current temperature prominently
  - Example API: https://api.open-meteo.com/v1/forecast?latitude=40.71&longitude=-74.01&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto
  - Use geocoding for city search: https://geocoding-api.open-meteo.com/v1/search?name=NewYork&count=5

=== DATA LAYER / ORM (CRITICAL FOR BIG WEBSITE PROTOTYPES) ===

**Do NOT use traditional ORMs or database connections in generated code.**
- No Prisma, Sequelize, TypeORM, SQLAlchemy, Django ORM, or any library that expects a long-lived DB connection.
- Reason: The built app runs on Vercel serverless; no database is provisioned in the build pod or at deploy time. ORM code would fail at build or runtime (connection refused, timeout).
- For prototypes (including "big" sites like feeds, dashboards, social UIs): use ONLY the patterns below so the build passes and deploys.

**Allowed patterns for data persistence:**
1. **localStorage / sessionStorage** – for client-side state (todos, preferences, simple auth).
2. **In-memory in api/index.js** – serverless function can keep a small in-memory store per request; for demo only (no cross-request persistence unless you use a single global object, which is not durable).
3. **External API (future)** – If you document "For production, plug in Supabase/PlanetScale via env" you may add a thin HTTP client that reads from an optional API URL; do NOT add DB connection strings or ORM in generated code.

**For "big website" prototypes (e.g. LinkedIn-style, dashboard, social feed):**
- Use the same rules: localStorage for user/session simulation, in-memory or localStorage for feed/list data in the prototype.
- Keep the UI and layout rich; keep the data layer simple so the app builds, audits, and deploys. Real ORM and DB come when the user takes the repo to production.

=== PROTOTYPING STRATEGY (For Larger Websites) ===
IMPORTANT: Build times are limited to 180 seconds. For "big websites" or complex apps:
1. Start with a LIGHTER PROTOTYPE that deploys quickly
2. Use localStorage instead of databases (no ORM, no DB connections)
3. After deployment, user can add real databases incrementally
4. This avoids timeouts and ensures successful delivery

Example progression:
- Phase 1: Static UI with mock data → Deploy & Verify
- Phase 2: Add localStorage for persistence → Deploy & Verify  
- Phase 3: User connects Supabase/MongoDB → Production ready

=== CRUD OPERATIONS (For Apps Needing Data Storage) ===
When user requests an app with login, user data, or persistent storage:

1. **Use localStorage for Client-Side Storage**:
```javascript
const db = {
  save: (key, data) => localStorage.setItem(key, JSON.stringify(data)),
  load: (key) => JSON.parse(localStorage.getItem(key) || '[]'),
  delete: (key) => localStorage.removeItem(key)
};
```

2. **User Authentication (Simple)**:
```javascript
const auth = {
  users: () => db.load('users'),
  register: (email, pass) => {
    const users = auth.users();
    if (users.find(u => u.email === email)) return { error: 'User exists' };
    users.push({ email, pass: btoa(pass), created: Date.now() });
    db.save('users', users);
    return { success: true };
  },
  login: (email, pass) => {
    const user = auth.users().find(u => u.email === email && u.pass === btoa(pass));
    if (user) { sessionStorage.setItem('user', email); return { success: true }; }
    return { error: 'Invalid credentials' };
  },
  logout: () => sessionStorage.removeItem('user'),
  current: () => sessionStorage.getItem('user')
};
```

3. **CRUD Operations Template**:
```javascript
const crud = {
  items: () => db.load('items'),
  create: (item) => { const all = crud.items(); all.push({...item, id: Date.now()}); db.save('items', all); },
  read: (id) => crud.items().find(i => i.id === id),
  update: (id, data) => { const all = crud.items().map(i => i.id === id ? {...i, ...data} : i); db.save('items', all); },
  delete: (id) => { const all = crud.items().filter(i => i.id !== id); db.save('items', all); }
};
```

4. **Always include tests for CRUD operations**:
```javascript
// tests/index.test.js
const assert = (c, m) => { if (!c) throw new Error(m); };

// Test CRUD
let items = [];
items.push({ id: 1, name: 'Test' });
assert(items.length === 1, 'Create failed');
items = items.filter(i => i.id !== 1);
assert(items.length === 0, 'Delete failed');

console.log('All CRUD tests passed');
```

=== TESTING REQUIREMENTS (MANDATORY - ALL LANGUAGES) ===

EVERY app MUST include tests with 90% coverage. Test files depend on stack:

**JavaScript/Node.js apps:** tests/index.test.js
**Python apps:** tests/test_app.py  
**Static HTML apps:** tests/index.test.js (test any embedded JS logic)

=== LANGUAGE-SPECIFIC TEST PATTERNS ===

### JAVASCRIPT/NODE.JS TESTS (tests/index.test.js)

```javascript
const assert = (condition, msg) => { if (!condition) throw new Error(msg); };

// STATEFUL MOCKS (required for DOM testing)
const mockElements = {
  'input': { value: '', innerHTML: '', textContent: '', style: {} },
  'list': { innerHTML: '', textContent: '', style: {} }
};
global.document = {
  getElementById: (id) => mockElements[id] || { value: '', innerHTML: '', textContent: '', style: {} }
};
global.localStorage = {
  _data: {},
  setItem(k, v) { this._data[k] = String(v); },
  getItem(k) { return this._data[k] || null; },
  removeItem(k) { delete this._data[k]; },
  clear() { this._data = {}; }
};

// DUPLICATE functions from HTML here (cannot extract from browser)
let items = [];
function addItem() { /* copy exact code from HTML */ }

// Tests
mockElements['input'].value = 'Test';
addItem();
assert(items.length === 1, 'Should add item');
console.log('All tests passed!');
```

### PYTHON TESTS (tests/test_app.py)

```python
import sys
sys.path.insert(0, '.')

def test_basic():
    # Test pure functions first
    result = 1 + 1
    assert result == 2, "Basic math failed"

def test_data_operations():
    items = []
    items.append({"id": 1, "text": "Test"})
    assert len(items) == 1, "Append failed"
    items = [i for i in items if i["id"] != 1]
    assert len(items) == 0, "Filter failed"

if __name__ == "__main__":
    test_basic()
    test_data_operations()
    print("All tests passed!")
```

=== FORBIDDEN TEST PATTERNS (WILL CAUSE BUILD FAILURE) ===

**UNIVERSAL RULES (ALL LANGUAGES):**
1. NEVER import external test frameworks not in package.json/requirements.txt
2. NEVER read files from disk to extract code (no fs.readFileSync, no open())
3. NEVER use eval() or exec() to run code extracted from other files
4. NEVER use database connections in tests (mock all data)
5. NEVER make real HTTP requests in tests (mock responses)
6. NEVER rely on environment variables being set
7. NEVER use async/await without proper handling

**JAVASCRIPT-SPECIFIC FORBIDDEN PATTERNS:**
- NEVER use document.querySelector() - only getElementById is mocked
- NEVER use document.querySelectorAll() - not mocked
- NEVER use addEventListener in HTML - use onclick, onkeypress, etc.
- NEVER use eval() to extract <script> content from HTML
- NEVER use require('fs') to read HTML files
- NEVER use import/export in test files - use CommonJS (module.exports)

**PYTHON-SPECIFIC FORBIDDEN PATTERNS:**
- NEVER import pytest, unittest without adding to requirements.txt
- NEVER use Django/Flask test clients without proper mocking
- NEVER connect to real databases - use mock data
- NEVER import the main app if it has side effects on import

**CRITICAL: Functions MUST be FULLY DUPLICATED in test files**
Tests run in a clean environment. You CANNOT extract functions from HTML or other files.

WRONG - Empty stub (WILL FAIL):
```javascript
function searchWeather() {
  // This would normally update DOM - WRONG! Test will fail!
}
```

RIGHT - Full implementation copied:
```javascript
function searchWeather() {
  const cityInput = document.getElementById('city-input');
  const weatherInfo = document.getElementById('weather-info');
  // ... FULL logic here, exactly as in HTML ...
  weatherInfo.style.display = 'block';
  weatherInfo.innerHTML = `<div>${cityName}</div>`;
}
```

RULE: If a function modifies DOM or state, you MUST copy the FULL implementation.
Never use stubs or comments like "would normally update DOM".

=== DOM MOCKING (CRITICAL - JAVASCRIPT ONLY) ===

When testing browser code that uses document.getElementById, you MUST use STATEFUL mocks.

**BAD PATTERN (will fail):**
```javascript
// WRONG - creates new object each call, tests will fail!
global.document = {
  getElementById: () => ({ value: '', innerHTML: '' })
};
```

**CORRECT PATTERN (use this):**
```javascript
// CORRECT - returns same object for same ID
const mockElements = {
  'post-input': { value: '', innerHTML: '', textContent: '' },
  'posts': { innerHTML: '' },
  'user-info': { textContent: '' }
};
global.document = {
  getElementById: (id) => mockElements[id] || { value: '', innerHTML: '', textContent: '' }
};
```

**localStorage mock:**
```javascript
global.localStorage = {
  _data: {},
  setItem(key, value) { this._data[key] = String(value); },
  getItem(key) { return this._data[key] || null; },
  removeItem(key) { delete this._data[key]; },
  clear() { this._data = {}; }
};
```

=== COMPLETE TEST FILE TEMPLATE ===

CRITICAL TEST RULES:
1. **DUPLICATE all functions from HTML into test file** - cannot extract from HTML
2. **SET input BEFORE calling functions** that read from inputs
3. **RESET state before each test** - clear arrays, reset mock values
4. **Test pure logic FIRST** (arrays, objects) before DOM-dependent code
5. **Functions that clear inputs** - you MUST set input.value BEFORE calling again
6. **ONLY use getElementById** - querySelector, querySelectorAll are NOT mocked
7. **HTML inline event syntax:** `<input onkeypress="if(event.key==='Enter')myFunc()">`

```javascript
// tests/index.test.js
const assert = (condition, msg) => { if (!condition) throw new Error(msg); };

// === STATEFUL MOCKS ===
const mockElements = {
  'input': { value: '', innerHTML: '', textContent: '' },
  'list': { innerHTML: '', textContent: '' }
};
global.document = {
  getElementById: (id) => mockElements[id] || { value: '', innerHTML: '', textContent: '' }
};
global.localStorage = {
  _data: {},
  setItem(k, v) { this._data[k] = String(v); },
  getItem(k) { return this._data[k] || null; },
  clear() { this._data = {}; }
};

// === DUPLICATE FUNCTIONS FROM HTML (MANDATORY) ===
// Copy the EXACT functions from your HTML <script> tag here
// Tests run in Node.js - you CANNOT extract from HTML!

let items = [];

function addItem() {
  const input = document.getElementById('input');
  if (input.value.trim()) {
    items.push({ id: Date.now(), text: input.value.trim() });
    input.value = '';
    renderList();
  }
}

function renderList() {
  const list = document.getElementById('list');
  list.innerHTML = items.map(i => '<div>' + i.text + '</div>').join('');
}

// === HELPER: Reset state between tests ===
function resetState() {
  items = [];
  mockElements['input'].value = '';
  mockElements['list'].innerHTML = '';
  localStorage.clear();
}

// === TESTS ===

// Test 1: Pure array operations (no DOM needed)
resetState();
items.push({ id: 1, text: 'Test' });
assert(items.length === 1, 'Add to array failed');
items = items.filter(i => i.id !== 1);
assert(items.length === 0, 'Filter array failed');

// Test 2: addItem function
resetState();
mockElements['input'].value = 'Test Item';  // SET INPUT BEFORE calling
addItem();
assert(items.length === 1, 'addItem should add item');
assert(items[0].text === 'Test Item', 'Item text should match');
assert(mockElements['input'].value === '', 'Input should be cleared');

// Test 3: renderList function
resetState();
items = [{ id: 1, text: 'First' }, { id: 2, text: 'Second' }];
renderList();
assert(mockElements['list'].innerHTML.includes('First'), 'List should contain First');
assert(mockElements['list'].innerHTML.includes('Second'), 'List should contain Second');

// Test 4: localStorage
resetState();
localStorage.setItem('data', JSON.stringify([{id: 1}]));
const saved = JSON.parse(localStorage.getItem('data'));
assert(saved.length === 1, 'localStorage roundtrip failed');

console.log('All tests passed!');
```

**AVOID THIS BUG:**
```javascript
// WRONG - function clears input, second call has empty input!
mockElements['input'].value = 'First';
addItem();  // This may clear input.value = ''
items = []; // Reset array but forgot to reset input!
addItem();  // input.value is STILL empty, nothing added!
assert(items.length === 1, 'FAILS!');

// CORRECT - always set input before functions that read it
mockElements['input'].value = 'First';
addItem();
items = [];
mockElements['input'].value = 'Second';  // SET INPUT AGAIN!
addItem();
assert(items.length === 1, 'Works!');
```

=== AUDIT COMMANDS BY STACK ===

**JavaScript/Node.js:** "node tests/index.test.js"
**Python:** "python tests/test_app.py" or "python -m pytest tests/ -v"
**Static HTML:** "node tests/index.test.js" (for any embedded JS logic)

=== MULTI-LANGUAGE STACK SUPPORT ===

The "stack" field determines the runtime and audit approach:

**stack: "node"** (default, most common)
- Use for: Web apps, SPAs, dashboards, games, calculators
- Files: public/index.html, tests/index.test.js, vercel.json, package.json
- Audit: "node tests/index.test.js"
- Run: "npx serve public" or "npm start"

**stack: "python"** (for Python-heavy apps)
- Use for: Data tools, CLI apps, simple APIs
- Files: app.py, tests/test_app.py, requirements.txt, vercel.json
- Audit: "python tests/test_app.py"
- Run: "python app.py"

**For BOTH stacks:**
- Include public/index.html for UI (always needed!)
- Use localStorage for data persistence
- Tests MUST pass before deployment

=== STACK AUTO-SELECTION ===

Choose stack based on request:
- "website", "app", "dashboard", "game", "calculator" → node
- "data analysis", "script", "automation" → python
- When in doubt → node (broader browser support)

NEVER return just JSON APIs - always build COMPLETE web applications with beautiful UI and TESTS."""

# System prompt for architectural consultation
CONSULT_PROMPT = """You are the Gantry Chief Architect - an expert who builds REAL web applications.

YOUR ROLE:
1. Analyze user requests and suggest the best approach
2. For LARGER WEBSITES or DATABASE requests, always propose: "I'll build a lighter prototype first to ensure fast deployment. After it's live and working, you can add a real database step by step."
3. Emphasize resource efficiency: Build times are limited to 3 minutes, so we prototype first
3. Be confident, specific, and practical

PROTOTYPE-FIRST APPROACH:
- If user gives minimal details: Suggest 3-4 core features and offer to build prototype
- If user gives too many features: Prioritize top 3-4, build prototype, iterate later
- Always ask: "Should I build a working prototype with these core features first?"

WHAT YOU DELIVER:
- Real web apps with HTML/CSS/JavaScript
- Beautiful, modern UI with responsive design
- Unit tests with 90% coverage
- Deployed instantly to Vercel

RESUME/CONTINUE SUPPORT:
- If user mentions an existing app name or says "continue", "add to", "enhance"
- Ask for the project name or URL to identify the existing project
- Suggest enhancements based on the existing app

OUTPUT FORMAT (strict JSON, no markdown):
{
  "response": "PLAIN TEXT response",
  "ready_to_build": false,
  "suggested_stack": "node",
  "app_name": "AppName",
  "app_type": "Web App",
  "key_features": ["feature1", "feature2", "feature3"],
  "is_prototype": true,
  "continue_from": null
}

RULES:
- "response" must be PLAIN TEXT only
- If user confirms with "yes", "ok", "proceed", "build", "go" -> set ready_to_build: true
- If building prototype, set is_prototype: true
- If continuing existing app, set continue_from: "project_name" """

HEAL_PROMPT = """You are a PRINCIPAL ENGINEER and Senior Debugger for the Gantry Build System.
The previous build FAILED. Your job is to analyze and FIX it.

=== CRITICAL RULES ===
1. Output ONLY valid JSON - no markdown, no commentary
2. FIX the SPECIFIC error shown in the logs
3. Return ALL files, not just changed ones
4. Build REAL web apps with HTML/CSS/JS UI, not just APIs
5. TESTS MUST PASS - this is the most common failure point

=== SCHEMA ===
{
  "project_name": "string (keep same name)",
  "stack": "node",
  "files": [{"path": "path.ext", "content": "CORRECTED content"}],
  "audit_command": "command to verify",
  "run_command": "command to run"
}

=== ERROR-SPECIFIC FIXES ===

**DOM_MOCK_ERROR (querySelector not a function):**
- REPLACE: document.querySelector('x') → document.getElementById('x')
- ADD missing element to mockElements in test file
- NEVER use querySelector, querySelectorAll in tests

**DOM_MOCK_MISSING (cannot read property of null):**
- ADD the missing element ID to mockElements object:
  ```javascript
  const mockElements = {
    'missing-id': { value: '', innerHTML: '', textContent: '', style: {} }
  };
  ```

**EVENT_LISTENER_ERROR (addEventListener):**
- In HTML: Replace addEventListener with inline handlers
  BAD:  element.addEventListener('click', handler)
  GOOD: <button onclick="handler()">Click</button>

**REFERENCE_ERROR (function not defined):**
- DUPLICATE all functions from HTML into test file
- Tests run in Node.js, cannot extract from browser
- Define functions BEFORE calling them in tests

**TEST_FUNCTION_STUB_ERROR / EMPTY_STUB_ERROR (assertion fails because function doesn't modify state):**
- THIS IS THE #1 FAILURE CAUSE - AUTOMATIC BUILD REJECTION IF DETECTED
- NEVER create empty function stubs in tests
- WRONG: function searchWeather() { /* would update DOM */ }
- WRONG: function calculate() { // TODO implement }
- WRONG: function addItem() { }
- RIGHT: function searchWeather() { weatherInfo.style.display = 'block'; weatherInfo.innerHTML = '...'; }
- RIGHT: function calculate() { const a = parseFloat(input1.value); result.textContent = a + b; }
- If the test asserts something, the function MUST actually do it!
- COPY THE FULL IMPLEMENTATION from the HTML &lt;script&gt; tag into the test file

**SYNTAX_ERROR:**
- Check the EXACT line number in error
- Look for: missing brackets, quotes, semicolons, trailing commas
- Validate JSON structure (no trailing commas!)

**MODULE_NOT_FOUND:**
- Verify file path exists in manifest
- Check relative paths (./file vs ../file)
- Ensure package.json lists dependencies

**TEST_ASSERTION_FAILED:**
- Reset state between tests (items = [], mockElements cleared)
- Set input values BEFORE calling functions that read them
- Check test logic matches implementation

**VERCEL_STRUCTURE_ERROR:**
- Ensure public/index.html exists
- vercel.json must have correct rewrites
- api/index.js must use module.exports (not export default)

=== JAVASCRIPT TEST FILE TEMPLATE (use this!) ===

```javascript
const assert = (condition, msg) => { if (!condition) throw new Error(msg); };

// STATEFUL MOCKS - add ALL element IDs used in app
const mockElements = {
  'input': { value: '', innerHTML: '', textContent: '', style: {} },
  'output': { innerHTML: '', textContent: '', style: {} },
  'list': { innerHTML: '', textContent: '', style: {} }
};
global.document = {
  getElementById: (id) => mockElements[id] || { value: '', innerHTML: '', textContent: '', style: {} }
};
global.localStorage = {
  _data: {},
  setItem(k, v) { this._data[k] = String(v); },
  getItem(k) { return this._data[k] || null; },
  removeItem(k) { delete this._data[k]; },
  clear() { this._data = {}; }
};

// DUPLICATE ALL FUNCTIONS FROM HTML HERE - FULL IMPLEMENTATION!
// WRONG: function search() { /* would update display */ }  <-- NEVER DO THIS
// RIGHT: Copy the EXACT implementation that modifies DOM/state

let items = [];
function addItem() {
  const input = document.getElementById('input');
  if (input.value.trim()) {
    items.push(input.value.trim());  // Actually modify state
    input.value = '';
    render();
  }
}
function render() {
  document.getElementById('list').innerHTML = items.map(i => `<li>${i}</li>`).join('');
}
// If HTML has searchWeather(), copy the FULL implementation that sets display='block'

// RESET before each test
function resetState() {
  state = [];
  Object.keys(mockElements).forEach(k => {
    mockElements[k].value = '';
    mockElements[k].innerHTML = '';
  });
  localStorage.clear();
}

// TESTS
resetState();
mockElements['input'].value = 'test';  // SET BEFORE calling
myFunction();
assert(state.length === 1, 'Should work');

console.log('All tests passed!');
```

=== PYTHON TEST FILE TEMPLATE ===

```python
import sys
sys.path.insert(0, '.')

def test_basic():
    assert 1 + 1 == 2, "Math works"

def test_data():
    items = []
    items.append({"id": 1})
    assert len(items) == 1
    items = [i for i in items if i["id"] != 1]
    assert len(items) == 0

if __name__ == "__main__":
    test_basic()
    test_data()
    print("All tests passed!")
```

ALWAYS include public/index.html with real HTML/CSS/JS UI.
Return COMPLETE corrected manifest with ALL files."""


class ArchitectError(Exception):
    """Raised when the Architect fails to generate a valid manifest."""

    pass


class Architect:
    """
    The AI Brain that translates voice memos into Fabrication Instructions.

    Uses Bedrock API Key for authentication.
    """

    def __init__(self, api_key: str | None = None, region: str = BEDROCK_REGION) -> None:
        """
        Initialize the Bedrock client using API Key.

        Args:
            api_key: Bedrock API key. Defaults to BEDROCK_API_KEY env var.
            region: AWS region for Bedrock.

        Raises:
            ArchitectError: If API key is not provided.
        """
        self._api_key = api_key or os.getenv("BEDROCK_API_KEY")
        self._region = region
        self._endpoint = f"https://bedrock-runtime.{self._region}.amazonaws.com"

        if not self._api_key:
            console.print("[red][ARCHITECT] BEDROCK_API_KEY not found[/red]")
            raise ArchitectError("BEDROCK_API_KEY environment variable not set")

        console.print(f"[green][ARCHITECT] Brain online (region: {self._region})[/green]")

    def _clean_json(self, text: str) -> str:
        """
        Extract valid JSON from Claude's response.

        Why: Claude sometimes wraps JSON in markdown, adds commentary,
        or outputs JSON with literal control characters that need escaping.
        """
        # Find JSON object boundaries
        first_brace = text.find("{")
        last_brace = text.rfind("}")

        if first_brace == -1 or last_brace == -1 or first_brace >= last_brace:
            raise ArchitectError(f"No valid JSON in response: {text[:200]}...")

        json_str = text[first_brace : last_brace + 1]

        # Fix common LLM JSON errors (trailing commas)
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)

        # Try to parse, if it fails, attempt to fix control characters
        try:
            json.loads(json_str)  # Test parse
            return json_str
        except json.JSONDecodeError:
            # Escape unescaped control characters in string values
            # Replace literal newlines/tabs with escaped versions
            result = []
            in_string = False
            escape_next = False

            for char in json_str:
                if escape_next:
                    result.append(char)
                    escape_next = False
                elif char == "\\":
                    result.append(char)
                    escape_next = True
                elif char == '"':
                    result.append(char)
                    in_string = not in_string
                elif in_string and char == "\n":
                    result.append("\\n")
                elif in_string and char == "\r":
                    result.append("\\r")
                elif in_string and char == "\t":
                    result.append("\\t")
                else:
                    result.append(char)

            return "".join(result)

    def _load_design_image(self, mission_id: str | None) -> tuple[str | None, str | None]:
        """
        Load design reference image for a mission.

        Args:
            mission_id: The mission ID to look up.

        Returns:
            Tuple of (base64_data, media_type) or (None, None) if not found.
        """
        if not mission_id:
            return None, None

        mission_dir = MISSIONS_DIR / mission_id
        if not mission_dir.exists():
            return None, None

        # Look for design-reference.* files
        for ext in ("png", "jpg", "jpeg", "gif", "webp"):
            image_path = mission_dir / f"design-reference.{ext}"
            if image_path.exists():
                try:
                    image_data = image_path.read_bytes()
                    image_b64 = base64.b64encode(image_data).decode("utf-8")
                    media_type = f"image/{ext}" if ext != "jpg" else "image/jpeg"
                    console.print(
                        f"[cyan][ARCHITECT] Loaded design reference: {image_path.name}[/cyan]"
                    )
                    return image_b64, media_type
                except Exception as e:
                    console.print(f"[yellow][ARCHITECT] Failed to load design image: {e}[/yellow]")

        return None, None

    def _call_model_api(
        self,
        model_id: str,
        system_prompt: str,
        user_content: str | list,
        max_tokens: int = 4096,
        retry_count: int = 2,
    ) -> str:
        """
        Call a specific Claude model via Bedrock API with retry logic.

        Args:
            model_id: The Claude model ID to use.
            system_prompt: The system prompt.
            user_content: The user message (text or multimodal content).
            max_tokens: Maximum tokens to generate.
            retry_count: Number of retries on transient failures.

        Returns:
            Raw text response from the model.

        Raises:
            ArchitectError: If API call fails after all retries.
        """
        import time

        url = f"{self._endpoint}/model/{model_id}/invoke"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
        }

        last_error = None
        for attempt in range(retry_count + 1):
            try:
                # Exponential backoff on retries
                if attempt > 0:
                    wait_time = 2**attempt  # 2s, 4s, 8s...
                    console.print(
                        f"[yellow][ARCHITECT] Retry {attempt}/{retry_count} in {wait_time}s...[/yellow]"
                    )
                    time.sleep(wait_time)

                response = requests.post(url, headers=headers, json=body, timeout=120)

                # Handle rate limiting with retry
                if response.status_code == 429:
                    last_error = "Rate limited (429)"
                    console.print("[yellow][ARCHITECT] Rate limited, will retry...[/yellow]")
                    continue

                # Handle server errors with retry
                if response.status_code >= 500:
                    last_error = f"Server error ({response.status_code})"
                    console.print(f"[yellow][ARCHITECT] {last_error}, will retry...[/yellow]")
                    continue

                # Client errors are not retryable
                if response.status_code != 200:
                    raise ArchitectError(f"API error {response.status_code}: {response.text[:500]}")

                response_body = response.json()
                return response_body["content"][0]["text"]

            except requests.Timeout:
                last_error = "Request timeout"
                console.print("[yellow][ARCHITECT] Request timed out, will retry...[/yellow]")
                continue

            except requests.ConnectionError as e:
                last_error = f"Connection error: {e}"
                console.print(f"[yellow][ARCHITECT] {last_error}, will retry...[/yellow]")
                continue

        # All retries exhausted
        raise ArchitectError(f"API call failed after {retry_count + 1} attempts: {last_error}")

    def _pre_validate_manifest(self, manifest: GantryManifest) -> tuple[bool, str]:
        """
        Pre-validate manifest before returning to catch common issues.

        Returns:
            Tuple of (is_valid, error_message)
        """
        issues = []

        # Check for test file
        has_tests = any("test" in f.path.lower() for f in manifest.files)
        if not has_tests:
            issues.append("Missing test file (tests/index.test.js or tests/test_app.py)")

        # Check for main HTML file
        has_html = any(
            f.path.endswith(".html") and "index" in f.path.lower() for f in manifest.files
        )
        if not has_html and manifest.stack == "node":
            issues.append("Missing index.html (should be public/index.html)")

        # Check test file for forbidden patterns
        for file in manifest.files:
            if "test" in file.path.lower() and file.path.endswith(".js"):
                content = file.content

                # Check for querySelector (forbidden)
                if "querySelector" in content and "// FORBIDDEN" not in content:
                    issues.append(f"{file.path}: Uses querySelector (must use getElementById)")

                # Check for eval with querySelector
                if "eval(" in content and (
                    "querySelector" in content or "script" in content.lower()
                ):
                    issues.append(f"{file.path}: Uses eval to extract scripts (forbidden)")

                # Check for fs.readFileSync
                if "readFileSync" in content:
                    issues.append(f"{file.path}: Uses fs.readFileSync (forbidden in tests)")

                # Check for proper mocks
                if "document.getElementById" in content and "mockElements" not in content:
                    issues.append(f"{file.path}: Uses getElementById but no mockElements defined")

        # Check for vercel.json in node projects
        if manifest.stack == "node":
            has_vercel = any(f.path == "vercel.json" for f in manifest.files)
            if not has_vercel:
                issues.append("Missing vercel.json for Node.js project")

        if issues:
            return False, "; ".join(issues)
        return True, ""

    def draft_blueprint(
        self,
        prompt: str,
        design_target: str | None = None,
        mission_id: str | None = None,
    ) -> GantryManifest:
        """
        Draft Fabrication Instructions from a voice memo.

        3-Tier Model Architecture with automatic fallback.
        - Tier 1: Claude 4 Opus (most capable)
        - Tier 2: Claude 4 Sonnet (balanced)
        - Tier 3: Claude 3.5 Sonnet (battle-tested)

        Simple apps should NEVER fail. Complex apps get 3 chances.

        Args:
            prompt: The user's voice memo / build request.
            design_target: Optional famous app to clone (LINKEDIN, TWITTER, etc.)
            mission_id: Optional mission ID to load design reference image from.

        Returns:
            A validated GantryManifest ready for the Foundry.

        Raises:
            ArchitectError: If ALL model tiers fail.
        """
        # Auto-detect design target if not provided
        if not design_target:
            design_target = detect_design_target(prompt)

        console.print(f"[cyan][ARCHITECT] Drafting blueprint: {prompt[:50]}...[/cyan]")
        if design_target:
            console.print(f"[cyan][ARCHITECT] Clone protocol: {design_target}[/cyan]")

        # Load design reference image if available
        image_b64, media_type = self._load_design_image(mission_id)
        has_mockup = image_b64 is not None

        if has_mockup:
            console.print("[cyan][ARCHITECT] Vision mode: 95% mockup matching enabled[/cyan]")

        # Inject design theme into system prompt
        system_prompt = SYSTEM_PROMPT
        if design_target:
            theme_prompt = get_theme_prompt(design_target)
            system_prompt = SYSTEM_PROMPT + theme_prompt

        # Build multimodal content if image is provided
        if has_mockup:
            user_content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": f"""DESIGN MOCKUP PROVIDED - MATCH THIS AT 95% ACCURACY!

The image above is the user's design mockup/screenshot/sketch. Your generated UI MUST match it as closely as possible (95% visual fidelity target).

Analyze the image carefully:
- Layout structure (columns, rows, spacing)
- Color scheme (exact hex values)
- Typography (sizes, weights, fonts)
- Component styles (buttons, inputs, cards)
- Spacing and padding patterns
- Shadows and borders

User request: {prompt}

Generate a GantryManifest that replicates this design with 95% accuracy. Include a README.md that references the design mockup.""",
                },
            ]
        else:
            user_content = prompt

        # =====================================================================
        # 3-TIER MODEL FALLBACK ARCHITECTURE
        # =====================================================================
        # Try each tier until we get a valid manifest. This ensures:
        # - Simple apps NEVER fail (try 3 models before giving up)
        # - Complex apps get the best model first, then fallback
        # - We maximize success rate beyond competitors
        # =====================================================================

        last_error = None
        tiers_to_try = MODEL_TIERS if ENABLE_MODEL_FALLBACK else [MODEL_TIERS[0]]

        for tier_idx, tier in enumerate(tiers_to_try):
            model_id = tier["id"]
            model_name = tier["name"]
            max_tokens = tier["max_tokens"]

            console.print(
                f"[cyan][ARCHITECT] Tier {tier_idx + 1}/{len(tiers_to_try)}: {model_name}[/cyan]"
            )

            try:
                raw_text = self._call_model_api(
                    model_id=model_id,
                    system_prompt=system_prompt,
                    user_content=user_content,
                    max_tokens=max_tokens,
                )

                console.print("[cyan][ARCHITECT] Response received, parsing...[/cyan]")

                # Parse and validate the response
                clean_json = self._clean_json(raw_text)
                manifest_data = json.loads(clean_json)
                manifest = GantryManifest(**manifest_data)

                # Pre-validate manifest to catch common issues early
                is_valid, validation_error = self._pre_validate_manifest(manifest)
                if not is_valid:
                    console.print(
                        f"[yellow][ARCHITECT] Pre-validation failed: {validation_error}[/yellow]"
                    )
                    # Don't fail - try to fix in next tier or let build self-heal
                    # But log it for visibility

                console.print(
                    f"[green][ARCHITECT] Blueprint ready: {manifest.project_name} "
                    f"(via {model_name})[/green]"
                )
                return manifest

            except requests.RequestException as e:
                last_error = f"Network error with {model_name}: {e}"
                console.print(f"[yellow][ARCHITECT] {last_error}[/yellow]")

            except json.JSONDecodeError as e:
                last_error = f"JSON parse failed with {model_name}: {e}"
                console.print(f"[yellow][ARCHITECT] {last_error}[/yellow]")

            except ValidationError as e:
                last_error = f"Manifest validation failed with {model_name}: {e}"
                console.print(f"[yellow][ARCHITECT] {last_error}[/yellow]")

            except ArchitectError as e:
                last_error = f"API error with {model_name}: {e}"
                console.print(f"[yellow][ARCHITECT] {last_error}[/yellow]")

            except Exception as e:
                last_error = f"Unexpected error with {model_name}: {e}"
                console.print(f"[yellow][ARCHITECT] {last_error}[/yellow]")

            # If this tier failed, try the next one
            if tier_idx < len(tiers_to_try) - 1:
                console.print(
                    f"[yellow][ARCHITECT] Falling back to Tier {tier_idx + 2}...[/yellow]"
                )

        # All tiers failed
        console.print("[red][ARCHITECT] All model tiers exhausted[/red]")
        raise ArchitectError(
            f"All {len(tiers_to_try)} model tiers failed. Last error: {last_error}"
        )

    def heal_blueprint(self, original_manifest: GantryManifest, error_log: str) -> GantryManifest:
        """
        Self-Healing: Analyze error and generate a fixed manifest.

        This is the "Repair" skill that makes Gantry agentic.
        When a build fails, the Architect reads the error and fixes the code.
        Uses 3-tier model fallback for maximum success rate.

        Args:
            original_manifest: The manifest that failed.
            error_log: The error output from the failed audit.

        Returns:
            A new, corrected GantryManifest.

        Raises:
            ArchitectError: If ALL healing attempts fail.
        """
        console.print("[yellow][ARCHITECT] Self-healing: analyzing failure...[/yellow]")

        # Analyze error type to provide better context
        error_analysis = self._analyze_error(error_log)
        console.print(f"[cyan][ARCHITECT] Error type: {error_analysis['type']}[/cyan]")

        # Build the healing prompt with context and specific fix guidance
        healing_request = f"""## FAILED BUILD - NEEDS FIX

### Error Analysis:
- Error Type: {error_analysis["type"]}
- Likely Cause: {error_analysis["cause"]}
- Suggested Fix: {error_analysis["fix"]}

### Original Manifest:
```json
{json.dumps(original_manifest.model_dump(), indent=2)}
```

### Error Log:
```
{error_log[:3000]}
```

CRITICAL REQUIREMENTS FOR FIX:
1. Fix the SPECIFIC error shown above
2. Return ALL files (not just changed ones)
3. TESTS MUST PASS - this is usually why builds fail:
   - Functions in test file must have FULL implementation (not empty stubs)
   - If test asserts "display === 'block'", the function MUST set display to 'block'
   - NEVER write empty stubs like: function foo() followed by a comment
   - ALWAYS write the full implementation that modifies the DOM/state
4. If DOM error: only use getElementById (NOT querySelector)
5. If import error: check file paths and module format
6. If assertion error: the function being tested isn't actually doing what the test expects

Analyze the error and return a CORRECTED GantryManifest that fixes this issue."""

        # =====================================================================
        # 3-TIER HEALING FALLBACK (same as draft_blueprint)
        # =====================================================================
        last_error = None
        tiers_to_try = MODEL_TIERS if ENABLE_MODEL_FALLBACK else [MODEL_TIERS[0]]

        for tier_idx, tier in enumerate(tiers_to_try):
            model_id = tier["id"]
            model_name = tier["name"]
            max_tokens = tier["max_tokens"]

            console.print(
                f"[yellow][ARCHITECT] Healing Tier {tier_idx + 1}/{len(tiers_to_try)}: {model_name}[/yellow]"
            )

            try:
                raw_text = self._call_model_api(
                    model_id=model_id,
                    system_prompt=HEAL_PROMPT,
                    user_content=healing_request,
                    max_tokens=max_tokens,
                )

                console.print("[cyan][ARCHITECT] Healing response received, parsing...[/cyan]")

                # Parse and validate the response
                clean_json = self._clean_json(raw_text)
                manifest_data = json.loads(clean_json)
                healed_manifest = GantryManifest(**manifest_data)

                # Validate the healed manifest has required fixes
                if self._validate_healed_manifest(healed_manifest, error_analysis):
                    console.print(
                        f"[green][ARCHITECT] Healed blueprint ready: {healed_manifest.project_name} "
                        f"(via {model_name})[/green]"
                    )
                    return healed_manifest
                else:
                    last_error = "Healed manifest didn't address the error properly"
                    console.print(f"[yellow][ARCHITECT] {last_error}[/yellow]")

            except requests.RequestException as e:
                last_error = f"Network error with {model_name}: {e}"
                console.print(f"[yellow][ARCHITECT] {last_error}[/yellow]")

            except json.JSONDecodeError as e:
                last_error = f"JSON parse failed with {model_name}: {e}"
                console.print(f"[yellow][ARCHITECT] {last_error}[/yellow]")

            except ValidationError as e:
                last_error = f"Manifest validation failed with {model_name}: {e}"
                console.print(f"[yellow][ARCHITECT] {last_error}[/yellow]")

            except ArchitectError as e:
                last_error = f"API error with {model_name}: {e}"
                console.print(f"[yellow][ARCHITECT] {last_error}[/yellow]")

            except Exception as e:
                last_error = f"Unexpected error with {model_name}: {e}"
                console.print(f"[yellow][ARCHITECT] {last_error}[/yellow]")

            # If this tier failed, try the next one
            if tier_idx < len(tiers_to_try) - 1:
                console.print(
                    f"[yellow][ARCHITECT] Healing fallback to Tier {tier_idx + 2}...[/yellow]"
                )

        # All tiers failed
        console.print("[red][ARCHITECT] All healing tiers exhausted[/red]")
        raise ArchitectError(
            f"All {len(tiers_to_try)} healing tiers failed. Last error: {last_error}"
        )

    def _analyze_error(self, error_log: str) -> dict:
        """
        Analyze error log to determine error type and suggest fixes.

        This helps the LLM focus on the right solution.
        """
        error_lower = error_log.lower()

        # Error patterns mapped to their analysis
        error_patterns = [
            # DOM/Browser errors
            (
                lambda e: "queryselector" in e and "not a function" in e,
                {
                    "type": "DOM_MOCK_ERROR",
                    "cause": "Test uses document.querySelector which is not mocked",
                    "fix": "Replace querySelector with getElementById, add element to mockElements",
                },
            ),
            (
                lambda e: "getelementbyid" in e and ("null" in e or "undefined" in e),
                {
                    "type": "DOM_MOCK_MISSING",
                    "cause": "Element ID not found in mockElements",
                    "fix": "Add missing element ID to mockElements object in test file",
                },
            ),
            (
                lambda e: "addeventlistener" in e,
                {
                    "type": "EVENT_LISTENER_ERROR",
                    "cause": "Using addEventListener which is not mocked",
                    "fix": "Replace addEventListener with inline handlers (onclick, onkeypress)",
                },
            ),
            # Syntax errors
            (
                lambda e: "syntaxerror" in e or "unexpected token" in e,
                {
                    "type": "SYNTAX_ERROR",
                    "cause": "Invalid JavaScript/Python syntax",
                    "fix": "Check for missing brackets, quotes, semicolons at indicated line",
                },
            ),
            # Module/Import errors
            (
                lambda e: "module not found" in e or "cannot find module" in e,
                {
                    "type": "MODULE_NOT_FOUND",
                    "cause": "Required module/file doesn't exist",
                    "fix": "Check file paths, ensure all required files are generated",
                },
            ),
            (
                lambda e: "modulenotfounderror" in e or "no module named" in e,
                {
                    "type": "PYTHON_IMPORT_ERROR",
                    "cause": "Python module not found",
                    "fix": "Check sys.path, ensure module exists, use relative imports",
                },
            ),
            # Reference errors
            (
                lambda e: "referenceerror" in e or "is not defined" in e,
                {
                    "type": "REFERENCE_ERROR",
                    "cause": "Variable or function used before definition",
                    "fix": "Ensure functions are defined before use, duplicate from HTML to test",
                },
            ),
            # Type errors
            (
                lambda e: "typeerror" in e,
                {
                    "type": "TYPE_ERROR",
                    "cause": "Operation on wrong type (e.g., calling non-function)",
                    "fix": "Check variable types, ensure mocks return correct types",
                },
            ),
            # Assertion failures - check if it's a stub issue
            (
                lambda e: ("assertionerror" in e or "assert" in e)
                and ("display" in e or "innerhtml" in e or "textcontent" in e),
                {
                    "type": "EMPTY_STUB_ERROR",
                    "cause": "Test function is an empty stub that doesn't modify DOM",
                    "fix": "Function MUST have FULL implementation - copy exact code from HTML script",
                },
            ),
            (
                lambda e: "assertionerror" in e or "assert" in e,
                {
                    "type": "TEST_ASSERTION_FAILED",
                    "cause": "Test assertion did not pass",
                    "fix": "Ensure functions actually modify state/DOM, not empty stubs",
                },
            ),
            # Vercel structure errors
            (
                lambda e: "invalid vercel" in e or "structure" in e,
                {
                    "type": "VERCEL_STRUCTURE_ERROR",
                    "cause": "Invalid Vercel deployment structure",
                    "fix": "Ensure public/index.html exists, vercel.json is correct",
                },
            ),
        ]

        # Find first matching pattern
        for matcher, result in error_patterns:
            if matcher(error_lower):
                return result

        # Default if no pattern matches
        return {
            "type": "UNKNOWN_ERROR",
            "cause": "Unrecognized error pattern",
            "fix": "Review error log carefully and fix the specific issue",
        }

    def _validate_healed_manifest(self, manifest: GantryManifest, error_analysis: dict) -> bool:
        """
        Validate that the healed manifest likely addresses the error.

        Returns True if manifest looks correct, False if obvious issues remain.
        """
        # Check for common issues based on error type
        if error_analysis["type"] == "DOM_MOCK_ERROR":
            # Ensure no querySelector in test files
            for file in manifest.files:
                if "test" in file.path.lower() and "querySelector" in file.content:
                    console.print(
                        "[yellow][ARCHITECT] Healed manifest still has querySelector[/yellow]"
                    )
                    return False

        if error_analysis["type"] == "VERCEL_STRUCTURE_ERROR":
            # Ensure public/index.html exists
            has_index = any(f.path in ("public/index.html", "index.html") for f in manifest.files)
            if not has_index:
                console.print("[yellow][ARCHITECT] Healed manifest missing index.html[/yellow]")
                return False

        # CRITICAL: Detect empty function stubs in test files
        # This is the #1 cause of test failures!
        empty_stub_patterns = [
            "/* would",
            "// would",
            "/* TODO",
            "// TODO",
            "{ }",
            "{}",
            "pass  #",
            "pass #",
        ]
        for file in manifest.files:
            if "test" in file.path.lower():
                content = file.content
                # Check for suspicious empty function bodies
                for pattern in empty_stub_patterns:
                    if pattern in content:
                        console.print(
                            f"[yellow][ARCHITECT] Warning: Test file may have empty stub ({pattern})[/yellow]"
                        )
                        # Don't fail, just warn - sometimes these are in comments

                # More aggressive check: function with only comment inside
                import re

                empty_func_pattern = (
                    r"function\s+\w+\s*\([^)]*\)\s*\{\s*(//[^\n]*|/\*[^*]*\*/)\s*\}"
                )
                if re.search(empty_func_pattern, content):
                    console.print(
                        "[red][ARCHITECT] CRITICAL: Test has empty function stub with only comment![/red]"
                    )
                    return False

        # Basic validation - ensure tests file exists
        has_tests = any("test" in f.path.lower() for f in manifest.files)
        if not has_tests:
            console.print("[yellow][ARCHITECT] Healed manifest missing test file[/yellow]")
        return has_tests

    def consult(self, messages: list[dict]) -> dict:
        """
        Architectural consultation - have a conversation about the project.

        This is the "Critic" skill that reviews requirements before building.
        The Architect answers questions about scalability, testing, security, etc.

        Args:
            messages: Conversation history [{"role": "user"|"assistant", "content": "..."}]

        Returns:
            dict with response, ready_to_build, suggested_stack, etc.
        """
        console.print("[cyan][ARCHITECT] Consulting on architecture...[/cyan]")

        url = f"{self._endpoint}/model/{CLAUDE_MODEL_ID}/invoke"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "system": CONSULT_PROMPT,
            "messages": messages,
        }

        try:
            response = requests.post(url, headers=headers, json=body, timeout=30)

            if response.status_code != 200:
                console.print(f"[red][ARCHITECT] Consult API error: {response.status_code}[/red]")
                return {
                    "response": "I'm having trouble connecting. Please try again.",
                    "ready_to_build": False,
                }

            response_body = response.json()
            raw_text = response_body["content"][0]["text"]

            # Try to parse as JSON
            try:
                clean_json = self._clean_json(raw_text)
                result = json.loads(clean_json)

                # Handle case where Claude double-encoded JSON in the response field
                resp_field = result.get("response", "")
                if isinstance(resp_field, str) and resp_field.strip().startswith("{"):
                    console.print("[cyan][ARCHITECT] Detected nested JSON, extracting...[/cyan]")
                    try:
                        inner = json.loads(resp_field)
                        if isinstance(inner, dict) and "response" in inner:
                            result = inner  # Use the inner JSON
                            console.print(
                                "[green][ARCHITECT] Successfully extracted inner JSON[/green]"
                            )
                    except json.JSONDecodeError as e:
                        console.print(f"[yellow][ARCHITECT] Inner JSON parse failed: {e}[/yellow]")

                console.print(
                    f"[green][ARCHITECT] Consultation complete (ready: {result.get('ready_to_build', False)})[/green]"
                )
                return result
            except (json.JSONDecodeError, ArchitectError) as e:
                console.print(
                    f"[yellow][ARCHITECT] JSON parse failed: {e}, returning raw text[/yellow]"
                )
                return {"response": raw_text, "ready_to_build": False}

        except requests.RequestException as e:
            console.print(f"[red][ARCHITECT] Consult request failed: {e}[/red]")
            return {"response": f"Connection error: {e}", "ready_to_build": False}
