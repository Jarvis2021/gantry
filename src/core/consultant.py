# -----------------------------------------------------------------------------
# THE CTO CONSULTANT - V6.5 INTERROGATOR
# -----------------------------------------------------------------------------
# Responsibility: Analyze user requests and decide if we have enough info to
# build, or if we need to ask clarifying questions.
#
# The Consultation Loop:
# Voice -> CTO Proposal -> User Feedback -> Final Spec -> "Proceed" -> Build
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


class ConsultantResponse(BaseModel):
    """
    The CTO's analysis and recommendation.

    status: NEEDS_INPUT | READY_TO_BUILD | NEEDS_CONFIRMATION
    """

    status: str  # NEEDS_INPUT, READY_TO_BUILD, NEEDS_CONFIRMATION
    question: str | None = None  # Question to ask user (if NEEDS_INPUT)
    proposed_stack: str | None = None  # Recommended tech stack
    design_target: str | None = None  # Detected famous app clone
    speech: str  # TTS-friendly summary
    features: list[str] = []  # Proposed features
    confidence: float = 0.0  # How confident we are (0-1)


# =============================================================================
# CTO SYSTEM PROMPT
# =============================================================================

CTO_SYSTEM_PROMPT = """You are the Gantry CTO - a Senior Software Architect who reviews requirements before building.

YOUR MISSION:
Analyze the user's request and determine if you have enough information to build a production-ready application.

DECISION TREE:

1. **CHECK CLARITY**:
   - Is the request too vague? (e.g., "Build an app", "Make something cool")
   - If YES → status: NEEDS_INPUT, ask "What kind of app? Social, productivity, e-commerce?"

2. **CHECK STACK**:
   - Did they specify a tech stack?
   - If NO → Recommend the best stack based on the app type, but ASK for confirmation
   - status: NEEDS_CONFIRMATION, question: "I recommend Next.js with Tailwind for this. Proceed?"

3. **CHECK DESIGN TARGET**:
   - Are they asking to clone a famous app? (LinkedIn, Twitter, Instagram, etc.)
   - If YES → Acknowledge it: "I'll replicate the LinkedIn interface with exact colors and layout."

4. **READY TO BUILD**:
   - If request is CLEAR + STACK is confirmed or obvious + user says "yes"/"proceed"/"build"/"go"
   - status: READY_TO_BUILD

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
  "confidence": 0.0 to 1.0
}

FAMOUS APP DESIGN TARGETS:
- LINKEDIN: Professional network, blue (#0a66c2), three-column layout
- TWITTER: Microblogging, dark theme, timeline feed
- INSTAGRAM: Photo sharing, stories, grid layout
- FACEBOOK: Social network, blue navbar, news feed
- SLACK: Team chat, channel sidebar, threaded messages
- SPOTIFY: Music streaming, dark theme, now-playing bar
- NOTION: Note-taking, block editor, sidebar pages
- AIRBNB: Listings, search, card grid

EXAMPLES:

User: "Build an app"
→ {"status": "NEEDS_INPUT", "question": "What kind of app would you like? Social, productivity, e-commerce, or something else?", "speech": "I need more details. What kind of app?", "confidence": 0.1}

User: "Build a LinkedIn clone"
→ {"status": "NEEDS_CONFIRMATION", "question": "I'll create a LinkedIn clone with Next.js and Tailwind, matching the exact blue theme and three-column layout. Shall I proceed?", "proposed_stack": "next.js", "design_target": "LINKEDIN", "speech": "I can build a LinkedIn clone with Next.js. Shall I proceed?", "features": ["Login page", "Feed view", "Profile cards", "Post composer"], "confidence": 0.85}

User: "Yes, go ahead"
→ {"status": "READY_TO_BUILD", "speech": "Copy. Clone protocol initiated. Building LinkedIn interface.", "confidence": 1.0}
"""


class Consultant:
    """
    The CTO Consultant that manages the consultation loop.

    Decides whether to build or ask for clarification.
    """

    def __init__(self, api_key: str | None = None, region: str = BEDROCK_REGION) -> None:
        """Initialize the Consultant with Bedrock credentials."""
        self._api_key = api_key or os.getenv("BEDROCK_API_KEY")
        self._region = region
        self._endpoint = f"https://bedrock-runtime.{self._region}.amazonaws.com"

        if not self._api_key:
            raise ArchitectError("BEDROCK_API_KEY not set")

        console.print("[green][CTO] Consultant online[/green]")

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
        console.print("[cyan][CTO] Analyzing request...[/cyan]")

        # Check for design target in latest user message
        latest_user_msg = ""
        for msg in reversed(conversation):
            if msg.get("role") == "user":
                latest_user_msg = msg.get("content", "")
                break

        detected_target = detect_design_target(latest_user_msg)
        if detected_target:
            console.print(f"[cyan][CTO] Detected clone target: {detected_target}[/cyan]")

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
            console.print("[green][CTO] User confirmed. Ready to build.[/green]")

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

        try:
            response = requests.post(url, headers=headers, json=body, timeout=30)

            if response.status_code != 200:
                console.print(f"[red][CTO] API error: {response.status_code}[/red]")
                return ConsultantResponse(
                    status="NEEDS_INPUT",
                    question="I'm having trouble. Please rephrase your request.",
                    speech="Connection issue. Please try again.",
                    confidence=0.0,
                )

            response_body = response.json()
            raw_text = response_body["content"][0]["text"]

            # Parse JSON response
            clean_json = self._clean_json(raw_text)
            result = json.loads(clean_json)

            # Override with detected design target
            if detected_target and not result.get("design_target"):
                result["design_target"] = detected_target

            return ConsultantResponse(
                status=result.get("status", "NEEDS_INPUT"),
                question=result.get("question"),
                proposed_stack=result.get("proposed_stack"),
                design_target=result.get("design_target"),
                speech=result.get("speech", "Please provide more details."),
                features=result.get("features", []),
                confidence=result.get("confidence", 0.5),
            )

        except requests.RequestException as e:
            console.print(f"[red][CTO] Request failed: {e}[/red]")
            return ConsultantResponse(
                status="NEEDS_INPUT",
                question="Connection failed. Please try again.",
                speech="Connection error.",
                confidence=0.0,
            )
        except (json.JSONDecodeError, KeyError) as e:
            console.print(f"[red][CTO] Parse error: {e}[/red]")
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
