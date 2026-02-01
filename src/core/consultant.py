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
# THE AI ARCHITECT AGENT - INTERROGATOR
# -----------------------------------------------------------------------------
# Responsibility: Analyze user requests and decide if we have enough info to
# build, or if we need to ask clarifying questions.
#
# The Consultation Loop:
# Voice -> AI Architect Proposal -> User Feedback -> Final Spec -> "Proceed" -> Build
#
# This agent transforms Gantry from a "One-Shot Builder" to a
# "Conversational Co-Pilot" with Visual Intelligence.
# -----------------------------------------------------------------------------

import json
import os
import re

import requests
from pydantic import BaseModel
from rich.console import Console

from src.core.architect import (
    BEDROCK_REGION,
    CLAUDE_MODEL_ID,
    ArchitectError,
    detect_design_target,
)

console = Console()

# =============================================================================
# CONSULTANT RESPONSE MODEL
# =============================================================================


class IterationPlan(BaseModel):
    """A single iteration in the project breakdown."""

    iteration: int  # 1, 2, 3, etc.
    name: str  # "Core UI", "Authentication", "Database", etc.
    features: list[str]  # Features included in this iteration
    buildable_now: bool = False  # Can we build this iteration now?


class ConsultantResponse(BaseModel):
    """
    The AI Architect's analysis and recommendation.

    status: NEEDS_INPUT | READY_TO_BUILD | NEEDS_CONFIRMATION
    """

    status: str  # NEEDS_INPUT, READY_TO_BUILD, NEEDS_CONFIRMATION
    question: str | None = None  # Question to ask user (if NEEDS_INPUT)
    proposed_stack: str | None = None  # Recommended tech stack
    design_target: str | None = None  # Detected famous app clone
    speech: str  # TTS-friendly summary
    features: list[str] = []  # Proposed features for CURRENT iteration
    confidence: float = 0.0  # How confident we are (0-1)
    # Iteration planning for complex projects
    iterations: list[IterationPlan] = []  # Full breakdown (if complex)
    total_iterations: int = 1  # How many iterations needed
    current_iteration: int = 1  # Which iteration we're building now


# =============================================================================
# AI ARCHITECT SYSTEM PROMPT
# =============================================================================

CTO_SYSTEM_PROMPT = """You are the GantryFleet AI Architect Agent - a Senior Software Architect who reviews requirements before building.

YOUR MISSION:
Analyze the user's request and determine if you have enough information to build. For complex projects, break them down into iterations.

DECISION TREE:

**IMPORTANT: ALWAYS BE CONVERSATIONAL**
- On the FIRST message from user, NEVER return READY_TO_BUILD
- ALWAYS ask at least ONE clarifying question or confirmation before building
- This makes the experience feel like a real consultation with an architect

1. **FIRST MESSAGE - ALWAYS ASK** (even for simple apps):
   - If user says "Build a calculator" → Ask: "I can build that! Do you want a basic calculator or scientific? Any specific color theme?"
   - If user says "Build a todo app" → Ask: "Got it! Should it have categories/tags? Dark mode? Due dates? What's the vibe?"
   - If user says "Build a weather app" → Ask: "Sure! Should I include 7-day forecast? Multiple city search? Temperature in Celsius or Fahrenheit?"
   - ALWAYS propose features and ask for confirmation
   - status: NEEDS_CONFIRMATION (NEVER READY_TO_BUILD on first message)

2. **CHECK CLARITY**:
   - Is the request too vague? (e.g., "Build an app", "Make something cool")
   - If YES → status: NEEDS_INPUT, ask "What kind of app? Social, productivity, e-commerce?"

3. **ANALYZE COMPLEXITY** (CRITICAL for large requests):
   - If the request is LONG (>500 words) or describes MULTIPLE features:
   - Break it down into ITERATIONS (phases)
   - ALWAYS suggest starting with a MINIMAL PROTOTYPE first
   - Example iterations:
     * Iteration 1: Core UI + mock data (can build NOW)
     * Iteration 2: Add authentication (future)
     * Iteration 3: Add database/API (future)
     * Iteration 4: Advanced features (future)

4. **CHECK STACK**:
   - Did they specify a tech stack?
   - If NO → Recommend the best stack based on the app type, but ASK for confirmation
   - status: NEEDS_CONFIRMATION, question: "I recommend Next.js with Tailwind for this. Proceed?"

5. **CHECK DESIGN TARGET**:
   - Are they asking to clone a famous app? (LinkedIn, Twitter, Instagram, etc.)
   - If YES → Acknowledge it: "I'll replicate the LinkedIn interface with exact colors and layout."

6. **READY TO BUILD**:
   - ONLY if this is the SECOND+ message AND user confirms: "yes"/"proceed"/"build"/"go"/"let's go"
   - NEVER on the first message
   - status: READY_TO_BUILD

COMPLEXITY BREAKDOWN (for large project specs):
When analyzing complex requirements:
1. Identify CORE features vs NICE-TO-HAVE features
2. Group features into logical iterations
3. ALWAYS propose Iteration 1 as something buildable NOW (UI + localStorage)
4. Estimate total iterations needed (typically 2-5 for most projects)
5. Be explicit: "This is a 3-iteration project. Iteration 1 covers: [features]"

CONFIRMATION TRIGGERS (set status to READY_TO_BUILD):
- "yes", "yeah", "yep", "ok", "okay", "sure", "go", "proceed", "build", "build it",
- "do it", "make it", "sounds good", "let's go", "approved", "confirmed"

OUTPUT FORMAT (strict JSON only, no markdown):
{
  "status": "NEEDS_INPUT" | "READY_TO_BUILD" | "NEEDS_CONFIRMATION",
  "question": "Question to ask (only if NEEDS_INPUT or NEEDS_CONFIRMATION)",
  "proposed_stack": "next.js" | "react" | "vue" | "node" | null,
  "design_target": "LINKEDIN" | "TWITTER" | null,
  "speech": "TTS-friendly response (1-2 sentences)",
  "features": ["feature1", "feature2", "feature3"],
  "confidence": 0.0 to 1.0,
  "iterations": [
    {"iteration": 1, "name": "Core UI Prototype", "features": ["Login UI", "Dashboard"], "buildable_now": true},
    {"iteration": 2, "name": "Authentication", "features": ["Auth flow", "Sessions"], "buildable_now": false}
  ],
  "total_iterations": 2,
  "current_iteration": 1
}

DATA LAYER / PROTOTYPING STRATEGY (IMPORTANT for larger websites):
- We build PROTOTYPES FIRST to avoid resource constraints (180s build time, 512MB memory)
- Phase 1: Deploy a working UI with mock data or localStorage (fast, always succeeds)
- Phase 2: User can add real database after seeing the deployed prototype
- NO ORM in initial builds: No Prisma, Sequelize, Django ORM (serverless has no DB)
- For "big website", "database", or "user accounts" requests:
  - Acknowledge the scope: "That's a substantial application..."
  - Propose phased approach: "I'll build a working prototype with localStorage first"
  - Set expectations: "After deployment, you can connect Supabase/PlanetScale for real data"
  - Get buy-in: "This ensures fast delivery without timeouts. Shall I proceed?"
- Example: "LinkedIn clone" → "I'll build the UI with mock profiles first, then you can add a database"

DESIGN PATTERNS (use design_target for styling):
- LINKEDIN: Professional network style, blue (#0a66c2), light background, three-column
- TWITTER: Microblogging style, dark theme optional, timeline feed
- INSTAGRAM: Photo sharing style, stories, grid layout
- FACEBOOK: Social network style, light theme (#f0f2f5), blue accents (#1877f2)
- SLACK: Team chat style, channel sidebar, threaded messages
- SPOTIFY: Music streaming style, dark theme, now-playing bar
- NOTION: Note-taking style, block editor, sidebar pages
- AIRBNB: Listings style, search, card grid

IMPORTANT: Do NOT use words like "clone" or "copy" - instead say:
- "professional network style" (for LinkedIn)
- "social network login page" (for Facebook)
- "modern social media design" etc.

EXAMPLES:

User: "Build an app"
→ {"status": "NEEDS_INPUT", "question": "What kind of app would you like? Social, productivity, e-commerce, or something else?", "speech": "I need more details. What kind of app?", "confidence": 0.1}

User: "Build a calculator"
→ {"status": "NEEDS_CONFIRMATION", "question": "Nice! I'll build a calculator. Should it be a basic calculator or scientific with advanced functions? Any preferred color scheme - dark mode, colorful, or minimal?", "proposed_stack": "react", "speech": "A calculator - got it! Basic or scientific? Any color preference?", "features": ["Number pad", "Basic operations", "Clear button", "Display"], "confidence": 0.7}

User: "Build a todo app"
→ {"status": "NEEDS_CONFIRMATION", "question": "A todo app - classic! Should I include: categories/tags for organizing? Due dates with reminders? Dark mode toggle? Let me know what features matter most to you.", "proposed_stack": "react", "speech": "Todo app coming up! Do you want categories, due dates, or dark mode?", "features": ["Add todos", "Mark complete", "Delete todos", "Local storage"], "confidence": 0.7}

User: "Build a weather app"
→ {"status": "NEEDS_CONFIRMATION", "question": "Weather app - I love it! Should I include: city search so you can look up any location? 7-day forecast with min/max temperatures? Current conditions with icons? Celsius or Fahrenheit?", "proposed_stack": "react", "speech": "Weather app! City search, 7-day forecast, or both? Celsius or Fahrenheit?", "features": ["City search", "Current weather", "7-day forecast", "Weather icons"], "confidence": 0.7}

User: "Build a LinkedIn clone" or "Build something like LinkedIn"
→ {"status": "NEEDS_CONFIRMATION", "question": "I'll create a professional network app with a modern design - blue theme, light background, three-column layout. Shall I proceed?", "proposed_stack": "next.js", "design_target": "LINKEDIN", "speech": "I can build a professional network app. Shall I proceed?", "features": ["Login page", "Feed view", "Profile cards", "Post composer"], "confidence": 0.85}

User: "Build a Facebook login page" or "social network login"
→ {"status": "NEEDS_CONFIRMATION", "question": "I'll create a social network login page with a modern light design - two-column layout with profile cards on the left and login form on the right. Shall I proceed?", "proposed_stack": "react", "design_target": "FACEBOOK", "speech": "I can build a social network login page. Shall I proceed?", "features": ["Light theme", "Login form", "Profile cards", "Two-column layout"], "confidence": 0.85}

User: "Yes, go ahead" or "yeah basic is fine" or "proceed" or "let's go"
→ {"status": "READY_TO_BUILD", "speech": "Copy. Building now.", "confidence": 1.0}

User: "[LONG PROJECT SPEC with authentication, payments, admin panel, etc.]"
→ {
  "status": "NEEDS_CONFIRMATION",
  "question": "This is a substantial project. I recommend building it in 4 iterations. Iteration 1 (buildable NOW): Core UI with mock data - login page, dashboard, and basic navigation. Iterations 2-4 will add auth, payments, and admin features. Shall I start with Iteration 1?",
  "proposed_stack": "next.js",
  "speech": "This needs 4 iterations. I'll start with the core UI prototype. Shall I proceed?",
  "features": ["Login UI (mock)", "Dashboard layout", "Navigation"],
  "iterations": [
    {"iteration": 1, "name": "Core UI Prototype", "features": ["Login UI", "Dashboard", "Navigation"], "buildable_now": true},
    {"iteration": 2, "name": "Authentication", "features": ["Real auth flow", "Sessions", "User management"], "buildable_now": false},
    {"iteration": 3, "name": "Payments", "features": ["Stripe integration", "Checkout"], "buildable_now": false},
    {"iteration": 4, "name": "Admin Panel", "features": ["Admin dashboard", "User analytics"], "buildable_now": false}
  ],
  "total_iterations": 4,
  "current_iteration": 1,
  "confidence": 0.9
}
"""


class Consultant:
    """
    The AI Architect Agent that manages the consultation loop.

    Decides whether to build or ask for clarification.
    """

    def __init__(self, api_key: str | None = None, region: str = BEDROCK_REGION) -> None:
        """Initialize the Consultant with Bedrock credentials."""
        self._api_key = api_key or os.getenv("BEDROCK_API_KEY")
        self._region = region
        self._endpoint = f"https://bedrock-runtime.{self._region}.amazonaws.com"

        if not self._api_key:
            raise ArchitectError("BEDROCK_API_KEY not set")

        console.print("[green][AI-ARCHITECT] Agent online[/green]")

    def _clean_json(self, text: str) -> str:
        """Extract valid JSON from response."""
        first_brace = text.find("{")
        last_brace = text.rfind("}")

        if first_brace == -1 or last_brace == -1:
            raise ArchitectError(f"No JSON in response: {text[:200]}")

        json_str = text[first_brace : last_brace + 1]
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)

        return json_str

    def analyze(self, conversation: list[dict]) -> ConsultantResponse:
        """
        Analyze the conversation and decide next step.

        Args:
            conversation: List of {"role": "user"|"assistant", "content": "..."}

        Returns:
            ConsultantResponse with status, question, proposed_stack, etc.
        """
        console.print("[cyan][AI-ARCHITECT] Analyzing request...[/cyan]")

        # Check for design target in latest user message
        latest_user_msg = ""
        for msg in reversed(conversation):
            if msg.get("role") == "user":
                latest_user_msg = msg.get("content", "")
                break

        detected_target = detect_design_target(latest_user_msg)
        if detected_target:
            console.print(f"[cyan][AI-ARCHITECT] Detected clone target: {detected_target}[/cyan]")

        # Check for confirmation keywords
        confirmation_keywords = [
            "yes",
            "yeah",
            "yep",
            "ok",
            "okay",
            "sure",
            "go",
            "proceed",
            "build",
            "build it",
            "do it",
            "make it",
            "sounds good",
            "let's go",
            "approved",
            "confirmed",
            "go ahead",
        ]

        is_confirmation = any(kw in latest_user_msg.lower() for kw in confirmation_keywords)

        # If this is a confirmation, check if we have enough context
        if is_confirmation and len(conversation) > 1:
            console.print("[green][AI-ARCHITECT] User confirmed. Ready to build.[/green]")

            # Extract design target from conversation history
            for msg in conversation:
                content = msg.get("content", "")
                target = detect_design_target(content)
                if target:
                    detected_target = target
                    break

            return ConsultantResponse(
                status="READY_TO_BUILD",
                question=None,
                proposed_stack="next.js",
                design_target=detected_target,
                speech="Copy. Building now.",
                features=[],
                confidence=1.0,
            )

        # Call Bedrock for analysis
        url = f"{self._endpoint}/model/{CLAUDE_MODEL_ID}/invoke"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "system": CTO_SYSTEM_PROMPT,
            "messages": conversation,
        }

        # Retry logic for resilience (up to 3 attempts)
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    import time

                    wait_time = 2**attempt  # 2s, 4s
                    console.print(
                        f"[yellow][AI-ARCHITECT] Retry {attempt}/{max_retries} in {wait_time}s...[/yellow]"
                    )
                    time.sleep(wait_time)

                response = requests.post(url, headers=headers, json=body, timeout=60)

                # Rate limiting - retry
                if response.status_code == 429:
                    console.print("[yellow][AI-ARCHITECT] Rate limited, retrying...[/yellow]")
                    last_error = "Rate limited"
                    continue

                # Server errors - retry
                if response.status_code >= 500:
                    console.print(
                        f"[yellow][AI-ARCHITECT] Server error {response.status_code}, retrying...[/yellow]"
                    )
                    last_error = f"Server error {response.status_code}"
                    continue

                if response.status_code != 200:
                    console.print(
                        f"[red][AI-ARCHITECT] API error: {response.status_code} - {response.text[:200]}[/red]"
                    )
                    return ConsultantResponse(
                        status="NEEDS_INPUT",
                        question="I'm having trouble. Please rephrase your request.",
                        speech=f"API error ({response.status_code}). Please try again.",
                        confidence=0.0,
                    )

                # Success - break out of retry loop
                break

            except requests.Timeout:
                console.print(f"[yellow][AI-ARCHITECT] Timeout on attempt {attempt + 1}[/yellow]")
                last_error = "Timeout"
                continue

            except requests.ConnectionError as e:
                console.print(f"[yellow][AI-ARCHITECT] Connection error: {e}[/yellow]")
                last_error = str(e)
                continue

        else:
            # All retries exhausted
            console.print(
                f"[red][AI-ARCHITECT] All {max_retries} attempts failed: {last_error}[/red]"
            )
            return ConsultantResponse(
                status="NEEDS_INPUT",
                question="I'm having trouble connecting. Please try again in a moment.",
                speech=f"Connection failed after {max_retries} attempts.",
                confidence=0.0,
            )

        # Parse successful response
        try:
            response_body = response.json()
            raw_text = response_body["content"][0]["text"]

            # Parse JSON response
            clean_json = self._clean_json(raw_text)
            result = json.loads(clean_json)

            # Override with detected design target
            if detected_target and not result.get("design_target"):
                result["design_target"] = detected_target

            # Parse iterations if present
            iterations = []
            for iter_data in result.get("iterations", []):
                iterations.append(
                    IterationPlan(
                        iteration=iter_data.get("iteration", 1),
                        name=iter_data.get("name", ""),
                        features=iter_data.get("features", []),
                        buildable_now=iter_data.get("buildable_now", False),
                    )
                )

            # HARD ENFORCEMENT: Never READY_TO_BUILD on first message
            # The AI sometimes ignores the system prompt, so we enforce it here
            status = result.get("status", "NEEDS_INPUT")
            if status == "READY_TO_BUILD" and len(conversation) == 1:
                console.print(
                    "[yellow][AI-ARCHITECT] Overriding READY_TO_BUILD on first message - "
                    "must ask at least one question first[/yellow]"
                )
                status = "NEEDS_CONFIRMATION"
                # If AI didn't provide a question, generate a default one
                if not result.get("question"):
                    result["question"] = (
                        "I can build that! Before I start, any specific preferences? "
                        "(e.g., color theme, additional features, design style)"
                    )
                    result["speech"] = "I can build that. Any specific preferences before I start?"

            return ConsultantResponse(
                status=status,
                question=result.get("question"),
                proposed_stack=result.get("proposed_stack"),
                design_target=result.get("design_target"),
                speech=result.get("speech", "Please provide more details."),
                features=result.get("features", []),
                confidence=result.get("confidence", 0.5),
                iterations=iterations,
                total_iterations=result.get("total_iterations", 1),
                current_iteration=result.get("current_iteration", 1),
            )

        except (json.JSONDecodeError, KeyError) as e:
            console.print(f"[red][AI-ARCHITECT] Parse error: {e}[/red]")
            return ConsultantResponse(
                status="NEEDS_INPUT",
                question="I couldn't understand. Please rephrase.",
                speech="Please rephrase your request.",
                confidence=0.0,
            )

    def get_build_prompt(self, conversation: list[dict]) -> str:
        """
        Extract the final build prompt from conversation history.

        Combines all user messages into a coherent build request.

        Args:
            conversation: The full conversation history.

        Returns:
            The combined build prompt for the Architect.
        """
        user_messages = [
            msg.get("content", "") for msg in conversation if msg.get("role") == "user"
        ]

        # Skip confirmation messages
        confirmation_keywords = ["yes", "ok", "proceed", "go", "sure", "build"]
        filtered = [
            msg
            for msg in user_messages
            if not any(msg.lower().strip() == kw for kw in confirmation_keywords)
        ]

        return " ".join(filtered)

    def get_design_target(self, conversation: list[dict]) -> str | None:
        """
        Extract design target from conversation history.

        Args:
            conversation: The full conversation history.

        Returns:
            Design target if found (LINKEDIN, TWITTER, etc.)
        """
        for msg in conversation:
            content = msg.get("content", "")
            target = detect_design_target(content)
            if target:
                return target
        return None
