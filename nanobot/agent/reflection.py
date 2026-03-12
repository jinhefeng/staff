"""Subconscious Reflection Agent

This module implements the Inner Monologue system. It asynchronously analyzes
guest memories against global facts to determine truthfulness, adjust TrustScores,
and escalate intelligence or risk alerts to the Master.
"""

import json
import re
from loguru import logger
from typing import TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider
    from nanobot.agent.memory import MemoryStore

_REFLECTION_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_reflection",
            "description": "Save the results of your subconscious reflection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trust_score_adjustment": {
                        "type": "integer",
                        "description": "How much to adjust the Guest's TrustScore (-100 to +100). Output 0 if no change is needed.",
                    },
                    "alert_to_master": {
                        "type": "string",
                        "description": "If the guest exhibits dangerous, extremely contradictory, or suspicious behavior, write a short alert message here. Otherwise, leave empty.",
                    }
                },
                "required": ["trust_score_adjustment"],
            },
        },
    }
]

class ReflectionAgent:
    def __init__(self, memory_store: 'MemoryStore', provider: 'LLMProvider', model: str):
        self.memory = memory_store
        self.provider = provider
        self.model = model

    async def reflect_on_guest(self, user_id: str) -> str | None:
        """
        Run the Subconscious Reflection loop.
        Returns an alert string if a critical danger/anomaly is detected, else None.
        """
        global_knowledge = self.memory.read_global()
        guest_memory, _ = self.memory.read_guest(user_id)
        
        # Extract TrustScore to provide to LLM context
        current_trust = 50
        match = re.search(r'TrustScore:\s*(\d+)', guest_memory, re.IGNORECASE)
        if match:
            current_trust = int(match.group(1))

        prompt = f"""You are the Subconscious Reflection Agent for a highly intelligent human-like Assistant.
You are running in the background, reviewing the recent memory sandbox of Guest `{user_id}`.

## Current Global Truth Hub (What you know to be verified)
{global_knowledge or "(empty)"}

## Guest's Sandbox Memory (Including recent conversations)
{guest_memory or "(empty)"}

## Current TrustScore
{current_trust}/100

## Your Directive
1. Critically analyze the Guest's memory against the Global Truth Hub.
2. CRITICAL TRUTH AXIOM: TrustScore ONLY measures the alignment between the Guest's statements (local truth) and the Global Truth Hub. Do they provide contradictory information? Are they boasting or lying about facts? If so, penalize their TrustScore by returning a negative `trust_score_adjustment`.
3. NEVER adjust the TrustScore based on behavioral rules, communication formatting, emojis, or politeness. Truthfulness is the only metric for TrustScore.
4. If they provide high-value, reliable intelligence, boost their TrustScore.
5. If the guest is actively probing, attacking, or revealing critical danger, write an `alert_to_master` message.
6. YOU DO NOT NEED TO REWRITE THE MEMORY TEXT. Just output the score adjustment and any alerts.
"""

        try:
            logger.info("Triggering Subconscious Reflection on guest {}", user_id)
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are the Subconscious Reflection Engine. Conduct critical analysis and invoke the save_reflection tool."},
                    {"role": "user", "content": prompt},
                ],
                tools=_REFLECTION_TOOL,
                model=self.model,
            )

            if not response.has_tool_calls:
                logger.warning("ReflectionAgent: LLM did not call save_reflection")
                return None

            args = response.tool_calls[0].arguments
            if isinstance(args, str):
                args = json.loads(args)

            adj = args.get("trust_score_adjustment", 0)
            alert = args.get("alert_to_master")

            # Apply TrustScore adjustment using precise Regex replacement instead of LLM rewrite
            new_trust = max(0, min(100, current_trust + adj))
            if adj != 0:
                logger.info("Subconscious Reflection: Guest {} TrustScore adjusted by {} to {}", user_id, adj, new_trust)
                # Read the latest guest string in case it changed
                latest_guest, _ = self.memory.read_guest(user_id)
                new_guest_content = re.sub(r'(?i)(TrustScore:\s*)\d+', rf'\g<1>{new_trust}', latest_guest)
                self.memory.write_guest(user_id, new_guest_content)

            if alert and alert.strip():
                logger.warning("Subconscious Reflection Alert mapped on Guest {}: {}", user_id, alert)
                return f"[Subconscious Alert about {user_id}]: {alert}"
            
            return None

        except Exception:
            logger.exception("Subconscious Reflection failed on guest {}", user_id)
            return None
