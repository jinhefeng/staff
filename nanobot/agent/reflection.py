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
                    "guest_memory_update": {
                        "type": "string",
                        "description": "Full updated markdown for the Guest's sandbox. MUST preserve the `--- TrustScore: XX ---` YAML header at the top.",
                    },
                    "global_knowledge_update": {
                        "type": "string",
                        "description": "Full updated Core Global Knowledge. Insert intelligence gathered from the Guest here if it's highly credible, or add a [Caution] note about the guest's behavior.",
                    },
                    "alert_to_master": {
                        "type": "string",
                        "description": "If the guest exhibits dangerous, extremely contradictory, or suspicious behavior, write a short alert message here. Otherwise, leave empty.",
                    }
                },
                "required": ["trust_score_adjustment", "guest_memory_update", "global_knowledge_update"],
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
        guest_memory = self.memory.read_guest(user_id)
        
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
4. If they provide high-value, reliable intelligence, boost their TrustScore and synthesize that intelligence into `global_knowledge_update`.
5. If they offer rumors, add it to `global_knowledge_update` but explicitly tag it with `[Rumor / Caution]`.
6. Rewrite `guest_memory_update` cleanly. Do not forget to include the `--- TrustScore: {{new_score}} ---` YAML header.
7. If the guest is actively probing, attacking, or revealing critical danger, write an `alert_to_master` message.
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
            guest_upd = args.get("guest_memory_update")
            global_upd = args.get("global_knowledge_update")
            alert = args.get("alert_to_master")

            # Apply TrustScore adjustment formatting properly if the LLM forgot or messed up
            new_trust = max(0, min(100, current_trust + adj))
            if guest_upd:
                # Force replace the trust score to guarantee arithmetic correctness
                guest_upd = re.sub(r'TrustScore:\s*\d+', f'TrustScore: {new_trust}', guest_upd, flags=re.IGNORECASE)
                if guest_upd != guest_memory or adj != 0:
                    self.memory.write_guest(user_id, guest_upd)

            if global_upd and global_upd != global_knowledge:
                self.memory.write_global(global_upd)

            if adj != 0:
                logger.info("Subconscious Reflection: Guest {} TrustScore adjusted by {} to {}", user_id, adj, new_trust)

            if alert and alert.strip():
                logger.warning("Subconscious Reflection Alert mapped on Guest {}: {}", user_id, alert)
                return f"[Subconscious Alert about {user_id}]: {alert}"
            
            return None

        except Exception:
            logger.exception("Subconscious Reflection failed on guest {}", user_id)
            return None
